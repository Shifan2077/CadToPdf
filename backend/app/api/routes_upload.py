from __future__ import annotations

from uuid import uuid4
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile
from ezdxf import recover

from app.cad.dxf_parser import parse_dxf
from app.cad.storage import create_project, store_drawing

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, str]:
    content = await file.read()
    filename = file.filename or "drawing.dxf"
    try:
        entities = parse_dxf(content)
        document, _ = recover.read(BytesIO(content))
    except Exception as error:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid DXF drawing.") from error

    project = create_project("Legacy Upload")
    drawing = store_drawing(project, filename, content, entities, {"dxf_version": document.dxfversion})
    return {"upload_id": drawing.id, "filename": filename, "status": drawing.status}
