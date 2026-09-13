import json
import os
from time import monotonic
from unittest.mock import Mock

import pytest

from lb_scrobbler.music import MusicReader, parse_sample, read_sample
from lb_scrobbler.tracking import Sample


def test_parse_streaming_metadata():
    data = {
        'state': 'playing',
        'title': 'Track',
        'artist': 'Artist',
        'album': '',
        'duration': 180.5,
        'position': 12.5,
    }
    assert parse_sample(json.dumps(data).encode()) == Sample(**data)


@pytest.mark.parametrize(
    'data',
    [
        [],
        None,
        {'error': 1},
        {'position': True},
        {'duration': -1},
        {'position': float('nan')},
        {'duration': float('inf')},
        {'title': None},
    ],
)
def test_reject_invalid_metadata(data):
    if isinstance(data, dict) and 'error' not in data:
        data = {'state': 'playing', **data}
    with pytest.raises(RuntimeError, match='invalid playback metadata'):
        parse_sample(json.dumps(data).encode())


def test_probe_closes_observer_after_failure(monkeypatch):
    reader = Mock()
    reader.read.side_effect = RuntimeError('observer failed')
    monkeypatch.setattr('lb_scrobbler.music.MusicReader', lambda: reader)
    with pytest.raises(RuntimeError, match='observer failed'):
        read_sample()
    reader.close.assert_called_once()


@pytest.fixture
def observer_pipe():
    read_fd, write_fd = os.pipe()
    reader = MusicReader()
    reader.process = Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
    try:
        yield reader, write_fd
    finally:
        reader.close()
        os.close(write_fd)


def test_reader_consumes_buffered_samples_before_waiting(observer_pipe, monkeypatch):
    reader, write_fd = observer_pipe
    os.write(write_fd, b'{"state":"playing"}\n{"state":"paused"}\n')
    assert reader.read().state == 'playing'

    def unexpected_wait(*args):
        pytest.fail('A complete buffered sample must not wait for pipe readiness')

    monkeypatch.setattr('lb_scrobbler.music.select.select', unexpected_wait)
    assert reader.read().state == 'paused'


def test_partial_sample_obeys_deadline(observer_pipe):
    reader, write_fd = observer_pipe
    os.write(write_fd, b'{"state":')
    started = monotonic()
    with pytest.raises(RuntimeError, match='Music query timed out'):
        reader._read_line(0.02)
    assert monotonic() - started < 0.5
    assert reader.process is None
    assert not reader.buffer


def test_eof_discards_partial_sample_and_restarts(monkeypatch):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b'{"state":')
    os.close(write_fd)
    reader = MusicReader()
    reader.process = Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
    with pytest.raises(RuntimeError, match='Music observer exited'):
        reader.read()

    read_fd, write_fd = os.pipe()
    os.write(write_fd, b'{"state":"stopped"}\n')
    os.close(write_fd)
    process = Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
    monkeypatch.setattr('lb_scrobbler.music.subprocess.Popen', lambda *a, **kw: process)
    try:
        assert reader.read().state == 'stopped'
    finally:
        reader.close()
