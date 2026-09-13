from lb_scrobbler.store import Store
from lb_scrobbler.tracking import Sample, Tracker


def sample(position, state='playing', title='Track', duration=100):
    return Sample(state, title, 'Artist', 'Album', duration, position)


def play(tracker, start=0, end=50, offset=1000, **kwargs):
    results = []
    for position in range(start, end + 1, 2):
        result = tracker.observe(sample(position, **kwargs), offset + position)
        if result:
            results.append(result)
    return results


def test_threshold_and_metadata():
    tracker = Tracker()
    assert play(tracker, end=48) == []
    payload = tracker.observe(sample(50), 1050)
    assert payload['listened_at'] == 1000
    assert payload['track_metadata']['track_name'] == 'Track'
    assert payload['track_metadata']['additional_info']['duration_ms'] == 100000
    assert play(tracker, start=52, end=98) == []


def test_four_minute_cap():
    tracker = Tracker()
    assert play(tracker, end=238, duration=1000) == []
    assert tracker.observe(sample(240, duration=1000), 1240) is not None


def test_pause_seek_and_sleep_do_not_count():
    tracker = Tracker()
    play(tracker, end=10)
    tracker.observe(sample(10, 'paused'), 1012)
    tracker.observe(sample(10, 'paused'), 1112)
    tracker.observe(sample(10), 1114)
    tracker.observe(sample(80), 1116)
    tracker.observe(sample(82), 1118)
    tracker.observe(sample(90), 2000)
    assert tracker.session.seconds == 12
    tracker.observe(sample(30), 2002)
    assert tracker.session.seconds == 12


def test_midtrack_attach_does_not_credit_unobserved_playback():
    tracker = Tracker()
    assert play(tracker, start=60, end=98) == []
    assert tracker.session.seconds == 38


def test_repeat_creates_a_new_listen():
    tracker = Tracker()
    first = play(tracker, end=98)[0]
    second = play(tracker, offset=1100)[0]
    assert first['listened_at'] == 1000
    assert second['listened_at'] == 1100


def test_backward_seek_does_not_duplicate_qualified_track():
    tracker = Tracker()
    play(tracker, end=60)
    assert play(tracker, offset=1062) == []


def test_track_change_and_stop_reset_progress():
    tracker = Tracker()
    play(tracker, end=30)
    tracker.observe(sample(0, title='Other'), 1032)
    assert tracker.session.seconds == 0
    tracker.observe(Sample('stopped'), 1034)
    assert tracker.session is None


def test_restart_keeps_queue_and_prevents_duplicate(tmp_path):
    path = tmp_path / 'state.sqlite3'
    store = Store(path)
    tracker = store.restore()
    payload = play(tracker)[0]
    store.checkpoint(tracker, payload)
    key = tracker.session.id
    store.close()
    store = Store(path)
    restored = store.restore()
    assert play(restored, start=52, end=98) == []
    store.checkpoint(restored, None)
    assert store.next(2000)[0] == key
    store.fail(key, 'HTTP 503', 2100)
    assert store.next(2099) is None
    assert store.next(2100)[2] == 1
    store.acknowledge(key)
    store.close()
    store = Store(path)
    assert store.next(2200) is None
    assert store.restore().session.queued
    store.close()


def test_blocked_payload_is_retained_for_manual_retry(tmp_path):
    store = Store(tmp_path / 'state.sqlite3')
    tracker = Tracker()
    payload = play(tracker)[0]
    store.checkpoint(tracker, payload)
    store.fail(tracker.session.id, 'HTTP 400', 0, blocked=True)
    assert store.next(2000) is None
    assert store.status()['errors'] == ['HTTP 400']
    store.retry()
    assert store.next(2000)[0] == tracker.session.id
    store.close()


def test_transient_read_failure_preserves_qualified_session():
    tracker = Tracker()
    play(tracker)
    tracker.observe(Sample('unavailable'), 1052)
    assert play(tracker, start=54, end=98) == []
    assert tracker.session.queued


def test_transient_read_failure_does_not_credit_the_gap():
    tracker = Tracker()
    play(tracker, end=10)
    tracker.observe(Sample('unavailable'), 1012)
    tracker.observe(sample(18), 1018)
    assert tracker.session.seconds == 10
