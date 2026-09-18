from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.cad.storage import drawings
from app.cad.region_detector import detect_region_candidates, entities_intersecting_region
from app.detection.drawing_detector import DrawingDetector
from app.rendering.region_renderer import render_region, render_region_png

router = APIRouter()


class AnalysisRequest(BaseModel):
    upload_id: str


def _entities_for_region(entities: list[dict[str, object]], region: dict[str, object]) -> list[dict[str, object]]:
    return entities_intersecting_region(entities, region.get("bbox") or [])


@router.get("/drawings/{drawing_id}")
async def get_drawing(drawing_id: str) -> dict[str, object]:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    return {
        "id": drawing.id,
        "project_id": drawing.project_id,
        "filename": drawing.filename,
        "file_size": drawing.file_size,
        "status": drawing.status,
        "error": drawing.error,
        "uploaded_at": drawing.uploaded_at,
        "metadata": drawing.metadata,
    }


@router.get("/drawings/{drawing_id}/raw")
async def get_raw_drawing(drawing_id: str) -> dict[str, object]:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    return {"drawing_id": drawing.id, "project_id": drawing.project_id, "filename": drawing.filename, "metadata": drawing.metadata, "entities": drawing.entities}


@router.get("/drawings/{drawing_id}/regions")
async def get_region_candidates(drawing_id: str) -> dict[str, object]:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    regions = drawing.metadata.get("region_candidates")
    if not isinstance(regions, list):
        regions = detect_region_candidates(drawing.entities)
    entity_counts: dict[str, int] = {}
    for entity in drawing.entities:
        entity_type = str(entity.get("entity_type", "UNKNOWN"))
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
    return {
        "drawing_id": drawing.id,
        "schema_version": drawing.metadata.get("schema_version", "2.0"),
        "entity_counts": entity_counts,
        "text_count": sum(entity.get("entity_type") == "TEXT" for entity in drawing.entities),
        "mtext_count": sum(entity.get("entity_type") == "MTEXT" for entity in drawing.entities),
        "dimension_count": sum(entity.get("entity_type") == "DIMENSION" for entity in drawing.entities),
        "regions": regions,
    }


@router.get("/drawings/{drawing_id}/regions/{region_id}/image")
async def render_region_image(drawing_id: str, region_id: str) -> Response:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    regions = drawing.metadata.get("region_candidates")
    if not isinstance(regions, list):
        regions = detect_region_candidates(drawing.entities)
    region = next((item for item in regions if item.get("id") == region_id), None)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found.")
    region_entities = _entities_for_region(drawing.entities, region)
    image = render_region(region_entities, region["bbox"])
    return Response(content=image, media_type="image/svg+xml")


@router.get("/drawings/{drawing_id}/regions/{region_id}/image.png")
async def render_region_png_image(drawing_id: str, region_id: str) -> Response:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    regions = drawing.metadata.get("region_candidates")
    if not isinstance(regions, list):
        regions = detect_region_candidates(drawing.entities)
    region = next((item for item in regions if item.get("id") == region_id), None)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found.")
    region_entities = _entities_for_region(drawing.entities, region)
    image = render_region_png(region_entities, region["bbox"], max_dimension=2400)
    text_count = sum(entity.get("entity_type") in {"TEXT", "MTEXT"} for entity in region_entities)
    geometry_count = len(region_entities) - text_count
    return Response(
        content=image,
        media_type="image/png",
        headers={
            "X-Region-BBox": ",".join(str(value) for value in region["bbox"]),
            "X-Region-Entity-Count": str(len(region_entities)),
            "X-Region-Text-Count": str(text_count),
            "X-Region-Geometry-Count": str(geometry_count),
        },
    )


@router.get("/drawings/{drawing_id}/regions/{region_id}/debug")
async def debug_region(drawing_id: str, region_id: str) -> dict[str, object]:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Drawing not found.")
    regions = drawing.metadata.get("region_candidates")
    if not isinstance(regions, list):
        regions = detect_region_candidates(drawing.entities)
    region = next((item for item in regions if item.get("id") == region_id), None)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found.")
    region_entities = _entities_for_region(drawing.entities, region)
    text_entities = [entity for entity in region_entities if entity.get("entity_type") in {"TEXT", "MTEXT"}]
    return {
        "drawing_id": drawing.id,
        "region": region,
        "entity_count": len(region_entities),
        "text_count": len(text_entities),
        "mtext_count": sum(entity.get("entity_type") == "MTEXT" for entity in text_entities),
        "dimension_count": sum(entity.get("entity_type") == "DIMENSION" for entity in region_entities),
        "geometry_count": len(region_entities) - len(text_entities),
        "text_entities": text_entities,
        "geometry_entities": [entity for entity in region_entities if entity not in text_entities],
    }


@router.post("/drawings/{drawing_id}/regions/{region_id}/analyze-vision")
async def analyze_region_vision(drawing_id: str, region_id: str) -> dict[str, object]:
    raise HTTPException(status_code=409, detail="Vision inference is disabled until a specification-table region is verified.")


def _bbox_for_entities(entities: list[dict[str, object]]) -> list[float] | None:
    boxes = [entity["bbox"] for entity in entities if entity.get("bbox")]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes), min(box[1] for box in boxes),
        max(box[2] for box in boxes), max(box[3] for box in boxes),
    ]


def _layer_summary(entities: list[dict[str, object]]) -> list[dict[str, object]]:
    layers: dict[str, list[dict[str, object]]] = {}
    for entity in entities:
        layers.setdefault(str(entity.get("layer", "0")), []).append(entity)
    return [
        {
            "name": name,
            "entity_count": len(items),
            "entity_types": sorted({str(item["entity_type"]) for item in items}),
            "bbox": _bbox_for_entities(items),
        }
        for name, items in sorted(layers.items())
    ]


@router.post("/analyze")
@router.post("/drawings/{drawing_id}/analyze")
async def analyze(request: AnalysisRequest | None = None, drawing_id: str | None = None) -> dict[str, object]:
    requested_id = drawing_id or (request.upload_id if request else None)
    drawing = drawings.get(requested_id or "")
    if drawing is None:
        raise HTTPException(status_code=404, detail="Uploaded drawing not found.")

    result = DrawingDetector().detect(drawing.entities)
    dimensions_detected = sum(entity["entity_type"] == "DIMENSION" for entity in drawing.entities)
    annotations_detected = sum(
        entity["entity_type"] in {"TEXT", "MTEXT", "DIMENSION"}
        for entity in drawing.entities
    )
    detailed_dimensions = [
        entity["measurement"]
        for entity in drawing.entities
        if entity["entity_type"] == "DIMENSION" and "measurement" in entity
    ]
    primary_entities = result["clusters"][0]["entities"] if result["clusters"] else []
    lines = [entity for entity in drawing.entities if entity["entity_type"] == "LINE"]
    line_length = sum(
        ((entity["geometry"]["end"][0] - entity["geometry"]["start"][0]) ** 2
         + (entity["geometry"]["end"][1] - entity["geometry"]["start"][1]) ** 2) ** 0.5
        for entity in lines if entity.get("geometry")
    )
    raw_bbox = _bbox_for_entities(drawing.entities) or [0.0, 0.0, 0.0, 0.0]
    dimensions = [
        {
            "id": entity["id"],
            "type": entity.get("dimension_type", "unknown"),
            "text": entity.get("text") or None,
            "value": entity.get("measurement"),
            "bbox": entity.get("bbox"),
            "layer": entity.get("layer"),
            "status": "resolved" if "measurement" in entity else "unresolved",
        }
        for entity in drawing.entities if entity["entity_type"] == "DIMENSION"
    ]
    text_annotations = [
        {"id": entity["id"], "text": entity.get("text", ""), "layer": entity.get("layer"),
         "position": entity.get("geometry", {}).get("point"), "metadata": entity.get("text_metadata", {})}
        for entity in drawing.entities if entity["entity_type"] in {"TEXT", "MTEXT"}
    ]
    blocks = [
        {"id": entity["id"], "name": entity.get("block_name", ""), "layer": entity.get("layer"),
         "metadata": entity.get("insert_metadata", {})}
        for entity in drawing.entities if entity["entity_type"] == "INSERT"
    ]
    return {
        "semantic_model_version": "1.0",
        "upload_id": requested_id,
        "file": {"name": drawing.filename, "size_bytes": drawing.file_size, **drawing.metadata},
        "raw_cad_extents": raw_bbox,
        "entities_detected": len(drawing.entities),
        "candidate_drawing_clusters": len(result["clusters"]),
        "dimensions_detected": dimensions_detected,
        "detailed_dimensions": detailed_dimensions,
        "annotations_detected": annotations_detected,
        "selected_primary_cluster": result["selected_cluster"],
        "drawing_size": {
            "width": result["bbox"][2] - result["bbox"][0],
            "height": result["bbox"][3] - result["bbox"][1],
        },
        "bbox": result["bbox"],
        "layers": _layer_summary(drawing.entities),
        "dimensions": dimensions,
        "text_annotations": text_annotations,
        "blocks": blocks,
        "geometry_summary": {
            "line_count": len(lines),
            "total_line_length": round(line_length, 2),
            "closed_polylines": sum(1 for entity in drawing.entities if entity["entity_type"] in {"LWPOLYLINE", "POLYLINE"} and entity.get("geometry", {}).get("closed")),
            "open_polylines": sum(1 for entity in drawing.entities if entity["entity_type"] in {"LWPOLYLINE", "POLYLINE"} and not entity.get("geometry", {}).get("closed")),
            "circle_count": sum(1 for entity in drawing.entities if entity["entity_type"] == "CIRCLE"),
        },
        "primary_entity_count": len(primary_entities),
        "summary": f"The file contains {len(drawing.entities)} entities across {len(_layer_summary(drawing.entities))} layers. A primary drawing region was detected.",
        "entities": drawing.entities,
    }
