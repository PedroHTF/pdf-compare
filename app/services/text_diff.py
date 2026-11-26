"""Comparação de texto entre PDFs, palavra por palavra.

O primeiro PDF aberto é a referência. Cada um dos outros é comparado com ele:
- no PDF de referência são marcadas as palavras removidas ou alteradas;
- no outro PDF, as palavras incluídas ou alteradas.

Para ser rápido em documentos longos, a comparação é feita em dois níveis:
primeiro por linhas e, nos trechos de linhas diferentes, palavra por palavra.
Mudanças de quebra de linha ou de página não aparecem como diferença.

Pontos de sincronização (`sync`): pares (página a, y a, página b, y b) que o
usuário alinhou à mão (trechos, linhas, páginas fixadas). Com eles, o texto é
dividido nesses pontos e cada pedaço do a é comparado só com o pedaço
correspondente do b — a comparação segue o alinhamento do usuário.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.text_index import DocumentIndex, Rect, fold

ADDED = "added"       # existe só no outro PDF
REMOVED = "removed"   # existe só no PDF de referência
CHANGED = "changed"   # palavra trocada

# Acima disso (palavras x palavras) um trecho é marcado inteiro como alterado,
# para não travar a interface com documentos completamente diferentes.
MAX_WORD_PAIRS = 4_000_000


@dataclass(frozen=True)
class DiffMark:
    page: int
    rects: Tuple[Rect, ...]
    kind: str


@dataclass(frozen=True)
class _Word:
    page: int
    text: str
    rects: Tuple[Rect, ...]
    raw: str = ""          # texto original (para o relatório)


PageRange = Tuple[int, int]   # páginas [início, fim)


def _words(index: DocumentIndex, case_sensitive: bool, ignore_accents: bool,
           pages: Optional[PageRange] = None) -> Tuple[List[_Word], List[Tuple[int, int]]]:
    """Palavras do documento (ou do intervalo de páginas) e os intervalos [início, fim) de cada linha."""
    words: List[_Word] = []
    lines: List[Tuple[int, int]] = []
    first, last = pages if pages is not None else (0, len(index.pages))
    for page_no in range(max(first, 0), min(last, len(index.pages))):
        tokens = index.pages[page_no]
        start = len(words)
        last_line = None
        for token in tokens:
            if last_line is not None and token.line != last_line:
                lines.append((start, len(words)))
                start = len(words)
            last_line = token.line
            words.append(_Word(page_no, fold(token.text, case_sensitive, ignore_accents), tuple(token.rects),
                               token.raw or token.text))
        if len(words) > start:
            lines.append((start, len(words)))
    return words, lines


def _marks(words: Sequence[_Word], start: int, end: int, kind: str) -> List[DiffMark]:
    """Agrupa palavras seguidas da mesma página em uma única marca."""
    marks: List[DiffMark] = []
    group: List[_Word] = []
    for w in words[start:end]:
        if group and w.page != group[0].page:
            marks.append(DiffMark(group[0].page, tuple(r for g in group for r in g.rects), kind))
            group = []
        group.append(w)
    if group:
        marks.append(DiffMark(group[0].page, tuple(r for g in group for r in g.rects), kind))
    return marks


SyncPoint = Tuple[int, float, int, float]   # (página a, y a, página b, y b)


def _line_at(words: Sequence[_Word], lines: Sequence[Tuple[int, int]], page: int, y: float) -> int:
    """Primeira linha que começa no ponto (página, y) ou depois dele."""
    for k, (start, _) in enumerate(lines):
        w = words[start]
        top = w.rects[0][1] if w.rects else 0.0
        if (w.page, top) >= (page, y - 0.5):
            return k
    return len(lines)


def _segments(wa, la, wb, lb, sync: Optional[Sequence[SyncPoint]]) -> List[Tuple[int, int, int, int]]:
    """Pedaços (linhas [i0, i1) do a, [j0, j1) do b) comparados separadamente."""
    cuts: List[Tuple[int, int]] = []
    last = (0, 0)
    for pa, ya, pb, yb in sorted(sync or ()):
        i, j = _line_at(wa, la, pa, ya), _line_at(wb, lb, pb, yb)
        if i < last[0] or j < last[1] or (i, j) == last:
            continue   # fora de ordem (ou repetido): ignora
        cuts.append((i, j))
        last = (i, j)
    bounds = [(0, 0)] + cuts + [(len(la), len(lb))]
    return [(i0, i1, j0, j1) for (i0, j0), (i1, j1) in zip(bounds, bounds[1:])]


def _changed_ranges(wa, la, wb, lb, sync: Optional[Sequence[SyncPoint]] = None):
    """Trechos de palavras diferentes (a0, a1, b0, b1), comparando linha por linha."""
    keys_a = [" ".join(w.text for w in wa[s:e]) for s, e in la]
    keys_b = [" ".join(w.text for w in wb[s:e]) for s, e in lb]
    for i0, i1, j0, j1 in _segments(wa, la, wb, lb, sync):
        matcher = SequenceMatcher(None, keys_a[i0:i1], keys_b[j0:j1], autojunk=False)
        for tag, x1, x2, y1, y2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            x1, x2, y1, y2 = x1 + i0, x2 + i0, y1 + j0, y2 + j0
            a0 = la[x1][0] if x1 < len(la) else len(wa)
            a1 = la[x2 - 1][1] if x1 < x2 else a0
            b0 = lb[y1][0] if y1 < len(lb) else len(wb)
            b1 = lb[y2 - 1][1] if y1 < y2 else b0
            yield a0, a1, b0, b1


def diff_pair(
    ref: DocumentIndex,
    other: DocumentIndex,
    case_sensitive: bool = True,
    ignore_accents: bool = False,
    ref_pages: Optional[PageRange] = None,
    other_pages: Optional[PageRange] = None,
    sync: Optional[Sequence[SyncPoint]] = None,
) -> Tuple[List[DiffMark], List[DiffMark]]:
    """Diferenças entre dois documentos: (marcas na referência, marcas no outro).

    Com `ref_pages` / `other_pages`, compara só esses intervalos (comparação em lotes).
    Com `sync`, compara separadamente os pedaços entre os pontos alinhados pelo usuário.
    """
    wa, la = _words(ref, case_sensitive, ignore_accents, ref_pages)
    wb, lb = _words(other, case_sensitive, ignore_accents, other_pages)
    marks_a: List[DiffMark] = []
    marks_b: List[DiffMark] = []
    for a0, a1, b0, b1 in _changed_ranges(wa, la, wb, lb, sync):
        _diff_words(wa, a0, a1, wb, b0, b1, marks_a, marks_b)
    return marks_a, marks_b


def _diff_words(wa, a0, a1, wb, b0, b1, marks_a, marks_b) -> None:
    if a0 == a1:
        marks_b.extend(_marks(wb, b0, b1, ADDED))
        return
    if b0 == b1:
        marks_a.extend(_marks(wa, a0, a1, REMOVED))
        return
    if (a1 - a0) * (b1 - b0) > MAX_WORD_PAIRS:
        marks_a.extend(_marks(wa, a0, a1, CHANGED))
        marks_b.extend(_marks(wb, b0, b1, CHANGED))
        return
    ta = [w.text for w in wa[a0:a1]]
    tb = [w.text for w in wb[b0:b1]]
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            marks_a.extend(_marks(wa, a0 + i1, a0 + i2, CHANGED))
            marks_b.extend(_marks(wb, b0 + j1, b0 + j2, CHANGED))
        elif tag == "delete":
            marks_a.extend(_marks(wa, a0 + i1, a0 + i2, REMOVED))
        else:
            marks_b.extend(_marks(wb, b0 + j1, b0 + j2, ADDED))


def diff_documents(indexes: Sequence[DocumentIndex], **options) -> List[List[DiffMark]]:
    """Compara cada documento com o primeiro. Devolve as marcas de cada um, em ordem de leitura."""
    if len(indexes) < 2:
        return [[] for _ in indexes]
    pairs = [diff_pair(indexes[0], indexes[i], **options) for i in range(1, len(indexes))]
    return merge_pairs(pairs)


def reading_order(mark: DiffMark) -> tuple:
    return (mark.page, mark.rects[0][1], mark.rects[0][0]) if mark.rects else (mark.page, 0, 0)


def merge_pairs(pairs: Sequence[Tuple[Sequence[DiffMark], Sequence[DiffMark]]]) -> List[List[DiffMark]]:
    """Junta os resultados de cada par (referência, outro) em uma lista de marcas por documento.

    Uma palavra da referência marcada em vários pares aparece uma vez só.
    """
    result: List[List[DiffMark]] = [[] for _ in range(len(pairs) + 1)]
    ref_marks: Dict[Tuple[int, Tuple[Rect, ...]], DiffMark] = {}
    for i, (marks_ref, marks_other) in enumerate(pairs, start=1):
        for mark in marks_ref:
            ref_marks.setdefault((mark.page, mark.rects), mark)
        result[i] = sorted(marks_other, key=reading_order)
    result[0] = sorted(ref_marks.values(), key=reading_order)
    return result


def merge_results(documents: int, pairs: Sequence[Tuple[int, int]],
                  results: Sequence[Tuple[Sequence[DiffMark], Sequence[DiffMark]]]) -> List[List[DiffMark]]:
    """Junta resultados de pares quaisquer (a, b) em marcas por documento.

    Cada documento que aparece como "b" (o comparado) mostra as marcas que recebeu
    nesse papel. Um documento que só aparece como "a" (a base: a referência, ou o
    primeiro da cadeia) mostra o que foi removido ou alterado nele, sem repetições.
    """
    as_other: Dict[int, List[DiffMark]] = {}
    as_base: Dict[int, Dict[Tuple[int, Tuple[Rect, ...]], DiffMark]] = {}
    for (a, b), (marks_a, marks_b) in zip(pairs, results):
        as_other.setdefault(b, []).extend(marks_b)
        base = as_base.setdefault(a, {})
        for mark in marks_a:
            base.setdefault((mark.page, mark.rects), mark)
    out: List[List[DiffMark]] = []
    for doc in range(documents):
        marks = as_other[doc] if doc in as_other else list(as_base.get(doc, {}).values())
        out.append(sorted(marks, key=reading_order))
    return out


@dataclass(frozen=True)
class ReportEntry:
    """Uma mudança, para o relatório: o texto na base (a) e no PDF comparado (b)."""

    kind: str
    page_a: Optional[int]   # página onde está (ou estaria) o trecho no PDF a
    text_a: str
    page_b: Optional[int]
    text_b: str


def _text(words: Sequence[_Word], start: int, end: int, limit: int = 400) -> str:
    text = " ".join(w.raw or w.text for w in words[start:end])
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _page_at(words: Sequence[_Word], start: int, end: int) -> Optional[int]:
    if start < end:
        return words[start].page
    if start < len(words):
        return words[start].page
    return words[-1].page if words else None


def report_entries(ref: DocumentIndex, other: DocumentIndex, case_sensitive: bool = True,
                   ignore_accents: bool = False, sync: Optional[Sequence[SyncPoint]] = None) -> List[ReportEntry]:
    """Lista legível das mudanças entre dois documentos inteiros (mesmo método de diff_pair)."""
    wa, la = _words(ref, case_sensitive, ignore_accents)
    wb, lb = _words(other, case_sensitive, ignore_accents)
    entries: List[ReportEntry] = []
    for a0, a1, b0, b1 in _changed_ranges(wa, la, wb, lb, sync):
        if a0 == a1 or b0 == b1 or (a1 - a0) * (b1 - b0) > MAX_WORD_PAIRS:
            kind = ADDED if a0 == a1 else REMOVED if b0 == b1 else CHANGED
            entries.append(ReportEntry(kind, _page_at(wa, a0, a1), _text(wa, a0, a1),
                                       _page_at(wb, b0, b1), _text(wb, b0, b1)))
            continue
        ta = [w.text for w in wa[a0:a1]]
        tb = [w.text for w in wb[b0:b1]]
        for op, x1, x2, y1, y2 in SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
            if op == "equal":
                continue
            kind = {"replace": CHANGED, "delete": REMOVED, "insert": ADDED}[op]
            entries.append(ReportEntry(kind, _page_at(wa, a0 + x1, a0 + x2), _text(wa, a0 + x1, a0 + x2),
                                       _page_at(wb, b0 + y1, b0 + y2), _text(wb, b0 + y1, b0 + y2)))
    return entries


def count_by_kind(marks: Sequence[DiffMark]) -> Dict[str, int]:
    counts = {ADDED: 0, REMOVED: 0, CHANGED: 0}
    for mark in marks:
        counts[mark.kind] += 1
    return counts
