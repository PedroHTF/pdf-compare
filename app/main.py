"""Ponto de entrada: python -m app.main [arquivo1.pdf arquivo2.pdf ... | sessao.pdfcompare]"""

from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTimer, QTranslator
from PySide6.QtWidgets import QApplication

from app import __version__
from app import i18n
from app.services.workspace import SESSION_SUFFIX
from app.ui.main_window import APP_NAME, MainWindow
from app.ui.resources import app_icon
from app.ui.style import APP_STYLE


def _set_windows_app_id() -> None:
    """Faz a barra de tarefas mostrar o ícone do programa (e não o do Python)."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFCompare.App")
        except Exception:
            pass


def _choose_language() -> str:
    """Idioma salvo pelo usuário; na primeira execução, o idioma do sistema (português ou inglês)."""
    saved = QSettings().value("app/language", "")
    return i18n.set_language(str(saved) if saved else QLocale.system().name())


def _install_qt_translation(app: QApplication) -> None:
    """Botões e diálogos padrão do Qt em português ("Fechar", "Cancelar"...)."""
    if i18n.language() != i18n.PORTUGUESE:
        return
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_pt_BR", path):
        app.installTranslator(translator)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _set_windows_app_id()
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("PDFCompare")
    _choose_language()
    _install_qt_translation(app)
    app.setWindowIcon(app_icon())
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()

    files = [a for a in argv[1:] if a.lower().endswith(".pdf")]
    sessions = [a for a in argv[1:] if a.lower().endswith(SESSION_SUFFIX)]
    if sessions:  # "Abrir com" em um arquivo de sessão
        QTimer.singleShot(0, lambda: window.open_session(sessions[0]))
    elif files:  # permite "Abrir com" e arrastar arquivos sobre o .exe
        QTimer.singleShot(0, lambda: window.add_files(files))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
