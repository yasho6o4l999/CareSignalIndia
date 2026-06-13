INSERT INTO dim_member(
    member_id, city_id, age_band, preferred_language, preferred_channel,
    outreach_consent, last_contact_date, generator_version, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
