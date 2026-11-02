"""Match a confirmed report to an NGO need, then rank volunteers to carry it.

Need: the food must reach the NGO before it is needed and before the food's own
deadline (cooked time + SAFE_WINDOW_HOURS), suit a veg-only need, and feed at
least NEED_MIN_SHARE of the people. Nearest NGO to the kitchen wins.

Volunteer: available, can carry the quantity, reaches the kitchen before the
pickup deadline and, when there is a need, the NGO in time too. Soonest first.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .config import settings
from .models import Kitchen, Need, NeedStatus, Ngo, Report, Volunteer

EARTH_RADIUS_KM = 6371.0

# Volunteer capacity is in plates; other units are converted for the capacity check.
PLATES_PER_UNIT = {"plate": 1.0, "box": 1.0, "kg": 4.0, "litre": 4.0}


@dataclass(frozen=True)
class Candidate:
    volunteer: Volunteer
    distance_km: float  # volunteer -> kitchen
    eta_minutes: float  # to the kitchen, loading included
    arrival: datetime  # at the kitchen
    delivery_km: float = 0.0  # kitchen -> NGO, when the food goes to a need
    delivered_at: Optional[datetime] = None

    @property
    def total_km(self) -> float:
        return self.distance_km + self.delivery_km


@dataclass(frozen=True)
class NeedMatch:
    need: Need
    ngo: Ngo
    distance_km: float  # kitchen -> NGO
    arrival: datetime  # earliest delivery
    people_fed: float


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def plate_equivalent(quantity: float, unit: Optional[str]) -> float:
    return quantity * PLATES_PER_UNIT.get(unit or "plate", 1.0)


def travel_minutes(distance_km: float, speed_kmh: float, buffer_minutes: float) -> float:
    return distance_km / speed_kmh * 60 + buffer_minutes


def kitchen_to_ngo_km(kitchen: Kitchen, ngo: Ngo) -> float:
    return haversine_km(kitchen.lat, kitchen.lng, ngo.lat, ngo.lng)


def _too_late(when: datetime, *limits: Optional[datetime]) -> bool:
    return any(limit is not None and when > limit for limit in limits)


def rank_volunteers(report: Report, kitchen: Kitchen, volunteers: Iterable[Volunteer],
                    now: datetime, speed_kmh: Optional[float] = None,
                    buffer_minutes: Optional[float] = None, ngo: Optional[Ngo] = None,
                    needed_by: Optional[datetime] = None) -> list[Candidate]:
    """Qualifying volunteers, soonest arrival first (ties: more spare capacity).
    With an `ngo`, the route is volunteer -> kitchen -> NGO and must end by `needed_by`."""
    speed = speed_kmh or settings.volunteer_speed_kmh
    buffer = settings.pickup_buffer_minutes if buffer_minutes is None else buffer_minutes
    needed = plate_equivalent(report.quantity or 0, report.unit)
    drop_km = kitchen_to_ngo_km(kitchen, ngo) if ngo else 0.0

    candidates = []
    for v in volunteers:
        if not v.available or v.capacity < needed:
            continue
        km = haversine_km(kitchen.lat, kitchen.lng, v.lat, v.lng)
        eta = travel_minutes(km, speed, buffer)
        arrival = now + timedelta(minutes=eta)
        if _too_late(arrival, report.deadline):
            continue
        delivered = None
        if ngo:
            delivered = arrival + timedelta(minutes=travel_minutes(drop_km, speed, 0))
            if _too_late(delivered, needed_by, report.deadline):
                continue
        candidates.append(Candidate(v, km, eta, arrival, drop_km, delivered))
    return sorted(candidates, key=lambda c: (c.eta_minutes, -(c.volunteer.capacity - needed),
                                             c.volunteer.id))


def veg_compatible(report_veg: Optional[bool], veg_only: bool) -> bool:
    """Unknown food (veg is None) never goes to a veg-only need."""
    return not veg_only or report_veg is True


def rank_needs(report: Report, kitchen: Kitchen, needs: Iterable[tuple[Need, Ngo]],
               earliest_pickup: datetime, speed_kmh: Optional[float] = None,
               min_share: Optional[float] = None) -> list[NeedMatch]:
    """Open needs this report can serve, nearest NGO first (ties: needed soonest, then
    the least food left over). `earliest_pickup` is when the fastest volunteer can load."""
    speed = speed_kmh or settings.volunteer_speed_kmh
    share = settings.need_min_share if min_share is None else min_share
    fed = plate_equivalent(report.quantity or 0, report.unit)

    matches = []
    for need, ngo in needs:
        if need.status != NeedStatus.OPEN or not need.people_count or need.needed_by is None:
            continue
        if not veg_compatible(report.veg, need.veg_only):
            continue
        if fed < share * need.people_count:
            continue
        km = kitchen_to_ngo_km(kitchen, ngo)
        arrival = earliest_pickup + timedelta(minutes=travel_minutes(km, speed, 0))
        if _too_late(arrival, need.needed_by, report.deadline):
            continue
        matches.append(NeedMatch(need, ngo, km, arrival, fed))
    return sorted(matches, key=lambda m: (round(m.distance_km, 2), m.need.needed_by,
                                          abs(fed - m.need.people_count), m.need.id))
