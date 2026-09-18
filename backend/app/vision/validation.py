from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

STATUSES = {"MATCH", "CONFLICT", "SOURCE_ONLY", "VISUAL_ONLY", "UNCLEAR"}


def _source_values(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for entity in entities:
        source_text = str(entity.get("source_text", "")).strip()
        if source_text and source_text != "<>" and source_text not in {item["source_value"] for item in values}:
            values.append({"source_value": source_text, "source_entity_id": entity.get("id"), "source_handle": entity.get("source_handle")})
    return values


def validate_visual_items(entities: list[dict[str, Any]], visual_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare model observations without modifying authoritative entity text."""
    sources = _source_values(entities)
    results: list[dict[str, Any]] = []
    matched_sources: set[str] = set()
    for item in visual_items:
        field = str(item.get("field", "")).strip()
        visual_value = str(item.get("visual_value", "")).strip()
        confidence = item.get("relationship_confidence")
        notes = str(item.get("notes", ""))
        if not visual_value or visual_value.upper() in {"UNCLEAR", "UNKNOWN", "N/A"}:
            results.append({"field": field, "source_value": None, "visual_value": visual_value or None, "source_type": "SOURCE_CAD", "visual_source_type": item.get("source_type", "VECTOR_VISUAL"), "source": "ezdxf", "status": "UNCLEAR", "relationship_confidence": confidence, "notes": notes})
            continue
        exact = next((source for source in sources if source["source_value"] == visual_value), None)
        if exact is not None:
            matched_sources.add(exact["source_value"])
            status = "MATCH"
            source_value = exact["source_value"]
            source_entity_id = exact["source_entity_id"]
            source_handle = exact["source_handle"]
        elif sources:
            similar = max(sources, key=lambda source: SequenceMatcher(None, source["source_value"].lower(), visual_value.lower()).ratio())
            similarity = SequenceMatcher(None, similar["source_value"].lower(), visual_value.lower()).ratio()
            if similarity < 0.35:
                source_value = None
                source_entity_id = None
                source_handle = None
                status = "VISUAL_ONLY"
            else:
                source_value = similar["source_value"]
                source_entity_id = similar["source_entity_id"]
                source_handle = similar["source_handle"]
                status = "CONFLICT"
        else:
            source_value = None
            source_entity_id = None
            source_handle = None
            status = "VISUAL_ONLY"
        result = {"field": field, "source_value": source_value, "visual_value": visual_value, "source_type": "SOURCE_CAD" if source_value is not None else None, "visual_source_type": item.get("source_type", "VECTOR_VISUAL"), "source": "ezdxf", "status": status, "relationship_confidence": confidence, "notes": notes}
        if source_entity_id is not None:
            result["source_entity_id"] = source_entity_id
        if source_handle is not None:
            result["source_handle"] = source_handle
        results.append(result)

    for source in sources:
        if source["source_value"] not in matched_sources and not any(result.get("source_value") == source["source_value"] for result in results):
            results.append({"field": None, "source_value": source["source_value"], "visual_value": None, "source_type": "SOURCE_CAD", "visual_source_type": None, "source": "ezdxf", "status": "SOURCE_ONLY", "source_entity_id": source["source_entity_id"], "source_handle": source["source_handle"]})
    return results


__all__ = ["STATUSES", "validate_visual_items"]