from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# PHASE 2 — CURRENTLY DISABLED. The active application does not import this renderer.

def _transform(point: list[float], bounds: tuple[float, float, float, float], scale: float, left: float, bottom: float) -> tuple[float, float]:
    return (
        left + (point[0] - bounds[0]) * scale,
        bottom + (point[1] - bounds[1]) * scale,
    )


def _dimension_label(entity: dict[str, Any]) -> str:
    override = str(entity.get("text") or "").strip()
    if override and override != "<>":
        return override
    measurement = entity.get("measurement")
    if isinstance(measurement, (int, float)):
        return f"{measurement:.2f}".rstrip("0").rstrip(".")
    return "DIM"


def render_drawing_pdf(entities: list[dict[str, Any]], bounds: tuple[float, float, float, float]) -> bytes:
    page_width, page_height = landscape(A4)
    pdf_buffer = BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=(page_width, page_height))
    pdf.setTitle("CAD Drawing")

    left = 42.0
    bottom = 42.0
    top = page_height - 64.0
    right = page_width - 42.0
    width = max(bounds[2] - bounds[0], 1.0)
    height = max(bounds[3] - bounds[1], 1.0)
    scale = min((right - left) / width, (top - bottom) / height)

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left, page_height - 30.0, "CAD Drawing")
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(HexColor("#64748b"))
    pdf.drawRightString(right, page_height - 28.0, "Framed from detected primary drawing")
    pdf.setStrokeColor(HexColor("#cbd5e1"))
    pdf.rect(left, bottom, right - left, top - bottom)

    pdf.setStrokeColor(HexColor("#0f172a"))
    pdf.setFillColor(HexColor("#0f172a"))
    pdf.setLineWidth(0.8)

    for entity in entities:
        geometry = entity.get("geometry", {})
        kind = geometry.get("kind")
        if kind == "line":
            start = _transform(geometry["start"], bounds, scale, left, bottom)
            end = _transform(geometry["end"], bounds, scale, left, bottom)
            pdf.line(*start, *end)
        elif kind == "polyline" and geometry.get("points"):
            points = [_transform(point, bounds, scale, left, bottom) for point in geometry["points"]]
            path = pdf.beginPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            if geometry.get("closed"):
                path.close()
            pdf.drawPath(path)
        elif kind in {"circle", "arc"}:
            center = geometry["center"]
            radius = geometry["radius"] * scale
            x, y = _transform(center, bounds, scale, left, bottom)
            if kind == "circle":
                pdf.circle(x, y, radius)
            else:
                pdf.arc(x - radius, y - radius, x + radius, y + radius, geometry["start_angle"], geometry["end_angle"] - geometry["start_angle"])
        elif kind == "point":
            x, y = _transform(geometry["point"], bounds, scale, left, bottom)
            pdf.circle(x, y, 1.5, fill=1)
        elif kind == "text":
            x, y = _transform(geometry["point"], bounds, scale, left, bottom)
            pdf.setFont("Helvetica", 6)
            pdf.drawString(x, y, str(entity.get("text", ""))[:80])
            pdf.setFont("Helvetica", 8)
        elif entity.get("entity_type") == "DIMENSION" and entity.get("dimension_geometry"):
            pdf.setStrokeColor(HexColor("#2563eb"))
            pdf.setFillColor(HexColor("#2563eb"))
            for part in entity["dimension_geometry"]:
                if part["kind"] == "line":
                    start = _transform(part["start"], bounds, scale, left, bottom)
                    end = _transform(part["end"], bounds, scale, left, bottom)
                    pdf.line(*start, *end)
                elif part["kind"] == "text":
                    x, y = _transform(part["point"], bounds, scale, left, bottom)
                    pdf.setFont("Helvetica", 6)
                    pdf.drawCentredString(x, y, _dimension_label(entity)[:40])
            pdf.setStrokeColor(HexColor("#0f172a"))
            pdf.setFillColor(HexColor("#0f172a"))
        elif entity.get("entity_type") == "DIMENSION" and entity.get("bbox"):
            bbox = entity["bbox"]
            lower = _transform([bbox[0], bbox[1]], bounds, scale, left, bottom)
            upper = _transform([bbox[2], bbox[3]], bounds, scale, left, bottom)
            pdf.setStrokeColor(HexColor("#2563eb"))
            pdf.rect(lower[0], lower[1], upper[0] - lower[0], upper[1] - lower[1])
            pdf.setFillColor(HexColor("#2563eb"))
            pdf.setFont("Helvetica", 6)
            pdf.drawString(lower[0], upper[1] + 2, _dimension_label(entity)[:40])
            pdf.setStrokeColor(HexColor("#0f172a"))
            pdf.setFillColor(HexColor("#0f172a"))

    pdf.save()
    return pdf_buffer.getvalue()