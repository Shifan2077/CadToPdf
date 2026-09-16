from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, str]:
    return {"filename": file.filename or "unknown.dxf", "status": "received"}
