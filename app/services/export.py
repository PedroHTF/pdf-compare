"""Exportação da comparação e das páginas atuais como PDF ou PNG.

- Comparação lado a lado: uma página de saída por posição, com as páginas dos
  PDFs em colunas e o nome de cada arquivo acima. Em PDF o conteúdo continua
  vetorial (texto selecionável); em PNG é uma imagem por posição.
- Páginas atuais: um arquivo por PDF, com a página que está à vista.

Com `annotations`, os destaques e notas do usuário entram na saída.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import fitz

from app.services.annotations import Annotation, annotated_copy

PDF = "pdf"
PNG = "png"
FORMATS = (PDF, PNG)

GAP = 18.0          # espaço entre colunas (pontos)
MARGIN = 18.0
LABEL_HEIGHT = 22.0
LABEL_SIZE = 10.0
DEFAULT_DPI = 150


class ExportError(Exception):
    """Falha ao exportar (pasta sem permissão, disco cheio...)."""


@dataclass
class Column:
    """Um PDF na exportação."""

    doc: fitz.Document
    name: str
    annotations: Sequence[Annotation] = field(default_factory=list)


Row = List[Optional[int]]   # página de cada coluna (None = sem página nessa posição)


def _source(column: Column, page_no: int, cache: Dict) -> tuple:
    """Documento e página a usar como origem (cópia anotada, se houver anotações nela)."""
    if not any(a.page == page_no for a in column.annotations):
        return column.doc, page_no
    key = (id(column), page_no)
    if key not in cache:
        cache[key] = annotated_copy(column.doc, column.annotations, (page_no, page_no), bake=True)
    return cache[key], 0


def build_comparison(columns: Sequence[Column], rows: Sequence[Row], labels: bool = True) -> fitz.Document:
    """Monta um PDF com uma página por linha de `rows`, colunas lado a lado."""
    if not columns:
        raise ExportError("Nenhum PDF para exportar.")
    out = fitz.open()
    cache: Dict = {}
    try:
        for row in rows:
            sizes = []
            for col, page_no in zip(columns, row):
                rect = col.doc[page_no].rect if page_no is not None else None
                sizes.append(rect)
            known = [r for r in sizes if r is not None] or [fitz.paper_rect("a4")]
            cell_w = max(r.width for r in known)
            cell_h = max(r.height for r in known)
            top = MARGIN + (LABEL_HEIGHT if labels else 0)
            width = 2 * MARGIN + len(columns) * cell_w + (len(columns) - 1) * GAP
            height = top + cell_h + MARGIN
            page = out.new_page(width=width, height=height)
            page.draw_rect(page.rect, color=None, fill=(0.93, 0.93, 0.93))
            for c, (col, page_no) in enumerate(zip(columns, row)):
                x0 = MARGIN + c * (cell_w + GAP)
                cell = fitz.Rect(x0, top, x0 + cell_w, top + cell_h)
                if labels:
                    caption = col.name if page_no is None else f"{col.name} · página {page_no + 1}"
                    page.insert_textbox(fitz.Rect(x0, MARGIN, x0 + cell_w, top - 4), caption,
                                        fontsize=LABEL_SIZE, fontname="helv", color=(0.2, 0.2, 0.2))
                if page_no is None:
                    page.draw_rect(cell, color=(0.7, 0.7, 0.7), fill=(0.98, 0.98, 0.98), dashes="[4] 0")
                    page.insert_textbox(cell + (0, cell.height / 2 - 10, 0, 0), "(sem página nesta posição)",
                                        fontsize=LABEL_SIZE, fontname="helv", align=fitz.TEXT_ALIGN_CENTER,
                                        color=(0.5, 0.5, 0.5))
                    continue
                src_doc, src_page = _source(col, page_no, cache)
                page.draw_rect(cell, color=None, fill=(1, 1, 1))
                page.show_pdf_page(cell, src_doc, src_page, keep_proportion=True)
    except Exception:
        out.close()
        raise
    finally:
        for doc in cache.values():
            doc.close()
    return out


def build_single(column: Column, page_no: int) -> fitz.Document:
    """PDF com uma única página de um documento (com as anotações dessa página)."""
    if any(a.page == page_no for a in column.annotations):
        return annotated_copy(column.doc, column.annotations, (page_no, page_no))
    out = fitz.open()
    out.insert_pdf(column.doc, from_page=page_no, to_page=page_no)
    return out


def numbered_paths(path: Path, count: int) -> List[Path]:
    """Nomes para várias imagens: comparacao.png -> comparacao_001.png, comparacao_002.png..."""
    if count == 1:
        return [path]
    digits = max(3, len(str(count)))
    return [path.with_name(f"{path.stem}_{i + 1:0{digits}d}{path.suffix}") for i in range(count)]


def write(doc: fitz.Document, path: Path | str, fmt: str, dpi: int = DEFAULT_DPI,
          progress: Optional[Callable[[int, int], None]] = None) -> List[Path]:
    """Grava o documento montado como PDF (um arquivo) ou PNG (um arquivo por página)."""
    path = Path(path)
    if fmt not in FORMATS:
        raise ExportError(f"Formato desconhecido: {fmt}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == PDF:
            doc.save(str(path), garbage=3, deflate=True)
            return [path]
        targets = numbered_paths(path, doc.page_count)
        for i, (page, target) in enumerate(zip(doc, targets)):
            page.get_pixmap(dpi=dpi, alpha=False).save(str(target))
            if progress is not None:
                progress(i + 1, len(targets))
        return targets
    except OSError as exc:
        raise ExportError(f"Não foi possível gravar “{path.name}”: {exc.strerror or exc}") from exc


def export_comparison(columns: Sequence[Column], rows: Sequence[Row], path: Path | str, fmt: str,
                      dpi: int = DEFAULT_DPI, labels: bool = True,
                      progress: Optional[Callable[[int, int], None]] = None) -> List[Path]:
    doc = build_comparison(columns, rows, labels)
    try:
        return write(doc, path, fmt, dpi, progress)
    finally:
        doc.close()


def safe_stem(name: str) -> str:
    stem = Path(name).stem
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in stem).strip() or "documento"


def export_current_pages(columns: Sequence[Column], pages: Sequence[Optional[int]], folder: Path | str,
                         fmt: str, dpi: int = DEFAULT_DPI) -> List[Path]:
    """Um arquivo por PDF com a página à vista: <nome>_p<N>.pdf/png. PDFs sem página são pulados."""
    folder = Path(folder)
    written: List[Path] = []
    used: set = set()
    for column, page_no in zip(columns, pages):
        if page_no is None:
            continue
        base = f"{safe_stem(column.name)}_p{page_no + 1}"
        name, k = base, 2
        while name in used:
            name, k = f"{base}_{k}", k + 1
        used.add(name)
        doc = build_single(column, page_no)
        try:
            written += write(doc, folder / f"{name}.{fmt}", fmt, dpi)
        finally:
            doc.close()
    return written
