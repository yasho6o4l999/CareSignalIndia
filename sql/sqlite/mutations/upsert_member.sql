INSERT INTO dim_member(
    member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
    last_contact_date, generator_version, updated_at, source_hash, is_active
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
ON CONFLICT(member_id) DO UPDATE SET
    city_id = excluded.city_id,
    age_band = excluded.age_band,
    preferred_language = excluded.preferred_language,
    preferred_channel = excluded.preferred_channel,
    outreach_consent = excluded.outreach_consent,
    generator_version = excluded.generator_version,
    updated_at = excluded.updated_at,
    source_hash = excluded.source_hash,
    is_active = 1;
