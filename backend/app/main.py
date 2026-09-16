from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_upload import router as upload_router
from app.api.routes_analysis import router as analysis_router
from app.api.routes_preview import router as preview_router
from app.api.routes_projects import router as projects_router

app = FastAPI(title="ARECON CAD Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(preview_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
# PDF generation is Phase 2 and intentionally not registered in the active app.


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
