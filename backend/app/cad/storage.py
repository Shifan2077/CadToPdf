from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UploadedDrawing:
    filename: str
    entities: list[dict[str, object]]


drawings: dict[str, UploadedDrawing] = {}