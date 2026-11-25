"""Disposição da rolagem contínua com espaços de alinhamento."""

import pytest

from app.services.content_align import PairMatch, combined_anchors
from app.services.strip_layout import PAGE_SPACING, compute_layouts


def test_no_alignment_just_stacks_pages():
    [layout] = compute_layouts([[100, 200]], [2.0])
    assert [(p.page, p.top, p.height) for p in layout.pieces] == [(0, 0, 200), (1, 200 + PAGE_SPACING, 400)]
    assert layout.height == 600 + PAGE_SPACING
    assert layout.to_strip(1, 50) == 200 + PAGE_SPACING + 100
    assert layout.from_strip(200 + PAGE_SPACING + 100) == (1, 50)


def test_extra_paragraph_in_other_pdf_opens_space_in_primary():
    # B tem um parágrafo de 60 pt a mais antes da linha que em A está em y=200
    anchors = {1: [(0, 100, 0, 100), (0, 200, 0, 260)]}
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=anchors)
    [gap] = a.gaps()
    assert gap.gap.page == 0 and gap.gap.y == pytest.approx(200) and gap.height == pytest.approx(60)
    assert b.gaps() == []
    assert a.to_strip(0, 200) == pytest.approx(b.to_strip(0, 260))       # linhas iguais na mesma altura
    assert a.to_strip(0, 150) == pytest.approx(150)                         # antes do espaço nada muda
    assert a.from_strip(200 + 10) == (0, pytest.approx(200))   # dentro do espaço: o ponto logo abaixo dele


def test_removed_content_opens_space_in_the_other_and_third_pdf_follows():
    anchors = {1: [(0, 100, 0, 100), (0, 300, 0, 200)], 2: [(0, 100, 0, 100), (0, 300, 0, 300)]}
    layouts = compute_layouts([[800]] * 3, [1.0] * 3, anchors=anchors)
    assert [len(l.gaps()) for l in layouts] == [0, 1, 0]
    assert layouts[1].to_strip(0, 200) == pytest.approx(300)

    # o PDF 1 tem conteúdo a mais: espaço no principal e no PDF 2, no mesmo ponto
    anchors = {1: [(0, 100, 0, 100), (0, 300, 0, 400)], 2: [(0, 100, 0, 100), (0, 300, 0, 300)]}
    p, one, two = compute_layouts([[800]] * 3, [1.0] * 3, anchors=anchors)
    assert p.gaps()[0].height == pytest.approx(100) and two.gaps()[0].height == pytest.approx(100)
    assert p.to_strip(0, 300) == pytest.approx(one.to_strip(0, 400)) == pytest.approx(two.to_strip(0, 300))


def test_small_drift_is_ignored_and_scales_differ():
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors={1: [(0, 100, 0, 103)]})
    assert a.gaps() == [] and b.gaps() == []
    # PDF 1 com o dobro da escala: os espaços são calculados em pixels de cada um
    a, b = compute_layouts([[800], [400]], [1.0, 2.0], anchors={1: [(0, 300, 0, 100)]})
    assert a.to_strip(0, 300) == pytest.approx(b.to_strip(0, 100), abs=0.01)


def test_manual_gaps_add_to_auto_and_last_until_next_anchor():
    anchors = {1: [(0, 100, 0, 100), (0, 200, 0, 260), (0, 500, 0, 560)]}
    # usuário aumentou em 20 pt o espaço automático (fica em y=200 no principal)
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors=anchors, manual={0: [(0, 200.0, 20.0)]})
    [gap] = a.gaps()
    assert gap.height == pytest.approx(80) and gap.gap.manual == pytest.approx(20)
    # a próxima âncora compensa: a partir dela tudo volta a ficar alinhado
    assert a.to_strip(0, 500) == pytest.approx(b.to_strip(0, 560))
    assert b.gaps()[0].height == pytest.approx(20)

    # espaço manual num ponto sem âncora (ex.: PDF escaneado): continua até o fim
    a, b = compute_layouts([[800], [800]], [1.0, 1.0], anchors={}, manual={1: [(0, 50.0, 30.0)]})
    assert b.gaps()[0].height == pytest.approx(30) and b.to_strip(0, 700) == pytest.approx(730)


def test_gap_across_pages():
    anchors = {1: [(0, 100, 0, 100), (1, 50, 1, 150)]}
    a, b = compute_layouts([[400, 400], [400, 400]], [1.0, 1.0], anchors=anchors)
    assert a.gaps()[0].gap.page == 1
    assert a.to_strip(1, 50) == pytest.approx(b.to_strip(1, 150))
    pages = [p.page for p in a.pieces if p.page is not None]
    assert pages == [0, 1, 1]       # a página 2 foi cortada no ponto do espaço


def test_combined_anchors_drop_crossing_auto_ones():
    match = PairMatch(2, 2, [(0, 10, 0, 10), (0, 50, 1, 20), (1, 30, 1, 40)])
    manual = [(0, 60, 0, 80)]
    assert combined_anchors(match, manual) == [(0, 10, 0, 10), (0, 60, 0, 80), (1, 30, 1, 40)]
