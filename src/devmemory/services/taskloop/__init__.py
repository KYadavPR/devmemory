"""The state-aware coding loop.

``engine`` is the entry point: create a task, then ``refresh_state`` /
``get_state`` drive the loop. Collectors aggregate evidence (Git, Entire, tests,
optional Graph); ``requirements`` normalizes and evaluates requirements. Nothing
here decides *how* code is written - that stays with Antigravity.
"""

from devmemory.services.taskloop.engine import (
    TaskNotFoundError,
    create_task,
    get_checkpoint,
    get_state,
    get_task,
    latest_task,
    list_snapshots,
    list_tasks,
    mark_complete,
    refresh_state,
    report_issue,
    resolve_issue,
    set_requirement_status,
)

__all__ = [
    "TaskNotFoundError",
    "create_task",
    "get_checkpoint",
    "get_state",
    "get_task",
    "latest_task",
    "list_snapshots",
    "list_tasks",
    "mark_complete",
    "refresh_state",
    "report_issue",
    "resolve_issue",
    "set_requirement_status",
]
