"""Anotações (destaques e notas) guardadas fora do PDF.

O PDF original nunca é alterado. As anotações ficam em um arquivo JSON por
documento, na pasta de dados do programa, identificado pelo conteúdo do PDF
(hash SHA-256). Assim elas reaparecem mesmo que o arquivo seja renomeado ou
movido, e não se misturam se outro PDF tiver o mesmo nome.

Coordenadas: as da página sem rotação (as mesmas de page.get_text("words")).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz

from app.services.text_index import Rect

HIGHLIGHT = "highlight"
NOTE = "note"
FORMAT_VERSION = 1

HIGHLIGHT_COLOR = (1.0, 0.85, 0.0)   # amarelo
NOTE_COLOR = (1.0, 0.6, 0.0)         # laranja
NOTE_SIZE = 18.0                     # tamanho do ícone da nota (pontos)


@dataclass
class Annotation:
    kind: str                       # HIGHLIGHT ou NOTE
    page: int
    rects: List[Rect]               # destaque: áreas das palavras; nota: [ícone]
    text: str = ""                  # conteúdo da nota (ou comentário do destaque)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def bounds(self) -> Rect:
        return (min(r[0] for r in self.rects), min(r[1] for r in self.rects),
                max(r[2] for r in self.rects), max(r[3] for r in self.rects))

    def contains(self, x: float, y: float, tolerance: float = 0.0) -> bool:
        return any(r[0] - tolerance <= x <= r[2] + tolerance and r[1] - tolerance <= y <= r[3] + tolerance
                   for r in self.rects)

    @classmethod
    def from_dict(cls, data: dict) -> "Annotation":
        kind = data.get("kind")
        if kind not in (HIGHLIGHT, NOTE):
            raise ValueError(f"tipo de anotação desconhecido: {kind!r}")
        rects = [tuple(float(v) for v in r) for r in data.get("rects", [])]
        if not rects or any(len(r) != 4 for r in rects):
            raise ValueError("anotação sem área válida")
        return cls(kind=kind, page=int(data["page"]), rects=rects, text=str(data.get("text", "")),
                   id=str(data.get("id") or uuid.uuid4().hex))


def file_fingerprint(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def note_rect(x: float, y: float) -> Rect:
    return (x, y, x + NOTE_SIZE, y + NOTE_SIZE)


def words_in_rect(page: fitz.Page, rect: Rect) -> List[Rect]:
    """Áreas das palavras que tocam o retângulo (para destacar texto selecionado)."""
    area = fitz.Rect(rect).normalize()
    return [tuple(w[:4]) for w in page.get_text("words") if fitz.Rect(w[:4]).intersects(area)]


class AnnotationStore:
    """Lê e grava as anotações de cada documento em `folder`."""

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)
        self._cache: Dict[str, List[Annotation]] = {}

    def _file(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def load(self, key: str) -> List[Annotation]:
        if key in self._cache:
            return self._cache[key]
        items: List[Annotation] = []
        try:
            data = json.loads(self._file(key).read_text(encoding="utf-8"))
            for raw in data.get("annotations", []):
                try:
                    items.append(Annotation.from_dict(raw))
                except (KeyError, TypeError, ValueError):
                    continue   # ignora só a anotação danificada
        except (OSError, ValueError, AttributeError):
            items = []
        self._cache[key] = items
        return items

    def save(self, key: str, name: str = "") -> None:
        items = self._cache.get(key, [])
        path = self._file(key)
        if not items:
            path.unlink(missing_ok=True)
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        data = {"version": FORMAT_VERSION, "file_name": name,
                "annotations": [asdict(a) for a in items]}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    def add(self, key: str, annotation: Annotation, name: str = "") -> None:
        self.load(key).append(annotation)
        self.save(key, name)

    def remove(self, key: str, annotation_id: str, name: str = "") -> bool:
        items = self.load(key)
        before = len(items)
        items[:] = [a for a in items if a.id != annotation_id]
        if len(items) != before:
            self.save(key, name)
            return True
        return False

    def update_text(self, key: str, annotation_id: str, text: str, name: str = "") -> bool:
        for a in self.load(key):
            if a.id == annotation_id:
                a.text = text
                self.save(key, name)
                return True
        return False

    def clear(self, key: str) -> None:
        self._cache[key] = []
        self.save(key)


def for_page(annotations: Sequence[Annotation], page: Optional[int]) -> List[Annotation]:
    return [a for a in annotations if a.page == page]


def find_at(annotations: Sequence[Annotation], page: int, x: float, y: float) -> Optional[Annotation]:
    """Anotação sob o ponto (a mais recente, se houver sobreposição)."""
    for a in reversed(annotations):
        if a.page == page and a.contains(x, y, tolerance=2.0):
            return a
    return None


def apply_to_page(page: fitz.Page, annotations: Sequence[Annotation]) -> None:
    """Grava as anotações como anotações PDF de verdade (em uma cópia, nunca no original)."""
    for a in annotations:
        if a.kind == HIGHLIGHT:
            quads = [fitz.Rect(r).quad for r in a.rects]
            annot = page.add_highlight_annot(quads)
            annot.set_colors(stroke=HIGHLIGHT_COLOR)
            if a.text:
                annot.set_info(content=a.text, title="PDF Compare")
        else:
            x0, y0 = a.rects[0][0], a.rects[0][1]
            annot = page.add_text_annot(fitz.Point(x0, y0), a.text or "", icon="Note")
            annot.set_colors(stroke=NOTE_COLOR)
            annot.set_info(title="PDF Compare")
        annot.update()


def annotated_copy(doc: fitz.Document, annotations: Sequence[Annotation],
                   pages: Optional[Tuple[int, int]] = None, bake: bool = False) -> fitz.Document:
    """Cópia em memória do documento (ou de um intervalo de páginas) com as anotações.

    Com `bake`, as anotações viram parte do conteúdo da página (necessário para
    que apareçam quando a página é desenhada dentro de outra).
    """
    first, last = pages if pages is not None else (0, doc.page_count - 1)
    copy = fitz.open()
    copy.insert_pdf(doc, from_page=first, to_page=last)
    for a in annotations:
        if first <= a.page <= last:
            apply_to_page(copy[a.page - first], [a])
    if bake:
        copy.bake()
    return copy


def save_annotated_pdf(doc: fitz.Document, annotations: Sequence[Annotation], out_path: Path | str) -> None:
    """Salva um novo PDF com as anotações (editáveis em outros leitores)."""
    copy = annotated_copy(doc, annotations)
    try:
        copy.save(str(out_path), garbage=3, deflate=True)
    finally:
        copy.close()
