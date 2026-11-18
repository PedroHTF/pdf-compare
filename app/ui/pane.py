"""Painel de visualização de um PDF: cabeçalho com controles e a página renderizada."""

from __future__ import annotations

from app.i18n import tr

from collections import OrderedDict
from typing import List, Optional, Tuple, Union

import fitz
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
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
from app.services.annotations import HIGHLIGHT, Annotation
from app.services.search import Hit
from app.services.text_diff import ADDED, CHANGED, REMOVED, DiffMark
from app.ui.widgets import ElidedLabel

ZoomMode = Union[str, float]
FIT_WIDTH = "width"
FIT_PAGE = "page"

HIT_FILL = QColor(255, 213, 0, 100)
CURRENT_FILL = QColor(255, 140, 0, 110)
CURRENT_PEN = QColor(214, 92, 0)
DIFF_STYLE = {   # preenchimento, sublinhado
    ADDED: (QColor(52, 168, 83, 70), QColor(30, 130, 60)),
    REMOVED: (QColor(234, 67, 53, 70), QColor(197, 34, 31)),
    CHANGED: (QColor(66, 133, 244, 70), QColor(25, 103, 210)),
}
CURRENT_DIFF_PEN = QColor(60, 60, 60)
ANNOT_FILL = QColor(255, 235, 59, 120)
NOTE_FILL = QColor(255, 167, 38)
NOTE_PEN = QColor(150, 80, 0)

# Ferramentas de anotação
TOOL_NONE = ""
TOOL_HIGHLIGHT = "highlight"
TOOL_NOTE = "note"

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

        row.addWidget(self.name_label, 1)
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
        annot_key = tuple((a.id, a.kind, tuple(a.rects), a.text) for a in annotations)
        args: RenderArgs = (page, raw_page, tuple(page_hits), current_hit, zoom,
                            tuple(page_diffs), current_diff, annot_key)
        if args == self._args:
            return
        self._args = args
        self._render_now()

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
        if page_hits or page_diffs or self._annotations:
            image = image.copy()
            if self._annotations:
                self._paint_annotations(image, page, self._annotations, scale * dpr, dpr)
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
    def _paint_annotations(cls, image: QImage, page: fitz.Page, annotations, scale: float, dpr: float) -> None:
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        matrix = page.rotation_matrix
        for a in annotations:
            if a.kind == HIGHLIGHT:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
                for rect in a.rects:
                    painter.fillRect(cls._qrect(rect, matrix, scale), ANNOT_FILL)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            else:
                q = cls._qrect(a.rects[0], matrix, scale)
                painter.setBrush(NOTE_FILL)
                painter.setPen(QPen(NOTE_PEN, 1.5 * dpr))
                painter.drawRoundedRect(q, 3 * dpr, 3 * dpr)
                painter.setPen(QPen(NOTE_PEN, 1.2 * dpr))
                for k in (0.33, 0.5, 0.67):   # "linhas" do bilhete
                    y = q.top() + q.height() * k
                    painter.drawLine(QPointF(q.left() + q.width() * 0.22, y), QPointF(q.right() - q.width() * 0.22, y))
        painter.end()

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

    def _image_event(self, event: QEvent) -> bool:
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            pos = event.position().toPoint()
            if event.button() == Qt.MouseButton.RightButton:
                point = self.to_page_point(pos)
                if point is not None:
                    self.annotation_menu.emit(self.index, self._shown_page, point[0], point[1],
                                              event.globalPosition().toPoint())
                return True
            if event.button() == Qt.MouseButton.LeftButton and self.tool == TOOL_NOTE:
                point = self.to_page_point(pos)
                if point is not None:
                    self.note_requested.emit(self.index, self._shown_page, point[0], point[1])
                return True
            if event.button() == Qt.MouseButton.LeftButton and self.tool == TOOL_HIGHLIGHT:
                self._drag_start = pos
                self.rubber.setGeometry(QRect(pos, QSize()))
                self.rubber.show()
                return True
        elif etype == QEvent.Type.MouseMove:
            pos = event.position().toPoint()
            if self._drag_start is not None:
                self.rubber.setGeometry(QRect(self._drag_start, pos).normalized())
                return True
            point = self.to_page_point(pos)
            self.image.setToolTip(self.annotation_tooltip(*point) if point is not None else "")
        elif etype == QEvent.Type.MouseButtonRelease and self._drag_start is not None:
            self.finish_highlight(self._drag_start, event.position().toPoint())
            return True
        return False

    def finish_highlight(self, start: QPoint, end: QPoint) -> None:
        self._drag_start = None
        self.rubber.hide()
        a = self.to_page_point(start)
        b = self.to_page_point(end)
        if a is None or b is None or self._shown_page is None:
            return
        rect = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        self.highlight_requested.emit(self.index, self._shown_page, rect)

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        cursor = Qt.CursorShape.ArrowCursor
        if tool == TOOL_HIGHLIGHT:
            cursor = Qt.CursorShape.IBeamCursor
        elif tool == TOOL_NOTE:
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
