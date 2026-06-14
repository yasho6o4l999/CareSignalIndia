import json

import pytest

from src.reference import (
    apply_member_snapshot_retention,
    member_snapshot_id,
    publish_member_snapshot,
    verify_member_snapshot,
)


MEMBERS = [
    {
        "member_id": "M-1",
        "city_id": "delhi",
        "age_band": "40-59",
        "preferred_language": "Hindi",
        "preferred_channel": "app",
        "outreach_consent": True,
        "last_contact_date": "2026-06-01",
        "generator_version": "v1",
    },
    {
        "member_id": "M-2",
        "city_id": "mumbai",
        "age_band": "60+",
        "preferred_language": "Marathi",
        "preferred_channel": "sms",
        "outreach_consent": True,
        "last_contact_date": "2026-05-01",
        "generator_version": "v1",
    },
]
CONDITIONS = [
    {"member_id": "M-1", "condition": "diabetes"},
    {"member_id": "M-2", "condition": "cardiovascular"},
]


def test_member_snapshot_is_partitioned_manifested_and_reusable(tmp_path) -> None:
    root, manifest, checksum = publish_member_snapshot(
        tmp_path, "snapshot-1", "config-1", MEMBERS, CONDITIONS
    )
    reused_root, reused_manifest, reused_checksum = publish_member_snapshot(
        tmp_path, "snapshot-1", "config-1", MEMBERS, CONDITIONS
    )

    assert (root / "members/city_id=delhi/data.parquet").exists()
    assert (root / "member_conditions/city_id=mumbai/data.parquet").exists()
    assert manifest["member_count"] == 2
    assert reused_root == root
    assert reused_manifest == manifest
    assert reused_checksum == checksum
    assert not list(tmp_path.glob(".staging-*"))


def test_member_snapshot_rejects_checksum_corruption(tmp_path) -> None:
    root, _, _ = publish_member_snapshot(tmp_path, "snapshot-1", "config-1", MEMBERS, CONDITIONS)
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["files"][0]["sha256"] = "invalid"
    (root / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_member_snapshot(root)


def test_member_snapshot_rejects_unknown_condition_member(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown members"):
        publish_member_snapshot(
            tmp_path,
            "snapshot-1",
            "config-1",
            MEMBERS,
            [{"member_id": "M-unknown", "condition": "diabetes"}],
        )


def test_snapshot_id_changes_with_member_content() -> None:
    changed = [{**MEMBERS[0], "city_id": "mumbai"}, MEMBERS[1]]
    assert member_snapshot_id("v1", MEMBERS, CONDITIONS) != member_snapshot_id(
        "v1", changed, CONDITIONS
    )


def test_snapshot_reuses_unchanged_city_partitions(tmp_path) -> None:
    first_root, first_manifest, _ = publish_member_snapshot(
        tmp_path, "snapshot-1", "config-1", MEMBERS, CONDITIONS
    )
    changed_members = [{**MEMBERS[0], "preferred_channel": "sms"}, MEMBERS[1]]
    second_root, second_manifest, _ = publish_member_snapshot(
        tmp_path,
        "snapshot-2",
        "config-2",
        changed_members,
        CONDITIONS,
        previous_root=first_root,
        changed_cities={"delhi"},
    )

    first_mumbai = next(
        item for item in first_manifest["files"] if item["path"] == "members/city_id=mumbai/data.parquet"
    )
    second_mumbai = next(
        item for item in second_manifest["files"] if item["path"] == "members/city_id=mumbai/data.parquet"
    )
    assert first_mumbai["sha256"] == second_mumbai["sha256"]
    assert (second_root / "members/city_id=delhi/data.parquet").exists()


def test_snapshot_retention_protects_referenced_and_latest_versions(tmp_path) -> None:
    for name in ("old", "protected", "latest"):
        path = tmp_path / f"snapshot_id={name}"
        path.mkdir()
    removed = apply_member_snapshot_retention(tmp_path, {"protected"}, keep_latest=1)

    assert removed == ["old"]
    assert (tmp_path / "snapshot_id=protected").exists()
    assert (tmp_path / "snapshot_id=latest").exists()
