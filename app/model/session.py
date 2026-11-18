"""Representa um PDF aberto na comparação."""

from __future__ import annotations

from app.i18n import tr

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

_ids = itertools.count(1)


class PdfOpenError(Exception):
    """Falha ao abrir um PDF (arquivo inválido, protegido por senha, vazio...)."""


class PasswordRequired(PdfOpenError):
    """O PDF tem senha de abertura e nenhuma senha foi informada."""


class WrongPassword(PdfOpenError):
    """A senha informada não abre o PDF."""


@dataclass(eq=False)
class DocumentSession:
    path: Path
    # Deslocamento de alinhamento: página exibida = posição global - offset.
    # Muda quando o usuário ajusta só este PDF; "Realinhar" volta a zero.
    offset: int = 0
    doc: fitz.Document | None = field(default=None, repr=False)
    uid: int = field(default_factory=lambda: next(_ids))
    encrypted: bool = False  # aberto com senha (a senha em si nunca é guardada)

    @classmethod
    def open(cls, path: Path | str, offset: int = 0, password: str | None = None) -> "DocumentSession":
        """Abre o PDF. Se ele tiver senha de abertura, `password` é obrigatória.

        PDFs só com senha de permissões (impressão, cópia) abrem sem pedir nada.
        """
        path = Path(path)
        try:
            doc = fitz.open(str(path))
        except Exception as exc:  # PyMuPDF levanta exceções variadas
            raise PdfOpenError(tr("Não foi possível abrir “{name}”: arquivo inválido ou corrompido.", name=path.name)) from exc
        if not doc.is_pdf:
            doc.close()
            raise PdfOpenError(tr("“{name}” não é um PDF.", name=path.name))
        encrypted = bool(doc.needs_pass)
        if encrypted:
            if password is None:
                doc.close()
                raise PasswordRequired(tr("“{name}” está protegido por senha.", name=path.name))
            if not doc.authenticate(password):
                doc.close()
                raise WrongPassword(tr("Senha incorreta para “{name}”.", name=path.name))
        if doc.page_count == 0:
            doc.close()
            raise PdfOpenError(tr("“{name}” não contém páginas.", name=path.name))
        return cls(path=path, offset=offset, doc=doc, encrypted=encrypted)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc is not None else 0

    @property
    def logical_last(self) -> int:
        """Última posição global ocupada por este documento."""
        return self.offset + self.page_count - 1

    def page_at(self, logical: int) -> int | None:
        """Página do arquivo na posição global, ou None se fora do documento."""
        index = logical - self.offset
        if 0 <= index < self.page_count:
            return index
        return None

    def close(self) -> None:
        if self.doc is not None:
            self.doc.close()
            self.doc = None
