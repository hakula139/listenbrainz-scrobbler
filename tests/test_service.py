import plistlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lb_scrobbler import service


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


@pytest.fixture
def agent(monkeypatch, tmp_path):
    plist = tmp_path / 'agent.plist'
    stop = Mock()
    load_token = Mock()
    monkeypatch.setattr('lb_scrobbler.service.__file__', CHECKOUT_PACKAGE)
    monkeypatch.setattr('lb_scrobbler.service.STATE', tmp_path / 'state')
    monkeypatch.setattr('lb_scrobbler.service.PLIST', plist)
    monkeypatch.setattr('lb_scrobbler.service.stop', stop)
    monkeypatch.setattr('lb_scrobbler.service.load_token', load_token)
    monkeypatch.setattr('lb_scrobbler.service.subprocess.run', Mock())

    return SimpleNamespace(
        plist=plist,
        state=tmp_path / 'state',
        stop=stop,
        load_token=load_token,
    )


@pytest.mark.parametrize(
    ('package_file', 'expected'),
    [
        pytest.param(NIX_PACKAGE / 'service.py', True, id='nix-package'),
        pytest.param(Path(CHECKOUT_PACKAGE), False, id='checkout'),
    ],
)
def test_from_nix_store(monkeypatch, package_file, expected):
    monkeypatch.setattr('lb_scrobbler.service.__file__', str(package_file))

    assert service.from_nix_store() is expected


@pytest.mark.parametrize(
    ('arguments', 'expected'),
    [
        pytest.param(HOME_MANAGER_AGENT, True, id='home-manager'),
        pytest.param(UV_AGENT, False, id='uv-tool'),
        pytest.param(BROKEN_NIX_AGENT, False, id='nix-python'),
    ],
)
def test_managed_by_home_manager(agent, arguments, expected):
    write_agent(agent.plist, arguments)

    assert service.managed_by_home_manager() is expected


@pytest.mark.parametrize(
    'content',
    [
        pytest.param(b'not a plist', id='invalid-format'),
        pytest.param(plistlib.dumps({'ProgramArguments': []}), id='empty-program'),
    ],
)
def test_managed_by_home_manager_ignores_malformed(agent, content):
    agent.plist.write_bytes(content)

    assert service.managed_by_home_manager() is False


def test_install_refuses_nix_store_package(agent, monkeypatch):
    monkeypatch.setattr(
        'lb_scrobbler.service.__file__', str(NIX_PACKAGE / 'service.py')
    )

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        service.install(dry_run=False)

    agent.stop.assert_not_called()
    agent.load_token.assert_not_called()
    assert not agent.state.exists()


def test_install_refuses_home_manager_agent(agent):
    write_agent(agent.plist, HOME_MANAGER_AGENT)
    before = agent.plist.read_bytes()

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        service.install(dry_run=False)

    agent.stop.assert_not_called()
    agent.load_token.assert_not_called()
    assert agent.plist.read_bytes() == before


def test_uninstall_refuses_home_manager_agent(agent):
    write_agent(agent.plist, HOME_MANAGER_AGENT)

    with pytest.raises(RuntimeError, match=r'services\.listenbrainz-scrobbler'):
        service.uninstall()

    agent.stop.assert_not_called()
    assert agent.plist.exists()
