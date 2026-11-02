from contextlib import closing

import support

from lb_scrobbler.store import Store
from lb_scrobbler.tracking import Tracker


def test_restart_keeps_queue_and_prevents_duplicate(store_path):
    current = support.session()
    current.queued = True
    tracker = Tracker(current)
    with closing(Store(store_path)) as store:
        store.checkpoint(tracker, current.payload())

    with closing(Store(store_path)) as store:
        store.checkpoint(store.restore(), None)
        assert store.status()['pending'] == 1
        assert store.next(2000).id == current.id

    with closing(Store(store_path)) as store:
        assert store.restore().session.queued is True


def test_fail_defers_retry_and_counts_attempts(store):
    current = support.session()
    tracker = Tracker(current)
    store.checkpoint(tracker, current.payload())

    store.fail(current.id, 'HTTP 503', 2100)

    assert store.next(2099) is None
    assert store.next(2100).attempts == 1


def test_acknowledgement_survives_reopen(store_path):
    current = support.session()
    tracker = Tracker(current)
    with closing(Store(store_path)) as store:
        store.checkpoint(tracker, current.payload())
        store.acknowledge(current.id)

    with closing(Store(store_path)) as store:
        assert store.next(2000) is None


def test_blocked_payload_is_retained_for_manual_retry(store):
    current = support.session()
    tracker = Tracker(current)
    store.checkpoint(tracker, current.payload())

    store.fail(current.id, 'HTTP 400', 0, blocked=True)

    assert store.next(2000) is None
    assert store.status()['errors'] == ['HTTP 400']
    store.retry()
    assert store.next(2000).id == current.id
