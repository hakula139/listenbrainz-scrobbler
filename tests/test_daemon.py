import fcntl
import json
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lb_scrobbler.daemon import PlaybackMonitor, monitor_playback, run
from lb_scrobbler.store import Store
from lb_scrobbler.tracking import Sample


@pytest.fixture
def run_monitor(monkeypatch, tmp_path):
    monitor = Mock()
    monkeypatch.setattr('lb_scrobbler.daemon.service.STATE', tmp_path)
    monkeypatch.setattr('lb_scrobbler.daemon.monitor_playback', monitor)
    monkeypatch.setattr('lb_scrobbler.daemon.signal.signal', Mock())

    return monitor


def test_monitor_retains_progress_across_read_failure(tmp_path, monkeypatch):
    reader = Mock()
    reader.read.side_effect = [
        Sample('playing', 'Track', 'Artist', '', 100, 0),
        Sample('playing', 'Track', 'Artist', '', 100, 10),
        RuntimeError('Music unavailable'),
        Sample('playing', 'Track', 'Artist', '', 100, 18),
    ]

    clock = iter([1000, 1010, 1012, 1018])
    monkeypatch.setattr(
        'lb_scrobbler.daemon.time',
        SimpleNamespace(time=lambda: next(clock), monotonic=lambda: 1),
    )

    with closing(Store(tmp_path / 'state.sqlite3')) as store:
        monitor = PlaybackMonitor(store, reader, tmp_path, dry_run=True)

        for _ in range(3):
            monitor.poll()

        status = json.loads((tmp_path / 'status.json').read_text())
        assert status['error'] == 'Music unavailable'
        assert status['observed_seconds'] == 10

        monitor.poll()

        status = json.loads((tmp_path / 'status.json').read_text())
        assert status['error'] is None
        assert status['sample']['position'] == 18
        assert store.restore().session.seconds == 10
        assert store.next(2000) is None


def test_monitor_queues_qualified_listen(tmp_path, monkeypatch):
    reader = Mock()
    reader.read.side_effect = [
        Sample('playing', 'Track', 'Artist', '', 20, 0),
        Sample('playing', 'Track', 'Artist', '', 20, 10),
    ]

    clock = iter([1000, 1010])
    monkeypatch.setattr(
        'lb_scrobbler.daemon.time',
        SimpleNamespace(time=lambda: next(clock), monotonic=lambda: 1),
    )

    with closing(Store(tmp_path / 'state.sqlite3')) as store:
        monitor = PlaybackMonitor(store, reader, tmp_path, dry_run=True)

        monitor.poll()
        monitor.poll()

        pending = store.next(2000)
        assert json.loads(pending.payload)['listened_at'] == 1000
        assert store.restore().session.queued


@pytest.mark.parametrize(
    ('dry_run', 'database', 'token'),
    [
        pytest.param(True, 'dry-run.sqlite3', None, id='dry-run'),
        pytest.param(False, 'state.sqlite3', 'test-token', id='submission'),
    ],
)
def test_run_uses_the_matching_database(
    run_monitor, monkeypatch, tmp_path, dry_run, database, token
):
    load_token = Mock(return_value='test-token')
    monkeypatch.setattr('lb_scrobbler.daemon.load_token', load_token)

    run(dry_run=dry_run)

    assert run_monitor.call_args.args[:2] == (tmp_path / database, token)
    if dry_run:
        load_token.assert_not_called()
    else:
        load_token.assert_called_once_with()


def test_run_refuses_when_another_process_owns_the_tracker(run_monitor, tmp_path):
    lock_path = tmp_path / 'run.lock'

    with lock_path.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        with pytest.raises(RuntimeError, match='already running'):
            run(dry_run=True)

    run_monitor.assert_not_called()


def test_dry_run_observes_without_starting_submission_worker(tmp_path, monkeypatch):
    reader = Mock()
    reader.read.return_value = Sample('playing', 'Track', 'Artist', '', 100, 0)

    stop = Mock()
    stop.is_set.side_effect = [False, True]

    thread = Mock()
    monkeypatch.setattr('lb_scrobbler.daemon.MusicReader', lambda: reader)
    monkeypatch.setattr('lb_scrobbler.daemon.threading.Thread', thread)
    monkeypatch.setattr('lb_scrobbler.daemon.service.STATE', tmp_path)

    monitor_playback(tmp_path / 'dry-run.sqlite3', None, stop)

    thread.assert_not_called()
    status = json.loads((tmp_path / 'status.json').read_text())
    assert status['dry_run'] is True
    assert status['sample']['title'] == 'Track'
