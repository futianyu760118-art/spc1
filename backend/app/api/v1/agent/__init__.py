from .admin_assistant import router as admin_assistant_router
from .routes import router

router.include_router(admin_assistant_router, prefix="/admin/assistant")

__all__ = ["router"]
