ALTER TABLE pipeline_runs ADD COLUMN member_snapshot_id TEXT;

CREATE TABLE IF NOT EXISTS dim_member (
    member_id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    age_band TEXT NOT NULL CHECK (age_band IN ('18-39', '40-59', '60+')),
    preferred_language TEXT NOT NULL,
    preferred_channel TEXT NOT NULL CHECK (preferred_channel IN ('app', 'sms', 'call')),
    outreach_consent INTEGER NOT NULL CHECK (outreach_consent IN (0, 1)),
    last_contact_date TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bridge_member_condition (
    member_id TEXT NOT NULL REFERENCES dim_member(member_id) ON DELETE CASCADE,
    condition TEXT NOT NULL CHECK (condition IN ('diabetes', 'cardiovascular', 'renal', 'respiratory')),
    PRIMARY KEY (member_id, condition)
);

CREATE TABLE IF NOT EXISTS member_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    generator_version TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    manifest_checksum TEXT NOT NULL,
    member_count INTEGER NOT NULL,
    condition_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('published', 'invalid'))
);

CREATE INDEX IF NOT EXISTS idx_dim_member_city ON dim_member(city_id);
CREATE INDEX IF NOT EXISTS idx_member_condition_condition ON bridge_member_condition(condition);
