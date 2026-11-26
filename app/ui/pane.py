"""Painel de visualização de um PDF: cabeçalho com controles e a página renderizada."""

from __future__ import annotations

from app.i18n import tr

from collections import OrderedDict
import math
from typing import Dict, List, Optional, Tuple, Union

import fitz
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QRubberBand,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.model.session import DocumentSession
from app.services import annotations as am
from app.services.annotations import HIGHLIGHT, Annotation, Color
from app.services.preferences import DEFAULT_DIFF_COLORS, DEFAULT_STYLE, MarkStyle
from app.services.search import Hit
from app.services.strip_layout import StripLayout
from app.services.strip_layout import _build as rebuild_layout
from app.services.text_diff import ADDED, CHANGED, REMOVED, DiffMark
from app.services.visual_diff import VISUAL
from app.ui.continuous import ContinuousCanvas
from app.ui.widgets import ElidedLabel

ZoomMode = Union[str, float]
FIT_WIDTH = "width"
FIT_PAGE = "page"

HIT_FILL = QColor(255, 213, 0, 100)
CURRENT_FILL = QColor(255, 140, 0, 110)
CURRENT_PEN = QColor(214, 92, 0)
DIFF_STYLE: Dict[str, Tuple[QColor, QColor]] = {}   # tipo -> (preenchimento, sublinhado)


def qcolor(color: Color, alpha: int = 255) -> QColor:
    return QColor(round(color[0] * 255), round(color[1] * 255), round(color[2] * 255), alpha)


def set_diff_colors(colors: Dict[str, Color]) -> None:
    """Cores da comparação de texto (Configurações). Vale para todos os painéis."""
    for kind, color in colors.items():
        DIFF_STYLE[kind] = (qcolor(color, 70), qcolor(color).darker(130))


set_diff_colors(DEFAULT_DIFF_COLORS)
CURRENT_DIFF_PEN = QColor(60, 60, 60)
NOTE_PEN = QColor(150, 80, 0)
SELECTION_PEN = QColor(25, 103, 210)
HANDLE_PX = 7          # tamanho das alças de redimensionar (pixels de tela)

# Ferramentas de anotação (o nome da ferramenta é o tipo da marcação que ela cria)
TOOL_NONE = ""         # selecionar / mover / redimensionar
TOOL_HIGHLIGHT = am.HIGHLIGHT
TOOL_NOTE = am.NOTE
DRAG_TOOLS = (am.RECT, am.ELLIPSE, am.LINE, am.ARROW, am.TEXTBOX, am.CALLOUT, am.INK)
CALLOUT_SIZE = (150.0, 44.0)
TEXTBOX_SIZE = (170.0, 40.0)

MAX_RENDER_SIDE = 8000  # pixels; evita imagens gigantes em zoom muito alto


def tool_button(text: str, tip: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tip)
    button.setAccessibleName(tip)
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


RenderArgs = Tuple[Optional[int], int, Tuple[Hit, ...], Optional[Hit], ZoomMode,
                   Tuple[DiffMark, ...], Optional[DiffMark], Tuple[Tuple, ...]]


class PdfPane(QFrame):
    page_step = Signal(int, int)      # (painel, delta)
    page_jump = Signal(int, int)      # (painel, página do arquivo)
    hit_step = Signal(int, int)       # (painel, delta)
    close_requested = Signal(int)
    zoom_step = Signal(int)           # +1 / -1 (Ctrl + roda do mouse)
    scrolled = Signal(int, float)     # (painel, proporção vertical 0..1)
    highlight_requested = Signal(int, int, tuple)        # (painel, página, retângulo na página)
    markup_requested = Signal(int, int, str, tuple)      # (painel, página, tipo, retângulo)
    shape_drawn = Signal(int, object)                    # (painel, Annotation nova)
    stamp_requested = Signal(int, int, float, float)     # (painel, página, x, y)
    annotation_changed = Signal(int, object)             # (painel, Annotation movida/redimensionada)
    selection_changed = Signal(int, str)                 # (painel, id da marcação ou "")
    edit_requested = Signal(int, str)                    # (painel, id) — duplo clique
    note_requested = Signal(int, int, float, float)      # (painel, página, x, y)
    annotation_menu = Signal(int, int, float, float, QPoint)  # (painel, página, x, y, posição global)
    strip_scrolled = Signal(int, float)      # rolagem contínua: (painel, posição em pixels)
    gap_resized = Signal(int, int, float, float)   # (painel, página, y do espaço, ajuste manual em pontos)
    point_picked = Signal(int, int, float)   # "Alinhar este trecho com…": (painel, página, y)
    region_picked = Signal(int, int, float, int, float)   # "Alinhar seleções": (painel, pág. início, y, pág. fim, y)
    relayout_requested = Signal(int)         # rolagem contínua: o painel mudou de tamanho
    page_flip = Signal(int, int)             # uma página por vez: rolou além da borda (painel, +1 / -1)

    CACHE_SIZE = 4
    MARGIN = 12

    def __init__(self, index: int, session: DocumentSession, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.session = session
        self.setObjectName("pdfPane")
        self.last_scale = 1.0
        self._cache: "OrderedDict[Tuple[int, float], QImage]" = OrderedDict()
        self._args: Optional[RenderArgs] = None
        self._shown_page: Optional[int] = None
        self._shown_hit: Optional[Hit] = None
        self._programmatic = False
        self.tool = TOOL_NONE
        self._annotations: Tuple[Annotation, ...] = ()
        self._drag_start: Optional[QPoint] = None
        self.mark_style: MarkStyle = DEFAULT_STYLE
        self.selected_id = ""
        self._preview: Optional[Annotation] = None
        self._gesture: Optional[dict] = None          # desenho / movimento / redimensionamento
        self._polygon: List[Tuple[float, float]] = []
        self._scale = 1.0
        self._dpr = 1.0
        self.continuous = False
        self.pick_mode = False                 # esperando o clique de "Alinhar este trecho com…"
        self.last_context_gap = None           # espaço sob o último clique com o botão direito
        self.last_context_block = None         # trecho alinhado sob o último clique com o botão direito
        self.region_mode = False               # "Alinhar seleções": arrastar marca um trecho
        self.region_marks: list = []           # trechos destacados: (pág. início, y, pág. fim, y, tipo, referência)
        self.region_drag: Optional[Tuple[float, float]] = None   # trecho sendo arrastado (pixels da faixa)
        self.gap_drag_line: Optional[float] = None
        self._gap_drag: Optional[dict] = None
        self._cdata: dict = {"hits": {}, "diffs": {}, "marks": {}, "hit": None, "diff": None}
        self._cfocus = None
        self._max_size: Optional[Tuple[float, float]] = None
        self.visual_provider = None            # rolagem contínua: página -> áreas da diferença visual
        self.scope_provider = None             # página -> (ignorada, % cabeçalho, % rodapé) fora da comparação
        self.wheel_flip = True                 # uma página por vez: a roda do mouse passa de página nas bordas
        self.land_at_bottom = False            # a próxima página aberta começa pela parte de baixo
        self._edge_wheel = 0                   # rolagem acumulada contra a borda (1/8 de grau)

        self._build_header()
        self._build_view()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.scroll, 1)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._render_now)

    # --- construção -----------------------------------------------------------
    def _build_header(self) -> None:
        self.header = QWidget()
        self.header.setObjectName("paneHeader")
        row = QHBoxLayout(self.header)
        row.setContentsMargins(8, 3, 3, 3)
        row.setSpacing(2)

        self.name_label = ElidedLabel(self.session.name)
        font = self.name_label.font()
        font.setBold(True)
        self.name_label.setFont(font)
        tip = str(self.session.path)
        if self.session.encrypted:
            tip += tr("\nProtegido por senha (desbloqueado enquanto estiver aberto)")
        self.name_label.setToolTip(tip)

        self.btn_prev = tool_button("◀", tr("Página anterior somente neste PDF"))
        self.btn_next = tool_button("▶", tr("Próxima página somente neste PDF"))

        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, self.session.page_count)
        self.page_spin.setSpecialValueText("–")
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_spin.setFixedWidth(self.fontMetrics().horizontalAdvance("00000") + 12)
        self.page_spin.setToolTip(tr("Digite uma página e pressione Enter (somente neste PDF)"))
        self.page_spin.setAccessibleName(tr("Página atual deste PDF"))
        self.page_total = QLabel(f"/ {self.session.page_count}")

        self.hit_box = QWidget()
        self.hit_box.setObjectName("hitBox")
        self.hit_box.setToolTip(tr("Ocorrências da pesquisa neste PDF"))
        hits = QHBoxLayout(self.hit_box)
        hits.setContentsMargins(2, 0, 2, 0)
        hits.setSpacing(0)
        self.btn_hit_prev = tool_button("▲", tr("Ocorrência anterior neste PDF"))
        self.hit_label = QLabel()
        self.hit_label.setObjectName("hitLabel")
        self.hit_label.setMinimumWidth(self.fontMetrics().horizontalAdvance("000 de 000") + 10)
        self.hit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_hit_next = tool_button("▼", tr("Próxima ocorrência neste PDF"))
        hits.addWidget(self.btn_hit_prev)
        hits.addWidget(self.hit_label)
        hits.addWidget(self.btn_hit_next)
        self.hit_box.hide()

        self.btn_close = tool_button("✕", tr("Fechar este PDF"))
        self.role_label = QLabel()
        self.role_label.setObjectName("roleBadge")
        self.role_label.hide()

        row.addWidget(self.name_label, 1)
        row.addWidget(self.role_label)
        row.addSpacing(6)
        row.addWidget(self.btn_prev)
        row.addWidget(self.page_spin)
        row.addWidget(self.page_total)
        row.addWidget(self.btn_next)
        row.addSpacing(8)
        row.addWidget(self.hit_box)
        row.addSpacing(4)
        row.addWidget(self.btn_close)

        self.btn_prev.clicked.connect(lambda: self.page_step.emit(self.index, -1))
        self.btn_next.clicked.connect(lambda: self.page_step.emit(self.index, +1))
        self.btn_hit_prev.clicked.connect(lambda: self.hit_step.emit(self.index, -1))
        self.btn_hit_next.clicked.connect(lambda: self.hit_step.emit(self.index, +1))
        self.btn_close.clicked.connect(lambda: self.close_requested.emit(self.index))
        self.page_spin.valueChanged.connect(self._on_spin)

    def _build_view(self) -> None:
        self.image = QLabel()
        self.image.setObjectName("pageImage")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("pageScroll")
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.image)
        self.scroll.viewport().setObjectName("pageViewport")
        self.scroll.viewport().installEventFilter(self)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.image.installEventFilter(self)
        self.image.setMouseTracking(True)
        self.rubber = QRubberBand(QRubberBand.Shape.Rectangle, self.image)
        self.canvas = ContinuousCanvas(self)
        self.canvas.setParent(self)
        self.canvas.hide()
        self.canvas.installEventFilter(self)
        self.canvas_rubber = QRubberBand(QRubberBand.Shape.Rectangle, self.canvas)

    # --- superfície de desenho (página única ou rolagem contínua) --------------------
    @property
    def surface(self) -> QWidget:
        return self.canvas if self.continuous else self.image

    @property
    def _rubber(self) -> QRubberBand:
        return self.canvas_rubber if self.continuous else self.rubber

    def set_view_mode(self, continuous: bool) -> None:
        if continuous == self.continuous:
            return
        self.cancel_drawing()
        self.continuous = continuous
        old = self.scroll.takeWidget()
        old.setParent(self)
        old.hide()
        widget = self.canvas if continuous else self.image
        self.scroll.setWidget(widget)
        widget.show()
        self._args = None
        self._cfocus = None
        self._shown_page = None
        self._shown_hit = None
        self.set_tool(self.tool)

    # --- API pública ----------------------------------------------------------
    def render(
        self,
        page: Optional[int],
        raw_page: int,
        page_hits: List[Hit],
        current_hit: Optional[Hit],
        zoom: ZoomMode,
        page_diffs: List[DiffMark] = (),
        current_diff: Optional[DiffMark] = None,
        annotations: List[Annotation] = (),
        blank_text: str = "",
        visual: List[DiffMark] = (),
    ) -> None:
        """Exibe a página `page` (None = posição fora do documento ou sem página correspondente)."""
        self._annotations = tuple(annotations)
        self._blank_text = blank_text
        self._visual = tuple(visual)
        self._scope = self._scope_for(page)
        annot_key = tuple(repr(a) for a in annotations) + (self.selected_id, blank_text, self._visual, self._scope)
        args: RenderArgs = (page, raw_page, tuple(page_hits), current_hit, zoom,
                            tuple(page_diffs), current_diff, annot_key)
        if args == self._args:
            return
        self._args = args
        self._render_now()

    def set_role(self, text: str, tip: str = "") -> None:
        """Etiqueta no cabeçalho (ex.: "Referência" da comparação)."""
        self.role_label.setText(text)
        self.role_label.setToolTip(tip)
        self.role_label.setVisible(bool(text))

    def invalidate(self) -> None:
        """Força redesenhar na próxima render() (ex.: cores trocadas nas Configurações)."""
        self._args = None

    def set_hit_status(self, active: bool, count: int, position: int) -> None:
        self.hit_box.setVisible(active)
        if not active:
            return
        if count == 0:
            text, tip, state = tr("nenhuma"), tr("Nenhuma ocorrência neste PDF"), "none"
        elif position < 0:
            text = tr("{n} ocorr.", n=count)
            tip, state = tr("{n} ocorrência(s) neste PDF — use ▼ para ir à próxima", n=count), "found"
        else:
            text = tr("{pos} de {n}", pos=position + 1, n=count)
            tip, state = tr("Ocorrência {pos} de {n} neste PDF", pos=position + 1, n=count), "found"
        self.hit_label.setText(text)
        self.hit_label.setToolTip(tip)
        if self.hit_label.property("state") != state:
            self.hit_label.setProperty("state", state)
            self.hit_label.style().unpolish(self.hit_label)
            self.hit_label.style().polish(self.hit_label)
        self.btn_hit_prev.setEnabled(count > 0)
        self.btn_hit_next.setEnabled(count > 0)

    def set_scroll_ratio(self, ratio: float) -> None:
        bar = self.scroll.verticalScrollBar()
        self._programmatic = True
        try:
            bar.setValue(round(ratio * bar.maximum()))
        finally:
            self._programmatic = False

    # --- rolagem contínua ---------------------------------------------------------
    def max_page_size(self) -> Tuple[float, float]:
        if self._max_size is None:
            doc = self.session.doc
            w = h = 1.0
            for p in range(doc.page_count if doc is not None else 0):
                r = doc[p].rect
                w, h = max(w, r.width), max(h, r.height)
            self._max_size = (w, h)
        return self._max_size

    def page_heights(self) -> List[float]:
        doc = self.session.doc
        return [doc[p].rect.height for p in range(doc.page_count)] if doc is not None else []

    def continuous_scale(self, zoom: ZoomMode) -> float:
        width, height = self.max_page_size()
        return self._scale_for(fitz.Rect(0, 0, width, height), zoom)

    def render_continuous(self, layout: StripLayout, hits: List[Hit], current_hit: Optional[Hit],
                          diffs: List[DiffMark], current_diff: Optional[DiffMark],
                          annotations: List[Annotation]) -> bool:
        """Mostra o PDF inteiro em rolagem contínua. Devolve True se rolou até uma ocorrência/diferença."""
        by_page = lambda items: {p: [i for i in items if i.page == p] for p in {i.page for i in items}}  # noqa: E731
        self._cdata = {"hits": by_page(hits), "diffs": by_page(diffs), "marks": by_page(annotations),
                       "hit": current_hit, "diff": current_diff}
        self._annotations = tuple(annotations)
        self._scale = layout.scale
        self._dpr = self.devicePixelRatioF() or 1.0
        self.last_scale = layout.scale
        self.canvas.layout_strip = layout
        self.canvas.page_width = self.max_page_size()[0] * layout.scale
        self.canvas.resize_to_layout(self.scroll.viewport().width())
        self.canvas.update()
        self._update_header_continuous()
        focus = current_hit if current_hit is not None else current_diff
        if focus is not None and focus != self._cfocus:
            self._cfocus = focus
            r = fitz.Rect(focus.rects[0])
            y = layout.to_strip(focus.page, (r.y0 + r.y1) / 2)
            self.scroll_to_strip(y - self.scroll.viewport().height() * 0.35)
            return True
        self._cfocus = focus
        return False

    def strip_value(self) -> float:
        return float(self.scroll.verticalScrollBar().value())

    def scroll_to_strip(self, value: float) -> None:
        bar = self.scroll.verticalScrollBar()
        if self.canvas.height() > bar.maximum() + self.scroll.viewport().height():
            bar.setMaximum(max(self.canvas.height() - self.scroll.viewport().height(), 0))
        self._programmatic = True
        try:
            bar.setValue(round(max(value, 0)))
        finally:
            self._programmatic = False
        self._update_header_continuous()

    def top_page(self) -> Optional[int]:
        layout = self.canvas.layout_strip
        if layout is None or not layout.page_top:
            return None
        return layout.page_at(self.strip_value() + 4)

    def _update_header_continuous(self) -> None:
        page = self.top_page()
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page + 1 if page is not None else 0)
        self.page_spin.blockSignals(False)
        count = self.session.page_count
        self.btn_prev.setEnabled(page is not None and page > 0)
        self.btn_next.setEnabled(page is not None and page < count - 1)

    def continuous_overlay_key(self, page_no: int) -> tuple:
        d = self._cdata
        marks = list(d["marks"].get(page_no, []))
        preview = self._preview if self._preview is not None and self._preview.page == page_no else None
        hit = d["hit"] if d["hit"] is not None and d["hit"].page == page_no else None
        diff = d["diff"] if d["diff"] is not None and d["diff"].page == page_no else None
        visual = tuple(self.visual_provider(page_no)) if self.visual_provider is not None else ()
        return (tuple(d["hits"].get(page_no, [])), hit, tuple(d["diffs"].get(page_no, [])), diff,
                tuple(repr(a) for a in marks), repr(preview), self.selected_id, visual, self._scope_for(page_no))

    def _scope_for(self, page_no: Optional[int]):
        if self.scope_provider is None or page_no is None:
            return None
        return self.scope_provider(page_no)

    def page_image_with_overlays(self, page: fitz.Page, page_no: int, scale: float, dpr: float) -> QImage:
        d = self._cdata
        image = self._page_image(page, page_no, scale * dpr)
        marks = list(d["marks"].get(page_no, []))
        if self._preview is not None and self._preview.page == page_no:
            marks = [a for a in marks if a.id != self._preview.id] + [self._preview]
        hits, diffs = d["hits"].get(page_no, []), d["diffs"].get(page_no, [])
        visual = self.visual_provider(page_no) if self.visual_provider is not None else []
        scope = self._scope_for(page_no)
        if not (marks or hits or diffs or visual or scope):
            return image
        image = image.copy()
        if scope:
            self._paint_scope(image, page, scope, scale * dpr, dpr)
        if visual:
            self._paint_visual(image, page, visual, scale * dpr, dpr)
        if marks:
            self._paint_annotations(image, page, marks, scale * dpr, dpr, self.selected_id)
        if diffs:
            self._paint_diffs(image, page, diffs, d["diff"], scale * dpr, dpr)
        if hits:
            self._paint_hits(image, page, hits, d["hit"], scale * dpr, dpr)
        return image

    def _continuous_point(self, page_no: int, pos: QPoint) -> Optional[Tuple[float, float]]:
        layout = self.canvas.layout_strip
        if layout is None:
            return None
        pieces = [p for p in layout.pieces if p.page == page_no]
        if not pieces:
            return None
        y_px = pos.y()
        if y_px <= pieces[0].top:
            y = pieces[0].y0 + (y_px - pieces[0].top) / layout.scale
        elif y_px >= pieces[-1].bottom:
            y = pieces[-1].y1 + (y_px - pieces[-1].bottom) / layout.scale
        else:
            y = pieces[-1].y1
            for piece in pieces:
                if piece.top <= y_px <= piece.bottom:
                    y = piece.y0 + (y_px - piece.top) / layout.scale
                    break
                if y_px < piece.top:   # dentro de um espaço: borda de cima do pedaço seguinte
                    y = piece.y0
                    break
        x = (pos.x() - self.canvas.page_left(page_no)) / layout.scale
        point = fitz.Point(x, y) * self.session.doc[page_no].derotation_matrix
        return point.x, point.y

    def _page_under(self, pos: QPoint) -> Optional[int]:
        layout = self.canvas.layout_strip
        return layout.from_strip(pos.y())[0] if layout is not None and layout.page_top else None

    def _canvas_event(self, event: QEvent) -> bool:
        """Eventos próprios da rolagem contínua; o resto segue para _image_event."""
        etype = event.type()
        if etype not in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease,
                         QEvent.Type.MouseButtonDblClick):
            return False
        pos = event.position().toPoint()
        layout = self.canvas.layout_strip
        if self._gap_drag is not None:
            if etype == QEvent.Type.MouseMove:
                g = self._gap_drag
                g["gap"].manual = g["manual"] + (pos.y() - g["start"])
                rebuild_layout(layout, [p.gap for p in g["gaps"]])
                self.canvas.resize_to_layout(self.scroll.viewport().width())
                self.canvas.update()
                return True
            if etype == QEvent.Type.MouseButtonRelease:
                g, self._gap_drag = self._gap_drag, None
                gap = g["gap"]
                self.gap_resized.emit(self.index, gap.page, gap.y, gap.manual / max(layout.scale, 1e-6))
                return True
        if self.region_mode and self.region_drag is not None:
            if etype == QEvent.Type.MouseMove:
                self.region_drag = (self.region_drag[0], float(pos.y()))
                self.canvas.update()
                return True
            if etype == QEvent.Type.MouseButtonRelease:
                start, _ = self.region_drag
                self.region_drag = None
                self.canvas.update()
                self._emit_region(start, float(pos.y()), pos.x())
                return True
        if etype == QEvent.Type.MouseMove and (self.region_mode or self.pick_mode):
            return True            # o cursor (cruz / proibido) foi escolhido pela janela
        if etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if self.region_mode and not self.pick_mode:
                self.region_drag = (float(pos.y()), float(pos.y()))
                self.canvas.update()
                return True
            if self.pick_mode:
                page = self._page_under(pos)
                point = self._continuous_point(page, pos) if page is not None else None
                if point is not None:
                    self.point_picked.emit(self.index, page, point[1])
                return True
            handle = self.canvas.gap_handle_at(pos.y()) if self.tool == TOOL_NONE else None
            if handle is not None and handle.gap.locked:
                return True        # travado: não se arrasta
            if handle is not None:
                gaps = layout.gaps()
                self._gap_drag = {"gap": handle.gap, "manual": handle.gap.manual, "start": pos.y(), "gaps": gaps}
                return True
        if etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
            gap = self.canvas.gap_at(pos.y())
            self.last_context_gap = gap.gap if gap is not None else None
            self.last_context_block = self.canvas.block_at(pos.y())
        busy = self._gesture is not None or self._polygon or self._drag_start is not None
        if not busy and etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseMove):
            page = self._page_under(pos)
            if page is not None:
                self._shown_page = page
            if etype == QEvent.Type.MouseMove and self.tool == TOOL_NONE and not self.region_mode:
                handle = self.canvas.gap_handle_at(pos.y())
                if handle is not None:
                    self.canvas.setCursor(Qt.CursorShape.ForbiddenCursor if handle.gap.locked
                                          else Qt.CursorShape.SizeVerCursor)
                    return True
        return False

    def _emit_region(self, start: float, end: float, x: int) -> None:
        """Fim do arrasto de "Alinhar seleções": o trecho entre as duas alturas."""
        layout = self.canvas.layout_strip
        if layout is None or not layout.page_top:
            return
        top, bottom = min(start, end), max(start, end)
        if bottom - top < 3:   # só um clique: a linha sob o cursor
            bottom = top + 1
        points = []
        for value in (top, bottom):
            page = layout.from_strip(value)[0]
            point = self._continuous_point(page, QPoint(x, int(round(value))))
            if point is None:
                return
            points.append((page, point[1]))
        (p0, y0), (p1, y1) = points
        self.region_picked.emit(self.index, p0, y0, p1, y1)

    def cancel_region(self) -> bool:
        if self.region_drag is None:
            return False
        self.region_drag = None
        self.canvas.update()
        return True

    # --- renderização ---------------------------------------------------------
    def _render_now(self) -> None:
        if self.continuous:
            if self._resize_timer.isActive() or self.sender() is self._resize_timer:
                self.relayout_requested.emit(self.index)
            self.canvas.update()
            return
        if self._args is None or self.session.doc is None:
            return
        page_no, raw, page_hits, current, zoom, page_diffs, current_diff, _ = self._args
        count = self.session.page_count

        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page_no + 1 if page_no is not None else 0)
        self.page_spin.blockSignals(False)
        self.btn_prev.setEnabled(raw > 0)
        self.btn_next.setEnabled(raw < count - 1)

        if page_no is None:
            self._show_blank(raw, count)
            return

        page = self.session.doc[page_no]
        scale = self._scale_for(page.rect, zoom)
        self.last_scale = scale
        dpr = self.devicePixelRatioF() or 1.0
        self._scale, self._dpr = scale, dpr
        image = self._page_image(page, page_no, scale * dpr)
        marks = list(self._annotations)
        if self._preview is not None:
            marks = [a for a in marks if a.id != self._preview.id] + [self._preview]
        visual = getattr(self, "_visual", ())
        scope = getattr(self, "_scope", None)
        if page_hits or page_diffs or marks or visual or scope:
            image = image.copy()
            if scope:
                self._paint_scope(image, page, scope, scale * dpr, dpr)
            if visual:
                self._paint_visual(image, page, visual, scale * dpr, dpr)
            if marks:
                self._paint_annotations(image, page, marks, scale * dpr, dpr, self.selected_id)
            if page_diffs:
                self._paint_diffs(image, page, page_diffs, current_diff, scale * dpr, dpr)
            if page_hits:
                self._paint_hits(image, page, page_hits, current, scale * dpr, dpr)

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        self.image.setText("")
        self.image.setPixmap(pixmap)
        self.image.resize(round(image.width() / dpr), round(image.height() / dpr))

        page_changed = page_no != self._shown_page
        focus = current if current is not None else current_diff
        hit_changed = focus is not None and focus != self._shown_hit
        self._shown_page = page_no
        self._shown_hit = focus
        if hit_changed:
            r = fitz.Rect(focus.rects[0]) * page.rotation_matrix
            target = ((r.x0 + r.x1) / 2 * scale, (r.y0 + r.y1) / 2 * scale)
            QTimer.singleShot(0, lambda: self._position_view(target))
        elif page_changed:
            bottom, self.land_at_bottom = self.land_at_bottom, False
            QTimer.singleShot(0, lambda: self._position_view(None, bottom))

    def _show_blank(self, raw: int, count: int) -> None:
        self._shown_page = None
        self._shown_hit = None
        self.image.setPixmap(QPixmap())
        if getattr(self, "_blank_text", ""):
            self.image.setText(self._blank_text)
        elif raw < 0:
            self.image.setText(tr("Este PDF começa mais adiante.\nUse ▶ neste painel para trazê-lo para cá."))
        else:
            self.image.setText(tr("Fim do documento ({n} páginas).\nUse ◀ neste painel para voltar.", n=count))
        self.image.resize(self.scroll.viewport().size())

    def _scale_for(self, rect: fitz.Rect, zoom: ZoomMode) -> float:
        if not isinstance(zoom, str):
            scale = float(zoom)
        else:
            frame = self.scroll.frameWidth() * 2
            bar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
            avail_w = max(self.scroll.width() - frame - bar - self.MARGIN, 50)
            scale = avail_w / rect.width
            if zoom == FIT_PAGE:
                avail_h = max(self.scroll.height() - frame - self.MARGIN, 50)
                scale = min(scale, avail_h / rect.height)
        longest = max(rect.width, rect.height)
        return max(min(scale, MAX_RENDER_SIDE / longest), 0.05)

    def _page_image(self, page: fitz.Page, page_no: int, scale: float) -> QImage:
        key = (page_no, round(scale, 3))
        image = self._cache.get(key)
        if image is not None:
            self._cache.move_to_end(key)
            return image
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        self._cache[key] = image
        while len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return image

    @staticmethod
    def _paint_hits(image: QImage, page: fitz.Page, hits, current: Optional[Hit], scale: float, dpr: float) -> None:
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        matrix = page.rotation_matrix
        for hit in hits:
            is_current = hit == current
            painter.setBrush(CURRENT_FILL if is_current else HIT_FILL)
            painter.setPen(QPen(CURRENT_PEN, 2 * dpr) if is_current else Qt.PenStyle.NoPen)
            for rect in hit.rects:
                r = (fitz.Rect(rect) * matrix).normalize()
                painter.drawRect(QRectF(r.x0 * scale, r.y0 * scale, r.width * scale, r.height * scale).adjusted(-2, -2, 2, 2))
        painter.end()

    @staticmethod
    def _qrect(rect, matrix, scale: float) -> QRectF:
        r = (fitz.Rect(rect) * matrix).normalize()
        return QRectF(r.x0 * scale, r.y0 * scale, r.width * scale, r.height * scale)

    @classmethod
    def _paint_visual(cls, image: QImage, page: fitz.Page, marks, scale: float, dpr: float) -> None:
        """Áreas da diferença visual: contorno tracejado com um leve preenchimento."""
        fill, line = DIFF_STYLE.get(VISUAL, DIFF_STYLE[CHANGED])
        painter = QPainter(image)
        painter.setPen(QPen(line, 1.6 * dpr, Qt.PenStyle.DashLine))
        light = QColor(fill)
        light.setAlpha(35)
        painter.setBrush(light)
        matrix = page.rotation_matrix
        for mark in marks:
            for rect in mark.rects:
                painter.drawRect(cls._qrect(rect, matrix, scale).adjusted(-2, -2, 2, 2))
        painter.end()

    def _paint_scope(self, image: QImage, page: fitz.Page, scope, scale: float, dpr: float) -> None:
        """Partes fora da comparação: cabeçalho e rodapé ignorados (faixa cinza) ou a página inteira."""
        ignored, header, footer = scope
        width, height = image.width(), image.height()
        painter = QPainter(image)
        shade = QColor(90, 98, 120, 34)
        pen = QPen(QColor(90, 98, 120, 150), 1 * dpr, Qt.PenStyle.DashLine)
        if ignored:
            painter.fillRect(QRectF(0, 0, width, height), QColor(90, 98, 120, 60))
            font = QFont(self.font())
            font.setPointSizeF(font.pointSizeF() * 1.3 * dpr)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(60, 66, 85))
            painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter,
                             tr("Página ignorada na comparação"))
            painter.end()
            return
        painter.setPen(pen)
        if header:
            y = height * header / 100
            painter.fillRect(QRectF(0, 0, width, y), shade)
            painter.drawLine(QPointF(0, y), QPointF(width, y))
        if footer:
            y = height * (1 - footer / 100)
            painter.fillRect(QRectF(0, y, width, height - y), shade)
            painter.drawLine(QPointF(0, y), QPointF(width, y))
        painter.end()

    @classmethod
    def _paint_diffs(cls, image: QImage, page: fitz.Page, marks, current: Optional[DiffMark],
                     scale: float, dpr: float) -> None:
        painter = QPainter(image)
        matrix = page.rotation_matrix
        for mark in marks:
            fill, line = DIFF_STYLE.get(mark.kind, DIFF_STYLE[CHANGED])
            for rect in mark.rects:
                q = cls._qrect(rect, matrix, scale).adjusted(-1, -1, 1, 1)
                painter.fillRect(q, fill)
                painter.setPen(QPen(line, 1.5 * dpr))
                painter.drawLine(q.bottomLeft(), q.bottomRight())
                if mark.kind == REMOVED:   # tachado
                    painter.drawLine(QPointF(q.left(), q.center().y()), QPointF(q.right(), q.center().y()))
            if mark == current:
                painter.setPen(QPen(CURRENT_DIFF_PEN, 2 * dpr, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for rect in mark.rects:
                    painter.drawRect(cls._qrect(rect, matrix, scale).adjusted(-3, -3, 3, 3))
        painter.end()

    @classmethod
    def _paint_annotations(cls, image: QImage, page: fitz.Page, annotations, scale: float, dpr: float,
                           selected_id: str = "") -> None:
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        matrix = page.rotation_matrix
        for a in annotations:
            painter.save()
            painter.setOpacity(a.opacity)
            try:
                cls._paint_one(painter, a, matrix, scale, dpr)
            finally:
                painter.restore()
        for a in annotations:
            if a.id == selected_id:
                cls._paint_selection(painter, a, matrix, scale, dpr)
        painter.end()

    @staticmethod
    def _qpoint(point, matrix, scale: float) -> QPointF:
        p = fitz.Point(point) * matrix
        return QPointF(p.x * scale, p.y * scale)

    @classmethod
    def _paint_one(cls, painter: QPainter, a: Annotation, matrix, scale: float, dpr: float) -> None:
        color = qcolor(a.stroke_color)
        pen = QPen(color, max(a.width, 0.5) * scale, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        no_pen = a.width <= 0
        brush = qcolor(a.fill) if a.fill is not None else Qt.BrushStyle.NoBrush
        kind = a.kind
        if kind == am.HIGHLIGHT:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            for rect in a.rects:
                painter.fillRect(cls._qrect(rect, matrix, scale), qcolor(a.stroke_color, 150))
        elif kind in (am.UNDERLINE, am.STRIKEOUT, am.SQUIGGLY):
            painter.setPen(QPen(color, max(1.2 * dpr, scale * 1.0)))
            for rect in a.rects:
                q = cls._qrect(rect, matrix, scale)
                if kind == am.UNDERLINE:
                    painter.drawLine(q.bottomLeft(), q.bottomRight())
                elif kind == am.STRIKEOUT:
                    painter.drawLine(QPointF(q.left(), q.center().y()), QPointF(q.right(), q.center().y()))
                else:
                    step = max(q.height() / 5, 2.0)
                    path = QPainterPath(QPointF(q.left(), q.bottom()))
                    x, up = q.left(), True
                    while x < q.right():
                        x = min(x + step, q.right())
                        path.lineTo(QPointF(x, q.bottom() - (step if up else 0)))
                        up = not up
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)
        elif kind == am.NOTE:
            q = cls._qrect(a.rects[0], matrix, scale)
            painter.setBrush(color)
            painter.setPen(QPen(NOTE_PEN, 1.5 * dpr))
            painter.drawRoundedRect(q, 3 * dpr, 3 * dpr)
            painter.setPen(QPen(NOTE_PEN, 1.2 * dpr))
            for k in (0.33, 0.5, 0.67):   # "linhas" do bilhete
                y = q.top() + q.height() * k
                painter.drawLine(QPointF(q.left() + q.width() * 0.22, y), QPointF(q.right() - q.width() * 0.22, y))
        elif kind in (am.RECT, am.ELLIPSE):
            q = cls._qrect(a.rects[0], matrix, scale)
            painter.setPen(Qt.PenStyle.NoPen if no_pen else pen)
            painter.setBrush(brush)
            painter.drawRect(q) if kind == am.RECT else painter.drawEllipse(q)
        elif kind in (am.LINE, am.ARROW):
            p0, p1 = (cls._qpoint(p, matrix, scale) for p in a.points[:2])
            painter.setPen(pen)
            painter.drawLine(p0, p1)
            if kind == am.ARROW:
                cls._arrow_head(painter, p0, p1, max(a.width, 1.0) * scale, color)
        elif kind == am.POLYGON:
            painter.setPen(Qt.PenStyle.NoPen if no_pen else pen)
            painter.setBrush(brush)
            points = [cls._qpoint(p, matrix, scale) for p in a.points]
            painter.drawPolygon(QPolygonF(points)) if len(points) > 2 else painter.drawPolyline(QPolygonF(points))
        elif kind == am.INK:
            painter.setPen(pen)
            for stroke in a.strokes:
                painter.drawPolyline(QPolygonF([cls._qpoint(p, matrix, scale) for p in stroke]))
        elif kind in (am.TEXTBOX, am.CALLOUT):
            q = cls._qrect(a.rects[0], matrix, scale)
            border = QPen(color, max(a.width, 1.0 if kind == am.CALLOUT else 0.0) * scale)
            if kind == am.CALLOUT and a.points:
                tip = cls._qpoint(a.points[0], matrix, scale)
                edge = QPointF(min(max(tip.x(), q.left()), q.right()), min(max(tip.y(), q.top()), q.bottom()))
                if q.contains(tip):
                    edge = QPointF(q.left(), q.center().y())
                painter.setPen(border)
                painter.drawLine(edge, tip)
                cls._arrow_head(painter, edge, tip, max(a.width, 1.0) * scale, color, open_head=True)
            painter.setBrush(brush)
            painter.setPen(border if (a.width > 0 or kind == am.CALLOUT) else Qt.PenStyle.NoPen)
            painter.drawRect(q)
            cls._draw_text(painter, q, a.text, a.font_size * scale, color, Qt.AlignmentFlag.AlignLeft)
        elif kind == am.STAMP:
            q = cls._qrect(a.rects[0], matrix, scale)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, max(a.width, 2.0) * scale))
            painter.drawRoundedRect(q, 4 * scale, 4 * scale)
            size = min(a.font_size, (a.rects[0][3] - a.rects[0][1]) * 0.6) * scale
            cls._draw_text(painter, q, a.text.upper(), size, color, Qt.AlignmentFlag.AlignCenter, bold=True)

    @staticmethod
    def _draw_text(painter: QPainter, q: QRectF, text: str, pixel_size: float, color: QColor,
                   align: Qt.AlignmentFlag, bold: bool = False) -> None:
        if not text or pixel_size < 1:
            return
        font = QFont("Helvetica")
        font.setPixelSize(max(1, round(pixel_size)))
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(color)
        pad = pixel_size * 0.25
        flags = int(align | Qt.AlignmentFlag.AlignVCenter if bold else align | Qt.AlignmentFlag.AlignTop)
        painter.drawText(q.adjusted(pad, pad * 0.5, -pad, -pad * 0.5), flags | int(Qt.TextFlag.TextWordWrap), text)

    @staticmethod
    def _arrow_head(painter: QPainter, p0: QPointF, p1: QPointF, width: float, color: QColor,
                    open_head: bool = False) -> None:
        angle = math.atan2(p1.y() - p0.y(), p1.x() - p0.x())
        size = max(width * 4, 8)
        left = QPointF(p1.x() - size * math.cos(angle - 0.45), p1.y() - size * math.sin(angle - 0.45))
        right = QPointF(p1.x() - size * math.cos(angle + 0.45), p1.y() - size * math.sin(angle + 0.45))
        if open_head:
            painter.drawPolyline(QPolygonF([left, p1, right]))
        else:
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([left, p1, right]))

    @classmethod
    def _paint_selection(cls, painter: QPainter, a: Annotation, matrix, scale: float, dpr: float) -> None:
        q = cls._qrect(am.selection_box(a), matrix, scale).adjusted(-3 * dpr, -3 * dpr, 3 * dpr, 3 * dpr)
        painter.setOpacity(1.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(SELECTION_PEN, 1.2 * dpr, Qt.PenStyle.DashLine))
        painter.drawRect(q)
        if a.kind in am.RESIZABLE:
            h = HANDLE_PX * dpr
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(QPen(SELECTION_PEN, 1.2 * dpr))
            for c in (q.topLeft(), q.topRight(), q.bottomLeft(), q.bottomRight()):
                painter.drawRect(QRectF(c.x() - h / 2, c.y() - h / 2, h, h))

    def annotation_tooltip(self, x: float, y: float) -> str:
        from app.services.annotations import find_at

        page = self._shown_page
        found = find_at(self._annotations, page, x, y) if page is not None else None
        return found.text if found is not None else ""

    # --- coordenadas ------------------------------------------------------------
    def to_page_point(self, pos: QPoint) -> Optional[Tuple[float, float]]:
        """Converte um ponto da imagem (pixels) para coordenadas da página sem rotação."""
        if self._shown_page is None or self.session.doc is None:
            return None
        if self.continuous:
            return self._continuous_point(self._shown_page, pos)
        pix = self.image.pixmap()
        if pix is None or pix.isNull():
            return None
        # a imagem pode estar centralizada dentro do QLabel
        w = pix.width() / self._dpr
        h = pix.height() / self._dpr
        ox = (self.image.width() - w) / 2
        oy = (self.image.height() - h) / 2
        px = (pos.x() - ox) / self._scale
        py = (pos.y() - oy) / self._scale
        page = self.session.doc[self._shown_page]
        point = fitz.Point(px, py) * page.derotation_matrix
        return point.x, point.y

    # --- interação: marcar, desenhar, selecionar ------------------------------------
    def _new_mark(self, kind: str, rects, **geometry) -> Annotation:
        st = self.mark_style
        color = st.highlight if kind == am.HIGHLIGHT else st.color
        if kind == am.NOTE:
            color = am.NOTE_COLOR
        fill = st.fill if kind in am.FILLABLE else None
        if kind in (am.TEXTBOX, am.CALLOUT) and fill is None:
            fill = (1.0, 1.0, 1.0)
        return Annotation(kind, self._shown_page, list(rects), color=color, fill=fill, width=st.width,
                          opacity=st.opacity, font_size=st.font_size, **geometry)

    def _handle_at(self, x: float, y: float) -> Optional[Tuple[float, float]]:
        """Canto oposto (fixo) se (x, y) estiver sobre uma alça da marcação selecionada."""
        sel = self.selected_annotation()
        if sel is None or sel.kind not in am.RESIZABLE:
            return None
        box = am.selection_box(sel)
        reach = (HANDLE_PX + 3) / max(self._scale, 1e-6)
        pad = 3 / max(self._scale, 1e-6)
        corners = {(box[0] - pad, box[1] - pad): (box[2], box[3]), (box[2] + pad, box[1] - pad): (box[0], box[3]),
                   (box[0] - pad, box[3] + pad): (box[2], box[1]), (box[2] + pad, box[3] + pad): (box[0], box[1])}
        for (cx, cy), fixed in corners.items():
            if abs(x - cx) <= reach and abs(y - cy) <= reach:
                return fixed
        return None

    def selected_annotation(self) -> Optional[Annotation]:
        return next((a for a in self._annotations if a.id == self.selected_id), None) if self.selected_id else None

    def set_selected(self, annotation_id: str) -> None:
        if annotation_id != self.selected_id:
            self.selected_id = annotation_id
            self._args = None if self._args is None else self._args[:-1] + ((),)
            self._render_now()

    def _select(self, annotation_id: str) -> None:
        self.set_selected(annotation_id)
        self.selection_changed.emit(self.index, annotation_id)

    def _show_preview(self, annotation: Optional[Annotation]) -> None:
        self._preview = annotation
        self._render_now()

    def _image_event(self, event: QEvent) -> bool:
        etype = event.type()
        if etype == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            if self.tool == am.POLYGON:
                self.finish_polygon()
                return True
            point = self.to_page_point(event.position().toPoint())
            if self.tool == TOOL_NONE and point is not None:
                from app.services.annotations import find_at

                found = find_at(self._annotations, self._shown_page, *point)
                if found is not None:
                    self.edit_requested.emit(self.index, found.id)
                    return True
            return False
        if etype == QEvent.Type.MouseButtonPress:
            pos = event.position().toPoint()
            point = self.to_page_point(pos)
            if event.button() == Qt.MouseButton.RightButton:
                if point is not None:
                    self.annotation_menu.emit(self.index, self._shown_page, point[0], point[1],
                                              event.globalPosition().toPoint())
                return True
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            tool = self.tool
            if tool == TOOL_NOTE:
                if point is not None:
                    self.note_requested.emit(self.index, self._shown_page, point[0], point[1])
                return True
            if tool == am.STAMP:
                if point is not None:
                    self.stamp_requested.emit(self.index, self._shown_page, point[0], point[1])
                return True
            if tool in am.TEXT_MARKUPS:
                self._drag_start = pos
                self._rubber.setGeometry(QRect(pos, QSize()))
                self._rubber.show()
                return True
            if point is None:
                return tool != TOOL_NONE
            if tool == am.POLYGON:
                self._polygon.append(point)
                self._show_preview(self._polygon_mark(point))
                return True
            if tool in DRAG_TOOLS:
                self._gesture = {"mode": "draw", "start": point, "points": [point]}
                return True
            if tool == TOOL_NONE:
                return self._press_select(point)
            return False
        if etype == QEvent.Type.MouseMove:
            pos = event.position().toPoint()
            if self._drag_start is not None:
                self._rubber.setGeometry(QRect(self._drag_start, pos).normalized())
                return True
            point = self.to_page_point(pos)
            if self._gesture is not None and point is not None:
                self._update_gesture(point)
                return True
            if self.tool == am.POLYGON and self._polygon and point is not None:
                self._show_preview(self._polygon_mark(point))
                return True
            self.surface.setToolTip(self.annotation_tooltip(*point) if point is not None else "")
            if self.tool == TOOL_NONE and point is not None:
                over_handle = self._handle_at(*point) is not None
                self.surface.setCursor(Qt.CursorShape.SizeFDiagCursor if over_handle else Qt.CursorShape.ArrowCursor)
            return False
        if etype == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            if self._drag_start is not None:
                self.finish_highlight(self._drag_start, event.position().toPoint())
                return True
            if self._gesture is not None:
                point = self.to_page_point(event.position().toPoint())
                self._finish_gesture(point)
                return True
        return False

    def _press_select(self, point: Tuple[float, float]) -> bool:
        from app.services.annotations import find_at

        fixed = self._handle_at(*point)
        sel = self.selected_annotation()
        if fixed is not None and sel is not None:
            self._gesture = {"mode": "resize", "fixed": fixed, "original": sel}
            return True
        found = find_at(self._annotations, self._shown_page, *point)
        if found is None:
            if self.selected_id:
                self._select("")
            return False
        self._select(found.id)
        self._gesture = {"mode": "move", "start": point, "original": found}
        return True

    def _update_gesture(self, point: Tuple[float, float]) -> None:
        g = self._gesture
        if g["mode"] == "move":
            dx, dy = point[0] - g["start"][0], point[1] - g["start"][1]
            self._show_preview(am.moved(g["original"], dx, dy))
        elif g["mode"] == "resize":
            fx, fy = g["fixed"]
            self._show_preview(am.resized(g["original"], (fx, fy, point[0], point[1])))
        else:
            g["points"].append(point)
            self._show_preview(self._drawn_mark(g["start"], point, g["points"], final=False))

    def _finish_gesture(self, point: Optional[Tuple[float, float]]) -> None:
        g, self._gesture = self._gesture, None
        result = self._preview
        self._preview = None
        if g["mode"] in ("move", "resize"):
            if result is not None and repr(result) != repr(g["original"]):
                self.annotation_changed.emit(self.index, result)
            else:
                self._render_now()
            return
        end = point or g["points"][-1]
        mark = self._drawn_mark(g["start"], end, g["points"] + [end], final=True)
        self._render_now()
        if mark is not None:
            self.shape_drawn.emit(self.index, mark)

    def _drawn_mark(self, start, end, points, final: bool) -> Optional[Annotation]:
        tool = self.tool
        x0, y0 = start
        x1, y1 = end
        small = abs(x1 - x0) < am.MIN_SIZE and abs(y1 - y0) < am.MIN_SIZE
        if tool in (am.RECT, am.ELLIPSE, am.TEXTBOX):
            if small:
                if not final or tool != am.TEXTBOX:
                    return None
                x1, y1 = x0 + TEXTBOX_SIZE[0], y0 + TEXTBOX_SIZE[1]
            return self._new_mark(tool, [(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))])
        if tool in (am.LINE, am.ARROW):
            return None if small else self._new_mark(tool, [], points=[start, end])
        if tool == am.CALLOUT:
            w, h = CALLOUT_SIZE
            if small:   # clique: balão acima e à direita do ponto
                x1, y1 = x0 + 30, y0 - 30 - h
            return self._new_mark(tool, [(x1, y1, x1 + w, y1 + h)], points=[start])
        if tool == am.INK:
            pts = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
            return None if len(pts) < 2 else self._new_mark(tool, [], strokes=[pts])
        return None

    def _polygon_mark(self, cursor: Tuple[float, float]) -> Optional[Annotation]:
        pts = self._polygon + [cursor]
        if len(pts) < 2:
            return None
        return self._new_mark(am.POLYGON, [], points=pts)

    def finish_polygon(self) -> None:
        pts = [p for i, p in enumerate(self._polygon) if i == 0 or p != self._polygon[i - 1]]
        self._polygon = []
        self._preview = None
        self._render_now()
        if len(pts) >= 3:
            self.shape_drawn.emit(self.index, self._new_mark(am.POLYGON, [], points=pts))

    def cancel_drawing(self) -> bool:
        """Esc: cancela o polígono ou o arraste em andamento."""
        busy = bool(self._polygon) or self._gesture is not None or self._drag_start is not None
        self._polygon = []
        self._gesture = None
        self._drag_start = None
        self._rubber.hide()
        if self._preview is not None:
            self._preview = None
            self._render_now()
        return busy

    def finish_highlight(self, start: QPoint, end: QPoint) -> None:
        self._drag_start = None
        self._rubber.hide()
        a = self.to_page_point(start)
        b = self.to_page_point(end)
        if a is None or b is None or self._shown_page is None:
            return
        rect = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        kind = self.tool if self.tool in am.TEXT_MARKUPS else am.HIGHLIGHT
        if kind == am.HIGHLIGHT:
            self.highlight_requested.emit(self.index, self._shown_page, rect)
        else:
            self.markup_requested.emit(self.index, self._shown_page, kind, rect)

    def set_tool(self, tool: str) -> None:
        self.cancel_drawing()
        self.tool = tool
        cursor = Qt.CursorShape.ArrowCursor
        if tool in am.TEXT_MARKUPS:
            cursor = Qt.CursorShape.IBeamCursor
        elif tool != TOOL_NONE:
            cursor = Qt.CursorShape.CrossCursor
        self.surface.setCursor(cursor)

    def _position_view(self, target: Optional[Tuple[float, float]], bottom: bool = False) -> None:
        self._programmatic = True
        try:
            if target is None:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.maximum() if bottom else 0)
                self.scroll.horizontalScrollBar().setValue(0)
            else:
                margin_y = int(self.scroll.viewport().height() * 0.35)
                self.scroll.ensureVisible(int(target[0]), int(target[1]), 60, margin_y)
        finally:
            self._programmatic = False

    # --- eventos ----------------------------------------------------------------
    def _on_spin(self, value: int) -> None:
        if value >= 1:
            self.page_jump.emit(self.index, value - 1)

    def _on_scroll(self, value: int) -> None:
        if self.continuous:
            self._update_header_continuous()
            if not self._programmatic:
                self.strip_scrolled.emit(self.index, float(value))
            return
        if self._programmatic:
            return
        maximum = self.scroll.verticalScrollBar().maximum()
        self.scrolled.emit(self.index, value / maximum if maximum else 0.0)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if self.continuous and obj is self.canvas and self._canvas_event(event):
            return True
        if obj is self.surface and self._image_event(event):
            return True
        if (
            obj is self.scroll.viewport()
            and event.type() == QEvent.Type.Wheel
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.zoom_step.emit(1 if event.angleDelta().y() > 0 else -1)
            return True
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Wheel and self._wheel_at_edge(event):
            return True
        return super().eventFilter(obj, event)

    EDGE_WHEEL = 120    # um "clique" da roda contra a borda passa de página

    def _wheel_at_edge(self, event) -> bool:
        """Uma página por vez: rolar além do fim (ou do início) da página passa para a seguinte."""
        if self.continuous or not self.wheel_flip or self._shown_page is None:
            self._edge_wheel = 0
            return False
        dy = event.angleDelta().y() or event.pixelDelta().y()
        if dy == 0 or event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            return False
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum()
        at_top = bar.value() <= bar.minimum()
        if (dy < 0 and not at_bottom) or (dy > 0 and not at_top):
            self._edge_wheel = 0
            return False       # ainda há página para rolar
        if (self._edge_wheel < 0) != (dy < 0):
            self._edge_wheel = 0
        self._edge_wheel += dy
        if abs(self._edge_wheel) < self.EDGE_WHEEL:
            return True
        self._edge_wheel = 0
        self.page_flip.emit(self.index, +1 if dy < 0 else -1)
        return True

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.continuous:
            self._resize_timer.start()
            return
        if self._args is not None and (isinstance(self._args[4], str) or self._args[0] is None):
            self._resize_timer.start()
