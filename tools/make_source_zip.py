"""Gera o pacote de código-fonte que acompanha o executável (exigência da AGPL).

Uso: python tools/make_source_zip.py [pasta_de_saida]   (padrão: dist/PDFCompare)

Inclui tudo o que é preciso para reconstruir o programa: código, testes, ícones,
scripts de build, versões exatas das dependências e textos das licenças.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.legal import SOURCE_ZIP_NAME  # noqa: E402

INCLUDE_FILES = [
    "LICENSE", "README.md", "run.py", "build.ps1",
    "requirements.txt", "requirements-dev.txt", "requirements-lock.txt", ".gitignore",
]
INCLUDE_DIRS = ["app", "tests", "tools", "licenses", "samples"]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

SOURCE_README = """PDF Compare - código-fonte
==========================

Este arquivo contém o código-fonte completo do PDF Compare, distribuído sob a
GNU Affero General Public License v3 ou posterior (arquivo LICENSE).
Repositório público: https://github.com/PedroHTF/pdf-compare

Como reconstruir o executável no Windows:

  1. Instale o Python 3.9 ou mais recente (64 bits).
  2. Na pasta extraída:
       python -m venv .venv
       .venv\\Scripts\\activate
       pip install -r requirements-lock.txt
  3. Gere o executável:
       powershell -ExecutionPolicy Bypass -File build.ps1

As bibliotecas de terceiros são usadas sem modificação, nas versões exatas
listadas em requirements-lock.txt. Os códigos-fonte delas estão disponíveis em:
  - PyMuPDF / MuPDF (AGPL-3.0): https://github.com/pymupdf/PyMuPDF  e  https://mupdf.com
  - PySide6 / Qt (LGPL-3.0):    https://code.qt.io  e  https://download.qt.io/official_releases/QtForPython/
  - Python (PSF):               https://www.python.org/downloads/source/
"""


def collect(root: Path) -> List[Path]:
    files: List[Path] = []
    for name in INCLUDE_FILES:
        path = root / name
        if path.is_file():
            files.append(path)
    for folder in INCLUDE_DIRS:
        for path in sorted((root / folder).rglob("*")):
            if not path.is_file():
                continue
            if EXCLUDE_PARTS.intersection(path.relative_to(root).parts) or path.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(path)
    return files


def make_zip(out_dir: Path, root: Path = ROOT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / SOURCE_ZIP_NAME
    prefix = target.stem
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in collect(root):
            zf.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")
        zf.writestr(f"{prefix}/LEIA-ME-CODIGO-FONTE.txt", SOURCE_README)
    return target


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    out_dir = Path(args[0]) if args else ROOT / "dist" / "PDFCompare"
    target = make_zip(out_dir)
    print(f"Gerado: {target} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
