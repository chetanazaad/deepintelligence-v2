from fastapi import FastAPI

from api.routers import health_router, intelligence_router
from database.config import get_settings
from database.session import create_tables

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

@app.on_event("startup")
def on_startup() -> None:
    create_tables()


app.include_router(health_router)
app.include_router(intelligence_router)
