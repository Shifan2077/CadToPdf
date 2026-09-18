from __future__ import annotations

from io import BytesIO
from typing import Any

from ezdxf import recover
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.cad.dxf_parser import parse_dxf
from app.cad.region_detector import detect_region_candidates
from app.cad.storage import Project, UploadedDrawing, create_project, drawings, projects, store_drawing, store_failed_drawing

router = APIRouter()


class ProjectRequest(BaseModel):
    name: str


def _metadata(content: bytes, entities: list[dict[str, Any]]) -> dict[str, object]:
    document, _ = recover.read(BytesIO(content))
    layer_names = {str(entity.get("layer", "0")) for entity in entities}
    entity_counts: dict[str, int] = {}
    for entity in entities:
        entity_type = str(entity["entity_type"])
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
    units_code = int(document.header.get("$INSUNITS", 0))
    units = {0: "Unitless", 1: "Inches", 2: "Feet", 3: "Miles", 4: "Millimeters", 5: "Centimeters", 6: "Meters", 7: "Kilometers"}.get(units_code, f"Code {units_code}")
    layout_audit = {}
    for layout in document.layouts:
        counts: dict[str, int] = {}
        for entity in layout:
            counts[entity.dxftype()] = counts.get(entity.dxftype(), 0) + 1
        layout_audit[layout.name] = counts
    block_audit = {}
    insert_virtual_audit = []
    for block in document.blocks:
        if block.name.startswith("*"):
            continue
        counts: dict[str, int] = {}
        for entity in block:
            counts[entity.dxftype()] = counts.get(entity.dxftype(), 0) + 1
        block_audit[block.name] = counts
    for entity in document.modelspace().query("INSERT"):
        try:
            virtual_types: dict[str, int] = {}
            for virtual_entity in entity.virtual_entities():
                virtual_types[virtual_entity.dxftype()] = virtual_types.get(virtual_entity.dxftype(), 0) + 1
            insert_virtual_audit.append({"handle": entity.dxf.get("handle"), "block_name": entity.dxf.get("name"), "entity_counts": virtual_types})
        except Exception:
            insert_virtual_audit.append({"handle": entity.dxf.get("handle"), "block_name": entity.dxf.get("name"), "entity_counts": {}, "error": "virtual_entities_unavailable"})
    annotation_count = sum(entity_counts.get(kind, 0) for kind in ("TEXT", "MTEXT", "DIMENSION"))
    annotation_count += sum(counts.get(kind, 0) for counts in layout_audit.values() for kind in ("TEXT", "MTEXT", "DIMENSION"))
    annotation_count += sum(counts.get(kind, 0) for counts in block_audit.values() for kind in ("TEXT", "MTEXT", "DIMENSION"))
    annotation_count += sum(item["entity_counts"].get(kind, 0) for item in insert_virtual_audit for kind in ("TEXT", "MTEXT", "DIMENSION"))
    return {
        "schema_version": "2.0",
        "dxf_version": document.dxfversion,
        "units": units,
        "units_code": units_code,
        "model_space_entities": len(document.modelspace()),
        "layouts": [layout.name for layout in document.layouts],
        "layer_count": len(layer_names),
        "block_count": sum(1 for block in document.blocks if not block.name.startswith("*")),
        "entity_counts": entity_counts,
        "region_candidates": detect_region_candidates(entities),
        "paperspace_extracted": True,
        "extraction_audit": {
            "modelspace_entity_counts": entity_counts,
            "layout_entity_counts": layout_audit,
            "block_definition_entity_counts": block_audit,
            "insert_virtual_entity_counts": insert_virtual_audit,
            "annotation_entities_present": annotation_count > 0,
            "annotation_representation": "SOURCE_CAD" if annotation_count else "VECTOR_VISUAL / geometry-only annotation",
        },
    }


def _drawing_response(drawing: UploadedDrawing) -> dict[str, object]:
    return {"id": drawing.id, "filename": drawing.filename, "status": drawing.status, "error": drawing.error, "file_size": drawing.file_size, "uploaded_at": drawing.uploaded_at}


@router.post("/projects")
async def create_project_route(request: ProjectRequest) -> dict[str, object]:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")
    project = create_project(name)
    return {"id": project.id, "name": project.name, "created_at": project.created_at, "updated_at": project.updated_at, "drawings": []}


@router.get("/projects")
async def list_projects() -> list[dict[str, object]]:
    return [{"id": project.id, "name": project.name, "created_at": project.created_at, "updated_at": project.updated_at, "drawing_count": len(project.drawing_ids)} for project in projects.values()]


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, object]:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"id": project.id, "name": project.name, "created_at": project.created_at, "updated_at": project.updated_at, "drawings": [_drawing_response(drawings[drawing_id]) for drawing_id in project.drawing_ids]}


@router.post("/projects/{project_id}/drawings")
async def upload_project_drawings(project_id: str, files: list[UploadFile] = File(...)) -> dict[str, object]:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    existing = {drawings[drawing_id].filename.lower() for drawing_id in project.drawing_ids}
    results: list[dict[str, object]] = []
    for file in files:
        filename = file.filename or "drawing.dxf"
        content = await file.read()
        if not filename.lower().endswith(".dxf"):
            results.append(_drawing_response(store_failed_drawing(project, filename, content, "Only DXF files are supported.")))
            continue
        if filename.lower() in existing:
            results.append(_drawing_response(store_failed_drawing(project, filename, content, "Duplicate filename in this project.")))
            continue
        try:
            entities = parse_dxf(content)
            metadata = _metadata(content, entities)
            drawing = store_drawing(project, filename, content, entities, metadata)
            existing.add(filename.lower())
            results.append(_drawing_response(drawing))
        except Exception as error:
            results.append(_drawing_response(store_failed_drawing(project, filename, content, f"DXF extraction failed: {error}")))
    return {"project_id": project_id, "drawings": results}


@router.get("/projects/{project_id}/drawings")
async def list_project_drawings(project_id: str) -> list[dict[str, object]]:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return [_drawing_response(drawings[drawing_id]) for drawing_id in project.drawing_ids]