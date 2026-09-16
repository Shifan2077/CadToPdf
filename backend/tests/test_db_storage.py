from app.db import DrawingRecord, ProjectRecord
from app.cad.storage import create_project, store_drawing


def test_project_and_drawing_are_persisted_to_db():
    project = create_project("DB Project")
    drawing = store_drawing(
        project,
        "sample.dxf",
        b"test-content",
        [{
            "id": "entity_1",
            "entity_type": "LINE",
            "layer": "0",
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "geometry": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        }],
        {"dxf_version": "R12", "units": "Millimeters"},
    )

    assert project.id.startswith("project_")
    assert drawing.id.startswith("drawing_")
    assert ProjectRecord.get_by_id(project.id) is not None
    assert DrawingRecord.get_by_id(drawing.id) is not None
    assert DrawingRecord.get_by_id(drawing.id).filename == "sample.dxf"
