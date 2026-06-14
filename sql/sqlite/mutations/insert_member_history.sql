INSERT INTO dim_member_history(
    member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
    generator_version, source_hash, effective_from, is_current
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
