import random
import hashlib
from datetime import date, timedelta

from src.config import City


CONDITIONS = ["diabetes", "cardiovascular", "renal", "respiratory"]
LANGUAGES = ["Hindi", "English", "Tamil", "Kannada", "Marathi", "Gujarati"]
CHANNELS = ["app", "sms", "call"]
GENERATOR_VERSION = "v1"


def member_reference_version(cities: list[City], count: int = 5000) -> str:
    city_ids = ",".join(sorted(city.city_id for city in cities))
    digest = hashlib.sha256(f"{GENERATOR_VERSION}|{count}|{city_ids}".encode()).hexdigest()[:12]
    return f"{GENERATOR_VERSION}-{digest}"


def generate_members(cities: list[City], count: int = 5000, seed: int = 20260612) -> tuple[list[dict], list[dict]]:
    randomizer = random.Random(seed)
    members: list[dict] = []
    member_conditions: list[dict] = []
    for index in range(1, count + 1):
        member_id = f"M-{index:06d}"
        city = randomizer.choice(cities)
        condition_count = randomizer.choices([1, 2, 3], weights=[70, 25, 5])[0]
        conditions = randomizer.sample(CONDITIONS, condition_count)
        members.append(
            {
                "member_id": member_id,
                "city_id": city.city_id,
                "age_band": randomizer.choices(["18-39", "40-59", "60+"], weights=[30, 45, 25])[0],
                "preferred_language": randomizer.choice(LANGUAGES),
                "preferred_channel": randomizer.choice(CHANNELS),
                "outreach_consent": randomizer.random() < 0.9,
                "last_contact_date": date.today() - timedelta(days=randomizer.randint(0, 60)),
                "generator_version": GENERATOR_VERSION,
            }
        )
        member_conditions.extend({"member_id": member_id, "condition": condition} for condition in conditions)
    return members, member_conditions
