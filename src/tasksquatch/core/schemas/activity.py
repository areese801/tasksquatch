"""
Pydantic v2 schema for the
:class:`~tasksquatch.core.models.ActivityLog` entity.

The activity log is read-only at the surface boundary — there is no
Create or Update schema because no surface writes activity rows
directly; only mutating services in ``core`` do.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ActivityRead(BaseModel):
    """
    Read-side view of an activity log entry.

    ``event_type`` is emitted as the string value of the underlying
    :class:`~tasksquatch.core.models.ActivityEventType` enum so the
    REST and MCP surfaces produce stable, human-readable strings
    regardless of how the enum is stored internally.
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: str
    task_id: str | None
    event_type: str
    detail: Mapping[str, Any]
    created_at: datetime
