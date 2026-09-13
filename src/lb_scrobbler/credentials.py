"""Keep the submission token in the user's macOS login Keychain."""

from keyring.backends.macOS import Keyring


SERVICE = 'xyz.hakula.listenbrainz-scrobbler'
ACCOUNT = 'listenbrainz'


def load_token() -> str:
    token = Keyring().get_password(SERVICE, ACCOUNT)
    if not token:
        raise RuntimeError('No token in Keychain. Run lb-scrobbler auth first.')
    return token


def save_token(token: str):
    Keyring().set_password(SERVICE, ACCOUNT, token)
