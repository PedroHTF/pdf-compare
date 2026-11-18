"""Indexação de texto em segundo plano, sem travar a interface.

Processa páginas em pequenas fatias de tempo na thread principal (via QTimer).
Isso evita usar PyMuPDF em várias threads, o que a biblioteca não suporta.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.model.session import DocumentSession
from app.services.text_index import DocumentIndex, extract_tokens


class IndexScheduler(QObject):
    progress = Signal(int, int)          # páginas processadas, total (0, 0 = ocioso)
    document_indexed = Signal(object)    # DocumentSession concluída

    TIME_SLICE = 0.025  # segundos de trabalho por ciclo do loop de eventos

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._indexes: Dict[int, DocumentIndex] = {}
        self._queue: List[DocumentSession] = []
        self._done = 0
        self._total = 0
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._tick)

    @property
    def busy(self) -> bool:
        return bool(self._queue)

    def index_for(self, session: DocumentSession) -> Optional[DocumentIndex]:
        return self._indexes.get(session.uid)

    def add(self, session: DocumentSession) -> None:
        self._indexes[session.uid] = DocumentIndex(session.page_count)
        self._queue.append(session)
        self._total += session.page_count
        self.progress.emit(self._done, self._total)
        if not self._timer.isActive():
            self._timer.start()

    def remove(self, session: DocumentSession) -> None:
        index = self._indexes.pop(session.uid, None)
        if session in self._queue:
            self._queue.remove(session)
            self._done -= len(index.pages) if index else 0
            self._total -= session.page_count
            if not self._queue:
                self._finish()

    def clear(self) -> None:
        self._indexes.clear()
        self._queue.clear()
        self._finish()

    def _tick(self) -> None:
        deadline = time.perf_counter() + self.TIME_SLICE
        while self._queue and time.perf_counter() < deadline:
            session = self._queue[0]
            index = self._indexes[session.uid]
            if session.doc is None:
                self._queue.pop(0)
                continue
            try:
                tokens = extract_tokens(session.doc[len(index.pages)])
            except Exception:  # página danificada: segue sem texto
                tokens = []
            index.add_page(tokens)
            self._done += 1
            if index.complete:
                self._queue.pop(0)
                self.document_indexed.emit(session)
        if self._queue:
            self.progress.emit(self._done, self._total)
        else:
            self._finish()

    def _finish(self) -> None:
        self._timer.stop()
        self._done = self._total = 0
        self.progress.emit(0, 0)
