"""Painel lateral com a lista de ocorrências da pesquisa (trecho + página)."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

MAX_ITEMS_PER_DOC = 500   # evita lista enorme com termos muito comuns

# Cada documento: (nome, [(página, trecho), ...])
Results = Sequence[Tuple[str, Sequence[Tuple[int, str]]]]


class ResultsPanel(QWidget):
    hit_activated = Signal(int, int)   # (índice do PDF, posição da ocorrência)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.info = QLabel("Digite algo na pesquisa para ver as ocorrências aqui.")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAccessibleName("Lista de ocorrências da pesquisa")
        self.tree.itemActivated.connect(self._on_item)
        self.tree.itemClicked.connect(self._on_item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.info)
        layout.addWidget(self.tree, 1)

    def set_results(self, query: str, results: Results) -> None:
        self.tree.clear()
        if not query:
            self.info.setText("Digite algo na pesquisa para ver as ocorrências aqui.")
            return
        total = sum(len(items) for _, items in results)
        self.info.setText(f"{total} ocorrência(s) de “{query}”. Clique para ir até ela."
                          if total else f"Nenhuma ocorrência de “{query}”.")
        for doc_index, (name, items) in enumerate(results):
            parent = QTreeWidgetItem([f"{name}  ({len(items)})"])
            parent.setToolTip(0, name)
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for pos, (page, snippet) in enumerate(items[:MAX_ITEMS_PER_DOC]):
                child = QTreeWidgetItem([f"p. {page + 1}  —  {snippet}"])
                child.setToolTip(0, snippet)
                child.setData(0, Qt.ItemDataRole.UserRole, (doc_index, pos))
                parent.addChild(child)
            if len(items) > MAX_ITEMS_PER_DOC:
                more = QTreeWidgetItem([f"… e mais {len(items) - MAX_ITEMS_PER_DOC} (use ▲ ▼ no painel)"])
                more.setFlags(Qt.ItemFlag.NoItemFlags)
                parent.addChild(more)
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)

    def item_count(self) -> List[int]:
        return [self.tree.topLevelItem(i).childCount() for i in range(self.tree.topLevelItemCount())]

    def activate(self, doc_index: int, position: int) -> None:
        """Equivale a clicar na ocorrência (usado também pelos testes)."""
        self.hit_activated.emit(doc_index, position)

    def _on_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.hit_activated.emit(*data)
