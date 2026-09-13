"""Read Music.app through a persistent scripting process."""

import json
import math
import select
import subprocess
from contextlib import closing
from pathlib import Path

from .tracking import Sample


class MusicReader:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def close(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            assert self.process.stdout is not None
            self.process.stdout.close()
            self.process = None

    def read(self) -> Sample:
        timeout = 10
        if self.process is None:
            # Reusing OSA avoids repeated, costly macOS input-method initialization.
            self.process = subprocess.Popen(
                [
                    '/usr/bin/osascript',
                    '-l',
                    'JavaScript',
                    str(Path(__file__).with_name('music.js')),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            timeout = 60
        assert self.process.stdout is not None
        ready, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            self.close()
            raise RuntimeError(
                'Music query timed out. Check Automation access and Music.'
            )
        line = self.process.stdout.readline()
        if not line:
            self.close()
            raise RuntimeError('Music observer exited')
        return parse_sample(line)


def parse_sample(line: bytes) -> Sample:
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError('Expected a playback object')
        if 'error' in data:
            if not isinstance(data['error'], str):
                raise ValueError('Expected an error message')
            raise RuntimeError(data['error'])
        sample = Sample(**data)
        if not isinstance(sample.state, str) or not all(
            isinstance(value, str) for value in sample.identity
        ):
            raise ValueError('Invalid metadata')
        if not all(
            type(value) in (int, float) and math.isfinite(value) and value >= 0
            for value in (sample.duration, sample.position)
        ):
            raise ValueError('Invalid playback position or duration')
        return sample
    except (ValueError, TypeError) as error:
        raise RuntimeError('Music returned invalid playback metadata') from error


def read_sample() -> Sample:
    with closing(MusicReader()) as reader:
        return reader.read()
