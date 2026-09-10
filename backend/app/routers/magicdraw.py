from fastapi import APIRouter

from app.schemas import MagicDrawDiagramCatalogResponse, MagicDrawPublishRequest, MagicDrawPublishResponse
from app.services.magicdraw_adapter import MagicDrawAdapter


router = APIRouter(prefix="/magicdraw", tags=["magicdraw"])


@router.get("/status")
def magicdraw_status() -> dict:
    return MagicDrawAdapter().health_check()


@router.get("/diagram-catalog", response_model=MagicDrawDiagramCatalogResponse)
def latest_diagram_catalog() -> dict:
    return MagicDrawAdapter().latest_diagram_catalog()


@router.post("/publish", response_model=MagicDrawPublishResponse)
def publish_to_magicdraw(payload: MagicDrawPublishRequest) -> dict:
    return MagicDrawAdapter().publish_model(
        [item.model_dump() for item in payload.elements],
        [item.model_dump() for item in payload.relationships],
        payload.package_name,
        payload.diagram_views,
    )


@router.post("/save")
def save_magicdraw_project() -> dict:
    return MagicDrawAdapter().save_project()


@router.get("/current-model")
def read_magicdraw_current_model() -> dict:
    return MagicDrawAdapter().current_model()
