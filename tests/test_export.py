"""Exportação da comparação e das páginas atuais."""

import fitz
import pytest

from app.services.annotations import HIGHLIGHT, Annotation
from app.services.export import (
    PDF,
    PNG,
    Column,
    ExportError,
    export_comparison,
    export_current_pages,
    numbered_paths,
    safe_stem,
)


@pytest.fixture
def columns(make_pdf):
    docs = [fitz.open(str(make_pdf("a.pdf", texts=["alfa um", "alfa dois"]))),
            fitz.open(str(make_pdf("b.pdf", texts=["beta um"])))]
    yield [Column(docs[0], "a.pdf"), Column(docs[1], "b.pdf")]
    for d in docs:
        d.close()


def test_side_by_side_pdf_keeps_text_and_labels(columns, tmp_path):
    out = tmp_path / "comp.pdf"
    assert export_comparison(columns, [[0, 0], [1, None]], out, PDF) == [out]
    doc = fitz.open(str(out))
    assert doc.page_count == 2
    first = doc[0].get_text()
    assert "alfa um" in first and "beta um" in first and "a.pdf · página 1" in first
    assert "sem página nesta posição" in doc[1].get_text()
    assert doc[0].rect.width > 2 * columns[0].doc[0].rect.width
    doc.close()


def test_side_by_side_png_one_image_per_position(columns, tmp_path):
    files = export_comparison(columns, [[0, 0], [1, None]], tmp_path / "comp.png", PNG, dpi=40)
    assert [f.name for f in files] == ["comp_001.png", "comp_002.png"]
    pix = fitz.Pixmap(str(files[0]))
    assert pix.width > pix.height
    single = export_comparison(columns, [[0, 0]], tmp_path / "um.png", PNG, dpi=40)
    assert [f.name for f in single] == ["um.png"]


def test_export_with_annotations_bakes_highlight(columns, tmp_path):
    word = columns[0].doc[0].get_text("words")[0]
    columns[0].annotations = [Annotation(HIGHLIGHT, 0, [tuple(word[:4])])]
    plain = export_comparison([Column(columns[0].doc, "a.pdf")], [[0]], tmp_path / "s.png", PNG, dpi=40)[0]
    marked = export_comparison(columns[:1], [[0]], tmp_path / "c.png", PNG, dpi=40)[0]
    assert plain.read_bytes() != marked.read_bytes()
    assert not list(columns[0].doc[0].annots())   # original intocado


def test_current_pages_one_file_per_pdf(columns, tmp_path):
    files = export_current_pages(columns, [1, None], tmp_path / "saida", PDF)
    assert [f.name for f in files] == ["a_p2.pdf"]
    doc = fitz.open(str(files[0]))
    assert doc.page_count == 1 and "alfa dois" in doc[0].get_text()
    doc.close()
    pngs = export_current_pages(columns, [0, 0], tmp_path / "png", PNG, dpi=40)
    assert sorted(f.name for f in pngs) == ["a_p1.png", "b_p1.png"]


def test_same_names_do_not_overwrite(columns, tmp_path):
    cols = [columns[0], Column(columns[0].doc, "a.pdf")]
    files = export_current_pages(cols, [0, 0], tmp_path, PDF)
    assert sorted(f.name for f in files) == ["a_p1.pdf", "a_p1_2.pdf"]


def test_helpers():
    from pathlib import Path

    assert numbered_paths(Path("x.png"), 2) == [Path("x_001.png"), Path("x_002.png")]
    assert safe_stem('con:tra*to?.pdf') == "con_tra_to_"
    assert safe_stem(".pdf") == "documento" or safe_stem(".pdf")


def test_errors(columns, tmp_path):
    with pytest.raises(ExportError):
        export_comparison([], [[]], tmp_path / "x.pdf", PDF)
    with pytest.raises(ExportError):
        export_comparison(columns, [[0, 0]], tmp_path / "x.gif", "gif")
    blocker = tmp_path / "arquivo"
    blocker.write_text("x")
    with pytest.raises(ExportError):
        export_comparison(columns, [[0, 0]], blocker / "sub" / "x.pdf", PDF)
