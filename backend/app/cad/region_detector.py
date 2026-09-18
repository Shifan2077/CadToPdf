from __future__ import annotations

from typing import Any


def _entity_bbox(entity: dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = entity.get("bbox")
    if bbox is not None and len(bbox) == 4:
        return tuple(float(value) for value in bbox)
    insertion = entity.get("insertion_point")
    if insertion is not None and len(insertion) >= 2:
        x, y = float(insertion[0]), float(insertion[1])
        return (x, y, x, y)
    geometry = entity.get("geometry", {})
    point = geometry.get("point")
    if point is not None and len(point) >= 2:
        x, y = float(point[0]), float(point[1])
        return (x, y, x, y)
    return None


def _expand(bbox: tuple[float, float, float, float], padding: float) -> tuple[float, float, float, float]:
    return (bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding)


def _overlaps(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return not (first[2] < second[0] or second[2] < first[0] or first[3] < second[1] or second[3] < first[1])


def entities_intersecting_region(entities: list[dict[str, Any]], region_bbox: list[float] | tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Return all source entities whose drawable bounds overlap a region."""
    bounds = tuple(float(value) for value in region_bbox)
    return [
        entity for entity in entities
        if (entity_box := _entity_bbox(entity)) is not None and _overlaps(entity_box, bounds)
    ]


def _union(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _line_kind(entity: dict[str, Any]) -> str | None:
    geometry = entity.get("geometry", {})
    if geometry.get("kind") != "line":
        return None
    start = geometry.get("start")
    end = geometry.get("end")
    if not start or not end:
        return None
    dx = abs(float(end[0]) - float(start[0]))
    dy = abs(float(end[1]) - float(start[1]))
    if dy <= max(dx, 1.0) * 0.001:
        return "horizontal"
    if dx <= max(dy, 1.0) * 0.001:
        return "vertical"
    return None


def _axis_segments(entity: dict[str, Any]) -> list[tuple[tuple[float, float], tuple[float, float], str]]:
    geometry = entity.get("geometry", {})
    if geometry.get("kind") == "line":
        points = [geometry.get("start"), geometry.get("end")]
    elif geometry.get("kind") == "polyline":
        points = geometry.get("points", [])
    else:
        return []
    segments = []
    for start, end in zip(points, points[1:]):
        if not start or not end:
            continue
        dx = abs(float(end[0]) - float(start[0]))
        dy = abs(float(end[1]) - float(start[1]))
        if dy <= max(dx, 1.0) * 0.001:
            kind = "horizontal"
        elif dx <= max(dy, 1.0) * 0.001:
            kind = "vertical"
        else:
            continue
        segments.append(((float(start[0]), float(start[1])), (float(end[0]), float(end[1])), kind))
    return segments


def _cluster_values(values: list[float], tolerance: float) -> list[float]:
    if not values:
        return []
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or abs(value - sum(clusters[-1]) / len(clusters[-1])) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _geometry_candidates(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = []
    for entity in entities:
        for start, end, kind in _axis_segments(entity):
            bbox = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
            lines.append((entity, bbox, kind))
    if not lines:
        return []
    all_boxes = [bbox for _, bbox, _ in lines]
    drawing_box = _union(all_boxes)
    width = max(drawing_box[2] - drawing_box[0], 1.0)
    height = max(drawing_box[3] - drawing_box[1], 1.0)
    grid_lines = [
        line for line in lines
        if max(line[1][2] - line[1][0], line[1][3] - line[1][1]) >= max(width * 0.08, height * 0.08)
        and not (
            (line[2] == "horizontal" and line[1][2] - line[1][0] >= width * 0.75)
            or (line[2] == "vertical" and line[1][3] - line[1][1] >= height * 0.75)
        )
    ]
    if len(grid_lines) >= 4:
        lines = grid_lines
    columns = max(6, min(16, round((len(lines) ** 0.5) * 0.08)))
    rows = max(4, round(columns * height / width))
    tiles: dict[tuple[int, int], list[tuple[dict[str, Any], tuple[float, float, float, float], str]]] = {}
    for line in lines:
        entity, bbox, kind = line
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        column = min(columns - 1, max(0, int((center_x - drawing_box[0]) / width * columns)))
        row = min(rows - 1, max(0, int((center_y - drawing_box[1]) / height * rows)))
        tiles.setdefault((column, row), []).append(line)

    eligible = {
        key: value for key, value in tiles.items()
        if sum(item[2] == "horizontal" for item in value) >= 2
        and sum(item[2] == "vertical" for item in value) >= 2
    }
    tile_components: list[list[tuple[int, int]]] = []
    for key in eligible:
        adjacent = [index for index, component in enumerate(tile_components) if any(abs(key[0] - other[0]) <= 1 and abs(key[1] - other[1]) <= 1 for other in component)]
        if not adjacent:
            tile_components.append([key])
            continue
        first = adjacent[0]
        tile_components[first].append(key)
        for index in reversed(adjacent[1:]):
            tile_components[first].extend(tile_components.pop(index))

    candidates = []
    for index, tile_component in enumerate(tile_components):
        component = [item for key in tile_component for item in eligible[key]]
        horizontal = [item for item in component if item[2] == "horizontal"]
        vertical = [item for item in component if item[2] == "vertical"]
        if len(horizontal) < 2 or len(vertical) < 2:
            continue
        tile_width = width / columns
        tile_height = height / rows
        component_boxes = [item[1] for item in component]
        component_box = _union(component_boxes)
        padding = max(width, height) * 0.01
        bbox = _expand(component_box, padding)
        tolerance = max(width, height) * 0.002
        row_positions = _cluster_values([(item[1][1] + item[1][3]) / 2 for item in horizontal], tolerance)
        column_positions = _cluster_values([(item[1][0] + item[1][2]) / 2 for item in vertical], tolerance)
        dense_rows = []
        for row_position in row_positions:
            row_count = sum(abs(((item[1][1] + item[1][3]) / 2) - row_position) <= tolerance for item in horizontal)
            if row_count >= 3:
                dense_rows.append(row_position)
        if len(dense_rows) >= 2:
            row_runs: list[list[float]] = [[dense_rows[0]]]
            row_gap = max(width, height) * 0.06
            for row in dense_rows[1:]:
                if row - row_runs[-1][-1] > row_gap:
                    row_runs.append([row])
                else:
                    row_runs[-1].append(row)
            longest_run = max(row_runs, key=len)
            if len(longest_run) >= 5:
                dense_rows = longest_run
            dense_horizontal = [
                item for item in horizontal
                if any(abs(((item[1][1] + item[1][3]) / 2) - row) <= tolerance for row in dense_rows)
            ]
            row_positions = dense_rows
        entity_ids = sorted({str(item[0]["id"]) for item in component})
        area_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (width * height)
        border_like = area_ratio > 0.65 and len(row_positions) <= 4 and len(column_positions) <= 4
        row_count = len(row_positions)
        column_count = len(column_positions)
        grid_score = min(1.0, 0.25 * min(row_count / 8, 1.0) + 0.25 * min(column_count / 4, 1.0) + 0.25 * min(len(horizontal) / 20, 1.0) + 0.25 * min(len(vertical) / 12, 1.0))
        confidence = min(0.95, grid_score + (0.1 if not border_like else -0.2))
        if border_like or row_count < 2 or column_count < 2:
            continue
        candidates.append({
            "id": f"geometry_region_{index}",
            "bbox": list(bbox),
            "text_entity_ids": [],
            "geometry_entity_ids": entity_ids,
            "candidate_text": [],
            "layers": sorted({str(item[0].get("layer", "0")) for item in component}),
            "width": bbox[2] - bbox[0],
            "height": bbox[3] - bbox[1],
            "line_count": len(component),
            "horizontal_line_count": len(horizontal),
            "vertical_line_count": len(vertical),
            "row_count_estimate": row_count,
            "column_count_estimate": column_count,
            "grid_score": round(grid_score, 3),
            "confidence": round(confidence, 3),
            "region_type": "specification_table_candidate",
            "text_count": 0,
            "geometry_count": len(component),
            "reasoning": {
                "horizontal_line_count": len(horizontal),
                "vertical_line_count": len(vertical),
                "method": "adaptive connected grid tiles with repeated row/column lines",
                "text_available": False,
                "border_rejected": False,
            },
        })
    if not candidates:
        horizontal = [item for item in lines if item[2] == "horizontal"]
        vertical = [item for item in lines if item[2] == "vertical"]
        if len(horizontal) >= 2 and len(vertical) >= 2:
            candidates.append({
                "id": "geometry_region_0",
                "bbox": list(_expand(drawing_box, max(width, height) * 0.01)),
                "text_entity_ids": [],
                "geometry_entity_ids": [str(item[0]["id"]) for item in lines],
                "candidate_text": [],
                "layers": sorted({str(item[0].get("layer", "0")) for item in lines}),
                "confidence": 0.2,
                "region_type": "geometry_grid_candidate",
                "text_count": 0,
                "geometry_count": len(lines),
                "reasoning": {
                    "horizontal_line_count": len(horizontal),
                    "vertical_line_count": len(vertical),
                    "method": "axis-aligned line extent fallback",
                    "text_available": False,
                    "long_segment_filter": "0.08 of drawing major dimension",
                },
            })
    return candidates


def detect_region_candidates(entities: list[dict[str, Any]], proximity: float = 12.0) -> list[dict[str, Any]]:
    """Group nearby text and surrounding CAD geometry into renderable candidates.

    This is intentionally conservative: it suggests regions for later inspection and
    never changes or removes the source entity records.
    """
    text_entities = [
        entity for entity in entities
        if str(entity.get("entity_type", "")).upper() in {"TEXT", "MTEXT"}
        and (entity.get("source_text") or entity.get("text"))
        and _entity_bbox(entity) is not None
    ]
    groups: list[list[dict[str, Any]]] = []
    for entity in text_entities:
        entity_box = _entity_bbox(entity)
        assert entity_box is not None
        matching_groups = []
        for index, group in enumerate(groups):
            group_box = _union([_entity_bbox(item) for item in group if _entity_bbox(item) is not None])
            if _overlaps(_expand(group_box, proximity), entity_box):
                matching_groups.append(index)
        if not matching_groups:
            groups.append([entity])
            continue
        first_index = matching_groups[0]
        groups[first_index].append(entity)
        for index in reversed(matching_groups[1:]):
            groups[first_index].extend(groups.pop(index))

    candidates: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        text_boxes = [_entity_bbox(entity) for entity in group]
        valid_text_boxes = [box for box in text_boxes if box is not None]
        if not valid_text_boxes:
            continue
        text_box = _union(valid_text_boxes)
        region_box = _expand(text_box, proximity)
        geometry_entities = []
        for entity in entities:
            if entity in group or str(entity.get("entity_type", "")).upper() in {"TEXT", "MTEXT"}:
                continue
            entity_box = _entity_bbox(entity)
            if entity_box is not None and _overlaps(region_box, entity_box):
                geometry_entities.append(entity)
        all_boxes = valid_text_boxes + [_entity_bbox(entity) for entity in geometry_entities if _entity_bbox(entity) is not None]
        candidates.append({
            "id": f"region_{index}",
            "bbox": list(_expand(_union(all_boxes), proximity / 2)),
            "text_entity_ids": [str(entity["id"]) for entity in group],
            "geometry_entity_ids": [str(entity["id"]) for entity in geometry_entities],
            "candidate_text": [entity.get("source_text", entity.get("text", "")) for entity in group],
            "layers": sorted({str(entity.get("layer", "0")) for entity in group + geometry_entities}),
            "confidence": min(1.0, 0.45 + 0.1 * len(group) + 0.05 * len(geometry_entities)),
            "region_type": "text_geometry_candidate",
            "text_count": len(group),
            "geometry_count": len(geometry_entities),
            "reasoning": {
                "text_count": len(group),
                "nearby_geometry_count": len(geometry_entities),
                "method": "text proximity with overlapping geometry",
            },
        })
    candidates.extend(_geometry_candidates(entities))
    candidates.sort(key=lambda candidate: (candidate.get("text_count", 0) >= 2, candidate.get("geometry_count", 0), candidate.get("confidence", 0.0)), reverse=True)
    for index, candidate in enumerate(candidates):
        candidate["rank"] = index
    return candidates


__all__ = ["detect_region_candidates", "entities_intersecting_region"]