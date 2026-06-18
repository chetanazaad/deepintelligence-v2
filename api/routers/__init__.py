from api.routers.expansion import router as expansion_router
from api.routers.goals import router as goals_router
from api.routers.health import router as health_router
from api.routers.intelligence import router as intelligence_router
from api.routers.research import router as research_router

__all__ = ["health_router", "intelligence_router", "expansion_router", "research_router", "goals_router"]
