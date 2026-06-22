"""
Domain routers for the tasksquatch REST surface.

Each module exposes a :class:`fastapi.APIRouter` named ``router`` that
:func:`tasksquatch.rest.app.create_app` mounts under ``/api/v1``.
Surfaces consume the same ``core/services`` API the CLI uses; routes
here are thin parse/dispatch/serialize layers.
"""
