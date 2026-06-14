import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


HISTORICAL_FACTS = (
    "environmental_conditions_daily.parquet",
    "environmental_metrics_daily.parquet",
    "member_risk_exposure_daily.parquet",
    "care_workload_daily.parquet",
)


def publish_history_snapshot(root: Path, run_id: str, published_run: Path) -> Path:
    history_root = root / "data/analytical_history"
    final = history_root / f"run_id={run_id}"
    staging = history_root / f".staging-{run_id}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for name in HISTORICAL_FACTS:
            source = published_run / name
            destination = staging / name
            try:
                os.link(source, destination)
            except OSError:
                shutil.copy2(source, destination)
        os.replace(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def apply_history_retention(root: Path, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    history_root = root / "data/analytical_history"
    for path in history_root.glob("run_id=*"):
        try:
            run_time = datetime.strptime(path.name.removeprefix("run_id="), "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        if run_time < cutoff:
            shutil.rmtree(path)
