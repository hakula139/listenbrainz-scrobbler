import httpx

from lb_scrobbler.tracking import Sample, Session


API = 'https://api.listenbrainz.org/1/'


def session(state='playing', title='Track', key='session'):
    return Session(key, Sample(state, title, 'Artist', 'Album', 120, 0), 1000, 1000)


def mock_http(handler) -> httpx.Client:
    return httpx.Client(base_url=API, transport=httpx.MockTransport(handler))
