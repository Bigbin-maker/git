from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db, reset_runtime_state
from app.routers import chat, documents, health, impact, magicdraw, merge, requirements, simulation, sysml, validation


settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    if settings.reset_runtime_state_on_startup:
        reset_runtime_state(clear_knowledge=settings.reset_knowledge_on_startup)


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(requirements.router, prefix=settings.api_prefix)
app.include_router(sysml.router, prefix=settings.api_prefix)
app.include_router(magicdraw.router, prefix=settings.api_prefix)
app.include_router(impact.router, prefix=settings.api_prefix)
app.include_router(merge.router, prefix=settings.api_prefix)
app.include_router(validation.router, prefix=settings.api_prefix)
app.include_router(simulation.router, prefix=settings.api_prefix)
