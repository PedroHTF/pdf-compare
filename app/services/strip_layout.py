"""Disposição da rolagem contínua: páginas empilhadas e espaços que alinham o conteúdo.

Na rolagem contínua, cada PDF é uma faixa vertical com as páginas uma embaixo da
outra. Com o alinhamento por conteúdo ligado, são inseridos espaços vazios para
que as linhas iguais fiquem na mesma altura em todos os PDFs: se um PDF tem um
parágrafo a mais, os outros recebem um espaço do tamanho desse parágrafo, no
lugar onde ele estaria.

Âncoras: pares (página, y) de linhas iguais entre o PDF principal e cada outro
PDF (ver content_align). O cálculo percorre as âncoras em ordem; quando um lado
está "atrasado", recebe um espaço na posição da âncora.

Espaços manuais (definidos pelo usuário):
- ajuste (arrastar a alça, "Inserir espaço aqui"): soma-se ao espaço automático
  do mesmo ponto. O que ele acrescenta vale até a próxima âncora, onde o
  alinhamento volta a compensar (os outros PDFs recebem o espaço).
- fixo (removido, ou travado): a altura é a escolhida pelo usuário, seja qual for
  o automático. O que ele tira do automático (um espaço removido ou diminuído) é
  aceito: o alinhamento não recria esse espaço mais abaixo enquanto a mesma
  diferença continuar; só volta a alinhar quando os PDFs se reencontram sozinhos
  (ou a diferença muda). Diminuir um espaço pela alça também funciona assim.
- travado: fixo que o usuário protegeu: não se arrasta e "Realinhar" não desfaz.

Âncoras forçadas (trechos alinhados pelo usuário) sempre alinham, mesmo onde
havia uma diferença aceita.

Unidades: pontos do PDF para posições dentro da página; pixels de tela para a
faixa (cada PDF pode ter a própria escala). Sem dependência de interface gráfica.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from app.services.content_align import Anchor

PAGE_SPACING = 10.0     # pixels entre páginas
TOLERANCE = 6.0         # diferenças menores (pixels) são ignoradas
ANCHOR_MARGIN = 0.0     # as âncoras já vêm no ponto de corte entre as linhas (content_align)

class ManualGap(NamedTuple):
    page: int
    y: float               # pontos, na página
    height: float          # pontos: ajuste (somado ao automático) ou altura final (fixed)
    fixed: bool = False    # altura final escolhida pelo usuário (removido = 0)
    locked: bool = False   # travado: não muda com o alinhamento nem com "Realinhar"


@dataclass
class Gap:
    doc: int
    page: int
    y: float               # posição no PDF (pontos, na página)
    auto: float            # altura automática (pixels)
    manual: float = 0.0    # pixels: ajuste do usuário (pode ser negativo) ou, se fixed, a altura final
    fixed: bool = False
    locked: bool = False
    contributed: float = field(default=0.0, repr=False, compare=False)   # já somado ao deslocamento

    @property
    def height(self) -> float:
        if self.fixed:
            return max(self.manual, 0.0)
        return max(self.auto + self.manual, 0.0)

    @property
    def adjusted(self) -> bool:
        """O usuário mexeu neste espaço (é desenhado com outra cor)."""
        return self.fixed or abs(self.manual) > 0.5

    @property
    def removed(self) -> bool:
        return self.fixed and self.manual <= 0.5

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
        if g.height > 0.5 or g.locked:      # travado e removido: fica uma marca de altura zero
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


def _manual_gap(item) -> ManualGap:
    return item if isinstance(item, ManualGap) else ManualGap(*item)


SAME_POINT = 1.0   # pontos: espaços a menos disso na mesma página são o mesmo espaço


def compute_layouts(
    page_heights: Sequence[Sequence[float]],
    scales: Sequence[float],
    primary: int = 0,
    anchors: Optional[Dict[int, Sequence[Anchor]]] = None,
    manual: Optional[Dict[int, Sequence[ManualGap]]] = None,
    aligned: bool = True,
    forced: Optional[Dict[int, Sequence[Anchor]]] = None,
) -> List[StripLayout]:
    """Disposição de cada PDF. `anchors[d]`: (pág. principal, y, pág. d, y) de linhas iguais.

    `forced[d]`: as âncoras de `anchors[d]` definidas pelo usuário (sempre alinham).
    """
    n = len(page_heights)
    layouts = [StripLayout(scales[d], list(page_heights[d])) for d in range(n)]
    if not aligned or n < 2:
        return [_build(l, []) for l in layouts]
    anchors = anchors or {}
    manual = manual or {}
    forced_set = {d: set(items) for d, items in (forced or {}).items()}
    tops = [_stack(page_heights[d], scales[d]) for d in range(n)]

    def strip(d: int, page: int, y: float) -> float:
        page = max(0, min(page, len(tops[d]) - 1))
        return tops[d][page] + max(0.0, min(y, page_heights[d][page])) * scales[d]

    # espaços manuais de cada PDF, em ordem na faixa
    pending: List[List[Tuple[float, Gap]]] = []
    gaps: List[List[Gap]] = []
    for d in range(n):
        items = []
        for entry in manual.get(d, []):
            m = _manual_gap(entry)
            if 0 <= m.page < len(tops[d]):
                g = Gap(d, m.page, m.y, 0.0, m.height * scales[d], bool(m.fixed), bool(m.locked))
                items.append((strip(d, m.page, m.y), g))
        items.sort(key=lambda t: t[0])
        pending.append(items)
        gaps.append([g for _, g in items])
    passed = [0] * n           # quantos espaços manuais o percurso já passou, por PDF
    shift = [0.0] * n          # soma dos espaços já inseridos antes do ponto atual, por PDF
    # diferença aceita entre o PDF d e o principal (pixels; > 0: d está "adiantado"), vinda de
    # espaços removidos ou diminuídos pelo usuário; o alinhamento não a compensa
    accepted = [0.0] * n

    near = 0.5 * max(scales)   # espaço manual a menos de ~0,5 pt da âncora conta como "no mesmo ponto"

    def sync(g: Gap) -> float:
        """Soma ao deslocamento do PDF o que mudou na altura do espaço; devolve a mudança."""
        delta = g.height - g.contributed
        shift[g.doc] += delta
        g.contributed = g.height
        return delta

    def pass_manual(d: int, until: float, inclusive: bool) -> None:
        items = pending[d]
        limit = until + near if inclusive else until - near
        while passed[d] < len(items) and (items[passed[d]][0] < limit or (inclusive and items[passed[d]][0] <= limit)):
            sync(items[passed[d]][1])
            passed[d] += 1

    def find(d: int, page: int, y: float) -> Optional[Gap]:
        best = None
        for g in gaps[d]:
            if g.page == page and abs(g.y - y) < SAME_POINT and (best is None or abs(g.y - y) < abs(best.y - y)):
                best = g
        return best

    def request(d: int, page: int, y: float, height: float) -> float:
        """Pede um espaço automático; devolve quanto o PDF desceu de fato (espaços fixos limitam)."""
        g = find(d, page, y)
        if g is None:
            g = Gap(d, page, y, 0.0)
            gaps[d].append(g)
        g.auto += height
        return sync(g)

    def hold(d: int, diff: float) -> float:
        """Parte da diferença que já foi aceita pelo usuário (some quando os PDFs se reencontram)."""
        a = accepted[d]
        if a > 0:
            a = a if diff >= a - TOLERANCE else min(a, max(diff, 0.0))
        elif a < 0:
            a = a if diff <= a + TOLERANCE else max(a, min(diff, 0.0))
        accepted[d] = a
        return a

    events = []
    for d, items in anchors.items():
        if d == primary or not (0 <= d < n):
            continue
        for anchor in items:
            pa, ya, pb, yb = anchor
            is_forced = anchor in forced_set.get(d, ())
            ya, yb = max(ya - ANCHOR_MARGIN, 0.0), max(yb - ANCHOR_MARGIN, 0.0)
            events.append((strip(primary, pa, ya), d, pa, ya, pb, yb, is_forced))
    events.sort()
    last_seen = [-1.0] * n
    for sp, d, pa, ya, pb, yb, is_forced in events:
        sd = strip(d, pb, yb)
        if sd < last_seen[d]:
            continue   # âncora fora de ordem (não deveria acontecer)
        last_seen[d] = sd
        pass_manual(primary, sp, inclusive=False)
        pass_manual(d, sd, inclusive=False)
        diff = (sp + shift[primary]) - (sd + shift[d])
        if is_forced:
            accepted[d] = 0.0
            need = diff
        else:
            need = diff - hold(d, diff)
        if need > TOLERANCE:              # o PDF d está "adiantado": espaço nele
            placed = request(d, pb, yb, need)
            accepted[d] += max(need - placed, 0.0)
        elif need < -TOLERANCE:           # o PDF d tem conteúdo a mais: espaço no principal e nos demais
            target = sp + shift[primary]
            placed = request(primary, pa, ya, -need)
            accepted[d] -= max(-need - placed, 0.0)
            moved = min(placed, -need)    # os outros acompanham o quanto o principal desceu
            if moved > 0.5:
                for j in range(n):
                    if j in (primary, d):
                        continue
                    pos = target - shift[j]
                    page, y = _locate(tops[j], page_heights[j], scales[j], pos)
                    pass_manual(j, pos, inclusive=False)
                    placed_j = request(j, page, y, moved)
                    accepted[j] += max(moved - placed_j, 0.0)
        # um espaço manual no mesmo ponto do automático soma-se a ele (não é compensado aqui)
        pass_manual(primary, sp, inclusive=True)
        pass_manual(d, sd, inclusive=True)
    return [_build(layouts[d], gaps[d]) for d in range(n)]


def _locate(tops: List[float], heights: Sequence[float], scale: float, pos: float) -> Tuple[int, float]:
    if not tops:
        return 0, 0.0
    page = max(bisect_right(tops, pos) - 1, 0)
    y = (pos - tops[page]) / scale
    return page, max(0.0, min(y, heights[page]))
