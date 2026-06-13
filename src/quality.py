from datetime import date, datetime, timedelta, timezone

import duckdb

from src.config import load_cities
from src.models import QualityResult
from src.sql import render_sql


def run_quality_checks(run_id: str, raw_root: str) -> list[QualityResult]:
    checked_at = datetime.now(timezone.utc)
    connection = duckdb.connect()
    weather = f"{raw_root}/source=open_meteo_weather/run_id={run_id}/*.parquet"
    air = f"{raw_root}/source=open_meteo_air_quality/run_id={run_id}/*.parquet"
    checks: list[QualityResult] = []
    for dataset, path in [("weather", weather), ("air_quality", air)]:
        count, unique_count, latest = connection.execute(
            render_sql("quality/profile_dataset.sql", dataset_path=path)
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
        expected_minimum = len(load_cities()) * 24
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
    historical = f"{raw_root}/source=nasa_power_daily/schema_version=v2/baseline_end_year={date.today().year - 1}/**/*.parquet"
    expected_cities = len(load_cities())
    count, city_count, year_count, latest = connection.execute(
        render_sql("quality/profile_historical_dataset.sql", dataset_path=historical)
    ).fetchone()
    checks.extend(
        [
            QualityResult(
                run_id=run_id,
                check_name="historical_coverage",
                dataset="historical_weather",
                status="pass" if count >= expected_cities * 365 * 5 * 0.95 else "fail",
                details=f"rows={count}, cities={city_count}, years={year_count}",
                checked_at=checked_at,
            ),
            QualityResult(
                run_id=run_id,
                check_name="historical_city_coverage",
                dataset="historical_weather",
                status="pass" if city_count == expected_cities else "fail",
                details=f"cities={city_count}",
                checked_at=checked_at,
            ),
            QualityResult(
                run_id=run_id,
                check_name="historical_year_coverage",
                dataset="historical_weather",
                status="pass" if year_count == 5 else "fail",
                details=f"years={year_count}, latest={latest}",
                checked_at=checked_at,
            ),
        ]
    )
    return checks
