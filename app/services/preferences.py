"""Preferências do usuário que a janela de Configurações altera.

Funciona com qualquer objeto com value()/setValue() (QSettings nos programas,
um dicionário simples nos testes). As cores são guardadas como "#rrggbb".
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from app.services.annotations import HIGHLIGHT_COLOR, SHAPE_COLOR, Color
from app.services.compare_scope import MAX_ZONE, CompareScope
from app.services.diff_batches import DEFAULT_BATCH_SIZE, DEFAULT_RETENTION_DAYS
from app.services.text_diff import ADDED, CHANGED, REMOVED
from app.services.visual_diff import DEFAULT_SENSITIVITY, VISUAL

DEFAULT_DIFF_COLORS: Dict[str, Color] = {
    ADDED: (52 / 255, 168 / 255, 83 / 255),     # verde
    REMOVED: (234 / 255, 67 / 255, 53 / 255),   # vermelho
    CHANGED: (66 / 255, 133 / 255, 244 / 255),  # azul
    VISUAL: (200 / 255, 40 / 255, 200 / 255),   # magenta
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
REALIGN_ON_CLICK = "click"   # alinhamento mudou: mostra "Recomparar" e espera o clique
REALIGN_AUTO = "auto"        # alinhamento mudou: recompara sozinho (depois de uma pausa)


@dataclass(frozen=True)
class CompareSettings:
    """Comparação em lotes e cache dos resultados."""

    batch_size: int = DEFAULT_BATCH_SIZE    # páginas por lote; 0 = tudo de uma vez
    next_mode: str = NEXT_ON_CLICK
    lookahead: int = 1                      # lotes adiantados no modo automático; 0 = todos
    pause_while_busy: bool = True           # segundo plano espera o usuário parar de rolar/anotar
    cache_days: int = DEFAULT_RETENTION_DAYS    # 0 = nunca apagar
    realign_mode: str = REALIGN_ON_CLICK
    visual_sensitivity: int = DEFAULT_SENSITIVITY   # diferença visual: 1 (pouco) a 100 (muito sensível)
    header: float = 0.0                     # % da altura ignorada no topo de cada página (0 = não ignorar)
    footer: float = 0.0                     # % ignorada na base de cada página
    auto_bands: bool = True                 # detectar cabeçalho e rodapé ao abrir os PDFs (até 40%)
    sides: bool = False                     # faixas laterais (esquerda / direita) habilitadas
    left: float = 0.0                       # % da largura ignorada à esquerda
    right: float = 0.0                      # % ignorada à direita
    follow_alignment: bool = True           # a comparação segue os trechos/páginas alinhados à mão
    page_only: bool = False                 # comparar só a página atual (em vez do documento inteiro)

    @property
    def scope(self) -> CompareScope:
        if self.sides:
            return CompareScope(self.header, self.footer, self.left, self.right)
        return CompareScope(self.header, self.footer)


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
        pause = self._bool("compare/pause_while_busy", d.pause_while_busy)
        realign = str(self.settings.value("compare/realign_mode", d.realign_mode))
        return CompareSettings(
            visual_sensitivity=self._int("compare/visual_sensitivity", d.visual_sensitivity, 1, 100),
            realign_mode=realign if realign in (REALIGN_ON_CLICK, REALIGN_AUTO) else d.realign_mode,
            batch_size=self._int("compare/batch_size", d.batch_size, 0, 100000),
            next_mode=mode if mode in (NEXT_ON_CLICK, NEXT_AUTO) else d.next_mode,
            lookahead=self._int("compare/lookahead", d.lookahead, 0, 1000),
            pause_while_busy=bool(pause),
            cache_days=self._int("compare/cache_days", d.cache_days, 0, 3650),
            header=self._float("compare/header", d.header, 0, MAX_ZONE),
            footer=self._float("compare/footer", d.footer, 0, MAX_ZONE),
            auto_bands=self._bool("compare/auto_bands", d.auto_bands),
            sides=self._bool("compare/sides", d.sides),
            left=self._float("compare/left", d.left, 0, MAX_ZONE),
            right=self._float("compare/right", d.right, 0, MAX_ZONE),
            follow_alignment=self._bool("compare/follow_alignment", d.follow_alignment),
            page_only=self._bool("compare/page_only", d.page_only),
        )

    def _float(self, key: str, default: float, low: float, high: float) -> float:
        try:
            value = float(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default
        return round(min(max(value, low), high), 1)

    def _bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    def set_compare_settings(self, c: CompareSettings) -> None:
        self.settings.setValue("compare/batch_size", c.batch_size)
        self.settings.setValue("compare/next_mode", c.next_mode)
        self.settings.setValue("compare/lookahead", c.lookahead)
        self.settings.setValue("compare/pause_while_busy", c.pause_while_busy)
        self.settings.setValue("compare/cache_days", c.cache_days)
        self.settings.setValue("compare/realign_mode", c.realign_mode)
        self.settings.setValue("compare/visual_sensitivity", c.visual_sensitivity)
        self.settings.setValue("compare/header", c.header)
        self.settings.setValue("compare/footer", c.footer)
        self.settings.setValue("compare/auto_bands", c.auto_bands)
        self.settings.setValue("compare/sides", c.sides)
        self.settings.setValue("compare/left", c.left)
        self.settings.setValue("compare/right", c.right)
        self.settings.setValue("compare/follow_alignment", c.follow_alignment)
        self.settings.setValue("compare/page_only", c.page_only)

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
