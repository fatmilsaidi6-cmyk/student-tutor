import io
import shutil

import pymupdf
import pytest
from PIL import Image, ImageDraw

from app.extract import read_homework


def _pdf_with_text(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 96), text, fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_text_layer_is_extracted():
    data = _pdf_with_text("Solve 2x + 3 = 11 and explain every step clearly please.")
    text, method = read_homework("homework.pdf", data)
    assert method == "pdf-text"
    assert "2x" in text


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_image_falls_back_to_local_ocr():
    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 80), "Homework 12345", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")

    text, method = read_homework("homework.png", buf.getvalue())
    assert method == "local-ocr"
    assert isinstance(text, str)


def test_unknown_extension_is_attempted_as_image():
    # Unless tesseract is present this returns empty text, but it must not raise.
    img = Image.new("RGB", (10, 10), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    text, method = read_homework("scan.dat", buf.getvalue())
    assert method in ("local-ocr", "cloud-vision")
    assert isinstance(text, str)
