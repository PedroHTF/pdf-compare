"""Testes de interface (rodam sem abrir janelas, via QT_QPA_PLATFORM=offscreen)."""

import pytest

from app.ui.main_window import FIT_WIDTH


def _wait_index(qtbot, w):
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)


def _search(w, text):
    w.search_bar.edit.setText(text)
    w.search_bar.flush()


@pytest.fixture
def two_pdfs(make_pdf):
    a = make_pdf("a.pdf", texts=["Introdução", "O contrato foi assinado", "Fim"])
    b = make_pdf("b.pdf", texts=["Capa", "Sumário", "Contrato revisado", "Contrato final"])
    return a, b


def test_window_has_app_icon(window):
    assert not window.windowIcon().isNull()
    assert 16 in [s.width() for s in window.windowIcon().availableSizes()]


def test_starts_with_empty_state(window):
    assert window.stack.currentIndex() == 0
    assert not window.act_next.isEnabled()
    assert not window.search_bar.isEnabled()


def test_open_two_pdfs_shows_two_panes(window, two_pdfs):
    window.add_files(two_pdfs)
    assert len(window.panes) == 2
    assert window.stack.currentIndex() == 1
    assert window.search_bar.isEnabled()
    assert "a.pdf" in window.windowTitle()


def test_global_navigation_moves_all_panes(window, two_pdfs):
    window.add_files(two_pdfs)
    window.step(+1)
    assert [p.page_spin.value() for p in window.panes] == [2, 2]
    window.go_last()
    assert window.nav.page_for(0) is None      # a.pdf (3 páginas) já terminou
    assert window.panes[1].page_spin.value() == 4
    assert not window.act_next.isEnabled()


def test_pane_buttons_move_only_that_pdf(window, two_pdfs):
    window.add_files(two_pdfs)
    window.panes[1].btn_next.click()
    assert [p.page_spin.value() for p in window.panes] == [1, 2]
    assert window.act_realign.isEnabled()
    window.realign()
    assert [p.page_spin.value() for p in window.panes] == [1, 1]


def test_page_spin_jumps_in_one_pdf(window, two_pdfs):
    window.add_files(two_pdfs)
    window.panes[1].page_spin.setValue(3)
    assert window.nav.page_for(1) == 2
    assert window.nav.page_for(0) == 0


def test_search_counts_and_navigates_each_pdf(window, qtbot, two_pdfs):
    window.add_files(two_pdfs)
    _wait_index(qtbot, window)
    _search(window, "contrato")
    assert (window.nav.hit_count(0), window.nav.hit_count(1)) == (1, 2)
    assert "3 ocorrências em 2 de 2 PDFs" in window.search_bar.summary.text()
    assert window.panes[0].hit_box.isVisibleTo(window.panes[0])

    window.next_hit_all(+1)
    assert (window.nav.page_for(0), window.nav.page_for(1)) == (1, 2)
    assert window.panes[1].hit_label.text() == "1 de 2"

    window.next_hit_all(+1)
    assert (window.nav.page_for(0), window.nav.page_for(1)) == (1, 3)
    assert window.panes[1].hit_label.text() == "2 de 2"

    window.step(-1)                       # saiu da página da ocorrência: mostra só o total
    assert window.panes[1].hit_label.text() == "2 ocorr."


def test_search_without_results(window, qtbot, two_pdfs):
    window.add_files(two_pdfs)
    _wait_index(qtbot, window)
    _search(window, "inexistente")
    assert window.nav.total_hits == 0
    assert "Nenhuma" in window.search_bar.summary.text()
    assert not window.act_hit_next.isEnabled()


def test_clearing_search_hides_hit_controls(window, qtbot, two_pdfs):
    window.add_files(two_pdfs)
    _wait_index(qtbot, window)
    _search(window, "contrato")
    _search(window, "")
    assert window.nav.total_hits == 0
    assert not window.panes[0].hit_box.isVisibleTo(window.panes[0])


def test_search_before_indexing_finishes_updates_later(window, qtbot, make_pdf):
    big = [make_pdf(f"d{i}.pdf", texts=[f"pagina {p} termo" for p in range(40)]) for i in range(2)]
    window.add_files(big)
    _search(window, "termo")
    _wait_index(qtbot, window)
    assert window.nav.total_hits == 80


def test_limit_of_six_documents(window, make_pdf):
    paths = [make_pdf(f"f{i}.pdf", 1) for i in range(7)]
    window.add_files(paths)
    assert len(window.sessions) == 6
    assert window.notifications and "f6.pdf" in window.notifications[0][2]
    assert not window.act_add.isEnabled()


def test_invalid_and_non_pdf_files_are_reported(window, make_pdf, tmp_path):
    bad = tmp_path / "quebrado.pdf"
    bad.write_bytes(b"isto nao e um pdf")
    txt = tmp_path / "nota.txt"
    txt.write_text("x")
    window.add_files([make_pdf("ok.pdf", 1), bad, txt])
    assert len(window.sessions) == 1
    message = window.notifications[0][2]
    assert "quebrado.pdf" in message and "não ser PDF" in message


def test_single_pdf_shows_add_slot(window, make_pdf):
    window.add_files([make_pdf("so.pdf", 2)])
    assert len(window.panes) == 1
    assert window.grid.count() == 2   # painel + área "Adicione outro PDF"


def test_remove_and_close_all(window, two_pdfs):
    window.add_files(two_pdfs)
    window.panes[0].btn_close.click()
    assert [s.name for s in window.sessions] == ["b.pdf"]
    window.close_all()
    assert window.sessions == [] and window.stack.currentIndex() == 0


def test_zoom_modes(window, two_pdfs):
    window.add_files(two_pdfs)
    window.set_zoom(1.0)
    assert window.panes[0].last_scale == pytest.approx(1.0)
    window.zoom_by(+1)
    assert window.zoom_mode == 1.25
    window.set_zoom(FIT_WIDTH)
    assert window.zoom_combo.currentData() == FIT_WIDTH


def test_linked_scroll_moves_other_panes(window, two_pdfs):
    window.add_files(two_pdfs)
    window.set_zoom(3.0)
    bar0 = window.panes[0].scroll.verticalScrollBar()
    bar1 = window.panes[1].scroll.verticalScrollBar()
    bar0.setValue(bar0.maximum() // 2)
    assert bar1.value() == pytest.approx(bar1.maximum() / 2, abs=2)
