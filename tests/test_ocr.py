"""OCR opcional (Tesseract)."""

import fitz
import pytest

from app.services import ocr

HAS_TESSERACT = ocr.check("por").available


def _scanned_pdf(path, text="Contrato escaneado numero 42"):
    """PDF só com imagem: renderiza um PDF de texto e guarda como figura."""
    src = fitz.open()
    page = src.new_page(width=400, height=200)
    page.insert_text((30, 100), text, fontsize=24)
    pix = page.get_pixmap(dpi=200)
    out = fitz.open()
    img_page = out.new_page(width=400, height=200)
    img_page.insert_image(img_page.rect, pixmap=pix)
    out.save(str(path))
    src.close()
    out.close()
    return path


def test_missing_tesseract_is_reported_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path / "nao_existe"))
    monkeypatch.setattr(ocr.fitz, "get_tessdata", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(ocr, "WINDOWS_TESSDATA", [tmp_path / "nada"])
    status = ocr.check()
    assert not status.available and "Tesseract" in status.message and "UB Mannheim" in status.message
    doc = fitz.open(str(_scanned_pdf(tmp_path / "s.pdf")))
    with pytest.raises(ocr.OcrUnavailable):
        ocr.ocr_tokens(doc[0])
    doc.close()


def test_missing_language_is_reported(monkeypatch, tmp_path):
    (tmp_path / "eng.traineddata").write_bytes(b"")
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path))
    status = ocr.check("por+eng")
    assert not status.available and "por" in status.message and "eng" in status.message.split("instalados:")[1]


def test_split_language():
    assert ocr.split_language("por+eng") == ["por", "eng"]
    assert ocr.split_language("por, eng") == ["por", "eng"]


def test_page_needs_ocr(make_pdf, tmp_path):
    text_doc = fitz.open(str(make_pdf("t.pdf", texts=["tem texto"])))
    assert not ocr.page_needs_ocr(text_doc[0])
    scan = fitz.open(str(_scanned_pdf(tmp_path / "s.pdf")))
    assert ocr.page_needs_ocr(scan[0])
    blank = fitz.open()
    blank.new_page()
    assert not ocr.page_needs_ocr(blank[0])


@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract com idioma 'por' não instalado")
def test_ocr_recognizes_scanned_text(tmp_path):
    doc = fitz.open(str(_scanned_pdf(tmp_path / "s.pdf")))
    words = [t.text.lower() for t in ocr.ocr_tokens(doc[0], "por", dpi=200)]
    assert "contrato" in words and "escaneado" in words
    assert doc[0].get_text().strip() == ""   # PDF original não muda
    doc.close()


@pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract com idioma 'por' não instalado")
def test_indexer_uses_ocr_when_enabled(qtbot, tmp_path):
    from app.model.session import DocumentSession
    from app.services.indexer import IndexScheduler
    from app.services.search import search_index

    session = DocumentSession.open(_scanned_pdf(tmp_path / "s.pdf"))
    sched = IndexScheduler()
    sched.add(session)
    qtbot.waitUntil(lambda: not sched.busy, timeout=10000)
    assert search_index(sched.index_for(session), "contrato") == []

    sched.set_ocr(True, "por")
    sched.add(session)
    qtbot.waitUntil(lambda: not sched.busy, timeout=30000)
    assert len(search_index(sched.index_for(session), "contrato")) == 1
    assert sched.ocr_pages[session.uid] == 1
    session.close()


def test_indexer_disables_ocr_and_warns_when_unavailable(qtbot, tmp_path, monkeypatch):
    from app.model.session import DocumentSession
    from app.services.indexer import IndexScheduler

    def fail(*_a, **_k):
        raise ocr.OcrUnavailable("sem tesseract")

    monkeypatch.setattr(ocr, "ocr_tokens", fail)
    session = DocumentSession.open(_scanned_pdf(tmp_path / "s.pdf"))
    sched = IndexScheduler()
    sched.set_ocr(True)
    with qtbot.waitSignal(sched.ocr_failed, timeout=5000) as blocker:
        sched.add(session)
    assert blocker.args == ["sem tesseract"]
    qtbot.waitUntil(lambda: not sched.busy, timeout=5000)
    assert not sched.ocr_enabled and sched.index_for(session).complete
    session.close()
