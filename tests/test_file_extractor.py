import io
import pytest
from src.collectors.file_extractor import (
    is_supported_attachment,
    extract_text_from_file_bytes,
    extract_text_from_plain_bytes,
)
from src.collectors.enricher import OrderEnricher
from src.models.order import RawOrder, SourcePlatform


def test_is_supported_attachment():
    assert is_supported_attachment("tech_spec.docx") is True
    assert is_supported_attachment("architecture.DOC") is True
    assert is_supported_attachment("brief.pdf") is True
    assert is_supported_attachment("data.json") is True
    assert is_supported_attachment("script.py") is True
    assert is_supported_attachment("notes.txt") is True
    assert is_supported_attachment("archive.exe") is False
    assert is_supported_attachment("") is False


def test_extract_plain_text():
    content = "Проектирование микросервисной архитектуры\nТребования: FastAPI, Redis".encode("utf-8")
    extracted = extract_text_from_file_bytes(content, "requirements.txt")
    assert "Проектирование микросервисной архитектуры" in extracted
    assert "FastAPI, Redis" in extracted


def test_extract_plain_text_cp1251():
    content = "ТЗ на разработку бота".encode("cp1251")
    extracted = extract_text_from_file_bytes(content, "tz.txt")
    assert "ТЗ на разработку бота" in extracted


def test_extract_docx():
    import docx

    doc = docx.Document()
    doc.add_paragraph("Архитектура лаунж-бара")
    doc.add_paragraph("Сканирование QR-кодов Wallet карт")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Модуль"
    table.rows[0].cells[1].text = "Назначение"
    table.rows[1].cells[0].text = "QR Scanner"
    table.rows[1].cells[1].text = "ZXing веб"

    buf = io.BytesIO()
    doc.save(buf)
    content = buf.getvalue()

    extracted = extract_text_from_file_bytes(content, "lounge_Al_Technical_Architecture.docx")
    assert "Архитектура лаунж-бара" in extracted
    assert "Сканирование QR-кодов Wallet карт" in extracted
    assert "QR Scanner" in extracted


def test_extract_pdf():
    import pypdf

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    content = buf.getvalue()

    # Even blank page shouldn't fail
    extracted = extract_text_from_file_bytes(content, "specification.pdf")
    # Blank page returns None or empty
    assert extracted is None or extracted == ""


@pytest.mark.asyncio
async def test_enricher_fl_ru_with_files(monkeypatch):
    sample_html = """
    <html>
    <body>
        <div id="projectp123" class="fl-project-content__description-text">
            Основной текст ТЗ проекта
        </div>
        <a href="/upload/files/spec.docx">spec.docx</a>
        <a href="/download/data.txt">data.txt</a>
    </body>
    </html>
    """

    enricher = OrderEnricher()

    class MockResponse:
        def __init__(self, status_code, text, content):
            self.status_code = status_code
            self.text = text
            self.content = content

    async def mock_get(self, url, *args, **kwargs):
        url_str = str(url)
        if "123" in url_str:
            return MockResponse(200, sample_html, sample_html.encode())
        elif "data.txt" in url_str:
            txt = "Содержимое текстового файла ТЗ"
            return MockResponse(200, txt, txt.encode())
        elif "spec.docx" in url_str:
            import docx

            doc = docx.Document()
            doc.add_paragraph("Спецификация из docx файла")
            buf = io.BytesIO()
            doc.save(buf)
            content = buf.getvalue()
            return MockResponse(200, "docx binary", content)
        return MockResponse(404, "", b"")

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    order = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="123",
        title="Тест",
        description="Кратко",
        url="https://www.fl.ru/projects/123/test.html",
    )

    enriched = await enricher.enrich(order)
    assert "Основной текст ТЗ проекта" in enriched.description
    assert enriched.attachments_text is not None
    assert "Спецификация из docx файла" in enriched.attachments_text
    assert "Содержимое текстового файла ТЗ" in enriched.attachments_text
