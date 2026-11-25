"""Diálogo de exportação: o que exportar, em que formato e para onde."""

from __future__ import annotations

from app.i18n import tr

from dataclasses import dataclass
from typing import Optional

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.export import PDF, PNG

SIDE_BY_SIDE = "side_by_side"   # comparação lado a lado
CURRENT_PAGES = "current"       # página atual de cada PDF, um arquivo por PDF
ANNOTATED = "annotated"         # cada PDF inteiro com as anotações

SCOPE_CURRENT = "current"
SCOPE_ALL = "all"


@dataclass
class ExportChoice:
    kind: str = SIDE_BY_SIDE
    fmt: str = PDF
    scope: str = SCOPE_CURRENT
    with_annotations: bool = True
    dpi: int = 150


class ExportDialog(QDialog):
    def __init__(self, has_annotations: bool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exportar")

        what = QGroupBox(tr("O que exportar"))
        self.rb_side = QRadioButton(tr("Comparação lado a lado (todos os PDFs em uma página)"))
        self.rb_current = QRadioButton(tr("Página atual de cada PDF (um arquivo por PDF)"))
        self.rb_annotated = QRadioButton(tr("Cada PDF inteiro com as anotações (PDF, um arquivo por PDF)"))
        self.rb_side.setChecked(True)
        self.kind_group = QButtonGroup(self)
        box = QVBoxLayout(what)
        for rb in (self.rb_side, self.rb_current, self.rb_annotated):
            self.kind_group.addButton(rb)
            box.addWidget(rb)

        self.fmt = QComboBox()
        self.fmt.addItem(tr("PDF (texto continua selecionável)"), PDF)
        self.fmt.addItem(tr("PNG (imagem)"), PNG)
        self.scope = QComboBox()
        self.scope.addItem(tr("Somente a posição atual"), SCOPE_CURRENT)
        self.scope.addItem(tr("Todas as páginas (uma página/imagem por posição)"), SCOPE_ALL)
        self.dpi = QSpinBox()
        self.dpi.setRange(50, 600)
        self.dpi.setSingleStep(50)
        self.dpi.setValue(150)
        self.dpi.setSuffix(tr(" dpi"))
        self.annotations = QCheckBox(tr("Incluir minhas marcações (destaques, formas, textos e notas)"))
        self.annotations.setChecked(has_annotations)

        form = QFormLayout()
        form.addRow(tr("Formato:"), self.fmt)
        form.addRow(tr("Páginas:"), self.scope)
        form.addRow(tr("Resolução do PNG:"), self.dpi)

        note = QLabel(tr("O PDF original nunca é alterado: a exportação cria arquivos novos."))
        note.setObjectName("muted")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Exportar…"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(what)
        layout.addLayout(form)
        layout.addWidget(self.annotations)
        layout.addWidget(note)
        layout.addWidget(buttons)

        for w in (self.rb_side, self.rb_current, self.rb_annotated):
            w.toggled.connect(self._sync)
        self.fmt.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        annotated = self.rb_annotated.isChecked()
        self.fmt.setEnabled(not annotated)
        if annotated:
            self.fmt.setCurrentIndex(0)
        self.scope.setEnabled(self.rb_side.isChecked())
        self.dpi.setEnabled(self.fmt.currentData() == PNG)
        self.annotations.setEnabled(not annotated)

    def choice(self) -> ExportChoice:
        if self.rb_annotated.isChecked():
            kind = ANNOTATED
        elif self.rb_current.isChecked():
            kind = CURRENT_PAGES
        else:
            kind = SIDE_BY_SIDE
        return ExportChoice(
            kind=kind,
            fmt=self.fmt.currentData(),
            scope=self.scope.currentData() if kind == SIDE_BY_SIDE else SCOPE_CURRENT,
            with_annotations=True if kind == ANNOTATED else self.annotations.isChecked(),
            dpi=self.dpi.value(),
        )
