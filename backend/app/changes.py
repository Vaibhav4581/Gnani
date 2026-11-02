"""Which reports (and whether any NGO needs) changed since the dashboard last looked.

log_event() marks the report on its session; only a successful commit moves the
mark into the shared set, so the dashboard never reads a change before it is
saved. Sessions run in worker threads and on the event loop, hence the lock.
"""
import threading
from typing import Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

_lock = threading.Lock()
_changed: set[int] = set()
_needs_changed = False
_KEY = "changed_reports"
_NEEDS_KEY = "changed_needs"


def mark(session: Session, report_id: Optional[int]) -> None:
    if report_id is not None:
        session.info.setdefault(_KEY, set()).add(report_id)


def mark_needs(session: Session) -> None:
    session.info[_NEEDS_KEY] = True


def drain_needs() -> bool:
    """True if any need was committed since the last call."""
    global _needs_changed
    with _lock:
        changed, _needs_changed = _needs_changed, False
    return changed


def drain() -> set[int]:
    """Report ids committed since the last drain."""
    with _lock:
        ids = set(_changed)
        _changed.clear()
    return ids


@event.listens_for(Session, "after_commit")
def _committed(session: Session) -> None:
    global _needs_changed
    ids = session.info.pop(_KEY, None)
    needs = session.info.pop(_NEEDS_KEY, False)
    if ids or needs:
        with _lock:
            _changed.update(ids or ())
            _needs_changed = _needs_changed or needs


@event.listens_for(Session, "after_rollback")
def _rolled_back(session: Session) -> None:
    session.info.pop(_KEY, None)
    session.info.pop(_NEEDS_KEY, None)
