from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from app.cad.region_detector import detect_region_candidates, entities_intersecting_region
from app.rendering.region_renderer import render_region_png
from app.vision.ollama_client import OllamaClient, OllamaResult
from app.vision.validation import validate_visual_items

if TYPE_CHECKING:
    from app.cad.storage import UploadedDrawing

logger = logging.getLogger(__name__)

VISION_PROMPT = """You are analyzing a technical CAD drawing.

The image contains a selected region of the original drawing.

Identify the visible specification/table structure and relationships between labels, rows, columns, and values.
Determine which value visually belongs to which specification field.

Focus on:
- material
- construction
- finish
- dimensions
- hardware
- manufacturer/model references

Do not invent information. Do not infer values that are not visible. If text is unclear, explicitly mark it unclear.

The original DXF text is supplied separately by the application and is the authoritative source for exact text.
Your task is visual/contextual interpretation, not authoritative OCR.

Treat the image as a visual technical drawing, not as an OCR transcript. Identify labels, specification values, dimensions, quantities, materials, hardware, section headings, table rows, table columns, and relationships between labels and values.
For every item, return its evidence classification. Use SOURCE_CAD only when the supplied structured DXF entity explicitly contains the information. Use VECTOR_VISUAL for lettering or dimensions represented only by geometry. Use MODEL_INTERPRETATION only for an interpretation that is not explicit in either source. If vector lettering is not confidently readable, return visual_value as UNCLEAR and source_type as VECTOR_VISUAL.

Return JSON only in this shape:
{{"items":[{{"field":"...","visual_value":"...","source_type":"VECTOR_VISUAL","region_id":"...","relationship_confidence":0.0,"notes":"..."}}]}}

DXF context for relationship checking:
{context}
"""


class VisionResponseError(ValueError):
    """Raised when Ollama does not return the required structured shape."""


def _parse_items(raw_text: str) -> list[dict[str, Any]]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removeprefix("json").removesuffix("```").strip()
    parsed = json.loads(cleaned)
    if isinstance(parsed, dict):
        parsed = parsed.get("items", [])
    if not isinstance(parsed, list):
        raise VisionResponseError("Ollama response did not contain an items list.")
    return [item for item in parsed if isinstance(item, dict)]


def _regions(drawing: UploadedDrawing) -> list[dict[str, Any]]:
    regions = drawing.metadata.get("region_candidates")
    return regions if isinstance(regions, list) else detect_region_candidates(drawing.entities)


def analyze_region(drawing: UploadedDrawing, region_id: str, client: OllamaClient) -> dict[str, Any]:
    started = time.perf_counter()
    region = next((item for item in _regions(drawing) if item.get("id") == region_id), None)
    if region is None:
        raise ValueError(f"Region not found: {region_id}")
    source_entities = entities_intersecting_region(drawing.entities, region["bbox"])
    context = [
        {
            "entity_id": entity.get("id"),
            "handle": entity.get("source_handle"),
            "entity_type": entity.get("entity_type"),
            "source_text": entity.get("source_text"),
            "source_type": "SOURCE_CAD" if entity.get("entity_type") in {"TEXT", "MTEXT", "DIMENSION"} else "VECTOR_VISUAL",
            "normalized_text": entity.get("normalized_text"),
            "coordinates": entity.get("coordinates"),
            "bbox": entity.get("bbox"),
        }
        for entity in source_entities
    ]
    image_width = 2400
    image_height = 1600
    image = render_region_png(source_entities, region["bbox"], width=image_width, height=image_height, max_dimension=2400)
    result: OllamaResult = client.analyze_image(image, VISION_PROMPT.format(context=json.dumps(context, ensure_ascii=True)))
    visual_items = _parse_items(result.raw_text)
    validation = validate_visual_items(source_entities, visual_items)
    conflicts = sum(item["status"] == "CONFLICT" for item in validation)
    logger.info("Vision analysis drawing_id=%s region_id=%s bbox=%s image_dimensions=%sx%s image_bytes=%s model=%s duration_ms=%s source_entities=%s visual_items=%s conflicts=%s", drawing.id, region_id, region["bbox"], image_width, image_height, len(image), result.model, result.duration_ms, len(source_entities), len(visual_items), conflicts)
    return {
        "region_id": region_id,
        "drawing_id": drawing.id,
        "model": result.model,
        "region_bbox": region["bbox"],
        "image_dimensions": {"width": image_width, "height": image_height},
        "source_entities": source_entities,
        "visual_items": visual_items,
        "validation": validation,
        "conflict_count": conflicts,
        "raw_model_response": result.raw_response,
        "inference_duration_ms": result.duration_ms,
        "pipeline_duration_ms": int((time.perf_counter() - started) * 1000),
    }


__all__ = ["VISION_PROMPT", "VisionResponseError", "analyze_region"]