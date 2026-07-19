# PDFeditorAthome user guide

## Starting the application

For the Windows release, extract the release ZIP and run `PDFeditorAthome.exe`. Your default browser opens the editor automatically. Keep the accompanying console window open; closing it stops the application.

For source installations, run `run.bat` or `python app.py`, then open <http://127.0.0.1:5050>.

## Opening documents

Select **Open** or press Ctrl+O. Supported inputs are:

- PDF
- DOCX
- TXT, Markdown and HTML
- PNG, JPG, JPEG and WebP
- `.pdfeditorathome` editable projects

Selectable document text becomes editable objects. Scanned PDFs and image files do not contain selectable text and require OCR before their wording can be edited.

## Selecting and arranging objects

Choose **Select**, then:

- Click an object to select it.
- Shift-click to add or remove individual objects.
- Drag from empty page space to create a selection rectangle.
- Press Ctrl+A to select all objects on the page.
- Drag any selected object to move the selection.
- Drag the top-right selection handle to resize.
- Hold Ctrl during resize to preserve proportions.
- Press Delete to remove the selected objects.

When no objects are selected, Ctrl+C copies the current page, Ctrl+V inserts its copy after the current page, and Delete removes the current page.

## Editing text

Double-click a text object to edit it. Use the properties panel to control its font, size, emphasis, color, opacity, alignment and background covering. Background covering is useful when replacing wording that is part of an image layer.

## Drawing

Choose **Pen** or **Highlight**, then drag over the page. Select a completed stroke to move, resize, duplicate or remove it. Use **Erase** to remove an object with one click.

## Pages

Use the left page panel to select and reorder pages. The page controls can add a blank page, duplicate the current page or delete it. A document always retains at least one page.

## Saving editable work

Open **Export** and choose **PDFeditorAthome project** to download a `.pdfeditorathome` file. It preserves page images, editable text and drawing objects for a later session.

## Exporting

- **PDF:** All pages with selectable text and vector strokes.
- **DOCX:** All pages represented using their composed visual layout.
- **PNG/JPG:** The current page.
- **PDFeditorAthome project:** Editable project data for future work.

## Current limitations

- OCR is not included.
- Imported PDF text fidelity depends on the fonts and positioning data stored in the source PDF.
- DOCX export prioritizes page appearance rather than reconstructing the original Word document structure.
- Editing and re-exporting an already signed PDF does not preserve its original cryptographic signature.

## Release verification

The Windows executable is not currently Authenticode code-signed. Download it only from this project's GitHub Releases page and compare its SHA-256 digest with the attached `SHA256SUMS.txt` before running it:

```powershell
Get-FileHash -Algorithm SHA256 .\PDFeditorAthome.exe
```

The digest must exactly match the value published with the same release. See the [security policy](../SECURITY.md) to report a vulnerability privately.
