import pytest

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


@pytest.mark.parametrize(
    ('duration', 'threshold'),
    [(100, 50), (1000, 240)],
    ids=['half-duration', 'four-minute-cap'],
)
def test_qualifies_at_half_duration_capped_at_four_minutes(duration, threshold):
    tracker = Tracker()
    assert play(tracker, end=threshold - 2, duration=duration) == []

    payload = tracker.observe(sample(threshold, duration=duration), 1000 + threshold)

    assert payload is not None


def test_payload_metadata_and_single_listen():
    tracker = Tracker()
    assert play(tracker, end=48) == []

    payload = tracker.observe(sample(50), 1050)

    assert payload['listened_at'] == 1000
    assert payload['track_metadata']['track_name'] == 'Track'
    assert payload['track_metadata']['additional_info']['duration_ms'] == 100000
    assert play(tracker, start=52, end=98) == []


def test_midtrack_attach_does_not_credit_unobserved_playback():
    tracker = Tracker()
    assert play(tracker, start=60, end=98) == []

    assert tracker.session.seconds == 38


def test_attach_while_paused_anchors_timestamp_on_resume():
    tracker = Tracker()
    tracker.observe(sample(10, 'paused'), 1000)
    assert tracker.session is None

    payload = play(tracker, start=10, end=60, offset=2000)[0]

    assert payload['listened_at'] == 2000


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


def test_transient_read_failure_does_not_credit_the_gap():
    tracker = Tracker()
    play(tracker, end=10)
    tracker.observe(Sample('unavailable'), 1012)
    tracker.observe(sample(18), 1018)

    assert tracker.session.seconds == 10


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


def test_transient_read_failure_preserves_qualified_session():
    tracker = Tracker()
    play(tracker)
    tracker.observe(Sample('unavailable'), 1052)

    assert play(tracker, start=54, end=98) == []
    assert tracker.session.queued
