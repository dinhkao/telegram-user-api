from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    date        TEXT,
    text        TEXT,
    raw_text    TEXT,
    text_norm   TEXT,
    media       TEXT,
    reply_to    INTEGER,
    updated_at  REAL,
    deleted     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_id_desc ON messages(id DESC) WHERE deleted = 0;
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text_norm,
    content='messages', content_rowid='id',
    tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text_norm) VALUES (new.id, new.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text_norm) VALUES('delete', old.id, old.text_norm);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text_norm) VALUES('delete', old.id, old.text_norm);
    INSERT INTO messages_fts(rowid, text_norm) VALUES (new.id, new.text_norm);
END;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
