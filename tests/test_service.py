import argparse
import plistlib
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from lb_scrobbler import cli, service


BROKEN_NIX_AGENT = [
    '/nix/store/abc123-python3.13/bin/python3.13',
    '-m',
    'lb_scrobbler.cli',
    'run',
]
CHECKOUT_PACKAGE = '/home/u/src/app/src/lb_scrobbler/service.py'
HOME_MANAGER_AGENT = [
    '/nix/store/abc123-listenbrainz-scrobbler-0.2.0/bin/lb-scrobbler',
    'run',
]
NIX_PACKAGE = Path(
    '/nix/store/abc-python3.13-listenbrainz-scrobbler-0.2.0'
    '/lib/python3.13/site-packages/lb_scrobbler'
)
UV_AGENT = [
    '/home/u/.local/share/uv/tools/listenbrainz-scrobbler/bin/python',
    '-m',
    'lb_scrobbler.cli',
    'run',
]


def write_agent(path, arguments):
    config = {'Label': service.LABEL, 'ProgramArguments': arguments}
    path.write_bytes(plistlib.dumps(config))


@pytest.fixture(autouse=True)
def checkout_package(monkeypatch):
    monkeypatch.setattr('lb_scrobbler.service.__file__', CHECKOUT_PACKAGE)


@pytest.mark.parametrize(
    ('package_file', 'expected'),
    [
        (NIX_PACKAGE / 'service.py', True),
        (Path(CHECKOUT_PACKAGE), False),
        (
            Path(
                '/home/u/.local/share/uv/tools/listenbrainz-scrobbler'
                '/lib/python3.13/site-packages/lb_scrobbler/service.py'
            ),
            False,
        ),
    ],
)
def test_from_nix_store(monkeypatch, package_file, expected):
    monkeypatch.setattr('lb_scrobbler.service.__file__', str(package_file))

    assert service.from_nix_store() is expected


def test_from_nix_store_does_not_follow_symlinks(monkeypatch, tmp_path):
    store = tmp_path / 'store'
    (tmp_path / 'real').mkdir()
    store.symlink_to(tmp_path / 'real', target_is_directory=True)
    monkeypatch.setattr('lb_scrobbler.service.NIX_STORE', store)
    monkeypatch.setattr(
        'lb_scrobbler.service.__file__', str(store / 'pkg' / 'service.py')
    )

    assert service.from_nix_store() is True


@pytest.mark.parametrize(
    ('arguments', 'expected'),
    [
        pytest.param(HOME_MANAGER_AGENT, True, id='home-manager'),
        pytest.param(BROKEN_NIX_AGENT, False, id='broken-nix-install'),
        pytest.param(UV_AGENT, False, id='uv-tool'),
        pytest.param(
            ['/home/u/src/app/.venv/bin/python', '-m', 'lb_scrobbler.cli', 'run'],
            False,
            id='checkout',
        ),
        pytest.param(
            ['/nix/store/abc-other/bin/other', 'run'],
            False,
            id='store-other-program',
        ),
        pytest.param(
            ['/home/u/.local/bin/lb-scrobbler', 'run'],
            False,
            id='non-store-launcher',
        ),
    ],
)
def test_managed_by_home_manager(monkeypatch, tmp_path, arguments, expected):
    plist = tmp_path / 'agent.plist'
    write_agent(plist, arguments)
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)

    assert service.managed_by_home_manager() is expected


@pytest.mark.parametrize(
    'content',
    [
        pytest.param(b'not a plist', id='invalid-format'),
        pytest.param(b'<?xml version="1.0"?><plist><dict>', id='malformed-xml'),
        pytest.param(
            b'<?xml version="1.0"?><plist><dict>'
            b'<key>ProgramArguments</key><integer>abc</integer></dict></plist>',
            id='invalid-value',
        ),
        pytest.param(plistlib.dumps(['lb-scrobbler']), id='non-dict-root'),
        pytest.param(plistlib.dumps({'Label': service.LABEL}), id='missing-program'),
        pytest.param(
            plistlib.dumps({'ProgramArguments': {'program': 'lb-scrobbler'}}),
            id='non-list-program',
        ),
        pytest.param(plistlib.dumps({'ProgramArguments': []}), id='empty-program'),
        pytest.param(
            plistlib.dumps({'ProgramArguments': [42, 'run']}),
            id='non-string-program',
        ),
    ],
)
def test_managed_by_home_manager_ignores_malformed(monkeypatch, tmp_path, content):
    plist = tmp_path / 'agent.plist'
    plist.write_bytes(content)
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)

    assert service.managed_by_home_manager() is False


def test_managed_by_home_manager_without_agent(monkeypatch, tmp_path):
    monkeypatch.setattr('lb_scrobbler.service.PLIST', tmp_path / 'agent.plist')

    assert service.managed_by_home_manager() is False


def test_install_refuses_from_nix_store(monkeypatch, tmp_path):
    stop = Mock()
    load_token = Mock()
    monkeypatch.setattr(
        'lb_scrobbler.service.__file__', str(NIX_PACKAGE / 'service.py')
    )
    monkeypatch.setattr('lb_scrobbler.service.STATE', tmp_path / 'state')
    monkeypatch.setattr('lb_scrobbler.service.PLIST', tmp_path / 'agent.plist')
    monkeypatch.setattr('lb_scrobbler.service.stop', stop)
    monkeypatch.setattr('lb_scrobbler.service.load_token', load_token)
    monkeypatch.setattr('lb_scrobbler.service.subprocess.run', Mock())

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        service.install(dry_run=False)

    stop.assert_not_called()
    load_token.assert_not_called()
    assert not (tmp_path / 'state').exists()


def test_install_refuses_home_manager_agent(monkeypatch, tmp_path):
    plist = tmp_path / 'agent.plist'
    write_agent(plist, HOME_MANAGER_AGENT)
    before = plist.read_bytes()
    stop = Mock()
    load_token = Mock()
    monkeypatch.setattr('lb_scrobbler.service.STATE', tmp_path / 'state')
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)
    monkeypatch.setattr('lb_scrobbler.service.stop', stop)
    monkeypatch.setattr('lb_scrobbler.service.load_token', load_token)
    monkeypatch.setattr('lb_scrobbler.service.subprocess.run', Mock())

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        service.install(dry_run=False)

    stop.assert_not_called()
    load_token.assert_not_called()
    assert plist.read_bytes() == before


@pytest.mark.parametrize('dry_run', [True, False])
def test_install_allows_other_agents(monkeypatch, tmp_path, dry_run):
    plist = tmp_path / 'agent.plist'
    write_agent(plist, UV_AGENT)
    load_token = Mock()
    monkeypatch.setattr('lb_scrobbler.service.STATE', tmp_path / 'state')
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)
    monkeypatch.setattr('lb_scrobbler.service.stop', Mock())
    monkeypatch.setattr('lb_scrobbler.service.load_token', load_token)
    monkeypatch.setattr('lb_scrobbler.service.subprocess.run', Mock())

    service.install(dry_run=dry_run)

    config = plistlib.loads(plist.read_bytes())
    assert config['ProgramArguments'][0] == sys.executable
    assert ('--dry-run' in config['ProgramArguments']) is dry_run
    if dry_run:
        load_token.assert_not_called()
    else:
        load_token.assert_called_once_with()


def test_uninstall_refuses_home_manager_agent(monkeypatch, tmp_path):
    plist = tmp_path / 'agent.plist'
    write_agent(plist, HOME_MANAGER_AGENT)
    stop = Mock()
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)
    monkeypatch.setattr('lb_scrobbler.service.stop', stop)

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        service.uninstall()

    stop.assert_not_called()
    assert plist.exists()


def test_uninstall_allows_broken_nix_agent_from_nix_store(monkeypatch, tmp_path):
    plist = tmp_path / 'agent.plist'
    write_agent(plist, BROKEN_NIX_AGENT)
    stop = Mock()
    monkeypatch.setattr(
        'lb_scrobbler.service.__file__', str(NIX_PACKAGE / 'service.py')
    )
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)
    monkeypatch.setattr('lb_scrobbler.service.stop', stop)

    service.uninstall()

    stop.assert_called_once_with()
    assert not plist.exists()


def test_dispatch_refuses_nix_install_before_token(monkeypatch, tmp_path):
    load_token = Mock()
    monkeypatch.setattr(
        'lb_scrobbler.service.__file__', str(NIX_PACKAGE / 'service.py')
    )
    monkeypatch.setattr('lb_scrobbler.service.load_token', load_token)
    monkeypatch.setattr('lb_scrobbler.service.STATE', tmp_path / 'state')
    monkeypatch.setattr('lb_scrobbler.service.PLIST', tmp_path / 'agent.plist')
    monkeypatch.setattr('lb_scrobbler.service.subprocess.run', Mock())

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        cli.dispatch(argparse.Namespace(command='install', dry_run=False))

    load_token.assert_not_called()
