from __future__ import annotations

from html import escape
from typing import Any

from app.rendering.raster import rasterize_svg


def _project(point: list[float], bounds: tuple[float, float, float, float], width: int, height: int, padding: int) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bounds
    scale = min((width - 2 * padding) / max(max_x - min_x, 1.0), (height - 2 * padding) / max(max_y - min_y, 1.0))
    return padding + (point[0] - min_x) * scale, height - padding - (point[1] - min_y) * scale


def _inside(point: list[float] | tuple[float, float], bounds: tuple[float, float, float, float]) -> bool:
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def _segment_intersects(start: list[float], end: list[float], bounds: tuple[float, float, float, float]) -> bool:
    segment_bounds = (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1]))
    return not (segment_bounds[2] < bounds[0] or bounds[2] < segment_bounds[0] or segment_bounds[3] < bounds[1] or bounds[3] < segment_bounds[1])


def render_region(drawing: list[dict[str, Any]] | dict[str, Any], region_bbox: list[float] | tuple[float, float, float, float], *, width: int = 2400, height: int = 1600) -> bytes:
    """Render normalized extraction records for a selected region as an SVG image.

    The renderer deliberately consumes normalized records, so it can be replaced by
    a higher-fidelity raster renderer later without changing the extraction contract.
    """
    entities = drawing if isinstance(drawing, list) else drawing.get("entities", [])
    bounds = tuple(float(value) for value in region_bbox)
    padding = 32
    geometry_shapes: list[str] = []
    text_shapes: list[str] = []
    for entity in entities:
        geometry = entity.get("geometry", {})
        kind = geometry.get("kind")
        if kind == "line":
            midpoint = [(geometry["start"][0] + geometry["end"][0]) / 2, (geometry["start"][1] + geometry["end"][1]) / 2]
            if not _segment_intersects(geometry["start"], geometry["end"], bounds):
                continue
            start = _project(geometry["start"], bounds, width, height, padding)
            end = _project(geometry["end"], bounds, width, height, padding)
            geometry_shapes.append(f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}" />')
        elif kind == "polyline" and geometry.get("points"):
            source_points = geometry["points"]
            runs: list[list[list[float]]] = []
            current: list[list[float]] = []
            for start, end in zip(source_points, source_points[1:]):
                midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
                if _segment_intersects(start, end, bounds):
                    if not current:
                        current.append(start)
                    current.append(end)
                elif current:
                    runs.append(current)
                    current = []
            if current:
                runs.append(current)
            for run in runs:
                if len(run) < 2:
                    continue
                points = [_project(point, bounds, width, height, padding) for point in run]
                point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
                geometry_shapes.append(f'<polyline points="{point_text}" />')
        elif kind == "circle":
            center = _project(geometry["center"], bounds, width, height, padding)
            min_x, min_y, max_x, max_y = bounds
            scale = min((width - 2 * padding) / max(max_x - min_x, 1.0), (height - 2 * padding) / max(max_y - min_y, 1.0))
            geometry_shapes.append(f'<circle cx="{center[0]:.2f}" cy="{center[1]:.2f}" r="{float(geometry["radius"]) * scale:.2f}" />')
        elif kind == "text" and geometry.get("point"):
            point = _project(geometry["point"], bounds, width, height, padding)
            text = escape(str(entity.get("normalized_text") or entity.get("source_text", entity.get("text", ""))))
            if text:
                for line_index, line in enumerate(text.splitlines() or [text]):
                    text_shapes.append(f'<text x="{point[0]:.2f}" y="{point[1] + line_index * 12:.2f}">{line}</text>')
        elif entity.get("entity_type") == "DIMENSION":
            for part in entity.get("dimension_geometry", []):
                if part.get("kind") == "line":
                    start = _project(part["start"], bounds, width, height, padding)
                    end = _project(part["end"], bounds, width, height, padding)
                    geometry_shapes.append(f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}" />')
                elif part.get("kind") == "text":
                    point = _project(part["point"], bounds, width, height, padding)
                    text_shapes.append(f'<text x="{point[0]:.2f}" y="{point[1]:.2f}">{escape(str(part.get("text") or entity.get("source_text", "")))}</text>')

    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<g fill="none" stroke="#111827" stroke-width="1">{geometry_shapes}</g>
<g fill="#111827" stroke="none" font-family="Arial, sans-serif" font-size="12">{text_shapes}</g>
</svg>""".format(width=width, height=height, geometry_shapes="".join(geometry_shapes), text_shapes="".join(text_shapes))
    return svg.encode("utf-8")


def render_region_png(drawing: list[dict[str, Any]] | dict[str, Any], region_bbox: list[float] | tuple[float, float, float, float], *, width: int = 2400, height: int = 1600, max_dimension: int = 2400) -> bytes:
    """Render a selected region to SVG and convert it to a bounded PNG."""
    return rasterize_svg(render_region(drawing, region_bbox, width=width, height=height), max_dimension=max_dimension)


__all__ = ["render_region", "render_region_png"]