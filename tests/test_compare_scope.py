"""O que entra na comparação: cabeçalho/rodapé, páginas ignoradas, só a página atual,
pontos alinhados à mão e a roda do mouse passando de página."""

import fitz
import pytest

from app.services.compare_scope import (
    CompareScope,
    FilteredIndex,
    IgnoredPagesStore,
    format_pages,
    page_geometry,
    parse_pages,
    scoped_index,
)
from app.services.preferences import CompareSettings
from app.services.text_diff import ADDED, diff_pair, report_entries
from app.services.text_index import DocumentIndex


def _doc(path, pages):
    """pages: lista de (cabeçalho, [linhas do corpo], rodapé)."""
    doc = fitz.open()
    for header, body, footer in pages:
        page = doc.new_page()        # 595 x 842
        if header:
            page.insert_text((60, 40), header, fontsize=10)
        y = 120
        for line in body:
            page.insert_text((60, y), line, fontsize=11)
            y += 18
        if footer:
            page.insert_text((60, 820), footer, fontsize=10)
    doc.save(str(path))
    doc.close()
    return path


BODY = [f"Linha {k} do corpo do contrato com texto igual" for k in range(5)]


def _pair(tmp_path):
    a = _doc(tmp_path / "a.pdf", [("Empresa Alfa revisao 1", BODY, "Pagina 1 de 2"),
                                  ("Empresa Alfa revisao 1", BODY, "Pagina 2 de 2")])
    b = _doc(tmp_path / "b.pdf", [("Empresa Beta revisao 7", BODY, "Folha 1 / 2"),
                                  ("Empresa Beta revisao 7", BODY, "Folha 2 / 2")])
    return a, b


# --- serviço ---------------------------------------------------------------------------------------
def test_parse_and_format_pages():
    assert parse_pages("1-3, 7", 10) == {0, 1, 2, 6}
    assert parse_pages(" 5–4 ;9 ", 10) == {3, 4, 8}
    assert parse_pages("", 3) == set()
    for bad in ("0", "11", "a", "2-x"):
        with pytest.raises(ValueError):
            parse_pages(bad, 10)
    assert format_pages({0, 1, 2, 6, 8, 9}) == "1-3, 7, 9-10" and format_pages([]) == ""


def test_ignored_pages_store(tmp_path):
    store = IgnoredPagesStore(tmp_path / "x" / "ign.json")
    assert store.toggle("fp", 2) and store.toggle("fp", 0)
    assert not store.toggle("fp", 2)
    assert IgnoredPagesStore(tmp_path / "x" / "ign.json").pages("fp") == {0}
    store.set_pages("fp", [])
    assert IgnoredPagesStore(tmp_path / "x" / "ign.json").pages("fp") == frozenset()
    assert store.pages(None) == frozenset()


def test_header_and_footer_are_left_out(tmp_path):
    a, b = _pair(tmp_path)
    da, db = fitz.open(str(a)), fitz.open(str(b))
    ia, ib = DocumentIndex.build(da), DocumentIndex.build(db)
    marks_a, marks_b = diff_pair(ia, ib)
    assert marks_a and marks_b                                    # cabeçalhos e rodapés diferentes
    scope = CompareScope(header=10, footer=5)
    fa = scoped_index(ia, scope, page_geometry(da))
    fb = scoped_index(ib, scope, page_geometry(db))
    assert isinstance(fa, FilteredIndex) and fa.complete
    assert diff_pair(fa, fb) == ([], []) and report_entries(fa, fb) == []
    assert len(fa.pages[0]) == len(ia.pages[0]) - 4 - 4          # 4 palavras no cabeçalho e no rodapé
    assert scoped_index(ia, CompareScope(), []) is ia             # nada a ignorar: o próprio índice


def test_filtered_index_follows_the_index_being_read_and_rotation(tmp_path):
    a, _ = _pair(tmp_path)
    doc = fitz.open(str(a))
    partial = DocumentIndex(doc.page_count)
    from app.services.text_index import extract_tokens

    partial.add_page(extract_tokens(doc[0]))
    view = FilteredIndex(partial, CompareScope(10, 0), page_geometry(doc), ignored=[1])
    assert len(view.pages) == 1 and not view.complete
    partial.add_page(extract_tokens(doc[1]))
    assert len(view.pages) == 2 and view.pages[1] == [] and view.complete     # página 2 ignorada

    doc[0].set_rotation(90)          # girada: o "topo" da tela é a esquerda da página original
    rotated = FilteredIndex(partial, CompareScope(15, 0), page_geometry(doc))
    assert len(rotated.pages[0]) < len(partial.pages[0])


def test_sync_points_split_the_comparison():
    from app.services.text_index import Token

    def index(lines):
        idx = DocumentIndex(1)
        idx.add_page([Token(w, [(60 + 30 * k, 100 + 20 * n, 80 + 30 * k, 110 + 20 * n)], n)
                      for n, line in enumerate(lines) for k, w in enumerate(line.split())])
        return idx

    a = index(["capitulo um", "texto x", "capitulo dois", "texto y"])
    b = index(["capitulo dois", "texto y", "capitulo um", "texto x"])
    free = diff_pair(a, b)
    # sozinha, a comparação casa "capitulo um"; o usuário alinhou "capitulo dois" (linha 3 do a, y=140)
    # com "capitulo dois" (linha 1 do b, y=100)
    forced = diff_pair(a, b, sync=[(0, 139.0, 0, 99.0)])
    assert forced != free
    marks_a, marks_b = forced
    assert marks_a and all(m.rects[0][1] < 140 for m in marks_a)    # no a: "capitulo um" saiu
    assert marks_b and all(m.rects[0][1] >= 140 for m in marks_b)   # no b: "capitulo um" foi incluído
    assert {m.kind for m in marks_b} == {ADDED}
    assert diff_pair(a, b, sync=[(0, 500.0, 0, 0.0), (0, 0.0, 0, 500.0)])   # fora de ordem: não quebra


# --- interface ------------------------------------------------------------------------------------
def _idle(qtbot, w):
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)
    qtbot.waitUntil(lambda: not w.runner.busy, timeout=10000)


def test_ignore_header_footer_in_window(window, tmp_path, qtbot):
    w = window
    w.add_files(list(_pair(tmp_path)))
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert w.nav.total_diffs > 0
    w.set_compare_settings(CompareSettings(header=10, footer=5))
    _idle(qtbot, w)
    assert w.nav.total_diffs == 0 and "sem cabeçalho e rodapé" in w.diff_label.text()
    assert w.scope_marks(0, 0) == (False, 10, 5)
    w.panes[0].grab()                                        # desenha as faixas ignoradas


def test_ignore_page_from_menu_and_dialog(window, tmp_path, qtbot):
    from PySide6.QtCore import QTimer

    w = window
    a = _doc(tmp_path / "a.pdf", [("", ["Indice", "1 Introducao ..... 2"], ""), ("", BODY, "")])
    b = _doc(tmp_path / "b.pdf", [("", ["Sumario novo", "1 Intro ..... 3"], ""), ("", BODY, "")])
    w.add_files([a, b])
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert any(m.page == 0 for m in w.nav.diffs[1])
    w.toggle_ignored_page(0, 0)
    w.toggle_ignored_page(1, 0)
    _idle(qtbot, w)
    assert w.nav.total_diffs == 0 and "2 páginas ignoradas" in w.diff_label.text()
    assert w.scope_marks(1, 0) == (True, 0, 0) and w.scope_marks(1, 1) is None
    w.panes[1].grab()

    def fill():
        edits = w._ignored_edits
        edits[0].setText("9")                       # inválido: o diálogo avisa e não fecha
        from PySide6.QtWidgets import QDialogButtonBox

        box = w._ignored_dialog.findChild(QDialogButtonBox)
        box.accepted.emit()
        assert w._ignored_dialog.isVisible()
        edits[0].setText("")
        edits[1].setText("")
        box.accepted.emit()

    QTimer.singleShot(0, fill)
    w.edit_ignored_pages()
    _idle(qtbot, w)
    assert w._ignored(0) == frozenset() and w.nav.total_diffs > 0


def test_compare_only_current_page(window, tmp_path, qtbot):
    w = window
    a = _doc(tmp_path / "a.pdf", [("", ["pagina um alfa"], ""), ("", ["pagina dois igual"], ""),
                                  ("", ["pagina tres gama"], "")])
    b = _doc(tmp_path / "b.pdf", [("", ["pagina um ALFA"], ""), ("", ["pagina dois igual"], ""),
                                  ("", ["pagina tres GAMA"], "")])
    w.add_files([a, b])
    _idle(qtbot, w)
    w.act_diff_page.trigger()                       # escolher no menu liga a comparação
    _idle(qtbot, w)
    assert w.act_diff.isChecked() and w.compare.page_only
    assert [b.ranges for b in w.runner.batches] == [((0, 1), (0, 1))]
    assert {m.page for m in w.nav.diffs[1]} == {0} and "só a página atual" in w.diff_label.text()
    w.step(+1)
    _idle(qtbot, w)
    assert [b.ranges for b in w.runner.batches] == [((1, 2), (1, 2))] and w.nav.total_diffs == 0
    w.step(+1)
    _idle(qtbot, w)
    assert {m.page for m in w.nav.diffs[1]} == {2}
    w.act_diff_whole.trigger()
    _idle(qtbot, w)
    assert not w.compare.page_only and {m.page for m in w.nav.diffs[1]} == {0, 2}


def test_comparison_follows_aligned_passages(window, tmp_path, qtbot):
    from tests.test_alignment_v030 import _contract

    w = window
    w.add_files([_contract(tmp_path / "c1.pdf"), _contract(tmp_path / "c2.pdf", extra=True)])
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)
    w.act_content_align.trigger()
    w.set_compare_settings(CompareSettings(batch_size=0))
    assert w._sync_points() == {}
    w.align_store.add_block(w._gap_key(1), (0, 100.0), (0, 130.0), (0, 140.0), (0, 170.0))
    points = w._sync_points()
    assert list(points) == [(0, 1)] and len(points[(0, 1)]) == 2
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert w.runner._sync == points and w.runner._sync_key(0, 1)
    w.set_compare_settings(CompareSettings(batch_size=0, follow_alignment=False))
    assert w._sync_points() == {}


def test_wheel_past_the_page_edge_turns_the_page(window, tmp_path, qtbot):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    w = window
    pages = [("", [f"pagina {k}"] * 30, "") for k in range(3)]
    w.add_files([_doc(tmp_path / "a.pdf", pages), _doc(tmp_path / "b.pdf", pages)])
    w.set_zoom(2.0)
    pane = w.panes[0]

    def wheel(dy):
        event = QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, dy),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(pane.scroll.viewport(), event)

    bar = pane.scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    wheel(-120)                                      # além do fim: próxima página, nos dois
    assert w.nav.page_for(0) == 1 and w.nav.page_for(1) == 1
    qtbot.wait(20)
    assert bar.value() == 0
    wheel(+120)                                      # além do início: volta e mostra o fim da anterior
    assert w.nav.page_for(0) == 0
    qtbot.wait(20)
    assert bar.value() == bar.maximum()
    w.act_wheel_flip.trigger()                       # desligado: não passa de página
    bar.setValue(bar.maximum())
    wheel(-120)
    assert w.nav.page_for(0) == 0
