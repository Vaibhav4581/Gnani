"""Synthetic demo data around Kochi: 4 kitchens (one per language), 8 volunteers,
3 NGOs/shelters, and (after a demo reset) one open need.

Names, phone numbers and exact points are made up. Seeding upserts by id, so the
demo data is restored on every start.
"""
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel

from .languages import get_language
from .models import Kitchen, Need, NeedStatus, Ngo, Volunteer

# Centre points of the four demo areas (lat, lng).
AREAS = {
    "Kakkanad": (10.0159, 76.3419),
    "Edappally": (10.0261, 76.3086),
    "Vyttila": (9.9682, 76.3182),
    "Thrippunithura": (9.9454, 76.3489),
}

KITCHENS = [
    Kitchen(id=1, name="Annapurna Mess, Kakkanad", lat=10.0159, lng=76.3419,
            phone="+91-90000-00001", language="hi-IN"),
    Kitchen(id=2, name="Malabar Kitchen, Edappally", lat=10.0261, lng=76.3086,
            phone="+91-90000-00002", language="ml-IN"),
    Kitchen(id=3, name="Udupi Grand, Vyttila", lat=9.9682, lng=76.3182,
            phone="+91-90000-00003", language="kn-IN"),
    Kitchen(id=4, name="Temple Road Cafe, Thrippunithura", lat=9.9454, lng=76.3489,
            phone="+91-90000-00004", language="en-IN"),
]

# Capacity is in plates (see matcher.PLATES_PER_UNIT). Deepa is off duty, so
# the availability filter has something to filter.
VOLUNTEERS = [
    Volunteer(id=1, name="Anjali Menon", lat=10.0230, lng=76.3110, phone="+91-90000-10001",
              language="ml-IN", capacity=60),
    Volunteer(id=2, name="Rahul Verma", lat=10.0120, lng=76.3460, phone="+91-90000-10002",
              language="hi-IN", capacity=40),
    Volunteer(id=3, name="Kavya Rao", lat=9.9700, lng=76.3210, phone="+91-90000-10003",
              language="kn-IN", capacity=80),
    Volunteer(id=4, name="Arjun Nair", lat=9.9480, lng=76.3450, phone="+91-90000-10004",
              language="ml-IN", capacity=30),
    Volunteer(id=5, name="Priya Sharma", lat=9.9650, lng=76.3150, phone="+91-90000-10005",
              language="hi-IN", capacity=100),
    Volunteer(id=6, name="Deepa Shetty", lat=10.0190, lng=76.3380, phone="+91-90000-10006",
              language="kn-IN", capacity=50, available=False),
    Volunteer(id=7, name="John Mathew", lat=10.0290, lng=76.3050, phone="+91-90000-10007",
              language="en-IN", capacity=120),
    Volunteer(id=8, name="Sneha Kurian", lat=9.9420, lng=76.3520, phone="+91-90000-10008",
              language="en-IN", capacity=70),
]


# Where food is needed. Fictional organisations, placed in the demo areas.
NGOS = [
    Ngo(id=1, name="Asha Night Shelter", lat=10.0205, lng=76.3040, phone="+91-90000-20001",
        language="hi-IN"),
    Ngo(id=2, name="Sneha Shelter Home", lat=9.9735, lng=76.3245, phone="+91-90000-20002",
        language="ml-IN"),
    Ngo(id=3, name="Karunya Children's Home", lat=10.0105, lng=76.3505,
        phone="+91-90000-20003", language="en-IN"),
]


# A reset starts the demo with this need open: Annapurna Mess's 50 plates feed at least
# NEED_MIN_SHARE of 80 people. For those 50 plates Rahul (40) and Arjun (30) are too
# small and Deepa is off duty, so with everyone on duty Anjali Menon is asked first and
# John Mathew second: say "nahi" as Anjali to show the fallback.
DEMO_NEED_NGO_ID = 3  # Karunya Children's Home, Kakkanad
DEMO_NEED_PEOPLE = 80
DEMO_NEED_HOURS = 3


def demo_need(now: datetime) -> Need:
    """Open, any food, needed about DEMO_NEED_HOURS from now (on the half hour), so it
    still fits whatever time the demo runs."""
    by = (now + timedelta(hours=DEMO_NEED_HOURS, minutes=29)).replace(second=0, microsecond=0)
    by = by.replace(minute=0 if by.minute < 30 else 30)
    when = get_language("en-IN").prompts.by_time(by)
    return Need(ngo_id=DEMO_NEED_NGO_ID, people_count=DEMO_NEED_PEOPLE, veg_only=False,
                needed_by=by, status=NeedStatus.OPEN, created_at=now,
                transcript=f"We need food for {DEMO_NEED_PEOPLE} people {when}")


def nearest_area(lat: float, lng: float) -> str:
    """Name of the demo area closest to a point (for speech and the UI)."""
    return min(AREAS, key=lambda a: (AREAS[a][0] - lat) ** 2 + (AREAS[a][1] - lng) ** 2)


def _upsert(session: Session, rows: list[SQLModel]) -> None:
    for row in rows:
        existing = session.get(type(row), row.id)
        if existing is None:
            session.add(type(row)(**row.model_dump()))
        else:
            for key, value in row.model_dump().items():
                setattr(existing, key, value)


def seed(session: Session) -> None:
    _upsert(session, KITCHENS)
    _upsert(session, VOLUNTEERS)
    _upsert(session, NGOS)
    session.commit()
