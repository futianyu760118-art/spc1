from .admin_assistant import router as admin_assistant_router
from .routes import router
from .skills import router as skills_router

router.include_router(admin_assistant_router, prefix="/admin/assistant")
router.include_router(skills_router)

__all__ = ["router"]
