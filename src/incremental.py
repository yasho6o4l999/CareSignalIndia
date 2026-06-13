from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
from pydantic import BaseModel

from src.sql import render_sql
from src.storage import write_models


@dataclass(frozen=True)
class ChangeMetrics:
    inserted: int
    updated: int
    unchanged: int
    rejected: int = 0


SQL_BY_SOURCE = {
    "open_meteo_weather": (
        "incremental/weather_change_metrics.sql",
        "incremental/merge_weather_snapshot.sql",
    ),
    "open_meteo_air_quality": (
        "incremental/air_quality_change_metrics.sql",
        "incremental/merge_air_quality_snapshot.sql",
    ),
}


def merge_forecast_snapshot(
    source: str,
    incoming_records: list[BaseModel],
    previous_path: Path | None,
    output_path: Path,
    cutoff: datetime,
) -> ChangeMetrics:
    if source not in SQL_BY_SOURCE:
        raise ValueError(f"Unsupported incremental source: {source}")
    incoming_path = output_path.with_suffix(".incoming.parquet")
    write_models(incoming_path, incoming_records)
    if previous_path is None or not previous_path.exists():
        connection = duckdb.connect()
        connection.execute(
            render_sql(
                "incremental/deduplicate_forecast_snapshot.sql",
                incoming_path=incoming_path,
                output_path=output_path,
            )
        )
        connection.close()
        unique_count = pq.ParquetFile(output_path).metadata.num_rows
        incoming_path.unlink()
        return ChangeMetrics(
            inserted=unique_count,
            updated=0,
            unchanged=0,
            rejected=len(incoming_records) - unique_count,
        )

    metrics_sql, merge_sql = SQL_BY_SOURCE[source]
    connection = duckdb.connect()
    inserted, updated, unchanged, rejected = connection.execute(
        render_sql(metrics_sql, incoming_path=incoming_path, previous_path=previous_path)
    ).fetchone()
    connection.execute(
        render_sql(
            merge_sql,
            incoming_path=incoming_path,
            previous_path=previous_path,
            output_path=output_path,
        ),
        [cutoff],
    )
    connection.close()
    incoming_path.unlink()
    return ChangeMetrics(inserted=inserted, updated=updated, unchanged=unchanged, rejected=rejected)
