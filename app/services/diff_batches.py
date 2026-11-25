"""Comparação de texto em lotes de páginas, com cache em disco.

Em PDFs grandes, comparar tudo de uma vez pode demorar. Aqui o documento de
referência (o 1º PDF) é dividido em lotes de N páginas; para cada outro PDF,
o lote usa as páginas correspondentes, levando em conta o alinhamento feito
pelo usuário (deslocamento de cada painel). O primeiro lote começa na página 1
de todos os PDFs e o último vai até o fim de cada um, para que páginas a mais
ou a menos nas pontas apareçam como diferença.

Cada par (referência, outro PDF) de cada lote é guardado em um arquivo JSON na
pasta de cache, identificado pelo conteúdo dos dois PDFs, pelas páginas do lote
e pelas opções da comparação. Ao reabrir os mesmos arquivos, os lotes já
comparados são carregados sem refazer o trabalho. Arquivos não usados há mais
de N dias são apagados (configurável; 0 = nunca).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from app.services.text_diff import DiffMark, PageRange

ALGORITHM_VERSION = 1    # mude quando a comparação passar a produzir resultados diferentes
ALL_PAGES = 0            # tamanho de lote "tudo de uma vez"
DEFAULT_BATCH_SIZE = 50
DEFAULT_RETENTION_DAYS = 30

Pair = Tuple[List[DiffMark], List[DiffMark]]   # (marcas na referência, marcas no outro PDF)


@dataclass(frozen=True)
class Batch:
    number: int                       # 0, 1, 2...
    ranges: Tuple[PageRange, ...]     # páginas [início, fim) de cada PDF
    primary: int = 0                  # PDF que define os lotes (a referência ou o 1º da cadeia)

    @property
    def ref_range(self) -> PageRange:
        return self.ranges[self.primary]

    def label_pages(self) -> Tuple[int, int]:
        """Primeira e última página da referência, contadas a partir de 1."""
        start, end = self.ref_range
        return start + 1, max(end, start + 1)


def plan_batches(page_counts: Sequence[int], offsets: Sequence[int], batch_size: int,
                 primary: int = 0) -> List[Batch]:
    """Divide a comparação em lotes de páginas do PDF `primary`.

    `offsets[i]` é quantas páginas o PDF i está adiantado em relação ao principal
    (página do PDF i = página do principal + offsets[i]); offsets[primary] é 0.
    `batch_size` = 0 compara tudo em um único lote.
    """
    if not page_counts:
        return []
    ref_pages = page_counts[primary]
    if batch_size <= 0 or ref_pages <= batch_size:
        count = 1
        batch_size = max(ref_pages, 1)
    else:
        count = math.ceil(ref_pages / batch_size)
    batches = []
    for k in range(count):
        start = k * batch_size
        end = ref_pages if k == count - 1 else min((k + 1) * batch_size, ref_pages)
        ranges = []
        for i, (pages, offset) in enumerate(zip(page_counts, offsets)):
            if i == primary:
                ranges.append((start, end))
                continue
            first = 0 if k == 0 else min(max(start + offset, 0), pages)
            last = pages if k == count - 1 else min(max(end + offset, 0), pages)
            ranges.append((first, max(first, last)))
        batches.append(Batch(k, tuple(ranges), primary))
    return batches


def plan_batches_from_rows(rows: Sequence[Sequence[Optional[int]]], page_counts: Sequence[int],
                           batch_size: int, primary: int = 0) -> List[Batch]:
    """Lotes a partir do alinhamento por conteúdo (`rows`: a página de cada PDF em cada linha).

    Cada lote cobre as linhas das páginas [início, fim) do PDF principal, mais as
    páginas incluídas nos outros PDFs entre elas.
    """
    if not rows or not page_counts:
        return []
    ref_pages = page_counts[primary]
    row_of = {}
    for r, row in enumerate(rows):
        if row[primary] is not None:
            row_of.setdefault(row[primary], r)
    size = ref_pages if batch_size <= 0 or ref_pages <= batch_size else batch_size
    count = 1 if size >= ref_pages else math.ceil(ref_pages / size)
    batches = []
    for k in range(count):
        start, end = k * size, ref_pages if k == count - 1 else (k + 1) * size
        r0 = 0 if k == 0 else row_of.get(start, len(rows))
        r1 = len(rows) if k == count - 1 else row_of.get(end, len(rows))
        ranges = []
        for doc, pages in enumerate(page_counts):
            if doc == primary:
                ranges.append((start, end))
                continue
            shown = [row[doc] for row in rows[r0:r1] if row[doc] is not None]
            if shown:
                ranges.append((min(shown), max(shown) + 1))
            else:   # nada deste PDF no lote: intervalo vazio na posição certa
                after = next((row[doc] for row in rows[r1:] if row[doc] is not None), pages)
                ranges.append((after, after))
        batches.append(Batch(k, tuple(ranges), primary))
    return batches


def batch_for_page(batches: Sequence[Batch], ref_page: int) -> int:
    """Lote que contém a página da referência (o mais próximo, se estiver fora)."""
    for b in batches:
        if b.ref_range[0] <= ref_page < b.ref_range[1]:
            return b.number
    return 0 if not batches or ref_page < batches[0].ref_range[0] else batches[-1].number


def pair_key(ref_fingerprint: str, other_fingerprint: str, ref_range: PageRange, other_range: PageRange,
             options: str = "") -> str:
    """Identificador do resultado de um par em um lote (nome do arquivo no cache)."""
    text = "|".join([str(ALGORITHM_VERSION), ref_fingerprint, other_fingerprint,
                     f"{ref_range[0]}-{ref_range[1]}", f"{other_range[0]}-{other_range[1]}", options])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _marks_to_json(marks: Iterable[DiffMark]) -> list:
    return [[m.page, m.kind, [list(r) for r in m.rects]] for m in marks]


def _marks_from_json(data) -> List[DiffMark]:
    return [DiffMark(int(page), tuple(tuple(float(v) for v in r) for r in rects), str(kind))
            for page, kind, rects in data]


class DiffCache:
    """Resultados de comparação guardados em disco (um arquivo por par e lote)."""

    SUFFIX = ".json"

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)

    def _file(self, key: str) -> Path:
        return self.folder / f"{key}{self.SUFFIX}"

    def load(self, key: str) -> Optional[Pair]:
        path = self._file(key)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result = (_marks_from_json(data["ref"]), _marks_from_json(data["other"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None
        try:
            os.utime(path)   # marca como usado: a limpeza por idade conta a partir daqui
        except OSError:
            pass
        return result

    def save(self, key: str, pair: Pair) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self._file(key)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": ALGORITHM_VERSION, "ref": _marks_to_json(pair[0]),
                                       "other": _marks_to_json(pair[1])}), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass   # sem cache, a comparação continua funcionando

    def _files(self) -> List[Path]:
        try:
            return [p for p in self.folder.iterdir() if p.suffix in (self.SUFFIX, ".tmp")]
        except OSError:
            return []

    def size_bytes(self) -> int:
        total = 0
        for p in self._files():
            try:
                total += p.stat().st_size
            except OSError:
                pass
        return total

    def count(self) -> int:
        return len(self._files())

    def clear(self) -> int:
        removed = 0
        for p in self._files():
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def purge(self, days: int, now: Optional[float] = None) -> int:
        """Apaga resultados não usados há mais de `days` dias (0 = nunca apaga)."""
        if days <= 0:
            return 0
        limit = (now if now is not None else time.time()) - days * 86400
        removed = 0
        for p in self._files():
            try:
                if p.stat().st_mtime < limit:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
        return removed


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"
