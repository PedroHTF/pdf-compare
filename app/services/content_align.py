"""Alinhamento por conteúdo: quais páginas (e linhas) de um PDF correspondem às de outro.

1. As linhas de texto dos dois PDFs são comparadas em ordem (difflib). Cada
   linha igual vira uma "âncora": (página e altura no PDF a, página e altura no b).
2. Cada página do PDF a fica com a página do b com que mais compartilha linhas,
   mantendo a ordem (uma página não pode "voltar" para trás).
3. Entre duas páginas pareadas, as que sobraram (texto muito alterado ou sem
   texto) são pareadas pela semelhança das palavras, mantendo a ordem; o que
   ainda sobrar é página incluída (só no b) ou removida (só no a).

O usuário pode fixar pares de páginas à mão (`manual`); eles têm prioridade.
Sem dependência de interface gráfica.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.text_index import DocumentIndex, fold

PagePair = Tuple[Optional[int], Optional[int]]     # (página no a, página no b); None = sem correspondente
Anchor = Tuple[int, float, int, float]             # (página a, y a, página b, y b) de uma linha igual
Row = Tuple[Optional[int], ...]                    # página de cada PDF em uma linha da visualização


@dataclass(frozen=True)
class Line:
    page: int
    y: float       # topo da linha (pontos, página sem rotação)
    key: str
    bottom: float = 0.0
    cut: float = 0.0   # onde um espaço pode entrar acima desta linha sem cortar a anterior


def document_lines(index: DocumentIndex) -> List[Line]:
    lines: List[Line] = []
    for page_no, tokens in enumerate(index.pages):
        groups: List[Tuple[List[str], float, float]] = []
        current: Optional[int] = None
        for token in tokens:
            top = min((r[1] for r in token.rects), default=0.0)
            bottom = max((r[3] for r in token.rects), default=top)
            if token.line != current or not groups:
                groups.append(([], top, bottom))
                current = token.line
            words, t, b = groups[-1]
            words.append(fold(token.text, False, True))
            groups[-1] = (words, min(t, top), max(b, bottom))
        previous_bottom: Optional[float] = None
        for words, top, bottom in groups:
            if previous_bottom is not None and previous_bottom <= top:
                cut = (previous_bottom + top) / 2        # no meio do espaço entre as linhas
            else:
                cut = max(top - 2.0, 0.0)
            lines.append(Line(page_no, top, " ".join(words), bottom, cut))
            previous_bottom = bottom if previous_bottom is None else max(previous_bottom, bottom)
    return lines


@dataclass
class PairMatch:
    """Resultado da comparação de linhas entre dois PDFs (a parte demorada; fica em memória)."""

    pages_a: int
    pages_b: int
    anchors: List[Anchor]
    votes: Dict[Tuple[int, int], int] = field(default_factory=dict)
    words_a: List[frozenset] = field(default_factory=list)   # palavras de cada página (pareamento das sobras)
    words_b: List[frozenset] = field(default_factory=list)


def _page_words(lines: Sequence[Line], pages: int) -> List[frozenset]:
    words: List[set] = [set() for _ in range(pages)]
    for line in lines:
        if 0 <= line.page < pages:
            words[line.page].update(line.key.split())
    return [frozenset(w) for w in words]


def match_lines(a: DocumentIndex, b: DocumentIndex) -> PairMatch:
    la, lb = document_lines(a), document_lines(b)
    matcher = SequenceMatcher(None, [l.key for l in la], [l.key for l in lb], autojunk=False)
    anchors: List[Anchor] = []
    votes: Dict[Tuple[int, int], int] = {}
    for i, j, size in matcher.get_matching_blocks():
        for k in range(size):
            x, y = la[i + k], lb[j + k]
            # âncoras: início de cada trecho igual e primeira linha de cada página dentro dele
            if k == 0 or x.page != la[i + k - 1].page or y.page != lb[j + k - 1].page:
                anchors.append((x.page, x.cut, y.page, y.cut))
            votes[(x.page, y.page)] = votes.get((x.page, y.page), 0) + 1
    return PairMatch(a.page_count, b.page_count, anchors, votes,
                     _page_words(la, a.page_count), _page_words(lb, b.page_count))


def _similarity(x: frozenset, y: frozenset) -> float:
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


MAX_LEFTOVER_CELLS = 40_000


def _pair_leftovers(match: PairMatch, left_a: List[int], left_b: List[int]) -> List[PagePair]:
    """Pareia as páginas que sobraram entre duas âncoras, em ordem, pela semelhança.

    Cada par vale um pouco mesmo sem palavras em comum, então páginas sem texto
    ainda são pareadas na ordem (como antes de existir o alinhamento).
    """
    n, m = len(left_a), len(left_b)
    if n == 0 or m == 0 or n * m > MAX_LEFTOVER_CELLS or not (match.words_a and match.words_b):
        k = min(n, m)
        return [(left_a[i], left_b[i]) for i in range(k)] + [(p, None) for p in left_a[k:]] \
            + [(None, p) for p in left_b[k:]]
    bonus = 0.05
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            take = bonus + _similarity(match.words_a[left_a[i]], match.words_b[left_b[j]]) + score[i + 1][j + 1]
            score[i][j] = max(take, score[i + 1][j], score[i][j + 1])
    out: List[PagePair] = []
    i = j = 0
    while i < n and j < m:
        take = bonus + _similarity(match.words_a[left_a[i]], match.words_b[left_b[j]]) + score[i + 1][j + 1]
        if score[i][j] == take:
            out.append((left_a[i], left_b[j]))
            i += 1
            j += 1
        elif score[i][j] == score[i + 1][j]:
            out.append((left_a[i], None))
            i += 1
        else:
            out.append((None, left_b[j]))
            j += 1
    out += [(p, None) for p in left_a[i:]] + [(None, p) for p in left_b[j:]]
    return out


def _increasing_subset(candidates: Sequence[Tuple[int, int, float]]) -> List[Tuple[int, int]]:
    """Maior conjunto (por peso) de pares (pa, pb) com pa e pb crescentes. O(n log n)."""
    items = sorted(candidates)
    if not items:
        return []
    size = max(pb for _, pb, _ in items) + 2
    tree = [(0.0, -1)] * (size + 1)      # árvore de Fenwick: melhor (peso, item) com pb <= x

    def query(x: int) -> Tuple[float, int]:
        best = (0.0, -1)
        x += 1
        while x > 0:
            if tree[x][0] > best[0]:
                best = tree[x]
            x -= x & -x
        return best

    def update(x: int, value: Tuple[float, int]) -> None:
        x += 1
        while x <= size:
            if value[0] > tree[x][0]:
                tree[x] = value
            x += x & -x

    best_total, best_end = 0.0, -1
    prev = [-1] * len(items)
    k = 0
    while k < len(items):   # mesmo pa: consulta antes de atualizar (pa estritamente crescente)
        group = [g for g in range(k, len(items)) if items[g][0] == items[k][0]]
        results = []
        for g in group:
            _, pb, w = items[g]
            score, before = query(pb - 1)
            results.append((g, pb, score + w, before))
        for g, pb, total, before in results:
            prev[g] = before
            update(pb, (total, g))
            if total > best_total:
                best_total, best_end = total, g
        k = group[-1] + 1
    chosen = []
    while best_end >= 0:
        chosen.append((items[best_end][0], items[best_end][1]))
        best_end = prev[best_end]
    return chosen[::-1]


MANUAL_WEIGHT = 1e9


def align_pages(match: PairMatch, manual: Sequence[Tuple[int, int]] = ()) -> List[PagePair]:
    """Sequência de pares de páginas (a, b), em ordem, cobrindo todas as páginas dos dois PDFs."""
    best: Dict[int, Tuple[int, int]] = {}
    for (pa, pb), n in match.votes.items():
        if pa not in best or n > best[pa][1] or (n == best[pa][1] and abs(pb - pa) < abs(best[pa][0] - pa)):
            best[pa] = (pb, n)
    fixed_a = {pa for pa, _ in manual}
    fixed_b = {pb for _, pb in manual}
    candidates = [(pa, pb, float(n)) for pa, (pb, n) in best.items() if pa not in fixed_a and pb not in fixed_b]
    candidates += [(pa, pb, MANUAL_WEIGHT) for pa, pb in manual
                   if 0 <= pa < match.pages_a and 0 <= pb < match.pages_b]
    matched = _increasing_subset(candidates)

    pairs: List[PagePair] = []
    last_a = last_b = -1
    for pa, pb in matched + [(match.pages_a, match.pages_b)]:
        pairs += _pair_leftovers(match, list(range(last_a + 1, pa)), list(range(last_b + 1, pb)))
        if pa < match.pages_a:
            pairs.append((pa, pb))
        last_a, last_b = pa, pb
    return pairs


def build_rows(page_counts: Sequence[int], primary: int, pairs: Dict[int, Sequence[PagePair]]) -> List[Row]:
    """Linhas da visualização alinhada: a página de cada PDF em cada posição.

    `pairs[i]` alinha o PDF principal (a) com o PDF i (b). As páginas incluídas
    em PDFs diferentes no mesmo ponto ficam lado a lado.
    """
    n = len(page_counts)
    ref_pages = page_counts[primary]
    matched: Dict[int, Dict[int, Optional[int]]] = {}      # PDF -> página do principal -> página
    inserted: Dict[int, Dict[int, List[int]]] = {}         # PDF -> antes da página do principal -> incluídas
    for doc in range(n):
        if doc == primary:
            continue
        m: Dict[int, Optional[int]] = {}
        ins: Dict[int, List[int]] = {}
        pending: List[int] = []
        for pa, pb in pairs.get(doc, []):
            if pa is None:
                pending.append(pb)
            else:
                ins[pa] = pending
                pending = []
                m[pa] = pb
        ins[ref_pages] = pending
        matched[doc], inserted[doc] = m, ins
    rows: List[Row] = []
    for r in range(ref_pages + 1):
        extra = max((len(inserted[d].get(r, [])) for d in inserted), default=0)
        for k in range(extra):
            row = [None] * n
            for d in inserted:
                block = inserted[d].get(r, [])
                if k < len(block):
                    row[d] = block[k]
            rows.append(tuple(row))
        if r < ref_pages:
            row = [None] * n
            row[primary] = r
            for d in matched:
                row[d] = matched[d].get(r)
            rows.append(tuple(row))
    return rows


def combined_anchors(match: PairMatch, manual: Sequence[Anchor] = ()) -> List[Anchor]:
    """Âncoras automáticas mais as definidas pelo usuário ("Alinhar este trecho com…").

    As automáticas que ficariam fora de ordem em relação a uma manual são descartadas.
    """
    keep = []
    for anchor in match.anchors:
        a, b = (anchor[0], anchor[1]), (anchor[2], anchor[3])
        if all(((m[0], m[1]) < a) == ((m[2], m[3]) < b) and (m[0], m[1]) != a for m in manual):
            keep.append(anchor)
    return sorted(keep + list(manual))


def rows_key(rows: Sequence[Row]) -> str:
    return hashlib.sha1(repr(list(rows)).encode()).hexdigest()


class AlignmentStore:
    """Ajustes manuais de alinhamento, por par de PDFs (identificados pelo conteúdo).

    Guarda os pares de páginas fixados pelo usuário e os espaços da rolagem
    contínua. Reaparecem ao abrir os mesmos PDFs de novo.
    """

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)
        self._cache: Dict[str, dict] = {}

    @staticmethod
    def key(fingerprint_a: str, fingerprint_b: str) -> str:
        return hashlib.sha256(f"{fingerprint_a}|{fingerprint_b}".encode()).hexdigest()

    def _load(self, key: str) -> dict:
        if key not in self._cache:
            try:
                data = json.loads((self.folder / f"{key}.json").read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except (OSError, ValueError):
                data = {}
            self._cache[key] = data
        return self._cache[key]

    def _save(self, key: str) -> None:
        data = self._cache.get(key, {})
        path = self.folder / f"{key}.json"
        try:
            if not any(data.get(k) for k in ("pages", "gaps", "lines")):
                path.unlink(missing_ok=True)
                return
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    # pares de páginas fixados à mão
    def manual_pages(self, key: str) -> List[Tuple[int, int]]:
        try:
            return [(int(a), int(b)) for a, b in self._load(key).get("pages", [])]
        except (TypeError, ValueError):
            return []

    def fix_pages(self, key: str, page_a: int, page_b: int) -> None:
        """Fixa a página b com a página a. Remove os pares que ficariam fora de ordem."""
        kept = [(a, b) for a, b in self.manual_pages(key)
                if a != page_a and b != page_b and (a < page_a) == (b < page_b)]
        self._load(key)["pages"] = sorted(kept + [(page_a, page_b)])
        self._save(key)

    # espaços da rolagem contínua: (página, y, altura extra em pontos)
    def manual_gaps(self, key: str) -> List[Tuple[int, float, float]]:
        try:
            return [(int(p), float(y), float(h)) for p, y, h in self._load(key).get("gaps", [])]
        except (TypeError, ValueError):
            return []

    def set_gap(self, key: str, page: int, y: float, height: float) -> None:
        gaps = [(p, gy, h) for p, gy, h in self.manual_gaps(key) if not (p == page and abs(gy - y) < 1.0)]
        if abs(height) >= 0.5:
            gaps.append((page, round(y, 1), round(height, 1)))
        self._load(key)["gaps"] = sorted(gaps)
        self._save(key)

    # linhas alinhadas à mão na rolagem contínua: (página a, y a, página b, y b)
    def manual_lines(self, key: str) -> List[Anchor]:
        try:
            return [(int(a), float(ya), int(b), float(yb)) for a, ya, b, yb in self._load(key).get("lines", [])]
        except (TypeError, ValueError):
            return []

    def add_line(self, key: str, anchor: Anchor) -> None:
        pa, ya, pb, yb = anchor
        before = ((pa, ya), (pb, yb))
        kept = [l for l in self.manual_lines(key)
                if ((l[0], l[1]) < before[0]) == ((l[2], l[3]) < before[1]) and (l[0], l[1]) != before[0]]
        self._load(key)["lines"] = sorted(kept + [(pa, round(ya, 1), pb, round(yb, 1))])
        self._save(key)

    def has_manual(self, key: str) -> bool:
        data = self._load(key)
        return any(data.get(k) for k in ("pages", "gaps", "lines"))

    def clear(self, key: str) -> None:
        self._cache[key] = {}
        self._save(key)
