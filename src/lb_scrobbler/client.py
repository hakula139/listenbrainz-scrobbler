"""Send queued listens without blocking the playback sampler."""

import json
import logging
import math
import time
from contextlib import closing
from pathlib import Path
from threading import Event
from typing import cast

import httpx

from .playback import Playback, PlaybackState
from .store import Store


logger = logging.getLogger(__name__)


API = 'https://api.listenbrainz.org/1/'


def client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API,
        headers={'Authorization': f'Token {token}'},
        timeout=10,
        follow_redirects=False,
    )


def validate_token(token: str) -> str:
    with client(token) as http:
        response = http.get('validate-token')
        if response.status_code != 200:
            raise RuntimeError(f'Token validation failed: HTTP {response.status_code}')
        data = response.json()
        if not data.get('valid') or not isinstance(data.get('user_name'), str):
            raise RuntimeError('ListenBrainz token is invalid')
        return cast(str, data['user_name'])


def send_one(store: Store, http: httpx.Client, now: float) -> float:
    """Retain failed listens and return only an API-wide cooldown."""
    row = store.next(now)
    if row is None:
        return 0
    key, payload, attempts = row
    delay: float = min(900, 10 * 2 ** min(attempts, 7))
    try:
        response = http.post(
            'submit-listens',
            json={
                'listen_type': 'single',
                'payload': [json.loads(payload)],
            },
        )
    except httpx.TransportError:
        store.fail(key, 'Network request failed', now + delay)
        logger.warning(
            'Submission failed for listen %s: network error (retry in %.0f s)',
            key,
            delay,
        )
        return 0
    match response.status_code:
        case 200:
            store.acknowledge(key)
            logger.info('Submitted listen %s', key)
            return 0
        case 429:
            delay = rate_limit_delay(response)
        case 401 | 403:
            delay = 300

    blocked = response.status_code in (400, 404, 413, 422)
    error = f'HTTP {response.status_code}'
    store.fail(key, error, now + delay, blocked)
    if blocked:
        logger.warning('Submission blocked for listen %s: %s', key, error)
    else:
        logger.warning(
            'Submission failed for listen %s: %s (retry in %.0f s)', key, error, delay
        )
    return api_cooldown(response)


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
    def __init__(self, playback: PlaybackState) -> None:
        self.playback = playback
        self.generation = 0
        self.sent_generation = 0
        self.attempts = 0
        self.retry_at = 0.0
        self.refresh_at = 0.0
        self.identity: tuple[str, str] | None = None
        self.blocked = False
        self.announced = False
        self.synchronized = False

    def update_generation(self, generation: int) -> None:
        if generation != self.generation:
            self.generation = generation
            self.attempts = 0
            self.retry_at = 0
            self.blocked = False

    def send(self, http: httpx.Client, now: float) -> float:
        """Update or clear fresh playback and return an API-wide cooldown."""
        began = time.monotonic()
        current = self.playback.current(now)
        self.update_generation(current.generation if current else 0)
        if self.blocked or now < self.retry_at:
            return 0
        if current is None:
            return self.clear(http, now) if self.announced else 0
        if not self.synchronized:
            # Duplicate updates return success without renewing the server's TTL.
            # Clear our existing entry when its actual expiry is unknown.
            cooldown = self.clear(http, now)
            if not self.synchronized:
                return cooldown
            now += time.monotonic() - began
            current = self.playback.current(now)
            if current is None:
                return 0
            self.update_generation(current.generation)
        if self.sent_generation == self.generation and now < self.refresh_at:
            return 0
        return self.submit(http, current, now)

    def submit(self, http: httpx.Client, current: Playback, now: float) -> float:
        began = time.monotonic()
        try:
            response = http.post(
                'submit-listens',
                json={
                    'listen_type': 'playing_now',
                    'payload': [{'track_metadata': current.sample.metadata()}],
                },
            )
        except httpx.TransportError:
            # The server may have accepted the update before the response was lost.
            self.announced = True
            self.synchronized = False
            return self.fail(None, now)
        if response.status_code != 200:
            if response.status_code >= 500:
                self.announced = True
                self.synchronized = False
            return self.fail(response, now)

        identity = (current.sample.title, current.sample.artist)
        # ListenBrainz ignores same-title/artist updates until their TTL expires.
        if identity != self.identity or now >= self.refresh_at:
            completed = now + (time.monotonic() - began)
            self.refresh_at = completed + math.ceil(current.sample.duration) + 1
        self.identity = identity
        self.sent_generation = self.generation
        self.attempts = 0
        self.announced = True
        logger.info('Sent playing-now update for session %s', current.session_id)
        return 0

    def clear(self, http: httpx.Client, now: float) -> float:
        self.synchronized = False
        try:
            response = http.post(
                'playing-now/delete', json={'client': 'listenbrainz-scrobbler'}
            )
        except httpx.TransportError:
            return self.fail(None, now)
        if response.status_code not in (200, 404):
            return self.fail(response, now)

        self.announced = False
        self.synchronized = True
        self.identity = None
        self.refresh_at = 0
        logger.info('Cleared playing-now update')
        return 0

    def fail(self, response: httpx.Response | None, now: float) -> float:
        delay: float = min(900, 10 * 2 ** min(self.attempts, 7))
        cooldown = api_cooldown(response) if response is not None else 0
        self.retry_at = now + (cooldown or delay)
        self.attempts += 1
        self.blocked = response is not None and response.status_code in (
            400,
            404,
            413,
            422,
        )
        error = (
            f'HTTP {response.status_code}' if response is not None else 'network error'
        )
        if self.blocked:
            logger.warning('Playing-now update blocked: %s', error)
        else:
            logger.warning(
                'Playing-now update failed: %s (retry in %.0f s)',
                error,
                cooldown or delay,
            )
        return cooldown


def sender(path: Path, token: str, stop: Event, playback: PlaybackState) -> None:
    with closing(Store(path)) as store, client(token) as http:
        playing = PlayingNowSender(playback)
        while not stop.is_set():
            delay = playing.send(http, time.monotonic())
            if not delay and not stop.is_set():
                delay = send_one(store, http, time.time())
            stop.wait(delay or 2)
