"""Barra de pesquisa global (busca em todos os PDFs ao mesmo tempo)."""

from __future__ import annotations

from app.i18n import tr

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMenu, QToolButton, QWidget

from app.services.search import SearchOptions


class SearchBar(QWidget):
    search_changed = Signal()   # texto ou opções mudaram (texto com pequeno atraso)
    next_requested = Signal()
    prev_requested = Signal()

    DEBOUNCE_MS = 250

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        label = QLabel(tr("&Pesquisar:"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(tr("Palavra ou frase — busca em todos os PDFs (Ctrl+F)"))
        self.edit.setClearButtonEnabled(True)
        self.edit.setMinimumWidth(340)
        self.edit.setMaximumWidth(560)
        self.edit.setAccessibleName(tr("Pesquisar em todos os PDFs"))
        label.setBuddy(self.edit)

        self.btn_prev = QToolButton()
        self.btn_prev.setArrowType(Qt.ArrowType.UpArrow)
        self.btn_prev.setToolTip(tr("Ocorrência anterior em cada PDF (Shift+Enter ou Shift+F3)"))
        self.btn_prev.setAccessibleName(tr("Ocorrência anterior em cada PDF"))
        self.btn_next = QToolButton()
        self.btn_next.setArrowType(Qt.ArrowType.DownArrow)
        self.btn_next.setToolTip(tr("Próxima ocorrência em cada PDF (Enter ou F3)"))
        self.btn_next.setAccessibleName(tr("Próxima ocorrência em cada PDF"))

        menu = QMenu(self)
        self.act_case = menu.addAction(tr("Diferenciar maiúsculas e minúsculas"))
        self.act_whole = menu.addAction(tr("Somente palavras inteiras"))
        self.act_accents = menu.addAction(tr("Ignorar acentos (ação = acao)"))
        for action in (self.act_case, self.act_whole, self.act_accents):
            action.setCheckable(True)
        self.act_accents.setChecked(True)
        for action in (self.act_case, self.act_whole, self.act_accents):
            action.toggled.connect(self._on_options_toggled)

        self.btn_options = QToolButton()
        self.btn_options.setText(tr("Opções"))
        self.btn_options.setToolTip(tr("Opções de pesquisa"))
        self.btn_options.setMenu(menu)
        self.btn_options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.summary = QLabel()
        self.summary.setObjectName("searchSummary")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)
        layout.addWidget(label)
        layout.addWidget(self.edit)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_options)
        layout.addSpacing(10)
        layout.addWidget(self.summary, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self.search_changed.emit)
        self.edit.textChanged.connect(lambda _text: self._timer.start())
        self.edit.installEventFilter(self)
        self.btn_next.clicked.connect(self._go_next)
        self.btn_prev.clicked.connect(self._go_prev)

    # --- API --------------------------------------------------------------------
    def text(self) -> str:
        return self.edit.text().strip()

    def options(self) -> SearchOptions:
        return SearchOptions(
            case_sensitive=self.act_case.isChecked(),
            whole_word=self.act_whole.isChecked(),
            ignore_accents=self.act_accents.isChecked(),
        )

    def set_options(self, options: SearchOptions) -> None:
        for action, value in (
            (self.act_case, options.case_sensitive),
            (self.act_whole, options.whole_word),
            (self.act_accents, options.ignore_accents),
        ):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)

    def flush(self) -> None:
        """Executa já a pesquisa pendente (sem esperar o atraso de digitação)."""
        if self._timer.isActive():
            self._timer.stop()
            self.search_changed.emit()

    def focus_search(self) -> None:
        self.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.edit.selectAll()

    def set_summary(self, text: str, state: str = "") -> None:
        self.summary.setText(text)
        if self.summary.property("state") != state:
            self.summary.setProperty("state", state)
            self.summary.style().unpolish(self.summary)
            self.summary.style().polish(self.summary)

    # --- internos ---------------------------------------------------------------
    def _go_next(self) -> None:
        self.flush()
        self.next_requested.emit()

    def _go_prev(self) -> None:
        self.flush()
        self.prev_requested.emit()

    def _on_options_toggled(self, _checked: bool) -> None:
        self._timer.stop()
        self.search_changed.emit()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._go_prev()
                else:
                    self._go_next()
                return True
            if key == Qt.Key.Key_Escape and self.edit.text():
                self.edit.clear()
                self.flush()
                return True
        return super().eventFilter(obj, event)
