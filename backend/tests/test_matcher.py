"""Volunteer ranking: distance, availability, capacity and the pickup deadline."""
from datetime import timedelta

import pytest

from app.matcher import haversine_km, plate_equivalent, rank_volunteers, travel_minutes
from app.models import Kitchen, Report, Volunteer
from app.seed import KITCHENS, VOLUNTEERS, nearest_area

KAKKANAD = KITCHENS[0]


def ranked_ids(now, quantity=50, unit="plate", deadline_in=timedelta(hours=2),
               kitchen=KAKKANAD, volunteers=VOLUNTEERS):
    report = Report(kitchen_id=kitchen.id, quantity=quantity, unit=unit,
                    deadline=now + deadline_in)
    return [c.volunteer.id for c in rank_volunteers(report, kitchen, volunteers, now)]


def test_haversine_one_degree_of_longitude_at_equator():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.01)


def test_haversine_is_symmetric_and_zero_for_same_point():
    a, b = (10.0159, 76.3419), (9.9454, 76.3489)
    assert haversine_km(*a, *b) == pytest.approx(haversine_km(*b, *a))
    assert haversine_km(*a, *a) == 0


def test_travel_time_adds_pickup_buffer():
    assert travel_minutes(5, speed_kmh=15, buffer_minutes=10) == pytest.approx(30)


def test_units_convert_to_plates_for_capacity():
    assert plate_equivalent(20, "kg") == 80
    assert plate_equivalent(5, "litre") == 20
    assert plate_equivalent(3, "box") == 3


def test_nearest_first_and_filters_capacity_and_availability(now):
    # Rahul (40) and Arjun (30) can't carry 50 plates; Deepa is unavailable.
    assert ranked_ids(now) == [1, 7, 3, 5, 8]


def test_capacity_filter(now):
    assert ranked_ids(now, quantity=100) == [7, 5]


def test_kg_uses_plate_equivalent(now):
    assert ranked_ids(now, quantity=20, unit="kg") == [7, 3, 5]  # 80 plates


def test_must_arrive_before_deadline(now):
    # 15 km/h + 10 min buffer: only Anjali (24 min) and John (27 min) make 30 minutes.
    assert ranked_ids(now, deadline_in=timedelta(minutes=30)) == [1, 7]


def test_passed_deadline_matches_nobody(now):
    assert ranked_ids(now, deadline_in=timedelta(minutes=-5)) == []


def test_unavailable_volunteer_never_ranked(now):
    assert 6 not in ranked_ids(now, quantity=1)


def test_tie_goes_to_more_spare_capacity(now):
    same_place = [Volunteer(id=91, name="A", lat=10.0, lng=76.3, phone="x", capacity=60),
                  Volunteer(id=92, name="B", lat=10.0, lng=76.3, phone="x", capacity=90)]
    assert ranked_ids(now, volunteers=same_place) == [92, 91]


def test_rank_is_per_kitchen(now):
    tripunithura = KITCHENS[3]
    assert ranked_ids(now, kitchen=tripunithura)[0] == 8  # Sneha lives there


def test_nearest_area():
    assert nearest_area(10.0230, 76.3110) == "Edappally"
    assert isinstance(KAKKANAD, Kitchen)
