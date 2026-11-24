"""Preferências do usuário que a janela de Configurações altera.

Funciona com qualquer objeto com value()/setValue() (QSettings nos programas,
um dicionário simples nos testes). As cores são guardadas como "#rrggbb".
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from app.services.annotations import HIGHLIGHT_COLOR, SHAPE_COLOR, Color
from app.services.text_diff import ADDED, CHANGED, REMOVED

DEFAULT_DIFF_COLORS: Dict[str, Color] = {
    ADDED: (52 / 255, 168 / 255, 83 / 255),     # verde
    REMOVED: (234 / 255, 67 / 255, 53 / 255),   # vermelho
    CHANGED: (66 / 255, 133 / 255, 244 / 255),  # azul
}


def to_hex(color: Color) -> str:
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02x}" for c in color)


def from_hex(text, default: Optional[Color] = None) -> Optional[Color]:
    text = str(text or "").strip().lstrip("#")
    if len(text) != 6:
        return default
    try:
        return tuple(int(text[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return default


@dataclass(frozen=True)
class MarkStyle:
    """Estilo usado nas novas marcações (e editável na marcação selecionada)."""

    color: Color = SHAPE_COLOR
    highlight: Color = HIGHLIGHT_COLOR
    fill: Optional[Color] = None
    width: float = 1.5
    opacity: float = 1.0
    font_size: float = 11.0


DEFAULT_STYLE = MarkStyle()


class Preferences:
    def __init__(self, settings) -> None:
        self.settings = settings

    # --- cores da comparação ---------------------------------------------------------
    def diff_colors(self) -> Dict[str, Color]:
        return {kind: from_hex(self.settings.value(f"colors/{kind}", ""), default) or default
                for kind, default in DEFAULT_DIFF_COLORS.items()}

    def set_diff_colors(self, colors: Dict[str, Color]) -> None:
        for kind, color in colors.items():
            if kind in DEFAULT_DIFF_COLORS:
                self.settings.setValue(f"colors/{kind}", to_hex(color))

    # --- estilo das marcações -------------------------------------------------------
    def _float(self, key: str, default: float, low: float, high: float) -> float:
        try:
            value = float(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default
        return min(max(value, low), high)

    def mark_style(self) -> MarkStyle:
        d = DEFAULT_STYLE
        fill_raw = str(self.settings.value("marks/fill", "") or "")
        return MarkStyle(
            color=from_hex(self.settings.value("marks/color", ""), d.color) or d.color,
            highlight=from_hex(self.settings.value("marks/highlight", ""), d.highlight) or d.highlight,
            fill=from_hex(fill_raw) if fill_raw else None,
            width=self._float("marks/width", d.width, 0.0, 20.0),
            opacity=self._float("marks/opacity", d.opacity, 0.05, 1.0),
            font_size=self._float("marks/font_size", d.font_size, 4.0, 96.0),
        )

    def set_mark_style(self, style: MarkStyle) -> None:
        self.settings.setValue("marks/color", to_hex(style.color))
        self.settings.setValue("marks/highlight", to_hex(style.highlight))
        self.settings.setValue("marks/fill", to_hex(style.fill) if style.fill else "")
        self.settings.setValue("marks/width", style.width)
        self.settings.setValue("marks/opacity", style.opacity)
        self.settings.setValue("marks/font_size", style.font_size)


def with_values(style: MarkStyle, **changes) -> MarkStyle:
    return replace(style, **changes)


def rgb255(color: Color) -> Tuple[int, int, int]:
    return tuple(round(c * 255) for c in color)
