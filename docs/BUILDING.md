# Building and releasing PDFeditorAthome

## Requirements

- 64-bit Windows 10 or Windows 11
- Python 3.11 or later
- Internet access for the first dependency installation

## Source checks

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m py_compile app.py
```

## Reproducible Windows build

Run `build_release.bat` from the repository root. It performs these steps:

1. Creates `.build-venv` when it does not exist.
2. Installs the pinned dependencies in `requirements-release.txt`.
3. Runs PyInstaller using `PDFeditorAthome.spec`.
4. Embeds `packaging/assets/pdf-editor-at-home.ico` and Windows v1.0.0 metadata.
5. Creates `PDFeditorAthome.exe`, the release README and `SHA256SUMS.txt`.
6. Creates `PDFeditorAthome-v1.0.0-windows-x64.zip`.

Build output is written under `build`, `dist` and `release`. These directories are excluded from source control.

## Standalone smoke test

The executable supports two environment variables for automated checks:

- `PDFEDITORATHOME_PORT` selects a non-default local port.
- `PDFEDITORATHOME_NO_BROWSER=1` prevents automatic browser launch.

A release check should confirm the health endpoint, home page, static JavaScript, a document import and the executable checksum before publishing.

## GitHub release

Commit source and packaging definitions to `main`. Upload the following generated files to the GitHub Release tagged `v1.0.0`:

- `PDFeditorAthome.exe`
- `PDFeditorAthome-v1.0.0-windows-x64.zip`
- `SHA256SUMS.txt`

Do not commit compiled release artifacts to `main`.
