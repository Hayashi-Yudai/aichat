CREATE TABLE IF NOT EXISTS message (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    chat_id         TEXT NOT NULL,
    role            TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    content         TEXT,
    system_content  TEXT
);
