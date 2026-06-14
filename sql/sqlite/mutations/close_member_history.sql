UPDATE dim_member_history
SET effective_to = ?, is_current = 0
WHERE member_id = ? AND is_current = 1;
