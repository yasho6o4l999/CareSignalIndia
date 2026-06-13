INSERT INTO pipeline_runs(
    run_id, started_at, status, ruleset_version, member_generator_version, baseline_end_year
)
VALUES (?, ?, 'running', ?, ?, ?);
