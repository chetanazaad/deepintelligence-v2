from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import analyze_router, expansion_router, goals_router, health_router, intelligence_router, research_router, evaluation_router, assessment_router, validation_router
from database.config import get_settings
from database.session import create_tables

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup() -> None:
    create_tables()


app.include_router(analyze_router)
app.include_router(health_router)
app.include_router(intelligence_router)
app.include_router(expansion_router)
app.include_router(research_router)
app.include_router(goals_router)
app.include_router(evaluation_router)
app.include_router(assessment_router)
app.include_router(validation_router)


