"""Folha de estilos da aplicação (usa as cores do sistema, funciona no tema claro e escuro)."""

APP_STYLE = """
#pdfPane {
    border: 1px solid palette(mid);
    border-radius: 6px;
    background: palette(base);
}
#paneHeader {
    background: palette(window);
    border-bottom: 1px solid palette(mid);
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QScrollArea#pageScroll, QWidget#pageViewport { background: #5f6368; }
#pageImage { color: #f1f3f4; font-size: 13px; }

#dropZone {
    border: 2px dashed palette(mid);
    border-radius: 12px;
    background: palette(base);
}
#dropZone:hover { border-color: palette(highlight); }

QLabel#muted { color: gray; }

#hitBox {
    background: rgba(255, 213, 0, 70);
    border: 1px solid rgba(214, 160, 0, 140);
    border-radius: 9px;
}
QLabel#hitLabel { padding: 0 4px; background: transparent; }
QLabel#hitLabel[state="none"] { color: #c5221f; }
QLabel#hitLabel[state="found"] { font-weight: 600; }

QLabel#searchSummary[state="notfound"] { color: #c5221f; }
QLabel#searchSummary[state="found"] { font-weight: 600; }

QToolBar { spacing: 4px; padding: 2px; }
"""
