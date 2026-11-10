"""Utility for extracting plain text content from various file attachments (docx, pdf, txt, etc.)."""

import io
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    # Documents
    ".docx",
    ".doc",
    ".pdf",
    ".rtf",
    # Plain text / code
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".sql",
    ".log",
    ".yml",
    ".yaml",
    ".xml",
    ".html",
    ".htm",
    ".sh",
    ".env",
    ".cfg",
    ".ini",
}

MAX_EXTRACTED_CHARS = 25000  # Cap extracted text length to avoid token overflow


def is_supported_attachment(filename: str) -> bool:
    """Check if the file extension is supported for text extraction."""
    if not filename:
        return False
    ext = os.path.splitext(filename.split("?")[0].lower())[1]
    return ext in SUPPORTED_EXTENSIONS


def extract_text_from_docx_bytes(content: bytes) -> str:
    """Extract paragraphs and tables from a .docx file bytes."""
    # 1. Try python-docx if installed
    try:
        import docx

        doc = docx.Document(io.BytesIO(content))
        lines = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                lines.append(text)
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                if row_text:
                    lines.append(row_text)
        if lines:
            return "\n".join(lines)
    except Exception as e:
        logger.debug("python-docx extraction failed, trying zipfile fallback: %s", e)

    # 2. Fallback using standard library zipfile + XML parsing
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "word/document.xml" in z.namelist():
                xml_data = z.read("word/document.xml")
                tree = ET.fromstring(xml_data)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = []
                for p in tree.iterfind(".//w:p", ns):
                    texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                    if texts:
                        paragraphs.append("".join(texts))
                return "\n".join(paragraphs)
    except Exception as e:
        logger.warning("Failed to extract docx via fallback: %s", e)

    return ""


def extract_text_from_pdf_bytes(content: bytes) -> str:
    """Extract text from a .pdf file bytes."""
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(content))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages_text.append(text.strip())
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.warning("Failed to extract text from PDF: %s", e)
        return ""


def extract_text_from_plain_bytes(content: bytes) -> str:
    """Extract plain text decoding with common encodings."""
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


def extract_text_from_file_bytes(
    content: bytes, filename: str, max_chars: int = MAX_EXTRACTED_CHARS
) -> Optional[str]:
    """Universal text extractor for downloaded attachment bytes."""
    if not content:
        return None

    clean_name = filename.split("?")[0].lower()
    ext = os.path.splitext(clean_name)[1]

    text = ""
    try:
        if ext in (".docx", ".doc"):
            text = extract_text_from_docx_bytes(content)
        elif ext == ".pdf":
            text = extract_text_from_pdf_bytes(content)
        elif ext in SUPPORTED_EXTENSIONS or ext == "":
            text = extract_text_from_plain_bytes(content)
    except Exception as e:
        logger.warning("Error extracting text from %s: %s", filename, e)
        return None

    text = text.strip()
    if not text:
        return None

    # Sanitize and truncate
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [Текст файла обрезан, превышен лимит {max_chars} символов] ..."

    return text
