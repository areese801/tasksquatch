"""
Initial-data seeding helpers for tasksquatch core.

Currently only the Inbox is seeded. The Inbox is the default project a
task lands in when the user does not specify one; the application
guarantees exactly one Inbox row at any time via a partial unique
index in the :mod:`tasksquatch.core.models.project` model.

This module is invoked by both :func:`tasksquatch.core.db.init_schema`
callers (in tests and in the eventual ``tasksquatch init`` CLI
command) and by Alembic migrations once TSQ-16 lands. Both pathways
end up calling :func:`ensure_inbox` against an open session; the
function is idempotent, so it is safe to invoke on every startup.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core.models import Project

INBOX_NAME = "Inbox"


def ensure_inbox(session: Session) -> Project:
    """
    Return the Inbox project, creating it if it does not yet exist.

    The Inbox is identified by ``is_inbox = True``. If a row with that
    flag already exists it is returned untouched; otherwise a new
    :class:`Project` is inserted with ``name=INBOX_NAME``,
    ``is_inbox=True``, and ``position=0`` so the Inbox sorts above any
    user-created project that uses the default ``position`` of 1000.

    The caller owns the transaction — this function neither commits
    nor rolls back. It does flush, so the returned row has its
    primary key populated.

    :param session: An open SQLAlchemy session.
    :returns: The singleton Inbox :class:`Project`.
    """
    existing = session.execute(
        select(Project).where(Project.is_inbox.is_(True)).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    inbox = Project(name=INBOX_NAME, is_inbox=True, position=0)
    session.add(inbox)
    session.flush()
    return inbox
