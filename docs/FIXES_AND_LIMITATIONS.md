# Export and editor audit for v1.0.2

Checked on 14 October 2026.

## Fixed

- Word export previously embedded a complete page screenshot. It now writes editable paragraphs, formatted runs and native tables, with artwork as separate pictures.
- Word tables retain empty cells and horizontal or vertical merges. PDF grid tables and HTML tables are reconstructed where their structure can be detected.
- Word pictures and inline emphasis were discarded during import. Pictures and supported run formatting now survive.
- PDF exports changed imported physical page dimensions and rasterized page artwork. Original dimensions, including fractional sizes, and non-text vector artwork are retained.
- Long edits could disappear completely because the PDF text box did not fit. Lines are now rendered explicitly. Long imported paragraphs paginate.
- Plain text imports incorrectly stripped Markdown markers. TXT content is now retained literally.
- Transparent image imports could acquire a black background. Images now composite onto white and respect EXIF orientation.
- Single-point strokes were invisible in exports, and overlapping translucent strokes did not blend correctly. Both are fixed.
- Clicking without dragging cleared redo history. Movement and resize history now start with an actual change.
- Selection badges could enter edited text. Badges are removed before editing, and text input uses plain text.
- Font size changes did not update imported text baselines or bounds. These values now scale together.
- Invalid projects could partially replace a document. Projects are validated and page images decoded before committing the replacement.
- Malformed formatting and table cells in projects are rejected before replacing the current document.
- Document pagination now compresses completed previews immediately rather than retaining full bitmap pages. Fonts too large to fit on a page return a clear import error.
- Cache eviction could make open documents impossible to export. Imports embed their previews and PDF backgrounds in the browser; version 2 projects preserve them between sessions.
- Exporting a PNG incorrectly marked all project work as saved. Only saving the editor project clears the unsaved indicator.
- Invalid export payloads could crash routes. Shape, geometry, page limits, stroke points and table metadata are validated with JSON error responses.
- The source launcher could open the browser before the server started. Browser startup is now managed by the application.

## Verification

- 41 backend regression tests pass, covering native Word content, table cells and merges, styled text, PDF dimensions, vector content, long text, validation, lifecycle and image handling.
- 14 JavaScript behavior checks execute the production editor script against a DOM fixture. These cover history, edits, project restoration, portable imports, save status and copying table text.
- Ruff, format checks, Mypy, djLint, codespell, Vulture, Bandit, Git diff checks and offline Zizmor checks pass.
- The rebuilt Windows executable passes health, home-page, import and editable Word export smoke checks.
- A PDF rendering containing styled text and table content was visually reviewed.
- Live browser interaction was unavailable in this session. JavaScript behavior checks are not a replacement for live browser testing.
- A Word renderer was unavailable, so native Word content was checked structurally rather than visually. Complex layouts still need review in Word.
- Semgrep could not start because its Windows certificate-store initialization failed. The Linux CI scan remains configured.

## Remaining feature gaps

This release does not provide Adobe Acrobat feature parity, and an audit cannot guarantee that every bug has been found.

- OCR for scanned documents is not implemented.
- Interactive form editing, secure redaction, digital signing, encryption workflows and original signature preservation are not implemented.
- Rotated and angled PDF text remains in the original artwork layer to preserve its appearance. It is not yet directly editable.
- PDF table detection works best with visible grid lines; undetected table content exports as editable text.
- Word conversion reflows content. Complex layouts, nested tables, floating objects, headers, footers and footnotes are not fully reconstructed.
- Existing version 1 projects lack the new table and vector metadata. Reopen the original source document to obtain that information.
- Image-only Word exports created by older releases require the original document or OCR to recover editable wording.

See [the user guide](USER_GUIDE.md) for controls, save behavior and supported workflows.
