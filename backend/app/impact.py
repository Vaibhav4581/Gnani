"""Impact numbers: counted rescues only, no CO2 or money estimates.

A rescue is a report that is DELIVERED, or PICKED_UP when it had no NGO need (that
is where its chain ends). Plates and boxes count as meals one for one; kg and litres
are converted with MEALS_PER_KG, an assumption the API and dashboard label as such.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from .config import settings
from .models import Event, Need, Offer, Report, ReportStatus

COUNTED_UNITS = {"plate", "box"}
ESTIMATED_UNITS = {"kg", "litre"}
DONE_EVENT = {ReportStatus.DELIVERED: "delivered", ReportStatus.PICKED_UP: "picked_up"}


@dataclass(frozen=True)
class Rescue:
    report: Report
    volunteer_id: Optional[int]
    need: Optional[Need]
    completed_at: datetime
    meals: float
    estimated: bool  # meals converted from kg/litres

    @property
    def people_served(self) -> int:
        """People fed at the NGO: never more than it asked for, or than the food fed."""
        if self.need is None or self.report.status != ReportStatus.DELIVERED:
            return 0
        return int(min(self.need.people_count or 0, self.meals))


def meals_for(quantity: Optional[float], unit: Optional[str]) -> tuple[float, bool]:
    """(meals, estimated). Units the app doesn't know count as nothing rather than a guess."""
    if not quantity:
        return 0.0, False
    if unit in COUNTED_UNITS:
        return float(quantity), False
    if unit in ESTIMATED_UNITS:
        return float(quantity) * settings.meals_per_kg, True
    return 0.0, False


def is_rescue(report: Report) -> bool:
    return report.status == ReportStatus.DELIVERED or (
        report.status == ReportStatus.PICKED_UP and report.need_id is None)


def rescues(s: Session) -> list[Rescue]:
    reports = s.exec(select(Report).where(or_(
        Report.status == ReportStatus.DELIVERED,
        and_(Report.status == ReportStatus.PICKED_UP, Report.need_id.is_(None))))).all()
    return [rescue_of(s, r) for r in reports]


def rescue_of(s: Session, report: Report) -> Rescue:
    status = ReportStatus(report.status)
    done = s.exec(select(Event.ts).where(Event.report_id == report.id,
                                         Event.type == DONE_EVENT.get(status, "picked_up"))
                  .order_by(Event.id.desc())).first()
    offer = s.exec(select(Offer).where(Offer.report_id == report.id,
                                       Offer.status == "ACCEPTED")).first()
    meals, estimated = meals_for(report.quantity, report.unit)
    return Rescue(report, offer.volunteer_id if offer else None,
                  s.get(Need, report.need_id) if report.need_id else None,
                  done or report.created_at, meals, estimated)


def summarize(items: Iterable[Rescue]) -> dict:
    items = list(items)
    counted = sum(r.meals for r in items if not r.estimated)
    estimated = sum(r.meals for r in items if r.estimated)
    return {
        "rescues": len(items),
        "meals": {"total": round(counted + estimated), "counted": round(counted),
                  "estimated": round(estimated)},
        "kitchens": len({r.report.kitchen_id for r in items}),
        "volunteers": len({r.volunteer_id for r in items if r.volunteer_id is not None}),
        "ngos": len({r.need.ngo_id for r in items if r.need and r.people_served}),
        "people_served": sum(r.people_served for r in items),
    }


def impact(s: Session, now: datetime) -> dict:
    """Today (by completion date, local time) and all time."""
    items = rescues(s)
    return {
        "today": summarize(r for r in items if r.completed_at.date() == now.date()),
        "all_time": summarize(items),
        "assumptions": {
            "meals_per_kg": settings.meals_per_kg,
            "note": f"Plates and boxes are counted as one meal each. Food reported in kg or "
                    f"litres is estimated at {settings.meals_per_kg:g} meals per kg or litre.",
        },
        "as_of": now.isoformat(),
    }
