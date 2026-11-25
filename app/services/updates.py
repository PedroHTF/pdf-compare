"""Aviso de nova versão: consulta a última Release publicada no GitHub.

Nada é baixado nem instalado: o programa só lê o número da última versão e o
endereço da página da Release, para o usuário decidir se quer abrir. A consulta
é pública (sem conta, sem enviar dados do usuário) e qualquer falha (sem
internet, GitHub fora do ar, limite de consultas) é ignorada em silêncio.
Sem dependência de interface gráfica.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app import __url__, __version__

API_URL = "https://api.github.com/repos/PedroHTF/pdf-compare/releases/latest"
CHECK_INTERVAL = 24 * 3600   # verificação automática: no máximo uma vez por dia
TIMEOUT = 6


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str            # página da Release (downloads e novidades)
    notes: str = ""     # primeiras linhas das novidades


def parse_version(text: str) -> Tuple[int, ...]:
    """ "v0.3.0" -> (0, 3, 0). Sufixos como "-beta" são ignorados; texto inválido -> ()."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in match.group(1).split(".")) if match else ()


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    if not new or not old:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


def parse_release(data: dict) -> Optional[ReleaseInfo]:
    """Converte a resposta da API do GitHub. Ignora rascunhos e pré-lançamentos."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name") or "").lstrip("vV")
    if not parse_version(version):
        return None
    url = str(data.get("html_url") or f"{__url__}/releases/latest")
    if not url.startswith("https://github.com/"):
        url = f"{__url__}/releases/latest"   # só abre páginas do GitHub
    notes = str(data.get("body") or "").strip()
    return ReleaseInfo(version, url, notes[:1500])


def fetch_latest(opener: Callable = urllib.request.urlopen) -> Optional[ReleaseInfo]:
    """Última Release publicada, ou None se não for possível consultar."""
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"PDF-Compare/{__version__}",
    })
    try:
        with opener(request, timeout=TIMEOUT) as response:
            return parse_release(json.loads(response.read().decode("utf-8")))
    except Exception:   # rede, JSON, limite de consultas: o aviso simplesmente não aparece
        return None


def due(last_check: float, now: Optional[float] = None, interval: float = CHECK_INTERVAL) -> bool:
    now = time.time() if now is None else now
    return not last_check or now - last_check >= interval or last_check > now
