"""SQLModel tables.

Supply chain: Kitchen (supply) -> Volunteer (courier) -> Ngo (demand, via a Need).
"""
from enum import Enum
from typing import Optional

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

from .config import now_local


class ReportStatus(str, Enum):
    RECORDED = "RECORDED"
    TRANSCRIBED = "TRANSCRIBED"
    EXTRACTED = "EXTRACTED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    SAFETY_CHECK = "SAFETY_CHECK"  # two spoken questions: veg? covered?
    MATCHING = "MATCHING"
    OFFERED = "OFFERED"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"  # only reports matched to a Need; the NGO confirms by voice
    CANCELLED = "CANCELLED"  # the kitchen called it off (asked back by voice first)
    EXPIRED = "EXPIRED"  # its pickup deadline had passed by the safety check


class NeedStatus(str, Enum):
    CONFIRMING = "CONFIRMING"  # NGO is still confirming by voice
    OPEN = "OPEN"  # waiting for food
    MATCHED = "MATCHED"  # a report is reserved for it
    DELIVERED = "DELIVERED"
    EXPIRED = "EXPIRED"  # needed_by passed with no food


class Kitchen(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    lat: float
    lng: float
    phone: str
    language: str = "hi-IN"


class Volunteer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    lat: float
    lng: float
    phone: str
    language: str = "hi-IN"
    capacity: int = 50
    available: bool = True


class Ngo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    lat: float
    lng: float
    phone: str
    language: str = "hi-IN"


class Need(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ngo_id: int = Field(foreign_key="ngo.id")
    people_count: Optional[int] = None
    veg_only: bool = False
    needed_by: Optional[NaiveDatetime] = None
    status: NeedStatus = NeedStatus.CONFIRMING
    created_at: NaiveDatetime = Field(default_factory=now_local)
    transcript: str = ""


class Report(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kitchen_id: int = Field(foreign_key="kitchen.id")
    transcript: str = ""
    dish: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    cooked_at: Optional[NaiveDatetime] = None
    location: Optional[str] = None
    deadline: Optional[NaiveDatetime] = None
    status: ReportStatus = ReportStatus.RECORDED
    created_at: NaiveDatetime = Field(default_factory=now_local)
    veg: Optional[bool] = None  # asked at the safety check; unknown never feeds a veg-only need
    covered: Optional[bool] = None  # covered, clean container; never matched unless True
    need_id: Optional[int] = Field(default=None, foreign_key="need.id")


class Offer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="report.id")
    volunteer_id: int = Field(foreign_key="volunteer.id")
    rank: int
    status: str = "PENDING"
    sent_at: Optional[NaiveDatetime] = None
    responded_at: Optional[NaiveDatetime] = None
    reply_transcript: Optional[str] = None


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: Optional[int] = Field(default=None, foreign_key="report.id")
    type: str
    payload_json: str = "{}"
    latency_ms: Optional[int] = None
    ts: NaiveDatetime = Field(default_factory=now_local)
