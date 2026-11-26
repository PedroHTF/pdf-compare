"""O que entra na comparação de texto: cabeçalho, rodapé e páginas ignoradas.

O usuário pode deixar de fora da comparação (e do alinhamento por conteúdo):
- o cabeçalho e/ou o rodapé de cada página: faixas no topo e na base, em % da
  altura da página (vale para todos os PDFs);
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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

import fitz

from app.services.text_index import DocumentIndex, Token

MAX_ZONE = 40   # % da altura: limite do cabeçalho / rodapé

# geometria de cada página: matriz de rotação (6 números) e altura na tela (pontos)
PageGeometry = Tuple[Tuple[float, float, float, float, float, float], float]


@dataclass(frozen=True)
class CompareScope:
    header: int = 0    # % da altura da página ignorada no topo (0 = não ignorar)
    footer: int = 0    # % ignorada na base

    @property
    def active(self) -> bool:
        return self.header > 0 or self.footer > 0

    def key(self) -> str:
        return f"h{self.header}f{self.footer}" if self.active else ""

    def band(self, height: float) -> Tuple[float, float]:
        """Faixa vertical (pontos, página como é mostrada) que entra na comparação."""
        return height * self.header / 100, height * (1 - self.footer / 100)


def page_geometry(doc: fitz.Document) -> List[PageGeometry]:
    out: List[PageGeometry] = []
    for page in doc:
        m = page.rotation_matrix
        out.append(((m.a, m.b, m.c, m.d, m.e, m.f), page.rect.height))
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
        matrix, height = self.geometry[page]
        top, bottom = self.scope.band(height)
        m = fitz.Matrix(*matrix)
        kept = []
        for token in tokens:
            if not token.rects:
                continue
            x0, y0, x1, y1 = token.rects[0]
            y = (fitz.Point((x0 + x1) / 2, (y0 + y1) / 2) * m).y
            if top <= y <= bottom:
                kept.append(token)
        return kept


def scoped_index(base: Optional[DocumentIndex], scope: CompareScope, geometry: Sequence[PageGeometry],
                 ignored: Iterable[int] = ()) -> Optional[DocumentIndex]:
    """O índice como a comparação o vê (o próprio índice, se nada é ignorado)."""
    ignored = frozenset(ignored)
    if base is None or (not scope.active and not ignored):
        return base
    return FilteredIndex(base, scope, geometry, ignored)


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
