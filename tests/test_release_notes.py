"""Texto da Release montado a partir do CHANGELOG.md (tools/release_notes.py)."""

from tools.release_notes import CHANGELOG, TEMPLATE, build_notes, main, subsection, version_section

from app import __version__

CHANGELOG_SAMPLE = """# Novidades

## [1.1.0] — 2027

### Resumo

- Coisa nova

### Summary

- New thing

### Português

Detalhes longos.

## [1.0.0]

Primeira versão.
"""


def test_sections():
    section = version_section(CHANGELOG_SAMPLE, "1.1.0")
    assert section.startswith("### Resumo") and "Primeira versão" not in section
    assert subsection(section, "Resumo") == "- Coisa nova"
    assert subsection(section, "Summary") == "- New thing"
    assert version_section(CHANGELOG_SAMPLE, "1.0.0") == "Primeira versão."
    assert version_section(CHANGELOG_SAMPLE, "9.9.9") == ""


def test_build_notes_fills_template():
    template = "Baixe PDFCompare-Setup-{version}.exe\n{resumo}\n---\n{summary}\n"
    notes = build_notes("1.1.0", CHANGELOG_SAMPLE, template)
    assert notes == "Baixe PDFCompare-Setup-1.1.0.exe\n- Coisa nova\n---\n- New thing\n"
    # sem resumo: usa a seção inteira; sem seção: um traço
    assert "Primeira versão." in build_notes("1.0.0", CHANGELOG_SAMPLE, template)
    assert "—" in build_notes("2.0.0", CHANGELOG_SAMPLE, template)


def test_real_changelog_has_summaries_for_current_version(tmp_path):
    section = version_section(CHANGELOG.read_text(encoding="utf-8"), __version__)
    assert subsection(section, "Resumo") and subsection(section, "Summary")
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "{resumo}" in template and "{summary}" in template
    out = tmp_path / "notes" / "RELEASE.md"
    assert main(["release_notes", f"v{__version__}", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert f"PDFCompare-Setup-{__version__}.exe" in text and "{" not in text
    assert "## O que mudou" in text and "## What's new" in text and "Marcações completas" in text


def test_runs_on_a_windows_console_encoding(tmp_path, monkeypatch):
    import io
    import sys

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    assert main(["release_notes", __version__, str(tmp_path / "n.md")]) == 0
    assert "☕".encode("utf-8") in raw.getvalue()
