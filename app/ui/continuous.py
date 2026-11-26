"""Área de desenho da rolagem contínua: páginas empilhadas, cortadas nos espaços de alinhamento.

Só os pedaços visíveis são desenhados. Cada página é renderizada uma vez (com
ocorrências, diferenças e marcações por cima) e guardada em cache; os espaços
são desenhados como faixas vazias com uma alça na parte de baixo, que o
usuário arrasta para aumentar ou diminuir o espaço. Espaços travados mostram um
cadeado (e não têm alça); um espaço removido e travado vira só uma linha.
Trechos alinhados pelo usuário ("Alinhar seleções") ganham uma barra na margem.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Optional, Tuple

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.i18n import tr
from app.services.strip_layout import Piece, StripLayout

if TYPE_CHECKING:   # pragma: no cover
    from app.ui.pane import PdfPane

GAP_FILL = QColor(232, 236, 244)
GAP_LINE = QColor(150, 160, 185)
GAP_MANUAL = QColor(214, 92, 0)
GAP_LOCKED = QColor(40, 88, 168)
REGION_PENDING = QColor(37, 99, 235, 70)    # trecho escolhido, esperando o do outro PDF
REGION_BLOCK = QColor(16, 150, 120)         # trecho alinhado pelo usuário
REGION_BAR = 4
HANDLE_HEIGHT = 8       # pixels da alça (parte de baixo do espaço)
MIN_GAP_FOR_HANDLE = 4  # espaços menores ainda mostram a alça (com esta altura mínima)


class ContinuousCanvas(QWidget):
    def __init__(self, pane: "PdfPane") -> None:
        super().__init__()
        self.pane = pane
        self.layout_strip: Optional[StripLayout] = None
        self.page_width = 0.0       # largura (pixels) da página mais larga
        self._composites: "OrderedDict[tuple, QImage]" = OrderedDict()
        self.setMouseTracking(True)
        self.setObjectName("continuousCanvas")

    CACHE_SIZE = 12

    # --- geometria ------------------------------------------------------------
    def page_left(self, page: int) -> float:
        doc = self.pane.session.doc
        width = doc[page].rect.width * self.layout_strip.scale if doc is not None else 0
        return max((self.width() - width) / 2, 0)

    def resize_to_layout(self, viewport_width: int) -> None:
        if self.layout_strip is None:
            return
        width = max(viewport_width, int(self.page_width) + 2 * self.pane.MARGIN)
        self.resize(width, max(int(self.layout_strip.height) + 1, 1))

    def gap_handle_at(self, y: float) -> Optional[Piece]:
        """Espaço cuja alça (ou corpo) está na altura `y` (pixels do widget)."""
        if self.layout_strip is None:
            return None
        for piece in self.layout_strip.gaps():
            bottom = piece.top + max(piece.height, MIN_GAP_FOR_HANDLE)
            if bottom - HANDLE_HEIGHT - 2 <= y <= bottom + 3:
                return piece
        return None

    def gap_at(self, y: float) -> Optional[Piece]:
        if self.layout_strip is None:
            return None
        for piece in self.layout_strip.gaps():
            if piece.top - 3 <= y <= piece.top + max(piece.height, MIN_GAP_FOR_HANDLE) + 3:
                return piece
        return None

    def region_span(self, mark) -> Tuple[float, float]:
        """Topo e base (pixels) de um trecho destacado: (pág. início, y, pág. fim, y, ...)."""
        layout = self.layout_strip
        top, bottom = layout.to_strip(mark[0], mark[1]), layout.to_strip(mark[2], mark[3])
        return min(top, bottom), max(top, bottom)

    def block_at(self, y: float):
        """Referência do trecho alinhado sob a altura `y`, ou None."""
        if self.layout_strip is None:
            return None
        for mark in self.pane.region_marks:
            if mark[4] != "block":
                continue
            top, bottom = self.region_span(mark)
            if top - 2 <= y <= bottom + 2:
                return mark[5]
        return None

    # --- imagens das páginas --------------------------------------------------------
    def invalidate(self) -> None:
        self._composites.clear()
        self.update()

    def _composite(self, page_no: int) -> Tuple[QImage, float]:
        pane = self.pane
        scale = self.layout_strip.scale
        dpr = pane.devicePixelRatioF() or 1.0
        overlay = pane.continuous_overlay_key(page_no)
        key = (page_no, round(scale, 4), dpr, overlay)
        image = self._composites.get(key)
        if image is None:
            page = pane.session.doc[page_no]
            image = pane.page_image_with_overlays(page, page_no, scale, dpr)
            self._composites[key] = image
            while len(self._composites) > self.CACHE_SIZE:
                self._composites.popitem(last=False)
        else:
            self._composites.move_to_end(key)
        return image, dpr

    # --- desenho ----------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        if self.layout_strip is None or self.pane.session.doc is None:
            return
        painter = QPainter(self)
        area = event.rect()
        scale = self.layout_strip.scale
        for piece in self.layout_strip.pieces:
            if piece.bottom < area.top() - 1 or piece.top > area.bottom() + 1:
                continue
            if piece.page is not None:
                image, dpr = self._composite(piece.page)
                left = self.page_left(piece.page)
                source = QRectF(0, piece.y0 * scale * dpr, image.width(), (piece.y1 - piece.y0) * scale * dpr)
                target = QRectF(left, piece.top, image.width() / dpr, piece.height)
                painter.drawImage(target, image, source)
                painter.setPen(QPen(QColor(0, 0, 0, 40)))
                painter.drawLine(QPointF(left, piece.top), QPointF(left, piece.bottom))
                painter.drawLine(QPointF(left + image.width() / dpr, piece.top),
                                 QPointF(left + image.width() / dpr, piece.bottom))
            else:
                self._paint_gap(painter, piece)
        self._paint_regions(painter, area)
        drag = self.pane.gap_drag_line
        if drag is not None:
            painter.setPen(QPen(GAP_MANUAL, 2, Qt.PenStyle.DashLine))
            painter.drawLine(0, int(drag), self.width(), int(drag))
        painter.end()

    @staticmethod
    def _paint_lock(painter: QPainter, center: QPointF, color: QColor) -> None:
        """Cadeado pequeno (corpo e alça), centrado em `center`."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(center.x() - 3.5, center.y() - 7, 7, 8), 0, 180 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(center.x() - 5, center.y() - 2.5, 10, 7.5), 1.5, 1.5)
        painter.restore()

    def _paint_gap(self, painter: QPainter, piece: Piece) -> None:
        gap = piece.gap
        left = max((self.width() - self.page_width) / 2, 0)
        if gap.locked and piece.height <= 0.5:      # removido e travado: só uma linha com cadeado
            y = piece.top
            painter.setPen(QPen(GAP_LOCKED, 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(left, y), QPointF(left + self.page_width, y))
            badge = QRectF(left + self.page_width - 34, y - 8, 20, 16)
            painter.setPen(QPen(GAP_LOCKED, 1))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawRoundedRect(badge, 4, 4)
            self._paint_lock(painter, badge.center() + QPointF(0, 1), GAP_LOCKED)
            return
        height = max(piece.height, MIN_GAP_FOR_HANDLE)
        rect = QRectF(left, piece.top, self.page_width, height)
        painter.fillRect(rect, GAP_FILL)
        painter.fillRect(rect, QBrush(QColor(200, 206, 222), Qt.BrushStyle.BDiagPattern))
        color = GAP_LOCKED if gap.locked else GAP_MANUAL if gap.adjusted else GAP_LINE
        painter.setPen(QPen(color, 1.5 if gap.locked else 1, Qt.PenStyle.SolidLine if gap.locked
                            else Qt.PenStyle.DashLine))
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if gap.locked:
            self._paint_lock(painter, QPointF(rect.right() - 16, rect.center().y() + 1), GAP_LOCKED)
        else:
            handle = QRectF(rect.center().x() - 22, rect.bottom() - HANDLE_HEIGHT + 2, 44, HANDLE_HEIGHT - 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(handle, 2, 2)
        if piece.height >= 22:
            font = QFont(self.font())
            font.setPointSizeF(max(font.pointSizeF() - 1, 7))
            painter.setFont(font)
            painter.setPen(QColor(90, 98, 120))
            points = piece.height / self.layout_strip.scale
            text = tr("espaço de alinhamento · {pt} pt", pt=round(points))
            if gap.locked:
                text += " " + tr("(travado)")
            elif gap.adjusted:
                text += " " + tr("(ajustado)")
            painter.drawText(rect.adjusted(0, 2, 0, -HANDLE_HEIGHT), Qt.AlignmentFlag.AlignCenter, text)

    def _paint_regions(self, painter: QPainter, area: QRect) -> None:
        """Trechos alinhados (barra na margem) e o trecho escolhido / sendo arrastado (destaque)."""
        pane = self.pane
        left = max((self.width() - self.page_width) / 2, 0)
        bands = []
        for mark in pane.region_marks:
            top, bottom = self.region_span(mark)
            bands.append((top, bottom, mark[4]))
        if pane.region_drag is not None:
            a, b = pane.region_drag
            bands.append((min(a, b), max(a, b), "pending"))
        for top, bottom, kind in bands:
            if bottom < area.top() - 2 or top > area.bottom() + 2:
                continue
            if kind == "pending":
                painter.fillRect(QRectF(left, top, self.page_width, max(bottom - top, 2)), REGION_PENDING)
                continue
            bar = QRectF(max(left - REGION_BAR - 4, 0), top, REGION_BAR, max(bottom - top, 2))
            painter.fillRect(bar, REGION_BLOCK)
            tint = QColor(REGION_BLOCK)
            tint.setAlpha(18)
            painter.fillRect(QRectF(left, top, self.page_width, max(bottom - top, 2)), tint)

    def visible_band(self) -> QRect:
        return self.visibleRegion().boundingRect()
