from dataclasses import replace

from lb_scrobbler.playback import PlaybackState
from lb_scrobbler.tracking import Sample, Session


def session(state='playing', title='Track', key='session'):
    return Session(key, Sample(state, title, 'Artist', 'Album', 120, 0), 1000, 1000)


def test_mailbox_retains_immutable_sample_and_rejects_stale_observations():
    playback = PlaybackState()
    current = session()
    playback.update(current, 10)
    snapshot = playback.current(11)
    current.sample = replace(current.sample, title='Next')
    assert snapshot.sample.title == 'Track'
    assert playback.current(21) is None

    playback.update(current, 22)
    assert playback.current(22).generation != snapshot.generation
    assert playback.current(22).sample.title == 'Next'


def test_generations_distinguish_resume_and_repeat_from_normal_progress():
    playback = PlaybackState()
    current = session()
    playback.update(current, 10)
    first = playback.current(10).generation
    playback.update(current, 12)
    assert playback.current(12).generation == first

    playback.update(session(state='paused'), 14)
    assert playback.current(14) is None
    playback.update(current, 16)
    resumed = playback.current(16).generation
    assert resumed != first

    playback.update(session(key='repeat'), 18)
    assert playback.current(18).generation != resumed
