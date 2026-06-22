# Manual test plan — wheel install on a clean machine

**Goal.** Confirm the built wheel is self-contained — static assets
and templates ship inside it, the console scripts resolve outside the
dev venv, and the surfaces all come up against a scratch DB.

**Time budget.** ~10 minutes.

**Prereqs.** `uv` (or `python -m build`) and `pipx`.

## Steps

- [ ] Build the wheel:
      ```bash
      uv build
      # or: python -m build
      ```
- [ ] Inspect the wheel for the non-Python assets the Web UI depends
      on:
      ```bash
      unzip -l dist/tasksquatch-0.1.0-py3-none-any.whl \
        | grep -E "(htmx|style|template)"
      ```
      Expect `htmx.min.js`, `style.css`, and the `web/templates/*.html`
      partials. If any are missing, **stop** and fix the wheel
      packaging config before proceeding.
- [ ] Install the wheel in an isolated environment via `pipx` so the
      console scripts land outside the dev venv:
      ```bash
      pipx install dist/tasksquatch-0.1.0-py3-none-any.whl --force
      ```
- [ ] Confirm both console scripts resolve and report the right
      version:
      ```bash
      tasksquatch version
      tsq version          # the short alias
      ```
- [ ] Point at a scratch DB and exercise the surfaces:
      ```bash
      export TASKSQUATCH_DB=/tmp/wheel-test.db
      rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
      tsq add "wheel smoke"
      tsq list
      tsq web --port 18001
      # In another terminal: curl -sf http://127.0.0.1:18001/healthz
      ```
- [ ] Stop the web server (`Ctrl-C`).

## Cleanup

```bash
pipx uninstall tasksquatch
rm -f "$TASKSQUATCH_DB" "$TASKSQUATCH_DB"-wal "$TASKSQUATCH_DB"-shm
```
