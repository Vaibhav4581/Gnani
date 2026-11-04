"""Database engine, session dependency and event logging."""
import json
from typing import Any, Iterator, Optional

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from . import changes
from .config import settings
from .models import Event
from .seed import seed


def make_engine(url: str) -> Engine:
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=args)


engine = make_engine(settings.database_url)


# Columns added after the first release: (table, column, SQL type). create_all() makes
# new tables but never alters old ones, so an existing bacha.db gets them here.
ADDED_COLUMNS = [("report", "veg", "BOOLEAN"), ("report", "need_id", "INTEGER"),
                 ("report", "covered", "BOOLEAN"), ("report", "drop_ngo_id", "INTEGER"),
                 ("ngo", "is_default", "BOOLEAN NOT NULL DEFAULT 0")]


def add_missing_columns(eng: Engine) -> list[str]:
    """ALTER TABLE ... ADD COLUMN for any ADDED_COLUMNS the database lacks."""
    added = []
    with eng.begin() as conn:
        for table, column, sql_type in ADDED_COLUMNS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if existing and column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
                added.append(f"{table}.{column}")
    return added


def init_db(eng: Optional[Engine] = None) -> None:
    eng = eng or engine
    SQLModel.metadata.create_all(eng)
    add_missing_columns(eng)
    with Session(eng) as session:
        seed(session)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def log_event(session: Session, report_id: Optional[int], type_: str,
              latency_ms: Optional[int] = None, **payload: Any) -> None:
    session.add(Event(report_id=report_id, type=type_, latency_ms=latency_ms,
                      payload_json=json.dumps(payload, default=str, ensure_ascii=False)))
    changes.mark(session, report_id)  # the dashboard picks it up after commit
