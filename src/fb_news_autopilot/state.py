"""Persistent publication state machine and idempotency records."""
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import sqlite3

from .history import SQLiteHistory
from .security import redact


class State(StrEnum):
    DISCOVERED = 'DISCOVERED'
    FETCHED = 'FETCHED'
    SEMANTIC_PENDING = 'SEMANTIC_PENDING'
    VERIFIED = 'VERIFIED'
    REVIEW = 'REVIEW'
    REJECTED = 'REJECTED'
    EDITORIAL_PENDING = 'EDITORIAL_PENDING'
    EDITORIAL_READY = 'EDITORIAL_READY'
    ASSET_PENDING = 'ASSET_PENDING'
    ASSET_READY = 'ASSET_READY'
    HOLD_IMAGE_RIGHTS = 'HOLD_IMAGE_RIGHTS'
    COMPLIANCE_HOLD = 'COMPLIANCE_HOLD'
    READY_TO_PUBLISH = 'READY_TO_PUBLISH'
    PUBLISHING = 'PUBLISHING'
    PUBLISHED = 'PUBLISHED'
    PUBLISHED_COMMENT_PENDING = 'PUBLISHED_COMMENT_PENDING'
    RECONCILIATION_REQUIRED = 'RECONCILIATION_REQUIRED'
    COMMENTED = 'COMMENTED'
    VERIFIED_ON_FACEBOOK = 'VERIFIED_ON_FACEBOOK'
    FAILED = 'FAILED'


ALLOWED = {
    None: {State.DISCOVERED},
    State.DISCOVERED: {State.FETCHED, State.REJECTED, State.FAILED},
    State.FETCHED: {State.SEMANTIC_PENDING, State.REJECTED, State.FAILED},
    State.SEMANTIC_PENDING: {State.VERIFIED, State.REVIEW, State.REJECTED, State.FAILED},
    State.VERIFIED: {State.EDITORIAL_PENDING, State.FAILED},
    State.EDITORIAL_PENDING: {State.EDITORIAL_READY, State.COMPLIANCE_HOLD, State.FAILED},
    State.EDITORIAL_READY: {State.ASSET_PENDING, State.COMPLIANCE_HOLD, State.FAILED},
    State.ASSET_PENDING: {State.ASSET_READY, State.HOLD_IMAGE_RIGHTS, State.FAILED},
    State.ASSET_READY: {State.READY_TO_PUBLISH, State.COMPLIANCE_HOLD, State.FAILED},
    State.READY_TO_PUBLISH: {State.PUBLISHING, State.FAILED},
    State.PUBLISHING: {State.PUBLISHED, State.RECONCILIATION_REQUIRED, State.FAILED},
    State.PUBLISHED: {State.PUBLISHED_COMMENT_PENDING, State.COMMENTED, State.FAILED},
    State.PUBLISHED_COMMENT_PENDING: {State.PUBLISHED_COMMENT_PENDING, State.COMMENTED, State.FAILED},
    State.COMMENTED: {State.VERIFIED_ON_FACEBOOK, State.FAILED},
    State.REVIEW: set(), State.REJECTED: set(),
    State.HOLD_IMAGE_RIGHTS: {State.ASSET_PENDING},
    State.COMPLIANCE_HOLD: set(), State.RECONCILIATION_REQUIRED: set(),
    State.VERIFIED_ON_FACEBOOK: set(), State.FAILED: set(),
}


def publication_key(canonical_url, editorial_version):
    return hashlib.sha256((canonical_url.strip() + '\n' + editorial_version.strip()).encode()).hexdigest()


class StateStore:
    def __init__(self, path, run_id):
        self.history = SQLiteHistory(path, run_id)
        self.run_id = run_id

    def current(self, news_id):
        with self.history.connect() as connection:
            row = connection.execute('SELECT next_state FROM state_transitions WHERE run_id=? AND news_id=? ORDER BY id DESC LIMIT 1', (self.run_id, news_id)).fetchone()
        return State(row['next_state']) if row else None

    def transition(self, news_id, next_state, reason, retry_count=0):
        next_state = State(next_state)
        now = datetime.now(timezone.utc).isoformat()
        with self.history.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT next_state FROM state_transitions WHERE run_id=? AND news_id=? ORDER BY id DESC LIMIT 1', (self.run_id, news_id)).fetchone()
            previous = State(row['next_state']) if row else None
            if next_state not in ALLOWED[previous]:
                raise ValueError(f'Invalid transition: {previous} -> {next_state}')
            connection.execute('''INSERT INTO state_transitions
                (run_id,news_id,timestamp,previous_state,next_state,reason,retry_count)
                VALUES(?,?,?,?,?,?,?)''', (self.run_id, news_id, now,
                previous.value if previous else None, next_state.value, redact(reason), retry_count))
        return next_state

    def transitions(self, news_id):
        with self.history.connect() as connection:
            rows=connection.execute('''SELECT previous_state,next_state,reason,retry_count
                FROM state_transitions WHERE run_id=? AND news_id=? ORDER BY id''',
                (self.run_id,news_id)).fetchall()
        return [dict(row) for row in rows]

    def recent_publication(self, canonical_url, since, *, exclude_news_id=None):
        """Return the newest non-abandoned publication for a URL inside a cooldown."""
        with self.history.connect() as connection:
            row=connection.execute('''SELECT * FROM publication_history
                WHERE canonical_url=? AND created_at>=? AND status NOT IN ('FAILED')
                AND (? IS NULL OR news_id<>?) ORDER BY created_at DESC LIMIT 1''',
                (canonical_url,since,exclude_news_id,exclude_news_id)).fetchone()
        return dict(row) if row else None

    def reserve_publication(self, news_id, canonical_url, editorial_version):
        key = publication_key(canonical_url, editorial_version)
        now = datetime.now(timezone.utc).isoformat()
        with self.history.connect() as connection:
            cursor = connection.execute('''INSERT OR IGNORE INTO publication_history
                (idempotency_key,run_id,news_id,canonical_url,editorial_version,status,created_at,updated_at)
                VALUES(?,?,?,?,?,'RESERVED',?,?)''',
                (key, self.run_id, news_id, canonical_url, editorial_version, now, now))
            row = connection.execute('SELECT * FROM publication_history WHERE idempotency_key=?', (key,)).fetchone()
        return key, cursor.rowcount == 1, dict(row)

    def record_publication(self, key, result, status='PUBLISHED'):
        now = datetime.now(timezone.utc).isoformat()
        with self.history.connect() as connection:
            connection.execute('''UPDATE publication_history SET status=?,page_id=?,photo_id=?,post_id=?,updated_at=?
                WHERE idempotency_key=?''', (status, result.page_id, result.photo_id, result.post_id, now, key))

    def set_publication_status(self, key, status):
        now = datetime.now(timezone.utc).isoformat()
        with self.history.connect() as connection:
            connection.execute('UPDATE publication_history SET status=?,updated_at=? WHERE idempotency_key=?',
                               (status, now, key))

    def publication(self, key):
        with self.history.connect() as connection:
            row = connection.execute('SELECT * FROM publication_history WHERE idempotency_key=?', (key,)).fetchone()
        return dict(row) if row else None

    def comment_recorded(self, post_id):
        with self.history.connect() as connection:
            return connection.execute('SELECT comment_id FROM comment_history WHERE post_id=?', (post_id,)).fetchone() is not None

    def record_comment(self, result):
        try:
            with self.history.connect() as connection:
                connection.execute('INSERT INTO comment_history(post_id,comment_id,published_at) VALUES(?,?,?)',
                                   (result.post_id, result.comment_id, result.published_at))
        except sqlite3.IntegrityError as exc:
            raise ValueError('First comment is already recorded') from exc
