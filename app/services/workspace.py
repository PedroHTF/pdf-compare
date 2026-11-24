"""Pastas, arquivos recentes e sessões salvas (sem dependência de interface).

Sessão (.pdfcompare) = arquivo JSON com os PDFs, o deslocamento de cada um,
a posição atual e o zoom. Os caminhos são gravados absolutos e também relativos
à pasta da sessão, para continuar funcionando se a pasta inteira for movida.
Senhas nunca são gravadas.
"""

from __future__ import annotations

from app.i18n import tr

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

SESSION_SUFFIX = ".pdfcompare"
SESSION_VERSION = 1
MAX_RECENT = 10

Zoom = Union[str, float]


class SessionError(Exception):
    """Arquivo de sessão inválido ou ilegível."""


def _natural_key(path: Path) -> List:
    """Ordem natural: "v2" antes de "v10"."""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def pdfs_in_folder(folder: Path | str) -> List[Path]:
    """PDFs da pasta (sem subpastas), em ordem natural de nome."""
    folder = Path(folder)
    try:
        entries = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    except OSError:
        return []
    return sorted(entries, key=_natural_key)


# --- recentes -----------------------------------------------------------------
def add_recent(recent: Sequence[str], path: Path | str, limit: int = MAX_RECENT) -> List[str]:
    """Coloca o caminho no topo da lista (sem repetir; Windows não diferencia maiúsculas)."""
    path = str(Path(path))
    key = os.path.normcase(path)
    items = [p for p in recent if os.path.normcase(p) != key]
    return [path, *items][:limit]


def existing_recent(recent: Sequence[str]) -> List[str]:
    return [p for p in recent if Path(p).exists()]


# --- sessões ------------------------------------------------------------------
@dataclass
class SessionFile:
    path: Path
    offset: int = 0


@dataclass
class SessionData:
    files: List[SessionFile] = field(default_factory=list)
    current: int = 0
    zoom: Optional[Zoom] = None


def _relative(target: Path, base: Path) -> Optional[str]:
    try:
        return os.path.relpath(target, base)
    except ValueError:   # outro disco no Windows
        return None


def save_session(path: Path | str, data: SessionData) -> Path:
    path = Path(path)
    if path.suffix.lower() != SESSION_SUFFIX:
        path = path.with_name(path.name + SESSION_SUFFIX)
    base = path.parent.resolve()
    payload = {
        "app": "PDF Compare",
        "version": SESSION_VERSION,
        "current": data.current,
        "zoom": data.zoom,
        "files": [
            {"path": str(Path(f.path).resolve()), "relative": _relative(Path(f.path).resolve(), base),
             "offset": f.offset}
            for f in data.files
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise SessionError(tr("Não foi possível salvar a sessão: {error}", error=exc.strerror or exc)) from exc
    return path


def load_session(path: Path | str) -> Tuple[SessionData, List[str]]:
    """Lê a sessão. Devolve os dados e a lista de PDFs que não foram encontrados."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SessionError(tr("Não foi possível ler “{name}”: {error}", name=path.name, error=exc.strerror or exc)) from exc
    except ValueError as exc:
        raise SessionError(tr("“{name}” não é um arquivo de sessão válido.", name=path.name)) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("files"), list):
        raise SessionError(tr("“{name}” não é um arquivo de sessão válido.", name=path.name))
    if int(raw.get("version", 1)) > SESSION_VERSION:
        raise SessionError(tr("“{name}” foi criado por uma versão mais nova do programa.", name=path.name))

    base = path.parent
    files: List[SessionFile] = []
    missing: List[str] = []
    for item in raw["files"]:
        if not isinstance(item, dict) or "path" not in item:
            continue
        candidates = [Path(item["path"])]
        if item.get("relative"):
            candidates.append(base / item["relative"])
        found = next((c for c in candidates if c.exists()), None)
        if found is None:
            missing.append(Path(item["path"]).name)
            continue
        try:
            offset = int(item.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0
        files.append(SessionFile(found, offset))

    zoom = raw.get("zoom")
    if not isinstance(zoom, (str, int, float)) or isinstance(zoom, bool):
        zoom = None
    try:
        current = int(raw.get("current", 0))
    except (TypeError, ValueError):
        current = 0
    return SessionData(files=files, current=current, zoom=zoom), missing
