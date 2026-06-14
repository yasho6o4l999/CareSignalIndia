import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sql import render_sql


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark dashboard-style member-risk aggregations.")
    parser.add_argument("--member-risk-path", required=True, type=Path)
    parser.add_argument("--decision-date", required=True)
    parser.add_argument("--base-members", type=int, default=5000)
    parser.add_argument("--sizes", nargs="+", type=int, default=[5000, 100000, 1000000])
    arguments = parser.parse_args()
    connection = duckdb.connect()
    results = []
    for size in arguments.sizes:
        factor = max(1, round(size / arguments.base_members))
        sql = render_sql(
            "benchmark/member_scale_dashboard.sql",
            member_risk_exposure_path=arguments.member_risk_path,
            decision_date=arguments.decision_date,
            scale_factor=factor,
        )
        started = time.perf_counter()
        rows = connection.execute(sql).fetchall()
        results.append({
            "target_members": size,
            "scale_factor": factor,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "result_rows": len(rows),
        })
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
