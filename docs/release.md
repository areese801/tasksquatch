# Release procedure

This document is the recipe for cutting a `tasksquatch` release. It is
opinionated and assumes [`uv`](https://docs.astral.sh/uv/) for building
and publishing; substitute `python -m build` + `twine` if you prefer.

`tasksquatch` follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1. Cut the release

1. Ensure `git status` is clean and you're on `main`:

   ```bash
   git checkout main
   git pull --ff-only
   git status
   ```

2. Confirm CI parity locally:

   ```bash
   make test    # pytest -q
   make lint    # ruff check .
   ```

3. Bump the version in **both** of these to the release version (drop
   any `.devN` suffix):

   - `src/tasksquatch/__init__.py` — `__version__ = "X.Y.Z"`
   - `pyproject.toml` — `[project] version = "X.Y.Z"`

4. Move the new entry in `CHANGELOG.md` out of `Unreleased` (if you
   keep one) and stamp it with today's date (UTC) in `YYYY-MM-DD`
   form.

5. Open the bump PR:

   ```bash
   git switch -c chore/bump-vX.Y.Z
   git commit -am "chore: bump to vX.Y.Z"
   gh pr create --fill
   ```

   Merge it once green.

6. Pull the merged `main` and tag locally:

   ```bash
   git checkout main
   git pull --ff-only
   git tag vX.Y.Z
   ```

## 2. Build and verify the wheel

7. Build:

   ```bash
   uv build
   ```

   Two artifacts land in `dist/`:
   `tasksquatch-X.Y.Z-py3-none-any.whl` and `tasksquatch-X.Y.Z.tar.gz`.

8. Confirm the wheel contains the web assets — without these the Web UI
   and REST UI HTML break:

   ```bash
   unzip -l dist/tasksquatch-X.Y.Z-py3-none-any.whl \
     | grep -E 'tasksquatch/web/(static|templates)/'
   ```

   You should see at minimum:
   - `tasksquatch/web/static/htmx.min.js`
   - `tasksquatch/web/static/style.css`
   - `tasksquatch/web/templates/layout.html` (and the other Jinja2
     partials)

   If any are missing the packaging config is broken — fix
   `pyproject.toml` (see the `[tool.hatch.build.targets.wheel]` section
   and add a `force-include` block if hatchling fails to pick up the
   non-Python files) before publishing.

## 3. Pre-publish smoke test

Always smoke-test the wheel from a fresh, isolated environment before
publishing to PyPI. Run the wheel through `pipx` (which forces a clean
venv):

```bash
pipx install --force ./dist/tasksquatch-X.Y.Z-py3-none-any.whl
```

Then exercise each surface by eye:

- `tasksquatch --help` — CLI loads and lists the commands.
- `tasksquatch tui` — Textual app paints; quit with `q`.
- `tasksquatch web --port 18000` — visit
  <http://127.0.0.1:18000/ui> and confirm htmx + style.css load
  (network tab, no 404s) and that <http://127.0.0.1:18000/docs>
  renders.
- `tasksquatch-mcp < /dev/null` — server starts on stdio and exits
  cleanly on EOF.
- Add a task that's due in the past, then `tasksquatch notify` —
  confirm a real desktop banner fires (macOS / Linux / Windows).

If any of these regress, **abort the release** and investigate.

### 3a. External smoke + manual plans

Before publishing, run the external shell-driven smoke suite and walk
the human-driven plans for the surfaces automation cannot cover:

```bash
make smoke   # runs scripts/smoke-cli.sh, smoke-web.sh, smoke-mcp.sh
```

Then complete:

- [`test-plans/manual-tui-plan.md`](../test-plans/manual-tui-plan.md)
  — every Textual screen, keypress, and form.
- [`test-plans/manual-notify-plan.md`](../test-plans/manual-notify-plan.md)
  — a real desktop banner fires and dedups.

If any smoke script or plan regresses, **abort the release** and
investigate.

## 4. Publish

9. Authenticate. Either export the token or use a `.pypirc` per the uv
   docs:

   ```bash
   export UV_PUBLISH_TOKEN=<your-pypi-token>
   ```

10. Publish both artifacts:

    ```bash
    uv publish
    ```

11. Push the tag:

    ```bash
    git push origin vX.Y.Z
    ```

12. Cut the GitHub release. Either auto-generate notes or hand-write
    from the matching `CHANGELOG.md` entry:

    ```bash
    gh release create vX.Y.Z --generate-notes
    ```

## 5. Post-release housekeeping

- Bump `src/tasksquatch/__init__.py` and `pyproject.toml` to the next
  `X.Y.(Z+1).dev0` (or whichever pre-release marker fits) and open a
  follow-up PR so the next round of work has a clear version target.
- Add an empty `## [Unreleased]` section back to `CHANGELOG.md` if you
  use that convention.
