"""Pesquisa de palavras e frases em um índice de documento."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from app.services.text_index import DocumentIndex, Rect, clean, fold


@dataclass(frozen=True)
class SearchOptions:
    case_sensitive: bool = False
    whole_word: bool = False
    ignore_accents: bool = True


@dataclass(frozen=True)
class Hit:
    page: int                   # índice da página no arquivo
    rects: Tuple[Rect, ...]     # áreas a destacar (coordenadas da página)


def parse_query(query: str, options: SearchOptions) -> List[str]:
    folded = fold(query, options.case_sensitive, options.ignore_accents)
    return [part for part in (clean(p) for p in folded.split()) if part]


def search_index(index: DocumentIndex, query: str, options: SearchOptions = SearchOptions()) -> List[Hit]:
    """Ocorrências em ordem de leitura. Frases podem ocupar várias palavras."""
    terms = parse_query(query, options)
    if not terms:
        return []
    folded_pages = index.folded(options.case_sensitive, options.ignore_accents)
    n = len(terms)
    hits: List[Hit] = []
    for page_no, words in enumerate(folded_pages):
        tokens = index.pages[page_no]
        for i in range(len(words) - n + 1):
            if _matches(words, i, terms, options.whole_word):
                rects = tuple(r for t in tokens[i:i + n] for r in t.rects)
                hits.append(Hit(page_no, rects))
    return hits


def _matches(words: List[str], i: int, terms: List[str], whole_word: bool) -> bool:
    n = len(terms)
    if whole_word:
        return all(words[i + k] == terms[k] for k in range(n))
    if n == 1:
        return terms[0] in words[i]
    # frase: a primeira palavra pode ser final de palavra, a última pode ser início
    if not words[i].endswith(terms[0]) or not words[i + n - 1].startswith(terms[-1]):
        return False
    return all(words[i + k] == terms[k] for k in range(1, n - 1))
