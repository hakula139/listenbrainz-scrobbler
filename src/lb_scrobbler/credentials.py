"""Keep the submission token in the user's macOS login Keychain."""

SERVICE = 'xyz.hakula.listenbrainz-scrobbler'
ACCOUNT = 'listenbrainz'


def load_token() -> str:
    from keyring.backends.macOS import Keyring

    token = Keyring().get_password(SERVICE, ACCOUNT)
    if not isinstance(token, str) or not token:
        raise RuntimeError('No token in Keychain. Run lb-scrobbler auth first.')
    return token


def save_token(token: str) -> None:
    from keyring.backends.macOS import Keyring

    Keyring().set_password(SERVICE, ACCOUNT, token)
