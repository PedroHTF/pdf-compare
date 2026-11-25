"""Navegação: uma posição global compartilhada + deslocamento por documento.

- step()       move todos os PDFs juntos (mantém o alinhamento).
- step_pane()  ajusta só um PDF (altera o deslocamento dele).
- step_hit()   leva um PDF à próxima/anterior ocorrência da pesquisa.
- go_to_hit()  leva um PDF a uma ocorrência específica (lista de ocorrências).
- step_diff()  leva um PDF à próxima/anterior diferença de texto.
- realign()    zera os deslocamentos.

Com o alinhamento por conteúdo ligado (set_rows), a posição deixa de ser uma
página com deslocamentos e passa a ser uma linha da tabela de alinhamento:
cada linha diz qual página de cada PDF aparece (ou nenhuma, quando a página
existe só em outro PDF).

Sem dependência de interface gráfica, para ser testável diretamente.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.model.session import DocumentSession
from app.services.search import Hit
from app.services.text_diff import DiffMark


class NavigationController:
    def __init__(self) -> None:
        self.sessions: List[DocumentSession] = []
        self.current: int = 0
        self.hits: List[List[Hit]] = []
        self.hit_index: List[int] = []
        self._hits_by_page: List[Dict[int, List[Hit]]] = []
        self.diffs: List[List[DiffMark]] = []
        self.diff_index: List[int] = []
        self._diffs_by_page: List[Dict[int, List[DiffMark]]] = []
        self.rows: Optional[List[Tuple[Optional[int], ...]]] = None
        self._row_of: List[Dict[int, int]] = []

    # --- alinhamento por conteúdo -------------------------------------------
    @property
    def by_rows(self) -> bool:
        return self.rows is not None

    def set_rows(self, rows: Optional[Sequence[Sequence[Optional[int]]]], follow: Optional[int] = None) -> None:
        """Liga (rows) ou desliga (None) o alinhamento por conteúdo.

        `follow`: índice do PDF cuja página atual deve continuar à vista.
        """
        keep = None
        if follow is not None and 0 <= follow < len(self.sessions):
            keep = self.page_for(follow)
            if keep is None:
                keep = max(0, min(self.raw_page(follow), self.sessions[follow].page_count - 1))
        self.rows = [tuple(r) for r in rows] if rows is not None else None
        self._row_of = []
        if self.rows is not None:
            for doc in range(len(self.sessions)):
                self._row_of.append({row[doc]: r for r, row in reversed(list(enumerate(self.rows)))
                                     if row[doc] is not None})
            self.current = self._clamp(self.current)
            if keep is not None:
                self.current = self._row_of[follow].get(keep, self.current)
        else:
            if keep is not None:
                self.current = self._clamp(keep + self.sessions[follow].offset)
            self.current = self._clamp(self.current)

    def row_of(self, index: int, page: int) -> Optional[int]:
        return self._row_of[index].get(page) if self.rows is not None else None

    # --- documentos ---------------------------------------------------------
    def set_sessions(self, sessions: Sequence[DocumentSession], keep_position: bool = False) -> None:
        self.sessions = list(sessions)
        self.rows = None
        self._row_of = []
        if not keep_position:
            self.current = 0
        self.current = self._clamp(self.current)
        self.clear_hits()
        self.clear_diffs()

    @property
    def first(self) -> int:
        if self.rows is not None:
            return 0
        return min((s.offset for s in self.sessions), default=0)

    @property
    def last(self) -> int:
        if self.rows is not None:
            return max(len(self.rows) - 1, 0)
        return max(max((s.logical_last for s in self.sessions), default=0), self.first)

    @property
    def at_start(self) -> bool:
        return self.current <= self.first

    @property
    def at_end(self) -> bool:
        return self.current >= self.last

    @property
    def is_aligned(self) -> bool:
        return self.rows is not None or all(s.offset == 0 for s in self.sessions)

    def _clamp(self, value: int) -> int:
        return max(self.first, min(value, self.last))

    # --- navegação conjunta -------------------------------------------------
    def go_to(self, logical: int) -> None:
        self.current = self._clamp(logical)

    def step(self, delta: int) -> None:
        self.go_to(self.current + delta)

    def go_first(self) -> None:
        self.go_to(self.first)

    def go_last(self) -> None:
        self.go_to(self.last)

    def realign(self) -> None:
        """Todos voltam a mostrar a mesma página do primeiro PDF visível."""
        if self.rows is not None:
            return
        ref = next((p for p in (self.page_for(i) for i in range(len(self.sessions))) if p is not None), 0)
        for s in self.sessions:
            s.offset = 0
        self.current = self._clamp(ref)

    # --- navegação de um único PDF -----------------------------------------
    def raw_page(self, index: int) -> int:
        """Página "teórica" do painel (pode estar antes do início ou após o fim).

        Alinhado por conteúdo, numa linha sem página deste PDF: a última página
        antes dela (-1 se nenhuma).
        """
        if self.rows is not None:
            for r in range(min(self.current, len(self.rows) - 1), -1, -1):
                if self.rows[r][index] is not None:
                    return self.rows[r][index]
            return -1
        return self.current - self.sessions[index].offset

    def page_for(self, index: int) -> Optional[int]:
        if self.rows is not None:
            return self.rows[self.current][index] if self.rows else None
        return self.sessions[index].page_at(self.current)

    def show_page(self, index: int, page: int) -> None:
        session = self.sessions[index]
        if session.page_count == 0:
            return
        page = max(0, min(page, session.page_count - 1))
        if self.rows is not None:   # alinhado: vai à linha da página (todos acompanham)
            row = self._row_of[index].get(page)
            if row is not None:
                self.current = row
            return
        session.offset = self.current - page

    def step_pane(self, index: int, delta: int) -> None:
        self.show_page(index, self.raw_page(index) + delta)

    # --- ocorrências da pesquisa -------------------------------------------
    def clear_hits(self) -> None:
        self.set_hits([[] for _ in self.sessions])

    def set_hits(self, hits: Sequence[Sequence[Hit]]) -> None:
        self.hits = [list(h) for h in hits]
        self.hit_index = [-1] * len(self.hits)
        self._hits_by_page = []
        for doc_hits in self.hits:
            by_page: Dict[int, List[Hit]] = {}
            for hit in doc_hits:
                by_page.setdefault(hit.page, []).append(hit)
            self._hits_by_page.append(by_page)

    @property
    def total_hits(self) -> int:
        return sum(len(h) for h in self.hits)

    def hit_count(self, index: int) -> int:
        return len(self.hits[index])

    def current_hit(self, index: int) -> Optional[Hit]:
        pos = self.hit_index[index]
        return self.hits[index][pos] if pos >= 0 else None

    def page_hits(self, index: int, page: Optional[int]) -> List[Hit]:
        if page is None:
            return []
        return self._hits_by_page[index].get(page, [])

    def step_hit(self, index: int, delta: int) -> bool:
        """Vai à próxima (+1) ou anterior (-1) ocorrência neste PDF, com retorno circular.

        Se o usuário mudou de página desde a última ocorrência, a busca recomeça
        a partir da página exibida.
        """
        return self._step_in(self.hits, self.hit_index, index, delta)

    def go_to_hit(self, index: int, position: int) -> bool:
        """Mostra a ocorrência `position` do PDF `index` (clique na lista de ocorrências)."""
        if not (0 <= index < len(self.hits) and 0 <= position < len(self.hits[index])):
            return False
        self.hit_index[index] = position
        self.show_page(index, self.hits[index][position].page)
        return True

    def _step_in(self, items: List[list], positions: List[int], index: int, delta: int) -> bool:
        marks = items[index]
        if not marks:
            return False
        shown = self.raw_page(index)
        pos = positions[index]
        if pos < 0 or marks[pos].page != shown:
            if delta > 0:
                pos = next((k for k, h in enumerate(marks) if h.page >= shown), 0)
            else:
                pos = next((k for k in range(len(marks) - 1, -1, -1) if marks[k].page <= shown), len(marks) - 1)
        else:
            pos = (pos + delta) % len(marks)
        positions[index] = pos
        self.show_page(index, marks[pos].page)
        return True

    def step_hit_all(self, delta: int) -> bool:
        if self.rows is not None:
            return self._step_rows(self.hits, self.hit_index, delta)
        moved = False
        for i in range(len(self.sessions)):
            moved = self.step_hit(i, delta) or moved
        return moved

    def _step_rows(self, items: List[list], positions: List[int], delta: int) -> bool:
        """Alinhado por conteúdo: vai à próxima marca de qualquer PDF, em ordem de linha."""
        start = self.current
        best = None
        total = max(len(self.rows), 1)
        for i in range(len(self.sessions)):
            if not items[i]:
                continue
            saved_pos = positions[i]
            self._step_in(items, positions, i, delta)
            row = self.current
            distance = ((row - start) * delta) % total
            if best is None or distance < best[0]:
                best = (distance, i, positions[i], row)
            positions[i] = saved_pos
            self.current = start
        if best is None:
            return False
        _, i, pos, row = best
        positions[i] = pos
        self.current = row
        return True

    # --- diferenças de texto ------------------------------------------------
    def clear_diffs(self) -> None:
        self.set_diffs([[] for _ in self.sessions])

    def set_diffs(self, diffs: Sequence[Sequence[DiffMark]]) -> None:
        self.diffs = [list(d) for d in diffs]
        self.diff_index = [-1] * len(self.diffs)
        self._diffs_by_page = []
        for doc_diffs in self.diffs:
            by_page: Dict[int, List[DiffMark]] = {}
            for mark in doc_diffs:
                by_page.setdefault(mark.page, []).append(mark)
            self._diffs_by_page.append(by_page)

    @property
    def total_diffs(self) -> int:
        return sum(len(d) for d in self.diffs)

    def page_diffs(self, index: int, page: Optional[int]) -> List[DiffMark]:
        if page is None or index >= len(self._diffs_by_page):
            return []
        return self._diffs_by_page[index].get(page, [])

    def current_diff(self, index: int) -> Optional[DiffMark]:
        if index >= len(self.diff_index):
            return None
        pos = self.diff_index[index]
        return self.diffs[index][pos] if pos >= 0 else None

    def step_diff(self, index: int, delta: int) -> bool:
        return self._step_in(self.diffs, self.diff_index, index, delta)

    def step_diff_all(self, delta: int) -> bool:
        if self.rows is not None:
            return self._step_rows(self.diffs, self.diff_index, delta)
        moved = False
        for i in range(len(self.sessions)):
            moved = self.step_diff(i, delta) or moved
        return moved
