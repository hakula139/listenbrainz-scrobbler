import json
from contextlib import closing, nullcontext
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest
import support

from lb_scrobbler.client import PlayingNowSender, submit_listens
from lb_scrobbler.playback import PlaybackState
from lb_scrobbler.store import Store
from lb_scrobbler.tracking import SUBMISSION_CLIENT_VERSION, Tracker


SUBMIT = '/1/submit-listens'
DELETE = '/1/playing-now/delete'


@pytest.fixture
def clock(monkeypatch):
    clock = Mock(return_value=10)
    monkeypatch.setattr('lb_scrobbler.client.time.monotonic', clock)
    return clock


@pytest.fixture
def playback():
    return PlaybackState()


@pytest.fixture
def poll(playback, clock):
    sender = PlayingNowSender(playback)

    def observe(http, session, now):
        clock.return_value = now
        playback.update(session, now)
        return sender.send(http)

    return observe


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


def test_sends_metadata_without_timestamp_once_per_playback(poll, http, requests):
    current = support.session()

    poll(http, current, 10)
    poll(http, current, 12)

    assert requests == [
        (
            SUBMIT,
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
                                'submission_client_version': SUBMISSION_CLIENT_VERSION,
                            },
                        },
                    }
                ],
            },
        ),
    ]


@pytest.mark.parametrize(
    ('changes', 'paths'),
    [
        ({}, [SUBMIT, DELETE, SUBMIT]),
        ({'album': 'Another album'}, [SUBMIT, DELETE, SUBMIT]),
        ({'artist': 'Another artist'}, [SUBMIT, SUBMIT]),
        ({'title': 'Another title'}, [SUBMIT, SUBMIT]),
    ],
)
def test_new_session_clears_only_a_matching_title_and_artist(
    poll, http, requests, changes, paths
):
    current = support.session()
    following = support.session(key='next')
    following.sample = replace(current.sample, **changes)

    poll(http, current, 10)
    poll(http, following, 12)

    assert [path for path, _ in requests] == paths
    assert (
        requests[-1][1]['payload'][0]['track_metadata'] == following.sample.metadata()
    )


def test_refresh_waits_for_expiry_from_completion_of_slow_post(poll, clock):
    operations = []
    current = support.session()

    def respond(request):
        operations.append((clock(), request.url.path))
        if request.url.path == SUBMIT:
            clock.return_value += 5
        return httpx.Response(200)

    with support.mock_http(respond) as http:
        poll(http, current, 10)
        for now in range(16, 137, 2):
            poll(http, current, now)

    assert operations == [(10, SUBMIT), (136, DELETE), (136, SUBMIT)]


@pytest.mark.parametrize('changed', [False, True])
def test_rechecks_playback_after_a_slow_repeat_clear(playback, poll, clock, changed):
    posted = []

    def respond(request):
        if request.url.path == DELETE:
            clock.return_value += 12
            if changed:
                playback.update(support.session(title='Next', key='next'), clock())
        else:
            metadata = json.loads(request.content)['payload'][0]['track_metadata']
            posted.append(metadata['track_name'])
        return httpx.Response(200)

    with support.mock_http(respond) as http:
        poll(http, support.session(), 10)
        poll(http, support.session(key='repeat'), 12)

    assert posted == (['Track', 'Next'] if changed else ['Track'])


def test_repeat_retries_each_failed_request_without_repeating_a_successful_clear(poll):
    operations = []
    outcomes = iter([200, 503, 200, 503, 200])
    repeated = support.session(key='repeat')

    def respond(request):
        operations.append(request.url.path)
        return httpx.Response(next(outcomes))

    with support.mock_http(respond) as http:
        poll(http, support.session(), 10)
        for now in range(12, 62, 2):
            poll(http, repeated, now)

    assert operations == [SUBMIT, DELETE, DELETE, SUBMIT, SUBMIT]


@pytest.mark.parametrize('state', ['paused', 'unavailable', 'stopped', 'stale'])
def test_clears_own_notification_once_and_announces_on_resume(
    playback, http, requests, clock, state
):
    playing = PlayingNowSender(playback)
    current = support.session()
    playback.update(current, clock())
    playing.send(http)

    clock.return_value = 22
    if state != 'stale':
        playback.update(support.session(state=state), clock())
    playing.send(http)
    playing.send(http)
    playback.update(current, clock())
    playing.send(http)

    assert [path for path, _ in requests] == [SUBMIT, DELETE, SUBMIT]
    assert requests[1][1] == {'client': 'listenbrainz-scrobbler'}


def test_startup_without_fresh_playback_does_not_clear_other_clients(
    playback, http, requests, clock
):
    playing = PlayingNowSender(playback)

    playing.send(http)
    playback.update(support.session(), clock())
    clock.return_value += 11
    playing.send(http)

    assert requests == []


@pytest.mark.parametrize('status', [None, 408, 503])
def test_submission_retries_directly_with_bounded_backoff(poll, clock, status):
    operations = []
    current = support.session()

    def respond(request):
        operations.append((clock(), request.url.path))
        if status is None:
            raise httpx.ReadTimeout('response lost', request=request)
        return httpx.Response(status)

    with support.mock_http(respond) as http:
        for now in range(10, 3090, 10):
            poll(http, current, now)
        poll(http, None, 3090)

    assert operations == [
        (now, SUBMIT) for now in [10, 20, 40, 80, 160, 320, 640, 1280, 2180, 3080]
    ]


@pytest.mark.parametrize('status', [400, 503])
def test_new_track_supersedes_rejection_or_backoff(poll, status):
    sent = []

    def respond(request):
        sent.append(json.loads(request.content)['payload'][0]['track_metadata'])
        return httpx.Response(status)

    current = support.session()
    following = support.session(title='Next', key='next')
    with support.mock_http(respond) as http:
        poll(http, current, 10)
        poll(http, current, 12)
        poll(http, following, 14)
        poll(http, following, 24)

    assert [track['track_name'] for track in sent] == (
        ['Track', 'Next'] if status == 400 else ['Track', 'Next', 'Next']
    )


@pytest.mark.parametrize(
    ('status', 'deletions'),
    [(400, [12]), (404, [12]), (408, [12, 24, 46]), (503, [12, 24, 46])],
)
def test_clear_failure_policy_and_recovery_on_track_change(
    poll, clock, status, deletions
):
    operations = []

    def respond(request):
        operations.append((clock(), request.url.path))
        if request.url.path == DELETE:
            clock.return_value += 2
        return httpx.Response(status if request.url.path == DELETE else 200)

    with support.mock_http(respond) as http:
        poll(http, support.session(), 10)
        for now in range(12, 62, 2):
            poll(http, None, now)
        resumed = (
            support.session()
            if status == 404
            else support.session(title='Next', key='next')
        )
        poll(http, resumed, 62)

    assert operations == [
        (10, SUBMIT),
        *((now, DELETE) for now in deletions),
        (62, SUBMIT),
    ]


@pytest.mark.parametrize(('status', 'cooldown'), [(429, 90), (401, 300)])
@pytest.mark.parametrize('endpoint', [SUBMIT, DELETE])
def test_worker_applies_shared_cooldown_before_queued_listens(
    tmp_path, playback, monkeypatch, clock, status, cooldown, endpoint
):
    def respond(request):
        return httpx.Response(
            status if request.url.path == endpoint else 200,
            headers={'Retry-After': '90'},
        )

    playback.update(support.session(), clock())
    queued = Mock(return_value=0)
    stop = Mock()
    cycles = 1 if endpoint == SUBMIT else 2
    stop.is_set.side_effect = lambda: stop.wait.call_count >= cycles
    stop.wait.side_effect = lambda _: playback.update(None, clock())
    monkeypatch.setattr('lb_scrobbler.client.send_one', queued)
    with support.mock_http(respond) as http:
        monkeypatch.setattr(
            'lb_scrobbler.client.api_client', lambda _: nullcontext(http)
        )

        submit_listens(tmp_path / 'state.sqlite3', 'test-token', stop, playback)

    assert queued.call_count == (0 if endpoint == SUBMIT else 1)
    assert [call.args[0] for call in stop.wait.call_args_list] == (
        [cooldown] if endpoint == SUBMIT else [2, cooldown]
    )


def test_queued_network_backoff_does_not_delay_next_track(
    store_path, playback, monkeypatch
):
    current = support.session()
    tracker = Tracker(current)
    with closing(Store(store_path)) as store:
        store.checkpoint(tracker, current.payload())

    sent = []

    def respond(request):
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
