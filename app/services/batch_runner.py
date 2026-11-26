"""Executa a comparação em lotes em segundo plano.

A comparação de cada par (referência, outro PDF) de um lote roda em uma thread
separada. Ela usa só as palavras já extraídas (listas Python), nunca o PyMuPDF,
então é seguro sair da thread principal. A interface continua respondendo e
os resultados chegam aos poucos.

- Lotes pedidos pelo usuário (prioritários) passam na frente e ignoram a pausa.
- Lotes adiantados em segundo plano esperam a pausa terminar (o usuário está
  rolando ou anotando) e podem ser cancelados.
- Um par só começa quando as páginas dele já foram lidas pelo indexador.
"""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from app.services.diff_batches import Batch, DiffCache, Pair, pair_key, plan_batches
from app.services.text_diff import DiffMark, SyncPoint, diff_pair, merge_results
from app.services.text_index import DocumentIndex


@dataclass
class _Job:
    batch: int
    pair: int            # posição do par (a, b) em `pairs`
    priority: bool
    key: str


class BatchRunner(QObject):
    changed = Signal()                 # novos resultados disponíveis
    progress = Signal(int, int)        # pares concluídos, total pedido (0, 0 = ocioso)

    POLL_MS = 30

    def __init__(self, cache: Optional[DiffCache] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.batches: List[Batch] = []
        self._indexes: List[DocumentIndex] = []
        self._fingerprints: List[str] = []
        self._options = ""
        self._sync: Dict[Tuple[int, int], List[SyncPoint]] = {}   # pontos alinhados à mão, por par
        self.pairs: List[Tuple[int, int]] = []           # (base, comparado) de cada comparação
        self._results: Dict[int, Dict[int, Pair]] = {}   # lote -> {par: resultado}
        self._queue: List[_Job] = []
        self._running: Optional[_Job] = None
        self._future: Optional[Future] = None
        self._generation = 0
        self._requested = 0
        self._finished = 0
        self.hold_until = 0.0
        self.from_cache = 0          # pares carregados do cache (informativo / testes)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdfcompare-diff")
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._tick)

    # --- configuração ----------------------------------------------------------
    def configure(self, indexes: Sequence[DocumentIndex], fingerprints: Sequence[str], offsets: Sequence[int],
                  batch_size: int, options: str = "", pairs: Optional[Sequence[Tuple[int, int]]] = None,
                  primary: int = 0, batches: Optional[Sequence[Batch]] = None,
                  sync: Optional[Dict[Tuple[int, int], Sequence[SyncPoint]]] = None) -> None:
        """Novo plano de lotes. Descarta resultados e pedidos anteriores.

        `pairs`: comparações (base, comparado); padrão: o PDF 0 com cada um dos outros.
        `batches`: plano pronto (ex.: do alinhamento por conteúdo); senão, usa `offsets`.
        `sync`: pontos alinhados pelo usuário em cada par (a comparação segue esse alinhamento).
        """
        self.reset()
        self._indexes = list(indexes)
        self._fingerprints = list(fingerprints)
        self._options = options
        self._sync = {pair: sorted(points) for pair, points in (sync or {}).items() if points}
        self.pairs = list(pairs) if pairs is not None else [(0, i) for i in range(1, len(indexes))]
        counts = [i.page_count for i in self._indexes]
        if len(counts) < 2:
            self.batches = []
        elif batches is not None:
            self.batches = list(batches)
        else:
            self.batches = plan_batches(counts, offsets, batch_size, primary)

    def reset(self) -> None:
        self._generation += 1
        self._queue.clear()
        self._running = None
        self._future = None
        self._results.clear()
        self.batches = []
        self.pairs = []
        self._requested = self._finished = 0
        self.from_cache = 0
        self._timer.stop()
        self.progress.emit(0, 0)

    def shutdown(self) -> None:
        self.reset()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --- estado ---------------------------------------------------------------
    @property
    def busy(self) -> bool:
        return bool(self._queue) or self._running is not None

    @property
    def documents(self) -> int:
        return len(self._indexes)

    def is_done(self, batch: int) -> bool:
        return bool(self.pairs) and len(self._results.get(batch, {})) == len(self.pairs)

    def is_pending(self, batch: int) -> bool:
        return any(j.batch == batch for j in self._queue) or (self._running is not None and self._running.batch == batch)

    def done_count(self) -> int:
        return sum(1 for b in self.batches if self.is_done(b.number))

    def background_pending(self) -> bool:
        return any(not j.priority for j in self._queue) or (self._running is not None and not self._running.priority)

    def marks(self) -> List[List[DiffMark]]:
        """Marcas de todos os lotes já comparados, por documento, em ordem de leitura."""
        result: List[List[DiffMark]] = [[] for _ in self._indexes]
        for b in self.batches:
            if not self.is_done(b.number):
                continue
            results = [self._results[b.number][p] for p in range(len(self.pairs))]
            for doc, marks in enumerate(merge_results(self.documents, self.pairs, results)):
                result[doc].extend(marks)
        return result

    # --- pedidos ---------------------------------------------------------------
    def request(self, batch: int, priority: bool = True) -> bool:
        """Pede a comparação de um lote. Devolve False se ele já está pronto ou pedido."""
        if not (0 <= batch < len(self.batches)) or self.is_done(batch):
            return False
        if self.is_pending(batch):
            if priority:   # sobe para a frente da fila
                jobs = [j for j in self._queue if j.batch == batch]
                for j in jobs:
                    j.priority = True
                self._queue = jobs + [j for j in self._queue if j.batch != batch]
            return False
        b = self.batches[batch]
        jobs = []
        for p, (a, other) in enumerate(self.pairs):
            if p in self._results.get(batch, {}):
                continue
            key = pair_key(self._fingerprints[a], self._fingerprints[other], b.ranges[a], b.ranges[other],
                           self._options + self._sync_key(a, other))
            jobs.append(_Job(batch, p, priority, key))
        self._queue = jobs + self._queue if priority else self._queue + jobs
        self._requested += len(jobs)
        self.progress.emit(self._finished, self._requested)
        if not self._timer.isActive():
            self._timer.start()
        QTimer.singleShot(0, self._tick)
        return True

    def _sync_key(self, a: int, b: int) -> str:
        points = self._sync.get((a, b))
        if not points:
            return ""
        return ":sync=" + hashlib.sha1(repr(points).encode()).hexdigest()[:16]

    def cancel_background(self) -> None:
        """Cancela os lotes adiantados (os pedidos pelo usuário continuam)."""
        removed = [j for j in self._queue if not j.priority]
        self._queue = [j for j in self._queue if j.priority]
        self._requested -= len(removed)
        if self._running is not None and not self._running.priority:
            self._generation += 1      # o resultado em andamento será ignorado
            self._requested -= 1
            self._running = None
            self._future = None
        self._after_change()

    def cancel(self) -> None:
        """Cancela tudo o que ainda não terminou (os lotes prontos continuam valendo)."""
        self._generation += 1
        self._queue.clear()
        self._running = None
        self._future = None
        self._requested = self._finished
        self._after_change()

    def pause_for(self, seconds: float) -> None:
        self.hold_until = max(self.hold_until, time.monotonic() + seconds)

    # --- execução ----------------------------------------------------------------
    def _ready(self, job: _Job) -> bool:
        b = self.batches[job.batch]
        for doc in self.pairs[job.pair]:
            end = b.ranges[doc][1]
            if len(self._indexes[doc].pages) < end:
                return False
        return True

    def _tick(self) -> None:
        if self._future is not None:
            if not self._future.done():
                return
            self._collect()
        if self._running is not None:
            return
        held = time.monotonic() < self.hold_until
        for pos, job in enumerate(self._queue):
            if (held and not job.priority) or not self._ready(job):
                continue
            self._queue.pop(pos)
            self._start(job)
            break
        if not self.busy:
            self._after_change()

    def _start(self, job: _Job) -> None:
        cached = self.cache.load(job.key) if self.cache is not None else None
        if cached is not None:
            self.from_cache += 1
            self._store(job, cached)
            QTimer.singleShot(0, self._tick)
            return
        b = self.batches[job.batch]
        a, other = self.pairs[job.pair]
        self._running = job
        self._future = self._executor.submit(diff_pair, self._indexes[a], self._indexes[other],
                                             ref_pages=b.ranges[a], other_pages=b.ranges[other],
                                             sync=self._sync.get((a, other)))
        self._future.generation = self._generation   # type: ignore[attr-defined]

    def _collect(self) -> None:
        future, job = self._future, self._running
        self._future = None
        self._running = None
        if job is None or getattr(future, "generation", None) != self._generation:
            return
        try:
            pair = future.result()
        except Exception:   # nunca deve acontecer; o lote fica sem diferenças em vez de travar
            pair = ([], [])
        if self.cache is not None:
            self.cache.save(job.key, pair)
        self._store(job, pair)

    def _store(self, job: _Job, pair: Pair) -> None:
        self._results.setdefault(job.batch, {})[job.pair] = (list(pair[0]), list(pair[1]))
        self._finished += 1
        self.progress.emit(self._finished, self._requested)
        if self.is_done(job.batch):
            self.changed.emit()

    def _after_change(self) -> None:
        if not self.busy:
            self._timer.stop()
            self._requested = self._finished = 0
            self.progress.emit(0, 0)
        else:
            self.progress.emit(self._finished, self._requested)
