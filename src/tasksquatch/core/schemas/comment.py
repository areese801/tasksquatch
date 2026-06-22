"""
Pydantic v2 schemas for the :class:`~tasksquatch.core.models.Comment`
entity.

A comment is a free-form note attached to a task. The Create payload
intentionally does not carry ``task_id``; the REST layer takes it from
the URL path.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentRead(BaseModel):
    """
    Read-side view of a comment.
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: str
    task_id: str
    body: str
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    """
    Payload for creating a comment on a task.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(..., min_length=1)


class CommentUpdate(BaseModel):
    """
    Payload for editing a comment's body.

    ``body`` is required; there is nothing else on a comment to update.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(..., min_length=1)
