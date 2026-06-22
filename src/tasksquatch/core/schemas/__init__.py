"""
Pydantic v2 DTOs for the tasksquatch core layer.

Each entity gets a Read / Create / Update triple. Schemas are designed
to be consumed by surface boundaries — primarily the REST API and the
MCP server — so they hide the SQLAlchemy ORM rows behind plain
``model_validate`` and explicit conversion helpers. ``core`` itself
still trades in ORM objects internally; schemas are the *outward*
contract.
"""

from __future__ import annotations

from tasksquatch.core.schemas.activity import ActivityRead
from tasksquatch.core.schemas.comment import (
    CommentCreate,
    CommentRead,
    CommentUpdate,
)
from tasksquatch.core.schemas.label import LabelCreate, LabelRead, LabelUpdate
from tasksquatch.core.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from tasksquatch.core.schemas.task import TaskCreate, TaskRead, TaskUpdate

__all__ = [
    "ActivityRead",
    "CommentCreate",
    "CommentRead",
    "CommentUpdate",
    "LabelCreate",
    "LabelRead",
    "LabelUpdate",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "TaskCreate",
    "TaskRead",
    "TaskUpdate",
]
