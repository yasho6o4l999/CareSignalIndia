from datetime import datetime


def validate_time_series(
    city_id: str,
    records: list,
    minimum_records: int,
    expected_interval_hours: int,
    allow_gaps: bool = False,
) -> None:
    if len(records) < minimum_records:
        raise ValueError(
            f"{city_id} response has {len(records)} records; expected at least {minimum_records}"
        )
    timestamps = [
        getattr(record, "observed_at", None) or getattr(record, "observed_date", None)
        for record in records
    ]
    if any(timestamp is None for timestamp in timestamps):
        raise ValueError(f"{city_id} response contains missing timestamps")
    if timestamps != sorted(timestamps):
        raise ValueError(f"{city_id} response timestamps are not ordered")
    if len(timestamps) != len(set(timestamps)):
        raise ValueError(f"{city_id} response contains duplicate timestamps")
    intervals = {
        round((right - left).total_seconds() / 3600)
        for left, right in zip(timestamps, timestamps[1:])
    }
    invalid_intervals = (
        {interval for interval in intervals if interval <= 0 or interval % expected_interval_hours != 0}
        if allow_gaps
        else intervals - {expected_interval_hours}
    )
    if invalid_intervals:
        raise ValueError(
            f"{city_id} response contains unexpected intervals: {sorted(invalid_intervals)}"
        )


def validate_parallel_arrays(payload: dict, keys: list[str]) -> None:
    missing = set(keys) - set(payload)
    if missing:
        raise ValueError(f"response is missing required arrays: {sorted(missing)}")
    lengths = {key: len(payload[key]) for key in keys}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"response arrays have different lengths: {lengths}")
