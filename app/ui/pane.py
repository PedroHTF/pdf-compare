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
from app.services.text_diff import ADDED, CHANGED, REMOVED, DiffMark
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
    ) -> None:
        """Exibe a página `page` (None = posição fora do documento)."""
        self._annotations = tuple(annotations)
        annot_key = tuple(repr(a) for a in annotations) + (self.selected_id,)
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

    # --- renderização ---------------------------------------------------------
    def _render_now(self) -> None:
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
        if page_hits or page_diffs or marks:
            image = image.copy()
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
            QTimer.singleShot(0, lambda: self._position_view(None))

    def _show_blank(self, raw: int, count: int) -> None:
        self._shown_page = None
        self._shown_hit = None
        self.image.setPixmap(QPixmap())
        if raw < 0:
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
                self.rubber.setGeometry(QRect(pos, QSize()))
                self.rubber.show()
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
                self.rubber.setGeometry(QRect(self._drag_start, pos).normalized())
                return True
            point = self.to_page_point(pos)
            if self._gesture is not None and point is not None:
                self._update_gesture(point)
                return True
            if self.tool == am.POLYGON and self._polygon and point is not None:
                self._show_preview(self._polygon_mark(point))
                return True
            self.image.setToolTip(self.annotation_tooltip(*point) if point is not None else "")
            if self.tool == TOOL_NONE and point is not None:
                over_handle = self._handle_at(*point) is not None
                self.image.setCursor(Qt.CursorShape.SizeFDiagCursor if over_handle else Qt.CursorShape.ArrowCursor)
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
        self.rubber.hide()
        if self._preview is not None:
            self._preview = None
            self._render_now()
        return busy

    def finish_highlight(self, start: QPoint, end: QPoint) -> None:
        self._drag_start = None
        self.rubber.hide()
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
        self.image.setCursor(cursor)

    def _position_view(self, target: Optional[Tuple[float, float]]) -> None:
        self._programmatic = True
        try:
            if target is None:
                self.scroll.verticalScrollBar().setValue(0)
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
        if self._programmatic:
            return
        maximum = self.scroll.verticalScrollBar().maximum()
        self.scrolled.emit(self.index, value / maximum if maximum else 0.0)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self.image and self._image_event(event):
            return True
        if (
            obj is self.scroll.viewport()
            and event.type() == QEvent.Type.Wheel
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.zoom_step.emit(1 if event.angleDelta().y() > 0 else -1)
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._args is not None and (isinstance(self._args[4], str) or self._args[0] is None):
            self._resize_timer.start()
