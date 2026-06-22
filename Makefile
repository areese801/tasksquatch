.PHONY: help install test lint format typecheck run clean migrate migrate-revision

help:
	@echo "tasksquatch — available make targets:"
	@echo "  install            Install the package and dev dependencies (editable)"
	@echo "  test               Run the test suite with pytest"
	@echo "  lint               Run ruff in lint mode"
	@echo "  format             Run ruff format on the codebase"
	@echo "  typecheck          Run mypy against src/"
	@echo "  run                Show the tasksquatch CLI --help"
	@echo "  migrate            Run 'alembic upgrade head' against TASKSQUATCH_DB"
	@echo "  migrate-revision   Autogenerate a new revision: make migrate-revision MSG=\"add foo\""
	@echo "  clean              Remove build artifacts and tool caches"

install:
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install -e ".[dev]"; \
	else \
		pip install -e ".[dev]"; \
	fi

test:
	pytest -q

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src

run:
	tasksquatch --help

migrate:
	alembic upgrade head

migrate-revision:
	@if [ -z "$(MSG)" ]; then \
		echo "Usage: make migrate-revision MSG=\"short description\""; \
		exit 2; \
	fi
	alembic revision --autogenerate -m "$(MSG)"

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
