SELECT member_id, condition
FROM bridge_member_condition c
INNER JOIN dim_member m USING (member_id)
WHERE m.is_active = 1
ORDER BY member_id, condition;
