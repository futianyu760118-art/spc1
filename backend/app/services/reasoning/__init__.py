"""执行面推理服务（AEOS reason_control_platform 中台侧实现，任务书 2026-10 版）"""

from app.services.reasoning.service import (
    TASK_TYPES,
    ReasoningError,
    run_reasoning_task,
    cancel_task,
    get_task_view,
    running_count,
    new_task_id,
)
