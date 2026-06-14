UPDATE dim_member
SET is_active = 0, updated_at = ?
WHERE member_id = ?;
