"""Etapa 3 da v0.3.0: referência da comparação, cadeia, alinhamento por conteúdo e rolagem contínua."""

import pytest

from app.services.diff_batches import plan_batches, plan_batches_from_rows
from app.services.preferences import CompareSettings
from app.services.text_diff import ADDED, CHANGED, REMOVED, DiffMark, merge_results


def _idle(qtbot, w):
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)
    qtbot.waitUntil(lambda: not w.runner.busy, timeout=10000)


def _kinds(marks):
    return sorted({m.kind for m in marks})


# --- referência e cadeia ------------------------------------------------------------------------
def test_merge_results_for_reference_and_chain():
    r = DiffMark(0, ((0, 0, 1, 1),), REMOVED)
    a = DiffMark(0, ((2, 2, 3, 3),), ADDED)
    # referência = PDF 1: o 1 mostra o que foi removido (sem repetir), os outros o que foi incluído
    out = merge_results(3, [(1, 0), (1, 2)], [([r], [a]), ([r], [a])])
    assert out == [[a], [r], [a]]
    # cadeia 0→1→2: só o primeiro mostra remoções; o do meio mostra o que recebeu do anterior
    out = merge_results(3, [(0, 1), (1, 2)], [([r], [a]), ([r], [])])
    assert out == [[r], [a], []]


def test_plan_batches_with_another_primary():
    batches = plan_batches([10, 12, 10], [-1, 0, 1], 5, primary=1)
    assert [b.ref_range for b in batches] == [(0, 5), (5, 10), (10, 12)]
    assert batches[1].ranges == ((4, 9), (5, 10), (6, 10))


def test_plan_batches_from_rows_follow_inserted_pages():
    # PDF 1 tem uma página a mais (incluída depois da página 2 do PDF 0) e perdeu a página 4
    rows = [(0, 0), (1, 1), (2, 2), (None, 3), (3, 4), (4, None), (5, 5)]
    batches = plan_batches_from_rows(rows, [6, 6], 3)
    assert [b.ranges for b in batches] == [((0, 3), (0, 4)), ((3, 6), (4, 6))]


@pytest.fixture
def three(window, make_pdf):
    a = make_pdf("v1.pdf", texts=["alfa beta gama"])
    b = make_pdf("v2.pdf", texts=["alfa BETA gama"])
    c = make_pdf("v3.pdf", texts=["alfa BETA gama delta"])
    window.set_compare_settings(CompareSettings(batch_size=0))
    window.add_files([a, b, c])
    return window


def test_choose_reference(three, qtbot):
    w = three
    assert w.panes[0].role_label.text() == "Referência" and not w.panes[1].role_label.isVisibleTo(w)
    w.act_diff.trigger()
    _idle(qtbot, w)
    assert _kinds(w.nav.diffs[0]) == [CHANGED] and _kinds(w.nav.diffs[2]) == [ADDED, CHANGED]

    w.set_reference(1)
    _idle(qtbot, w)
    assert w.runner.pairs == [(1, 0), (1, 2)]
    assert w.panes[1].role_label.text() == "Referência" and not w.panes[0].role_label.isVisibleTo(w)
    assert _kinds(w.nav.diffs[0]) == [CHANGED]          # v1 comparado com v2
    assert _kinds(w.nav.diffs[1]) == [CHANGED]          # a referência mostra o que mudou nela
    assert _kinds(w.nav.diffs[2]) == [ADDED]            # v3 só acrescentou "delta"
    assert "em relação a v2.pdf" in w.diff_label.text()

    w.remove_document(1)                                # fechou a referência: volta ao 1º PDF
    assert w.reference_index() == 0 and w.panes[0].role_label.text() == "Referência"


def test_chain_mode(three, qtbot):
    w = three
    w.act_diff.trigger()
    w.set_chain_mode(True)
    _idle(qtbot, w)
    assert w.act_chain.isChecked() and w.runner.pairs == [(0, 1), (1, 2)]
    assert [p.role_label.text() for p in w.panes] == ["1º", "2º", "3º"]
    assert _kinds(w.nav.diffs[2]) == [ADDED]            # v3 comparado com v2, não com v1
    assert "Em cadeia" in w.diff_label.text()

    w.set_reference(2)                                  # escolher uma referência sai da cadeia
    _idle(qtbot, w)
    assert not w.chain_mode and w.runner.pairs == [(2, 0), (2, 1)]


# --- alinhamento por conteúdo: serviço ------------------------------------------------------------
from app.services.content_align import (  # noqa: E402
    AlignmentStore,
    PairMatch,
    _increasing_subset,
    align_pages,
    build_rows,
    match_lines,
)


def _match(pages_a, pages_b, votes):
    return PairMatch(pages_a, pages_b, [], dict(votes))


def test_align_pages_detects_inserted_and_removed_pages():
    # B tem uma página nova depois da 2ª e perdeu a 4ª página de A
    votes = {(0, 0): 9, (1, 1): 9, (2, 3): 9, (4, 4): 9, (1, 3): 1}
    assert align_pages(_match(5, 5, votes)) == [(0, 0), (1, 1), (None, 2), (2, 3), (3, None), (4, 4)]


def test_align_pages_pairs_leftovers_in_order_and_respects_manual():
    # sem texto em comum (ex.: PDFs escaneados): pareia na ordem
    assert align_pages(_match(3, 4, {})) == [(0, 0), (1, 1), (2, 2), (None, 3)]
    # página 1 de A muito alterada: fica com a página 1 de B, que sobrou entre as pareadas
    assert align_pages(_match(3, 3, {(0, 0): 5, (2, 2): 5})) == [(0, 0), (1, 1), (2, 2)]
    # par fixado à mão tem prioridade sobre os votos
    pairs = align_pages(_match(3, 4, {(0, 0): 5, (1, 1): 5, (2, 2): 5}), manual=[(1, 2)])
    assert pairs == [(0, 0), (None, 1), (1, 2), (2, 3)]


def test_increasing_subset_prefers_heavier_consistent_pairs():
    chosen = _increasing_subset([(0, 0, 5), (1, 5, 1), (2, 1, 5), (3, 2, 5)])
    assert chosen == [(0, 0), (2, 1), (3, 2)]


def test_build_rows_places_insertions_side_by_side():
    pairs = {1: [(0, 0), (None, 1), (1, 2)], 2: [(0, 0), (None, 1), (None, 2), (1, 3)]}
    rows = build_rows([2, 3, 4], 0, pairs)
    assert rows == [(0, 0, 0), (None, 1, 1), (None, None, 2), (1, 2, 3)]
    rows = build_rows([3, 2], 1, {0: [(0, 0), (None, 1), (1, 2)]})   # outro PDF como principal
    assert rows == [(0, 0), (1, None), (2, 1)]


def test_match_lines_from_real_pdfs(make_pdf):
    import fitz

    from app.services.text_index import DocumentIndex

    def index(path):
        with fitz.open(path) as doc:
            return DocumentIndex.build(doc)

    a = index(make_pdf("a.pdf", texts=["um", "dois", "tres"]))
    b = index(make_pdf("b.pdf", texts=["um", "novo", "dois", "tres"]))
    m = match_lines(a, b)
    assert m.votes == {(0, 0): 1, (1, 2): 1, (2, 3): 1}
    assert [(pa, pb) for pa, _, pb, _ in m.anchors] == [(0, 0), (1, 2), (2, 3)]
    assert align_pages(m) == [(0, 0), (None, 1), (1, 2), (2, 3)]


def test_alignment_store(tmp_path):
    store = AlignmentStore(tmp_path / "al")
    key = AlignmentStore.key("fa", "fb")
    assert key != AlignmentStore.key("fb", "fa") and not store.has_manual(key)
    store.fix_pages(key, 2, 5)
    store.fix_pages(key, 4, 3)          # fora de ordem com (2, 5): substitui
    assert store.manual_pages(key) == [(4, 3)]
    store.fix_pages(key, 1, 1)
    store.set_gap(key, 3, 100.0, 24.0)
    store.add_line(key, (1, 50.0, 2, 80.0))
    again = AlignmentStore(tmp_path / "al")
    assert again.manual_pages(key) == [(1, 1), (4, 3)]
    assert again.manual_gaps(key) == [(3, 100.0, 24.0, False, False)] and again.manual_lines(key) == [(1, 50.0, 2, 80.0)]
    again.set_gap(key, 3, 100.4, 0)     # altura 0 remove o espaço
    assert again.manual_gaps(key) == []
    again.clear(key)
    assert not AlignmentStore(tmp_path / "al").has_manual(key)


# --- alinhamento por conteúdo: interface -----------------------------------------------------------
CHAPTERS = [f"Capitulo {k} texto exclusivo {k * 7} fim" for k in range(6)]


@pytest.fixture
def versions(window, make_pdf):
    a = make_pdf("v1.pdf", texts=CHAPTERS)
    # v2: página nova depois do capítulo 1, capítulo 4 removido, capítulo 5 alterado
    b = make_pdf("v2.pdf", texts=CHAPTERS[:2] + ["Pagina totalmente nova"] + CHAPTERS[2:4]
                 + ["Capitulo 5 texto exclusivo 35 ALTERADO"])
    window.set_compare_settings(CompareSettings(batch_size=0))
    window.add_files([a, b])
    qtbot_wait = window
    return window


def _align(w, qtbot):
    qtbot.waitUntil(lambda: not w.indexer.busy, timeout=10000)
    w.act_content_align.trigger()
    assert w.nav.by_rows


def test_content_alignment_rows_and_blank_panes(versions, qtbot):
    w = versions
    _align(w, qtbot)
    assert w.nav.rows == [(0, 0), (1, 1), (None, 2), (2, 3), (3, 4), (4, None), (5, 5)]
    w.go_first()
    w.step(+2)
    assert (w.nav.page_for(0), w.nav.page_for(1)) == (None, 2)
    assert "Sem página correspondente" in w.panes[0].image.text()
    w.step(+3)
    assert (w.nav.page_for(0), w.nav.page_for(1)) == (4, None)
    w.step(+1)
    assert (w.nav.page_for(0), w.nav.page_for(1)) == (5, 5)

    w.act_content_align.trigger()                      # desligar volta ao modo por página
    assert not w.nav.by_rows and w.nav.page_for(0) == 5


def test_content_alignment_with_text_comparison(versions, qtbot):
    w = versions
    _align(w, qtbot)
    w.act_diff.trigger()
    _idle(qtbot, w)
    pages = sorted({m.page for m in w.nav.diffs[1]})
    assert pages == [2, 5]                             # só a página nova e o capítulo 5 alterado
    assert sorted({m.page for m in w.nav.diffs[0]}) == [4, 5]   # capítulo 4 removido
    w.go_first()
    w.act_diff_next.trigger()                          # F7 vai à próxima diferença de qualquer PDF
    assert w.nav.page_for(1) == 2


def test_manual_alignment_is_saved_and_realign_undoes(versions, qtbot, tmp_path):
    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow

    w = versions
    _align(w, qtbot)
    w.go_first()
    w.step(+1)                                         # capítulo 1 ao lado do capítulo 1
    w._on_pane_step(1, +1)                             # usuário: "a página 3 de v2 fica aqui"
    assert (w.nav.page_for(0), w.nav.page_for(1)) == (1, 2)
    assert w.act_realign.isEnabled() and "fixada" in w.statusBar().currentMessage()

    again = MainWindow(QSettings(str(tmp_path / "s2.ini"), QSettings.Format.IniFormat), data_dir=w.data_dir)
    again._notify = lambda *a: None
    qtbot.addWidget(again)
    again.act_content_align.setChecked(True)
    again.add_files([s.path for s in w.sessions])
    qtbot.waitUntil(lambda: not again.indexer.busy, timeout=10000)
    assert (1, 2) in again.nav.rows                    # o ajuste manual volta com os mesmos PDFs

    w.realign()
    assert (1, 1) in w.nav.rows and not w.act_realign.isEnabled()


def test_content_alignment_follows_reference(versions, qtbot):
    w = versions
    _align(w, qtbot)
    w.set_reference(1)
    assert w.nav.rows == [(0, 0), (1, 1), (None, 2), (2, 3), (3, 4), (4, None), (5, 5)]
    assert w.runner.pairs == [] or w.runner.pairs == [(1, 0)]
    w.panes[0].page_jump.emit(0, 3)                    # página digitada no painel, alinhado: fixa o par
    assert w.nav.page_for(0) == 3


# --- rolagem contínua ---------------------------------------------------------------------------------
def _contract(path, extra=False, drop=False):
    import fitz

    lines = []
    for k in range(1, 31):
        if drop and k == 11:
            continue
        lines += [f"Clausula {k}. O contratante se obriga a cumprir o item {k}",
                  f"conforme o anexo {k} e as condicoes gerais numero {k * 3}.", ""]
        if extra and k == 3:
            lines += ["Paragrafo NOVO incluido na versao 2 sobre multas e prazos",
                      "adicionais que nao existiam na versao anterior do contrato.", ""]
    doc = fitz.open()
    page, y = doc.new_page(), 60
    for line in lines:
        if y > 780:
            page, y = doc.new_page(), 60
        page.insert_text((60, y), line, fontsize=11)
        y += 16
    doc.save(str(path))
    return path


@pytest.fixture
def contracts(window, tmp_path, qtbot):
    a = _contract(tmp_path / "c1.pdf")
    b = _contract(tmp_path / "c2.pdf", extra=True, drop=True)
    window.resize(1200, 800)
    window.add_files([a, b])
    qtbot.waitUntil(lambda: not window.indexer.busy, timeout=10000)
    window.act_content_align.trigger()
    window.act_continuous.trigger()
    return window


def test_continuous_aligned_layout_opens_spaces_where_content_differs(contracts):
    w = contracts
    assert all(p.continuous and p.scroll.widget() is p.canvas for p in w.panes)
    one, two = w._layouts
    [gap_one] = one.gaps()
    [gap_two] = two.gaps()
    assert gap_one.gap.page == 0 and 180 < gap_one.gap.y < 200      # antes da cláusula 4 (parágrafo novo na v2)
    assert gap_two.gap.page == 0 and 560 < gap_two.gap.y < 600      # antes da cláusula 12 (cláusula 11 removida)
    # a cláusula 12 fica na mesma altura nos dois
    def clause_top(doc, number):
        index = w.indexer.index_for(w.sessions[doc])
        for page, tokens in enumerate(index.pages):
            for t, nxt in zip(tokens, tokens[1:]):
                if t.text == "Clausula" and nxt.text == str(number):
                    return page, t.rects[0][1]
        raise AssertionError(number)

    for number in (12, 20, 28):   # inclusive na 2ª página (as páginas quebram em pontos diferentes)
        assert one.to_strip(*clause_top(0, number)) == pytest.approx(two.to_strip(*clause_top(1, number)), abs=4)


def test_continuous_linked_scroll_and_navigation(contracts):
    w = contracts
    w.panes[0].scroll.verticalScrollBar().setValue(300)       # o usuário rola o 1º PDF
    assert w.panes[1].strip_value() == 300 and w.nav.page_for(0) == 0
    w.panes[0].scroll.verticalScrollBar().setValue(0)
    w.go_last()                                                 # navegação pela barra rola os dois
    assert w.panes[0].strip_value() == w.panes[1].strip_value()
    w.act_continuous.trigger()                                  # volta a uma página por vez
    assert all(not p.continuous and p.scroll.widget() is p.image for p in w.panes)
    assert w.nav.page_for(0) is not None


def test_gap_handle_insert_remove_and_realign(contracts, qtbot):
    w = contracts
    one = w._layouts[0]
    [piece] = one.gaps()
    before = piece.height
    w.panes[0].gap_resized.emit(0, piece.gap.page, piece.gap.y, 20.0)   # arrastou a alça +20 pt
    [piece] = w._layouts[0].gaps()
    assert piece.height == pytest.approx(before + 20 * w._layouts[0].scale)
    assert w.act_realign.isEnabled()

    w.insert_gap(1, 0, 100.0)
    assert any(abs(g.gap.y - 100) < 1 for g in w._layouts[1].gaps())
    w.remove_gap(1, next(g.gap for g in w._layouts[1].gaps() if abs(g.gap.y - 100) < 1))
    assert all(g.height < 1 for g in w._layouts[1].gaps() if abs(g.gap.y - 100) < 1)

    w.realign()
    [piece] = w._layouts[0].gaps()
    assert piece.height == pytest.approx(before) and not w.act_realign.isEnabled()


def test_align_passage_with_another_pdf(contracts):
    w = contracts
    w.start_pick(0, 0, 400.0)
    assert w.panes[1].pick_mode and not w.panes[0].pick_mode
    w.panes[1].point_picked.emit(1, 0, 300.0)                   # "este trecho" da v1 = esse da v2
    assert not w.panes[1].pick_mode
    one, two = w._layouts
    assert one.to_strip(0, 400) == pytest.approx(two.to_strip(0, 300), abs=2)

    w.start_pick(1, 0, 100.0)
    w.escape()                                                  # Esc cancela
    assert w._pick is None and not w.panes[0].pick_mode


def test_draw_mark_in_continuous_mode(contracts, qtbot):
    from PySide6.QtCore import QPoint, Qt

    from app.services import annotations as am

    w = contracts
    pane = w.panes[1]
    layout = w._layouts[1]

    def at(page, x, y):
        return QPoint(round(pane.canvas.page_left(page) + x * layout.scale), round(layout.to_strip(page, y)))

    w.set_tool(am.RECT)
    qtbot.mousePress(pane.canvas, Qt.MouseButton.LeftButton, pos=at(1, 100, 100))
    qtbot.mouseMove(pane.canvas, at(1, 200, 160))
    qtbot.mouseRelease(pane.canvas, Qt.MouseButton.LeftButton, pos=at(1, 200, 160))
    [mark] = w.document_annotations(1)
    assert mark.page == 1 and mark.rects[0] == pytest.approx((100, 100, 200, 160), abs=1.5)


def test_continuous_without_content_alignment_scrolls_by_page(window, tmp_path, qtbot):
    w = window
    a = _contract(tmp_path / "c1.pdf")
    b = _contract(tmp_path / "c2.pdf", extra=True)
    w.add_files([a, b])
    w.act_continuous.trigger()
    one, two = w._layouts
    assert one.gaps() == [] and two.gaps() == []
    w.panes[0].scroll.verticalScrollBar().setValue(round(one.page_top[1]))
    assert w.panes[1].top_page() == 1 and w.nav.page_for(0) == 1
