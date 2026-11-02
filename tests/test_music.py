import json
import os
import re
import time
from unittest.mock import Mock

import pytest

from lb_scrobbler.music import MusicReader, parse_sample
from lb_scrobbler.tracking import Sample


def closed_pipe(output):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, output)
    os.close(write_fd)
    return os.fdopen(read_fd, 'rb', buffering=0)


@pytest.fixture
def observer_pipe():
    read_fd, write_fd = os.pipe()
    reader = MusicReader()
    reader.process = Mock(stdout=os.fdopen(read_fd, 'rb', buffering=0))
    yield reader, write_fd

    reader.close()
    os.close(write_fd)


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
    ('data', 'message'),
    [
        pytest.param(
            [],
            'Music returned invalid playback metadata: Expected a playback object',
            id='non-object',
        ),
        pytest.param(
            None,
            'Music returned invalid playback metadata: Expected a playback object',
            id='null',
        ),
        pytest.param(
            {'error': 1},
            'Music returned invalid playback metadata: Expected an error message',
            id='non-string-error',
        ),
        pytest.param(
            {'state': 'playing', 'position': True},
            'Music returned invalid playback metadata: '
            'Invalid playback position or duration',
            id='boolean-position',
        ),
        pytest.param(
            {'state': 'playing', 'duration': -1},
            'Music returned invalid playback metadata: '
            'Invalid playback position or duration',
            id='negative-duration',
        ),
        pytest.param(
            {'state': 'playing', 'position': float('nan')},
            'Music returned invalid playback metadata: '
            'Invalid playback position or duration',
            id='nan-position',
        ),
        pytest.param(
            {'state': 'playing', 'duration': float('inf')},
            'Music returned invalid playback metadata: '
            'Invalid playback position or duration',
            id='infinite-duration',
        ),
        pytest.param(
            {'state': 'playing', 'title': None},
            'Music returned invalid playback metadata: Invalid metadata',
            id='non-string-title',
        ),
        pytest.param(
            {'error': 'Music Automation access denied (-1743)'},
            'Music Automation access denied (-1743)',
            id='error-passthrough',
        ),
    ],
)
def test_parse_failures_report_their_cause(data, message):
    with pytest.raises(RuntimeError, match=f'^{re.escape(message)}$'):
        parse_sample(json.dumps(data).encode())


def test_partial_sample_obeys_deadline(observer_pipe):
    reader, write_fd = observer_pipe
    os.write(write_fd, b'{"state":')
    started = time.monotonic()

    with pytest.raises(RuntimeError, match='Music query timed out'):
        reader._read_line(0.02)

    assert time.monotonic() - started < 0.5
    assert reader.process is None
    assert not reader.buffer


def test_reader_reuses_process_and_restarts_after_eof(monkeypatch):
    reader = MusicReader()
    reader.process = Mock(
        stdout=closed_pipe(b'{"state":"playing"}\n{"state":"paused"}\n{"state":')
    )

    process = Mock(stdout=closed_pipe(b'{"state":"stopped"}\n'))
    popen = Mock(return_value=process)
    monkeypatch.setattr('lb_scrobbler.music.subprocess.Popen', popen)

    try:
        assert reader.read().state == 'playing'
        assert reader.read().state == 'paused'
        popen.assert_not_called()

        with pytest.raises(RuntimeError, match='Music observer exited'):
            reader.read()

        assert reader.read().state == 'stopped'
        popen.assert_called_once()
    finally:
        reader.close()
