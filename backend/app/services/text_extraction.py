import hashlib
from pathlib import Path

import pdfplumber
from docx import Document as DocxDocument


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "pdf":
        return _extract_text_pdf(path)
    if suffix in {"docx"}:
        return _extract_text_docx(path)
    if suffix in {"doc", "txt", "rtf"}:
        return _extract_text_plain(path)
    if suffix in {"png", "jpg", "jpeg"}:
        return _extract_text_image(path)
    return ""


def _extract_text_pdf(path: Path) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def _extract_text_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    parts = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(parts).strip()


def _extract_text_plain(path: Path) -> str:
    try:
        return path.read_text("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _extract_text_image(path: Path) -> str:
    # OCR opcional: só executa se PIL+pytesseract estiverem disponíveis no ambiente.
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        with Image.open(str(path)) as img:
            txt = pytesseract.image_to_string(img, lang="por+eng")
        return (txt or "").strip()
    except Exception:
        return ""
