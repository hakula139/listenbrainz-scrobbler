"""Command-line setup, diagnosis, and foreground service execution."""

import argparse
import fcntl
import getpass
import json
import logging
import os
import plistlib
import signal
import threading
import time
from dataclasses import asdict
from pathlib import Path

from . import service
from .client import sender, validate_token
from .credentials import load_token, save_token
from .music import MusicReader, read_sample
from .store import Store
from .tracking import Sample


def run(dry_run: bool):
    service.STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (service.STATE / 'run.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                'Another scrobbler process is already running'
            ) from error
        _run(dry_run)


def _run(dry_run: bool):
    path = service.STATE / ('dry-run.sqlite3' if dry_run else 'state.sqlite3')
    token = None if dry_run else load_token()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    store = Store(path)
    tracker = store.restore()
    worker = None
    if token:
        worker = threading.Thread(target=sender, args=(path, token, stop), daemon=True)
        worker.start()
    previous_error = None
    reader = MusicReader()
    logging.info('Started in %s mode', 'dry-run' if dry_run else 'submission')
    try:
        while not stop.is_set():
            began = time.monotonic()
            error = None
            try:
                sample = reader.read()
            except RuntimeError as exc:
                error = str(exc)
                sample = Sample('unavailable')
            if error != previous_error:
                if error:
                    logging.warning('%s', error)
                elif previous_error:
                    logging.info('Playback observation recovered')
            previous_error = error
            now = time.time()
            if worker and not worker.is_alive() and not stop.is_set():
                raise RuntimeError('Submission worker exited. Restarting service')
            payload = tracker.observe(sample, now)
            store.checkpoint(tracker, payload)
            if payload:
                logging.info('Qualified listen %s', tracker.session.id)
            status = {
                'updated_at': now,
                'dry_run': dry_run,
                'sample': asdict(sample),
                'observed_seconds': tracker.session.seconds if tracker.session else 0,
                'error': error,
                **store.status(),
            }
            pending = service.STATE / 'status.tmp'
            pending.write_text(json.dumps(status, ensure_ascii=False) + '\n')
            pending.replace(service.STATE / 'status.json')
            stop.wait(max(0, 2 - (time.monotonic() - began)))
    finally:
        stop.set()
        reader.close()
        if worker:
            worker.join(timeout=12)
        store.close()


def main():
    os.umask(0o077)
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s'
    )
    logging.getLogger('httpx').setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('probe', help='Read current Music playback without submitting')
    auth = commands.add_parser(
        'auth', help='Validate and save a token in login Keychain'
    )
    auth.add_argument(
        '--from-smashtunes',
        action='store_true',
        help='Read the existing SmashTunes token without displaying it',
    )
    for name, help_text in (
        ('run', 'Run in the foreground'),
        ('install', 'Install and start the launch agent'),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument(
            '--dry-run',
            action='store_true',
            help='Observe and queue locally without network submissions',
        )
    commands.add_parser('status', help='Show the last observation and queue status')
    commands.add_parser('stop', help='Stop the launch agent for this login session')
    commands.add_parser(
        'uninstall', help='Remove the launch agent, retaining queue and token'
    )
    commands.add_parser('retry', help='Retry retained submission failures')
    args = parser.parse_args()
    try:
        if args.command == 'probe':
            print(json.dumps(asdict(read_sample()), ensure_ascii=False))
        elif args.command == 'auth':
            if args.from_smashtunes:
                path = Path.home() / (
                    'Library/Containers/nl.smashbits.SmashTunes/Data/Library/'
                    'Preferences/nl.smashbits.SmashTunes.plist'
                )
                with path.open('rb') as source:
                    token = plistlib.load(source).get('ListenBrainzToken', '')
            else:
                token = getpass.getpass('ListenBrainz token: ')
            if not isinstance(token, str) or not token.strip():
                raise RuntimeError('No ListenBrainz token supplied')
            token = token.strip()
            username = validate_token(token)
            save_token(token)
            print(f'Token saved in login Keychain for {username}.')
        elif args.command == 'run':
            run(args.dry_run)
        elif args.command == 'install':
            if not args.dry_run:
                load_token()
            service.install(args.dry_run)
            print('Launch agent installed. Run status to verify playback access.')
        elif args.command == 'status':
            status_path = service.STATE / 'status.json'
            status = json.loads(status_path.read_text()) if status_path.exists() else {}
            status['agent_loaded'] = service.loaded()
            if 'updated_at' in status:
                status['observation_age_seconds'] = round(
                    time.time() - status['updated_at'], 1
                )
            print(json.dumps(status, ensure_ascii=False, indent=2))
        elif args.command == 'retry':
            store = Store(service.STATE / 'state.sqlite3')
            store.retry()
            store.close()
            print('Retained submissions marked for retry.')
        else:
            getattr(service, args.command)()
    except Exception as error:
        # Transport and Keychain exceptions may carry sensitive context.
        message = (
            str(error) if isinstance(error, RuntimeError) else type(error).__name__
        )
        parser.exit(1, f'Error: {message}\n')


if __name__ == '__main__':
    main()
