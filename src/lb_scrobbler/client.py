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
    """Return the retry delay while preserving failed listens in the outbox."""
    row = store.next(now)
    if row is None:
        return 2
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
        return delay
    match response.status_code:
        case 200:
            store.acknowledge(key)
            logger.info('Submitted listen %s', key)
            return 1
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
    return delay


def rate_limit_delay(response: httpx.Response) -> float:
    raw = response.headers.get('Retry-After') or response.headers.get(
        'X-RateLimit-Reset-In', '60'
    )
    try:
        delay = float(raw)
    except ValueError:
        return 60
    return max(1, delay) if math.isfinite(delay) and delay >= 0 else 60


def sender(path: Path, token: str, stop: Event) -> None:
    with closing(Store(path)) as store, client(token) as http:
        while not stop.is_set():
            stop.wait(send_one(store, http, time.time()))
