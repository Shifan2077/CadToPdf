from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFont


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value.rstrip("px"))


def _points(value: str) -> list[tuple[float, float]]:
    values = value.replace(",", " ").split()
    return [(float(values[index]), float(values[index + 1])) for index in range(0, len(values), 2)]


def rasterize_svg(svg: bytes, *, max_dimension: int = 2400) -> bytes:
    """Convert the SVG emitted by the region renderer into a PNG image."""
    root = ElementTree.fromstring(svg)
    source_width = max(1, int(_number(root.get("width"), 2400)))
    source_height = max(1, int(_number(root.get("height"), 1600)))
    scale = min(1.0, max_dimension / max(source_width, source_height))
    width = max(1, int(source_width * scale))
    height = max(1, int(source_height * scale))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def scaled(point: tuple[float, float]) -> tuple[float, float]:
        return point[0] * scale, point[1] * scale

    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "line":
            draw.line([scaled((_number(element.get("x1")), _number(element.get("y1")))), scaled((_number(element.get("x2")), _number(element.get("y2"))))], fill="#111827", width=max(1, int(scale)))
        elif tag in {"polyline", "polygon"}:
            points = [scaled(point) for point in _points(element.get("points", ""))]
            if len(points) > 1:
                draw.line(points + ([points[0]] if tag == "polygon" else []), fill="#111827", width=max(1, int(scale)))
        elif tag == "circle":
            center = scaled((_number(element.get("cx")), _number(element.get("cy"))))
            radius = _number(element.get("r")) * scale
            draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline="#111827", width=max(1, int(scale)))
        elif tag == "text":
            point = scaled((_number(element.get("x")), _number(element.get("y"))))
            draw.text(point, "".join(element.itertext()), fill="#111827", font=ImageFont.load_default())

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


__all__ = ["rasterize_svg"]