"""Janela de Configurações: geral (idiomas), cores da comparação e estilo das marcações."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
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
from app.services.compare_scope import MAX_ZONE
from app.services.preferences import (
    DEFAULT_COMPARE,
    DEFAULT_DIFF_COLORS,
    DEFAULT_STYLE,
    LOOKAHEAD_ALL,
    NEXT_AUTO,
    NEXT_ON_CLICK,
    REALIGN_AUTO,
    REALIGN_ON_CLICK,
    CompareSettings,
    MarkStyle,
)
from app.services.text_diff import ADDED, CHANGED, REMOVED
from app.services.visual_diff import VISUAL
from app.ui.mark_widgets import ColorButton


@dataclass
class SettingsValues:
    language: str
    ocr_language: str
    diff_colors: Dict[str, Color]
    mark_style: MarkStyle
    compare: CompareSettings = field(default_factory=lambda: DEFAULT_COMPARE)
    check_updates: bool = True


LOOKAHEAD_CHOICES = (1, 2, 3, 5, 10, LOOKAHEAD_ALL)


class SettingsDialog(QDialog):
    def __init__(self, values: SettingsValues, ocr_hint: str = "", parent: Optional[QWidget] = None,
                 cache_info: Optional[Callable[[], str]] = None,
                 clear_cache: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self._cache_info = cache_info
        self._clear_cache = clear_cache
        self.setWindowTitle(tr("Configurações"))
        self.setMinimumWidth(580)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(values, ocr_hint), tr("Geral"))
        tabs.addTab(self._compare_tab(values), tr("Comparação"))
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
        self.updates_check = QCheckBox(tr("Verificar atualizações ao abrir (no máximo uma vez por dia)"))
        self.updates_check.setChecked(values.check_updates)
        self.updates_check.setToolTip(tr("Só consulta no GitHub o número da última versão. Nada é baixado "
                                         "ou instalado sem você pedir."))
        form.addRow(tr("Atualizações"), self.updates_check)
        return page

    def _compare_tab(self, values: SettingsValues) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        c = values.compare
        self._page_only = c.page_only

        scope = QGroupBox(tr("O que comparar"))
        form = QFormLayout(scope)
        self.header_spin = QSpinBox()
        self.footer_spin = QSpinBox()
        for spin, value in ((self.header_spin, c.header), (self.footer_spin, c.footer)):
            spin.setRange(0, MAX_ZONE)
            spin.setSpecialValueText(tr("Comparar"))
            spin.setSuffix(tr(" % da página"))
            spin.setValue(value)
        self.header_spin.setToolTip(tr("Ignora o texto no topo de cada página (cabeçalho), na comparação, "
                                       "no relatório e no alinhamento por conteúdo"))
        self.footer_spin.setToolTip(tr("Ignora o texto na base de cada página (rodapé), na comparação, "
                                       "no relatório e no alinhamento por conteúdo"))
        form.addRow(tr("Ignorar cabeçalho"), self.header_spin)
        form.addRow(tr("Ignorar rodapé"), self.footer_spin)
        self.follow_check = QCheckBox(tr("Seguir o alinhamento feito à mão (trechos e páginas alinhados)"))
        self.follow_check.setChecked(c.follow_alignment)
        self.follow_check.setToolTip(tr("Com o alinhamento por conteúdo ligado, cada trecho é comparado com o "
                                        "trecho que você alinhou a ele"))
        form.addRow("", self.follow_check)
        note = QLabel(tr("Páginas inteiras (ex.: índice) podem ser ignoradas pelo botão direito na página ou em "
                         "Ferramentas › Páginas ignoradas na comparação."))
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(scope)

        batches = QGroupBox(tr("Comparação em lotes"))
        form = QFormLayout(batches)
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(0, 10000)
        self.batch_spin.setSingleStep(10)
        self.batch_spin.setSpecialValueText(tr("Tudo de uma vez"))
        self.batch_spin.setSuffix(tr(" páginas"))
        self.batch_spin.setValue(c.batch_size)
        form.addRow(tr("Páginas por lote"), self.batch_spin)
        self.next_combo = QComboBox()
        self.next_combo.addItem(tr("Ao clicar em “Comparar próximo lote”"), NEXT_ON_CLICK)
        self.next_combo.addItem(tr("Automaticamente, em segundo plano"), NEXT_AUTO)
        self.next_combo.setCurrentIndex(max(self.next_combo.findData(c.next_mode), 0))
        form.addRow(tr("Comparar o próximo lote"), self.next_combo)
        self.lookahead_combo = QComboBox()
        for n in LOOKAHEAD_CHOICES:
            self.lookahead_combo.addItem(tr("Todos") if n == LOOKAHEAD_ALL else str(n), n)
        self.lookahead_combo.setCurrentIndex(max(self.lookahead_combo.findData(c.lookahead), 0))
        form.addRow(tr("Lotes preparados à frente"), self.lookahead_combo)
        self.pause_check = QCheckBox(tr("Pausar enquanto eu rolo as páginas ou faço marcações"))
        self.pause_check.setChecked(c.pause_while_busy)
        form.addRow("", self.pause_check)
        self.realign_combo = QComboBox()
        self.realign_combo.addItem(tr("Mostrar “Recomparar” e esperar o meu clique"), REALIGN_ON_CLICK)
        self.realign_combo.addItem(tr("Recomparar automaticamente"), REALIGN_AUTO)
        self.realign_combo.setCurrentIndex(max(self.realign_combo.findData(c.realign_mode), 0))
        self.realign_combo.setToolTip(tr("O que fazer quando você ajusta o alinhamento de um PDF "
                                         "(◀ ▶ do painel, página digitada ou Realinhar)"))
        form.addRow(tr("Quando o alinhamento mudar"), self.realign_combo)
        self.next_combo.currentIndexChanged.connect(self._sync_compare_widgets)
        self.batch_spin.valueChanged.connect(self._sync_compare_widgets)
        layout.addWidget(batches)

        saved = QGroupBox(tr("Comparações salvas (cache)"))
        form = QFormLayout(saved)
        self.cache_days_spin = QSpinBox()
        self.cache_days_spin.setRange(0, 3650)
        self.cache_days_spin.setSpecialValueText(tr("Nunca"))
        self.cache_days_spin.setSuffix(tr(" dias"))
        self.cache_days_spin.setValue(c.cache_days)
        form.addRow(tr("Apagar as não usadas após"), self.cache_days_spin)
        self.cache_label = QLabel()
        self.cache_label.setObjectName("muted")
        clear = QPushButton(tr("Limpar cache agora"))
        clear.clicked.connect(self.clear_cache)
        clear.setEnabled(self._clear_cache is not None)
        form.addRow(self.cache_label, clear)
        self._update_cache_label()
        note = QLabel(tr("Lotes já comparados são reaproveitados ao reabrir os mesmos PDFs."))
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(saved)

        visual = QGroupBox(tr("Diferença visual (pixel a pixel)"))
        form = QFormLayout(visual)
        self.visual_spin = QSpinBox()
        self.visual_spin.setRange(1, 100)
        self.visual_spin.setSuffix(" %")
        self.visual_spin.setValue(c.visual_sensitivity)
        self.visual_spin.setToolTip(tr("Mais alto: marca diferenças menores (e mais ruído em PDFs escaneados)"))
        form.addRow(tr("Sensibilidade"), self.visual_spin)
        note = QLabel(tr("Ligue em Ferramentas › Diferença visual. Encontra mudanças em imagens, assinaturas, "
                         "carimbos e PDFs escaneados."))
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(visual)

        colors = QGroupBox(tr("Cores"))
        form = QFormLayout(colors)
        self.diff_buttons = {
            ADDED: ColorButton(values.diff_colors[ADDED], tr("Incluído")),
            REMOVED: ColorButton(values.diff_colors[REMOVED], tr("Removido")),
            CHANGED: ColorButton(values.diff_colors[CHANGED], tr("Alterado")),
            VISUAL: ColorButton(values.diff_colors[VISUAL], tr("Diferença visual")),
        }
        for kind, button in self.diff_buttons.items():
            form.addRow(button.toolTip(), button)
        reset = QPushButton(tr("Restaurar cores padrão"))
        reset.clicked.connect(self.reset_diff_colors)
        form.addRow("", reset)
        layout.addWidget(colors)
        layout.addStretch(1)
        self._sync_compare_widgets()
        return page

    def _sync_compare_widgets(self) -> None:
        batched = self.batch_spin.value() > 0
        auto = self.next_combo.currentData() == NEXT_AUTO
        self.next_combo.setEnabled(batched)
        self.realign_combo.setEnabled(batched)
        self.lookahead_combo.setEnabled(batched and auto)
        self.pause_check.setEnabled(batched and auto)

    def _update_cache_label(self) -> None:
        self.cache_label.setText(self._cache_info() if self._cache_info else "")

    def clear_cache(self) -> None:
        if self._clear_cache is not None:
            self._clear_cache()
            self._update_cache_label()

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
            check_updates=self.updates_check.isChecked(),
            compare=CompareSettings(
                batch_size=self.batch_spin.value(), next_mode=self.next_combo.currentData(),
                lookahead=self.lookahead_combo.currentData(), pause_while_busy=self.pause_check.isChecked(),
                cache_days=self.cache_days_spin.value(), realign_mode=self.realign_combo.currentData(),
                visual_sensitivity=self.visual_spin.value(),
                header=self.header_spin.value(), footer=self.footer_spin.value(),
                follow_alignment=self.follow_check.isChecked(), page_only=self._page_only,
            ),
        )
