"""Diferença visual (pixel a pixel) entre duas páginas.

Encontra o que mudou na aparência, inclusive o que não é texto: imagens,
assinaturas, carimbos, tabelas desenhadas e páginas escaneadas sem OCR.

1. As duas páginas são renderizadas em tons de cinza, no mesmo tamanho.
2. O Qt calcula a diferença absoluta entre as imagens (modo de composição
   "Difference") e reduz o resultado a uma grade de células, tirando a média
   de cada célula.
3. Células acima do limite (definido pela sensibilidade) são agrupadas em
   áreas vizinhas, devolvidas como retângulos nas coordenadas de cada página.

Usa só o PyMuPDF e o Qt (sem dependências extras).
"""

from __future__ import annotations

import math
from typing import List, Tuple

import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

Rect = Tuple[float, float, float, float]

VISUAL = "visual"        # tipo de marca da diferença visual
RENDER_SCALE = 1.5       # ~108 dpi: detalhe suficiente e rápido
CELL = 8                 # pixels por célula da grade
DEFAULT_SENSITIVITY = 50


def threshold_for(sensitivity: int) -> float:
    """Diferença média (0–255) que uma célula precisa ter: mais sensível = limite menor."""
    sensitivity = max(1, min(int(sensitivity), 100))
    return 48 - 0.44 * sensitivity


def _gray(page: fitz.Page, width: int, height: int) -> QImage:
    rect = page.rect
    matrix = fitz.Matrix(width / rect.width, height / rect.height)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_Grayscale8).copy()
    if image.width() != width or image.height() != height:
        image = image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    return image


def difference_grid(page_a: fitz.Page, page_b: fitz.Page, scale: float = RENDER_SCALE,
                    cell: int = CELL) -> Tuple[List[List[int]], int, int]:
    """Grade com a diferença média de cada célula; também a largura e altura renderizadas."""
    width = max(int(round(page_a.rect.width * scale)), 1)
    height = max(int(round(page_a.rect.height * scale)), 1)
    a = _gray(page_a, width, height).convertToFormat(QImage.Format.Format_RGB32)
    b = _gray(page_b, width, height).convertToFormat(QImage.Format.Format_RGB32)
    painter = QPainter(a)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
    painter.drawImage(0, 0, b)
    painter.end()
    cols, rows = math.ceil(width / cell), math.ceil(height / cell)
    small = a.convertToFormat(QImage.Format.Format_Grayscale8).scaled(
        cols, rows, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    data = bytes(small.constBits())
    stride = small.bytesPerLine()
    grid = [list(data[r * stride: r * stride + cols]) for r in range(rows)]
    return grid, width, height


def _regions(marked: List[List[bool]]) -> List[Tuple[int, int, int, int]]:
    """Agrupa células marcadas vizinhas (inclusive a uma célula de distância) em retângulos."""
    rows = len(marked)
    cols = len(marked[0]) if rows else 0
    seen = [[False] * cols for _ in range(rows)]
    boxes = []
    for r in range(rows):
        for c in range(cols):
            if not marked[r][c] or seen[r][c]:
                continue
            stack = [(r, c)]
            seen[r][c] = True
            r0, c0, r1, c1 = r, c, r, c
            while stack:
                y, x = stack.pop()
                r0, c0, r1, c1 = min(r0, y), min(c0, x), max(r1, y), max(c1, x)
                for dy in (-2, -1, 0, 1, 2):
                    for dx in (-2, -1, 0, 1, 2):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < rows and 0 <= nx < cols and marked[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((ny, nx))
            boxes.append((c0, r0, c1 + 1, r1 + 1))
    return boxes


def page_difference(page_a: fitz.Page, page_b: fitz.Page,
                    sensitivity: int = DEFAULT_SENSITIVITY) -> Tuple[List[Rect], List[Rect]]:
    """Áreas diferentes: (retângulos na página a, retângulos na página b), sem rotação."""
    grid, width, height = difference_grid(page_a, page_b)
    limit = threshold_for(sensitivity)
    marked = [[value > limit for value in row] for row in grid]
    out_a: List[Rect] = []
    out_b: List[Rect] = []
    for c0, r0, c1, r1 in _regions(marked):
        x0, y0 = c0 * CELL / width, r0 * CELL / height          # frações da página
        x1, y1 = min(c1 * CELL / width, 1.0), min(r1 * CELL / height, 1.0)
        for page, out in ((page_a, out_a), (page_b, out_b)):
            r = page.rect
            box = fitz.Rect(x0 * r.width, y0 * r.height, x1 * r.width, y1 * r.height) * page.derotation_matrix
            box.normalize()
            out.append((box.x0, box.y0, box.x1, box.y1))
    return out_a, out_b
