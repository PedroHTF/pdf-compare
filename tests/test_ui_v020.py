"""Testes de interface das funções da versão 0.2.0."""

import fitz
import pytest
from PySide6.QtCore import QPoint

from app.services import ocr
from app.services.annotations import HIGHLIGHT, NOTE
from app.services.export import PDF, PNG
from app.ui.export_dialog import ANNOTATED, CURRENT_PAGES, SCOPE_ALL, SIDE_BY_SIDE, ExportChoice, ExportDialog
from app.ui.pane import TOOL_HIGHLIGHT, TOOL_NONE, TOOL_NOTE


def _wait_index(qtbot, w):
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)


def _wait_diff(qtbot, w):
    """A comparação roda em segundo plano: espera o primeiro lote ficar pronto."""
    qtbot.waitUntil(lambda: not w.runner.busy and w.runner.done_count() > 0, timeout=10000)


def _search(w, text):
    w.search_bar.edit.setText(text)
    w.search_bar.flush()


@pytest.fixture
def versions(make_pdf):
    a = make_pdf("v1.pdf", texts=["Capa", "O prazo e de 30 dias", "Fim do contrato"])
    b = make_pdf("v2.pdf", texts=["Capa", "O prazo e de 45 dias", "Fim do contrato"])
    return a, b


# --- lista de ocorrências -------------------------------------------------------
def test_results_panel_lists_hits_and_jumps(window, qtbot, versions):
    window.add_files(versions)
    _wait_index(qtbot, window)
    _search(window, "contrato")
    assert window.results_panel.item_count() == [1, 1]
    first = window.results_panel.tree.topLevelItem(0).child(0).text(0)
    assert first.startswith("p. 3") and "[contrato]" in first

    window.results_panel.activate(1, 0)
    assert window.nav.page_for(1) == 2 and window.nav.page_for(0) == 0
    assert window.panes[1].hit_label.text() == "1 de 1"

    _search(window, "")
    assert window.results_panel.item_count() == []


def test_results_panel_toggle_persists(window):
    window.act_results.trigger()
    assert window.results_dock.isVisible()
    window.close()
    assert window.settings.value("view/results_panel") in (True, "true")


# --- anotações --------------------------------------------------------------------
def test_highlight_snaps_to_words_and_persists(window, versions, tmp_path, qtbot):
    from app.ui.main_window import MainWindow

    original = versions[0].read_bytes()
    window.add_files(versions)
    window.set_tool(TOOL_HIGHLIGHT)
    assert window.panes[0].tool == TOOL_HIGHLIGHT
    word = window.sessions[0].doc[0].get_text("words")[0]
    window.panes[0].highlight_requested.emit(0, 0, (word[0] + 1, word[1] + 1, word[2] - 1, word[3] - 1))
    items = window.document_annotations(0)
    assert len(items) == 1 and items[0].kind == HIGHLIGHT and items[0].rects == [tuple(word[:4])]
    assert window.page_annotations(1, 0) == []
    assert versions[0].read_bytes() == original

    other = MainWindow(settings=window.settings, data_dir=tmp_path / "dados")
    qtbot.addWidget(other)
    other._notify = lambda *a: None
    other.add_files(versions)
    assert len(other.document_annotations(0)) == 1


def test_tiny_drag_without_text_is_ignored(window, versions):
    window.add_files(versions)
    window.panes[0].highlight_requested.emit(0, 0, (500, 700, 501, 701))
    assert window.document_annotations(0) == []


def test_note_add_edit_remove(window, versions):
    window.add_files(versions)
    answers = iter(["revisar prazo", "prazo ok"])
    window._ask_note_text = lambda initial: next(answers)
    window.set_tool(TOOL_NOTE)
    window.panes[1].note_requested.emit(1, 0, 100.0, 100.0)
    note = window.document_annotations(1)[0]
    assert note.kind == NOTE and note.text == "revisar prazo" and note.contains(100, 100)
    assert window.panes[1].annotation_tooltip(100, 100) == "revisar prazo"

    window.edit_annotation(1, note.id)
    assert window.document_annotations(1)[0].text == "prazo ok"
    window.remove_annotation(1, note.id)
    assert window.document_annotations(1) == []


def test_cancelled_note_is_not_added(window, versions):
    window.add_files(versions)
    window._ask_note_text = lambda initial: None
    window.panes[0].note_requested.emit(0, 0, 50.0, 50.0)
    assert window.document_annotations(0) == []


def test_tool_toggle(window, versions):
    window.add_files(versions)
    window.toggle_tool(TOOL_NOTE)
    assert window.act_note.isChecked() and not window.act_highlight.isChecked()
    window.toggle_tool(TOOL_NOTE)
    assert window.tool == TOOL_NONE and not window.act_note.isChecked()


def test_pane_maps_mouse_to_page_coordinates(window, versions):
    window.add_files(versions)
    window.set_zoom(1.0)
    pane = window.panes[0]
    point = pane.to_page_point(QPoint(100, 50))
    assert point == pytest.approx((100, 50), abs=1)
    window.set_zoom(2.0)
    assert pane.to_page_point(QPoint(100, 50)) == pytest.approx((50, 25), abs=1)


def test_drag_on_pane_creates_highlight(window, versions):
    window.add_files(versions)
    window.set_zoom(1.0)
    window.set_tool(TOOL_HIGHLIGHT)
    word = window.sessions[0].doc[0].get_text("words")[0]
    pane = window.panes[0]
    pane.finish_highlight(QPoint(int(word[0]) + 1, int(word[1]) + 2), QPoint(int(word[2]) - 1, int(word[3]) - 2))
    assert len(window.document_annotations(0)) == 1


# --- comparação de texto --------------------------------------------------------
def test_text_diff_highlights_and_navigates(window, qtbot, versions):
    window.add_files(versions)
    _wait_index(qtbot, window)
    assert window.act_diff.isEnabled()
    window.act_diff.trigger()
    _wait_diff(qtbot, window)
    assert window.nav.total_diffs == 2
    assert "~1" in window.diff_label.text()
    assert (window.nav.page_for(0), window.nav.page_for(1)) == (1, 1)   # já foi para a 1ª diferença
    assert window.act_diff_next.isEnabled()
    window.act_diff.trigger()
    assert window.nav.total_diffs == 0 and not window.diff_label.isVisibleTo(window)


def test_text_diff_waits_for_indexing(window, qtbot, versions):
    window.act_diff.setChecked(True)
    window.add_files(versions)
    if window.indexer.busy:
        assert "aguardando" in window.diff_label.text()
    _wait_index(qtbot, window)
    _wait_diff(qtbot, window)
    assert window.nav.total_diffs == 2


def test_text_diff_identical(window, qtbot, make_pdf):
    window.add_files([make_pdf("a.pdf", texts=["igual"]), make_pdf("b.pdf", texts=["igual"])])
    _wait_index(qtbot, window)
    window.act_diff.trigger()
    _wait_diff(qtbot, window)
    assert "idêntico" in window.diff_label.text()


# --- exportação -------------------------------------------------------------------
def test_export_side_by_side_current_and_all(window, versions, tmp_path):
    window.add_files(versions)
    window.step(+1)
    files = window.export(ExportChoice(SIDE_BY_SIDE, PDF), tmp_path / "c.pdf")
    doc = fitz.open(str(files[0]))
    assert doc.page_count == 1 and "30 dias" in doc[0].get_text() and "45 dias" in doc[0].get_text()
    doc.close()
    files = window.export(ExportChoice(SIDE_BY_SIDE, PNG, SCOPE_ALL, dpi=40), tmp_path / "todas.png")
    assert len(files) == 3 and all(f.exists() for f in files)


def test_export_current_pages_and_annotated(window, versions, tmp_path):
    window.add_files(versions)
    window._ask_note_text = lambda initial: "nota"
    window.panes[0].note_requested.emit(0, 0, 60.0, 60.0)
    files = window.export(ExportChoice(CURRENT_PAGES, PDF), tmp_path / "atuais")
    assert sorted(f.name for f in files) == ["v1_p1.pdf", "v2_p1.pdf"]
    assert len(list(fitz.open(str(tmp_path / "atuais" / "v1_p1.pdf"))[0].annots())) == 1
    no_notes = window.export(ExportChoice(CURRENT_PAGES, PDF, with_annotations=False), tmp_path / "sem")
    assert not list(fitz.open(str(no_notes[0]))[0].annots())

    files = window.export(ExportChoice(ANNOTATED), tmp_path / "anotados")
    assert sorted(f.name for f in files) == ["v1_anotado.pdf", "v2_anotado.pdf"]
    assert not list(fitz.open(str(versions[0]))[0].annots())


def test_export_error_is_reported(window, versions, tmp_path):
    window.add_files(versions)
    blocker = tmp_path / "arquivo"
    blocker.write_text("x")
    assert window.export(ExportChoice(SIDE_BY_SIDE, PDF), blocker / "x" / "c.pdf") == []
    assert window.notifications[-1][1] == "Exportação não concluída"


def test_export_dialog_choices(qtbot):
    dlg = ExportDialog(has_annotations=False)
    qtbot.addWidget(dlg)
    assert dlg.choice().kind == SIDE_BY_SIDE and not dlg.choice().with_annotations
    dlg.rb_annotated.setChecked(True)
    assert not dlg.fmt.isEnabled() and dlg.choice().fmt == PDF and dlg.choice().kind == ANNOTATED
    dlg.rb_current.setChecked(True)
    dlg.fmt.setCurrentIndex(1)
    assert dlg.choice().fmt == PNG and dlg.dpi.isEnabled() and not dlg.scope.isEnabled()


# --- pasta, recentes e sessões ----------------------------------------------------
def test_open_folder(window, make_pdf, tmp_path):
    make_pdf("b10.pdf", 1)
    make_pdf("b2.pdf", 1)
    window.open_folder(tmp_path)
    assert [s.name for s in window.sessions] == ["b2.pdf", "b10.pdf"]
    empty = tmp_path / "vazia"
    empty.mkdir()
    window.open_folder(empty)
    assert window.notifications[-1][1] == "Nenhum PDF"


def test_recent_files(window, versions):
    window.add_files(versions)
    assert [p.split("/")[-1].split("\\")[-1] for p in window.recent_files()[:2]] == ["v2.pdf", "v1.pdf"]
    window._fill_recent_menu()
    labels = [a.text() for a in window.recent_menu.actions()]
    assert "v1.pdf" in labels and "Limpar lista" in labels
    window.close_all()
    window.open_recent(window.recent_files()[0])
    assert [s.name for s in window.sessions] == ["v2.pdf"]


def test_save_and_open_session(window, versions, tmp_path):
    window.add_files(versions)
    window.panes[1].btn_next.click()    # v2 adiantado uma página
    window.step(+1)
    window.set_zoom(1.5)
    saved = window.save_session_to(tmp_path / "trabalho")
    assert saved.name == "trabalho.pdfcompare"

    window.close_all()
    window.set_zoom(1.0)
    window.open_session(saved)
    assert [s.name for s in window.sessions] == ["v1.pdf", "v2.pdf"]
    assert (window.nav.page_for(0), window.nav.page_for(1)) == (1, 2)
    assert window.zoom_mode == 1.5
    assert str(saved) in window.recent_files()


def test_session_with_missing_file(window, versions, tmp_path):
    window.add_files(versions)
    saved = window.save_session_to(tmp_path / "s")
    window.close_all()          # no Windows, um PDF aberto não pode ser apagado
    versions[1].unlink()
    window.open_session(saved)
    assert [s.name for s in window.sessions] == ["v1.pdf"]
    assert "v2.pdf" in window.notifications[-1][2]


def test_invalid_session(window, tmp_path):
    bad = tmp_path / "x.pdfcompare"
    bad.write_text("lixo")
    window.open_session(bad)
    assert window.notifications[-1][1] == "Sessão não aberta"


# --- OCR --------------------------------------------------------------------------
def _no_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "check", lambda language="por": ocr.OcrStatus(False, None, (), "sem Tesseract"))


def test_ocr_unavailable_warns_and_keeps_working(window, versions, monkeypatch):
    _no_tesseract(monkeypatch)
    window.add_files(versions)
    window.act_ocr.trigger()
    assert not window.act_ocr.isChecked() and not window.indexer.ocr_enabled
    assert window.notifications[-1] == ("warning", "OCR indisponível", "sem Tesseract")
    assert len(window.sessions) == 2


def test_ocr_enabled_setting_without_tesseract_starts_silently(tmp_path, qtbot, monkeypatch):
    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow

    _no_tesseract(monkeypatch)
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue("ocr/enabled", True)
    w = MainWindow(settings=settings, data_dir=tmp_path)
    qtbot.addWidget(w)
    assert not w.act_ocr.isChecked() and "OCR desativado" in w.statusBar().currentMessage()


def test_ocr_failure_during_indexing_turns_off(window):
    window.act_ocr.setChecked(True)
    window.indexer.ocr_failed.emit("falhou")
    assert not window.act_ocr.isChecked()
    assert "falhou" in window.notifications[-1][2]


def test_ocr_language_setting(window, monkeypatch):
    window.set_ocr_language("por+eng")
    assert window.ocr_language() == "por+eng"
    _no_tesseract(monkeypatch)
    window.act_ocr.setChecked(True)
    window.set_ocr_language("xyz")
    assert not window.act_ocr.isChecked()


@pytest.mark.skipif(not ocr.check("por").available, reason="Tesseract com idioma 'por' não instalado")
def test_ocr_makes_scanned_pdf_searchable(window, qtbot, tmp_path):
    from tests.test_ocr import _scanned_pdf

    window.add_files([_scanned_pdf(tmp_path / "scan.pdf")])
    _wait_index(qtbot, window)
    assert "escaneado" in window.statusBar().currentMessage()
    window.act_ocr.trigger()
    assert window.act_ocr.isChecked()
    qtbot.waitUntil(lambda: not window.indexer.busy, timeout=30000)
    _search(window, "contrato")
    assert window.nav.total_hits == 1
