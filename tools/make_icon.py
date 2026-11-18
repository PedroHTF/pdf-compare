"""Gera app/resources/app.ico (vários tamanhos) e logo_256.png a partir de logo.svg.

Uso: python tools/make_icon.py
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

RES = Path(__file__).resolve().parent.parent / "app" / "resources"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path: Path, images: dict) -> None:
    """ICO com entradas PNG (suportado desde o Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    entries, blobs = b"", b""
    offset = 6 + 16 * len(images)
    for size, blob in images.items():
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    path.write_bytes(header + entries + blobs)


def main() -> int:
    QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(RES / "logo.svg"))
    if not renderer.isValid():
        print("logo.svg inválido")
        return 1
    images = {size: png_bytes(render(renderer, size)) for size in SIZES}
    write_ico(RES / "app.ico", images)
    (RES / "logo_256.png").write_bytes(images[256])
    print(f"Gerado: {RES / 'app.ico'} ({len(SIZES)} tamanhos) e logo_256.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
