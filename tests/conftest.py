from contextlib import closing

import pytest

from lb_scrobbler.store import Store


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / 'state.sqlite3'


@pytest.fixture
def store(store_path):
    with closing(Store(store_path)) as store:
        yield store
