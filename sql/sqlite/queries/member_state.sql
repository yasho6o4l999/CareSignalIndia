SELECT member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
       generator_version, source_hash, is_active
FROM dim_member
ORDER BY member_id;
