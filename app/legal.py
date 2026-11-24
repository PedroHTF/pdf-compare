"""Informações de licença do programa e dos componentes de terceiros."""

from __future__ import annotations

from app.i18n import tr

import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app import __url__, __version__

# Em código-fonte: raiz do projeto. No .exe (PyInstaller): pasta _internal.
BUNDLE_ROOT = Path(__file__).resolve().parent.parent
LICENSES_DIR = BUNDLE_ROOT / "licenses"
SOURCE_ZIP_NAME = f"codigo-fonte-PDFCompare-{__version__}.zip"


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    license: str
    license_file: str   # arquivo em licenses/
    owner: str
    url: str


@dataclass(frozen=True)
class LicenseText:
    title: str
    file: str


LICENSE_TEXTS = [
    LicenseText("GNU AGPL v3 (licença deste programa e do PyMuPDF/MuPDF)", "AGPL-3.0.txt"),
    LicenseText("GNU LGPL v3 (Qt / PySide6)", "LGPL-3.0.txt"),
    LicenseText("GNU GPL v3 (referenciada pela LGPL e pela AGPL)", "GPL-3.0.txt"),
    LicenseText("Python Software Foundation License (Python)", "Python-PSF.txt"),
    LicenseText("PyInstaller (GPL v2 com exceção para o carregador)", "PyInstaller.txt"),
]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def program_dir() -> Path:
    """Pasta onde o usuário encontra o programa (e o pacote de código-fonte)."""
    return Path(sys.executable).resolve().parent if is_frozen() else BUNDLE_ROOT


def source_zip_path() -> Optional[Path]:
    path = program_dir() / SOURCE_ZIP_NAME
    return path if path.exists() else None


def read_license(file_name: str) -> str:
    try:
        return (LICENSES_DIR / file_name).read_text(encoding="utf-8")
    except OSError:
        return tr("Arquivo de licença não encontrado: {name}", name=file_name)


def components() -> List[Component]:
    import fitz
    import PySide6
    from PySide6.QtCore import qVersion

    items = [
        Component("PDF Compare", __version__, "AGPL-3.0-or-later", "AGPL-3.0.txt",
                  tr("Os autores do PDF Compare"), __url__),
        Component("PyMuPDF", fitz.VersionBind, tr("AGPL-3.0 (ou licença comercial)"), "AGPL-3.0.txt",
                  "Artifex Software", "https://pymupdf.readthedocs.io"),
        Component("MuPDF", fitz.VersionFitz, tr("AGPL-3.0 (ou licença comercial)"), "AGPL-3.0.txt",
                  "Artifex Software", "https://mupdf.com"),
        Component("PySide6 (Qt for Python)", PySide6.__version__, "LGPL-3.0", "LGPL-3.0.txt",
                  "The Qt Company", "https://www.qt.io/qt-for-python"),
        Component("Qt", qVersion(), "LGPL-3.0", "LGPL-3.0.txt", "The Qt Company", "https://www.qt.io"),
        Component("Python", platform.python_version(), "PSF License", "Python-PSF.txt",
                  "Python Software Foundation", "https://www.python.org"),
    ]
    if is_frozen():
        items.append(Component(tr("PyInstaller (carregador)"), "", tr("GPL-2.0 com exceção de carregador"),
                               "PyInstaller.txt", tr("Equipe PyInstaller"), "https://pyinstaller.org"))
    return items
