"""Janela de Configurações: geral (idiomas), cores da comparação e estilo das marcações."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import LANGUAGES, tr
from app.services.annotations import Color
from app.services.preferences import DEFAULT_DIFF_COLORS, DEFAULT_STYLE, MarkStyle
from app.services.text_diff import ADDED, CHANGED, REMOVED
from app.ui.mark_widgets import ColorButton


@dataclass
class SettingsValues:
    language: str
    ocr_language: str
    diff_colors: Dict[str, Color]
    mark_style: MarkStyle


class SettingsDialog(QDialog):
    def __init__(self, values: SettingsValues, ocr_hint: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Configurações"))
        self.setMinimumWidth(460)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(values, ocr_hint), tr("Geral"))
        tabs.addTab(self._colors_tab(values), tr("Cores da comparação"))
        tabs.addTab(self._marks_tab(values.mark_style), tr("Marcações"))
        self.tabs = tabs

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --- abas ----------------------------------------------------------------------
    def _general_tab(self, values: SettingsValues, ocr_hint: str) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.language_combo = QComboBox()
        for code, label in LANGUAGES.items():
            self.language_combo.addItem(label, code)
        self.language_combo.setCurrentIndex(max(self.language_combo.findData(values.language), 0))
        form.addRow("Idioma / Language", self.language_combo)
        note = QLabel(tr("A troca de idioma vale depois de reiniciar o programa."))
        note.setObjectName("muted")
        form.addRow("", note)
        self.ocr_edit = QLineEdit(values.ocr_language)
        self.ocr_edit.setPlaceholderText("eng")
        form.addRow(tr("Idioma do OCR"), self.ocr_edit)
        if ocr_hint:
            hint = QLabel(ocr_hint)
            hint.setObjectName("muted")
            hint.setWordWrap(True)
            form.addRow("", hint)
        return page

    def _colors_tab(self, values: SettingsValues) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.diff_buttons = {
            ADDED: ColorButton(values.diff_colors[ADDED], tr("Incluído")),
            REMOVED: ColorButton(values.diff_colors[REMOVED], tr("Removido")),
            CHANGED: ColorButton(values.diff_colors[CHANGED], tr("Alterado")),
        }
        for kind, button in self.diff_buttons.items():
            form.addRow(button.toolTip(), button)
        reset = QPushButton(tr("Restaurar cores padrão"))
        reset.clicked.connect(self.reset_diff_colors)
        form.addRow("", reset)
        return page

    def _marks_tab(self, style: MarkStyle) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.mark_color = ColorButton(style.color, tr("Cor do contorno e do texto"))
        self.mark_highlight = ColorButton(style.highlight, tr("Cor do destaque"))
        self.mark_fill = ColorButton(style.fill, tr("Preenchimento das formas"), allow_none=True)
        self.mark_width = QDoubleSpinBox()
        self.mark_width.setRange(0.0, 20.0)
        self.mark_width.setSingleStep(0.5)
        self.mark_width.setDecimals(1)
        self.mark_width.setSuffix(" pt")
        self.mark_opacity = QSpinBox()
        self.mark_opacity.setRange(5, 100)
        self.mark_opacity.setSuffix(" %")
        self.mark_font = QSpinBox()
        self.mark_font.setRange(4, 96)
        self.mark_font.setSuffix(" pt")
        form.addRow(tr("Cor do contorno e do texto"), self.mark_color)
        form.addRow(tr("Cor do destaque"), self.mark_highlight)
        form.addRow(tr("Preenchimento das formas"), self.mark_fill)
        form.addRow(tr("Espessura do contorno"), self.mark_width)
        form.addRow(tr("Opacidade"), self.mark_opacity)
        form.addRow(tr("Tamanho da fonte"), self.mark_font)
        reset = QPushButton(tr("Restaurar estilo padrão"))
        reset.clicked.connect(lambda: self._show_style(DEFAULT_STYLE))
        form.addRow("", reset)
        self._show_style(style)
        return page

    # --- valores ------------------------------------------------------------------
    def reset_diff_colors(self) -> None:
        for kind, button in self.diff_buttons.items():
            button.set_color(DEFAULT_DIFF_COLORS[kind])

    def _show_style(self, style: MarkStyle) -> None:
        self.mark_color.set_color(style.color)
        self.mark_highlight.set_color(style.highlight)
        self.mark_fill.set_color(style.fill)
        self.mark_width.setValue(style.width)
        self.mark_opacity.setValue(round(style.opacity * 100))
        self.mark_font.setValue(round(style.font_size))

    def values(self) -> SettingsValues:
        return SettingsValues(
            language=self.language_combo.currentData(),
            ocr_language=self.ocr_edit.text().strip() or "eng",
            diff_colors={kind: b.color() for kind, b in self.diff_buttons.items()},
            mark_style=MarkStyle(
                color=self.mark_color.color(), highlight=self.mark_highlight.color(), fill=self.mark_fill.color(),
                width=float(self.mark_width.value()), opacity=self.mark_opacity.value() / 100,
                font_size=float(self.mark_font.value()),
            ),
        )
