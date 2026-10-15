"""SQLite kalıcı depolama ve CSV dışa aktarma."""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    username        TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    ig_id           TEXT,
    name            TEXT,
    biography       TEXT,
    website         TEXT,
    followers_count INTEGER,
    follows_count   INTEGER,
    media_count     INTEGER,
    avg_likes       REAL,
    avg_comments    REAL,
    engagement_rate REAL,
    posts_per_week  REAL,
    PRIMARY KEY (username, fetched_at)
);

CREATE TABLE IF NOT EXISTS media (
    id                 TEXT PRIMARY KEY,
    owner_username     TEXT,
    caption            TEXT,
    media_type         TEXT,
    media_product_type TEXT,
    like_count         INTEGER,
    comments_count     INTEGER,
    timestamp          TEXT,
    permalink          TEXT,
    fetched_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hashtags (
    name       TEXT PRIMARY KEY,
    hashtag_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hashtag_media (
    hashtag    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    media_id   TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (hashtag, kind, media_id)
);

CREATE TABLE IF NOT EXISTS insights (
    scope      TEXT NOT NULL,
    object_id  TEXT NOT NULL,
    metric     TEXT NOT NULL,
    value      REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (scope, object_id, metric, fetched_at)
);
"""

TABLES = ("account_snapshots", "media", "hashtags", "hashtag_media", "insights")


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Storage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def save_account_snapshot(self, profile: dict, summary: dict, fetched_at: str | None = None) -> None:
        fetched_at = fetched_at or utcnow()
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO account_snapshots VALUES
                   (:username, :fetched_at, :ig_id, :name, :biography, :website, :followers_count,
                    :follows_count, :media_count, :avg_likes, :avg_comments, :engagement_rate, :posts_per_week)""",
                {
                    "username": profile.get("username"),
                    "fetched_at": fetched_at,
                    "ig_id": profile.get("id"),
                    "name": profile.get("name"),
                    "biography": profile.get("biography"),
                    "website": profile.get("website"),
                    "followers_count": profile.get("followers_count"),
                    "follows_count": profile.get("follows_count"),
                    "media_count": profile.get("media_count"),
                    "avg_likes": summary.get("avg_likes"),
                    "avg_comments": summary.get("avg_comments"),
                    "engagement_rate": summary.get("engagement_rate"),
                    "posts_per_week": summary.get("posts_per_week"),
                },
            )

    def save_media(self, media: Iterable[dict], owner_username: str | None = None,
                   fetched_at: str | None = None) -> None:
        fetched_at = fetched_at or utcnow()
        with self.conn:
            self.conn.executemany(
                """INSERT INTO media VALUES
                   (:id, :owner, :caption, :media_type, :media_product_type, :like_count,
                    :comments_count, :timestamp, :permalink, :fetched_at)
                   ON CONFLICT(id) DO UPDATE SET
                     owner_username = COALESCE(excluded.owner_username, media.owner_username),
                     caption = excluded.caption,
                     like_count = excluded.like_count,
                     comments_count = excluded.comments_count,
                     fetched_at = excluded.fetched_at""",
                [
                    {
                        "id": m["id"],
                        "owner": owner_username,
                        "caption": m.get("caption"),
                        "media_type": m.get("media_type"),
                        "media_product_type": m.get("media_product_type"),
                        "like_count": m.get("like_count"),
                        "comments_count": m.get("comments_count"),
                        "timestamp": m.get("timestamp"),
                        "permalink": m.get("permalink"),
                        "fetched_at": fetched_at,
                    }
                    for m in media
                ],
            )

    def get_hashtag_id(self, name: str) -> str | None:
        row = self.conn.execute("SELECT hashtag_id FROM hashtags WHERE name = ?", (name,)).fetchone()
        return row["hashtag_id"] if row else None

    def save_hashtag_id(self, name: str, hashtag_id: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO hashtags VALUES (?, ?)", (name, hashtag_id))

    def save_hashtag_media(self, hashtag: str, kind: str, media: list[dict]) -> None:
        fetched_at = utcnow()
        self.save_media(media, fetched_at=fetched_at)
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO hashtag_media VALUES (?, ?, ?, ?)",
                [(hashtag, kind, m["id"], fetched_at) for m in media],
            )

    def save_insights(self, scope: str, object_id: str, values: dict[str, float | None],
                      fetched_at: str | None = None) -> None:
        fetched_at = fetched_at or utcnow()
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO insights VALUES (?, ?, ?, ?, ?)",
                [(scope, object_id, metric, value, fetched_at) for metric, value in values.items()],
            )

    def account_history(self, username: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT fetched_at, followers_count, media_count, engagement_rate, posts_per_week
               FROM account_snapshots WHERE username = ? ORDER BY fetched_at""",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]

    def table_rows(self, table: str) -> list[dict]:
        if table not in TABLES:
            raise ValueError(f"Bilinmeyen tablo: {table}. Seçenekler: {', '.join(TABLES)}")
        return [dict(r) for r in self.conn.execute(f"SELECT * FROM {table}")]


def write_csv(rows: Sequence[dict], path: str | Path, columns: Sequence[str] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = list(dict.fromkeys(key for row in rows for key in row))
    # utf-8-sig: Excel'in Türkçe karakterleri doğru göstermesi için BOM ekler.
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path
