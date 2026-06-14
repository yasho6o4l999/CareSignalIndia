# Performance Benchmark

The deterministic benchmark scales the retained member-risk fact through DuckDB and executes a representative
city and severity aggregation without pandas.

```bash
python scripts/benchmark_dashboard.py \
  --member-risk-path data/analytical_history/run_id=<run-id>/member_risk_exposure_daily.parquet \
  --decision-date 2026-06-14
```

Results measured locally on June 14, 2026:

| Target member scale | Duration |
|---:|---:|
| 5,000 | 3.77 ms |
| 100,000 | 4.14 ms |
| 1,000,000 | 17.88 ms |

These results measure one representative aggregation against synthetically scaled exposure rows; they are
not a full production load test. They demonstrate that columnar Parquet scans and DuckDB aggregation remain
responsive at the assignment's target scales. Production benchmarking should additionally capture peak
memory, concurrent dashboard users, object-storage latency, and end-to-end mart build duration.
