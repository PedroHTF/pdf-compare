"""OCR opcional para PDFs escaneados (Tesseract, chamado pelo PyMuPDF).

O Tesseract é um programa à parte, instalado pelo usuário; ele não vem junto
com o PDF Compare. Se não estiver instalado (ou faltar o idioma pedido), as
funções avisam com OcrUnavailable e o programa continua funcionando sem OCR.

O PyMuPDF encontra os dados de idioma pela variável TESSDATA_PREFIX ou, se ela
não existir, procurando o Tesseract instalado. Aqui também procuramos nas pastas
padrão do instalador para Windows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import fitz

from app.services.text_index import Token, extract_tokens

DEFAULT_LANGUAGE = "por"
DEFAULT_DPI = 300

WINDOWS_TESSDATA = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tessdata",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tessdata",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tessdata",
]

INSTALL_HELP = (
    "Para usar o OCR, instale o Tesseract OCR (para Windows: instalador da UB Mannheim, "
    "https://github.com/UB-Mannheim/tesseract/wiki) e marque o idioma Português durante a "
    "instalação. Se ele foi instalado em outra pasta, defina a variável de ambiente "
    "TESSDATA_PREFIX com o caminho da pasta “tessdata”. Depois, reinicie o programa."
)


class OcrUnavailable(Exception):
    """Tesseract ou idioma não disponível."""


@dataclass(frozen=True)
class OcrStatus:
    available: bool
    tessdata: Optional[str]
    languages: tuple
    message: str


def find_tessdata() -> Optional[str]:
    """Pasta tessdata do Tesseract, ou None se não encontrada."""
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).is_dir():
        return env
    try:
        found = fitz.get_tessdata()
        if found and Path(found).is_dir():
            return str(found)
    except Exception:   # PyMuPDF levanta RuntimeError quando não encontra
        pass
    for candidate in WINDOWS_TESSDATA:
        if candidate.is_dir():
            return str(candidate)
    return None


def installed_languages(tessdata: Optional[str]) -> tuple:
    if not tessdata:
        return ()
    try:
        return tuple(sorted(p.stem for p in Path(tessdata).glob("*.traineddata")))
    except OSError:
        return ()


def split_language(language: str) -> List[str]:
    return [part for part in language.replace(",", "+").replace(" ", "+").split("+") if part]


def check(language: str = DEFAULT_LANGUAGE) -> OcrStatus:
    """Verifica se o OCR pode ser usado com o idioma pedido ("por", "por+eng"...)."""
    tessdata = find_tessdata()
    if tessdata is None:
        return OcrStatus(False, None, (), "O Tesseract OCR não foi encontrado neste computador.\n\n" + INSTALL_HELP)
    langs = installed_languages(tessdata)
    wanted = split_language(language) or [DEFAULT_LANGUAGE]
    missing = [w for w in wanted if w not in langs]
    if missing:
        return OcrStatus(
            False, tessdata, langs,
            f"O Tesseract foi encontrado, mas falta o idioma “{'+'.join(missing)}”.\n"
            f"Idiomas instalados: {', '.join(langs) or 'nenhum'}.\n\n" + INSTALL_HELP,
        )
    return OcrStatus(True, tessdata, langs, "OCR disponível.")


def page_needs_ocr(page: fitz.Page) -> bool:
    """Página sem texto pesquisável, mas com imagem (provavelmente escaneada)."""
    if page.get_text("text").strip():
        return False
    try:
        return bool(page.get_images(full=False))
    except Exception:
        return False


def ocr_tokens(page: fitz.Page, language: str = DEFAULT_LANGUAGE, dpi: int = DEFAULT_DPI,
               tessdata: Optional[str] = None) -> List[Token]:
    """Reconhece o texto da página (sem alterar o PDF) e devolve as palavras com posição."""
    tessdata = tessdata or find_tessdata()
    if tessdata is None:
        raise OcrUnavailable("Tesseract OCR não encontrado.")
    lang = "+".join(split_language(language)) or DEFAULT_LANGUAGE
    try:
        textpage = page.get_textpage_ocr(language=lang, dpi=dpi, full=True, tessdata=tessdata)
    except Exception as exc:
        raise OcrUnavailable(f"Falha no OCR: {exc}") from exc
    return extract_tokens(page, textpage=textpage)
