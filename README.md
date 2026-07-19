# PDFeditorAthome

PDFeditorAthome is a local-first document editor for Windows. It opens PDF, DOCX, text, Markdown, HTML and common image files, converts supported text into editable objects, and exports the result as PDF, DOCX, PNG or JPG.

## Features

- Edit selectable text extracted from PDFs and supported document formats.
- Add and edit text boxes, pen strokes and highlights.
- Drag-select multiple objects, move them together and resize from the top-right handle.
- Hold Ctrl while resizing to preserve proportions.
- Copy and paste selected objects or clone the current page when nothing is selected.
- Add, duplicate, reorder and delete pages.
- Export selectable PDF text and vector drawings.
- Save editable `.pdfeditorathome` project files.

## Windows release

Download the latest package from [GitHub Releases](https://github.com/TL0024/pdf-editor-athome/releases). Extract the ZIP, double-click `PDFeditorAthome.exe`, and keep its console window open while using the editor. Close the console window to stop the local server.

The packaged application supports 64-bit Windows 10 and Windows 11 and does not require Python. The v1.0.0 executable is not Authenticode code-signed, so Windows may display an unknown-publisher warning. Verify the executable against the included `SHA256SUMS.txt` before running it.

## Run from source

Python 3.11 or later is recommended.

```powershell
python -m pip install -r requirements.txt
python app.py
```

Alternatively, double-click `run.bat`. The editor is available at <http://127.0.0.1:5050>.

## Editing controls

- **Text:** Double-click imported or newly added text to edit it. Select the Text tool and click empty page space to add another box.
- **Select:** Drag over empty page space to select multiple objects. Shift-click adds or removes an object from the selection. Ctrl+A selects every object on the current page.
- **Move:** Drag any selected object to move the entire selection.
- **Resize:** Drag the top-right handle. Hold Ctrl to preserve proportions; release Ctrl for independent width and height resizing.
- **Copy and paste:** Ctrl+C and Ctrl+V operate on selected objects. With no selection, they copy and insert the current page immediately afterward.
- **Delete:** Delete removes selected objects. With no selection, it removes the current page.
- **Drawing:** Use Pen or Highlight and drag over the page.
- **Erase:** Select Erase and click a text box or stroke.
- **Undo and redo:** Ctrl+Z and Ctrl+Shift+Z.

## Import and export behavior

Selectable PDF text and text from DOCX, TXT, Markdown and HTML files becomes editable text. Images, lines and other page artwork remain in the page layer. Image-only or scanned PDFs require OCR before their wording can be edited.

PDF exports retain selectable text and vector drawings. DOCX and image exports preserve the visual page result. Save a `.pdfeditorathome` project when you want to continue editing its objects later.

## Build the Windows release

Run:

```powershell
.\build_release.bat
```

The script creates an isolated `.build-venv`, installs the pinned packages from `requirements-release.txt`, builds `PDFeditorAthome.exe`, creates a SHA-256 checksum and assembles `PDFeditorAthome-v1.0.0-windows-x64.zip`. Generated `build`, `dist` and `release` directories are ignored by git; compiled artifacts are distributed through GitHub Releases rather than committed to `main`.

See [Building and releasing](docs/BUILDING.md) for the complete release procedure and [User guide](docs/USER_GUIDE.md) for usage details.

## Test

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Local processing

PDFeditorAthome listens only on `127.0.0.1`. Imported pages and document previews are processed locally, held in memory while the application runs, and discarded when the process stops.
