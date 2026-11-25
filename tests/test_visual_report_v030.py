"""Etapa 4 da v0.3.0: diferença visual (opcional) e relatório de diferenças."""

import csv

import fitz
import pytest

from app.services.preferences import CompareSettings
from app.services.report import PairReport, make_report, to_html, write_report
from app.services.text_diff import ADDED, CHANGED, REMOVED, ReportEntry, report_entries
from app.services.text_index import DocumentIndex
from app.services.visual_diff import VISUAL, page_difference, threshold_for


def _page(draw=None, text="Contrato de prestacao de servicos", size=(595, 842)):
    doc = fitz.open()
    page = doc.new_page(width=size[0], height=size[1])
    page.insert_text((72, 72), text, fontsize=14)
    if draw:
        draw(page)
    return doc


def _circle(page):
    page.draw_circle(fitz.Point(150, 400), 30, color=(1, 0, 0), width=3)


# --- diferença visual: serviço -------------------------------------------------------------------
def test_visual_difference_finds_drawings_and_ignores_identical_pages(qapp):
    a, b = _page(), _page(_circle)
    boxes_a, boxes_b = page_difference(a[0], b[0])
    [box] = boxes_b
    assert box[0] < 125 and box[1] < 375 and box[2] > 175 and box[3] > 425   # cobre o círculo
    assert boxes_a == [tuple(box)]                                           # mesma área na outra página
    assert page_difference(a[0], _page()[0]) == ([], [])


def test_visual_sensitivity(qapp):
    faint = lambda page: page.draw_rect(fitz.Rect(300, 600, 400, 700), color=None, fill=(0.93, 0.93, 0.93))  # noqa: E731
    a, b = _page(), _page(faint)
    assert page_difference(a[0], b[0], sensitivity=10)[1] == []      # pouco sensível: ignora cinza claro
    assert len(page_difference(a[0], b[0], sensitivity=95)[1]) == 1  # muito sensível: encontra
    assert threshold_for(100) < threshold_for(50) < threshold_for(1)


def test_visual_difference_with_different_page_sizes(qapp):
    a = _page(size=(595, 842))
    b = _page(_circle, size=(612, 792))
    _, boxes_b = page_difference(a[0], b[0])
    assert boxes_b and all(0 <= r[0] < r[2] <= 612 and 0 <= r[1] < r[3] <= 792 for r in boxes_b)


# --- relatório: serviço ---------------------------------------------------------------------------
def _index(texts):
    doc = fitz.open()
    for text in texts:
        doc.new_page().insert_text((72, 72), text, fontsize=12)
    return DocumentIndex.build(doc)


def test_report_entries_keep_punctuation_and_pages():
    a = _index(["O prazo e de 30 dias.", "Multa de 2%, art. 5.", "Fim"])
    b = _index(["O prazo e de 45 dias.", "Fim", "Anexo novo"])
    entries = report_entries(a, b)
    assert entries == [
        ReportEntry(CHANGED, 0, "30", 0, "45"),
        ReportEntry(REMOVED, 1, "Multa de 2%, art. 5.", 1, ""),
        ReportEntry(ADDED, 2, "", 2, "Anexo novo"),
    ]
    assert report_entries(a, a) == []


@pytest.fixture
def sample_report():
    entries = [ReportEntry(CHANGED, 0, "30 <dias>", 0, "45 dias"), ReportEntry(ADDED, 2, "", 3, "Anexo & novo")]
    return make_report("25/11/2026 10:00", "Referência: v1.pdf", ["v1.pdf", "v2.pdf"],
                       [PairReport("v1.pdf", "v2.pdf", entries), PairReport("v1.pdf", "v3.pdf", [])])


def test_report_formats(sample_report, tmp_path):
    assert write_report(tmp_path / "r.csv", sample_report) == "csv"
    with open(tmp_path / "r.csv", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    assert rows[0][:3] == ["Base", "Comparado", "Tipo"]
    assert rows[1] == ["v1.pdf", "v2.pdf", "Alterado", "1", "30 <dias>", "1", "45 dias"]
    assert rows[2] == ["v1.pdf", "v2.pdf", "Incluído", "", "", "4", "Anexo & novo"]

    assert write_report(tmp_path / "r.htm", sample_report) == "html"
    page = (tmp_path / "r.htm").read_text(encoding="utf-8")
    assert "30 &lt;dias&gt;" in page and "Anexo &amp; novo" in page and "Texto idêntico." in page

    assert write_report(tmp_path / "r.pdf", sample_report) == "pdf"
    with fitz.open(tmp_path / "r.pdf") as doc:
        text = doc[0].get_text()
    assert "Relatório de diferenças" in text and "45 dias" in text and "v1.pdf > v3.pdf" in text

    with pytest.raises(ValueError):
        write_report(tmp_path / "r.docx", sample_report)


def test_long_report_spans_pages(tmp_path):
    entries = [ReportEntry(CHANGED, k, f"antigo {k}", k, f"novo {k}") for k in range(300)]
    report = make_report("hoje", "modo", ["a", "b"], [PairReport("a", "b", entries)])
    write_report(tmp_path / "longo.pdf", report)
    with fitz.open(tmp_path / "longo.pdf") as doc:
        assert doc.page_count > 3
        assert "novo 299" in doc[-1].get_text()
    assert "<!DOCTYPE html>" in to_html(report) and "<!DOCTYPE" not in to_html(report, standalone=False)


# --- interface ---------------------------------------------------------------------------------------
@pytest.fixture
def drawn(window, tmp_path, qtbot):
    paths = []
    for name, draw in (("a.pdf", None), ("b.pdf", _circle)):
        doc = _page(draw, text="Contrato de prestacao de servicos 30 dias")
        doc.new_page().insert_text((72, 72), "Segunda pagina", fontsize=12)
        doc.save(tmp_path / name)
        paths.append(tmp_path / name)
    window.set_compare_settings(CompareSettings(batch_size=0))
    window.add_files(paths)
    qtbot.waitUntil(lambda: not window.indexer.busy, timeout=10000)
    return window


def test_visual_diff_toggle_without_text_comparison(drawn):
    w = drawn
    assert w.visual_marks(1, 0) == []                         # desligada: nada
    w.act_visual_diff.trigger()
    assert not w.act_diff.isChecked()
    [mark] = w.visual_marks(1, 0)
    assert mark.kind == VISUAL and mark.page == 0
    assert len(w.panes[1]._visual) == 1 and len(w.panes[0]._visual) == 1
    assert "1" in w.visual_label.text() or "2" in w.visual_label.text()
    w.step(+1)                                                # 2ª página igual
    assert w.panes[1]._visual == () and "0 área" in w.visual_label.text()
    w.act_visual_diff.trigger()
    assert not w.visual_label.isVisibleTo(w)


def test_visual_diff_sensitivity_from_settings_and_continuous(drawn):
    w = drawn
    w.act_visual_diff.trigger()
    assert w.visual_marks(1, 0)
    w.set_compare_settings(CompareSettings(batch_size=0, visual_sensitivity=1))
    assert not w._visual_cache                                 # recalcula com a nova sensibilidade
    w.act_continuous.trigger()
    assert w.panes[1].visual_provider(0) == w.visual_marks(1, 0)
    assert "ligada" in w.visual_label.text()


def test_visual_diff_follows_reference_and_alignment(drawn):
    w = drawn
    w.act_visual_diff.trigger()
    w.set_reference(1)
    assert w.visual_marks(0, 0) and w.visual_marks(1, 0)
    w._on_pane_step(1, +1)                                     # desalinhou: página 1 de A com a 2 de B
    assert w._partner_page(0, 0, 1) == 1


def test_report_from_window(drawn, tmp_path, make_pdf, qtbot):
    w = drawn
    path = tmp_path / "relatorio.csv"
    assert w.save_report(str(path))
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    assert len(rows) == 1                                       # só o cabeçalho: texto igual
    assert "0 mudança" in w.statusBar().currentMessage()

    w.add_files([make_pdf("c.pdf", texts=["Contrato de prestacao de servicos 45 dias", "Segunda pagina"])])
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)
    w.set_chain_mode(True)
    report = w.build_report()
    assert [(p.base, p.other) for p in report.pairs] == [("a.pdf", "b.pdf"), ("b.pdf", "c.pdf")]
    assert report.pairs[1].entries == [ReportEntry(CHANGED, 0, "30", 0, "45")]
    assert "cadeia" in report.mode
