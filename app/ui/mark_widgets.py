"""Widgets das marcações: botão de cor, barra de estilo e nomes dos tipos."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSpinBox,
    QToolButton,
    QWidget,
)

from app.i18n import tr
from app.services import annotations as am
from app.services.annotations import Color
from app.services.preferences import MarkStyle, rgb255, with_values


def kind_label(kind: str) -> str:
    labels = {
        am.HIGHLIGHT: tr("Destaque"), am.UNDERLINE: tr("Sublinhado"), am.STRIKEOUT: tr("Tachado"),
        am.SQUIGGLY: tr("Ondulado"), am.NOTE: tr("Nota"), am.RECT: tr("Retângulo"), am.ELLIPSE: tr("Elipse"),
        am.LINE: tr("Linha"), am.ARROW: tr("Seta"), am.POLYGON: tr("Polígono"), am.INK: tr("Caneta"),
        am.TEXTBOX: tr("Caixa de texto"), am.CALLOUT: tr("Balão"), am.STAMP: tr("Carimbo"),
    }
    return labels.get(kind, kind)


def stamp_label(stamp: str) -> str:
    return {"Aprovado": tr("Aprovado"), "Revisar": tr("Revisar"), "Divergência": tr("Divergência"),
            "OK": "OK", "Rejeitado": tr("Rejeitado"), "Confidencial": tr("Confidencial")}.get(stamp, stamp)


def swatch(color: Optional[Color], size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setPen(QColor(90, 90, 90))
    if color is None:   # "sem preenchimento": quadrado riscado
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRect(1, 1, size - 3, size - 3)
        painter.setPen(QColor(200, 40, 40))
        painter.drawLine(2, size - 3, size - 3, 2)
    else:
        painter.setBrush(QColor(*rgb255(color)))
        painter.drawRect(1, 1, size - 3, size - 3)
    painter.end()
    return QIcon(pix)


class ColorButton(QToolButton):
    """Mostra uma cor e abre o seletor de cores. Com `allow_none`, oferece "sem cor"."""

    color_changed = Signal(object)   # Color ou None

    def __init__(self, color: Optional[Color], tip: str, allow_none: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = color
        self.allow_none = allow_none
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if allow_none:
            menu = QMenu(self)
            menu.addAction(tr("Escolher cor…"), self.choose)
            menu.addAction(tr("Sem preenchimento"), lambda: self.set_color(None, emit=True))
            self.setMenu(menu)
            self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        else:
            self.clicked.connect(self.choose)
        self._refresh()

    def color(self) -> Optional[Color]:
        return self._color

    def set_color(self, color: Optional[Color], emit: bool = False) -> None:
        if color is None and not self.allow_none:
            return
        self._color = color
        self._refresh()
        if emit:
            self.color_changed.emit(color)

    def choose(self) -> None:
        start = QColor(*rgb255(self._color)) if self._color else QColor(255, 255, 255)
        chosen = QColorDialog.getColor(start, self, self.toolTip())
        if chosen.isValid():
            self.set_color((chosen.redF(), chosen.greenF(), chosen.blueF()), emit=True)

    def _refresh(self) -> None:
        self.setIcon(swatch(self._color))


class MarkStyleBar(QWidget):
    """Cor, preenchimento, espessura, opacidade e fonte das marcações.

    Vale para as próximas marcações e, se houver uma selecionada, também para ela.
    """

    style_changed = Signal(object)   # MarkStyle

    def __init__(self, style: MarkStyle, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._style = style
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(4)

        self.color_btn = ColorButton(style.color, tr("Cor do contorno e do texto"))
        self.highlight_btn = ColorButton(style.highlight, tr("Cor do destaque"))
        self.fill_btn = ColorButton(style.fill, tr("Preenchimento das formas"), allow_none=True)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.0, 20.0)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setDecimals(1)
        self.width_spin.setSuffix(" pt")
        self.width_spin.setToolTip(tr("Espessura do contorno"))
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(5, 100)
        self.opacity_spin.setSingleStep(5)
        self.opacity_spin.setSuffix(" %")
        self.opacity_spin.setToolTip(tr("Opacidade"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(4, 96)
        self.font_spin.setSuffix(" pt")
        self.font_spin.setToolTip(tr("Tamanho da fonte das caixas de texto, balões e carimbos"))
        for w in (self.width_spin, self.opacity_spin, self.font_spin):
            w.setAccessibleName(w.toolTip())
            w.setKeyboardTracking(False)

        for label, widget in ((tr("Cor"), self.color_btn), (tr("Destaque"), self.highlight_btn),
                              (tr("Preench."), self.fill_btn), (tr("Espessura"), self.width_spin),
                              (tr("Opacidade"), self.opacity_spin), (tr("Fonte"), self.font_spin)):
            caption = QLabel(label)
            caption.setObjectName("muted")
            row.addWidget(caption)
            row.addWidget(widget)
            row.addSpacing(4)
        self.set_style(style)

        self.color_btn.color_changed.connect(lambda c: self._emit(color=c))
        self.highlight_btn.color_changed.connect(lambda c: self._emit(highlight=c))
        self.fill_btn.color_changed.connect(lambda c: self._emit(fill=c))
        self.width_spin.valueChanged.connect(lambda v: self._emit(width=float(v)))
        self.opacity_spin.valueChanged.connect(lambda v: self._emit(opacity=v / 100))
        self.font_spin.valueChanged.connect(lambda v: self._emit(font_size=float(v)))

    def mark_style(self) -> MarkStyle:
        return self._style

    def set_style(self, style: MarkStyle) -> None:
        """Mostra o estilo sem emitir style_changed."""
        self._style = style
        widgets = (self.width_spin, self.opacity_spin, self.font_spin)
        for w in widgets:
            w.blockSignals(True)
        self.color_btn.set_color(style.color)
        self.highlight_btn.set_color(style.highlight)
        self.fill_btn.set_color(style.fill)
        self.width_spin.setValue(style.width)
        self.opacity_spin.setValue(round(style.opacity * 100))
        self.font_spin.setValue(round(style.font_size))
        for w in widgets:
            w.blockSignals(False)

    def _emit(self, **changes) -> None:
        self._style = with_values(self._style, **changes)
        self.style_changed.emit(self._style)
