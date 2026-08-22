CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    source TEXT,
    external_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    url TEXT,
    description TEXT,
    scraped_at TIMESTAMP,
    relevance_score REAL,
    status TEXT DEFAULT 'new',  -- new / scored / pending_approval / approved / letter_drafted / reviewed / sent / rejected
    UNIQUE (source, external_id)  -- external_id is only unique per source, not globally
    -- rejected_at / rejected_stage / rejected_reason are added via
    -- db/migrations.py (ensure_columns), not here -- see that file
);

CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    draft TEXT,
    generated_at TIMESTAMP,
    edited BOOLEAN DEFAULT 0,
    final_text TEXT
);

-- Small key/value table for lightweight app state, such as the last-processed
-- Telegram update_id (keeps old Approve/Reject clicks from being fetched and
-- processed again on every run).
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
