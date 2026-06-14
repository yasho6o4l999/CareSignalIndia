from src.config import load_cities, load_runtime_settings
from src.synthetic import generate_members, member_reference_version


def test_synthetic_members_are_reproducible() -> None:
    first = generate_members(load_cities(), count=10, seed=42)
    second = generate_members(load_cities(), count=10, seed=42)
    assert first == second


def test_member_version_changes_with_generation_policy() -> None:
    policy = load_runtime_settings().synthetic_members
    changed = policy.model_copy(update={"seed": policy.seed + 1})
    assert member_reference_version(load_cities(), policy) != member_reference_version(
        load_cities(), changed
    )
