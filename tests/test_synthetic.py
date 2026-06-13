from datetime import date

from src.config import load_cities, load_runtime_settings
from src.synthetic import generate_members, member_reference_version


def test_synthetic_members_are_reproducible() -> None:
    first = generate_members(load_cities(), count=10, seed=42)
    second = generate_members(load_cities(), count=10, seed=42)
    assert first == second


def test_synthetic_members_use_configured_anchor_date() -> None:
    members, _ = generate_members(
        load_cities(),
        count=10,
        seed=42,
        anchor_date=date(2020, 1, 1),
    )
    assert max(member["last_contact_date"] for member in members) <= date(2020, 1, 1)


def test_member_version_includes_anchor_date() -> None:
    policy = load_runtime_settings().synthetic_members
    changed = policy.model_copy(update={"anchor_date": date(2020, 1, 1)})
    assert member_reference_version(load_cities(), policy) != member_reference_version(
        load_cities(), changed
    )
