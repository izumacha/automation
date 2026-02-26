# AGENTS.md

## Cursor Cloud specific instructions

This is a single-file Python tkinter GUI reminder application (`reminder.py`). There are no backend services, databases, or containers to start.

### System dependencies

- `python3-tk` must be installed (`sudo apt-get install -y python3-tk`) for tkinter to work.
- `xvfb` is pre-installed in the cloud VM for headless GUI testing.

### Running the app

The app requires a display. In the headless cloud VM, use Xvfb:

```bash
Xvfb :99 -screen 0 1280x720x24 &
DISPLAY=:99 python3 reminder.py
```

### Running tests

```bash
xvfb-run python3 -m pytest tests -v
```

Tests mock tkinter objects so they work headlessly, but `import tkinter` still requires a display server. Using `xvfb-run` ensures the display is available.

### Linting

No linter is configured in the repository. Standard Python linting tools (e.g. `ruff`, `flake8`) can be used ad hoc.

### Key gotchas

- `python` is not on PATH; always use `python3`.
- pip installs to `~/.local/bin` which may not be on PATH; use `python3 -m pytest` instead of bare `pytest`.
- The app uses `cairosvg` for SVG-to-PNG icon conversion; it degrades gracefully if unavailable but is included in `requirements.txt`.
