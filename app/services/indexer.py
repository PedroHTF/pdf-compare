"""Indexação de texto em segundo plano, sem travar a interface.

Processa páginas em pequenas fatias de tempo na thread principal (via QTimer).
Isso evita usar PyMuPDF em várias threads, o que a biblioteca não suporta.

Com o OCR ligado, páginas sem texto e com imagem passam pelo Tesseract. Cada
página com OCR leva alguns segundos; a interface volta a responder entre uma
página e outra.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.model.session import DocumentSession
from app.services import ocr
from app.services.text_index import DocumentIndex, extract_tokens


class IndexScheduler(QObject):
    progress = Signal(int, int)          # páginas processadas, total (0, 0 = ocioso)
    document_indexed = Signal(object)    # DocumentSession concluída
    ocr_failed = Signal(str)             # mensagem; o OCR é desligado e a indexação segue

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
        self.ocr_enabled = False
        self.ocr_language = ocr.DEFAULT_LANGUAGE
        self._tessdata: Optional[str] = None
        self.ocr_pages: Dict[int, int] = {}   # uid -> páginas reconhecidas por OCR

    def set_ocr(self, enabled: bool, language: str = ocr.DEFAULT_LANGUAGE, tessdata: Optional[str] = None) -> None:
        self.ocr_enabled = enabled
        self.ocr_language = language
        self._tessdata = tessdata

    @property
    def busy(self) -> bool:
        return bool(self._queue)

    def index_for(self, session: DocumentSession) -> Optional[DocumentIndex]:
        return self._indexes.get(session.uid)

    def add(self, session: DocumentSession) -> None:
        if session in self._queue:
            self.remove(session)
        self._indexes[session.uid] = DocumentIndex(session.page_count)
        self.ocr_pages[session.uid] = 0
        self._queue.append(session)
        self._total += session.page_count
        self.progress.emit(self._done, self._total)
        if not self._timer.isActive():
            self._timer.start()

    def remove(self, session: DocumentSession) -> None:
        index = self._indexes.pop(session.uid, None)
        self.ocr_pages.pop(session.uid, None)
        if session in self._queue:
            self._queue.remove(session)
            self._done -= len(index.pages) if index else 0
            self._total -= session.page_count
            if not self._queue:
                self._finish()

    def clear(self) -> None:
        self._indexes.clear()
        self.ocr_pages.clear()
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
            page = session.doc[len(index.pages)]
            try:
                tokens = extract_tokens(page)
            except Exception:  # página danificada: segue sem texto
                tokens = []
            if not tokens and self.ocr_enabled:
                tokens = self._ocr(session, page)
            index.add_page(tokens)
            self._done += 1
            if index.complete:
                self._queue.pop(0)
                self.document_indexed.emit(session)
        if self._queue:
            self.progress.emit(self._done, self._total)
        else:
            self._finish()

    def _ocr(self, session: DocumentSession, page) -> list:
        try:
            if not ocr.page_needs_ocr(page):
                return []
            tokens = ocr.ocr_tokens(page, self.ocr_language, tessdata=self._tessdata)
        except ocr.OcrUnavailable as exc:
            self.ocr_enabled = False
            self.ocr_failed.emit(str(exc))
            return []
        except Exception:
            return []
        if tokens:
            self.ocr_pages[session.uid] = self.ocr_pages.get(session.uid, 0) + 1
        return tokens

    def _finish(self) -> None:
        self._timer.stop()
        self._done = self._total = 0
        self.progress.emit(0, 0)
