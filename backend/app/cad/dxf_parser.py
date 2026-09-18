from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Any

from ezdxf import bbox as ezdxf_bbox
from ezdxf import recover

logger = logging.getLogger(__name__)
EXTRACTION_SCHEMA_VERSION = "2.0"


def _clean_measurement(value: float) -> float:
    return round(value, 2)


def _point(value: Any) -> list[float]:
    return [float(value[0]), float(value[1])]


def _point3d(value: Any) -> list[float]:
    return [float(value[0]), float(value[1]), float(value[2])]


def _normalized_mtext(value: str) -> str:
    """Create a display form without changing the preserved source text."""
    normalized = re.sub(r"\\[A-Za-z]+(?:[-+]?\d*\.?\d+)?;", "", value)
    normalized = normalized.replace("\\P", "\n")
    return re.sub(r"[{}]", "", normalized).strip()


def _optional_point(entity: Any, name: str) -> list[float] | None:
    value = _dxf_get(entity, name)
    if value is None:
        return None
    try:
        return _point3d(value)
    except (TypeError, ValueError, IndexError):
        return None


def _dxf_get(entity: Any, name: str, default: Any = None) -> Any:
    try:
        return entity.dxf.get(name, default)
    except (AttributeError, KeyError, TypeError, ValueError):
        return default


def _block_summary(document: Any, name: str) -> dict[str, Any] | None:
    if not name or name not in document.blocks:
        return None
    block = document.blocks[name]
    text_entities: list[dict[str, Any]] = []
    entity_types: dict[str, int] = {}
    for block_entity in block:
        entity_type = block_entity.dxftype()
        entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
        if entity_type in {"TEXT", "MTEXT"}:
            source_text = str(block_entity.dxf.get("text", ""))
            text_entities.append({
                "entity_type": entity_type,
                "source_text": source_text,
                "normalized_text": _normalized_mtext(source_text) if entity_type == "MTEXT" else source_text,
                "insertion_point": _optional_point(block_entity, "insert"),
                "source_handle": block_entity.dxf.get("handle"),
                "layer": block_entity.dxf.get("layer", "0"),
                "context": {"space": "block_definition", "block_name": name},
            })
    return {
        "name": name,
        "base_point": _optional_point(block, "base_point"),
        "entity_count": sum(entity_types.values()),
        "entity_types": entity_types,
        "text_entities": text_entities,
        "context": {"space": "block_definition", "block_name": name},
    }


def parse_dxf(content: bytes) -> list[dict[str, Any]]:
    document, auditor = recover.read(BytesIO(content))
    if auditor.has_errors:
        logger.warning("DXF recovery reported %s errors", len(auditor.errors))
    entities: list[dict[str, Any]] = []

    for index, entity in enumerate(document.modelspace()):
        entity_type = entity.dxftype()
        try:
            extents = ezdxf_bbox.extents([entity])
            if extents.has_data:
                entity_bbox = (
                    float(extents.extmin.x),
                    float(extents.extmin.y),
                    float(extents.extmax.x),
                    float(extents.extmax.y),
                )
            else:
                entity_bbox = None
        except Exception:
            logger.warning("Could not calculate bounds for DXF entity %s", entity_type, exc_info=True)
            entity_bbox = None

        record: dict[str, Any] = {
            "schema_version": EXTRACTION_SCHEMA_VERSION,
            "id": f"{entity_type.lower()}_{index}",
            "entity_type": entity_type,
            "source_handle": entity.dxf.get("handle"),
            "layer": entity.dxf.get("layer", "0"),
            "bbox": entity_bbox,
            "properties": {},
            "context": {"space": "modelspace", "layout": "Model", "block_definition": None},
        }

        if entity_type == "LINE":
            record["geometry"] = {
                "kind": "line",
                "start": _point(entity.dxf.start),
                "end": _point(entity.dxf.end),
            }
            record["coordinates"] = {
                "start": _point3d(entity.dxf.start),
                "end": _point3d(entity.dxf.end),
            }
        elif entity_type == "LWPOLYLINE":
            record["geometry"] = {
                "kind": "polyline",
                "points": [_point(point) for point in entity.get_points("xy")],
                "closed": bool(entity.closed),
            }
            record["properties"].update({
                "elevation": float(entity.dxf.get("elevation", 0.0)),
                "constant_width": float(entity.dxf.get("const_width", 0.0)),
            })
            record["coordinates"] = [list(map(float, point)) for point in entity.get_points("xyz")]
        elif entity_type == "POLYLINE":
            record["geometry"] = {
                "kind": "polyline",
                "points": [[float(vertex.dxf.location.x), float(vertex.dxf.location.y)] for vertex in entity.vertices],
                "closed": bool(entity.is_closed),
            }
            record["coordinates"] = [_point3d(vertex.dxf.location) for vertex in entity.vertices]
        elif entity_type == "SPLINE":
            try:
                points = [[float(point.x), float(point.y)] for point in entity.flattening(0.01)]
            except Exception:
                points = [[float(point[0]), float(point[1])] for point in entity.control_points]
            record["geometry"] = {"kind": "polyline", "points": points, "closed": False}
            record["coordinates"] = [[float(point[0]), float(point[1])] for point in points]
        elif entity_type == "CIRCLE":
            record["geometry"] = {
                "kind": "circle",
                "center": _point(entity.dxf.center),
                "radius": float(entity.dxf.radius),
            }
            record["coordinates"] = {"center": _point3d(entity.dxf.center)}
        elif entity_type == "ARC":
            record["geometry"] = {
                "kind": "arc",
                "center": _point(entity.dxf.center),
                "radius": float(entity.dxf.radius),
                "start_angle": float(entity.dxf.start_angle),
                "end_angle": float(entity.dxf.end_angle),
            }
            record["coordinates"] = {"center": _point3d(entity.dxf.center)}
        elif entity_type == "POINT":
            record["geometry"] = {"kind": "point", "point": _point(entity.dxf.location)}
            record["coordinates"] = {"point": _point3d(entity.dxf.location)}

        if entity_type in {"TEXT", "MTEXT"}:
            source_text = str(entity.dxf.get("text", ""))
            normalized_text = _normalized_mtext(source_text) if entity_type == "MTEXT" else source_text
            record["source_text"] = source_text
            record["normalized_text"] = normalized_text
            record["text"] = source_text
            record["raw_text"] = source_text
            record["insertion_point"] = _optional_point(entity, "insert")
            record["text_metadata"] = {
                "rotation": float(_dxf_get(entity, "rotation", 0.0)),
                "height": float(_dxf_get(entity, "height", _dxf_get(entity, "char_height", 0.0))),
                "style": _dxf_get(entity, "style", "Standard"),
                "halign": _dxf_get(entity, "halign"),
                "valign": _dxf_get(entity, "valign"),
                "attachment_point": _dxf_get(entity, "attachment_point"),
            }
            record["rotation"] = record["text_metadata"]["rotation"]
            record["height"] = record["text_metadata"]["height"]
            record["text_style"] = record["text_metadata"]["style"]
            record["geometry"] = {
                "kind": "text",
                "point": _point(entity.dxf.insert),
            }
        elif entity_type == "INSERT":
            record["block_name"] = str(entity.dxf.get("name", ""))
            record["insertion_point"] = _optional_point(entity, "insert")
            record["insert_metadata"] = {
                "rotation": float(entity.dxf.get("rotation", 0.0)),
                "scale": [
                    float(entity.dxf.get("xscale", 1.0)),
                    float(entity.dxf.get("yscale", 1.0)),
                    float(entity.dxf.get("zscale", 1.0)),
                ],
                "point": _point(entity.dxf.insert),
            }
            record["block_definition"] = _block_summary(document, record["block_name"])
        elif entity_type == "DIMENSION":
            source_text = str(entity.dxf.get("text", ""))
            record["source_text"] = source_text
            record["normalized_text"] = source_text
            record["text"] = source_text
            record["raw_text"] = source_text
            record["dimension_type"] = int(entity.dxf.get("dimtype", 0)) & 0x0F
            record["definition_points"] = [
                point for point in (_optional_point(entity, name) for name in ("defpoint", "defpoint2", "defpoint3", "defpoint4"))
                if point is not None
            ]
            dimension_geometry: list[dict[str, Any]] = []
            try:
                for part in entity.virtual_entities():
                    if part.dxftype() == "LINE":
                        dimension_geometry.append({
                            "kind": "line",
                            "start": _point(part.dxf.start),
                            "end": _point(part.dxf.end),
                        })
                    elif part.dxftype() in {"TEXT", "MTEXT"}:
                        dimension_geometry.append({
                            "kind": "text",
                            "point": _point(part.dxf.insert),
                            "text": part.dxf.get("text", ""),
                        })
            except Exception:
                logger.warning("Could not extract geometry for dimension %s", record["id"], exc_info=True)
            record["dimension_geometry"] = dimension_geometry
            try:
                measurement = entity.get_measurement()
                dimension_style = document.dimstyles.get(entity.dxf.dimstyle)
                dimlfac = float(dimension_style.dxf.get("dimlfac", 1.0))
                record["measurement"] = _clean_measurement(float(measurement) * dimlfac)
            except (TypeError, ValueError, AttributeError):
                logger.warning("Could not calculate measurement for dimension %s", record["id"])
            try:
                dimension_style = document.dimstyles.get(entity.dxf.dimstyle)
                record["dimension_style"] = {
                    "name": entity.dxf.dimstyle,
                    "dimlfac": float(dimension_style.dxf.get("dimlfac", 1.0)),
                    "dimtxt": float(dimension_style.dxf.get("dimtxt", 0.0)),
                    "dimdec": int(dimension_style.dxf.get("dimdec", 0)),
                }
            except (AttributeError, TypeError, ValueError):
                record["dimension_style"] = {"name": entity.dxf.get("dimstyle")}

        if entity_bbox is None:
            record["extraction_warnings"] = ["bounding_box_unavailable"]
            logger.info("Retaining DXF entity without bounds: %s", entity_type)
        entities.append(record)

    return entities