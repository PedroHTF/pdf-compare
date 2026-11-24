"""Preferências do usuário que a janela de Configurações altera.

Funciona com qualquer objeto com value()/setValue() (QSettings nos programas,
um dicionário simples nos testes). As cores são guardadas como "#rrggbb".
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from app.services.annotations import HIGHLIGHT_COLOR, SHAPE_COLOR, Color
from app.services.diff_batches import DEFAULT_BATCH_SIZE, DEFAULT_RETENTION_DAYS
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

NEXT_ON_CLICK = "click"     # o próximo lote só é comparado quando o usuário pede
NEXT_AUTO = "auto"          # os próximos lotes são comparados em segundo plano
LOOKAHEAD_ALL = 0


@dataclass(frozen=True)
class CompareSettings:
    """Comparação em lotes e cache dos resultados."""

    batch_size: int = DEFAULT_BATCH_SIZE    # páginas por lote; 0 = tudo de uma vez
    next_mode: str = NEXT_ON_CLICK
    lookahead: int = 1                      # lotes adiantados no modo automático; 0 = todos
    pause_while_busy: bool = True           # segundo plano espera o usuário parar de rolar/anotar
    cache_days: int = DEFAULT_RETENTION_DAYS    # 0 = nunca apagar


DEFAULT_COMPARE = CompareSettings()


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

    # --- comparação em lotes -------------------------------------------------------
    def _int(self, key: str, default: int, low: int, high: int) -> int:
        try:
            value = int(float(self.settings.value(key, default)))
        except (TypeError, ValueError):
            return default
        return min(max(value, low), high)

    def compare_settings(self) -> CompareSettings:
        d = DEFAULT_COMPARE
        mode = str(self.settings.value("compare/next_mode", d.next_mode))
        pause = self.settings.value("compare/pause_while_busy", d.pause_while_busy)
        if isinstance(pause, str):
            pause = pause.lower() in ("true", "1", "yes")
        return CompareSettings(
            batch_size=self._int("compare/batch_size", d.batch_size, 0, 100000),
            next_mode=mode if mode in (NEXT_ON_CLICK, NEXT_AUTO) else d.next_mode,
            lookahead=self._int("compare/lookahead", d.lookahead, 0, 1000),
            pause_while_busy=bool(pause),
            cache_days=self._int("compare/cache_days", d.cache_days, 0, 3650),
        )

    def set_compare_settings(self, c: CompareSettings) -> None:
        self.settings.setValue("compare/batch_size", c.batch_size)
        self.settings.setValue("compare/next_mode", c.next_mode)
        self.settings.setValue("compare/lookahead", c.lookahead)
        self.settings.setValue("compare/pause_while_busy", c.pause_while_busy)
        self.settings.setValue("compare/cache_days", c.cache_days)

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
