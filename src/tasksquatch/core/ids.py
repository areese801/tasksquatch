"""
ID generation for tasksquatch core.

Two responsibilities live here: minting UUIDv7 primary keys and
allocating the monotonic, never-reused user-facing task ``number``.
"""

from __future__ import annotations

import uuid_utils
from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core.db import TaskNumberSeq


def new_id() -> str:
    """
    Mint a new UUIDv7 as a 36-character canonical string.

    UUIDv7 is time-ordered, so primary keys generated in close
    succession sort naturally by creation time without exposing a
    leakable counter.

    :returns: The canonical hyphenated string form of a fresh UUIDv7.
    """
    return str(uuid_utils.uuid7())


def allocate_task_number(session: Session) -> int:
    """
    Allocate the next user-facing task ``number`` and return it.

    On first call against an empty database, inserts the singleton
    row at ``id = 1`` with ``last_number = 0``. Every call thereafter
    increments ``last_number`` by one and returns the new value.

    The function does not commit — the caller owns the transaction
    boundary. The caller must, however, be running inside a
    transaction that took a write lock at BEGIN time (which the
    engine configured in :mod:`tasksquatch.core.db` does
    automatically via ``BEGIN IMMEDIATE``); otherwise concurrent
    allocators racing on the same database can produce duplicate or
    skipped numbers.

    :param session: An open SQLAlchemy session.
    :returns: The newly allocated number, always one greater than the
        previously allocated number.
    """
    # with_for_update() is a no-op on SQLite — it does not emit
    # SELECT ... FOR UPDATE — but we still ask for it so the intent
    # carries over verbatim if the backend ever changes. Safety against
    # concurrent allocators on SQLite comes from the engine's BEGIN
    # IMMEDIATE hook, which serializes writers at transaction start.
    stmt = select(TaskNumberSeq).with_for_update()
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        row = TaskNumberSeq(id=1, last_number=0)
        session.add(row)
        # Flush so the INSERT lands before the increment, ensuring the
        # row.last_number we read back is the one persisted in the DB.
        session.flush()

    row.last_number = row.last_number + 1
    session.flush()
    return row.last_number
