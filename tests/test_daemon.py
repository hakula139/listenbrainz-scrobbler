import json
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

from lb_scrobbler.daemon import PlaybackMonitor
from lb_scrobbler.store import Store
from lb_scrobbler.tracking import Sample


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
        'lb_scrobbler.daemon.time', SimpleNamespace(time=lambda: next(clock))
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
