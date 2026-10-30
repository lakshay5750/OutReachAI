import sqlite3
from config import DB_PATH


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't already exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS influencers (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT    NOT NULL,
            platform            TEXT    NOT NULL,
            profile_url         TEXT    UNIQUE NOT NULL,
            follower_count      INTEGER,
            engagement_rate     REAL,
            niche               TEXT,
            content_themes      TEXT,          -- JSON array
            contact_email       TEXT,
            bio                 TEXT,
            recent_post_caption TEXT,
            recent_post_url     TEXT,
            audience_age        TEXT,
            audience_gender     TEXT,
            audience_geography  TEXT,
            website             TEXT,
            passed_filter       INTEGER DEFAULT 0,
            filter_reason       TEXT,
            category            TEXT,
            discovered_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS outreach_log (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            influencer_id    INTEGER NOT NULL REFERENCES influencers(id),
            platform         TEXT    NOT NULL DEFAULT 'email',
            email            TEXT,
            email_subject    TEXT,
            email_body       TEXT,
            dm_text          TEXT,
            sent_at          TIMESTAMP,
            status           TEXT    DEFAULT 'pending',
            error_message    TEXT,
            UNIQUE(influencer_id, platform)     -- prevents duplicate outreach
        );
    """)
    conn.commit()
    conn.close()
