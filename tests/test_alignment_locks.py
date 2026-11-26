"""Alinhamento por conteúdo: remover, travar espaços e alinhar seleções."""

import pytest

from app.services.content_align import AlignmentStore, block_anchors, combined_anchors, PairMatch
from app.services.strip_layout import ManualGap, compute_layouts

from tests.test_alignment_v030 import _contract, contracts  # noqa: F401  (fixture)


# --- disposição (sem interface) -------------------------------------------------------------------
# B perdeu 50 pt de conteúdo antes de y=300 (no A): o B recebe um espaço ali, e a diferença continua
LOST = {1: [(0, 100, 0, 100), (0, 300, 0, 250), (0, 500, 0, 450), (0, 700, 0, 650)]}


def test_removed_gap_is_not_recreated_below():
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=LOST)
    [gap] = b.gaps()
    assert gap.gap.y == pytest.approx(250) and gap.height == pytest.approx(50)

    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=LOST,
                           manual={1: [ManualGap(0, 250.0, 0.0, fixed=True)]})
    assert b.gaps() == [] and a.gaps() == []          # sumiu e não reapareceu na âncora seguinte
    assert b.to_strip(0, 650) == pytest.approx(650)   # a diferença foi aceita até o fim


def test_removed_gap_realigns_when_the_pdfs_meet_again():
    # B tem 50 pt a mais antes de y=300, e perde esses 50 pt antes de y=600 (no A)
    anchors = {1: [(0, 100, 0, 100), (0, 300, 0, 350), (0, 450, 0, 500), (0, 600, 0, 600), (0, 700, 0, 700)]}
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=anchors)
    assert len(a.gaps()) == 1 and len(b.gaps()) == 1
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=anchors,
                           manual={0: [ManualGap(0, 300.0, 0.0, fixed=True)]})
    assert a.gaps() == [] and b.gaps() == []          # nenhum dos dois espaços é preciso
    assert a.to_strip(0, 700) == pytest.approx(b.to_strip(0, 700))


def test_shrunk_gap_keeps_its_height_and_grows_only_for_new_differences():
    anchors = {1: [(0, 100, 0, 100), (0, 300, 0, 250), (0, 500, 0, 450), (0, 700, 0, 610)]}
    # usuário diminuiu o espaço de 50 para 20 pt; mais abaixo o B perde mais 40 pt
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=anchors, manual={1: [(0, 250.0, -30.0)]})
    first, second = b.gaps()
    assert first.height == pytest.approx(20) and first.gap.adjusted
    assert second.gap.y == pytest.approx(610) and second.height == pytest.approx(40)


def test_locked_gap_keeps_height_and_shows_even_when_removed():
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=LOST,
                           manual={1: [ManualGap(0, 250.0, 80.0, fixed=True, locked=True)]})
    [gap] = b.gaps()
    assert gap.height == pytest.approx(80) and gap.gap.locked
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=LOST,
                           manual={1: [ManualGap(0, 250.0, 0.0, fixed=True, locked=True)]})
    [mark] = b.gaps()                                  # removido e travado: marca de altura zero
    assert mark.height == 0 and mark.gap.removed and b.from_strip(mark.top) == (0, pytest.approx(250))


def test_forced_anchor_aligns_even_after_a_removed_gap():
    anchors = {1: LOST[1] + [(0, 600, 0, 550)]}
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=anchors,
                           manual={1: [ManualGap(0, 250.0, 0.0, fixed=True)]},
                           forced={1: [(0, 600, 0, 550)]})
    [gap] = b.gaps()
    assert gap.gap.y == pytest.approx(550)              # o trecho forçado volta a alinhar
    assert a.to_strip(0, 600) == pytest.approx(b.to_strip(0, 550))


# --- armazenamento --------------------------------------------------------------------------------
def test_store_locks_removals_and_blocks(tmp_path):
    store = AlignmentStore(tmp_path / "al")
    key = AlignmentStore.key("fa", "fb")
    store._load(key)["gaps"] = [[0, 10.0, 5.0]]              # formato antigo (sem fixo/travado)
    assert store.manual_gaps(key) == [(0, 10.0, 5.0, False, False)]

    store.remove_gap(key, 1, 200.0)
    assert store.gap_entry(key, 1, 200.3) == (1, 200.0, 0.0, True, False)
    store.lock_gap(key, 2, 300.0, 40.0)
    store.set_gap(key, 2, 300.2, 55.0)                        # mantém fixo e travado
    assert store.gap_entry(key, 2, 300.0) == (2, 300.0, 55.0, True, True)
    assert store.has_locked(key) and store.has_manual(key)

    store.add_block(key, (0, 100.0), (0, 140.0), (0, 120.0), (0, 180.0))
    store.add_line(key, (0, 50.0, 0, 60.0))
    store.add_line(key, (0, 120.0, 0, 90.0))                  # cruza o trecho: o trecho sai
    assert store.manual_blocks(key) == [] and (0, 120.0, 0, 90.0) in store.manual_lines(key)
    store.add_block(key, (1, 10.0), (1, 30.0), (1, 15.0), (1, 70.0))
    assert set(block_anchors(store.manual_blocks(key)[0])) <= set(store.forced_anchors(key))

    store.clear(key)                                          # "Realinhar": só os travados ficam
    again = AlignmentStore(tmp_path / "al")
    assert again.manual_gaps(key) == [(2, 300.0, 55.0, True, True)] and not again.has_manual(key)
    again.unlock_all(key)
    assert again.manual_gaps(key) == [(2, 300.0, 55.0, True, False)] and again.has_manual(key)
    again.remove_block(key, (9, 0, 9, 0, 9, 0, 9, 0))         # inexistente: nada muda


def test_combined_anchors_keeps_block_anchors():
    match = PairMatch(1, 1, [(0, 10, 0, 10), (0, 50, 0, 50), (0, 90, 0, 90)])
    forced = block_anchors((0, 40.0, 0, 60.0, 0, 70.0, 0, 120.0))
    out = combined_anchors(match, forced)
    assert (0, 40.0, 0, 70.0) in out and (0, 60.0, 0, 120.0) in out and (0, 50, 0, 50) not in out


# --- interface ------------------------------------------------------------------------------------
def test_remove_gap_in_window_is_not_recreated(contracts):
    w = contracts
    [gap] = w._layouts[1].gaps()
    w.remove_gap(1, gap.gap)
    w.strip_layouts()
    assert w._layouts[1].gaps() == []                         # antes, o espaço pulava para a página 2
    assert w.act_realign.isEnabled()
    w.realign()
    assert len(w._layouts[1].gaps()) == 1


def test_lock_gap_survives_realign_and_cannot_be_dragged(contracts, qtbot):
    from PySide6.QtCore import QPoint, QPointF, Qt

    w = contracts
    [piece] = w._layouts[0].gaps()
    w.lock_gap(0, piece.gap)
    [piece] = w._layouts[0].gaps()
    assert piece.gap.locked and w.act_unlock_gaps.isEnabled()
    assert not w.act_realign.isEnabled()                      # só há ajustes travados

    pane = w.panes[0]
    pane.scroll.verticalScrollBar().setValue(int(piece.top) - 50)
    canvas = pane.canvas
    y = int(piece.bottom - 3)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(int(canvas.width() / 2), y))
    assert pane._gap_drag is None                             # travado não se arrasta
    canvas.grab()                                             # desenha o cadeado

    w.remove_gap(0, piece.gap)                                # removido, continua travado
    w.realign()
    [mark] = w._layouts[0].gaps()
    assert mark.height == 0 and mark.gap.locked
    canvas.grab()
    w.unlock_all_gaps()
    w.realign()
    [piece] = w._layouts[0].gaps()
    assert piece.height > 30 and not piece.gap.locked and not w.act_unlock_gaps.isEnabled()


def _clause(w, doc, number):
    index = w.indexer.index_for(w.sessions[doc])
    for page, tokens in enumerate(index.pages):
        for t, nxt in zip(tokens, tokens[1:]):
            if t.text == "Clausula" and nxt.text == str(number):
                return page, t.rects[0][1], t.rects[0][3]
    raise AssertionError(number)


def test_align_selections_forces_start_and_end(contracts):
    w = contracts
    w.act_align_regions.trigger()
    assert w.act_align_regions.isChecked() and all(p.region_mode for p in w.panes)

    p5, top5, bottom5 = _clause(w, 0, 5)                      # cláusula 5 na v1 ...
    p8, top8, bottom8 = _clause(w, 1, 8)                      # ... "corresponde" à 8 na v2
    w.panes[0].region_picked.emit(0, p5, top5 + 1, p5, bottom5 + 14)   # as duas linhas da cláusula
    assert w._region_pick is not None and w.panes[0].region_marks[-1][4] == "pending"
    w.panes[0].canvas.grab()
    w.panes[1].region_picked.emit(1, p8, top8 + 1, p8, bottom8 + 14)
    assert w._region_pick is None
    [block] = w.align_store.manual_blocks(w._gap_key(1))
    one, two = w._layouts
    assert one.to_strip(block[0], block[1]) == pytest.approx(two.to_strip(block[4], block[5]), abs=1)
    assert one.to_strip(block[2], block[3]) == pytest.approx(two.to_strip(block[6], block[7]), abs=1)
    assert block[1] < top5 and block[3] > bottom5           # ajustado às linhas inteiras
    assert any(m[4] == "block" for m in w.panes[0].region_marks)
    assert any(m[4] == "block" for m in w.panes[1].region_marks)
    w.panes[1].canvas.grab()

    w.panes[1].last_context_block = None
    ref = w.panes[1].canvas.block_at(two.to_strip(block[4], block[5]) + 2)
    assert ref is not None
    w.remove_block(ref)
    assert w.align_store.manual_blocks(w._gap_key(1)) == []

    w.escape()                                                 # Esc sai do modo
    assert not w.act_align_regions.isChecked() and not any(p.region_mode for p in w.panes)


def test_align_selections_turns_on_continuous_and_content_alignment(window, tmp_path, qtbot):
    a, b = _contract(tmp_path / "x1.pdf"), _contract(tmp_path / "x2.pdf", extra=True)
    window.add_files([a, b])
    qtbot.waitUntil(lambda: not window.indexer.busy, timeout=10000)
    assert not window.act_continuous.isChecked()
    window.act_align_regions.trigger()
    assert window.act_continuous.isChecked() and window.act_content_align.isChecked()
    assert window.act_align_regions.isChecked()
    window.act_continuous.trigger()                            # saiu da rolagem contínua: desliga
    assert not window.act_align_regions.isChecked()


def test_drag_selection_in_canvas_emits_region(contracts, qtbot):
    from PySide6.QtCore import QPoint, Qt

    w = contracts
    w.act_align_regions.trigger()
    pane = w.panes[0]
    got = []
    pane.region_picked.connect(lambda *args: got.append(args))
    canvas = pane.canvas
    x = int(canvas.width() / 2)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 80))
    qtbot.mouseMove(canvas, QPoint(x, 140))
    assert pane.region_drag is not None
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 140))
    assert pane.region_drag is None and len(got) == 1
    index, p0, y0, p1, y1 = got[0]
    assert index == 0 and (p0, y0) < (p1, y1)
