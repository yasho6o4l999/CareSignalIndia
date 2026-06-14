ALTER TABLE dim_member ADD COLUMN source_hash TEXT;
ALTER TABLE dim_member ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1));

CREATE TABLE IF NOT EXISTS dim_member_history (
    member_history_sk INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL,
    city_id TEXT NOT NULL,
    age_band TEXT NOT NULL,
    preferred_language TEXT NOT NULL,
    preferred_channel TEXT NOT NULL,
    outreach_consent INTEGER NOT NULL,
    generator_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1))
);

CREATE TABLE IF NOT EXISTS member_outreach_activity (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES dim_member(member_id),
    activity_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    source TEXT NOT NULL,
    UNIQUE(member_id, activity_type, occurred_at, source)
);

CREATE TABLE IF NOT EXISTS member_sync_runs (
    sync_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    inserted INTEGER NOT NULL,
    updated INTEGER NOT NULL,
    deactivated INTEGER NOT NULL,
    unchanged INTEGER NOT NULL,
    condition_changes INTEGER NOT NULL,
    changed_cities TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_member_history_current ON dim_member_history(member_id, is_current);
CREATE INDEX IF NOT EXISTS idx_member_activity_member_time ON member_outreach_activity(member_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_dim_member_active_city ON dim_member(is_active, city_id);

INSERT INTO dim_member_history(
    member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
    generator_version, source_hash, effective_from, is_current
)
SELECT member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
       generator_version, coalesce(source_hash, ''), updated_at, 1
FROM dim_member;

INSERT OR IGNORE INTO member_outreach_activity(member_id, activity_type, occurred_at, source)
SELECT member_id, 'contact', last_contact_date, 'legacy_dimension'
FROM dim_member;
