from datetime import datetime, timedelta, timezone

import duckdb

from src.models import QualityResult


def run_quality_checks(run_id: str, raw_root: str) -> list[QualityResult]:
    checked_at = datetime.now(timezone.utc)
    connection = duckdb.connect()
    weather = f"{raw_root}/source=open_meteo_weather/run_id={run_id}/*.parquet"
    air = f"{raw_root}/source=open_meteo_air_quality/run_id={run_id}/*.parquet"
    checks: list[QualityResult] = []
    for dataset, path in [("weather", weather), ("air_quality", air)]:
        count, unique_count, latest = connection.execute(
            f"""
            SELECT count(*), count(DISTINCT city_id || '|' || CAST(observed_at AS VARCHAR)), max(observed_at)
            FROM read_parquet('{path}')
            """
        ).fetchone()
        checks.append(
            QualityResult(
                run_id=run_id,
                check_name="non_empty",
                dataset=dataset,
                status="pass" if count > 0 else "fail",
                details=f"rows={count}",
                checked_at=checked_at,
            )
        )
        expected_minimum = 5 * 24
        checks.append(
            QualityResult(
                run_id=run_id,
                check_name="forecast_coverage",
                dataset=dataset,
                status="pass" if count >= expected_minimum else "warning",
                details=f"rows={count}, expected_minimum={expected_minimum}",
                checked_at=checked_at,
            )
        )
        checks.append(
            QualityResult(
                run_id=run_id,
                check_name="unique_natural_key",
                dataset=dataset,
                status="pass" if count == unique_count else "fail",
                details=f"rows={count}, unique={unique_count}",
                checked_at=checked_at,
            )
        )
        is_fresh = latest is not None and latest >= checked_at - timedelta(hours=6)
        checks.append(
            QualityResult(
                run_id=run_id,
                check_name="forecast_freshness",
                dataset=dataset,
                status="pass" if is_fresh else "fail",
                details=f"latest_observed_at={latest}",
                checked_at=checked_at,
            )
        )
    return checks
