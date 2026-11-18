"""Acesso aos arquivos de app/resources (funciona no código-fonte e no .exe do PyInstaller)."""

from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap

RESOURCES = Path(__file__).resolve().parent.parent / "resources"


def app_icon() -> QIcon:
    return QIcon(str(RESOURCES / "app.ico"))


def logo_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(str(RESOURCES / "logo_256.png"))
    if pixmap.isNull():
        return pixmap
    from PySide6.QtCore import Qt

    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
