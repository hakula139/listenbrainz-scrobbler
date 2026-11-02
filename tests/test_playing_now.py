import json
import tomllib
from contextlib import closing, nullcontext
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import support
from packaging.version import Version

from lb_scrobbler.client import PlayingNowSender, submit_listens
from lb_scrobbler.playback import PlaybackState
from lb_scrobbler.store import Store
from lb_scrobbler.tracking import Tracker


with (Path(__file__).parents[1] / 'pyproject.toml').open('rb') as file:
    PROJECT_VERSION = tomllib.load(file)['project']['version']


@pytest.fixture(autouse=True)
def monotonic_clock(monkeypatch):
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', lambda: 0)


@pytest.fixture
def playback():
    return PlaybackState()


@pytest.fixture
def requests():
    return []


@pytest.fixture
def http(requests):
    def respond(request):
        requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200)

    with support.mock_http(respond) as client:
        yield client


def test_sends_metadata_without_timestamp_once_per_playback(playback, http, requests):
    playing = PlayingNowSender(playback)
    playback.update(support.session(), 10)
    playing.send(http, 10)
    playback.update(support.session(), 12)
    playing.send(http, 12)

    info = requests[1][1]['payload'][0]['track_metadata']['additional_info']
    sent_version = info.pop('submission_client_version')

    assert Version(sent_version) == Version(PROJECT_VERSION)

    assert requests == [
        ('/1/playing-now/delete', {'client': 'listenbrainz-scrobbler'}),
        (
            '/1/submit-listens',
            {
                'listen_type': 'playing_now',
                'payload': [
                    {
                        'track_metadata': {
                            'artist_name': 'Artist',
                            'track_name': 'Track',
                            'release_name': 'Album',
                            'additional_info': {
                                'duration_ms': 120000,
                                'media_player': 'Apple Music',
                                'submission_client': 'listenbrainz-scrobbler',
                            },
                        },
                    }
                ],
            },
        ),
    ]


@pytest.mark.parametrize('state', ['paused', 'unavailable', 'stopped', 'stale'])
def test_clears_own_notification_when_playback_ends(playback, http, requests, state):
    playing = PlayingNowSender(playback)
    playback.update(support.session(), 10)
    playing.send(http, 10)
    if state != 'stale':
        playback.update(support.session(state=state), 12)
    playing.send(http, 22)
    playing.send(http, 24)

    assert requests[-1] == (
        '/1/playing-now/delete',
        {'client': 'listenbrainz-scrobbler'},
    )
    assert len(requests) == 3

    playback.update(support.session(), 25)
    playing.send(http, 25)

    assert requests[-1][1]['listen_type'] == 'playing_now'
    assert len(requests) == 4


def test_startup_without_fresh_playback_does_not_clear_other_clients(
    playback, http, requests
):
    playing = PlayingNowSender(playback)
    playing.send(http, 10)
    playback.update(support.session(), 12)
    playing.send(http, 23)

    assert requests == []


def test_repeat_and_album_change_preserve_server_expiry(playback, http, requests):
    playing = PlayingNowSender(playback)
    playback.update(support.session(), 10)
    playing.send(http, 10)
    repeated = support.session(key='repeat')
    repeated.sample = replace(repeated.sample, album='Another album')
    playback.update(repeated, 120)
    playing.send(http, 120)
    playback.update(repeated, 130)
    playing.send(http, 130)
    assert len(requests) == 3

    playback.update(repeated, 131)
    playing.send(http, 131)

    assert len(requests) == 4
    assert (
        requests[-1][1]['payload'][0]['track_metadata']['release_name']
        == 'Another album'
    )


def test_blocked_playback_resumes_only_for_a_new_session(playback):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/playing-now/delete'):
            return httpx.Response(200)
        return httpx.Response(400)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        for now in range(10, 62, 2):
            playback.update(support.session(), now)
            playing.send(http, now)

        assert paths.count('/1/submit-listens') == 1

        playback.update(support.session(title='Next', key='next'), 62)
        playing.send(http, 62)

    assert paths.count('/1/submit-listens') == 2


def test_failed_old_track_is_replaced_and_current_failure_backs_off(playback):
    sent = []

    def respond(request):
        if request.url.path.endswith('/playing-now/delete'):
            return httpx.Response(200)
        sent.append(
            json.loads(request.content)['payload'][0]['track_metadata']['track_name']
        )
        return httpx.Response(503)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        playback.update(support.session(), 10)
        assert playing.send(http, 10) == 0
        playback.update(support.session(), 12)
        playing.send(http, 12)
        playback.update(support.session(title='Next', key='next'), 14)
        playing.send(http, 14)
        playback.update(support.session(title='Next', key='next'), 24)
        playing.send(http, 24)

    assert sent == ['Track', 'Next', 'Next']


def test_uncertain_submission_is_cleared_but_failed_clear_is_superseded(playback):
    paths = []

    def disconnect(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/playing-now/delete') and len(paths) != 3:
            return httpx.Response(200)
        raise httpx.ReadTimeout('timeout', request=request)

    playing = PlayingNowSender(playback)
    with support.mock_http(disconnect) as http:
        playback.update(support.session(), 10)
        playing.send(http, 10)
        playback.update(None, 12)
        playing.send(http, 12)
        playback.update(support.session(title='Next', key='next'), 14)
        playing.send(http, 14)

    assert paths == [
        '/1/playing-now/delete',
        '/1/submit-listens',
        '/1/playing-now/delete',
        '/1/playing-now/delete',
        '/1/submit-listens',
    ]


def test_clear_accepts_404_when_another_client_owns_notification(playback):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(404 if len(paths) == 3 else 200)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        playback.update(support.session(), 10)
        playing.send(http, 10)
        playback.update(None, 12)
        playing.send(http, 12)

        playback.update(support.session(title='Next', key='next'), 102)
        playing.send(http, 102)

    assert paths == [
        '/1/playing-now/delete',
        '/1/submit-listens',
        '/1/playing-now/delete',
        '/1/submit-listens',
    ]


@pytest.mark.parametrize(('status', 'cooldown'), [(429, 90), (401, 300)])
@pytest.mark.parametrize('endpoint', ['submit-listens', 'playing-now/delete'])
def test_worker_applies_shared_cooldown_before_queued_listens(
    tmp_path, playback, monkeypatch, status, cooldown, endpoint
):
    def respond(request):
        return httpx.Response(
            status if request.url.path.endswith(endpoint) else 200,
            headers={'Retry-After': '90'},
        )

    playback.update(support.session(), 10)
    queued = Mock()
    stop = Mock()
    stop.is_set.side_effect = [False, True]
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', lambda: 10)
    monkeypatch.setattr('lb_scrobbler.client.send_one', queued)

    with support.mock_http(respond) as http:
        monkeypatch.setattr(
            'lb_scrobbler.client.api_client', lambda _: nullcontext(http)
        )

        submit_listens(tmp_path / 'state.sqlite3', 'test-token', stop, playback)

    queued.assert_not_called()
    stop.wait.assert_called_once_with(cooldown)


def test_refresh_waits_for_server_expiry_after_slow_request(playback, monkeypatch):
    clock = [0]
    posted = []
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', lambda: clock[0])

    def respond(request):
        if request.url.path.endswith('/submit-listens'):
            posted.append(json.loads(request.content))
            clock[0] += 5
        return httpx.Response(200)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        playback.update(support.session(), 10)
        playing.send(http, 10)
        for now in range(12, 132, 2):
            playback.update(support.session(), now)
        playing.send(http, 131)
        assert len(posted) == 1

        playback.update(support.session(), 136)
        playing.send(http, 136)

    assert len(posted) == 2


def test_queued_network_backoff_does_not_delay_next_track(
    store_path, playback, monkeypatch
):
    current = support.session()
    tracker = Tracker(current)
    with closing(Store(store_path)) as store:
        store.checkpoint(tracker, current.payload())

    sent = []

    def respond(request):
        if request.url.path.endswith('/playing-now/delete'):
            return httpx.Response(200)
        payload = json.loads(request.content)
        sent.append(
            (
                payload['listen_type'],
                payload['payload'][0]['track_metadata']['track_name'],
            )
        )
        return httpx.Response(503 if payload['listen_type'] == 'single' else 200)

    clock = [10]
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('lb_scrobbler.client.time.time', lambda: 1990 + clock[0])
    playback.update(current, 10)
    stop = Mock()
    stop.is_set.side_effect = lambda: clock[0] >= 14

    def wait(delay):
        assert delay == 2
        clock[0] += delay
        playback.update(support.session(title='Next', key='next'), clock[0])

    stop.wait.side_effect = wait

    with support.mock_http(respond) as http:
        monkeypatch.setattr(
            'lb_scrobbler.client.api_client', lambda _: nullcontext(http)
        )

        submit_listens(store_path, 'test-token', stop, playback)

    assert sent == [
        ('playing_now', 'Track'),
        ('single', 'Track'),
        ('playing_now', 'Next'),
    ]

    with closing(Store(store_path)) as store:
        assert store.next(2009) is None
        assert json.loads(store.next(2010).payload)['listened_at'] == 1000


@pytest.mark.parametrize('failure', [None, 'transport', 'server'])
def test_unknown_existing_expiry_is_reset_before_publishing(
    playback, monkeypatch, failure
):
    clock = [60.0]
    cached = {'expires_at': 120.0, 'failure': failure}
    operations = []
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', lambda: clock[0])

    def respond(request):
        if request.url.path.endswith('/playing-now/delete'):
            assert json.loads(request.content) == {'client': 'listenbrainz-scrobbler'}
            cached['expires_at'] = 0
            operations.append('delete')
            return httpx.Response(200)

        operations.append('submit')
        # Match the server: a duplicate succeeds without refreshing expiry.
        if clock[0] >= cached['expires_at']:
            cached['expires_at'] = clock[0] + 120
        outcome = cached['failure']
        cached['failure'] = None
        if outcome == 'transport':
            raise httpx.ReadTimeout('response lost', request=request)
        if outcome == 'server':
            return httpx.Response(503)
        return httpx.Response(200)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        for now in range(60, 304, 2):
            clock[0] = now
            playback.update(support.session(), now)
            playing.send(http, now)
            if now > 70:
                # Two-second polling allows a brief interval at the TTL boundary.
                assert cached['expires_at'] >= now - 2

    assert operations[:2] == ['delete', 'submit']
    if failure:
        assert operations[:4] == ['delete', 'submit', 'delete', 'submit']


@pytest.mark.parametrize('failure', ['transport', 'server'])
def test_resynchronizing_unknown_acceptance_preserves_exponential_backoff(
    playback, failure
):
    submitted_at = []
    clock = [10]

    def respond(request):
        if request.url.path.endswith('/playing-now/delete'):
            return httpx.Response(200)
        submitted_at.append(clock[0])
        if failure == 'transport':
            raise httpx.ReadTimeout('response lost', request=request)
        return httpx.Response(503)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        for now in range(10, 82, 2):
            clock[0] = now
            playback.update(support.session(), now)
            playing.send(http, now)

    assert submitted_at == [10, 20, 40, 80]


@pytest.mark.parametrize('changed', [False, True])
def test_rechecks_current_playback_after_blocking_initial_clear(
    playback, monkeypatch, changed
):
    clock = [10]
    submitted = []
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', lambda: clock[0])

    def respond(request):
        if request.url.path.endswith('/playing-now/delete'):
            clock[0] = 22
            if changed:
                playback.update(support.session(title='Next', key='next'), clock[0])
        else:
            metadata = json.loads(request.content)['payload'][0]['track_metadata']
            submitted.append(metadata['track_name'])
        return httpx.Response(200)

    playing = PlayingNowSender(playback)
    with support.mock_http(respond) as http:
        playback.update(support.session(), 10)
        playing.send(http, 10)

    assert submitted == (['Next'] if changed else [])
