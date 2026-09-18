from __future__ import annotations

import json
from io import BytesIO
from urllib.error import URLError

import pytest

from app.vision.ollama_client import OllamaClient, OllamaClientError, OllamaConfig
from app.vision.ollama_client import OllamaResult
from app.vision.service import analyze_region
from app.vision.validation import validate_visual_items


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_ollama_config_defaults_and_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test/")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3-vl:test")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "12")

    config = OllamaConfig.from_environment()

    assert config.base_url == "http://ollama.test"
    assert config.model == "qwen3-vl:test"
    assert config.timeout_seconds == 12.0


def test_ollama_client_sends_image_and_returns_raw_response():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return _Response({"model": "qwen3-vl:4b", "response": '{"items": []}'})

    result = OllamaClient(OllamaConfig(timeout_seconds=4), opener=opener).analyze_image(b"png", "prompt")

    assert result.raw_text == '{"items": []}'
    assert result.raw_response["model"] == "qwen3-vl:4b"
    assert requests[0][1] == 4
    assert "images" in json.loads(requests[0][0].data)


def test_ollama_client_reports_unavailable_service():
    def opener(request, timeout):
        raise URLError("connection refused")

    with pytest.raises(OllamaClientError, match="Could not reach Ollama"):
        OllamaClient(opener=opener).analyze_image(b"png", "prompt")


def test_validation_preserves_source_and_reports_all_statuses():
    entities = [
        {"id": "a", "source_handle": "1", "source_text": "143 X 57 X 1.6"},
        {"id": "b", "source_handle": "2", "source_text": "STILE EDGES"},
        {"id": "c", "source_handle": "3", "source_text": "MATERIAL: STEEL"},
    ]
    visual_items = [
        {"field": "dimension", "visual_value": "143 X 57 X 1.6", "relationship_confidence": 0.9},
        {"field": "conflict", "visual_value": "143 X 67 X 1.6", "relationship_confidence": 0.8},
        {"field": "unclear", "visual_value": "UNCLEAR", "relationship_confidence": 0.2},
        {"field": "new", "visual_value": "ALUMINUM", "relationship_confidence": 0.7},
    ]

    results = validate_visual_items(entities, visual_items)
    statuses = {result["status"] for result in results}
    conflict = next(result for result in results if result["status"] == "CONFLICT")

    assert {"MATCH", "CONFLICT", "UNCLEAR", "VISUAL_ONLY", "SOURCE_ONLY"} <= statuses
    assert conflict["source_value"] == "143 X 57 X 1.6"
    assert conflict["visual_value"] == "143 X 67 X 1.6"
    assert conflict["source"] == "ezdxf"


def test_region_service_renders_selected_region_and_preserves_conflict():
    drawing = type("Drawing", (), {
        "id": "drawing_1",
        "metadata": {"region_candidates": [{"id": "region_1", "bbox": [0, 0, 20, 20], "text_entity_ids": ["text_1"], "geometry_entity_ids": []}]},
        "entities": [{
            "id": "text_1",
            "source_handle": "A1",
            "entity_type": "TEXT",
            "source_text": "143 X 57 X 1.6",
            "normalized_text": "143 X 57 X 1.6",
            "bbox": [5, 5, 15, 7],
            "geometry": {"kind": "text", "point": [5, 7]},
            "coordinates": {"point": [5, 7, 0]},
        }],
    })()

    class Client:
        def analyze_image(self, image, prompt):
            assert image.startswith(b"\x89PNG")
            assert "143 X 57 X 1.6" in prompt
            return OllamaResult("qwen3-vl:4b", '{"items":[{"field":"FRAME/JAMB","visual_value":"143 X 67 X 1.6","relationship_confidence":0.8,"notes":"visible"}]}', {"response": "raw"}, 12)

    result = analyze_region(drawing, "region_1", Client())

    assert result["validation"][0]["source_value"] == "143 X 57 X 1.6"
    assert result["validation"][0]["visual_value"] == "143 X 67 X 1.6"
    assert result["validation"][0]["status"] == "CONFLICT"
    assert result["raw_model_response"] == {"response": "raw"}