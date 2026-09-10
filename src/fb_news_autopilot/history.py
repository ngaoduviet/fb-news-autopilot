"""Persistent Package 01 run/history store using Python's SQLite library."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .models import ArticleEvidence, DuplicateIndex, DuplicateRecord, url_key, valid_url
from .security import redact


SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, run_at TEXT NOT NULL, timezone TEXT NOT NULL,
  mode TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
  news_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
  discovered_url TEXT NOT NULL, normalized_url TEXT NOT NULL,
  candidate_title TEXT NOT NULL, publisher TEXT, discovery_provider TEXT NOT NULL,
  story_cluster_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verifications (
  news_id TEXT PRIMARY KEY REFERENCES candidates(news_id), status TEXT NOT NULL,
  resolved_article_url TEXT, canonical_url TEXT, verified_event_key TEXT,
  effective_freshness_time TEXT, freshness_bucket TEXT NOT NULL,
  rejection_codes TEXT NOT NULL, review_codes TEXT NOT NULL, verified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_history (
  id INTEGER PRIMARY KEY, normalized_url TEXT NOT NULL, verified_event_key TEXT,
  effective_freshness_time TEXT, first_seen_run TEXT NOT NULL,
  last_seen_run TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS event_history_url_event
  ON event_history(normalized_url, verified_event_key) WHERE verified_event_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS event_history_url_unknown
  ON event_history(normalized_url) WHERE verified_event_key IS NULL;
CREATE INDEX IF NOT EXISTS event_history_event_key ON event_history(verified_event_key);
CREATE TABLE IF NOT EXISTS run_failures (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL,
  error_type TEXT NOT NULL, sanitized_message TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_transitions (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, news_id TEXT NOT NULL,
  timestamp TEXT NOT NULL, previous_state TEXT, next_state TEXT NOT NULL,
  reason TEXT NOT NULL, retry_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS publication_history (
  idempotency_key TEXT PRIMARY KEY, run_id TEXT NOT NULL, news_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL, editorial_version TEXT NOT NULL,
  status TEXT NOT NULL, page_id TEXT, photo_id TEXT, post_id TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comment_history (
  post_id TEXT PRIMARY KEY, comment_id TEXT NOT NULL, published_at TEXT NOT NULL
);
"""


def sanitize_error(value: BaseException | str, secrets=()) -> str:
    return redact(value, secrets)


class SQLiteHistory:
    def __init__(self, path: str | Path, run_id: str):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.run_id=run_id
        self.initialize()

    def connect(self):
        connection=sqlite3.connect(self.path,timeout=10)
        connection.row_factory=sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def initialize(self):
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def start_run(self, context):
        now=datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute('''INSERT INTO runs(run_id,run_at,timezone,mode,started_at,status)
                VALUES(?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET status=excluded.status''',
                (context.run_id,context.run_at,context.timezone,context.mode,now,'RUNNING'))

    def complete_run(self, status: str):
        now=datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute('UPDATE runs SET completed_at=?,status=? WHERE run_id=?',(now,status,self.run_id))

    def record_candidate(self, candidate: dict):
        discovery=candidate['discovery']
        raw=discovery['discovered_url']
        normalized=url_key(raw) if valid_url(raw) else raw
        with self.connect() as connection:
            connection.execute('''INSERT INTO candidates(news_id,run_id,discovered_url,normalized_url,candidate_title,publisher,discovery_provider,story_cluster_id)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(news_id) DO UPDATE SET
                discovered_url=excluded.discovered_url,normalized_url=excluded.normalized_url,
                candidate_title=excluded.candidate_title,publisher=excluded.publisher,
                discovery_provider=excluded.discovery_provider,story_cluster_id=excluded.story_cluster_id''',
                (candidate['news_id'],self.run_id,raw,normalized,candidate['normalized']['title'],
                 discovery['publisher_name'],discovery['discovery_provider'],candidate['story_cluster_id']))

    def record_verification(self, result: dict, verified_event_key: str | None = None):
        source=result['source']; freshness=result['freshness']; verification=result['verification']
        with self.connect() as connection:
            connection.execute('''INSERT INTO verifications(news_id,status,resolved_article_url,canonical_url,verified_event_key,effective_freshness_time,freshness_bucket,rejection_codes,review_codes,verified_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(news_id) DO UPDATE SET
                status=excluded.status,resolved_article_url=excluded.resolved_article_url,
                canonical_url=excluded.canonical_url,verified_event_key=excluded.verified_event_key,
                effective_freshness_time=excluded.effective_freshness_time,freshness_bucket=excluded.freshness_bucket,
                rejection_codes=excluded.rejection_codes,review_codes=excluded.review_codes,verified_at=excluded.verified_at''',
                (result['news_id'],verification['status'],source['resolved_article_url'],source['canonical_url'],
                 verified_event_key,freshness['effective_freshness_time'],freshness['bucket'],
                 json.dumps(verification['rejection_codes']),json.dumps(verification['review_codes']),verification['verified_at']))

    def record_failure(self, stage: str, error: BaseException, *, secrets=()):
        occurred=datetime.now(timezone.utc).isoformat()
        message=sanitize_error(error,secrets)
        with self.connect() as connection:
            connection.execute('INSERT INTO run_failures(run_id,stage,error_type,sanitized_message,occurred_at) VALUES(?,?,?,?,?)',
                (self.run_id,stage,type(error).__name__,message,occurred))
        return {'run_id':self.run_id,'stage':stage,'error_type':type(error).__name__,
                'sanitized_message':message,'timestamp':occurred}

    def _index(self):
        with self.connect() as connection:
            rows=connection.execute('SELECT normalized_url,verified_event_key,effective_freshness_time FROM event_history').fetchall()
        return DuplicateIndex([DuplicateRecord(row['normalized_url'],row['verified_event_key'],row['effective_freshness_time']) for row in rows])

    def decision(self, evidence: ArticleEvidence) -> str:
        return self._index().decision(evidence)

    def accept(self, evidence: ArticleEvidence, effective_freshness_time: str | None):
        urls={url_key(value) for value in (evidence.final_url,evidence.canonical_url) if value and valid_url(value)}
        with self.connect() as connection:
            for normalized_url in urls:
                existing=connection.execute('''SELECT id FROM event_history WHERE normalized_url=? AND
                    ((verified_event_key=? ) OR (verified_event_key IS NULL AND ? IS NULL))''',
                    (normalized_url,evidence.verified_event_key,evidence.verified_event_key)).fetchone()
                if existing:
                    connection.execute('UPDATE event_history SET last_seen_run=?,effective_freshness_time=? WHERE id=?',
                        (self.run_id,effective_freshness_time,existing['id']))
                else:
                    connection.execute('''INSERT INTO event_history(normalized_url,verified_event_key,effective_freshness_time,first_seen_run,last_seen_run)
                        VALUES(?,?,?,?,?)''',(normalized_url,evidence.verified_event_key,effective_freshness_time,self.run_id,self.run_id))
