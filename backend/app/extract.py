"""Turn an uploaded photo/PDF into text.

Strategy (auto-fallback):
1. PDFs with an embedded text layer -> read text directly with PyMuPDF.
2. Images / scanned PDFs -> try cloud vision if a key is configured, else local OCR.
   If cloud vision is unavailable or returns nothing usable, fall back to local Tesseract.
"""

from __future__ import annotations

import io
from typing import Callable

import pymupdf as fitz  # PyMuPDF
from PIL import Image
import pytesseract


MIN_CHARS = 40


def _ocr_image_bytes(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return pytesseract.image_to_string(img)


def _pdf_text_and_images(data: bytes) -> tuple[str, list[bytes]]:
    doc = fitz.open(stream=data, filetype="pdf")
    texts: list[str] = []
    images: list[bytes] = []
    for page in doc:
        page_text = page.get_text().strip()
        if len(page_text) >= MIN_CHARS:
            texts.append(page_text)
        else:
            pix = page.get_pixmap(dpi=200)
            images.append(pix.tobytes("png"))
    doc.close()
    return "\n\n".join(texts).strip(), images


def _read_images(
    images: list[bytes], cloud_reader: Callable[[list[bytes]], str] | None
) -> tuple[str, str]:
    if cloud_reader is not None:
        try:
            text = (cloud_reader(images) or "").strip()
            if len(text) >= 5:
                return text, "cloud-vision"
        except Exception:
            pass

    chunks: list[str] = []
    for b in images:
        try:
            chunks.append(_ocr_image_bytes(b))
        except Exception:
            chunks.append("")
    text = "\n\n".join(c.strip() for c in chunks if c.strip()).strip()
    return text, "local-ocr"


def read_homework(
    filename: str,
    data: bytes,
    cloud_reader: Callable[[list[bytes]], str] | None = None,
) -> tuple[str, str]:
    """Return (extracted_text, method_used)."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext == "pdf":
        text, images = _pdf_text_and_images(data)
        if len(text) >= MIN_CHARS:
            return text, "pdf-text"
        if images:
            return _read_images(images, cloud_reader)
        return text, "pdf-text"

    if ext in ("png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"):
        return _read_images([data], cloud_reader)

    # Unknown type: try OCR anyway.
    return _read_images([data], cloud_reader)
