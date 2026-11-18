"""Navegação: uma posição global compartilhada + deslocamento por documento.

- step()       move todos os PDFs juntos (mantém o alinhamento).
- step_pane()  ajusta só um PDF (altera o deslocamento dele).
- step_hit()   leva um PDF à próxima/anterior ocorrência da pesquisa.
- realign()    zera os deslocamentos.

Sem dependência de interface gráfica, para ser testável diretamente.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from app.model.session import DocumentSession
from app.services.search import Hit


class NavigationController:
    def __init__(self) -> None:
        self.sessions: List[DocumentSession] = []
        self.current: int = 0
        self.hits: List[List[Hit]] = []
        self.hit_index: List[int] = []
        self._hits_by_page: List[Dict[int, List[Hit]]] = []

    # --- documentos ---------------------------------------------------------
    def set_sessions(self, sessions: Sequence[DocumentSession], keep_position: bool = False) -> None:
        self.sessions = list(sessions)
        if not keep_position:
            self.current = 0
        self.current = self._clamp(self.current)
        self.clear_hits()

    @property
    def first(self) -> int:
        return min((s.offset for s in self.sessions), default=0)

    @property
    def last(self) -> int:
        return max(max((s.logical_last for s in self.sessions), default=0), self.first)

    @property
    def at_start(self) -> bool:
        return self.current <= self.first

    @property
    def at_end(self) -> bool:
        return self.current >= self.last

    @property
    def is_aligned(self) -> bool:
        return all(s.offset == 0 for s in self.sessions)

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
        ref = next((p for p in (self.page_for(i) for i in range(len(self.sessions))) if p is not None), 0)
        for s in self.sessions:
            s.offset = 0
        self.current = self._clamp(ref)

    # --- navegação de um único PDF -----------------------------------------
    def raw_page(self, index: int) -> int:
        """Página "teórica" do painel (pode estar antes do início ou após o fim)."""
        return self.current - self.sessions[index].offset

    def page_for(self, index: int) -> Optional[int]:
        return self.sessions[index].page_at(self.current)

    def show_page(self, index: int, page: int) -> None:
        session = self.sessions[index]
        if session.page_count == 0:
            return
        page = max(0, min(page, session.page_count - 1))
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
        hits = self.hits[index]
        if not hits:
            return False
        shown = self.raw_page(index)
        pos = self.hit_index[index]
        if pos < 0 or hits[pos].page != shown:
            if delta > 0:
                pos = next((k for k, h in enumerate(hits) if h.page >= shown), 0)
            else:
                pos = next((k for k in range(len(hits) - 1, -1, -1) if hits[k].page <= shown), len(hits) - 1)
        else:
            pos = (pos + delta) % len(hits)
        self.hit_index[index] = pos
        self.show_page(index, hits[pos].page)
        return True

    def step_hit_all(self, delta: int) -> bool:
        moved = False
        for i in range(len(self.sessions)):
            moved = self.step_hit(i, delta) or moved
        return moved
