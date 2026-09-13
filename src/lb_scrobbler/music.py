"""Read Music.app through a persistent scripting process."""

import json
import math
import os
import select
import subprocess
from contextlib import closing
from pathlib import Path
from time import monotonic

from .tracking import Sample


class MusicReader:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.buffer = bytearray()

    def close(self) -> None:
        self.buffer.clear()
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
                bufsize=0,
                stderr=subprocess.DEVNULL,
            )
            timeout = 60
        return parse_sample(self._read_line(timeout))

    def _read_line(self, timeout: float) -> bytes:
        assert self.process is not None and self.process.stdout is not None
        deadline = monotonic() + timeout
        while b'\n' not in self.buffer:
            remaining = deadline - monotonic()
            ready, _, _ = select.select(
                [self.process.stdout], [], [], max(0, remaining)
            )
            if remaining <= 0 or not ready:
                self.close()
                raise RuntimeError(
                    'Music query timed out. Check Automation access and Music.'
                )
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                self.close()
                raise RuntimeError('Music observer exited')
            self.buffer.extend(chunk)

        end = self.buffer.index(b'\n') + 1
        line = bytes(self.buffer[:end])
        del self.buffer[:end]
        return line


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
