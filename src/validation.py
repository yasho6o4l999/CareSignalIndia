from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class ValidationIssue:
    natural_key: str | None
    field_name: str | None
    error_type: str
    invalid_value: Any
    error_message: str
    record_payload: dict
    severity: Literal["fatal", "warning"] = "fatal"


@dataclass(frozen=True)
class ValidatedBatch:
    records: list[BaseModel]
    issues: list[ValidationIssue]
    received_records: int

    @property
    def invalid_records(self) -> int:
        return len({
            issue.natural_key or json.dumps(issue.record_payload, sort_keys=True, default=str)
            for issue in self.issues
            if issue.severity == "fatal"
        })

    @property
    def valid_ratio(self) -> float:
        return len(self.records) / self.received_records if self.received_records else 0


def source_utc_timestamp(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validation_issues(
    error: ValidationError,
    payload: dict,
    natural_key: str | None,
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            natural_key=natural_key,
            field_name=".".join(str(part) for part in detail["loc"]) or None,
            error_type=detail["type"],
            invalid_value=detail.get("input"),
            error_message=detail["msg"],
            record_payload=payload,
        )
        for detail in error.errors()
    ]


def validate_record(model: type[BaseModel], payload: dict, natural_key: str | None) -> tuple[BaseModel | None, list[ValidationIssue]]:
    try:
        return model.model_validate(payload), []
    except ValidationError as error:
        return None, validation_issues(error, payload, natural_key)


def cross_field_warnings(source: str, record: BaseModel, payload: dict, natural_key: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if source == "open_meteo_air_quality" and record.pm2_5 > record.pm10:
        issues.append(
            ValidationIssue(
                natural_key=natural_key,
                field_name="pm2_5",
                error_type="cross_field_pm25_above_pm10",
                invalid_value=record.pm2_5,
                error_message="PM2.5 exceeds PM10; retained as a warning for source review.",
                record_payload=payload,
                severity="warning",
            )
        )
    return issues
