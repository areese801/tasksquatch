"""
Pydantic v2 schemas for the :class:`~tasksquatch.core.models.Label`
entity.

Labels are intentionally tiny — a name and an id. They carry no
timestamps because the model itself does not.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LabelRead(BaseModel):
    """
    Read-side view of a label.
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: str
    name: str


class LabelCreate(BaseModel):
    """
    Payload for creating a label.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1)


class LabelUpdate(BaseModel):
    """
    PATCH-style payload for renaming a label.

    Only ``name`` is editable. Omit it to leave the row untouched.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1)
