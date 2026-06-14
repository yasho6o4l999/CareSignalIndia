SELECT m.member_id, m.city_id, m.age_band, m.preferred_language, m.preferred_channel,
       m.outreach_consent,
       coalesce(max(a.occurred_at), m.last_contact_date) AS last_contact_date,
       m.generator_version
FROM dim_member m
LEFT JOIN member_outreach_activity a USING (member_id)
WHERE m.is_active = 1
GROUP BY m.member_id, m.city_id, m.age_band, m.preferred_language, m.preferred_channel,
         m.outreach_consent, m.last_contact_date, m.generator_version
ORDER BY member_id;
