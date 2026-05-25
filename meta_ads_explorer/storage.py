from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .models import Ad

SCHEMA = """
CREATE TABLE IF NOT EXISTS ads (
    ad_archive_id TEXT PRIMARY KEY,
    page_id TEXT,
    page_name TEXT,
    page_profile_uri TEXT,
    start_date TEXT,
    end_date TEXT,
    is_active INTEGER,
    body_text TEXT,
    title TEXT,
    caption TEXT,
    cta_text TEXT,
    cta_type TEXT,
    link_url TEXT,
    publisher_platforms TEXT,
    images TEXT,
    videos TEXT,
    currency TEXT,
    raw_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ads_page_id ON ads(page_id);
CREATE INDEX IF NOT EXISTS idx_ads_is_active ON ads(is_active);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_archive_id TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    is_active INTEGER,
    snapshot_json TEXT NOT NULL,
    FOREIGN KEY (ad_archive_id) REFERENCES ads(ad_archive_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ad ON snapshots(ad_archive_id, seen_at);

CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT,
    country TEXT,
    ad_type TEXT,
    active_status TEXT,
    page_id TEXT,
    run_at TEXT NOT NULL,
    result_count INTEGER,
    raw_url TEXT
);

CREATE TABLE IF NOT EXISTS tracked_pages (
    page_id TEXT PRIMARY KEY,
    page_name TEXT,
    country TEXT,
    notes TEXT,
    added_at TEXT NOT NULL,
    last_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_archive_id TEXT NOT NULL,
    model TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    FOREIGN KEY (ad_archive_id) REFERENCES ads(ad_archive_id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_ad ON analyses(ad_archive_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_ads(self, ads: Iterable[Ad]) -> tuple[int, int]:
        """Inserta o actualiza anuncios. Devuelve (nuevos, vistos_de_nuevo)."""
        new_count = 0
        seen_count = 0
        now = _now()
        with self._conn() as c:
            for ad in ads:
                cur = c.execute(
                    "SELECT ad_archive_id FROM ads WHERE ad_archive_id = ?",
                    (ad.ad_archive_id,),
                )
                exists = cur.fetchone() is not None
                payload = {
                    "page_id": ad.page_id,
                    "page_name": ad.page_name,
                    "page_profile_uri": ad.page_profile_uri,
                    "start_date": ad.start_date.isoformat() if ad.start_date else None,
                    "end_date": ad.end_date.isoformat() if ad.end_date else None,
                    "is_active": int(bool(ad.is_active)) if ad.is_active is not None else None,
                    "body_text": ad.body_text,
                    "title": ad.title,
                    "caption": ad.caption,
                    "cta_text": ad.cta_text,
                    "cta_type": ad.cta_type,
                    "link_url": ad.link_url,
                    "publisher_platforms": json.dumps(ad.publisher_platforms),
                    "images": json.dumps(ad.images),
                    "videos": json.dumps(ad.videos),
                    "currency": ad.currency,
                    "raw_json": json.dumps(ad.raw, default=str),
                }
                if exists:
                    c.execute(
                        """UPDATE ads SET page_id=:page_id, page_name=:page_name,
                           page_profile_uri=:page_profile_uri, start_date=:start_date,
                           end_date=:end_date, is_active=:is_active, body_text=:body_text,
                           title=:title, caption=:caption, cta_text=:cta_text,
                           cta_type=:cta_type, link_url=:link_url,
                           publisher_platforms=:publisher_platforms, images=:images,
                           videos=:videos, currency=:currency, raw_json=:raw_json,
                           last_seen_at=:last_seen_at
                           WHERE ad_archive_id=:ad_archive_id""",
                        {**payload, "ad_archive_id": ad.ad_archive_id, "last_seen_at": now},
                    )
                    seen_count += 1
                else:
                    c.execute(
                        """INSERT INTO ads (ad_archive_id, page_id, page_name,
                           page_profile_uri, start_date, end_date, is_active, body_text,
                           title, caption, cta_text, cta_type, link_url,
                           publisher_platforms, images, videos, currency, raw_json,
                           first_seen_at, last_seen_at)
                           VALUES (:ad_archive_id, :page_id, :page_name, :page_profile_uri,
                           :start_date, :end_date, :is_active, :body_text, :title,
                           :caption, :cta_text, :cta_type, :link_url, :publisher_platforms,
                           :images, :videos, :currency, :raw_json, :first_seen_at,
                           :last_seen_at)""",
                        {
                            **payload,
                            "ad_archive_id": ad.ad_archive_id,
                            "first_seen_at": now,
                            "last_seen_at": now,
                        },
                    )
                    new_count += 1

                c.execute(
                    """INSERT INTO snapshots (ad_archive_id, seen_at, is_active, snapshot_json)
                       VALUES (?, ?, ?, ?)""",
                    (
                        ad.ad_archive_id,
                        now,
                        payload["is_active"],
                        json.dumps(ad.raw, default=str),
                    ),
                )
        return new_count, seen_count

    def log_search(
        self,
        query: str | None,
        country: str,
        ad_type: str,
        active_status: str,
        page_id: str | None,
        result_count: int,
        raw_url: str,
    ) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO searches (query, country, ad_type, active_status,
                   page_id, run_at, result_count, raw_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (query, country, ad_type, active_status, page_id, _now(), result_count, raw_url),
            )

    def add_tracked_page(self, page_id: str, page_name: str | None, country: str, notes: str | None) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO tracked_pages
                   (page_id, page_name, country, notes, added_at, last_checked_at)
                   VALUES (?, ?, ?, ?,
                       COALESCE((SELECT added_at FROM tracked_pages WHERE page_id=?), ?),
                       (SELECT last_checked_at FROM tracked_pages WHERE page_id=?))""",
                (page_id, page_name, country, notes, page_id, _now(), page_id),
            )

    def list_tracked_pages(self) -> list[sqlite3.Row]:
        with self._conn() as c:
            return list(c.execute("SELECT * FROM tracked_pages ORDER BY added_at DESC"))

    def mark_page_checked(self, page_id: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE tracked_pages SET last_checked_at=? WHERE page_id=?",
                (_now(), page_id),
            )

    def ads_for_page(self, page_id: str, only_active: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM ads WHERE page_id = ?"
        if only_active:
            sql += " AND is_active = 1"
        sql += " ORDER BY first_seen_at DESC"
        with self._conn() as c:
            return list(c.execute(sql, (page_id,)))

    def ad(self, ad_archive_id: str) -> sqlite3.Row | None:
        with self._conn() as c:
            cur = c.execute("SELECT * FROM ads WHERE ad_archive_id = ?", (ad_archive_id,))
            return cur.fetchone()

    def unanalyzed_ads(self, limit: int = 25) -> list[sqlite3.Row]:
        with self._conn() as c:
            return list(
                c.execute(
                    """SELECT a.* FROM ads a
                       LEFT JOIN analyses an ON an.ad_archive_id = a.ad_archive_id
                       WHERE an.id IS NULL
                       ORDER BY a.first_seen_at DESC
                       LIMIT ?""",
                    (limit,),
                )
            )

    def save_analysis(self, ad_archive_id: str, model: str, analysis: dict) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO analyses (ad_archive_id, model, analyzed_at, analysis_json)
                   VALUES (?, ?, ?, ?)""",
                (ad_archive_id, model, _now(), json.dumps(analysis, ensure_ascii=False)),
            )

    def analyses_summary(self, page_id: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
        sql = """SELECT a.ad_archive_id, a.page_name, a.body_text, a.cta_text,
                        an.analysis_json, an.analyzed_at
                 FROM analyses an
                 JOIN ads a ON a.ad_archive_id = an.ad_archive_id"""
        params: list = []
        if page_id:
            sql += " WHERE a.page_id = ?"
            params.append(page_id)
        sql += " ORDER BY an.analyzed_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as c:
            return list(c.execute(sql, params))

    def diff_for_page(self, page_id: str) -> dict:
        """Resumen de cambios para una página: activos vs inactivos, nuevos en 7d."""
        with self._conn() as c:
            active = c.execute(
                "SELECT COUNT(*) AS n FROM ads WHERE page_id=? AND is_active=1",
                (page_id,),
            ).fetchone()["n"]
            inactive = c.execute(
                "SELECT COUNT(*) AS n FROM ads WHERE page_id=? AND is_active=0",
                (page_id,),
            ).fetchone()["n"]
            recent = c.execute(
                """SELECT COUNT(*) AS n FROM ads
                   WHERE page_id=? AND first_seen_at >= datetime('now','-7 days')""",
                (page_id,),
            ).fetchone()["n"]
        return {"active": active, "inactive": inactive, "new_last_7d": recent}
