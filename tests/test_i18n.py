"""Idioma da interface: inglês e português."""

import ast
import string
from pathlib import Path

import pytest

from app import i18n
from app.i18n_en import EN

APP = Path(__file__).resolve().parent.parent / "app"


def _source_keys():
    """Todos os textos literais passados a tr() / _plural() / plural() no código."""
    keys = set()
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "_plural", "plural"):
                args = node.args[:1] if node.func.id == "tr" else node.args[1:]
                keys |= {a.value for a in args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    from app.legal import LICENSE_TEXTS

    keys |= {t.title for t in LICENSE_TEXTS}   # traduzidos na hora de exibir
    return keys


def _fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_text_has_english_translation():
    missing = sorted(_source_keys() - set(EN))
    assert missing == [], f"Sem tradução em app/i18n_en.py: {missing}"


def test_translations_keep_the_same_fields():
    for pt, en in EN.items():
        assert _fields(pt) == _fields(en), pt


def test_no_unused_translations():
    assert sorted(set(EN) - _source_keys()) == []


def test_tr_and_plural():
    i18n.set_language("en")
    assert i18n.tr("Abrir") == "Open"
    assert i18n.tr("Sessão salva em “{name}”.", name="x") == "Session saved to “x”."
    assert i18n.plural(2, "{n} PDF", "{n} PDFs") == "2 PDFs"
    assert i18n.tr("texto sem tradução") == "texto sem tradução"
    i18n.set_language("pt")
    assert i18n.tr("Abrir") == "Abrir"
    assert i18n.tr("Sessão salva em “{name}”.", name="x") == "Sessão salva em “x”."


@pytest.mark.parametrize("code,expected", [("pt_BR", "pt"), ("pt-PT", "pt"), ("PT", "pt"),
                                           ("en_US", "en"), ("de_DE", "en"), ("", "en"), (None, "en")])
def test_normalize(code, expected):
    assert i18n.normalize(code) == expected


def test_window_in_english(qtbot, tmp_path, make_pdf):
    from PySide6.QtCore import QSettings

    from app.ui.main_window import MainWindow

    i18n.set_language("en")
    w = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat), data_dir=tmp_path)
    qtbot.addWidget(w)
    w._notify = lambda *a: None
    menus = [a.text() for a in w.menuBar().actions()]
    assert menus == ["&File", "&Edit", "&Navigate", "&View", "&Tools", "&Help"]
    assert w.act_export.text() == "&Export…" and w.act_diff.text() == "Compare &text"
    assert "Open or drag" in w.hint_label.text()
    w.add_files([make_pdf("a.pdf", texts=["x"]), make_pdf("b.pdf", texts=["y"])])
    assert w.panes[0].btn_close.toolTip() == "Close this PDF"
    pt_words = ("ção", "ões", "Página", "Abrir", "Pesquis", "Próxim")
    texts = [a.text() + " " + a.toolTip() for a in w.findChildren(type(w.act_export))]
    assert not [t for t in texts if any(word in t for word in pt_words)]


def test_window_in_portuguese_by_default(window):
    assert window.act_export.text() == "&Exportar…"


def test_language_menu_saves_choice_and_asks_restart(window):
    labels = [a.text() for a in window.language_menu.actions()]
    assert labels == ["English", "Português"]
    window.set_ui_language("en")
    assert window.settings.value("app/language") == "en"
    assert window.notifications[-1][2] == "Restart the program to use the new language."
    assert [a.isChecked() for a in window.language_menu.actions()] == [True, False]


def test_export_labels_follow_language(make_pdf, tmp_path):
    import fitz

    from app.services.export import PDF, Column, export_comparison

    i18n.set_language("en")
    doc = fitz.open(str(make_pdf("a.pdf", 1)))
    out = export_comparison([Column(doc, "a.pdf")], [[0]], tmp_path / "c.pdf", PDF)[0]
    doc.close()
    assert "a.pdf · page 1" in fitz.open(str(out))[0].get_text()


def test_license_summary_in_both_languages():
    from app.ui.license_dialog import summary_html

    assert "O que você pode fazer" in summary_html()
    i18n.set_language("en")
    assert "What you can do" in summary_html()
