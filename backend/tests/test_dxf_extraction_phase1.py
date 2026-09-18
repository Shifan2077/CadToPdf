from __future__ import annotations

from io import StringIO

import ezdxf
from PIL import Image

from app.cad.dxf_parser import EXTRACTION_SCHEMA_VERSION, parse_dxf
from app.cad.region_detector import detect_region_candidates
from app.rendering.region_renderer import render_region, render_region_png


def _drawing_bytes() -> bytes:
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    modelspace.add_line((0, 0, 0), (100, 0, 0), dxfattribs={"layer": "SPEC"})
    modelspace.add_text("143 X 57 X 1.6", dxfattribs={"insert": (10, 20), "height": 2.5, "layer": "SPEC"})
    modelspace.add_mtext(r"{\C1;SHUTTER FRAME}\P143 X 57 X 1.6", dxfattribs={"insert": (10, 24), "char_height": 2.5, "layer": "SPEC"})
    dimension = modelspace.add_linear_dim(base=(10, 10), p1=(10, 0), p2=(30, 0), dxfattribs={"layer": "SPEC"})
    dimension.render()
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode("utf-8")


def test_parser_preserves_text_coordinates_and_schema_version():
    entities = parse_dxf(_drawing_bytes())
    text_entities = [entity for entity in entities if entity["entity_type"] in {"TEXT", "MTEXT"}]

    assert text_entities
    assert all(entity["schema_version"] == EXTRACTION_SCHEMA_VERSION for entity in entities)
    text = next(entity for entity in text_entities if entity["entity_type"] == "TEXT")
    assert text["source_text"] == "143 X 57 X 1.6"
    assert text["normalized_text"] == text["source_text"]
    assert text["insertion_point"] == [10.0, 20.0, 0.0]
    assert text["text_metadata"]["height"] == 2.5
    assert text["bbox"] is not None

    mtext = next(entity for entity in text_entities if entity["entity_type"] == "MTEXT")
    assert mtext["source_text"] == r"{\C1;SHUTTER FRAME}\P143 X 57 X 1.6"
    assert mtext["normalized_text"] == "SHUTTER FRAME\n143 X 57 X 1.6"


def test_parser_preserves_dimension_source_and_calculated_values():
    dimensions = [entity for entity in parse_dxf(_drawing_bytes()) if entity["entity_type"] == "DIMENSION"]

    assert dimensions
    dimension = dimensions[0]
    assert "source_text" in dimension
    assert "measurement" in dimension
    assert dimension["definition_points"]
    assert dimension["dimension_style"]["name"]
    assert dimension["dimension_geometry"]


def test_region_detector_groups_text_and_nearby_geometry():
    entities = parse_dxf(_drawing_bytes())
    regions = detect_region_candidates(entities)

    assert regions
    region = next(region for region in regions if len(region["text_entity_ids"]) == 2)
    assert set(region["candidate_text"]) == {"143 X 57 X 1.6", r"{\C1;SHUTTER FRAME}\P143 X 57 X 1.6"}
    assert region["geometry_entity_ids"]
    assert region["reasoning"]["method"] == "text proximity with overlapping geometry"


def test_table_region_contains_multiple_text_rows_and_grid_geometry():
    entities = [
        {"id": "text_field", "entity_type": "TEXT", "source_text": "SHUTTER FRAME", "normalized_text": "SHUTTER FRAME", "layer": "SPEC", "bbox": [10, 10, 30, 12], "geometry": {"kind": "text", "point": [10, 10]}},
        {"id": "text_value", "entity_type": "TEXT", "source_text": "STEEL", "normalized_text": "STEEL", "layer": "SPEC", "bbox": [40, 10, 50, 12], "geometry": {"kind": "text", "point": [40, 10]}},
        {"id": "row_top", "entity_type": "LINE", "layer": "SPEC", "bbox": [0, 5, 60, 5], "geometry": {"kind": "line", "start": [0, 5], "end": [60, 5]}},
        {"id": "row_bottom", "entity_type": "LINE", "layer": "SPEC", "bbox": [0, 20, 60, 20], "geometry": {"kind": "line", "start": [0, 20], "end": [60, 20]}},
        {"id": "column_left", "entity_type": "LINE", "layer": "SPEC", "bbox": [5, 5, 5, 20], "geometry": {"kind": "line", "start": [5, 5], "end": [5, 20]}},
        {"id": "column_right", "entity_type": "LINE", "layer": "SPEC", "bbox": [55, 5, 55, 20], "geometry": {"kind": "line", "start": [55, 5], "end": [55, 20]}},
    ]

    region = next(region for region in detect_region_candidates(entities) if region["region_type"] == "text_geometry_candidate")

    assert region["text_count"] == 2
    assert {"text_field", "text_value"} <= set(region["text_entity_ids"])
    assert region["bbox"][0] <= 10 and region["bbox"][2] >= 50


def test_geometry_only_candidates_are_not_specification_text_regions():
    entities = [
        {"id": "h1", "entity_type": "LINE", "bbox": [0, 0, 100, 0], "geometry": {"kind": "line", "start": [0, 0], "end": [100, 0]}},
        {"id": "h2", "entity_type": "LINE", "bbox": [0, 20, 100, 20], "geometry": {"kind": "line", "start": [0, 20], "end": [100, 20]}},
        {"id": "v1", "entity_type": "LINE", "bbox": [0, 0, 0, 20], "geometry": {"kind": "line", "start": [0, 0], "end": [0, 20]}},
        {"id": "v2", "entity_type": "LINE", "bbox": [100, 0, 100, 20], "geometry": {"kind": "line", "start": [100, 0], "end": [100, 20]}},
    ]

    regions = detect_region_candidates(entities)

    assert regions
    assert all(region["text_count"] == 0 for region in regions)
    assert all(region["region_type"] == "geometry_grid_candidate" for region in regions)


def test_polyline_grid_is_a_specification_table_candidate():
    entities = [
        {"id": "grid", "entity_type": "POLYLINE", "bbox": [0, 0, 100, 100], "geometry": {"kind": "polyline", "points": [[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]], "closed": False}},
        {"id": "row", "entity_type": "POLYLINE", "bbox": [0, 50, 100, 50], "geometry": {"kind": "polyline", "points": [[0, 50], [100, 50]], "closed": False}},
        {"id": "column", "entity_type": "POLYLINE", "bbox": [50, 0, 50, 100], "geometry": {"kind": "polyline", "points": [[50, 0], [50, 100]], "closed": False}},
        {"id": "far_h", "entity_type": "POLYLINE", "bbox": [200, 200, 300, 200], "geometry": {"kind": "polyline", "points": [[200, 200], [300, 200]], "closed": False}},
        {"id": "far_v", "entity_type": "POLYLINE", "bbox": [300, 200, 300, 300], "geometry": {"kind": "polyline", "points": [[300, 200], [300, 300]], "closed": False}},
    ]

    regions = detect_region_candidates(entities)

    assert regions
    candidate = regions[0]
    assert candidate["region_type"] in {"specification_table_candidate", "geometry_grid_candidate"}
    if candidate["region_type"] == "specification_table_candidate":
        assert candidate["row_count_estimate"] >= 2
        assert candidate["column_count_estimate"] >= 2
        assert candidate["grid_score"] > 0


def test_entities_without_bounds_are_retained(monkeypatch):
    class EmptyExtents:
        has_data = False

    monkeypatch.setattr("app.cad.dxf_parser.ezdxf_bbox.extents", lambda entities: EmptyExtents())
    entities = parse_dxf(_drawing_bytes())

    assert entities
    assert any(entity["bbox"] is None and "bounding_box_unavailable" in entity["extraction_warnings"] for entity in entities)


def test_region_renderer_returns_an_inspectable_image():
    image = render_region(
        [{"id": "text_1", "entity_type": "TEXT", "source_text": "SPEC", "geometry": {"kind": "text", "point": [10, 10]}}],
        [0, 0, 20, 20],
    )

    assert image.startswith(b"<svg")
    assert b"SPEC" in image
    assert b'<g fill="#111827"' in image


def test_region_renderer_keeps_short_strokes_inside_table():
    image = render_region(
        [{"id": "stroke", "entity_type": "LINE", "bbox": [9, 9, 11, 11], "geometry": {"kind": "line", "start": [9, 9], "end": [11, 11]}}],
        [0, 0, 20, 20],
    )

    assert b'<line ' in image


def test_region_renderer_keeps_line_crossing_region_boundary():
    image = render_region(
        [{"id": "crossing", "entity_type": "LINE", "bbox": [-10, 10, 10, 10], "geometry": {"kind": "line", "start": [-10, 10], "end": [10, 10]}}],
        [0, 0, 20, 20],
    )

    assert b'<line ' in image


def test_region_renderer_converts_svg_to_png():
    image = render_region_png(
        [{"id": "text_1", "entity_type": "TEXT", "source_text": "SPEC", "geometry": {"kind": "text", "point": [10, 10]}}],
        [0, 0, 20, 20],
        max_dimension=400,
    )

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    rendered = Image.open(__import__("io").BytesIO(image)).convert("RGB")
    assert sum(pixel != (255, 255, 255) for pixel in rendered.getdata()) > 0