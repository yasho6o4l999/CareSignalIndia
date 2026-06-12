from src.config import load_cities
from src.synthetic import generate_members


def test_synthetic_members_are_reproducible() -> None:
    first = generate_members(load_cities(), count=10, seed=42)
    second = generate_members(load_cities(), count=10, seed=42)
    assert first == second

