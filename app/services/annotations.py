"""Marcações (destaques, formas, caixas de texto, notas...) guardadas fora do PDF.

O PDF original nunca é alterado. As marcações ficam em um arquivo JSON por
documento, na pasta de dados do programa, identificado pelo conteúdo do PDF
(hash SHA-256). Assim elas reaparecem mesmo que o arquivo seja renomeado ou
movido, e não se misturam se outro PDF tiver o mesmo nome.

Coordenadas: as da página sem rotação (as mesmas de page.get_text("words")).

Geometria de cada tipo:
- marcações de texto (destaque, sublinhado, tachado, ondulado): `rects` com a
  área de cada palavra;
- caixas (nota, retângulo, elipse, caixa de texto, balão, carimbo): `rects[0]`;
  no balão, `points[0]` é a ponta da seta;
- linha, seta e polígono: `points`; caneta: `strokes` (um traço por lista).
  Para esses, `rects[0]` guarda a área ocupada (usada para seleção).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz

from app.services.text_index import Rect

Point = Tuple[float, float]
Color = Tuple[float, float, float]   # RGB de 0 a 1

HIGHLIGHT = "highlight"
UNDERLINE = "underline"
STRIKEOUT = "strikeout"
SQUIGGLY = "squiggly"
NOTE = "note"
RECT = "rect"
ELLIPSE = "ellipse"
LINE = "line"
ARROW = "arrow"
POLYGON = "polygon"
INK = "ink"
TEXTBOX = "textbox"
CALLOUT = "callout"
STAMP = "stamp"

TEXT_MARKUPS = (HIGHLIGHT, UNDERLINE, STRIKEOUT, SQUIGGLY)
BOX_KINDS = (NOTE, RECT, ELLIPSE, TEXTBOX, CALLOUT, STAMP)
POINT_KINDS = (LINE, ARROW, POLYGON)
KINDS = TEXT_MARKUPS + BOX_KINDS + POINT_KINDS + (INK,)
TEXT_KINDS = (TEXTBOX, CALLOUT, STAMP)       # o texto aparece na página
FILLABLE = (RECT, ELLIPSE, POLYGON, TEXTBOX, CALLOUT)
RESIZABLE = tuple(k for k in KINDS if k not in TEXT_MARKUPS + (NOTE,))

FORMAT_VERSION = 2

HIGHLIGHT_COLOR = (1.0, 0.85, 0.0)   # amarelo
NOTE_COLOR = (1.0, 0.6, 0.0)         # laranja
SHAPE_COLOR = (0.86, 0.15, 0.15)     # vermelho
DEFAULT_COLORS: Dict[str, Color] = {
    HIGHLIGHT: HIGHLIGHT_COLOR, UNDERLINE: (0.1, 0.45, 0.9), STRIKEOUT: (0.86, 0.15, 0.15),
    SQUIGGLY: (0.86, 0.15, 0.15), NOTE: NOTE_COLOR, TEXTBOX: (0.1, 0.1, 0.1),
    STAMP: (0.75, 0.1, 0.1),
}
NOTE_SIZE = 18.0                     # tamanho do ícone da nota (pontos)
MIN_SIZE = 4.0                       # menor lado de uma forma (pontos)

STAMPS = ("Aprovado", "Revisar", "Divergência", "OK", "Rejeitado", "Confidencial")
STAMP_FONT = 16.0


def _color(value) -> Optional[Color]:
    if value is None:
        return None
    c = tuple(float(v) for v in value)
    if len(c) != 3:
        raise ValueError("cor inválida")
    return tuple(min(max(v, 0.0), 1.0) for v in c)


def bbox_of(points: Sequence[Point], pad: float = 0.0) -> Rect:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


@dataclass
class Annotation:
    kind: str
    page: int
    rects: List[Rect]
    text: str = ""                  # nota, comentário do destaque ou texto da caixa
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    color: Optional[Color] = None   # contorno / texto / cor do destaque
    fill: Optional[Color] = None    # preenchimento (formas e caixas)
    width: float = 1.5              # espessura do contorno (pontos)
    opacity: float = 1.0
    font_size: float = 11.0
    points: List[Point] = field(default_factory=list)
    strokes: List[List[Point]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind in POINT_KINDS and self.points and not self.rects:
            self.rects = [bbox_of(self.points)]
        if self.kind == INK and self.strokes and not self.rects:
            self.rects = [bbox_of([p for s in self.strokes for p in s])]

    @property
    def stroke_color(self) -> Color:
        return self.color or DEFAULT_COLORS.get(self.kind, SHAPE_COLOR)

    @property
    def bounds(self) -> Rect:
        rects = list(self.rects)
        if self.kind == CALLOUT and self.points:
            rects.append(bbox_of(self.points))
        return (min(r[0] for r in rects), min(r[1] for r in rects),
                max(r[2] for r in rects), max(r[3] for r in rects))

    def contains(self, x: float, y: float, tolerance: float = 0.0) -> bool:
        if self.kind in (LINE, ARROW) and len(self.points) >= 2:
            return _dist_to_segment((x, y), self.points[0], self.points[1]) <= tolerance + self.width + 2
        if self.kind == INK:
            reach = tolerance + self.width + 2
            return any(_dist_to_segment((x, y), a, b) <= reach
                       for s in self.strokes for a, b in zip(s, s[1:] or s))
        rects = list(self.rects)
        if self.kind == CALLOUT and self.points:
            rects.append(bbox_of(self.points, 3))
        return any(r[0] - tolerance <= x <= r[2] + tolerance and r[1] - tolerance <= y <= r[3] + tolerance
                   for r in rects)

    def copy(self, new_id: bool = False) -> "Annotation":
        other = copy.deepcopy(self)
        if new_id:
            other.id = uuid.uuid4().hex
        return other

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Annotation":
        kind = data.get("kind")
        if kind not in KINDS:
            raise ValueError(f"tipo de anotação desconhecido: {kind!r}")
        rects = [tuple(float(v) for v in r) for r in data.get("rects", [])]
        points = [tuple(float(v) for v in p) for p in data.get("points", [])]
        strokes = [[tuple(float(v) for v in p) for p in s] for s in data.get("strokes", [])]
        if any(len(r) != 4 for r in rects) or any(len(p) != 2 for p in points + [q for s in strokes for q in s]):
            raise ValueError("anotação com geometria inválida")
        item = cls(kind=kind, page=int(data["page"]), rects=rects, text=str(data.get("text", "")),
                   id=str(data.get("id") or uuid.uuid4().hex), color=_color(data.get("color")),
                   fill=_color(data.get("fill")), width=float(data.get("width", 1.5)),
                   opacity=min(max(float(data.get("opacity", 1.0)), 0.05), 1.0),
                   font_size=float(data.get("font_size", 11.0)), points=points, strokes=strokes)
        if not item.rects:
            raise ValueError("anotação sem área válida")
        if kind in POINT_KINDS and len(points) < 2 or kind == INK and not strokes:
            raise ValueError("anotação sem pontos")
        return item


def _dist_to_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


# --- edição de geometria -------------------------------------------------------------
def moved(a: Annotation, dx: float, dy: float) -> Annotation:
    """Cópia da anotação deslocada (dx, dy)."""
    out = a.copy()
    out.rects = [(r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy) for r in a.rects]
    out.points = [(p[0] + dx, p[1] + dy) for p in a.points]
    out.strokes = [[(p[0] + dx, p[1] + dy) for p in s] for s in a.strokes]
    return out


def resized(a: Annotation, box: Rect) -> Annotation:
    """Cópia da anotação ajustada à nova área (a ponta do balão fica no lugar)."""
    box = (min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3]))
    if box[2] - box[0] < MIN_SIZE:
        box = (box[0], box[1], box[0] + MIN_SIZE, box[3])
    if box[3] - box[1] < MIN_SIZE:
        box = (box[0], box[1], box[2], box[1] + MIN_SIZE)
    out = a.copy()
    if a.kind in BOX_KINDS:
        out.rects = [box]
        return out
    old = a.rects[0]
    sx = (box[2] - box[0]) / max(old[2] - old[0], 1e-6)
    sy = (box[3] - box[1]) / max(old[3] - old[1], 1e-6)

    def tf(p: Point) -> Point:
        return (box[0] + (p[0] - old[0]) * sx, box[1] + (p[1] - old[1]) * sy)

    out.points = [tf(p) for p in a.points]
    out.strokes = [[tf(p) for p in s] for s in a.strokes]
    out.rects = [box]
    return out


def selection_box(a: Annotation) -> Rect:
    """Área que aparece selecionada e que as alças redimensionam."""
    return a.rects[0] if a.kind in RESIZABLE else a.bounds


def stamp_rect(x: float, y: float, text: str, font_size: float = STAMP_FONT) -> Rect:
    width = max(len(text), 2) * font_size * 0.68 + font_size * 1.4
    height = font_size * 1.9
    return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def file_fingerprint(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def note_rect(x: float, y: float) -> Rect:
    return (x, y, x + NOTE_SIZE, y + NOTE_SIZE)


def words_in_rect(page: fitz.Page, rect: Rect) -> List[Rect]:
    """Áreas das palavras que tocam o retângulo (para marcar texto selecionado)."""
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
                "annotations": [a.to_dict() for a in items]}
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

    def update(self, key: str, annotation: Annotation, name: str = "") -> bool:
        items = self.load(key)
        for i, a in enumerate(items):
            if a.id == annotation.id:
                items[i] = annotation
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

    def snapshot(self, key: str) -> List[Annotation]:
        return [a.copy() for a in self.load(key)]

    def restore(self, key: str, items: Sequence[Annotation], name: str = "") -> None:
        self._cache[key] = [a.copy() for a in items]
        self.save(key, name)

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


# --- gravação como anotações PDF -----------------------------------------------------------
def _box_edge_point(box: fitz.Rect, target: fitz.Point) -> fitz.Point:
    """Ponto da borda da caixa mais próximo de `target` (onde a seta do balão sai)."""
    x = min(max(target.x, box.x0), box.x1)
    y = min(max(target.y, box.y0), box.y1)
    if box.contains(target):
        return fitz.Point(box.x0, (box.y0 + box.y1) / 2)
    return fitz.Point(x, y)


def apply_to_page(page: fitz.Page, annotations: Sequence[Annotation]) -> None:
    """Grava as anotações como anotações PDF de verdade (em uma cópia, nunca no original)."""
    for a in annotations:
        color = a.stroke_color
        if a.kind in TEXT_MARKUPS:
            quads = [fitz.Rect(r).quad for r in a.rects]
            add = {HIGHLIGHT: page.add_highlight_annot, UNDERLINE: page.add_underline_annot,
                   STRIKEOUT: page.add_strikeout_annot, SQUIGGLY: page.add_squiggly_annot}[a.kind]
            annot = add(quads)
            annot.set_colors(stroke=color)
        elif a.kind == NOTE:
            x0, y0 = a.rects[0][0], a.rects[0][1]
            annot = page.add_text_annot(fitz.Point(x0, y0), a.text or "", icon="Note")
            annot.set_colors(stroke=color)
        elif a.kind in (RECT, ELLIPSE):
            rect = fitz.Rect(a.rects[0])
            annot = page.add_rect_annot(rect) if a.kind == RECT else page.add_circle_annot(rect)
            annot.set_colors(stroke=color, fill=a.fill)
            annot.set_border(width=a.width)
        elif a.kind in (LINE, ARROW):
            annot = page.add_line_annot(fitz.Point(a.points[0]), fitz.Point(a.points[1]))
            annot.set_colors(stroke=color, fill=color)
            annot.set_border(width=a.width)
            if a.kind == ARROW:
                annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
        elif a.kind == POLYGON:
            annot = page.add_polygon_annot([fitz.Point(p) for p in a.points])
            annot.set_colors(stroke=color, fill=a.fill)
            annot.set_border(width=a.width)
        elif a.kind == INK:
            annot = page.add_ink_annot([[tuple(p) for p in s] for s in a.strokes])
            annot.set_colors(stroke=color)
            annot.set_border(width=a.width)
        elif a.kind in (TEXTBOX, CALLOUT):
            box = fitz.Rect(a.rects[0])
            callout = None
            if a.kind == CALLOUT and a.points:
                tip = fitz.Point(a.points[0])
                callout = [tip, _box_edge_point(box, tip)]
            annot = page.add_freetext_annot(
                box, a.text or " ", fontsize=a.font_size, fontname="Helv", text_color=color,
                fill_color=a.fill,   # a borda usa a cor do texto (border_color exige rich text)
                border_width=a.width if a.kind == TEXTBOX else max(a.width, 1.0),
                callout=callout, line_end=fitz.PDF_ANNOT_LE_OPEN_ARROW, opacity=a.opacity)
        elif a.kind == STAMP:
            box = fitz.Rect(a.rects[0])
            annot = page.add_freetext_annot(
                box, a.text.upper(), fontsize=min(a.font_size, box.height * 0.6), fontname="Helv",
                text_color=color, border_width=max(a.width, 2.0),
                align=fitz.TEXT_ALIGN_CENTER, opacity=a.opacity)
        else:   # pragma: no cover - tipos validados em from_dict
            continue
        if a.opacity < 1.0 and a.kind not in (TEXTBOX, CALLOUT, STAMP):
            annot.set_opacity(a.opacity)
        info = {"title": "PDF Compare"}
        if a.text and a.kind not in (TEXTBOX, CALLOUT, STAMP):
            info["content"] = a.text
        annot.set_info(**info)
        annot.update()


def annotated_copy(doc: fitz.Document, annotations: Sequence[Annotation],
                   pages: Optional[Tuple[int, int]] = None, bake: bool = False) -> fitz.Document:
    """Cópia em memória do documento (ou de um intervalo de páginas) com as anotações.

    Com `bake`, as anotações viram parte do conteúdo da página (necessário para
    que apareçam quando a página é desenhada dentro de outra).
    """
    first, last = pages if pages is not None else (0, doc.page_count - 1)
    out = fitz.open()
    out.insert_pdf(doc, from_page=first, to_page=last)
    for a in annotations:
        if first <= a.page <= last:
            apply_to_page(out[a.page - first], [a])
    if bake:
        out.bake()
    return out


def save_annotated_pdf(doc: fitz.Document, annotations: Sequence[Annotation], out_path: Path | str) -> None:
    """Salva um novo PDF com as anotações (editáveis em outros leitores)."""
    out = annotated_copy(doc, annotations)
    try:
        out.save(str(out_path), garbage=3, deflate=True)
    finally:
        out.close()
