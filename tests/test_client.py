import json

import httpx
import pytest

from lb_scrobbler.client import send_one
from lb_scrobbler.store import Store
from lb_scrobbler.tracking import Sample, Tracker


@pytest.fixture
def queued(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    tracker = Tracker()
    for second in range(11):
        payload = tracker.observe(
            Sample('playing', 'Track', 'Artist', '', 20, second), 1000 + second
        )
        store.checkpoint(tracker, payload)
    yield store
    store.close()


def test_success_sends_original_payload_and_acknowledges(queued):
    def respond(request):
        payload = json.loads(request.content)
        assert request.url.path == '/1/submit-listens'
        assert payload['listen_type'] == 'single'
        assert payload['payload'][0]['listened_at'] == 1000
        assert payload['payload'][0]['track_metadata']['artist_name'] == 'Artist'
        return httpx.Response(200)

    with httpx.Client(
        base_url='https://api.listenbrainz.org/1/',
        transport=httpx.MockTransport(respond),
    ) as http:
        send_one(queued, http, 2000)
    assert queued.next(3000) is None


@pytest.mark.parametrize(
    'status,headers,delay,blocked',
    [
        (429, {'X-RateLimit-Reset-In': '90'}, 90, False),
        (503, {}, 10, False),
        (401, {}, 300, False),
        (400, {}, 10, True),
    ],
)
def test_errors_retain_payload_and_apply_retry_policy(
    queued, status, headers, delay, blocked
):
    original = queued.next(2000)[1]
    with httpx.Client(
        base_url='https://api.listenbrainz.org/1/',
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, headers=headers)
        ),
    ) as http:
        assert send_one(queued, http, 2000) == delay
    assert queued.next(2000) is None
    assert queued.status()['blocked'] == int(blocked)
    if blocked:
        queued.retry()
    assert queued.next(2000 + delay)[1] == original


def test_network_failure_retains_original_listen(queued):
    def disconnect(request):
        raise httpx.ReadTimeout('timeout', request=request)

    original = queued.next(2000)[1]
    with httpx.Client(
        base_url='https://api.listenbrainz.org/1/',
        transport=httpx.MockTransport(disconnect),
    ) as http:
        assert send_one(queued, http, 2000) == 10
    assert queued.next(2010)[1] == original


@pytest.mark.parametrize('value', ['nan', 'inf', '-5', 'invalid'])
def test_invalid_rate_limit_delay_uses_finite_backoff(queued, value):
    with httpx.Client(
        base_url='https://api.listenbrainz.org/1/',
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, headers={'Retry-After': value})
        ),
    ) as http:
        assert send_one(queued, http, 2000) == 60
    assert queued.next(2059) is None
    assert queued.next(2060) is not None
