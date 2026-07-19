# Third-party credits

PDFeditorAthome thanks the maintainers and contributors of the open-source projects below. The application has no third-party browser-side framework; its interface uses standard HTML, CSS and browser JavaScript APIs.

The license identifiers here describe the directly used packages and do not replace their license texts. Follow each project link for its authoritative copyright and license terms, especially when redistributing the application.

## Runtime libraries

- [Flask](https://flask.palletsprojects.com/) and [Werkzeug](https://werkzeug.palletsprojects.com/) by the Pallets community provide the local web application, HTTP routing and local WSGI server. Both use the BSD-3-Clause license.
- [PyMuPDF](https://pymupdf.readthedocs.io/) by Artifex and its contributors provides PDF reading, rendering, text extraction and PDF export. PyMuPDF is offered under the GNU Affero General Public License v3.0 or an Artifex commercial license.
- [python-docx](https://python-docx.readthedocs.io/) and its contributors provide DOCX import and export support under the MIT license.
- [Pillow](https://python-pillow.github.io/) and its contributors provide image decoding, composition and export under the MIT-CMU license.
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) by Leonard Richardson and its contributors provides HTML text extraction under the MIT license.

The exact release versions are recorded in [`requirements-release.txt`](https://github.com/TL0024/pdf-editor-athome/blob/main/requirements-release.txt). Development installs use the compatible ranges in [`requirements.txt`](https://github.com/TL0024/pdf-editor-athome/blob/main/requirements.txt).

## Build, test and quality tools

- [PyInstaller](https://pyinstaller.org/) creates the standalone Windows executable. It is licensed under GPL-2.0-or-later with the PyInstaller bootloader exception.
- [pytest](https://docs.pytest.org/), [pytest-cov](https://pytest-cov.readthedocs.io/), [Ruff](https://docs.astral.sh/ruff/), [Mypy](https://www.mypy-lang.org/), [djLint](https://djlint.com/), [codespell](https://github.com/codespell-project/codespell) and [Vulture](https://github.com/jendrikseipp/vulture) support tests and source-quality checks.
- [pip-audit](https://github.com/pypa/pip-audit), [Bandit](https://bandit.readthedocs.io/), [Semgrep](https://semgrep.dev/) and [Zizmor](https://docs.zizmor.sh/) support dependency, source and GitHub Actions security checks.

Python itself and the browser platform provide the standard-library and Web APIs used throughout the application. GitHub Actions hosts the project's automated test and release workflows.
