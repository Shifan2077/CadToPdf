from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/generate-pdf")
async def generate_pdf() -> dict[str, str]:
    return {"status": "pdf_ready", "filename": "drawing.pdf"}
