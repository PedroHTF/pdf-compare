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
