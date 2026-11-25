"""Disposição da rolagem contínua: páginas empilhadas e espaços que alinham o conteúdo.

Na rolagem contínua, cada PDF é uma faixa vertical com as páginas uma embaixo da
outra. Com o alinhamento por conteúdo ligado, são inseridos espaços vazios para
que as linhas iguais fiquem na mesma altura em todos os PDFs: se um PDF tem um
parágrafo a mais, os outros recebem um espaço do tamanho desse parágrafo, no
lugar onde ele estaria.

Âncoras: pares (página, y) de linhas iguais entre o PDF principal e cada outro
PDF (ver content_align). O cálculo percorre as âncoras em ordem; quando um lado
está "atrasado", recebe um espaço na posição da âncora.

Espaços manuais (definidos pelo usuário) ficam onde ele colocou e valem até a
próxima âncora; se estão no mesmo ponto de um espaço automático, somam-se a ele.

Unidades: pontos do PDF para posições dentro da página; pixels de tela para a
faixa (cada PDF pode ter a própria escala). Sem dependência de interface gráfica.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.content_align import Anchor

PAGE_SPACING = 10.0     # pixels entre páginas
TOLERANCE = 6.0         # diferenças menores (pixels) são ignoradas
ANCHOR_MARGIN = 0.0     # as âncoras já vêm no ponto de corte entre as linhas (content_align)

ManualGap = Tuple[int, float, float]   # (página, y em pontos, altura em pontos)


@dataclass
class Gap:
    doc: int
    page: int
    y: float               # posição no PDF (pontos, na página)
    auto: float            # altura automática (pixels)
    manual: float = 0.0    # altura acrescentada pelo usuário (pixels; pode ser negativa)

    @property
    def height(self) -> float:
        return max(self.auto + self.manual, 0.0)

    def key(self) -> Tuple[int, float]:
        return (self.page, round(self.y, 1))


@dataclass
class Piece:
    top: float                       # pixels na faixa
    height: float                    # pixels
    page: Optional[int] = None       # pedaço de página: qual página
    y0: float = 0.0                  # e qual trecho dela (pontos)
    y1: float = 0.0
    gap: Optional[Gap] = None        # espaço

    @property
    def bottom(self) -> float:
        return self.top + self.height


@dataclass
class StripLayout:
    scale: float
    page_heights: List[float]                      # pontos
    pieces: List[Piece] = field(default_factory=list)
    height: float = 0.0
    page_top: List[float] = field(default_factory=list)   # topo de cada página na faixa (pixels)

    # --- conversões ---------------------------------------------------------------
    def to_strip(self, page: int, y: float) -> float:
        """Posição (pixels) de um ponto da página, já com os espaços."""
        if not self.page_top:
            return 0.0
        page = max(0, min(page, len(self.page_top) - 1))
        y = max(0.0, min(y, self.page_heights[page]))
        found = None
        for piece in self._page_pieces(page):   # num corte, vale o pedaço de baixo (depois do espaço)
            if piece.y0 <= y <= piece.y1:
                found = piece
        if found is not None:
            return found.top + (y - found.y0) * self.scale
        return self.page_top[page] + y * self.scale

    def from_strip(self, value: float) -> Tuple[int, float]:
        """Página e y (pontos) na posição `value` da faixa (num espaço: o ponto logo abaixo)."""
        if not self.pieces:
            return 0, 0.0
        tops = [p.top for p in self.pieces]
        k = max(bisect_right(tops, value) - 1, 0)
        piece = self.pieces[k]
        if piece.page is not None:
            y = piece.y0 + (min(value, piece.bottom) - piece.top) / self.scale
            return piece.page, max(piece.y0, min(y, piece.y1))
        nxt = next((p for p in self.pieces[k:] if p.page is not None), None)
        if nxt is not None:
            return nxt.page, nxt.y0
        last = next(p for p in reversed(self.pieces) if p.page is not None)
        return last.page, last.y1

    def page_at(self, value: float) -> int:
        return self.from_strip(value)[0]

    def gaps(self) -> List[Piece]:
        return [p for p in self.pieces if p.gap is not None]

    def _page_pieces(self, page: int) -> List[Piece]:
        return [p for p in self.pieces if p.page == page]


def _stack(heights: Sequence[float], scale: float) -> List[float]:
    tops, y = [], 0.0
    for h in heights:
        tops.append(y)
        y += h * scale + PAGE_SPACING
    return tops


def _build(layout: StripLayout, gaps: List[Gap]) -> StripLayout:
    """Monta os pedaços (páginas cortadas nos espaços) a partir dos espaços de um PDF."""
    by_page: Dict[int, List[Gap]] = {}
    for g in gaps:
        if g.height > 0.5:
            by_page.setdefault(g.page, []).append(g)
    pieces: List[Piece] = []
    y = 0.0
    tops = []
    for page, h in enumerate(layout.page_heights):
        tops.append(y)
        cut = 0.0
        for g in sorted(by_page.get(page, []), key=lambda g: g.y):
            gy = max(0.0, min(g.y, h))
            if gy > cut:
                pieces.append(Piece(y, (gy - cut) * layout.scale, page, cut, gy))
                y += (gy - cut) * layout.scale
                cut = gy
            pieces.append(Piece(y, g.height, gap=g))
            y += g.height
        pieces.append(Piece(y, (h - cut) * layout.scale, page, cut, h))
        y += (h - cut) * layout.scale + PAGE_SPACING
    layout.pieces = pieces
    layout.page_top = tops
    layout.height = max(y - PAGE_SPACING, 0.0)
    return layout


def compute_layouts(
    page_heights: Sequence[Sequence[float]],
    scales: Sequence[float],
    primary: int = 0,
    anchors: Optional[Dict[int, Sequence[Anchor]]] = None,
    manual: Optional[Dict[int, Sequence[ManualGap]]] = None,
    aligned: bool = True,
) -> List[StripLayout]:
    """Disposição de cada PDF. `anchors[d]`: (pág. principal, y, pág. d, y) de linhas iguais."""
    n = len(page_heights)
    layouts = [StripLayout(scales[d], list(page_heights[d])) for d in range(n)]
    if not aligned or n < 2:
        return [_build(l, []) for l in layouts]
    anchors = anchors or {}
    manual = manual or {}
    tops = [_stack(page_heights[d], scales[d]) for d in range(n)]

    def strip(d: int, page: int, y: float) -> float:
        page = max(0, min(page, len(tops[d]) - 1))
        return tops[d][page] + max(0.0, min(y, page_heights[d][page])) * scales[d]

    # espaços manuais de cada PDF, em ordem na faixa
    manual_gaps: List[List[Tuple[float, Gap]]] = []
    for d in range(n):
        items = []
        for page, y, h in manual.get(d, []):
            if 0 <= page < len(tops[d]):
                items.append((strip(d, page, y), Gap(d, page, y, 0.0, h * scales[d])))
        manual_gaps.append(sorted(items, key=lambda t: t[0]))
    applied = [0] * n          # quantos espaços manuais já entraram, por PDF
    shift = [0.0] * n          # soma dos espaços já inseridos antes do ponto atual, por PDF
    gaps: List[List[Gap]] = [[g for _, g in manual_gaps[d]] for d in range(n)]
    gap_at: Dict[Tuple[int, Tuple[int, float]], Gap] = {(d, g.key()): g for d in range(n) for g in gaps[d]}

    near = 0.5 * max(scales)   # espaço manual a menos de ~0,5 pt da âncora conta como "no mesmo ponto"

    def take_manual(d: int, until: float, inclusive: bool) -> None:
        items = manual_gaps[d]
        limit = until + near if inclusive else until - near
        while applied[d] < len(items) and (items[applied[d]][0] < limit or (inclusive and items[applied[d]][0] <= limit)):
            shift[d] += items[applied[d]][1].manual
            applied[d] += 1

    def add_auto(d: int, page: int, y: float, height: float) -> None:
        g = gap_at.get((d, (page, round(y, 1))))
        if g is None:
            g = Gap(d, page, y, 0.0)
            gaps[d].append(g)
            gap_at[(d, g.key())] = g
        g.auto += height
        shift[d] += height

    events = []
    for d, items in anchors.items():
        if d == primary or not (0 <= d < n):
            continue
        for pa, ya, pb, yb in items:
            ya, yb = max(ya - ANCHOR_MARGIN, 0.0), max(yb - ANCHOR_MARGIN, 0.0)
            events.append((strip(primary, pa, ya), d, pa, ya, pb, yb))
    events.sort()
    last_seen = [-1.0] * n
    for sp, d, pa, ya, pb, yb in events:
        sd = strip(d, pb, yb)
        if sd < last_seen[d]:
            continue   # âncora fora de ordem (não deveria acontecer)
        last_seen[d] = sd
        take_manual(primary, sp, inclusive=False)
        take_manual(d, sd, inclusive=False)
        diff = (sp + shift[primary]) - (sd + shift[d])
        if diff > TOLERANCE:              # o PDF d está "adiantado": espaço nele
            add_auto(d, pb, yb, diff)
        elif diff < -TOLERANCE:           # o PDF d tem conteúdo a mais: espaço no principal e nos demais
            target = sp + shift[primary]
            add_auto(primary, pa, ya, -diff)
            for j in range(n):
                if j in (primary, d):
                    continue
                pos = target - shift[j]
                page, y = _locate(tops[j], page_heights[j], scales[j], pos)
                take_manual(j, pos, inclusive=False)
                add_auto(j, page, y, -diff)
        # um espaço manual no mesmo ponto do automático soma-se a ele (não é compensado aqui)
        take_manual(primary, sp, inclusive=True)
        take_manual(d, sd, inclusive=True)
    return [_build(layouts[d], gaps[d]) for d in range(n)]


def _locate(tops: List[float], heights: Sequence[float], scale: float, pos: float) -> Tuple[int, float]:
    if not tops:
        return 0, 0.0
    page = max(bisect_right(tops, pos) - 1, 0)
    y = (pos - tops[page]) / scale
    return page, max(0.0, min(y, heights[page]))
