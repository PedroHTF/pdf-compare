import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # testes de interface sem abrir janelas

from pathlib import Path  # noqa: E402
from typing import List, Optional  # noqa: E402

import fitz  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture
def make_pdf(tmp_path: Path):
    """Cria um PDF e devolve o caminho.

    make_pdf("a.pdf", 3)                      -> 3 páginas com texto padrão
    make_pdf("a.pdf", texts=["p1", "p2"])     -> uma página por texto
    """

    def _make(
        name: str,
        pages: Optional[int] = None,
        texts: Optional[List[str]] = None,
        user_pw: Optional[str] = None,
        owner_pw: Optional[str] = None,
    ) -> Path:
        if texts is None:
            texts = [f"{name} pagina {i + 1}" for i in range(pages or 1)]
        path = tmp_path / name
        doc = fitz.open()
        for text in texts:
            page = doc.new_page()
            page.insert_text((72, 72), text, fontsize=12)
        if user_pw is not None or owner_pw is not None:
            doc.save(
                str(path),
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=user_pw or "",
                owner_pw=owner_pw or user_pw or "",
                permissions=fitz.PDF_PERM_ACCESSIBILITY,
            )
        else:
            doc.save(str(path))
        doc.close()
        return path

    return _make


@pytest.fixture
def window(qtbot, tmp_path):
    """Janela principal isolada: preferências em arquivo temporário e avisos capturados."""
    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings=settings, data_dir=tmp_path / "dados")
    w.notifications = []
    w._notify = lambda kind, title, text: w.notifications.append((kind, title, text))
    qtbot.addWidget(w)
    w.resize(1200, 800)
    w.show()
    return w


@pytest.fixture(autouse=True)
def _portuguese_ui():
    """Os testes conferem textos em português; os de inglês trocam o idioma explicitamente."""
    from app import i18n

    i18n.set_language("pt")
    yield
    i18n.set_language("pt")
