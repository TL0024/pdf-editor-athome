import base64
import io
import zipfile
from typing import Any, cast

import fitz
import pytest
from docx import Document
from flask.testing import FlaskClient
from PIL import Image, ImageChops

from app import BrowserLifecycleMonitor, app


def client() -> FlaskClient:
    app.config.update(TESTING=True)
    return app.test_client()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_browser_lifecycle_waits_for_every_session_to_close() -> None:
    clock = FakeClock()
    monitor = BrowserLifecycleMonitor(heartbeat_timeout=10, close_grace=2, clock=clock)

    assert monitor.should_shutdown() is False
    monitor.heartbeat("first-tab", 1)
    monitor.heartbeat("second-tab", 1)
    monitor.disconnect("first-tab", 2)
    clock.advance(3)
    assert monitor.should_shutdown() is False

    monitor.disconnect("second-tab", 2)
    clock.advance(1.9)
    assert monitor.should_shutdown() is False
    clock.advance(0.1)
    assert monitor.should_shutdown() is True


def test_browser_lifecycle_heartbeat_recovers_during_close_grace() -> None:
    clock = FakeClock()
    monitor = BrowserLifecycleMonitor(heartbeat_timeout=10, close_grace=2, clock=clock)

    monitor.heartbeat("refreshing-tab", 1)
    monitor.disconnect("refreshing-tab", 2)
    clock.advance(1)
    monitor.heartbeat("replacement-tab", 1)
    clock.advance(5)

    assert monitor.should_shutdown() is False


def test_browser_lifecycle_expires_an_abandoned_session() -> None:
    clock = FakeClock()
    monitor = BrowserLifecycleMonitor(heartbeat_timeout=10, close_grace=2, clock=clock)

    monitor.heartbeat("abandoned-tab", 1)
    clock.advance(10)
    assert monitor.should_shutdown() is False
    clock.advance(2)
    assert monitor.should_shutdown() is True


def test_browser_lifecycle_ignores_a_late_heartbeat_after_disconnect() -> None:
    clock = FakeClock()
    monitor = BrowserLifecycleMonitor(heartbeat_timeout=10, close_grace=2, clock=clock)

    monitor.heartbeat("closing-tab", 1)
    monitor.disconnect("closing-tab", 3)
    monitor.heartbeat("closing-tab", 2)
    clock.advance(2)

    assert monitor.should_shutdown() is True


def test_browser_lifecycle_endpoints_validate_and_update_sessions() -> None:
    clock = FakeClock()
    monitor = BrowserLifecycleMonitor(heartbeat_timeout=10, close_grace=0, clock=clock)
    app.config["BROWSER_LIFECYCLE_MONITOR"] = monitor
    test_client = client()
    try:
        assert test_client.post("/api/lifecycle/heartbeat", json={}).status_code == 400
        assert (
            test_client.post("/api/lifecycle/heartbeat", json={"sessionId": "editor-tab", "sequence": 1}).status_code
            == 204
        )
        assert (
            test_client.post("/api/lifecycle/disconnect", json={"sessionId": "editor-tab", "sequence": 2}).status_code
            == 204
        )
        assert monitor.should_shutdown() is True
    finally:
        app.config.pop("BROWSER_LIFECYCLE_MONITOR", None)


def import_text_page(test_client: FlaskClient) -> dict[str, Any]:
    response = test_client.post(
        "/api/import",
        data={"file": (io.BytesIO(b"# Sample document\n\nA paragraph for export."), "sample.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    return response.get_json()


def export_payload(imported: dict[str, Any], export_format: str) -> dict[str, Any]:
    page = imported["pages"][0]
    return {
        "name": "Edited sample",
        "format": export_format,
        "pageIndex": 0,
        "pages": [
            {
                "width": page["width"],
                "height": page["height"],
                "documentId": imported["documentId"],
                "serverIndex": page["serverIndex"],
                "annotations": [
                    *page.get("annotations", []),
                    {
                        "id": "text-1",
                        "type": "text",
                        "x": 120,
                        "y": 300,
                        "width": 400,
                        "height": 60,
                        "text": "Editable note",
                        "fontSize": 28,
                        "color": "#4f46e5",
                        "opacity": 1,
                        "bold": True,
                    },
                    {
                        "id": "stroke-1",
                        "type": "stroke",
                        "points": [[100, 420], [220, 460], [370, 430]],
                        "lineWidth": 8,
                        "color": "#e11d48",
                        "opacity": 0.8,
                    },
                ],
            }
        ],
    }


def test_home_and_health() -> None:
    test_client = client()
    home = test_client.get("/")
    assert home.status_code == 200
    assert b"PDFeditorAthome" in home.data
    assert test_client.get("/api/health").get_json() == {"status": "ok"}


def test_import_text_and_serve_page() -> None:
    test_client = client()
    imported = import_text_page(test_client)
    assert imported["sourceFormat"] == "md"
    assert len(imported["pages"]) == 1
    assert imported["editableTextCount"] == 2
    assert {item["text"] for item in imported["pages"][0]["annotations"]} == {
        "Sample document",
        "A paragraph for export.",
    }
    page_response = test_client.get(imported["pages"][0]["imageUrl"])
    assert page_response.status_code == 200
    image = Image.open(io.BytesIO(page_response.data))
    assert image.size == (1240, 1754)


def test_import_pdf() -> None:
    source = fitz.open()
    page = source.new_page(width=300, height=500)
    page.draw_rect(page.rect, color=(0.8, 0.9, 1), fill=(0.8, 0.9, 1))
    page.insert_text((50, 80), "PDF import", fontsize=18, color=(0.1, 0.2, 0.6))
    pdf_bytes = source.tobytes()
    source.close()

    response = client().post(
        "/api/import",
        data={"file": (io.BytesIO(pdf_bytes), "source.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["sourceFormat"] == "pdf"
    assert len(data["pages"]) == 1
    assert data["pages"][0]["height"] > data["pages"][0]["width"]
    assert data["editableTextCount"] == 1
    annotation = data["pages"][0]["annotations"][0]
    assert annotation["text"] == "PDF import"
    assert annotation["type"] == "text"
    assert annotation["source"] == "imported"
    assert annotation["noWrap"] is True
    assert annotation["baselineY"] > annotation["y"]
    assert "Arial" in annotation["fontFamily"]

    background_response = client().get(data["pages"][0]["imageUrl"])
    background = Image.open(io.BytesIO(background_response.data)).convert("RGB")
    left, top = int(annotation["x"]), int(annotation["y"])
    right = min(background.width, int(annotation["x"] + annotation["width"]))
    bottom = min(background.height, int(annotation["y"] + annotation["height"]))
    pixels = cast(list[tuple[int, int, int]], list(background.crop((left, top, right, bottom)).get_flattened_data()))
    assert pixels
    assert min(min(pixel) for pixel in pixels) > 180


def test_pdf_styled_runs_preserve_outer_spaces() -> None:
    source = fitz.open()
    page = source.new_page(width=500, height=200)
    x, baseline = 40, 80
    runs = [
        ("Regular trailing  ", "helv"),
        ("  Bold separated  ", "hebo"),
        ("  end", "helv"),
    ]
    for text, font_name in runs:
        page.insert_text((x, baseline), text, fontname=font_name, fontsize=16)
        x += fitz.get_text_length(text, fontname=font_name, fontsize=16)
    pdf_bytes = source.tobytes()
    source.close()

    response = client().post(
        "/api/import",
        data={"file": (io.BytesIO(pdf_bytes), "spaces.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    annotations = response.get_json()["pages"][0]["annotations"]
    assert [annotation["text"] for annotation in annotations] == [text for text, _font in runs]


def test_import_docx_text_is_editable() -> None:
    source = io.BytesIO()
    document = Document()
    document.add_heading("Editable Word heading", level=1)
    document.add_paragraph("Editable Word paragraph")
    document.save(source)
    source.seek(0)

    response = client().post(
        "/api/import",
        data={"file": (source, "editable.docx")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["editableTextCount"] == 2
    assert [item["text"] for item in data["pages"][0]["annotations"]] == [
        "Editable Word heading",
        "Editable Word paragraph",
    ]


def test_export_pdf_png_and_docx() -> None:
    test_client = client()
    imported = import_text_page(test_client)

    pdf_response = test_client.post("/api/export", json=export_payload(imported, "pdf"))
    assert pdf_response.status_code == 200
    exported_pdf = fitz.open(stream=pdf_response.data, filetype="pdf")
    assert exported_pdf.page_count == 1
    selectable_text = exported_pdf[0].get_text().replace("\xa0", " ")
    assert "Sample document" in selectable_text
    assert "A paragraph for export." in selectable_text
    assert "Editable note" in selectable_text
    assert len(exported_pdf[0].get_drawings()) >= 1
    exported_pdf.close()

    png_response = test_client.post("/api/export", json=export_payload(imported, "png"))
    assert png_response.status_code == 200
    exported_png = Image.open(io.BytesIO(png_response.data))
    assert exported_png.size == (1240, 1754)

    docx_response = test_client.post("/api/export", json=export_payload(imported, "docx"))
    assert docx_response.status_code == 200
    exported_docx = Document(io.BytesIO(docx_response.data))
    assert len(exported_docx.inline_shapes) == 1
    assert {paragraph.text for paragraph in exported_docx.paragraphs} >= {
        "Sample document",
        "A paragraph for export.",
        "Editable note",
    }
    assert next(paragraph for paragraph in exported_docx.paragraphs if paragraph.text == "Editable note").runs[0].bold


def test_added_text_alignment_matches_pdf_and_image_exports() -> None:
    background = Image.new("RGB", (600, 400), "white")
    background_buffer = io.BytesIO()
    background.save(background_buffer, format="PNG")
    image_data = "data:image/png;base64," + base64.b64encode(background_buffer.getvalue()).decode()
    annotation = {
        "id": "alignment-text",
        "type": "text",
        "x": 200,
        "y": 150,
        "width": 220,
        "height": 60,
        "text": "Hello alignment",
        "fontSize": 24,
        "fontFamily": "Arial, sans-serif",
        "color": "#000000",
        "opacity": 1,
        "bold": False,
        "italic": False,
        "cover": False,
    }
    payload = {
        "name": "alignment",
        "pageIndex": 0,
        "pages": [{"width": 600, "height": 400, "imageData": image_data, "annotations": [annotation]}],
    }
    test_client = client()
    png_response = test_client.post("/api/export", json={**payload, "format": "png"})
    pdf_response = test_client.post("/api/export", json={**payload, "format": "pdf"})
    assert png_response.status_code == 200
    assert pdf_response.status_code == 200

    png_image = Image.open(io.BytesIO(png_response.data)).convert("RGB")
    pdf = fitz.open(stream=pdf_response.data, filetype="pdf")
    pixmap = pdf[0].get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
    pdf_image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    pdf.close()
    white = Image.new("RGB", png_image.size, "white")
    png_box = ImageChops.difference(png_image, white).getbbox()
    pdf_box = ImageChops.difference(pdf_image, white).getbbox()
    assert png_box and pdf_box
    assert abs(pdf_box[0] - png_box[0]) <= 2
    assert abs(pdf_box[1] - png_box[1]) <= 2


def test_reject_unsupported_extension() -> None:
    response = client().post(
        "/api/import",
        data={"file": (io.BytesIO(b"not a presentation"), "slides.ppt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 415
    assert "Unsupported" in response.get_json()["error"]


def blank_export_page(width: int = 1240, height: int = 1754) -> dict[str, Any]:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return {
        "width": width,
        "height": height,
        "imageData": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
        "annotations": [],
    }


def import_bytes(content: bytes, name: str) -> dict[str, Any]:
    response = client().post(
        "/api/import", data={"file": (io.BytesIO(content), name)}, content_type="multipart/form-data"
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def imported_export_pages(imported: dict[str, Any]) -> list[dict[str, Any]]:
    return [{**page, "documentId": imported["documentId"]} for page in imported["pages"]]


def test_word_export_uses_text_without_a_page_screenshot() -> None:
    imported = import_bytes(b"A native paragraph\nA second paragraph", "text.txt")
    response = client().post("/api/export", json={"format": "docx", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    document = Document(io.BytesIO(response.data))
    assert [paragraph.text for paragraph in document.paragraphs] == ["A native paragraph", "A second paragraph"]
    assert len(document.inline_shapes) == 0
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert not any(name.startswith("word/media/") for name in archive.namelist())


def test_word_table_round_trip_preserves_edits_empty_cells_and_merges() -> None:
    source = Document()
    source.add_paragraph("Before the table")
    table = source.add_table(rows=3, cols=3)
    table.cell(0, 0).merge(table.cell(0, 1)).text = "Merged heading"
    table.cell(0, 2).text = "Status"
    table.cell(1, 0).text = "Original"
    table.cell(1, 2).text = "Ready"
    table.cell(2, 0).merge(table.cell(2, 2)).text = "Footer"
    source.add_paragraph("After the table")
    output = io.BytesIO()
    source.save(output)
    imported = import_bytes(output.getvalue(), "table.docx")
    pages = imported_export_pages(imported)
    cells = [annotation for annotation in pages[0]["annotations"] if annotation.get("table")]
    assert len(cells) == 6
    next(annotation for annotation in cells if annotation["text"] == "Original")["text"] = "Edited cell"
    response = client().post("/api/export", json={"format": "docx", "pages": pages})
    assert response.status_code == 200, response.get_json()
    exported = Document(io.BytesIO(response.data))
    assert len(exported.tables) == 1
    result = exported.tables[0]
    assert result.cell(1, 0).text == "Edited cell"
    assert result.cell(1, 1).text == ""
    assert result.cell(0, 0)._tc is result.cell(0, 1)._tc
    assert result.cell(2, 0)._tc is result.cell(2, 2)._tc
    assert len(exported.inline_shapes) == 0


def test_word_vertical_merge_round_trip() -> None:
    source = Document()
    table = source.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(1, 0)).text = "Two rows"
    table.cell(0, 1).text = "One"
    table.cell(1, 1).text = "Two"
    output = io.BytesIO()
    source.save(output)
    imported = import_bytes(output.getvalue(), "vertical.docx")
    response = client().post("/api/export", json={"format": "docx", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    table = Document(io.BytesIO(response.data)).tables[0]
    assert table.cell(0, 0).text == "Two rows"
    assert table.cell(0, 0)._tc is table.cell(1, 0)._tc


def test_pdf_tables_export_to_native_word_cells() -> None:
    with fitz.open() as source:
        page = source.new_page(width=400, height=300)
        for x in (40, 180, 320):
            page.draw_line((x, 60), (x, 180))
        for y in (60, 120, 180):
            page.draw_line((40, y), (320, y))
        for text, x, y in (("Name", 50, 90), ("Value", 190, 90), ("Alice", 50, 150)):
            page.insert_text((x, y), text, fontsize=14)
        imported = import_bytes(source.tobytes(), "table.pdf")
    response = client().post("/api/export", json={"format": "docx", "pages": imported_export_pages(imported)})
    assert response.status_code == 200, response.get_json()
    exported = Document(io.BytesIO(response.data))
    assert len(exported.tables) == 1
    assert [[cell.text for cell in row.cells] for row in exported.tables[0].rows] == [["Name", "Value"], ["Alice", ""]]
    assert len(exported.inline_shapes) == 0


def test_pdf_round_trip_preserves_page_size_vector_artwork_and_edited_text() -> None:
    with fitz.open() as source:
        page = source.new_page(width=300, height=500)
        page.draw_rect(fitz.Rect(10, 10, 290, 490), color=(1, 0, 0))
        page.insert_text((40, 80), "Original wording", fontsize=18)
        imported = import_bytes(source.tobytes(), "vector.pdf")
    pages = imported_export_pages(imported)
    pages[0]["annotations"][0]["text"] = "Revised wording"
    response = client().post("/api/export", json={"format": "pdf", "pages": pages})
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as exported:
        assert exported[0].rect.width == pytest.approx(300)
        assert exported[0].rect.height == pytest.approx(500)
        assert exported[0].get_drawings()
        assert "Revised wording" in exported[0].get_text().replace("\xa0", " ")
        assert "Original wording" not in exported[0].get_text()
        assert not exported[0].get_images()


def test_portable_pdf_background_does_not_require_server_cache() -> None:
    with fitz.open() as source:
        page = source.new_page(width=200, height=300)
        page.draw_line((20, 20), (150, 20))
        imported = import_bytes(source.tobytes(), "portable.pdf")
    page = imported["pages"][0]
    page["imageData"] = "data:image/png;base64," + base64.b64encode(client().get(page["imageUrl"]).data).decode()
    page["pdfData"] = base64.b64encode(client().get(page["pdfUrl"]).data).decode()
    response = client().post("/api/export", json={"format": "pdf", "pages": [page]})
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as exported:
        assert exported[0].get_drawings()
        assert exported[0].rect.width == pytest.approx(200)


def test_rotated_pdf_keeps_original_text_and_orientation() -> None:
    with fitz.open() as source:
        page = source.new_page(width=300, height=500)
        page.insert_text((40, 80), "Rotated wording", fontsize=18)
        page.set_rotation(90)
        imported = import_bytes(source.tobytes(), "rotation.pdf")
    response = client().post("/api/export", json={"format": "pdf", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as exported:
        assert exported[0].rect.width == pytest.approx(500)
        assert exported[0].rect.height == pytest.approx(300)
        assert "Rotated wording" in exported[0].get_text()


@pytest.mark.parametrize(
    "payload",
    [
        [1],
        "invalid",
        {"pages": [None]},
        {"pages": {"x": 1}},
        {"pages": [{"width": "oops", "height": 400}]},
        {"pages": [{"width": 100000, "height": 100000}]},
        {"pages": [{"width": 400, "height": 400, "annotations": [{"type": "stroke", "points": [[1]]}]}]},
        {"pages": [{"width": 400, "height": 400, "annotations": [{"type": "text", "x": float("nan")}]}]},
        {"pages": [{"width": 400, "height": 400, "annotations": [{"type": "text", "table": {"id": "bad"}}]}]},
    ],
)
def test_invalid_export_returns_json_error(payload: Any) -> None:
    response = client().post("/api/export", json=payload)
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json()["error"]


def test_long_text_exports_without_silently_disappearing() -> None:
    page = blank_export_page(600, 800)
    page["annotations"] = [
        {
            "type": "text",
            "text": "Wrapping words " * 15 + "THE END",
            "x": 20,
            "y": 30,
            "width": 280,
            "height": 20,
            "fontSize": 24,
        }
    ]
    response = client().post("/api/export", json={"format": "pdf", "pages": [page]})
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as exported:
        assert "THE END" in " ".join(exported[0].get_text().split())
        assert exported[0].get_text().count("Wrapping") == 15


def test_long_imported_paragraph_paginates_without_losing_words() -> None:
    imported = import_bytes(("content " * 3000).encode(), "long.txt")
    assert len(imported["pages"]) > 1
    assert (
        sum(annotation["text"].count("content") for page in imported["pages"] for annotation in page["annotations"])
        == 3000
    )
    assert all(
        annotation["y"] + annotation["height"] <= page["height"]
        for page in imported["pages"]
        for annotation in page["annotations"]
    )


def test_text_import_does_not_strip_markdown_characters() -> None:
    imported = import_bytes(b"# Literal heading\n- Literal dash", "literal.txt")
    assert [annotation["text"] for annotation in imported["pages"][0]["annotations"]] == [
        "# Literal heading",
        "- Literal dash",
    ]


def test_html_tables_are_imported_and_exported_as_tables() -> None:
    imported = import_bytes(
        b"<p>Caption</p><table><tr><th>Name</th><th>Status</th></tr><tr><td>A</td><td>OK</td></tr></table>",
        "table.html",
    )
    response = client().post("/api/export", json={"format": "docx", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    document = Document(io.BytesIO(response.data))
    assert document.tables[0].cell(1, 1).text == "OK"
    assert document.paragraphs[0].text == "Caption"


def test_transparent_image_is_composited_on_white() -> None:
    image = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    imported = import_bytes(output.getvalue(), "transparent.png")
    background = Image.open(io.BytesIO(client().get(imported["pages"][0]["imageUrl"]).data))
    assert background.getpixel((0, 0)) == (255, 255, 255)


def test_word_import_preserves_inline_images_and_run_formatting() -> None:
    source = Document()
    paragraph = source.add_paragraph()
    paragraph.add_run("Plain ")
    run = paragraph.add_run("emphasis")
    run.bold, run.italic = True, True
    image = io.BytesIO()
    Image.new("RGB", (80, 60), "red").save(image, format="PNG")
    source.add_picture(image)
    output = io.BytesIO()
    source.save(output)
    imported = import_bytes(output.getvalue(), "picture.docx")
    response = client().post("/api/export", json={"format": "docx", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    document = Document(io.BytesIO(response.data))
    assert len(document.inline_shapes) == 1
    paragraph = next(paragraph for paragraph in document.paragraphs if paragraph.text == "Plain emphasis")
    assert paragraph.runs[1].bold and paragraph.runs[1].italic


def test_dot_stroke_is_visible_in_image_and_pdf_exports() -> None:
    page = blank_export_page(300, 300)
    page["annotations"] = [{"type": "stroke", "points": [[100, 100]], "lineWidth": 20, "color": "#ff0000"}]
    for export_format in ("png", "pdf"):
        response = client().post("/api/export", json={"format": export_format, "pages": [page]})
        assert response.status_code == 200
        if export_format == "png":
            image = Image.open(io.BytesIO(response.data))
            assert cast(tuple[int, int, int], image.getpixel((100, 100)))[1] < 50
        else:
            with fitz.open(stream=response.data, filetype="pdf") as exported:
                assert exported[0].get_drawings()


def test_pdf_fractional_page_dimensions_are_preserved_exactly() -> None:
    with fitz.open() as source:
        source.new_page(width=300.25, height=500.125)
        imported = import_bytes(source.tobytes(), "fractional.pdf")
    response = client().post("/api/export", json={"format": "pdf", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as exported:
        assert exported[0].rect.width == pytest.approx(300.25)
        assert exported[0].rect.height == pytest.approx(500.125)


def test_word_headings_keep_their_inherited_style_and_emphasis() -> None:
    source = Document()
    source.add_heading("Heading", level=1)
    output = io.BytesIO()
    source.save(output)
    imported = import_bytes(output.getvalue(), "heading.docx")
    response = client().post("/api/export", json={"format": "docx", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    paragraph = Document(io.BytesIO(response.data)).paragraphs[0]
    assert paragraph.style and paragraph.style.name == "Heading 1"
    assert paragraph.runs[0].bold


def test_overlapping_translucent_strokes_blend_consistently() -> None:
    page = blank_export_page(300, 300)
    stroke = {"type": "stroke", "points": [[30, 100], [250, 100]], "lineWidth": 20, "color": "#ff0000", "opacity": 0.5}
    page["annotations"] = [stroke, stroke]
    response = client().post("/api/export", json={"format": "png", "pages": [page]})
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.data))
    pixel = cast(tuple[int, int, int], image.getpixel((100, 100)))
    assert 62 <= pixel[1] <= 65


def test_word_run_formatting_survives_pdf_export() -> None:
    from docx.shared import Pt, RGBColor

    source = Document()
    paragraph = source.add_paragraph()
    paragraph.add_run("Regular ")
    run = paragraph.add_run("Bold red")
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(255, 0, 0)
    output = io.BytesIO()
    source.save(output)
    imported = import_bytes(output.getvalue(), "formatted.docx")
    response = client().post("/api/export", json={"format": "pdf", "pages": imported_export_pages(imported)})
    assert response.status_code == 200
    with fitz.open(stream=response.data, filetype="pdf") as exported:
        spans = [
            span
            for block in exported[0].get_text("dict")["blocks"]
            if block["type"] == 0
            for line in block["lines"]
            for span in line["spans"]
        ]
        assert any("Bold" in span["text"] and span["color"] == 0xFF0000 and span["flags"] & 16 for span in spans)
