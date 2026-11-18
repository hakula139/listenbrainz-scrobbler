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


@dataclass(frozen=True)
class Failure:
    error: str
    blocked: bool
    cooldown: float
    retry_in: float


def classify(response: httpx.Response | None, attempts: int) -> Failure:
    delay = retry_delay(attempts)
    if response is None:
        return Failure('Network request failed', False, 0, delay)

    cooldown = api_cooldown(response)
    return Failure(
        f'HTTP {response.status_code}',
        response.status_code in BLOCKED_STATUS_CODES,
        cooldown,
        cooldown or delay,
    )


class PlayingNowSender:
    """Keep this client's playing-now entry fresh and clear only its own entry.

    ListenBrainz ignores a repeated title/artist update while the entry is live.
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

    def current_playback(self, now: float) -> Playback | None:
        current = self.playback.current(now)
        generation = current.generation if current else 0
        if generation != self.generation:
            self.generation = generation
            self.attempts = 0
            self.retry_at = 0.0
            self.blocked = False
        return current

    def send(self, http: httpx.Client) -> float:
        """Update or clear fresh playback and return an API-wide cooldown."""
        now = time.monotonic()
        current = self.current_playback(now)
        if self.blocked or now < self.retry_at:
            return 0

        if current is None:
            return self.clear(http) if self.title_artist is not None else 0

        if self.sent_generation == current.generation and now < self.refresh_at:
            return 0

        if self.title_artist == (current.sample.title, current.sample.artist):
            cooldown = self.clear(http)
            if self.title_artist is not None:
                return cooldown

            current = self.current_playback(time.monotonic())
            if current is None:
                return 0

        return self.submit(http, current)

    def submit(self, http: httpx.Client, current: Playback) -> float:
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
            return self.fail(response)

        self.refresh_at = time.monotonic() + math.ceil(current.sample.duration) + 1
        self.title_artist = (current.sample.title, current.sample.artist)
        self.sent_generation = current.generation
        self.attempts = 0
        logger.info('Sent playing-now update for session %s', current.session_id)
        return 0

    def clear(self, http: httpx.Client) -> float:
        response: httpx.Response | None
        try:
            response = http.post(
                'playing-now/delete', json={'client': SUBMISSION_CLIENT}
            )
        except httpx.TransportError:
            response = None

        if response is None or response.status_code not in (200, 404):
            return self.fail(response)

        self.title_artist = None
        self.sent_generation = 0
        logger.info('Cleared playing-now update')
        return 0

    def fail(self, response: httpx.Response | None) -> float:
        failure = classify(response, self.attempts)
        self.retry_at = time.monotonic() + failure.retry_in
        self.attempts += 1
        self.blocked = (
            response is not None
            and response.is_client_error
            and response.status_code != 408
            and not failure.cooldown
        )
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
            delay = playing.send(http)
            if not delay and not stop.is_set():
                delay = send_one(store, http, time.time())
            stop.wait(delay or SAMPLE_INTERVAL)
