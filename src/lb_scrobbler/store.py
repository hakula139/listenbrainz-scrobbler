"""Persist playback checkpoints and an outbox in the same transaction."""

import json
import sqlite3
from pathlib import Path

from .tracking import Session, Tracker


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoint (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                retry_at REAL NOT NULL DEFAULT 0,
                error TEXT,
                blocked INTEGER NOT NULL DEFAULT 0
            );
        """)

    def close(self):
        self.db.close()

    def restore(self) -> Tracker:
        row = self.db.execute('SELECT data FROM checkpoint WHERE id = 1').fetchone()
        data = json.loads(row[0]) if row else None
        return Tracker(Session.decode(data) if data else None)

    def checkpoint(self, tracker: Tracker, payload: dict | None):
        with self.db:
            session = tracker.session
            self.db.execute(
                'INSERT OR REPLACE INTO checkpoint VALUES (1, ?)',
                (json.dumps(session.encode() if session else None),),
            )
            if payload is not None:
                assert session is not None
                self.db.execute(
                    'INSERT OR IGNORE INTO outbox (id, payload) VALUES (?, ?)',
                    (session.id, json.dumps(payload)),
                )

    def next(self, now: float) -> tuple | None:
        return self.db.execute(
            'SELECT id, payload, attempts FROM outbox '
            'WHERE blocked = 0 AND retry_at <= ? ORDER BY rowid LIMIT 1',
            (now,),
        ).fetchone()

    def acknowledge(self, key: str):
        with self.db:
            self.db.execute('DELETE FROM outbox WHERE id = ?', (key,))

    def fail(self, key: str, error: str, retry_at: float, blocked: bool = False):
        with self.db:
            self.db.execute(
                'UPDATE outbox SET attempts = attempts + 1, error = ?, '
                'retry_at = ?, blocked = ? WHERE id = ?',
                (error, retry_at, blocked, key),
            )

    def status(self) -> dict:
        pending, blocked = self.db.execute(
            'SELECT COUNT(*), COALESCE(SUM(blocked), 0) FROM outbox'
        ).fetchone()
        errors = self.db.execute(
            'SELECT DISTINCT error FROM outbox WHERE error IS NOT NULL'
        ).fetchall()
        return {
            'pending': pending,
            'blocked': blocked,
            'errors': [r[0] for r in errors],
        }

    def retry(self):
        with self.db:
            self.db.execute('UPDATE outbox SET blocked = 0, retry_at = 0')
