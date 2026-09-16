from math import isclose

from app.geometry.bbox import bounding_box_for_points
from app.detection.drawing_detector import DrawingDetector


def test_bounding_box_for_points():
    box = bounding_box_for_points([(0, 0), (3, 4), (-2, 1)])
    assert box == (-2.0, 0.0, 3.0, 4.0)


def test_draw_detector_selects_main_cluster():
    detector = DrawingDetector()
    entities = [
        {"id": "main1", "entity_type": "LINE", "bbox": (0, 0, 10, 10), "layer": "0"},
        {"id": "main2", "entity_type": "LINE", "bbox": (1, 1, 9, 9), "layer": "0"},
        {"id": "main3", "entity_type": "LINE", "bbox": (2, 2, 8, 8), "layer": "0"},
        {"id": "stray", "entity_type": "LINE", "bbox": (1000, 1000, 1010, 1010), "layer": "0"},
    ]
    result = detector.detect(entities)
    assert result["selected_cluster"] == "main"
    assert result["bbox"][0] <= 0
    assert result["bbox"][2] >= 10


def test_draw_detector_handles_sparse_drawings():
    detector = DrawingDetector()
    entities = [
        {"id": "single", "entity_type": "LINE", "bbox": (5, 5, 6, 6), "layer": "0"},
    ]
    result = detector.detect(entities)
    assert result["selected_cluster"] == "single"
    assert result["bbox"] == (5.0, 5.0, 6.0, 6.0)
