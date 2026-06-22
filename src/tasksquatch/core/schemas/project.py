"""
Pydantic v2 schemas for the :class:`~tasksquatch.core.models.Project`
entity.

The Update schema has every field as ``Optional`` because the REST
layer interprets PATCH semantics: any field the caller does not send
must be left untouched. Clients distinguish "field omitted" from
"field set to null" via :pyattr:`pydantic.BaseModel.model_fields_set`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectRead(BaseModel):
    """
    Read-side view of a project, suitable for REST and MCP responses.
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: str
    name: str
    position: int
    is_inbox: bool
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    """
    Payload for creating a project.

    ``position`` is optional; the service layer assigns a default
    position when omitted.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1)
    position: int | None = None


class ProjectUpdate(BaseModel):
    """
    PATCH-style payload for updating a project.

    All fields are optional. Use
    :pyattr:`pydantic.BaseModel.model_fields_set` to distinguish a
    field the caller omitted from a field the caller explicitly set to
    ``None`` — the service layer needs that distinction to honor PATCH
    semantics (omitted fields are untouched; explicit ``null`` would
    clear a column, where allowed).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1)
    position: int | None = None
