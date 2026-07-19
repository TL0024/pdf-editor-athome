# Building and releasing PDFeditorAthome

## Requirements

- 64-bit Windows 10 or Windows 11
- Python 3.11 or later
- Internet access for the first dependency installation

## Source checks

```powershell
python -m venv .quality-venv
python -m venv .security-venv
.\.quality-venv\Scripts\python.exe -m pip install -r requirements-quality.txt
.\.security-venv\Scripts\python.exe -m pip install -r requirements-security.txt
.\.quality-venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=term-missing
.\.quality-venv\Scripts\ruff.exe check .
.\.quality-venv\Scripts\ruff.exe format --check .
.\.quality-venv\Scripts\mypy.exe app.py tests
.\.security-venv\Scripts\pip-audit.exe --strict --requirement requirements-release.txt
python -m py_compile app.py
```

The full local command set and the purpose of every CI gate are documented in [Static analysis and CI](STATIC_ANALYSIS.md).

## Reproducible Windows build

Run `build_release.bat` from the repository root. It performs these steps:

1. Creates `.build-venv` when it does not exist.
2. Installs the pinned dependencies in `requirements-release.txt`.
3. Runs PyInstaller using `PDFeditorAthome.spec`.
4. Embeds `packaging/assets/pdf-editor-at-home.ico` and Windows v1.0.1 metadata.
5. Creates `PDFeditorAthome.exe`, the release README, third-party credits and `SHA256SUMS.txt`.
6. Creates `PDFeditorAthome-v1.0.1-windows-x64.zip`.

Build output is written under `build`, `dist` and `release`. These directories are excluded from source control.

## Standalone smoke test

The executable supports two environment variables for automated checks:

- `PDFEDITORATHOME_PORT` selects a non-default local port.
- `PDFEDITORATHOME_NO_BROWSER=1` prevents automatic browser launch and disables browser-lifecycle shutdown.

After building, run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke_test_release.ps1`. It starts the packaged executable in a hidden window, disables automatic browser launch and lifecycle monitoring, verifies the health endpoint and home page, and then stops the process. API tests cover document import, export and browser-session behavior; the build script creates the executable checksum.

## GitHub release

Merge source and packaging definitions into `main`, then create and push a tag matching `VERSION`. For v1.0.1:

```powershell
git tag -a v1.0.1 -m "PDFeditorAthome v1.0.1"
git push origin v1.0.1
```

The tag starts the release workflow. It reruns tests, builds and smoke-tests the executable, and creates the GitHub Release with:

- `PDFeditorAthome.exe`
- `PDFeditorAthome-v1.0.1-windows-x64.zip`
- `SHA256SUMS.txt`

Do not commit compiled release artifacts to `main`.
