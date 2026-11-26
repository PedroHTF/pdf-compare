"""O que entra na comparação de texto: cabeçalho, rodapé e páginas ignoradas.

O usuário pode deixar de fora da comparação (e do alinhamento por conteúdo):
- o cabeçalho e/ou o rodapé de cada página: faixas no topo e na base, em % da
  altura da página (vale para todos os PDFs); `detect_bands` sugere essas faixas
  procurando texto que se repete no topo e na base das páginas (até 40%);
- faixas nas laterais (esquerda e direita), em % da largura;
- páginas escolhidas de cada PDF (ex.: índice, capa), guardadas pelo conteúdo
  do PDF e lembradas ao abri-lo de novo.

`FilteredIndex` é uma "vista" do índice de texto sem essas palavras. Ela acompanha
o índice original enquanto ele ainda está sendo lido. A pesquisa continua usando
o índice completo. Sem dependência de interface gráfica (só PyMuPDF para as
páginas giradas).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

import fitz

from app.services.text_index import DocumentIndex, Token

MAX_ZONE = 40   # % da altura (ou largura): limite de cada faixa ignorada

# geometria de cada página: matriz de rotação (6 números), altura e largura na tela (pontos)
PageGeometry = Tuple[Tuple[float, float, float, float, float, float], float, float]


BANDS = ("header", "footer", "left", "right")


@dataclass(frozen=True)
class CompareScope:
    header: float = 0.0    # % da altura da página ignorada no topo (0 = não ignorar)
    footer: float = 0.0    # % ignorada na base
    left: float = 0.0      # % da largura ignorada à esquerda
    right: float = 0.0     # % ignorada à direita

    @property
    def active(self) -> bool:
        return any(getattr(self, k) > 0 for k in BANDS)

    def key(self) -> str:
        if not self.active:
            return ""
        return "h{:g}f{:g}l{:g}r{:g}".format(self.header, self.footer, self.left, self.right)

    def band(self, height: float) -> Tuple[float, float]:
        """Faixa vertical (pontos, página como é mostrada) que entra na comparação."""
        return height * self.header / 100, height * (1 - self.footer / 100)

    def hband(self, width: float) -> Tuple[float, float]:
        """Faixa horizontal que entra na comparação."""
        return width * self.left / 100, width * (1 - self.right / 100)

    def contains(self, x: float, y: float, width: float, height: float) -> bool:
        top, bottom = self.band(height)
        left, right = self.hband(width)
        return top <= y <= bottom and left <= x <= right


def page_geometry(doc: fitz.Document) -> List[PageGeometry]:
    out: List[PageGeometry] = []
    for page in doc:
        m = page.rotation_matrix
        out.append(((m.a, m.b, m.c, m.d, m.e, m.f), page.rect.height, page.rect.width))
    return out


class FilteredIndex(DocumentIndex):
    """Índice de texto sem as palavras do cabeçalho, do rodapé e das páginas ignoradas."""

    def __init__(self, base: DocumentIndex, scope: CompareScope, geometry: Sequence[PageGeometry],
                 ignored: Iterable[int] = ()) -> None:   # noqa: D107 (não chama DocumentIndex.__init__)
        self.base = base
        self.page_count = base.page_count
        self.scope = scope
        self.geometry = list(geometry)
        self.ignored: FrozenSet[int] = frozenset(ignored)
        self._filtered: List[List[Token]] = []
        self._folded = {}

    @property
    def pages(self) -> List[List[Token]]:   # type: ignore[override]
        source = self.base.pages
        while len(self._filtered) < len(source):
            p = len(self._filtered)
            self._filtered.append(self._keep(p, source[p]))
        return self._filtered

    @pages.setter
    def pages(self, value) -> None:   # DocumentIndex.__init__ não é chamado; só por segurança
        self._filtered = list(value)

    def add_page(self, tokens: List[Token]) -> None:   # o índice de origem é quem cresce
        raise TypeError("FilteredIndex é só leitura")

    def _keep(self, page: int, tokens: List[Token]) -> List[Token]:
        if page in self.ignored:
            return []
        if not self.scope.active or page >= len(self.geometry):
            return tokens
        matrix, height, width = self.geometry[page]
        m = fitz.Matrix(*matrix)
        kept = []
        for token in tokens:
            if not token.rects:
                continue
            x0, y0, x1, y1 = token.rects[0]
            point = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2) * m
            if self.scope.contains(point.x, point.y, width, height):
                kept.append(token)
        return kept


def scoped_index(base: Optional[DocumentIndex], scope: CompareScope, geometry: Sequence[PageGeometry],
                 ignored: Iterable[int] = ()) -> Optional[DocumentIndex]:
    """O índice como a comparação o vê (o próprio índice, se nada é ignorado)."""
    ignored = frozenset(ignored)
    if base is None or (not scope.active and not ignored):
        return base
    return FilteredIndex(base, scope, geometry, ignored)


# --- detecção automática do cabeçalho e do rodapé -----------------------------------------------------
MIN_SHARE = 0.5      # o texto precisa se repetir em pelo menos metade das páginas
BAND_MARGIN = 1.0    # % somado à borda do texto repetido


def _normalized(text: str) -> str:
    """Igual em todas as páginas: minúsculas e números trocados (ex.: "Página 3 de 10")."""
    return re.sub(r"\d+", "#", " ".join(text.lower().split()))


POSITION_SPREAD = 3.0   # % da altura: o texto repetido fica (quase) no mesmo lugar em todas as páginas


def _page_lines(tokens, matrix, height) -> List[Tuple[float, float, str]]:
    """Linhas da página como (topo %, base %, texto normalizado), de cima para baixo."""
    m = fitz.Matrix(*matrix)
    lines: Dict[int, List] = defaultdict(list)
    for token in tokens:
        if token.rects:
            lines[token.line].append(token)
    out = []
    for items in lines.values():
        ys = []
        for t in items:
            for x0, y0, x1, y1 in t.rects:
                ys += [(fitz.Point(x0, y0) * m).y, (fitz.Point(x1, y1) * m).y]
        key = _normalized(" ".join(t.raw or t.text for t in items))
        if key:
            out.append((min(ys) / height * 100, max(ys) / height * 100, key))
    return sorted(out)


def detect_bands(index: Optional[DocumentIndex], geometry: Sequence[PageGeometry],
                 limit: float = MAX_ZONE) -> Tuple[float, float]:
    """Sugere (% cabeçalho, % rodapé) para um PDF. (0, 0) se não achar.

    Cabeçalho: as primeiras linhas de cada página que se repetem (com os números
    trocados, ex.: "Página 3 de 10") em pelo menos metade das páginas, quase no
    mesmo lugar, até `limit` % a partir do topo. Rodapé: o mesmo, a partir da base.
    """
    if index is None:
        return 0.0, 0.0
    n = min(len(index.pages), len(geometry))
    if n < 2:
        return 0.0, 0.0
    pages = []
    for p in range(n):
        matrix, height, _ = geometry[p]
        pages.append(_page_lines(index.pages[p], matrix, height) if height > 0 else [])
    need = max(2, -(-n * MIN_SHARE // 1))

    def repeated(zone) -> set:
        where: Dict[str, Dict[int, float]] = defaultdict(dict)
        twice = set()      # aparece mais de uma vez na mesma página: é corpo (ex.: linhas de tabela)
        for p, lines in enumerate(pages):
            for top, bottom, key in lines:
                if zone(top, bottom):
                    if p in where[key]:
                        twice.add(key)
                    where[key].setdefault(p, top)
        return {k for k, v in where.items() if k not in twice
                and len(v) >= need and max(v.values()) - min(v.values()) <= POSITION_SPREAD}

    top_keys = repeated(lambda top, bottom: bottom <= limit)
    bottom_keys = repeated(lambda top, bottom: top >= 100 - limit)
    header_ends, footer_starts = [], []
    for lines in pages:
        end = None
        for top, bottom, key in lines:                 # de cima para baixo, enquanto se repetem
            if key not in top_keys or bottom > limit:
                break
            end = bottom
        if end is not None:
            header_ends.append(end)
        start = None
        for top, bottom, key in reversed(lines):       # de baixo para cima
            if key not in bottom_keys or top < 100 - limit:
                break
            start = top
        if start is not None:
            footer_starts.append(start)
    header = footer = 0.0
    if len(header_ends) >= need:
        header = min(median(header_ends) + BAND_MARGIN, limit)
    if len(footer_starts) >= need:
        footer = min(100 - median(footer_starts) + BAND_MARGIN, limit)
    return round(header * 2) / 2, round(footer * 2) / 2


def merge_detected(found: Iterable[Tuple[float, float]]) -> Tuple[float, float]:
    """Vários PDFs: a maior faixa de cada lado (vale para todos)."""
    found = list(found)
    return (max((h for h, _ in found), default=0.0), max((f for _, f in found), default=0.0))


# --- páginas ignoradas --------------------------------------------------------------------------------
def parse_pages(text: str, page_count: int) -> Set[int]:
    """"1-3, 7" -> {0, 1, 2, 6} (páginas contadas a partir de 1 no texto). ValueError se inválido."""
    pages: Set[int] = set()
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:\s*[-–]\s*(\d+))?", part)
        if match is None:
            raise ValueError(part)
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first > last:
            first, last = last, first
        if first < 1 or last > page_count:
            raise ValueError(part)
        pages.update(range(first - 1, last))
    return pages


def format_pages(pages: Iterable[int]) -> str:
    """{0, 1, 2, 6} -> "1-3, 7"."""
    ordered = sorted(set(pages))
    parts: List[str] = []
    k = 0
    while k < len(ordered):
        start = end = ordered[k]
        while k + 1 < len(ordered) and ordered[k + 1] == end + 1:
            k += 1
            end = ordered[k]
        parts.append(f"{start + 1}" if start == end else f"{start + 1}-{end + 1}")
        k += 1
    return ", ".join(parts)


class IgnoredPagesStore:
    """Páginas ignoradas de cada PDF (pela impressão digital do conteúdo), em um arquivo JSON."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._data: Optional[Dict[str, List[int]]] = None

    def _load(self) -> Dict[str, List[int]]:
        if self._data is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = {str(k): [int(p) for p in v] for k, v in data.items()} if isinstance(data, dict) else {}
            except (OSError, ValueError, TypeError, AttributeError):
                self._data = {}
        return self._data

    def pages(self, fingerprint: Optional[str]) -> FrozenSet[int]:
        return frozenset(self._load().get(fingerprint, ())) if fingerprint else frozenset()

    def set_pages(self, fingerprint: str, pages: Iterable[int]) -> None:
        data = self._load()
        pages = sorted(set(int(p) for p in pages))
        if pages:
            data[fingerprint] = pages
        else:
            data.pop(fingerprint, None)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def toggle(self, fingerprint: str, page: int) -> bool:
        """Liga/desliga uma página; devolve True se ela passou a ser ignorada."""
        pages = set(self.pages(fingerprint))
        now = page not in pages
        (pages.add if now else pages.discard)(page)
        self.set_pages(fingerprint, pages)
        return now
