"""Painel lateral com todas as marcações, por documento e página, com filtros."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.i18n import tr
from app.services import annotations as am
from app.services.annotations import Annotation
from app.services.preferences import from_hex, to_hex
from app.ui.mark_widgets import kind_label, swatch

ALL = ""
# Cada documento: (nome, [anotações])
Documents = Sequence[Tuple[str, Sequence[Annotation]]]


def mark_summary(a: Annotation) -> str:
    text = " ".join(a.text.split())
    if len(text) > 60:
        text = text[:57] + "…"
    base = tr("p. {page}  —  {kind}", page=a.page + 1, kind=kind_label(a.kind))
    return f"{base}: {text}" if text else base


class MarksPanel(QWidget):
    mark_activated = Signal(int, str)   # (índice do PDF, id da marcação)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.kind_filter = QComboBox()
        self.kind_filter.setToolTip(tr("Mostrar só um tipo de marcação"))
        self.kind_filter.addItem(tr("Todos os tipos"), ALL)
        for kind in am.KINDS:
            self.kind_filter.addItem(kind_label(kind), kind)
        self.color_filter = QComboBox()
        self.color_filter.setToolTip(tr("Mostrar só uma cor"))
        self.kind_filter.currentIndexChanged.connect(self._refill)
        self.color_filter.currentIndexChanged.connect(self._refill)

        filters = QHBoxLayout()
        filters.addWidget(self.kind_filter, 1)
        filters.addWidget(self.color_filter, 1)

        self.info = QLabel()
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAccessibleName(tr("Lista de marcações"))
        self.tree.itemActivated.connect(self._on_item)
        self.tree.itemClicked.connect(self._on_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(filters)
        layout.addWidget(self.info)
        layout.addWidget(self.tree, 1)
        self._documents: Documents = []
        self.set_documents([])

    def set_documents(self, documents: Documents) -> None:
        self._documents = documents
        colors = sorted({to_hex(a.stroke_color) for _, items in documents for a in items})
        current = self.color_filter.currentData()
        self.color_filter.blockSignals(True)
        self.color_filter.clear()
        self.color_filter.addItem(tr("Todas as cores"), ALL)
        for hex_color in colors:
            self.color_filter.addItem(swatch(from_hex(hex_color)), hex_color, hex_color)
        self.color_filter.setCurrentIndex(max(self.color_filter.findData(current), 0))
        self.color_filter.blockSignals(False)
        self._refill()

    def _refill(self) -> None:
        self.tree.clear()
        kind = self.kind_filter.currentData() or ALL
        color = self.color_filter.currentData() or ALL
        total = 0
        for doc_index, (name, items) in enumerate(self._documents):
            shown = [a for a in sorted(items, key=lambda a: (a.page, a.bounds[1], a.bounds[0]))
                     if (kind == ALL or a.kind == kind) and (color == ALL or to_hex(a.stroke_color) == color)]
            if not shown:
                continue
            total += len(shown)
            parent = QTreeWidgetItem([f"{name}  ({len(shown)})"])
            parent.setToolTip(0, name)
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for a in shown:
                child = QTreeWidgetItem([mark_summary(a)])
                child.setIcon(0, swatch(a.stroke_color, 12))
                child.setToolTip(0, a.text or kind_label(a.kind))
                child.setData(0, Qt.ItemDataRole.UserRole, (doc_index, a.id))
                parent.addChild(child)
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)
        if not any(items for _, items in self._documents):
            self.info.setText(tr("Nenhuma marcação ainda. Use a barra de marcação para destacar, desenhar ou escrever."))
        else:
            self.info.setText(tr("{n} marcação(ões). Clique para ir até ela.", n=total))

    def item_ids(self) -> List[str]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            out += [parent.child(j).data(0, Qt.ItemDataRole.UserRole)[1] for j in range(parent.childCount())]
        return out

    def _on_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.mark_activated.emit(*data)
