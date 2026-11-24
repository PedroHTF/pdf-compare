"""Comparação de texto entre PDFs, palavra por palavra.

O primeiro PDF aberto é a referência. Cada um dos outros é comparado com ele:
- no PDF de referência são marcadas as palavras removidas ou alteradas;
- no outro PDF, as palavras incluídas ou alteradas.

Para ser rápido em documentos longos, a comparação é feita em dois níveis:
primeiro por linhas e, nos trechos de linhas diferentes, palavra por palavra.
Mudanças de quebra de linha ou de página não aparecem como diferença.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Sequence, Tuple

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


def _words(index: DocumentIndex, case_sensitive: bool, ignore_accents: bool) -> Tuple[List[_Word], List[Tuple[int, int]]]:
    """Palavras do documento e os intervalos [início, fim) de cada linha."""
    words: List[_Word] = []
    lines: List[Tuple[int, int]] = []
    for page_no, tokens in enumerate(index.pages):
        start = len(words)
        last_line = None
        for token in tokens:
            if last_line is not None and token.line != last_line:
                lines.append((start, len(words)))
                start = len(words)
            last_line = token.line
            words.append(_Word(page_no, fold(token.text, case_sensitive, ignore_accents), tuple(token.rects)))
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


def diff_pair(
    ref: DocumentIndex,
    other: DocumentIndex,
    case_sensitive: bool = True,
    ignore_accents: bool = False,
) -> Tuple[List[DiffMark], List[DiffMark]]:
    """Diferenças entre dois documentos: (marcas na referência, marcas no outro)."""
    wa, la = _words(ref, case_sensitive, ignore_accents)
    wb, lb = _words(other, case_sensitive, ignore_accents)
    keys_a = [" ".join(w.text for w in wa[s:e]) for s, e in la]
    keys_b = [" ".join(w.text for w in wb[s:e]) for s, e in lb]

    marks_a: List[DiffMark] = []
    marks_b: List[DiffMark] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, keys_a, keys_b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        a0 = la[i1][0] if i1 < i2 else (la[i1][0] if i1 < len(la) else len(wa))
        a1 = la[i2 - 1][1] if i1 < i2 else a0
        b0 = lb[j1][0] if j1 < j2 else (lb[j1][0] if j1 < len(lb) else len(wb))
        b1 = lb[j2 - 1][1] if j1 < j2 else b0
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
    result: List[List[DiffMark]] = [[] for _ in indexes]
    ref_marks: Dict[Tuple[int, Tuple[Rect, ...]], DiffMark] = {}
    for i in range(1, len(indexes)):
        marks_ref, marks_other = diff_pair(indexes[0], indexes[i], **options)
        for mark in marks_ref:
            ref_marks.setdefault((mark.page, mark.rects), mark)
        result[i] = marks_other
    result[0] = sorted(ref_marks.values(), key=lambda m: (m.page, m.rects[0][1], m.rects[0][0]))
    return result


def count_by_kind(marks: Sequence[DiffMark]) -> Dict[str, int]:
    counts = {ADDED: 0, REMOVED: 0, CHANGED: 0}
    for mark in marks:
        counts[mark.kind] += 1
    return counts
