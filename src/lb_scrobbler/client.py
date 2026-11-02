"""Submit listening history and current playback outside the sampler."""

import json
import logging
import math
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import httpx

from .playback import Playback, PlaybackState
from .store import Store
from .tracking import SAMPLE_INTERVAL, SUBMISSION_CLIENT


logger = logging.getLogger(__name__)


API = 'https://api.listenbrainz.org/1/'
BLOCKED_STATUS_CODES = frozenset({400, 404, 413, 422})


@dataclass(frozen=True)
class Failure:
    error: str
    blocked: bool
    cooldown: float
    retry_in: float


def classify(response: httpx.Response | None, attempts: int) -> Failure:
    delay = retry_delay(attempts)
    cooldown = api_cooldown(response) if response is not None else 0

    if response is None:
        error = 'Network request failed'
        blocked = False
    else:
        error = f'HTTP {response.status_code}'
        blocked = response.status_code in BLOCKED_STATUS_CODES
    return Failure(error, blocked, cooldown, cooldown or delay)


def api_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API,
        headers={'Authorization': f'Token {token}'},
        timeout=10,
        follow_redirects=False,
    )


def validate_token(token: str) -> str:
    with api_client(token) as http:
        response = http.get('validate-token')
        if response.status_code != 200:
            raise RuntimeError(f'Token validation failed: HTTP {response.status_code}')

        data = response.json()
        user_name = data.get('user_name')
        if not data.get('valid') or not isinstance(user_name, str):
            raise RuntimeError('ListenBrainz token is invalid')
        return user_name


def send_one(store: Store, http: httpx.Client, now: float) -> float:
    """Retain failed listens and return only an API-wide cooldown."""
    pending = store.next(now)
    if pending is None:
        return 0

    response: httpx.Response | None
    try:
        response = http.post(
            'submit-listens',
            json={
                'listen_type': 'single',
                'payload': [json.loads(pending.payload)],
            },
        )
    except httpx.TransportError:
        response = None

    if response is not None and response.status_code == 200:
        store.acknowledge(pending.id)
        logger.info('Submitted listen %s', pending.id)
        return 0

    failure = classify(response, pending.attempts)
    store.fail(pending.id, failure.error, now + failure.retry_in, failure.blocked)
    if failure.blocked:
        logger.warning(
            'Submission blocked for listen %s: %s', pending.id, failure.error
        )
    else:
        logger.warning(
            'Submission failed for listen %s: %s (retry in %.0f s)',
            pending.id,
            failure.error,
            failure.retry_in,
        )
    return failure.cooldown


def retry_delay(attempts: int) -> float:
    return float(min(900, 10 * 2 ** min(attempts, 7)))


def api_cooldown(response: httpx.Response) -> float:
    match response.status_code:
        case 429:
            return rate_limit_delay(response)
        case 401 | 403:
            return 300
        case _:
            return 0


def rate_limit_delay(response: httpx.Response) -> float:
    raw = response.headers.get('Retry-After') or response.headers.get(
        'X-RateLimit-Reset-In', '60'
    )
    try:
        delay = float(raw)
    except ValueError:
        return 60
    return max(1, delay) if math.isfinite(delay) and delay >= 0 else 60


class PlayingNowSender:
    """Keep this client's playing-now entry fresh and clear only its own entry.

    ListenBrainz ignores a repeated title/artist update until the entry expires, and a
    lost response leaves acceptance unknown, so the sender clears and republishes
    whenever the entry's server expiry is uncertain.
    """

    def __init__(self, playback: PlaybackState) -> None:
        self.playback = playback

        self.generation = 0
        self.sent_generation = 0

        self.attempts = 0
        self.retry_at = 0.0
        self.blocked = False

        self.title_artist: tuple[str, str] | None = None
        self.refresh_at = 0.0

        self.announced = False
        self.synchronized = False

    def update_generation(self, generation: int) -> None:
        if generation != self.generation:
            self.generation = generation
            self.attempts = 0
            self.retry_at = 0.0
            self.blocked = False

    def current_playback(self, now: float) -> Playback | None:
        current = self.playback.current(now)
        self.update_generation(current.generation if current else 0)
        return current

    def send(self, http: httpx.Client, now: float) -> float:
        """Update or clear fresh playback and return an API-wide cooldown."""
        began = time.monotonic()
        current = self.current_playback(now)
        if self.blocked or now < self.retry_at:
            return 0

        if current is None:
            return self.clear(http, now) if self.announced else 0

        if not self.synchronized:
            cooldown = self.clear(http, now)
            if not self.synchronized:
                return cooldown

            now += time.monotonic() - began
            current = self.current_playback(now)
            if current is None:
                return 0

        if self.sent_generation == self.generation and now < self.refresh_at:
            return 0
        return self.submit(http, current, now)

    def submit(self, http: httpx.Client, current: Playback, now: float) -> float:
        began = time.monotonic()
        response: httpx.Response | None
        try:
            response = http.post(
                'submit-listens',
                json={
                    'listen_type': 'playing_now',
                    'payload': [{'track_metadata': current.sample.metadata()}],
                },
            )
        except httpx.TransportError:
            response = None

        if response is None or response.status_code != 200:
            # The server may have accepted the update before the response was lost.
            if response is None or response.status_code >= 500:
                self.announced = True
                self.synchronized = False
            return self.fail(classify(response, self.attempts), now)

        title_artist = (current.sample.title, current.sample.artist)
        if title_artist != self.title_artist or now >= self.refresh_at:
            completed = now + (time.monotonic() - began)
            self.refresh_at = completed + math.ceil(current.sample.duration) + 1
        self.title_artist = title_artist
        self.sent_generation = self.generation
        self.attempts = 0
        self.announced = True
        logger.info('Sent playing-now update for session %s', current.session_id)
        return 0

    def clear(self, http: httpx.Client, now: float) -> float:
        self.synchronized = False
        try:
            response = http.post(
                'playing-now/delete', json={'client': SUBMISSION_CLIENT}
            )
        except httpx.TransportError:
            return self.fail(classify(None, self.attempts), now)
        if response.status_code not in (200, 404):
            return self.fail(classify(response, self.attempts), now)

        self.announced = False
        self.synchronized = True
        self.title_artist = None
        self.refresh_at = 0.0
        logger.info('Cleared playing-now update')
        return 0

    def fail(self, failure: Failure, now: float) -> float:
        self.retry_at = now + failure.retry_in
        self.attempts += 1
        self.blocked = failure.blocked
        if self.blocked:
            logger.warning('Playing-now update blocked: %s', failure.error)
        else:
            logger.warning(
                'Playing-now update failed: %s (retry in %.0f s)',
                failure.error,
                failure.retry_in,
            )
        return failure.cooldown


def submit_listens(
    path: Path, token: str, stop: Event, playback: PlaybackState
) -> None:
    with closing(Store(path)) as store, api_client(token) as http:
        playing = PlayingNowSender(playback)
        while not stop.is_set():
            delay = playing.send(http, time.monotonic())
            if not delay and not stop.is_set():
                delay = send_one(store, http, time.time())
            stop.wait(delay or SAMPLE_INTERVAL)
