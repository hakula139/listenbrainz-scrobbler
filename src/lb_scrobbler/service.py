"""Install a per-user launch agent without requiring administrator access."""

import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path


LABEL = 'xyz.hakula.listenbrainz-scrobbler'
STATE = Path.home() / 'Library/Application Support/listenbrainz-scrobbler'
PLIST = Path.home() / 'Library/LaunchAgents' / f'{LABEL}.plist'


def domain() -> str:
    return f'gui/{os.getuid()}'


def loaded() -> bool:
    return (
        subprocess.run(
            ['launchctl', 'print', f'{domain()}/{LABEL}'], capture_output=True
        ).returncode
        == 0
    )


def stop() -> None:
    if loaded():
        subprocess.run(['launchctl', 'bootout', f'{domain()}/{LABEL}'], check=True)
        deadline = time.monotonic() + 90
        while loaded():
            if time.monotonic() >= deadline:
                raise RuntimeError('Previous launch agent has not finished stopping')
            time.sleep(0.2)


def install(dry_run: bool) -> None:
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    arguments = [sys.executable, '-m', 'lb_scrobbler.cli', 'run']
    if dry_run:
        arguments.append('--dry-run')
    config = {
        'Label': LABEL,
        'ProgramArguments': arguments,
        'WorkingDirectory': str(STATE),
        'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit': False},
        'ThrottleInterval': 30,
        'ExitTimeOut': 80,
        'StandardOutPath': str(STATE / 'service.log'),
        'StandardErrorPath': str(STATE / 'service.log'),
    }
    stop()
    PLIST.write_bytes(plistlib.dumps(config))
    subprocess.run(['launchctl', 'bootstrap', domain(), str(PLIST)], check=True)


def uninstall() -> None:
    stop()
    PLIST.unlink(missing_ok=True)
