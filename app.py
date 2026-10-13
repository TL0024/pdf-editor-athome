from __future__ import annotations

import base64
import io
import math
import os
import re
import sys
import threading
import time
import uuid
import webbrowser
from collections import OrderedDict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import fitz
from bs4 import BeautifulSoup
from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Pt, RGBColor
from flask import Flask, Response, jsonify, render_template, request, send_file
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageOps
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.serving import BaseWSGIServer, make_server

APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_VERSION = (APP_ROOT / "VERSION").read_text(encoding="utf-8").strip()
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_CACHED_DOCUMENTS = 8
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp"}
PAGE_SIZE = (1240, 1754)  # A4 at approximately 150 dpi
MAX_PAGE_PIXELS = 25_000_000
MAX_DOCUMENT_PAGES = 500
BROWSER_HEARTBEAT_TIMEOUT_SECONDS = 90.0
BROWSER_CLOSE_GRACE_SECONDS = 1.5
BROWSER_SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,128}")

app = Flask(
    __name__,
    static_folder=str(APP_ROOT / "static"),
    template_folder=str(APP_ROOT / "templates"),
)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# This app is intentionally local-first. Imported page previews stay in memory and
# are dropped as older documents are opened.
_documents: OrderedDict[str, dict[str, Any]] = OrderedDict()


class BrowserLifecycleMonitor:
    """Track open editor pages so the local server can follow their lifecycle."""

    def __init__(
        self,
        heartbeat_timeout: float = BROWSER_HEARTBEAT_TIMEOUT_SECONDS,
        close_grace: float = BROWSER_CLOSE_GRACE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.heartbeat_timeout = heartbeat_timeout
        self.close_grace = close_grace
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[float, int]] = {}
        self._last_sequences: dict[str, int] = {}
        self._ever_connected = False
        self._empty_since: float | None = None

    def heartbeat(self, session_id: str, sequence: int) -> None:
        with self._lock:
            if sequence <= self._last_sequences.get(session_id, -1):
                return
            self._last_sequences[session_id] = sequence
            self._sessions[session_id] = (self._clock(), sequence)
            self._ever_connected = True
            self._empty_since = None

    def disconnect(self, session_id: str, sequence: int) -> None:
        with self._lock:
            if sequence <= self._last_sequences.get(session_id, -1):
                return
            self._last_sequences[session_id] = sequence
            self._sessions.pop(session_id, None)
            self._ever_connected = True
            if not self._sessions:
                self._empty_since = self._clock()

    def should_shutdown(self) -> bool:
        with self._lock:
            now = self._clock()
            expired = [
                session_id
                for session_id, (last_seen, _sequence) in self._sessions.items()
                if now - last_seen >= self.heartbeat_timeout
            ]
            for session_id in expired:
                del self._sessions[session_id]

            if self._sessions or not self._ever_connected:
                self._empty_since = None
                return False
            if self._empty_since is None:
                self._empty_since = now
                return False
            return now - self._empty_since >= self.close_grace


def _browser_session() -> tuple[str, int] | None:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None
    session_id = payload.get("sessionId")
    sequence = payload.get("sequence")
    if not isinstance(session_id, str) or not BROWSER_SESSION_ID_PATTERN.fullmatch(session_id):
        return None
    if type(sequence) is not int or not 0 <= sequence <= 2_147_483_647:
        return None
    return session_id, sequence


def _font_file_path(
    bold: bool = False,
    italic: bool = False,
    family: str = "sans",
) -> Path | None:
    family = family.lower()
    if "calibri" in family:
        windows_name = (
            "calibriz.ttf"
            if bold and italic
            else "calibrib.ttf"
            if bold
            else "calibrii.ttf"
            if italic
            else "calibri.ttf"
        )
        linux_name = (
            "DejaVuSans-BoldOblique.ttf"
            if bold and italic
            else "DejaVuSans-Bold.ttf"
            if bold
            else "DejaVuSans-Oblique.ttf"
            if italic
            else "DejaVuSans.ttf"
        )
        linux_folder = "dejavu"
    elif "mono" in family or "consol" in family or "courier" in family:
        windows_name = (
            "consolaz.ttf"
            if bold and italic
            else "consolab.ttf"
            if bold
            else "consolai.ttf"
            if italic
            else "consola.ttf"
        )
        linux_name = (
            "DejaVuSansMono-BoldOblique.ttf"
            if bold and italic
            else "DejaVuSansMono-Bold.ttf"
            if bold
            else "DejaVuSansMono-Oblique.ttf"
            if italic
            else "DejaVuSansMono.ttf"
        )
        linux_folder = "dejavu"
    elif ("serif" in family and "sans-serif" not in family) or "times" in family or "georgia" in family:
        windows_name = (
            "timesbi.ttf" if bold and italic else "timesbd.ttf" if bold else "timesi.ttf" if italic else "times.ttf"
        )
        linux_name = (
            "DejaVuSerif-BoldItalic.ttf"
            if bold and italic
            else "DejaVuSerif-Bold.ttf"
            if bold
            else "DejaVuSerif-Italic.ttf"
            if italic
            else "DejaVuSerif.ttf"
        )
        linux_folder = "dejavu"
    else:
        windows_name = (
            "arialbi.ttf" if bold and italic else "arialbd.ttf" if bold else "ariali.ttf" if italic else "arial.ttf"
        )
        linux_name = (
            "DejaVuSans-BoldOblique.ttf"
            if bold and italic
            else "DejaVuSans-Bold.ttf"
            if bold
            else "DejaVuSans-Oblique.ttf"
            if italic
            else "DejaVuSans.ttf"
        )
        linux_folder = "dejavu"
    candidates = [
        Path("C:/Windows/Fonts") / windows_name,
        Path("/usr/share/fonts/truetype") / linux_folder / linux_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _font(
    size: int,
    bold: bool = False,
    italic: bool = False,
    family: str = "sans",
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = _font_file_path(bold, italic, family)
    if font_path:
        return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def _png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def _remember_document(
    name: str,
    pages: list[bytes],
    dimensions: list[tuple[int, int]],
    pdf_backgrounds: list[bytes] | None = None,
) -> str:
    document_id = uuid.uuid4().hex
    _documents[document_id] = {
        "name": name,
        "pages": pages,
        "dimensions": dimensions,
        "created": time.time(),
        "pdfPages": pdf_backgrounds or [],
    }
    _documents.move_to_end(document_id)
    while len(_documents) > MAX_CACHED_DOCUMENTS:
        _documents.popitem(last=False)
    return document_id


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: int,
) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    width = max(width, 1)
    for source_line in text.expandtabs(4).split("\n"):
        line = ""
        for token in re.findall(r"\s+|\S+", source_line):
            if line and draw.textlength(line + token, font=font) > width:
                lines.append(line.rstrip())
                line = ""
                token = token.lstrip()
            for character in token:
                if line and draw.textlength(line + character, font=font) > width:
                    lines.append(line)
                    line = ""
                line += character
        lines.append(line.rstrip())
    return lines or [""]


def _iter_docx_blocks(document: DocumentObject) -> Iterable[dict[str, Any]]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            style = (paragraph.style.name if paragraph.style else "") or ""
            yield {"type": "paragraph", "text": paragraph.text, "style": style, "runs": _docx_runs(paragraph)}
            for blip in child.xpath(".//a:blip"):
                relationship = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                if relationship and relationship in document.part.related_parts:
                    yield {"type": "image", "data": document.part.related_parts[relationship].blob}
            if child.xpath('.//w:br[@w:type="page"]'):
                yield {"type": "pageBreak"}
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            cells: dict[Any, dict[str, Any]] = {}
            for row_index, row in enumerate(table.rows):
                for column, cell in enumerate(row.cells, start=row.grid_cols_before):
                    if cell._tc in cells:
                        item = cells[cell._tc]
                        item["rowSpan"] = max(item["rowSpan"], row_index - item["row"] + 1)
                        item["columnSpan"] = max(item["columnSpan"], column - item["column"] + 1)
                    else:
                        cells[cell._tc] = {
                            "row": row_index,
                            "column": column,
                            "rowSpan": 1,
                            "columnSpan": 1,
                            "text": cell.text,
                            "runs": _docx_runs(cell.paragraphs[0]) if len(cell.paragraphs) == 1 else [],
                        }
            yield {"type": "table", "rows": rows, "cells": list(cells.values()), "columns": len(table.columns)}


def _docx_runs(paragraph: Any) -> list[dict[str, Any]]:
    runs = []
    for item in paragraph.iter_inner_content():
        for run in getattr(item, "runs", [item]):
            if not run.text:
                continue
            fonts = [run.font]
            for style in (run.style, paragraph.style):
                while style is not None:
                    fonts.append(style.font)
                    style = style.base_style

            def inherited(property_name: str, fonts: list[Any] = fonts) -> Any:
                return next(
                    (getattr(font, property_name) for font in fonts if getattr(font, property_name) is not None), None
                )

            font_size = inherited("size")
            runs.append(
                {
                    "text": run.text,
                    "bold": bool(inherited("bold")),
                    "italic": bool(inherited("italic")),
                    "underline": bool(inherited("underline")),
                    "fontFamily": inherited("name"),
                    "fontSize": font_size.pt / (72 / 150) if font_size else None,
                    "color": f"#{run.font.color.rgb}" if run.font.color.rgb else None,
                }
            )
    return runs


def _text_annotation(
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: float,
    color: str = "#172033",
    bold: bool = False,
    italic: bool = False,
    font_family: str = "Arial, sans-serif",
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "type": "text",
        "source": "imported",
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(max(width, font_size), 2),
        "height": round(max(height, font_size * 1.25), 2),
        "text": text,
        "fontSize": round(font_size, 2),
        "fontFamily": font_family,
        "color": color,
        "opacity": 1,
        "bold": bold,
        "italic": italic,
        "cover": False,
    }


def _render_blocks(
    blocks: Iterable[dict[str, Any]],
) -> tuple[list[bytes], list[tuple[int, int]], list[list[dict[str, Any]]]]:
    page_width, page_height = PAGE_SIZE
    margin_x, margin_y = 105, 105
    usable_width = page_width - margin_x * 2
    images: list[Image.Image] = []
    page_annotations: list[list[dict[str, Any]]] = []
    image = Image.new("RGB", (1, 1), "white")
    draw = ImageDraw.Draw(image)
    y = margin_y

    def new_page() -> None:
        nonlocal image, draw, y
        if len(images) >= MAX_DOCUMENT_PAGES:
            raise ValueError(f"Documents are limited to {MAX_DOCUMENT_PAGES} pages.")
        image = Image.new("RGB", PAGE_SIZE, "white")
        draw = ImageDraw.Draw(image)
        y = margin_y
        images.append(image)
        page_annotations.append([])

    def ensure_space(required: int) -> None:
        if y + required > page_height - margin_y:
            new_page()

    new_page()
    for block in blocks:
        if block.get("type") == "pageBreak":
            new_page()
            continue
        if block.get("type") == "image":
            with Image.open(io.BytesIO(block["data"])) as source_image:
                artwork = ImageOps.exif_transpose(source_image).convert("RGBA")
                artwork.thumbnail((usable_width, page_height - margin_y * 2), Image.Resampling.LANCZOS)
                ensure_space(artwork.height)
                image.paste(artwork, (margin_x, y), artwork)
                y += artwork.height + 24
            continue
        if block.get("type") == "table":
            rows = block.get("rows") or []
            if not rows:
                continue
            column_count = block.get("columns") or max(len(row) for row in rows)
            if column_count > 100:
                raise ValueError("Tables with more than 100 columns are not supported.")
            cell_width = usable_width // max(column_count, 1)
            table_font = _font(21)
            table_id = uuid.uuid4().hex
            cells = block.get("cells") or [
                {"row": row_index, "column": column, "rowSpan": 1, "columnSpan": 1, "text": text}
                for row_index, row in enumerate(rows)
                for column, text in enumerate(row)
            ]
            for row_index, row in enumerate(rows):
                wrapped_cells = [
                    _wrap_text(draw, str(row[index]) if index < len(row) else "", table_font, cell_width - 20)
                    for index in range(column_count)
                ]
                row_height = max(48, max(len(lines) for lines in wrapped_cells) * 29 + 18)
                ensure_space(row_height)
                for cell in (cell for cell in cells if cell["row"] == row_index):
                    index = cell["column"]
                    left = margin_x + index * cell_width
                    right = left + cell["columnSpan"] * cell_width
                    draw.rectangle((left, y, right, y + row_height), outline="#cbd5e1", width=2)
                    annotation = _text_annotation(
                        str(cell["text"]),
                        left + 10,
                        y + 9,
                        right - left - 20,
                        row_height - 18,
                        21,
                        color="#1e293b",
                    )
                    annotation["table"] = {
                        "id": table_id,
                        "row": row_index,
                        "column": index,
                        "rows": len(rows),
                        "columns": column_count,
                        "rowSpan": cell["rowSpan"],
                        "columnSpan": cell["columnSpan"],
                        "bounds": [left, y, right, y + row_height],
                    }
                    annotation["runs"] = cell.get("runs", [])
                    page_annotations[-1].append(annotation)
                y += row_height
            y += 24
            continue

        text = str(block.get("text", ""))
        style = str(block.get("style", "")).lower()
        if not text.strip():
            y += 18
            continue
        if "title" in style:
            size, bold, spacing = 45, True, 28
        elif "heading 1" in style or block.get("level") == 1:
            size, bold, spacing = 36, True, 22
        elif "heading 2" in style or block.get("level") == 2:
            size, bold, spacing = 30, True, 18
        elif block.get("bullet"):
            size, bold, spacing = 23, False, 12
            text = f"•  {text}"
        else:
            size, bold, spacing = 23, False, 14
        runs = block.get("runs") or []
        if runs:
            size = max(run.get("fontSize") or size for run in runs)
        if len(runs) == 1:
            bold = runs[0].get("bold", bold)
        font = _font(round(size), bold)
        line_height = int(size * 1.45)
        lines = _wrap_text(draw, text, font, usable_width)
        required = len(lines) * line_height + spacing
        if required <= page_height - margin_y * 2:
            ensure_space(required)
        while lines:
            available_lines = int((page_height - margin_y - y) // line_height)
            if available_lines < 1:
                new_page()
                continue
            chunk, lines = lines[:available_lines], lines[available_lines:]
            annotation = _text_annotation(
                text if len(chunk) * line_height + spacing == required else "\n".join(chunk),
                margin_x,
                y,
                usable_width,
                len(chunk) * line_height,
                size,
                bold=bold,
            )
            if "title" in style:
                annotation["paragraphStyle"] = "Title"
            elif "heading" in style or block.get("level"):
                annotation["paragraphStyle"] = f"Heading {block.get('level') or style.rsplit(' ', 1)[-1]}"
            if runs and "".join(run["text"] for run in runs) == annotation["text"]:
                annotation["runs"] = runs
            page_annotations[-1].append(annotation)
            y += len(chunk) * line_height
            if lines:
                new_page()
        y += spacing

    return [_png_bytes(page) for page in images], [PAGE_SIZE for _ in images], page_annotations


def _pdf_text_family(flags: int, embedded_name: str = "") -> str:
    normalized = embedded_name.split("+")[-1].lower().replace("-", " ")
    if "calibri" in normalized:
        return "Calibri, Arial, sans-serif"
    if "aptos" in normalized:
        return "Aptos, Calibri, Arial, sans-serif"
    if "cambria" in normalized:
        return "Cambria, Georgia, serif"
    if "georgia" in normalized:
        return "Georgia, Times New Roman, serif"
    if "times" in normalized:
        return "Times New Roman, Times, serif"
    if "consol" in normalized or "courier" in normalized:
        return "Consolas, Courier New, monospace"
    if "arial" in normalized or "helvetica" in normalized:
        return "Arial, Helvetica, sans-serif"
    if flags & 8:
        return "Consolas, Courier New, monospace"
    if flags & 4:
        return "Times New Roman, Times, serif"
    return "Arial, Helvetica, sans-serif"


def _pdf_text_color(value: int) -> str:
    return f"#{int(value) & 0xFFFFFF:06x}"


def _editable_pdf_pages(
    payload: bytes,
    pdf_backgrounds: list[bytes] | None = None,
) -> tuple[list[bytes], list[tuple[int, int]], list[list[dict[str, Any]]]]:
    source = fitz.open(stream=payload, filetype="pdf")
    if source.needs_pass:
        source.close()
        raise ValueError("This PDF is password protected. Open an unlocked copy.")
    if source.page_count == 0:
        source.close()
        raise ValueError("This PDF has no pages.")
    if source.page_count > MAX_DOCUMENT_PAGES:
        source.close()
        raise ValueError(f"Documents are limited to {MAX_DOCUMENT_PAGES} pages.")

    pages: list[bytes] = []
    dimensions: list[tuple[int, int]] = []
    page_annotations: list[list[dict[str, Any]]] = []
    render_scale = 1.6
    matrix = fitz.Matrix(render_scale, render_scale)

    for pdf_page in source:
        if pdf_page.rect.width * pdf_page.rect.height * render_scale**2 > MAX_PAGE_PIXELS:
            source.close()
            raise ValueError("A PDF page exceeds the supported rendering size.")
        annotations: list[dict[str, Any]] = []
        redact_rects: list[fitz.Rect] = []
        text_data = pdf_page.get_text("dict")
        tables = pdf_page.find_tables().tables if not pdf_page.rotation else []
        table_cells = []
        for table in tables:
            table_id = uuid.uuid4().hex
            for row_index, row in enumerate(table.rows):
                for column, bbox in enumerate(row.cells):
                    if bbox is not None:
                        table_cells.append(
                            (
                                fitz.Rect(bbox),
                                {
                                    "id": table_id,
                                    "row": row_index,
                                    "column": column,
                                    "rows": table.row_count,
                                    "columns": table.col_count,
                                    "rowSpan": 1,
                                    "columnSpan": 1,
                                    "bounds": [round(value * render_scale, 2) for value in bbox],
                                },
                            )
                        )
        rotation_matrix = pdf_page.rotation_matrix
        for block in text_data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                # Keep text with unsupported orientation in its original vector layer.
                # Removing it and replacing it horizontally would damage the document.
                if pdf_page.rotation or tuple(line.get("dir", (1, 0))) != (1, 0):
                    continue
                for span in line.get("spans", []):
                    text = str(span.get("text", ""))
                    if not text:
                        continue
                    source_rect = fitz.Rect(span["bbox"])
                    display_rect = source_rect * rotation_matrix
                    display_rect.normalize()
                    display_origin = fitz.Point(span.get("origin", (source_rect.x0, source_rect.y1))) * rotation_matrix
                    flags = int(span.get("flags", 0))
                    alpha = max(0, min(int(span.get("alpha", 255)), 255)) / 255
                    annotation = _text_annotation(
                        text=text,
                        x=display_rect.x0 * render_scale,
                        y=display_rect.y0 * render_scale,
                        width=display_rect.width * render_scale + 2,
                        height=display_rect.height * render_scale,
                        font_size=float(span.get("size", 11)) * render_scale,
                        color=_pdf_text_color(int(span.get("color", 0))),
                        bold=bool(flags & 16),
                        italic=bool(flags & 2),
                        font_family=_pdf_text_family(flags, str(span.get("font", ""))),
                    )
                    annotation["opacity"] = round(alpha, 3)
                    annotation["baselineY"] = round(display_origin.y * render_scale, 2)
                    annotation["noWrap"] = True
                    for cell_rect, cell_spec in table_cells:
                        if cell_rect.contains(source_rect.tl + (source_rect.br - source_rect.tl) * 0.5):
                            annotation["table"] = cell_spec
                            break
                    annotations.append(annotation)
                    redact_rects.append(source_rect)

        for rect in redact_rects:
            pdf_page.add_redact_annot(rect, fill=None, cross_out=False)
        if redact_rects:
            pdf_page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )

        for cell_rect, cell_spec in table_cells:
            if not any(annotation.get("table") == cell_spec for annotation in annotations):
                annotation = _text_annotation(
                    "",
                    cell_rect.x0 * render_scale + 4,
                    cell_rect.y0 * render_scale + 4,
                    cell_rect.width * render_scale - 8,
                    cell_rect.height * render_scale - 8,
                    18,
                )
                annotation["table"] = cell_spec
                annotations.append(annotation)

        pixmap = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        if pdf_backgrounds is not None:
            with fitz.open() as background_pdf:
                background_pdf.insert_pdf(source, from_page=pdf_page.number, to_page=pdf_page.number)
                pdf_backgrounds.append(background_pdf.tobytes(garbage=4, deflate=True))
        pages.append(pixmap.tobytes("png"))
        dimensions.append((pixmap.width, pixmap.height))
        page_annotations.append(annotations)

    source.close()
    return pages, dimensions, page_annotations


def _document_to_pages(
    filename: str,
    payload: bytes,
    pdf_backgrounds: list[bytes] | None = None,
) -> tuple[list[bytes], list[tuple[int, int]], list[list[dict[str, Any]]]]:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return _editable_pdf_pages(payload, pdf_backgrounds)

    if extension == ".docx":
        document = Document(io.BytesIO(payload))
        return _render_blocks(_iter_docx_blocks(document))

    if extension in {".txt", ".md", ".markdown", ".html", ".htm"}:
        raw = payload.decode("utf-8", errors="replace")
        blocks: list[dict[str, Any]] = []
        if extension in {".html", ".htm"}:
            soup = BeautifulSoup(raw, "html.parser")
            for element in soup.find_all(["h1", "h2", "h3", "p", "li", "table"]):
                if element.find_parent("table"):
                    continue
                if element.name == "table":
                    rows = [
                        [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
                        for row in element.find_all("tr")
                    ]
                    blocks.append({"type": "table", "rows": rows})
                    continue
                text = element.get_text(" ", strip=True)
                if text:
                    blocks.append(
                        {
                            "type": "paragraph",
                            "text": text,
                            "level": 1 if element.name == "h1" else 2 if element.name in {"h2", "h3"} else None,
                            "bullet": element.name == "li",
                        }
                    )
        else:
            for line in raw.splitlines():
                if extension == ".txt":
                    blocks.append({"type": "paragraph", "text": line})
                    continue
                stripped = line.strip()
                level = 1 if stripped.startswith("# ") else 2 if stripped.startswith(("## ", "### ")) else None
                bullet = bool(re.match(r"^[-*+]\s+", stripped))
                stripped = re.sub(r"^#{1,3}\s+", "", stripped)
                stripped = re.sub(r"^[-*+]\s+", "", stripped)
                blocks.append({"type": "paragraph", "text": stripped, "level": level, "bullet": bullet})
        return _render_blocks(blocks)

    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        source_image = ImageOps.exif_transpose(Image.open(io.BytesIO(payload))).convert("RGBA")
        image = Image.new("RGB", source_image.size, "white")
        image.paste(source_image, mask=source_image.getchannel("A"))
        image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        return [_png_bytes(image)], [image.size], [[]]

    raise ValueError("That file format is not supported.")


def _parse_color(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    try:
        red, green, blue = ImageColor.getrgb(value or "#111827")[:3]
    except ValueError:
        red, green, blue = (17, 24, 39)
    return red, green, blue, max(0, min(alpha, 255))


def _resolve_background(page: dict[str, Any]) -> Image.Image:
    data_url = page.get("imageData")
    if isinstance(data_url, str) and data_url.startswith("data:image/"):
        encoded = data_url.split(",", 1)[1]
        image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
        if image.width * image.height > MAX_PAGE_PIXELS:
            raise ValueError("A page background exceeds the supported rendering size.")
        return image.convert("RGBA")

    document_id = str(page.get("documentId", ""))
    page_index = int(page.get("serverIndex", -1))
    cached = _documents.get(document_id)
    if not cached or page_index < 0 or page_index >= len(cached["pages"]):
        raise ValueError("A page background is no longer available. Reopen the source file and try again.")
    return Image.open(io.BytesIO(cached["pages"][page_index])).convert("RGBA")


def _resolve_pdf_background(page: dict[str, Any]) -> bytes | None:
    if page.get("pdfData"):
        return base64.b64decode(page["pdfData"], validate=True)
    cached = _documents.get(str(page.get("documentId", "")))
    page_index = page.get("serverIndex")
    if cached and isinstance(page_index, int) and 0 <= page_index < len(cached["pdfPages"]):
        return cached["pdfPages"][page_index]
    return None


def _render_annotations(annotations: list[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    """Expand unchanged Word runs into positioned text for PDF and image rendering."""
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for annotation in annotations:
        runs = annotation.get("runs") or []
        if (
            annotation.get("type") != "text"
            or annotation.get("cover")
            or not runs
            or "".join(run["text"] for run in runs) != annotation.get("text")
        ):
            yield annotation
            continue
        left = float(annotation.get("x", 0))
        top = float(annotation.get("y", 0))
        font_size = float(annotation.get("fontSize", 24))
        right = left + float(annotation.get("width", 280))
        cursor = left
        baseline = top + font_size * 0.9
        for run in runs:
            style = {**annotation, **{key: value for key, value in run.items() if value is not None}}
            size = max(float(style.get("fontSize", font_size)), 1)
            font = _font(
                round(size), bool(style.get("bold")), bool(style.get("italic")), str(style.get("fontFamily", "sans"))
            )
            for fragment in re.findall(r"\n|[^\S\n]+|\S+", run["text"]):
                fragment_width = measure.textlength(fragment, font=font) if fragment != "\n" else 0
                if fragment == "\n" or (cursor > left and cursor + fragment_width > right):
                    cursor = left
                    baseline += font_size * 1.25
                    if fragment.isspace():
                        continue
                if fragment:
                    yield {
                        **style,
                        "runs": [],
                        "text": fragment,
                        "x": cursor,
                        "y": baseline - size * 0.9,
                        "width": max(fragment_width, 1),
                        "height": size * 1.25,
                        "baselineY": baseline,
                        "noWrap": True,
                    }
                    cursor += fragment_width


def _compose_page(page: dict[str, Any]) -> Image.Image:
    image = _resolve_background(page)
    scale_x = image.width / max(float(page.get("width", image.width)), 1)
    scale_y = image.height / max(float(page.get("height", image.height)), 1)

    for annotation in _render_annotations(page.get("annotations", [])):
        overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        annotation_type = annotation.get("type")
        opacity = float(annotation.get("opacity", 1))
        alpha = int(max(0, min(opacity, 1)) * 255)
        color = _parse_color(str(annotation.get("color", "#111827")), alpha)
        if annotation_type == "text":
            text = str(annotation.get("text", ""))
            if not text:
                continue
            x = int(float(annotation.get("x", 0)) * scale_x)
            y = int(float(annotation.get("y", 0)) * scale_y)
            width = int(float(annotation.get("width", 280)) * scale_x)
            font_size = max(8, int(float(annotation.get("fontSize", 24)) * min(scale_x, scale_y)))
            font = _font(
                font_size,
                bool(annotation.get("bold")),
                bool(annotation.get("italic")),
                str(annotation.get("fontFamily", "sans")),
            )
            line_height = int(font_size * 1.25)
            if annotation.get("cover"):
                height = int(float(annotation.get("height", line_height * 1.25)) * scale_y)
                draw.rectangle((x, y, x + width, y + height), fill=(255, 255, 255, 255))
            if not annotation.get("noWrap") and annotation.get("source") != "imported":
                x += round(5 * scale_x)
                y += round(3 * scale_y)
                width = max(width - round(10 * scale_x), 1)
            for line in text.splitlines() or [text]:
                rendered_lines = [line] if annotation.get("noWrap") else _wrap_text(draw, line, font, width)
                for wrapped in rendered_lines:
                    if annotation.get("noWrap") and wrapped:
                        baseline = (
                            float(
                                annotation.get(
                                    "baselineY", annotation.get("y", 0) + annotation.get("fontSize", 24) * 0.9
                                )
                            )
                            * scale_y
                        )
                        draw.text(
                            (x, baseline + (y - int(float(annotation.get("y", 0)) * scale_y))),
                            wrapped,
                            fill=color,
                            font=font,
                            anchor="ls",
                        )
                    else:
                        draw.text((x, y), wrapped, fill=color, font=font, anchor="lt")
                    y += line_height
        elif annotation_type == "stroke":
            points = annotation.get("points") or []
            if not points:
                continue
            scaled_points = [(float(point[0]) * scale_x, float(point[1]) * scale_y) for point in points]
            line_width = max(1, int(float(annotation.get("lineWidth", 4)) * min(scale_x, scale_y)))
            if len(points) == 1:
                dot_x, dot_y = scaled_points[0]
                draw.ellipse(
                    (dot_x - line_width / 2, dot_y - line_width / 2, dot_x + line_width / 2, dot_y + line_width / 2),
                    fill=color,
                )
            else:
                draw.line(scaled_points, fill=color, width=line_width, joint="curve")
        image = Image.alpha_composite(image, overlay)

    return image.convert("RGB")


def _pdf_base_font_name(bold: bool, italic: bool) -> str:
    if bold and italic:
        return "hebi"
    if bold:
        return "hebo"
    if italic:
        return "heit"
    return "helv"


def _register_pdf_font(
    pdf_page: fitz.Page,
    annotation: dict[str, Any],
    font_cache: dict[tuple[str, bool, bool], str],
) -> str:
    family = str(annotation.get("fontFamily", "sans"))
    bold = bool(annotation.get("bold"))
    italic = bool(annotation.get("italic"))
    key = (family, bold, italic)
    if key in font_cache:
        return font_cache[key]

    font_path = _font_file_path(bold, italic, family)
    if font_path:
        font_name = f"PF{len(font_cache) + 1}"
        pdf_page.insert_font(fontname=font_name, fontfile=str(font_path))
    else:
        font_name = _pdf_base_font_name(bold, italic)
    font_cache[key] = font_name
    return font_name


def _page_scale(page: dict[str, Any]) -> float:
    cached = _documents.get(str(page.get("documentId", "")))
    default = 1 / 1.6 if page.get("pdfData") or (cached and cached["pdfPages"]) else 72 / 150
    return float(page.get("pointsPerPixel", default))


def _page_dimensions(page: dict[str, Any]) -> tuple[float, float]:
    pdf_background = _resolve_pdf_background(page)
    if pdf_background:
        with fitz.open(stream=pdf_background, filetype="pdf") as source:
            return source[0].rect.width, source[0].rect.height
    scale = _page_scale(page)
    return page["width"] * scale, page["height"] * scale


def _build_selectable_pdf(pages: list[dict[str, Any]]) -> bytes:
    pdf = fitz.open()

    for page_spec in pages:
        background = _resolve_background(page_spec).convert("RGB")
        source_width = max(float(page_spec.get("width", background.width)), 1)
        source_height = max(float(page_spec.get("height", background.height)), 1)
        page_width, page_height = _page_dimensions(page_spec)
        scale_x = page_width / source_width
        scale_y = page_height / source_height
        pdf_page = pdf.new_page(width=page_width, height=page_height)
        pdf_background = _resolve_pdf_background(page_spec)
        if pdf_background:
            with fitz.open(stream=pdf_background, filetype="pdf") as source_pdf:
                if source_pdf[0].get_contents():
                    pdf_page.show_pdf_page(pdf_page.rect, source_pdf, 0)
        else:
            pdf_page.insert_image(pdf_page.rect, stream=_png_bytes(background))
        font_cache: dict[tuple[str, bool, bool], str] = {}

        for annotation in _render_annotations(page_spec.get("annotations", [])):
            annotation_type = annotation.get("type")
            opacity = max(0, min(float(annotation.get("opacity", 1)), 1))
            red, green, blue, _alpha = _parse_color(str(annotation.get("color", "#111827")))
            color = (red / 255, green / 255, blue / 255)

            if annotation_type == "text":
                text = str(annotation.get("text", ""))
                if not text:
                    continue
                x = float(annotation.get("x", 0)) * scale_x
                y = float(annotation.get("y", 0)) * scale_y
                width = max(float(annotation.get("width", 280)) * scale_x, 1)
                height = max(float(annotation.get("height", 50)) * scale_y, 1)
                font_size = max(float(annotation.get("fontSize", 24)) * min(scale_x, scale_y), 1)
                if annotation.get("cover"):
                    pdf_page.draw_rect(
                        fitz.Rect(x, y, x + width, y + height),
                        color=(1, 1, 1),
                        fill=(1, 1, 1),
                        overlay=True,
                    )
                if not annotation.get("noWrap") and annotation.get("source") != "imported":
                    x += 5 * scale_x
                    y += 3 * scale_y
                    width = max(width - 10 * scale_x, 1)
                font_name = _register_pdf_font(pdf_page, annotation, font_cache)
                if annotation.get("noWrap"):
                    baseline = (
                        float(
                            annotation.get("baselineY", annotation.get("y", 0) + annotation.get("fontSize", 24) * 0.9)
                        )
                        * scale_y
                    )
                    pdf_page.insert_text(
                        fitz.Point(x, baseline),
                        text,
                        fontname=font_name,
                        fontsize=font_size,
                        color=color,
                        fill_opacity=opacity,
                        lineheight=1.15,
                        overlay=True,
                    )
                else:
                    # insert_textbox silently emits nothing if any part cannot fit.
                    # Lay out lines explicitly so a long edit never disappears in export.
                    layout_font = _font(
                        max(round(font_size / scale_x), 1),
                        bool(annotation.get("bold")),
                        bool(annotation.get("italic")),
                        str(annotation.get("fontFamily", "sans")),
                    )
                    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
                    lines = _wrap_text(measure, text, layout_font, round(width / scale_x))
                    glyph_top = layout_font.getbbox(lines[0] or "Ag", anchor="ls")[1]
                    pdf_page.insert_text(
                        fitz.Point(x, y - glyph_top * scale_y),
                        "\n".join(lines),
                        fontname=font_name,
                        fontsize=font_size,
                        lineheight=1.25,
                        color=color,
                        fill_opacity=opacity,
                        overlay=True,
                    )
            elif annotation_type == "stroke":
                points = annotation.get("points") or []
                if not points:
                    continue
                pdf_points = [fitz.Point(float(point[0]) * scale_x, float(point[1]) * scale_y) for point in points]
                if len(points) == 1:
                    pdf_page.draw_circle(
                        pdf_points[0],
                        max(float(annotation.get("lineWidth", 4)) * scale_x / 2, 0.25),
                        color=color,
                        fill=color,
                        fill_opacity=opacity,
                        stroke_opacity=opacity,
                    )
                    continue
                pdf_page.draw_polyline(
                    pdf_points,
                    color=color,
                    width=max(float(annotation.get("lineWidth", 4)) * min(scale_x, scale_y), 0.5),
                    lineCap=1,
                    lineJoin=1,
                    stroke_opacity=opacity,
                    overlay=True,
                )

    result = pdf.tobytes(garbage=4, deflate=True)
    pdf.close()
    return result


def _word_runs(paragraph: Any, annotations: list[dict[str, Any]], scale: float) -> None:
    previous: dict[str, Any] | None = None
    for annotation in sorted(annotations, key=lambda item: (round(item.get("baselineY", item["y"])), item["x"])):
        text = str(annotation.get("text", ""))
        if previous and text:
            same_line = abs(annotation["y"] - previous["y"]) < max(annotation["fontSize"], previous["fontSize"]) * 0.6
            gap = annotation["x"] - previous["x"] - previous["width"]
            if not same_line:
                paragraph.add_run("\n")
            elif (
                gap > annotation["fontSize"] * 0.15 and not text.startswith(" ") and not previous["text"].endswith(" ")
            ):
                paragraph.add_run(" ")
        styles = annotation.get("runs") or []
        if "".join(str(style.get("text", "")) for style in styles) != text:
            styles = [{"text": text}]
        for style in styles:
            run = paragraph.add_run(style["text"])
            run.bold = bool(style.get("bold", annotation.get("bold")))
            run.italic = bool(style.get("italic", annotation.get("italic")))
            run.underline = bool(style.get("underline", False))
            run.font.name = (
                str(style.get("fontFamily") or annotation.get("fontFamily", "Arial")).split(",")[0].strip(" '\"")
            )
            run.font.size = Pt(max(float(style.get("fontSize") or annotation.get("fontSize", 24)) * scale, 1))
            red, green, blue, _alpha = _parse_color(str(style.get("color") or annotation.get("color", "#111827")))
            run.font.color.rgb = RGBColor(red, green, blue)
        previous = annotation


def _word_artwork(page: dict[str, Any], background: Image.Image) -> list[dict[str, Any]]:
    """Keep artwork as separate figures, with editable table borders rebuilt in Word."""
    image = background.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    scale_x, scale_y = image.width / page["width"], image.height / page["height"]
    for annotation in page.get("annotations", []):
        table = annotation.get("table")
        if table:
            left, top, right, bottom = table["bounds"]
            draw.rectangle(
                (left * scale_x - 3, top * scale_y - 3, right * scale_x + 3, bottom * scale_y + 3), fill="white"
            )
    for annotation in page.get("annotations", []):
        if annotation["type"] != "stroke":
            continue
        points = [(x * scale_x, y * scale_y) for x, y in annotation.get("points", [])]
        if not points:
            continue
        opacity = annotation.get("opacity", 1)
        rgb = _parse_color(annotation.get("color", "#111827"))[:3]
        color = tuple(round(value * opacity + 255 * (1 - opacity)) for value in rgb)
        line_width = max(round(annotation.get("lineWidth", 4) * scale_x), 1)
        if len(points) == 1:
            x, y = points[0]
            draw.ellipse((x - line_width / 2, y - line_width / 2, x + line_width / 2, y + line_width / 2), fill=color)
        else:
            draw.line(points, fill=color, width=line_width, joint="curve")
    difference = ImageChops.difference(image, Image.new("RGB", image.size, "white"))
    mask = difference.convert("L").point(lambda value: 255 if value > 12 else 0)
    bounds = mask.getbbox()
    if not bounds:
        return []
    # Separate illustrations on rows of whitespace so text can flow around them.
    regions = []
    start = bounds[1]
    last_ink = start
    for y in range(start, bounds[3]):
        if mask.crop((bounds[0], y, bounds[2], y + 1)).getbbox():
            last_ink = y
        elif y - last_ink > 12:
            if start <= last_ink:
                region = mask.crop((0, start, image.width, last_ink + 1)).getbbox()
                if region:
                    crop = (region[0], start, region[2], last_ink + 1)
                    regions.append(
                        {"type": "image", "x": crop[0] / scale_x, "y": start / scale_y, "image": image.crop(crop)}
                    )
            start = y + 1
    if start <= last_ink:
        region = mask.crop((0, start, image.width, last_ink + 1)).getbbox()
        if region:
            regions.append(
                {
                    "type": "image",
                    "x": region[0] / scale_x,
                    "y": start / scale_y,
                    "image": image.crop((region[0], start, region[2], last_ink + 1)),
                }
            )
    return regions


def _build_editable_docx(pages: list[dict[str, Any]]) -> bytes:
    document = Document()
    normal = document.styles["Normal"]
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.15
    for page_index, page in enumerate(pages):
        background = _resolve_background(page)
        scale = _page_scale(page)
        section = document.sections[0] if page_index == 0 else document.add_section(WD_SECTION.NEW_PAGE)
        point_width, point_height = _page_dimensions(page)
        section.page_width, section.page_height = Pt(point_width), Pt(point_height)
        margin = min(25.2, page["width"] * scale * 0.08, page["height"] * scale * 0.08)
        section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Pt(margin)
        usable_width = page["width"] * scale - margin * 2
        usable_height = page["height"] * scale - margin * 2
        tables: dict[str, dict[str, Any]] = {}
        content = []
        for annotation in sorted(page.get("annotations", []), key=lambda item: (item.get("y", 0), item.get("x", 0))):
            if annotation["type"] != "text":
                continue
            table = annotation.get("table")
            if table:
                table_id = table["id"]
                if table_id not in tables:
                    tables[table_id] = {"type": "table", "x": annotation["x"], "y": annotation["y"], "items": []}
                    content.append(tables[table_id])
                tables[table_id]["items"].append(annotation)
            elif annotation.get("text"):
                # PDF spans on the same baseline become runs in one editable paragraph.
                previous = content[-1] if content else None
                if (
                    annotation.get("noWrap")
                    and previous
                    and previous["type"] == "text"
                    and previous.get("noWrap")
                    and abs(previous["y"] - annotation["y"]) < 2
                ):
                    previous["items"].append(annotation)
                else:
                    content.append(
                        {
                            "type": "text",
                            "x": annotation["x"],
                            "y": annotation["y"],
                            "noWrap": annotation.get("noWrap"),
                            "items": [annotation],
                        }
                    )
        content.extend(_word_artwork(page, background))
        for item in sorted(content, key=lambda item: (item["y"], item["x"])):
            if item["type"] == "text":
                annotation = item["items"][0]
                style = annotation.get("paragraphStyle", "Normal")
                paragraph = document.add_paragraph(style=style if style in document.styles else "Normal")
                paragraph.paragraph_format.keep_with_next = False
                paragraph.paragraph_format.space_before = Pt(3)
                paragraph.paragraph_format.left_indent = Pt(max(0, min(item["x"] * scale - margin, usable_width * 0.8)))
                _word_runs(paragraph, item["items"], scale)
            elif item["type"] == "table":
                items = item["items"]
                first_row = min(annotation["table"]["row"] for annotation in items)
                last_row = max(
                    annotation["table"]["row"] + annotation["table"].get("rowSpan", 1) for annotation in items
                )
                columns = max(annotation["table"]["columns"] for annotation in items)
                table_object = document.add_table(rows=last_row - first_row, cols=columns)
                table_object.style = "Table Grid"
                table_object.alignment = WD_TABLE_ALIGNMENT.LEFT
                table_object.autofit = False
                for column in table_object.columns:
                    column.width = Pt(usable_width / columns)
                grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
                for annotation in items:
                    cell = annotation["table"]
                    grouped.setdefault((cell["row"] - first_row, cell["column"]), []).append(annotation)
                for (row, column), annotations in grouped.items():
                    spec = annotations[0]["table"]
                    cell_object = table_object.cell(row, column)
                    row_span, column_span = spec.get("rowSpan", 1), spec.get("columnSpan", 1)
                    if row_span > 1 or column_span > 1:
                        cell_object = cell_object.merge(table_object.cell(row + row_span - 1, column + column_span - 1))
                    _word_runs(cell_object.paragraphs[0], annotations, scale)
                document.add_paragraph().paragraph_format.space_after = Pt(3)
            else:
                image = item["image"]
                image_scale = min(
                    scale, usable_width / image.width, max(usable_height - 18, usable_height * 0.8) / image.height
                )
                document.add_paragraph().add_run().add_picture(
                    io.BytesIO(_png_bytes(image)),
                    width=Pt(image.width * image_scale),
                    height=Pt(image.height * image_scale),
                )
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _validate_export_pages(pages: Any) -> None:
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_DOCUMENT_PAGES:
        raise ValueError(f"Provide between 1 and {MAX_DOCUMENT_PAGES} pages.")

    def number(value: Any, minimum: float, maximum: float) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and minimum <= value <= maximum
        )

    for page in pages:
        if not isinstance(page, dict) or not all(number(page.get(key), 1, 40_000) for key in ("width", "height")):
            raise ValueError("Each page needs valid width and height values.")
        if page["width"] * page["height"] > MAX_PAGE_PIXELS:
            raise ValueError("A page exceeds the supported rendering size.")
        if "pointsPerPixel" in page and not number(page["pointsPerPixel"], 0.05, 5):
            raise ValueError("Invalid page scale.")
        annotations = page.get("annotations", [])
        if not isinstance(annotations, list) or len(annotations) > 100_000:
            raise ValueError("Invalid annotation list.")
        for annotation in annotations:
            if not isinstance(annotation, dict) or annotation.get("type") not in {"text", "stroke"}:
                raise ValueError("Unsupported annotation.")
            for key in ("x", "y", "width", "height", "fontSize", "baselineY", "lineWidth", "opacity"):
                if key in annotation and not number(
                    annotation[key], -100_000 if key in {"x", "y", "baselineY"} else 0, 100_000
                ):
                    raise ValueError(f"Invalid annotation {key}.")
            if annotation["type"] == "text":
                for key, default in (("x", 0), ("y", 0), ("width", 280), ("height", 50), ("fontSize", 24)):
                    annotation.setdefault(key, default)
                if not isinstance(annotation.get("text", ""), str):
                    raise ValueError("Text annotations must contain text.")
                runs = annotation.get("runs", [])
                if not isinstance(runs, list) or any(
                    not isinstance(run, dict) or not isinstance(run.get("text"), str) for run in runs
                ):
                    raise ValueError("Invalid text formatting.")
                if any(run.get("fontSize") is not None and not number(run["fontSize"], 1, 1000) for run in runs):
                    raise ValueError("Invalid text formatting size.")
                table = annotation.get("table")
                if table:
                    if not isinstance(table, dict) or not isinstance(table.get("id"), str):
                        raise ValueError("Invalid table metadata.")
                    for key, maximum in (("rows", 10_000), ("columns", 100), ("rowSpan", 10_000), ("columnSpan", 100)):
                        if key in {"rows", "columns"} and key not in table:
                            raise ValueError("Invalid table dimensions.")
                        if type(table.get(key, 1)) is not int or not 1 <= table.get(key, 1) <= maximum:
                            raise ValueError("Invalid table dimensions.")
                    if table.get("rows", 1) * table.get("columns", 1) > 100_000:
                        raise ValueError("The table contains too many cells.")
                    for key, size, span in (("row", "rows", "rowSpan"), ("column", "columns", "columnSpan")):
                        if (
                            type(table.get(key)) is not int
                            or not 0 <= table[key] < table[size]
                            or table[key] + table.get(span, 1) > table[size]
                        ):
                            raise ValueError("Invalid table cell.")
                    bounds = table.get("bounds")
                    if (
                        not isinstance(bounds, list)
                        or len(bounds) != 4
                        or not all(number(value, -100_000, 100_000) for value in bounds)
                    ):
                        raise ValueError("Invalid table bounds.")
            else:
                points = annotation.get("points", [])
                if (
                    not isinstance(points, list)
                    or len(points) > 1_000_000
                    or not all(
                        isinstance(point, list)
                        and len(point) == 2
                        and all(number(value, -100_000, 100_000) for value in point)
                        for point in points
                    )
                ):
                    raise ValueError("Invalid stroke points.")


def _safe_download_name(value: str, extension: str) -> str:
    stem = Path(value or "edited-document").stem
    stem = re.sub(r"[^A-Za-z0-9 _.-]", "", stem).strip(" .") or "edited-document"
    return f"{stem}.{extension}"


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/import")
def import_document() -> Response | tuple[Response, int]:
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "Choose a file to open."}), 400
    extension = Path(upload.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify(
            {"error": "Unsupported file. Open a PDF, DOCX, text, Markdown, HTML, PNG, JPG, or WebP file."}
        ), 415
    payload = upload.read()
    if not payload:
        return jsonify({"error": "The selected file is empty."}), 400
    try:
        pdf_backgrounds: list[bytes] = []
        pages, dimensions, annotations = _document_to_pages(upload.filename, payload, pdf_backgrounds)
    except Exception as exc:
        app.logger.exception("Import failed")
        return jsonify({"error": f"Could not open this file: {exc}"}), 422

    document_id = _remember_document(upload.filename, pages, dimensions, pdf_backgrounds)
    return jsonify(
        {
            "documentId": document_id,
            "name": Path(upload.filename).stem,
            "sourceFormat": extension.lstrip("."),
            "pages": [
                {
                    "width": width,
                    "height": height,
                    "serverIndex": index,
                    "imageUrl": f"/api/documents/{document_id}/pages/{index}",
                    "annotations": annotations[index],
                    "pointsPerPixel": 1 / 1.6 if extension == ".pdf" else 72 / 150,
                    "pdfUrl": f"/api/documents/{document_id}/pdf/{index}" if pdf_backgrounds else None,
                }
                for index, (width, height) in enumerate(dimensions)
            ],
            "editableTextCount": sum(bool(item.get("text")) for items in annotations for item in items),
        }
    )


@app.get("/api/documents/<document_id>/pages/<int:page_index>")
def document_page(document_id: str, page_index: int) -> Response | tuple[Response, int]:
    cached = _documents.get(document_id)
    if not cached or page_index < 0 or page_index >= len(cached["pages"]):
        return jsonify({"error": "Page not found."}), 404
    _documents.move_to_end(document_id)
    return send_file(io.BytesIO(cached["pages"][page_index]), mimetype="image/png", max_age=3600)


@app.get("/api/documents/<document_id>/pdf/<int:page_index>")
def document_pdf_background(document_id: str, page_index: int) -> Response | tuple[Response, int]:
    cached = _documents.get(document_id)
    if not cached or not 0 <= page_index < len(cached["pdfPages"]):
        return jsonify({"error": "PDF background not found."}), 404
    _documents.move_to_end(document_id)
    return send_file(io.BytesIO(cached["pdfPages"][page_index]), mimetype="application/pdf", max_age=3600)


@app.post("/api/export")
def export_document() -> Response | tuple[Response, int]:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Provide a JSON object."}), 400
    pages = payload.get("pages") or []
    export_format = str(payload.get("format", "pdf")).lower()
    if not pages:
        return jsonify({"error": "There are no pages to export."}), 400
    if export_format not in {"pdf", "docx", "png", "jpg"}:
        return jsonify({"error": "Unsupported export format."}), 400
    try:
        _validate_export_pages(pages)
        if not isinstance(payload.get("name", ""), str):
            raise ValueError("The document name must be text.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        if export_format in {"png", "jpg"}:
            page_index = max(0, min(int(payload.get("pageIndex", 0)), len(pages) - 1))
            image = _compose_page(pages[page_index])
            output = io.BytesIO()
            if export_format == "jpg":
                image.save(output, format="JPEG", quality=94, optimize=True)
                mimetype = "image/jpeg"
            else:
                image.save(output, format="PNG", optimize=True)
                mimetype = "image/png"
            output.seek(0)
            return send_file(
                output,
                mimetype=mimetype,
                as_attachment=True,
                download_name=_safe_download_name(payload.get("name", ""), export_format),
            )

        output = io.BytesIO()
        if export_format == "pdf":
            output.write(_build_selectable_pdf(pages))
            mimetype = "application/pdf"
        else:
            output.write(_build_editable_docx(pages))
            mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        output.seek(0)
        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=_safe_download_name(payload.get("name", ""), export_format),
        )
    except Exception as exc:
        app.logger.exception("Export failed")
        return jsonify({"error": f"Could not export this document: {exc}"}), 422


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error: RequestEntityTooLarge) -> tuple[Response, int]:
    return jsonify({"error": "That file is larger than the 50 MB limit."}), 413


@app.get("/api/health")
def health() -> Response:
    return jsonify({"status": "ok"})


@app.post("/api/lifecycle/heartbeat")
def browser_heartbeat() -> tuple[Response, int] | Response:
    browser_session = _browser_session()
    if browser_session is None:
        return jsonify({"error": "A valid browser session and sequence are required."}), 400
    monitor = app.config.get("BROWSER_LIFECYCLE_MONITOR")
    if isinstance(monitor, BrowserLifecycleMonitor):
        monitor.heartbeat(*browser_session)
    return Response(status=204)


@app.post("/api/lifecycle/disconnect")
def browser_disconnect() -> tuple[Response, int] | Response:
    browser_session = _browser_session()
    if browser_session is None:
        return jsonify({"error": "A valid browser session and sequence are required."}), 400
    monitor = app.config.get("BROWSER_LIFECYCLE_MONITOR")
    if isinstance(monitor, BrowserLifecycleMonitor):
        monitor.disconnect(*browser_session)
    return Response(status=204)


def _stop_server_when_browser_closes(
    server: BaseWSGIServer,
    monitor: BrowserLifecycleMonitor,
    stop_event: threading.Event,
) -> None:
    while not stop_event.wait(0.25):
        if monitor.should_shutdown():
            print("The editor page was closed. Stopping PDFeditorAthome...")
            server.shutdown()
            return


def run_local_server(port: int, *, monitor_browser: bool = True) -> None:
    server = make_server("127.0.0.1", port, app, threaded=True)
    stop_event = threading.Event()
    lifecycle_thread: threading.Thread | None = None
    monitor: BrowserLifecycleMonitor | None = None

    if monitor_browser:
        monitor = BrowserLifecycleMonitor()
        app.config["BROWSER_LIFECYCLE_MONITOR"] = monitor
        lifecycle_thread = threading.Thread(
            target=_stop_server_when_browser_closes,
            args=(server, monitor, stop_event),
            daemon=True,
            name="browser-lifecycle-monitor",
        )
        lifecycle_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()
        if lifecycle_thread is not None:
            lifecycle_thread.join(timeout=1.0)
        if app.config.get("BROWSER_LIFECYCLE_MONITOR") is monitor:
            app.config.pop("BROWSER_LIFECYCLE_MONITOR", None)


if __name__ == "__main__":
    try:
        port = int(os.environ.get("PDFEDITORATHOME_PORT", "5050"))
    except ValueError:
        port = 5050
    if not 1 <= port <= 65535:
        port = 5050
    address = f"http://127.0.0.1:{port}"
    no_browser = os.environ.get("PDFEDITORATHOME_NO_BROWSER") == "1"
    if not no_browser:
        browser_timer = threading.Timer(1.0, webbrowser.open, args=(address,))
        browser_timer.daemon = True
        browser_timer.start()
    print(f"PDFeditorAthome v{APP_VERSION} is running at {address}")
    print("Close every editor tab, or this window, to stop the app.")
    run_local_server(port, monitor_browser=not no_browser)
