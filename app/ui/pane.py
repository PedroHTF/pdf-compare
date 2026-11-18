"""Painel de visualização de um PDF: cabeçalho com controles e a página renderizada."""

from __future__ import annotations

from collections import OrderedDict
from typing import List, Optional, Tuple, Union

import fitz
from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
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
from app.services.search import Hit
from app.ui.widgets import ElidedLabel

ZoomMode = Union[str, float]
FIT_WIDTH = "width"
FIT_PAGE = "page"

HIT_FILL = QColor(255, 213, 0, 100)
CURRENT_FILL = QColor(255, 140, 0, 110)
CURRENT_PEN = QColor(214, 92, 0)
MAX_RENDER_SIDE = 8000  # pixels; evita imagens gigantes em zoom muito alto


def tool_button(text: str, tip: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tip)
    button.setAccessibleName(tip)
    button.setAutoRaise(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


RenderArgs = Tuple[Optional[int], int, Tuple[Hit, ...], Optional[Hit], ZoomMode]


class PdfPane(QFrame):
    page_step = Signal(int, int)      # (painel, delta)
    page_jump = Signal(int, int)      # (painel, página do arquivo)
    hit_step = Signal(int, int)       # (painel, delta)
    close_requested = Signal(int)
    zoom_step = Signal(int)           # +1 / -1 (Ctrl + roda do mouse)
    scrolled = Signal(int, float)     # (painel, proporção vertical 0..1)

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
            tip += "\nProtegido por senha (desbloqueado enquanto estiver aberto)"
        self.name_label.setToolTip(tip)

        self.btn_prev = tool_button("◀", "Página anterior somente neste PDF")
        self.btn_next = tool_button("▶", "Próxima página somente neste PDF")

        self.page_spin = QSpinBox()
        self.page_spin.setRange(0, self.session.page_count)
        self.page_spin.setSpecialValueText("–")
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_spin.setFixedWidth(self.fontMetrics().horizontalAdvance("00000") + 12)
        self.page_spin.setToolTip("Digite uma página e pressione Enter (somente neste PDF)")
        self.page_spin.setAccessibleName("Página atual deste PDF")
        self.page_total = QLabel(f"/ {self.session.page_count}")

        self.hit_box = QWidget()
        self.hit_box.setObjectName("hitBox")
        self.hit_box.setToolTip("Ocorrências da pesquisa neste PDF")
        hits = QHBoxLayout(self.hit_box)
        hits.setContentsMargins(2, 0, 2, 0)
        hits.setSpacing(0)
        self.btn_hit_prev = tool_button("▲", "Ocorrência anterior neste PDF")
        self.hit_label = QLabel()
        self.hit_label.setObjectName("hitLabel")
        self.hit_label.setMinimumWidth(self.fontMetrics().horizontalAdvance("000 de 000") + 10)
        self.hit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_hit_next = tool_button("▼", "Próxima ocorrência neste PDF")
        hits.addWidget(self.btn_hit_prev)
        hits.addWidget(self.hit_label)
        hits.addWidget(self.btn_hit_next)
        self.hit_box.hide()

        self.btn_close = tool_button("✕", "Fechar este PDF")

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

    # --- API pública ----------------------------------------------------------
    def render(
        self,
        page: Optional[int],
        raw_page: int,
        page_hits: List[Hit],
        current_hit: Optional[Hit],
        zoom: ZoomMode,
    ) -> None:
        """Exibe a página `page` (None = posição fora do documento)."""
        args: RenderArgs = (page, raw_page, tuple(page_hits), current_hit, zoom)
        if args == self._args:
            return
        self._args = args
        self._render_now()

    def set_hit_status(self, active: bool, count: int, position: int) -> None:
        self.hit_box.setVisible(active)
        if not active:
            return
        if count == 0:
            text, tip, state = "nenhuma", "Nenhuma ocorrência neste PDF", "none"
        elif position < 0:
            text = f"{count} ocorr."
            tip, state = f"{count} ocorrência(s) neste PDF — use ▼ para ir à próxima", "found"
        else:
            text, tip, state = f"{position + 1} de {count}", f"Ocorrência {position + 1} de {count} neste PDF", "found"
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
        page_no, raw, page_hits, current, zoom = self._args
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
        image = self._page_image(page, page_no, scale * dpr)
        if page_hits:
            image = image.copy()
            self._paint_hits(image, page, page_hits, current, scale * dpr, dpr)

        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        self.image.setText("")
        self.image.setPixmap(pixmap)
        self.image.resize(round(image.width() / dpr), round(image.height() / dpr))

        page_changed = page_no != self._shown_page
        hit_changed = current is not None and current != self._shown_hit
        self._shown_page = page_no
        self._shown_hit = current
        if hit_changed:
            r = fitz.Rect(current.rects[0]) * page.rotation_matrix
            target = ((r.x0 + r.x1) / 2 * scale, (r.y0 + r.y1) / 2 * scale)
            QTimer.singleShot(0, lambda: self._position_view(target))
        elif page_changed:
            QTimer.singleShot(0, lambda: self._position_view(None))

    def _show_blank(self, raw: int, count: int) -> None:
        self._shown_page = None
        self._shown_hit = None
        self.image.setPixmap(QPixmap())
        if raw < 0:
            self.image.setText("Este PDF começa mais adiante.\nUse ▶ neste painel para trazê-lo para cá.")
        else:
            self.image.setText(f"Fim do documento ({count} páginas).\nUse ◀ neste painel para voltar.")
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
