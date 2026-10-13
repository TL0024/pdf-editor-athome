PDFeditorAthome v1.0.2
================================

System requirements
-------------------
- Windows 10 or Windows 11, 64-bit
- A modern web browser
- No Python installation is required

Start PDFeditorAthome
---------------
1. Double-click PDFeditorAthome.exe.
2. PDFeditorAthome opens http://127.0.0.1:5050 in your default browser.
3. Close the editor tab when you are finished. After the last editor tab closes,
   the local server stops and its console window closes automatically.
4. You can also close the console window directly to stop the application.

Privacy
-------
PDFeditorAthome listens only on 127.0.0.1. Imported documents and page previews are
processed locally and held in memory while the application is running.

Windows warning
---------------
This executable is not Authenticode code-signed. Windows SmartScreen may
therefore display "Unknown publisher". Verify PDFeditorAthome.exe against the SHA-256
value in SHA256SUMS.txt before running it.

Export and save
---------------
Word exports contain editable paragraphs and detected native tables. Pictures,
drawings and scanned wording remain images; OCR is not included. Complex Word
layouts may reflow. PDF exports preserve original PDF page sizes and vector artwork.
Save a .pdfeditorathome project to retain editable objects for the next session.
Exporting PDF, Word or an image does not clear the unsaved-project indicator.

Third-party credits
-------------------
PDFeditorAthome is built with Flask and Werkzeug, PyMuPDF, python-docx, Pillow,
Beautiful Soup and PyInstaller. THIRD_PARTY.md contains project links, licenses and
credits for the runtime, build and quality tools used by this release.
