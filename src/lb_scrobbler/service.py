"""Install a per-user launch agent without requiring administrator access."""

import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from xml.parsers.expat import ExpatError

from .credentials import load_token


LABEL = 'xyz.hakula.listenbrainz-scrobbler'
STATE = Path.home() / 'Library/Application Support/listenbrainz-scrobbler'
PLIST = Path.home() / 'Library/LaunchAgents' / f'{LABEL}.plist'
NIX_STORE = Path('/nix/store')
HOME_MANAGER_PROGRAM = 'lb-scrobbler'
HOME_MANAGER_MODULE = (
    'Home Manager module (homeModules.default, services.listenbrainz-scrobbler.enable)'
)


def from_nix_store() -> bool:
    return Path(__file__).is_relative_to(NIX_STORE)


def managed_by_home_manager() -> bool:
    if not PLIST.exists():
        return False
    try:
        config = plistlib.loads(PLIST.read_bytes())
    except (ValueError, ExpatError):
        return False
    if not isinstance(config, dict):
        return False
    arguments = config.get('ProgramArguments')
    if not isinstance(arguments, list) or not arguments:
        return False
    program = arguments[0]
    if not isinstance(program, str):
        return False
    program = Path(program)
    return program.is_relative_to(NIX_STORE) and program.name == HOME_MANAGER_PROGRAM


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
    if from_nix_store():
        raise RuntimeError(
            'Cannot install the launch agent from the Nix package. '
            f'Manage it through the {HOME_MANAGER_MODULE} instead.'
        )
    if managed_by_home_manager():
        raise RuntimeError(
            f'The launch agent is owned by the {HOME_MANAGER_MODULE}. '
            'Manage it there instead.'
        )
    if not dry_run:
        load_token()
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
    if managed_by_home_manager():
        raise RuntimeError(
            f'The launch agent is owned by the {HOME_MANAGER_MODULE}. '
            'Disable the option and reactivate Home Manager to remove it.'
        )
    stop()
    PLIST.unlink(missing_ok=True)
