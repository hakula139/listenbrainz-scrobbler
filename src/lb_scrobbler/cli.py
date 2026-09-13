"""Command-line setup and diagnosis for Apple Music scrobbling."""

import argparse
import getpass
import json
import logging
import os
import plistlib
import time
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from . import service
from .client import validate_token
from .credentials import load_token, save_token
from .daemon import run
from .music import read_sample
from .store import Store


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def authenticate(from_smashtunes: bool) -> None:
    if from_smashtunes:
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


def print_status() -> None:
    status_path = service.STATE / 'status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    status['agent_loaded'] = service.loaded()
    if 'updated_at' in status:
        status['observation_age_seconds'] = round(time.time() - status['updated_at'], 1)

    print(json.dumps(status, ensure_ascii=False, indent=2))


def dispatch(args: argparse.Namespace) -> None:
    match args.command:
        case 'probe':
            print(json.dumps(asdict(read_sample()), ensure_ascii=False))
        case 'auth':
            authenticate(args.from_smashtunes)
        case 'run':
            run(args.dry_run)
        case 'install':
            if not args.dry_run:
                load_token()
            service.install(args.dry_run)
            print('Launch agent installed. Run status to verify playback access.')
        case 'status':
            print_status()
        case 'retry':
            with closing(Store(service.STATE / 'state.sqlite3')) as store:
                store.retry()
            print('Retained submissions marked for retry.')
        case 'stop':
            service.stop()
        case 'uninstall':
            service.uninstall()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z',
    )
    logging.getLogger('lb_scrobbler').setLevel(logging.INFO)


def main() -> None:
    os.umask(0o077)
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()

    try:
        dispatch(args)
    except Exception as error:
        # Transport and Keychain exceptions may carry sensitive context.
        message = (
            str(error) if isinstance(error, RuntimeError) else type(error).__name__
        )
        parser.exit(1, f'Error: {message}\n')


if __name__ == '__main__':
    main()
