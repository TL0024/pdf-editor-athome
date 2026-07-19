# Static analysis and CI

Every pull request and push to `main` runs two GitHub Actions workflows.

## Static analysis workflow

- Pytest and branch coverage on Python 3.11, 3.12, and 3.13, with a 70% minimum.
- Ruff linting and formatting checks.
- Mypy static type analysis.
- djLint HTML template linting.
- codespell documentation and source checks.
- Vulture high-confidence dead-code detection.
- pip-audit checks against the pinned release dependency set.
- Bandit Python security checks.
- Project-local Semgrep rules for dangerous Python and JavaScript APIs.
- Zizmor auditing of GitHub Actions permissions and definitions.

The Semgrep rules intentionally live at [`.semgrep.yml`](../.semgrep.yml) in the repository root. They are shared by the workflow and local commands, while `.github/workflows` is reserved for GitHub Actions workflow definitions.

## Windows package workflow

The Windows workflow runs the tests, builds the PyInstaller executable, starts it without opening a browser, verifies its health endpoint and home page, and uploads the executable, ZIP, and checksum as a temporary workflow artifact.

## Run the checks locally

Use an isolated environment:

```powershell
python -m venv .quality-venv
python -m venv .security-venv
.\.quality-venv\Scripts\python.exe -m pip install -r requirements-quality.txt
.\.security-venv\Scripts\python.exe -m pip install -r requirements-security.txt
.\.quality-venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=term-missing
.\.quality-venv\Scripts\ruff.exe check .
.\.quality-venv\Scripts\ruff.exe format --check .
.\.quality-venv\Scripts\mypy.exe app.py tests
.\.quality-venv\Scripts\djlint.exe templates --lint
.\.quality-venv\Scripts\codespell.exe
.\.quality-venv\Scripts\vulture.exe app.py --min-confidence 90
.\.security-venv\Scripts\pip-audit.exe --strict --requirement requirements-release.txt
.\.security-venv\Scripts\bandit.exe --quiet --recursive --configfile pyproject.toml app.py
.\.security-venv\Scripts\semgrep.exe scan --config .semgrep.yml --error --metrics=off app.py static/app.js
.\.security-venv\Scripts\zizmor.exe --min-severity medium .github/workflows
```

Run `build_release.bat`, followed by `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_test_release.ps1`, to reproduce the Windows packaging gate.
