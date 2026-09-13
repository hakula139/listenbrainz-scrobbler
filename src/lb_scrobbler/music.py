"""Read Music.app through its public scripting dictionary."""

import json
import math
import subprocess
from pathlib import Path

from .tracking import Sample


def read_sample(timeout: float = 8) -> Sample:
    try:
        result = subprocess.run(
            [
                '/usr/bin/osascript',
                '-l',
                'JavaScript',
                str(Path(__file__).with_name('music.js')),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Music query timed out. Check Automation consent') from error
    if result.returncode:
        if '-1743' in result.stderr:
            raise RuntimeError('Music Automation access denied (-1743)')
        raise RuntimeError('Music scripting query failed')
    try:
        data = json.loads(result.stdout)
        sample = Sample(**data)
        if not isinstance(sample.state, str) or not all(
            isinstance(value, str) for value in sample.identity
        ):
            raise ValueError('Invalid metadata')
        if not all(
            isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
            for value in (sample.duration, sample.position)
        ):
            raise ValueError('Invalid playback position or duration')
        return sample
    except (ValueError, TypeError) as error:
        raise RuntimeError('Music returned invalid playback metadata') from error
