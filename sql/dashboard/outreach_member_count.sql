SELECT count(DISTINCT member_id)
FROM read_parquet('{outreach_queue_path}');

