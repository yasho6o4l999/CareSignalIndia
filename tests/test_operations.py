import pytest

from src.operations import pipeline_lock, tracked_stage


def test_pipeline_lock_rejects_overlapping_execution(tmp_path) -> None:
    lock_path = tmp_path / "etl.lock"
    with pipeline_lock(lock_path):
        with pytest.raises(RuntimeError, match="already holds"):
            with pipeline_lock(lock_path):
                pass


def test_tracked_stage_records_failure() -> None:
    calls = []

    class Metadata:
        def start_stage(self, *args):
            calls.append(("start", args))

        def complete_stage(self, *args):
            calls.append(("complete", args))

    with pytest.raises(ValueError, match="bad stage"):
        with tracked_stage(Metadata(), "run-1", "stage-1", 12):
            raise ValueError("bad stage")

    assert calls[0] == ("start", ("run-1", "stage-1", 12))
    assert calls[1][1][2] == "failed"
