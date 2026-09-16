from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.cad.dxf_parser import parse_dxf
from app.cad.storage import UploadedDrawing, drawings

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, str]:
    content = await file.read()
    upload_id = str(uuid4())
    filename = file.filename or "drawing.dxf"
    try:
        entities = parse_dxf(content)
    except Exception as error:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid DXF drawing.") from error

    drawings[upload_id] = UploadedDrawing(filename=filename, entities=entities)
    return {"upload_id": upload_id, "filename": filename, "status": "received"}
