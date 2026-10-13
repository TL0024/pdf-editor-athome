# PDFeditorAthome user guide

## Starting the application

For the Windows release, extract the release ZIP and run `PDFeditorAthome.exe`. Your default browser opens the editor automatically. The accompanying console window stays open while the local editor is running.

For source installations, run `run.bat` or `python app.py`, then open <http://127.0.0.1:5050>.

## Stopping the application

Close the editor's browser tab when you are finished. The local server and its console window stop automatically after the last editor tab closes. If more than one editor tab is open, the server remains available until all of them close. Refreshing the page does not stop the server because a short grace period lets the replacement page reconnect.

If a browser is terminated without sending its close notification, the heartbeat fallback stops the server after approximately 90 seconds. You can always stop it immediately by closing the console window or pressing Ctrl+C there.

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

Double-click a text object to edit it. Use the properties panel to control its size, bold emphasis, color, opacity and background covering. Background covering is useful when replacing wording that is part of an image layer; it is a visual cover and does not securely redact underlying content.

## Drawing

Choose **Pen** or **Highlight**, then drag over the page. Select a completed stroke to move, resize, duplicate or remove it. Use **Erase** to remove an object with one click.

## Pages

Use the left page panel to select and reorder pages. The page controls can add a blank page, duplicate the current page or delete it. A document always retains at least one page.

## Saving editable work

Open **Export** and choose **PDFeditorAthome project** to download a `.pdfeditorathome` file. It preserves page images, original PDF vector artwork, page sizes, table structure, editable text and drawing objects for a later session. Version 1 projects remain supported; new projects use version 2.

Exporting PDF, Word or a single image does not save the editor's project state. Save the project to clear **Unsaved changes**. Opening another file prompts before discarding unsaved work.

## Exporting

- **PDF:** All pages with selectable text and vector strokes. Imported PDF page sizes and non-text vector artwork are retained.
- **DOCX:** Editable paragraphs, styled text and native tables reconstructed from DOCX, HTML and detected PDF grids. Empty and merged Word cells are retained. Pictures and drawings are separate images. Word can reflow content, changing complex page layouts.
- **PNG/JPG:** The current page.
- **PDFeditorAthome project:** Editable project data for future work.

## Current limitations

- OCR is not included.
- Imported PDF text fidelity depends on the fonts and positioning data stored in the source PDF.
- PDF table detection works best with visible grid lines. Unrecognized tables remain editable text rather than native Word tables.
- Rotated and angled PDF text remains in the original artwork layer to preserve its orientation; it cannot yet be edited directly.
- Complex Word layouts, nested tables, headers, footers, footnotes and floating objects are not fully reconstructed.
- OCR, interactive form editing, secure redaction and digital signing are not included. This application does not yet provide Adobe Acrobat feature parity.
- Editing and re-exporting an already signed PDF does not preserve its original cryptographic signature.

## Release verification

The Windows executable is not currently Authenticode code-signed. Download it only from this project's GitHub Releases page and compare its SHA-256 digest with the attached `SHA256SUMS.txt` before running it:

```powershell
Get-FileHash -Algorithm SHA256 .\PDFeditorAthome.exe
```

The digest must exactly match the value published with the same release. See the [security policy](../SECURITY.md) to report a vulnerability privately.
