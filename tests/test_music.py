import json

import pytest

from lb_scrobbler.music import parse_sample
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
        pytest.param([], id='non-object'),
        pytest.param(None, id='null'),
        pytest.param({'error': 1}, id='non-string-error'),
        pytest.param({'state': 'playing', 'position': True}, id='boolean-position'),
        pytest.param({'state': 'playing', 'duration': -1}, id='negative-duration'),
        pytest.param({'state': 'playing', 'position': float('nan')}, id='nan-position'),
        pytest.param(
            {'state': 'playing', 'duration': float('inf')}, id='infinite-duration'
        ),
        pytest.param({'state': 'playing', 'title': None}, id='non-string-title'),
    ],
)
def test_reject_invalid_metadata(data):
    with pytest.raises(RuntimeError, match='invalid playback metadata'):
        parse_sample(json.dumps(data).encode())
