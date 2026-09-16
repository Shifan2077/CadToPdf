from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.db import DrawingRecord, ProjectRecord, engine, get_drawings_from_db, get_projects_from_db

STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage"


@dataclass
class UploadedDrawing:
    id: str
    project_id: str
    filename: str
    file_size: int
    entities: list[dict[str, object]]
    metadata: dict[str, object]
    status: str = "UPLOADED"
    error: str | None = None
    uploaded_at: str = ""


@dataclass
class Project:
    id: str
    name: str
    created_at: str
    updated_at: str
    drawing_ids: list[str]


drawings: dict[str, UploadedDrawing] = {}
projects: dict[str, Project] = {}


def _project_to_model(record: ProjectRecord) -> Project:
    return Project(
        id=record.id,
        name=record.name,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        drawing_ids=list(record.drawing_ids or []),
    )


def _drawing_to_model(record: DrawingRecord) -> UploadedDrawing:
    return UploadedDrawing(
        id=record.id,
        project_id=record.project_id,
        filename=record.filename,
        file_size=record.file_size,
        entities=list(record.entities or []),
        metadata=dict(record.drawing_metadata or {}),
        status=record.status,
        error=record.error,
        uploaded_at=record.uploaded_at.isoformat() if isinstance(record.uploaded_at, datetime) else str(record.uploaded_at),
    )


def _hydrate_memory() -> None:
    if projects and drawings:
        return
    for project_record in get_projects_from_db():
        projects[project_record.id] = _project_to_model(project_record)
    for drawing_record in get_drawings_from_db():
        drawings[drawing_record.id] = _drawing_to_model(drawing_record)


_hydrate_memory()


def create_project(name: str) -> Project:
    project_id = f"project_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    project = Project(project_id, name.strip(), now.isoformat(), now.isoformat(), [])

    with Session(engine) as session:
        session.add(ProjectRecord(id=project.id, name=project.name, created_at=now, updated_at=now, drawing_ids=[]))
        session.commit()

    projects[project_id] = project
    (STORAGE_ROOT / "projects" / project_id / "files").mkdir(parents=True, exist_ok=True)
    (STORAGE_ROOT / "projects" / project_id / "raw").mkdir(parents=True, exist_ok=True)
    return project


def _sync_project_drawing_ids(project: Project) -> None:
    with Session(engine) as session:
        record = session.get(ProjectRecord, project.id)
        if record is not None:
            record.drawing_ids = list(project.drawing_ids)
            record.updated_at = datetime.now(timezone.utc)
            session.add(record)
            session.commit()


def store_drawing(project: Project, filename: str, content: bytes, entities: list[dict[str, Any]], metadata: dict[str, object]) -> UploadedDrawing:
    drawing_id = f"drawing_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    drawing = UploadedDrawing(
        id=drawing_id,
        project_id=project.id,
        filename=filename,
        file_size=len(content),
        entities=entities,
        metadata=metadata,
        status="COMPLETED",
        uploaded_at=now.isoformat(),
    )

    with Session(engine) as session:
        session.add(DrawingRecord(
            id=drawing.id,
            project_id=project.id,
            filename=filename,
            file_size=len(content),
            entities=entities,
            drawing_metadata=dict(metadata),
            status="COMPLETED",
            uploaded_at=now,
        ))
        session.commit()

    drawings[drawing_id] = drawing
    project.drawing_ids.append(drawing_id)
    project.updated_at = now.isoformat()
    _sync_project_drawing_ids(project)

    project_root = STORAGE_ROOT / "projects" / project.id
    (project_root / "files" / filename).write_bytes(content)
    (project_root / "raw" / f"{drawing_id}.json").write_text(json.dumps({
        "drawing_id": drawing_id, "project_id": project.id, "filename": filename,
        "metadata": metadata, "entities": entities,
    }, default=str, indent=2), encoding="utf-8")
    return drawing


def store_failed_drawing(project: Project, filename: str, content: bytes, error: str) -> UploadedDrawing:
    drawing_id = f"drawing_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    drawing = UploadedDrawing(
        id=drawing_id,
        project_id=project.id,
        filename=filename,
        file_size=len(content),
        entities=[],
        metadata={},
        status="FAILED",
        error=error,
        uploaded_at=now.isoformat(),
    )

    with Session(engine) as session:
        session.add(DrawingRecord(
            id=drawing.id,
            project_id=project.id,
            filename=filename,
            file_size=len(content),
            entities=[],
            drawing_metadata={},
            status="FAILED",
            error=error,
            uploaded_at=now,
        ))
        session.commit()

    drawings[drawing.id] = drawing
    project.drawing_ids.append(drawing.id)
    project.updated_at = now.isoformat()
    _sync_project_drawing_ids(project)

    project_root = STORAGE_ROOT / "projects" / project.id
    (project_root / "files" / filename).write_bytes(content)
    return drawing


__all__ = ["Project", "UploadedDrawing", "drawings", "projects", "create_project", "store_drawing", "store_failed_drawing"]
