"""
Textual-based interactive terminal interface for tasksquatch.

The TUI is a sibling surface to the CLI, REST, and MCP layers: it
opens its own short-lived SQLAlchemy session against the core data
model and never talks to any other surface. See ``docs/spec.md`` §8
for the surface contract.
"""

from __future__ import annotations
