import json
from unittest.mock import Mock

import pytest

from lb_scrobbler.music import parse_sample, read_sample
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
