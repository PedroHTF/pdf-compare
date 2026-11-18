"""Idioma da interface (inglês ou português), sem dependência de Qt.

Os textos do código-fonte estão em português e passam por tr(). Em inglês,
tr() devolve a tradução de app/i18n_en.py. Textos com valores variáveis usam
campos nomeados: tr("Senha de “{name}”", name=arquivo).

O idioma é escolhido uma vez, antes de criar a janela (o programa pede para
reiniciar quando o usuário troca de idioma).
"""

from __future__ import annotations

from typing import Dict, Optional

ENGLISH = "en"
PORTUGUESE = "pt"
LANGUAGES = {ENGLISH: "English", PORTUGUESE: "Português"}

_language = PORTUGUESE


def set_language(code: Optional[str]) -> str:
    global _language
    _language = normalize(code)
    return _language


def language() -> str:
    return _language


def normalize(code: Optional[str]) -> str:
    """"pt_BR", "pt-PT", "pt" -> pt; qualquer outro idioma -> en."""
    code = (code or "").strip().lower().replace("-", "_")
    return PORTUGUESE if code.startswith("pt") else ENGLISH


def _table() -> Dict[str, str]:
    if _language == ENGLISH:
        from app.i18n_en import EN

        return EN
    return {}


def tr(text: str, **fields) -> str:
    translated = _table().get(text, text)
    return translated.format(**fields) if fields else translated


def plural(n: int, singular: str, plural_: str) -> str:
    """tr() com singular/plural: plural(3, "{n} arquivo", "{n} arquivos")."""
    return tr(singular if n == 1 else plural_, n=n)
