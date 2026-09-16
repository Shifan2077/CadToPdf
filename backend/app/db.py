from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://arecon:change_me@localhost:5432/arecon")
engine = create_engine(DATABASE_URL, echo=False)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectRecord(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=lambda: f"project_{__import__('uuid').uuid4().hex[:12]}", primary_key=True, index=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    drawing_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    @classmethod
    def get_by_id(cls, project_id: str) -> "ProjectRecord | None":
        with Session(engine) as session:
            return session.get(cls, project_id)


class DrawingRecord(SQLModel, table=True):
    __tablename__ = "drawings"

    id: str = Field(default_factory=lambda: f"drawing_{__import__('uuid').uuid4().hex[:12]}", primary_key=True, index=True)
    project_id: str = Field(index=True)
    filename: str = Field(index=True)
    file_size: int
    entities: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    drawing_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "UPLOADED"
    error: str | None = None
    uploaded_at: datetime = Field(default_factory=utc_now)

    @classmethod
    def get_by_id(cls, drawing_id: str) -> "DrawingRecord | None":
        with Session(engine) as session:
            return session.get(cls, drawing_id)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_projects_from_db() -> list[ProjectRecord]:
    with Session(engine) as session:
        return list(session.exec(select(ProjectRecord)).all())


def get_drawings_from_db() -> list[DrawingRecord]:
    with Session(engine) as session:
        return list(session.exec(select(DrawingRecord)).all())


init_db()
