"""Own the playback monitor and submission worker for one service instance."""

import fcntl
import json
import logging
import signal
import threading
import time
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from . import service
from .client import sender
from .credentials import load_token
from .music import MusicReader
from .store import Store
from .tracking import Sample


logger = logging.getLogger(__name__)


class PlaybackMonitor:
    def __init__(self, store: Store, reader: MusicReader, state: Path, dry_run: bool):
        self.store = store
        self.reader = reader
        self.state = state
        self.dry_run = dry_run
        self.tracker = store.restore()
        self.previous_error: str | None = None

    def read(self) -> tuple[Sample, str | None]:
        error = None
        try:
            sample = self.reader.read()
        except RuntimeError as exc:
            error = str(exc)
            sample = Sample('unavailable')

        if error != self.previous_error:
            if error:
                logger.warning('%s', error)
            else:
                logger.info('Playback observation recovered')
        self.previous_error = error
        return sample, error

    def poll(self) -> None:
        sample, error = self.read()
        now = time.time()
        payload = self.tracker.observe(sample, now)
        self.store.checkpoint(self.tracker, payload)
        session = self.tracker.session
        if payload:
            assert session is not None
            logger.info('Qualified listen %s', session.id)

        status = {
            'updated_at': now,
            'dry_run': self.dry_run,
            'sample': asdict(sample),
            'observed_seconds': session.seconds if session else 0,
            'error': error,
            **self.store.status(),
        }
        pending = self.state / 'status.tmp'
        pending.write_text(json.dumps(status, ensure_ascii=False) + '\n')
        pending.replace(self.state / 'status.json')


def monitor_playback(path: Path, token: str | None, stop: threading.Event) -> None:
    with closing(Store(path)) as store, closing(MusicReader()) as reader:
        monitor = PlaybackMonitor(store, reader, service.STATE, dry_run=token is None)
        worker = None
        if token is not None:
            worker = threading.Thread(
                target=sender, args=(path, token, stop), daemon=True
            )
            worker.start()

        logger.info('Started in %s mode', 'dry-run' if token is None else 'submission')
        try:
            while not stop.is_set():
                began = time.monotonic()
                if worker and not worker.is_alive():
                    raise RuntimeError('Submission worker exited. Restarting service')
                monitor.poll()
                stop.wait(max(0, 2 - (time.monotonic() - began)))
        finally:
            stop.set()
            if worker:
                worker.join(timeout=12)


def run(dry_run: bool) -> None:
    service.STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (service.STATE / 'run.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                'Another scrobbler process is already running'
            ) from error

        path = service.STATE / ('dry-run.sqlite3' if dry_run else 'state.sqlite3')
        token = None if dry_run else load_token()
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())

        monitor_playback(path, token, stop)
