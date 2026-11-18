"""Licença: arquivos presentes, janela de créditos e pacote de código-fonte."""

import zipfile

from app import __license__
from app.legal import LICENSE_TEXTS, LICENSES_DIR, components, read_license


def test_project_is_agpl():
    assert __license__ == "AGPL-3.0-or-later"


def test_all_license_texts_are_present():
    for item in LICENSE_TEXTS:
        text = read_license(item.file)
        assert len(text) > 5000, item.file
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in read_license("AGPL-3.0.txt")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in read_license("LGPL-3.0.txt")
    assert (LICENSES_DIR.parent / "LICENSE").read_text(encoding="utf-8") == read_license("AGPL-3.0.txt")


def test_components_list_includes_pymupdf_and_qt():
    comps = {c.name: c for c in components()}
    assert "AGPL" in comps["PyMuPDF"].license
    assert comps["Qt"].license == "LGPL-3.0"
    assert all(c.version for c in comps.values())


def test_license_dialog(window, qtbot):
    from app.ui.license_dialog import LicenseDialog

    dialog = LicenseDialog(window)
    qtbot.addWidget(dialog)
    assert dialog.tabs.count() == 3
    text = dialog.summary.toPlainText()
    assert "O que você pode fazer" in text and "código-fonte completo" in text
    assert dialog.table.rowCount() >= 6
    dialog._show_license_of("LGPL-3.0.txt")
    assert "LESSER" in dialog.license_view.toPlainText()
    assert dialog.tabs.currentIndex() == 2


def test_help_menu_has_license_action(window):
    assert window.act_license.isEnabled()


def test_source_zip_contains_what_is_needed_to_rebuild(tmp_path):
    from tools.make_source_zip import make_zip

    target = make_zip(tmp_path)
    with zipfile.ZipFile(target) as zf:
        names = [n.split("/", 1)[1] for n in zf.namelist()]
    for required in ("LICENSE", "build.ps1", "requirements-lock.txt", "run.py", "app/main.py",
                     "app/resources/logo.svg", "licenses/LGPL-3.0.txt", "LEIA-ME-CODIGO-FONTE.txt"):
        assert required in names, required
    assert not any(n.startswith((".venv/", "dist/", "build/")) or "__pycache__" in n for n in names)
