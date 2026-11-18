"""Widgets auxiliares reutilizáveis."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class ElidedLabel(QWidget):
    """Rótulo de uma linha que abrevia o meio do texto quando falta espaço."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:  # noqa: N802 (padrão Qt)
        self._text = text
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(min(fm.horizontalAdvance(self._text) + 4, 400), fm.height() + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(30, self.fontMetrics().height() + 4)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        elided = self.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideMiddle, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)


class DropZone(QFrame):
    """Área clicável que convida a abrir ou arrastar PDFs (estado vazio)."""

    open_requested = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        button_text: str = "Escolher PDFs…",
        compact: bool = False,
        pixmap: Optional[QPixmap] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        icon = QLabel()
        if pixmap is None or pixmap.isNull():
            pixmap = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon).pixmap(40 if compact else 64)
        icon.setPixmap(pixmap)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        font = title_label.font()
        font.setPointSizeF(font.pointSizeF() + (3 if compact else 7))
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setWordWrap(True)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("muted")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setWordWrap(True)

        self.button = QPushButton(button_text)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setMinimumHeight(34)
        self.button.clicked.connect(self.open_requested.emit)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.button)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(icon)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(6)
        layout.addLayout(row)
        layout.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)
