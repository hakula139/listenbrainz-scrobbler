import json

import httpx
import pytest
import support

from lb_scrobbler.client import send_one
from lb_scrobbler.tracking import Tracker


@pytest.fixture
def queued(store):
    session = support.session()
    store.checkpoint(Tracker(session), session.payload())

    return store


def test_success_sends_original_payload_and_acknowledges(queued):
    def respond(request):
        payload = json.loads(request.content)
        assert request.url.path == '/1/submit-listens'
        assert payload['listen_type'] == 'single'
        assert payload['payload'][0]['listened_at'] == 1000
        assert payload['payload'][0]['track_metadata']['artist_name'] == 'Artist'
        return httpx.Response(200)

    with support.mock_http(respond) as http:
        send_one(queued, http, 2000)

    assert queued.next(3000) is None


@pytest.mark.parametrize(
    ('status', 'headers', 'delay', 'cooldown', 'blocked'),
    [
        pytest.param(
            429, {'X-RateLimit-Reset-In': '90'}, 90, 90, False, id='rate-limit'
        ),
        pytest.param(503, {}, 10, 0, False, id='server-error'),
        pytest.param(401, {}, 300, 300, False, id='unauthorized'),
        pytest.param(400, {}, 10, 0, True, id='blocked'),
    ],
)
def test_errors_retain_payload_and_apply_retry_policy(
    queued, status, headers, delay, cooldown, blocked
):
    original = queued.next(2000).payload

    with support.mock_http(lambda _: httpx.Response(status, headers=headers)) as http:
        assert send_one(queued, http, 2000) == cooldown

    assert queued.next(2000) is None
    assert queued.status()['blocked'] == int(blocked)
    if blocked:
        queued.retry()
    assert queued.next(2000 + delay).payload == original


def test_network_failure_retains_original_listen(queued):
    def disconnect(request):
        raise httpx.ReadTimeout('timeout', request=request)

    original = queued.next(2000).payload

    with support.mock_http(disconnect) as http:
        assert send_one(queued, http, 2000) == 0

    assert queued.next(2010).payload == original


@pytest.mark.parametrize('value', ['nan', 'inf', '-5', 'invalid'])
def test_invalid_rate_limit_delay_uses_finite_backoff(queued, value):
    with support.mock_http(
        lambda _: httpx.Response(429, headers={'Retry-After': value})
    ) as http:
        assert send_one(queued, http, 2000) == 60

    assert queued.next(2059) is None
    assert queued.next(2060) is not None
