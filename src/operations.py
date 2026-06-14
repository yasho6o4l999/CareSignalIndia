import fcntl
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from src.metadata import MetadataStore


@contextmanager
def pipeline_lock(path: Path):
    """Prevent overlapping local ETL runs from publishing competing snapshots."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise RuntimeError("Another ETL execution already holds the pipeline lock") from error
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextmanager
def tracked_stage(
    metadata: MetadataStore,
    run_id: str,
    stage_name: str,
    input_records: int = 0,
    output_records: Callable[[], int] | None = None,
):
    """Persist stage timing and row-flow evidence even when the stage fails."""
    started = time.perf_counter()
    metadata.start_stage(run_id, stage_name, input_records)
    try:
        yield
    except Exception as error:
        metadata.complete_stage(
            run_id, stage_name, "failed", round((time.perf_counter() - started) * 1000), 0, str(error)
        )
        raise
    else:
        result_count = output_records() if output_records else 0
        metadata.complete_stage(
            run_id, stage_name, "success", round((time.perf_counter() - started) * 1000), result_count
        )
