import json
import plistlib
from unittest.mock import Mock

import pytest

from lb_scrobbler import cli


def test_authenticate_imports_validated_smashtunes_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.Path, 'home', lambda: tmp_path)
    plist = tmp_path / (
        'Library/Containers/nl.smashbits.SmashTunes/Data/Library/'
        'Preferences/nl.smashbits.SmashTunes.plist'
    )
    plist.parent.mkdir(parents=True)
    plist.write_bytes(plistlib.dumps({'ListenBrainzToken': '  test-token  '}))
    validate = Mock(return_value='listener')
    save = Mock()
    monkeypatch.setattr(cli, 'validate_token', validate)
    monkeypatch.setattr(cli, 'save_token', save)

    cli.authenticate(True)

    validate.assert_called_once_with('test-token')
    save.assert_called_once_with('test-token')
    assert capsys.readouterr().out == 'Token saved in login Keychain for listener.\n'


def test_authenticate_never_saves_rejected_token(monkeypatch):
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: 'test-token')
    monkeypatch.setattr(
        cli, 'validate_token', Mock(side_effect=RuntimeError('invalid'))
    )
    save = Mock()
    monkeypatch.setattr(cli, 'save_token', save)

    with pytest.raises(RuntimeError, match='invalid'):
        cli.authenticate(False)

    save.assert_not_called()


def test_status_distinguishes_loaded_agent_from_last_observation(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cli.service, 'STATE', tmp_path)
    monkeypatch.setattr(cli.service, 'loaded', lambda: True)
    monkeypatch.setattr(cli.time, 'time', lambda: 102.5)

    cli.print_status()

    assert json.loads(capsys.readouterr().out) == {'agent_loaded': True}

    (tmp_path / cli.service.STATUS).write_text('{"updated_at": 100, "queued": 1}')

    cli.print_status()

    assert json.loads(capsys.readouterr().out) == {
        'updated_at': 100,
        'queued': 1,
        'agent_loaded': True,
        'observation_age_seconds': 2.5,
    }


@pytest.mark.parametrize(
    'contents',
    [
        pytest.param('{', id='invalid-json'),
        pytest.param('[]', id='array'),
        pytest.param('{"updated_at": null}', id='invalid-timestamp'),
        pytest.param(None, id='directory'),
    ],
)
def test_status_reports_unreadable_snapshot(tmp_path, monkeypatch, contents):
    monkeypatch.setattr(cli.service, 'STATE', tmp_path)
    monkeypatch.setattr(cli.service, 'loaded', lambda: False)
    path = tmp_path / cli.service.STATUS
    if contents is None:
        path.mkdir()
    else:
        path.write_text(contents)

    with pytest.raises(RuntimeError, match=r'status\.json'):
        cli.print_status()


@pytest.mark.parametrize(
    ('error', 'expected'),
    [
        (RuntimeError('Music observer exited'), 'Music observer exited'),
        (ValueError('private request details'), 'ValueError'),
    ],
)
def test_main_reports_safe_error_and_exits(monkeypatch, capsys, error, expected):
    monkeypatch.setattr('sys.argv', ['lb-scrobbler', 'probe'])
    monkeypatch.setattr(cli.os, 'umask', Mock())
    monkeypatch.setattr(cli, 'configure_logging', Mock())
    monkeypatch.setattr(cli, 'read_sample', Mock(side_effect=error))

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 1
    assert capsys.readouterr() == ('', f'Error: {expected}\n')
