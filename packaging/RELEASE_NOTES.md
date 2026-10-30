# PDFeditorAthome v1.0.2

- Upgrade Pillow to 13.0 to satisfy the existing release dependency-security gate.

- Verify Python 3.14 support and build the Windows release with Python 3.14.

- Word export now produces editable paragraphs, formatted runs and native tables instead of page screenshots.
- DOCX tables retain empty cells and horizontal or vertical merges; grid tables in PDFs and tables in HTML are reconstructed.
- DOCX pictures and text emphasis survive import and export.
- PDF exports retain original page dimensions and non-text vector artwork.
- Long text exports no longer disappear when their text box is too short; long imported paragraphs are paginated.
- Fixes project validation, background cache expiry, redo loss on a click, editing badges, font resizing, single-point strokes and transparent images.
- Version 2 projects embed PDF artwork and page scales and remain portable between sessions. Version 1 projects remain readable.
- Exporting a single image or another output format no longer marks the editable project as saved.
- Adds backend and JavaScript behavior regression tests.

OCR, interactive form editing, secure redaction, digital signing and full Acrobat parity remain outside the implemented feature set. Rotated text is retained in the original artwork layer. Complex Word layouts can reflow.

# PDFeditorAthome v1.0.1

First public Windows release of the local-first PDF and document editor.

## Highlights

- Imports PDF, DOCX, text, Markdown, HTML and common image files.
- Converts supported document text into editable objects.
- Adds editable text, pen strokes and highlights.
- Supports marquee multi-selection, grouped movement and resizing.
- Copies selected objects or duplicates complete pages with Ctrl+C and Ctrl+V.
- Exports PDF, DOCX, PNG and JPG.
- Saves editable `.pdfeditorathome` project files.
- Runs as a standalone 64-bit Windows executable without a Python installation.
- Stops the local server and console automatically after the last editor browser tab closes.
- Updates Flask and Pillow to audited, supported releases.
- Adds multi-version tests, type checking, linting, formatting, dead-code detection, dependency auditing, Python and JavaScript security rules, and GitHub Actions hardening checks.
- Builds and smoke-tests the Windows executable in CI before publishing it.
- Includes third-party library and tool credits in the release package.

The executable is not Authenticode code-signed. Confirm its SHA-256 value using the attached checksum file before running it.
