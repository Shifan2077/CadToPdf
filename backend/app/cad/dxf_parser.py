from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from ezdxf import bbox as ezdxf_bbox
from ezdxf import recover

logger = logging.getLogger(__name__)


def _clean_measurement(value: float) -> float:
    return round(value, 2)


def _point(value: Any) -> list[float]:
    return [float(value[0]), float(value[1])]


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
            "id": f"{entity_type.lower()}_{index}",
            "entity_type": entity_type,
            "source_handle": entity.dxf.get("handle"),
            "layer": entity.dxf.get("layer", "0"),
            "bbox": entity_bbox,
            "properties": {},
        }

        if entity_type == "LINE":
            record["geometry"] = {
                "kind": "line",
                "start": _point(entity.dxf.start),
                "end": _point(entity.dxf.end),
            }
        elif entity_type == "LWPOLYLINE":
            record["geometry"] = {
                "kind": "polyline",
                "points": [_point(point) for point in entity.get_points("xy")],
                "closed": bool(entity.closed),
            }
        elif entity_type == "POLYLINE":
            record["geometry"] = {
                "kind": "polyline",
                "points": [[float(vertex.dxf.location.x), float(vertex.dxf.location.y)] for vertex in entity.vertices],
                "closed": bool(entity.is_closed),
            }
        elif entity_type == "CIRCLE":
            record["geometry"] = {
                "kind": "circle",
                "center": _point(entity.dxf.center),
                "radius": float(entity.dxf.radius),
            }
        elif entity_type == "ARC":
            record["geometry"] = {
                "kind": "arc",
                "center": _point(entity.dxf.center),
                "radius": float(entity.dxf.radius),
                "start_angle": float(entity.dxf.start_angle),
                "end_angle": float(entity.dxf.end_angle),
            }
        elif entity_type == "POINT":
            record["geometry"] = {"kind": "point", "point": _point(entity.dxf.location)}

        if entity_type in {"TEXT", "MTEXT"}:
            record["text"] = entity.dxf.get("text", "")
            record["raw_text"] = record["text"]
            record["text_metadata"] = {
                "rotation": float(entity.dxf.get("rotation", 0.0)),
                "height": float(entity.dxf.get("height", entity.dxf.get("char_height", 0.0))),
                "style": entity.dxf.get("style", "Standard"),
            }
            record["geometry"] = {
                "kind": "text",
                "point": _point(entity.dxf.insert),
            }
        elif entity_type == "INSERT":
            record["block_name"] = str(entity.dxf.get("name", ""))
            record["insert_metadata"] = {
                "rotation": float(entity.dxf.get("rotation", 0.0)),
                "scale": [
                    float(entity.dxf.get("xscale", 1.0)),
                    float(entity.dxf.get("yscale", 1.0)),
                    float(entity.dxf.get("zscale", 1.0)),
                ],
                "point": _point(entity.dxf.insert),
            }
        elif entity_type == "DIMENSION":
            record["text"] = entity.dxf.get("text", "")
            record["raw_text"] = record["text"]
            record["dimension_type"] = int(entity.dxf.get("dimtype", 0)) & 0x0F
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

        if entity_bbox is not None:
            entities.append(record)
        else:
            logger.info("Skipping DXF entity without bounds: %s", entity_type)

    return entities