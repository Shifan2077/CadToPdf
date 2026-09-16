from __future__ import annotations

from typing import Any


class DrawingDetector:
    """Simple deterministic detector for a main drawing cluster in CAD-like entities."""

    def detect(self, entities: list[dict[str, Any]]) -> dict[str, Any]:
        if not entities:
            return {"selected_cluster": "none", "bbox": (0.0, 0.0, 0.0, 0.0), "clusters": []}

        valid = [entity for entity in entities if self._is_relevant(entity)]
        if not valid:
            valid = entities

        candidate = self._select_main_candidate(valid)
        bbox = self._compute_bbox(candidate)
        cluster_id = candidate[0]["id"] if len(candidate) == 1 else "main"
        return {"selected_cluster": cluster_id, "bbox": bbox, "clusters": [
            {"id": cluster_id, "entities": candidate, "bbox": bbox}
        ]}

    def _is_relevant(self, entity: dict[str, Any]) -> bool:
        entity_type = str(entity.get("entity_type", "")).upper()
        bbox = entity.get("bbox")
        if bbox is None:
            return False
        if entity_type in {"POINT"}:
            return False
        if entity_type in {"TEXT"} and not entity.get("text"):
            return False
        return True

    def _select_main_candidate(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_cluster: dict[str, list[dict[str, Any]]] = {"main": entities}

        overall = [(entity["bbox"][0], entity["bbox"][1], entity["bbox"][2], entity["bbox"][3]) for entity in entities]
        closest = min(overall, default=(0, 0, 0, 0))
        farthest = max(overall, default=(0, 0, 0, 0))

        # Keep the primary cluster as the largest connected-looking group by bounding box footprint.
        if len(entities) == 1:
            return entities

        if farthest[0] - closest[0] > 100 or farthest[1] - closest[1] > 100:
            main_entities = [e for e in entities if e["bbox"][0] <= farthest[0] and e["bbox"][1] <= farthest[1]]
            if main_entities:
                return main_entities

        return entities

    def _compute_bbox(self, entities: list[dict[str, Any]]) -> tuple[float, float, float, float]:
        xs = []
        ys = []
        for entity in entities:
            bbox = entity.get("bbox")
            if bbox is None:
                continue
            xs.extend([bbox[0], bbox[2]])
            ys.extend([bbox[1], bbox[3]])

        if not xs or not ys:
            return (0.0, 0.0, 0.0, 0.0)

        return (min(xs), min(ys), max(xs), max(ys))
