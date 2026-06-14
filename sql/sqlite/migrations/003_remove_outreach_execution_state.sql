-- Outreach execution is outside this assignment's scope. Rebuild the member
-- reference tables so existing databases lose contact history without losing
-- the current member population or condition mappings.
PRAGMA foreign_keys = OFF;

CREATE TABLE dim_member_without_outreach (
    member_id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    age_band TEXT NOT NULL CHECK (age_band IN ('18-39', '40-59', '60+')),
    preferred_language TEXT NOT NULL,
    preferred_channel TEXT NOT NULL CHECK (preferred_channel IN ('app', 'sms', 'call')),
    outreach_consent INTEGER NOT NULL CHECK (outreach_consent IN (0, 1)),
    generator_version TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

INSERT INTO dim_member_without_outreach (
    member_id, city_id, age_band, preferred_language, preferred_channel,
    outreach_consent, generator_version, updated_at, source_hash, is_active
)
SELECT
    member_id, city_id, age_band, preferred_language, preferred_channel,
    outreach_consent, generator_version, updated_at, source_hash, is_active
FROM dim_member;

CREATE TABLE bridge_member_condition_without_outreach (
    member_id TEXT NOT NULL REFERENCES dim_member_without_outreach(member_id) ON DELETE CASCADE,
    condition TEXT NOT NULL CHECK (condition IN ('diabetes', 'cardiovascular', 'renal', 'respiratory')),
    PRIMARY KEY (member_id, condition)
);

INSERT INTO bridge_member_condition_without_outreach (member_id, condition)
SELECT member_id, condition
FROM bridge_member_condition;

DROP TABLE bridge_member_condition;
DROP TABLE IF EXISTS member_outreach_activity;
DROP TABLE dim_member;

ALTER TABLE dim_member_without_outreach RENAME TO dim_member;
ALTER TABLE bridge_member_condition_without_outreach RENAME TO bridge_member_condition;

CREATE INDEX IF NOT EXISTS idx_dim_member_active_city
ON dim_member(is_active, city_id);

CREATE INDEX IF NOT EXISTS idx_member_condition_condition
ON bridge_member_condition(condition);

PRAGMA foreign_keys = ON;
