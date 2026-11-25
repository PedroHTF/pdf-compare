"""Índice de texto por documento: palavras de cada página com suas posições.

As posições (retângulos) permitem destacar as ocorrências na página renderizada.
"""

from __future__ import annotations

import string
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Tuple

import fitz

Rect = Tuple[float, float, float, float]

_PUNCT = string.punctuation + "“”‘’«»–—…•·¿¡"


def fold(text: str, case_sensitive: bool = False, ignore_accents: bool = True) -> str:
    """Normaliza o texto para comparação (acentos, ligaduras e maiúsculas)."""
    if ignore_accents:
        decomposed = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in decomposed if not unicodedata.combining(c))
    else:
        text = unicodedata.normalize("NFKC", text)
    if not case_sensitive:
        text = text.casefold()
    return text


def clean(word: str) -> str:
    """Remove pontuação nas extremidades ("contrato," -> "contrato")."""
    stripped = word.strip(_PUNCT)
    return stripped or word


@dataclass
class Token:
    text: str
    rects: List[Rect]
    line: int = 0   # identificador da linha na página (bloco e linha do PyMuPDF)
    raw: str = ""   # texto como está no PDF, com pontuação (para o relatório de diferenças)


def extract_tokens(page: fitz.Page, textpage: "fitz.TextPage | None" = None) -> List[Token]:
    """Extrai as palavras da página, juntando palavras hifenizadas no fim da linha.

    `textpage` permite usar um texto já extraído (por exemplo, o resultado do OCR).
    """
    words = page.get_text("words", textpage=textpage) if textpage is not None else page.get_text("words")
    tokens: List[Token] = []
    carry: Token | None = None

    for i, w in enumerate(words):
        x0, y0, x1, y1, txt, block, line = w[:7]
        rect = (x0, y0, x1, y1)
        if carry is not None:
            text, rects = carry.text[:-1] + txt, carry.rects + [rect]
            carry = None
        else:
            text, rects = txt, [rect]

        nxt = words[i + 1] if i + 1 < len(words) else None
        ends_line = nxt is None or (nxt[5], nxt[6]) != (block, line)
        if nxt is not None and ends_line and len(text) > 1 and text.endswith("-"):
            carry = Token(text, rects, block * 10000 + line)  # "docu-" + "mento" na linha seguinte
            continue
        tokens.append(Token(clean(text), rects, block * 10000 + line, text))

    if carry is not None:
        tokens.append(Token(clean(carry.text), carry.rects, carry.line, carry.text))
    return tokens


class DocumentIndex:
    """Palavras de um documento, preenchidas página a página."""

    def __init__(self, page_count: int) -> None:
        self.page_count = page_count
        self.pages: List[List[Token]] = []
        self._folded: Dict[Tuple[bool, bool], List[List[str]]] = {}

    @property
    def complete(self) -> bool:
        return len(self.pages) >= self.page_count

    def add_page(self, tokens: List[Token]) -> None:
        self.pages.append(tokens)

    def folded(self, case_sensitive: bool, ignore_accents: bool) -> List[List[str]]:
        """Textos normalizados por página (calculados uma vez por combinação de opções)."""
        cache = self._folded.setdefault((case_sensitive, ignore_accents), [])
        for p in range(len(cache), len(self.pages)):
            cache.append([fold(t.text, case_sensitive, ignore_accents) for t in self.pages[p]])
        return cache

    @classmethod
    def build(cls, doc: fitz.Document) -> "DocumentIndex":
        index = cls(doc.page_count)
        for page in doc:
            index.add_page(extract_tokens(page))
        return index
