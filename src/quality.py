from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from src.config import QualityPolicy, load_cities, load_quality_policy
from src.models import QualityResult
from src.sql import render_sql


@dataclass(frozen=True)
class QualityProfile:
    run_id: str
    stage: str
    dataset: str
    metric_name: str
    metric_value: float
    recorded_at: datetime


def threshold_status(value: float, warning: float, failure: float) -> str:
    if value > failure:
        return "fail"
    if value > warning:
        return "warning"
    return "pass"


def count_status(value: int, maximum: int) -> str:
    return "pass" if value <= maximum else "fail"


def forecast_paths(raw_root: str, run_id: str) -> tuple[Path, Path]:
    raw = Path(raw_root)
    weather_root = raw / f"source=open_meteo_weather/run_id={run_id}"
    air_root = raw / f"source=open_meteo_air_quality/run_id={run_id}"
    weather = (
        weather_root / "compacted/data.parquet"
        if (weather_root / "compacted/data.parquet").exists()
        else weather_root / "*.parquet"
    )
    air = (
        air_root / "compacted/data.parquet"
        if (air_root / "compacted/data.parquet").exists()
        else air_root / "*.parquet"
    )
    return weather, air


def anomaly_result(
    run_id: str,
    dataset: str,
    row_count: int,
    previous_profiles: dict[tuple[str, str], tuple[float, int]],
    policy: QualityPolicy,
    checked_at: datetime,
) -> QualityResult:
    average, samples = previous_profiles.get((dataset, "row_count"), (0.0, 0))
    if samples < policy.anomaly_detection.minimum_history_runs or average == 0:
        return QualityResult(
            run_id=run_id, check_name="historical_row_count_anomaly", dataset=dataset,
            status="pass",
            details=f"rows={row_count}, baseline_samples={samples}, baseline=insufficient",
            checked_at=checked_at,
        )
    change_ratio = abs(row_count - average) / average
    return QualityResult(
        run_id=run_id, check_name="historical_row_count_anomaly", dataset=dataset,
        status=threshold_status(
            change_ratio,
            policy.anomaly_detection.row_count_change_warning_ratio,
            policy.anomaly_detection.row_count_change_fail_ratio,
        ),
        details=(
            f"rows={row_count}, historical_average={average:.2f}, "
            f"samples={samples}, change_ratio={change_ratio:.4f}"
        ),
        checked_at=checked_at,
    )


def run_staging_quality_checks(
    run_id: str,
    raw_root: str,
    publication_cities_path: Path,
    previous_profiles: dict[tuple[str, str], tuple[float, int]] | None = None,
    expected_city_count: int | None = None,
    policy: QualityPolicy | None = None,
) -> tuple[list[QualityResult], list[QualityProfile]]:
    checked_at = datetime.now(timezone.utc)
    policy = policy or load_quality_policy()
    previous_profiles = previous_profiles or {}
    connection = duckdb.connect()
    weather, air = forecast_paths(raw_root, run_id)
    expected_cities = expected_city_count or len(load_cities())
    checks: list[QualityResult] = []
    profiles: list[QualityProfile] = []

    for dataset, path in [("weather", weather), ("air_quality", air)]:
        count, unique_count, latest = connection.execute(
            render_sql("quality/profile_dataset.sql", dataset_path=path)
        ).fetchone()
        profiles.extend([
            QualityProfile(run_id, "source", dataset, "row_count", count, checked_at),
            QualityProfile(run_id, "source", dataset, "unique_count", unique_count, checked_at),
        ])
        source_policy = policy.source_datasets[dataset]
        expected_minimum = expected_cities * source_policy.minimum_records_per_city
        checks.extend([
            QualityResult(
                run_id=run_id, check_name="non_empty", dataset=dataset,
                status="pass" if count > 0 else "fail", details=f"rows={count}",
                checked_at=checked_at,
            ),
            QualityResult(
                run_id=run_id, check_name="forecast_coverage", dataset=dataset,
                status="pass" if count >= expected_minimum else "fail",
                details=f"rows={count}, expected_minimum={expected_minimum}", checked_at=checked_at,
            ),
            QualityResult(
                run_id=run_id, check_name="unique_natural_key", dataset=dataset,
                status="pass" if count == unique_count else "fail",
                details=f"rows={count}, unique={unique_count}", checked_at=checked_at,
            ),
            QualityResult(
                run_id=run_id, check_name="forecast_freshness", dataset=dataset,
                status=(
                    "pass"
                    if latest is not None
                    and latest >= checked_at - timedelta(hours=source_policy.maximum_age_hours)
                    else "fail"
                ),
                details=(
                    f"latest_observed_at={latest}, maximum_age_hours="
                    f"{source_policy.maximum_age_hours}"
                ),
                checked_at=checked_at,
            ),
            anomaly_result(run_id, dataset, count, previous_profiles, policy, checked_at),
        ])

    weather_rows, air_rows, matched, weather_only, air_only = connection.execute(
        render_sql(
            "quality/cross_source_reconciliation.sql",
            weather_path=weather,
            air_path=air,
            publication_cities_path=publication_cities_path,
        )
    ).fetchone()
    weather_loss = weather_only / weather_rows if weather_rows else 1.0
    air_loss = air_only / air_rows if air_rows else 1.0
    profiles.extend([
        QualityProfile(run_id, "staging", "weather_air_join", "matched_rows", matched, checked_at),
        QualityProfile(run_id, "staging", "weather_air_join", "weather_join_loss_ratio", weather_loss, checked_at),
        QualityProfile(run_id, "staging", "weather_air_join", "air_join_loss_ratio", air_loss, checked_at),
    ])
    checks.extend([
        QualityResult(
            run_id=run_id, check_name="cross_source_weather_join_loss",
            dataset="weather_air_join",
            status=threshold_status(
                weather_loss,
                policy.cross_source.weather_join_loss_warning_ratio,
                policy.cross_source.weather_join_loss_fail_ratio,
            ),
            details=(
                f"weather_rows={weather_rows}, matched_rows={matched}, "
                f"weather_only_rows={weather_only}, loss_ratio={weather_loss:.4f}"
            ),
            checked_at=checked_at,
        ),
        QualityResult(
            run_id=run_id, check_name="cross_source_air_quality_join_loss",
            dataset="weather_air_join",
            status=threshold_status(
                air_loss,
                policy.cross_source.air_quality_join_loss_warning_ratio,
                policy.cross_source.air_quality_join_loss_fail_ratio,
            ),
            details=(
                f"air_rows={air_rows}, matched_rows={matched}, "
                f"air_only_rows={air_only}, loss_ratio={air_loss:.4f}"
            ),
            checked_at=checked_at,
        ),
    ])

    historical = (
        f"{raw_root}/source=nasa_power_daily/schema_version=v2/"
        f"baseline_end_year={date.today().year - 1}/**/*.parquet"
    )
    count, city_count, year_count, latest = connection.execute(
        render_sql("quality/profile_historical_dataset.sql", dataset_path=historical)
    ).fetchone()
    profiles.append(QualityProfile(run_id, "source", "historical_weather", "row_count", count, checked_at))
    checks.extend([
        QualityResult(
            run_id=run_id, check_name="historical_coverage", dataset="historical_weather",
            status=(
                "pass"
                if count >= expected_cities * 365 * policy.historical.required_years
                * policy.historical.minimum_coverage_ratio
                else "fail"
            ),
            details=f"rows={count}, cities={city_count}, years={year_count}", checked_at=checked_at,
        ),
        QualityResult(
            run_id=run_id, check_name="historical_city_coverage", dataset="historical_weather",
            status="pass" if city_count >= expected_cities else "fail",
            details=f"cities={city_count}, expected_minimum={expected_cities}", checked_at=checked_at,
        ),
        QualityResult(
            run_id=run_id, check_name="historical_year_coverage", dataset="historical_weather",
            status="pass" if year_count == policy.historical.required_years else "fail",
            details=f"years={year_count}, latest={latest}", checked_at=checked_at,
        ),
        anomaly_result(run_id, "historical_weather", count, previous_profiles, policy, checked_at),
    ])
    connection.close()
    return checks, profiles


def run_cross_mart_quality_checks(
    run_id: str,
    staging: Path,
    policy: QualityPolicy | None = None,
) -> tuple[list[QualityResult], list[QualityProfile]]:
    policy = policy or load_quality_policy()
    checked_at = datetime.now(timezone.utc)
    connection = duckdb.connect()
    values = connection.execute(
        render_sql(
            "quality/cross_mart_integrity.sql",
            outreach_queue_path=staging / "outreach_queue.parquet",
            active_triggers_path=staging / "active_triggers.parquet",
            stakeholder_alerts_path=staging / "stakeholder_alerts.parquet",
            publication_cities_path=staging / "publication_cities.parquet",
        )
    ).fetchone()
    connection.close()
    names = [
        "consent_leakage",
        "duplicate_member_triggers",
        "invalid_persistence_windows",
        "orphan_outreach_triggers",
        "stakeholder_reconciliation_errors",
        "unapproved_city_records",
    ]
    checks = [
        QualityResult(
            run_id=run_id, check_name=name, dataset="published_marts",
            status=count_status(value, getattr(policy.cross_mart, f"maximum_{name}")),
            details=f"actual={value}, maximum={getattr(policy.cross_mart, f'maximum_{name}')}",
            checked_at=checked_at,
        )
        for name, value in zip(names, values, strict=True)
    ]
    profiles = [
        QualityProfile(run_id, "mart", "published_marts", name, value, checked_at)
        for name, value in zip(names, values, strict=True)
    ]
    return checks, profiles
