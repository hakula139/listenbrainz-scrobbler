"""Send queued listens without blocking the playback sampler."""

import json
import logging
import time

import httpx

from .store import Store


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
        return data['user_name']


def send_one(store: Store, http: httpx.Client, now: float) -> float:
    """Return the retry delay while preserving failed listens in the outbox."""
    row = store.next(now)
    if row is None:
        return 2
    key, payload, attempts = row
    delay = min(900, 10 * 2 ** min(attempts, 7))
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
        return delay
    if response.status_code == 200:
        store.acknowledge(key)
        logging.info('Submitted listen %s', key)
        return 1
    if response.status_code == 429:
        raw = response.headers.get('Retry-After') or response.headers.get(
            'X-RateLimit-Reset-In', '60'
        )
        try:
            delay = max(1, float(raw))
            if not 0 < delay < float('inf'):
                delay = 60
        except ValueError:
            delay = 60
    elif response.status_code in (401, 403):
        delay = 300
    blocked = response.status_code in (400, 404, 413, 422)
    error = f'HTTP {response.status_code}'
    store.fail(key, error, now + delay, blocked)
    logging.warning(
        'Submission failed: %s%s', error, '; retained for retry' if blocked else ''
    )
    return delay


def sender(path, token: str, stop):
    store = Store(path)
    try:
        with client(token) as http:
            while not stop.is_set():
                stop.wait(send_one(store, http, time.time()))
    finally:
        store.close()
