from app.api.v1.system.backups import router as backups_router
from app.api.v1.system.ai_assistant import router as ai_assistant_router
from app.api.v1.system.execution_agent import router as execution_agent_router
from app.api.v1.system.execution_agents import router as execution_agents_router

__all__ = [
    "backups_router",
    "ai_assistant_router",
    "execution_agent_router",
    "execution_agents_router",
]
