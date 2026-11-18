"""Anotações guardadas fora do PDF."""

import json

import fitz
import pytest

from app.services.annotations import (
    HIGHLIGHT,
    NOTE,
    Annotation,
    AnnotationStore,
    annotated_copy,
    file_fingerprint,
    find_at,
    for_page,
    note_rect,
    save_annotated_pdf,
    words_in_rect,
)


@pytest.fixture
def store(tmp_path):
    return AnnotationStore(tmp_path / "anotacoes")


def test_store_roundtrip_and_original_untouched(store, make_pdf, tmp_path):
    pdf = make_pdf("a.pdf", texts=["texto"])
    before = pdf.read_bytes()
    key = file_fingerprint(pdf)
    store.add(key, Annotation(HIGHLIGHT, 0, [(10, 10, 50, 20)], "importante"), "a.pdf")
    store.add(key, Annotation(NOTE, 0, [note_rect(100, 100)], "revisar"), "a.pdf")

    fresh = AnnotationStore(tmp_path / "anotacoes")
    items = fresh.load(key)
    assert [(a.kind, a.text) for a in items] == [(HIGHLIGHT, "importante"), (NOTE, "revisar")]
    assert pdf.read_bytes() == before


def test_fingerprint_follows_content_not_name(make_pdf, tmp_path):
    pdf = make_pdf("a.pdf", texts=["igual"])
    copy = tmp_path / "renomeado.pdf"
    copy.write_bytes(pdf.read_bytes())
    assert file_fingerprint(pdf) == file_fingerprint(copy)
    other = make_pdf("b.pdf", texts=["diferente"])
    assert file_fingerprint(other) != file_fingerprint(pdf)


def test_remove_update_and_empty_store_deletes_file(store):
    a = Annotation(NOTE, 2, [note_rect(0, 0)], "x")
    store.add("k", a)
    assert store.update_text("k", a.id, "novo")
    assert AnnotationStore(store.folder).load("k")[0].text == "novo"
    assert store.remove("k", a.id)
    assert not (store.folder / "k.json").exists()
    assert not store.remove("k", "inexistente")


def test_corrupted_file_is_ignored(store):
    store.folder.mkdir(parents=True)
    (store.folder / "k.json").write_text("{ isto não é json", encoding="utf-8")
    assert store.load("k") == []


def test_invalid_entry_is_skipped(store):
    store.folder.mkdir(parents=True)
    data = {"annotations": [{"kind": "x", "page": 0, "rects": [[0, 0, 1, 1]]},
                            {"kind": "note", "page": 1, "rects": [[0, 0, 1, 1]], "text": "ok"}]}
    (store.folder / "k.json").write_text(json.dumps(data), encoding="utf-8")
    assert [a.text for a in store.load("k")] == ["ok"]


def test_find_and_filter_by_page():
    a = Annotation(HIGHLIGHT, 0, [(10, 10, 50, 20)])
    b = Annotation(NOTE, 1, [note_rect(5, 5)])
    assert for_page([a, b], 1) == [b]
    assert find_at([a, b], 0, 30, 15) is a
    assert find_at([a, b], 0, 300, 300) is None


def test_words_in_rect_snaps_to_words(make_pdf):
    doc = fitz.open(str(make_pdf("a.pdf", texts=["alfa beta gama"])))
    words = doc[0].get_text("words")
    beta = words[1]
    rects = words_in_rect(doc[0], (beta[0] + 1, beta[1] + 1, beta[2] - 1, beta[3] - 1))
    assert rects == [tuple(beta[:4])]
    doc.close()


def test_annotated_pdf_has_real_annotations(make_pdf, tmp_path):
    src = make_pdf("a.pdf", texts=["um", "dois"])
    doc = fitz.open(str(src))
    word = doc[1].get_text("words")[0]
    notes = [Annotation(HIGHLIGHT, 1, [tuple(word[:4])], "ver"), Annotation(NOTE, 0, [note_rect(50, 50)], "nota")]
    out = tmp_path / "anotado.pdf"
    save_annotated_pdf(doc, notes, out)
    doc.close()

    result = fitz.open(str(out))
    assert [a.type[1] for a in result[0].annots()] == ["Text"]
    assert [a.type[1] for a in result[1].annots()] == ["Highlight"]
    assert result[0].first_annot.info["content"] == "nota"
    result.close()
    assert not list(fitz.open(str(src))[0].annots())   # original sem anotações


def test_annotated_copy_of_page_range(make_pdf):
    doc = fitz.open(str(make_pdf("a.pdf", 3)))
    copy = annotated_copy(doc, [Annotation(NOTE, 2, [note_rect(1, 1)], "n")], (2, 2))
    assert copy.page_count == 1 and len(list(copy[0].annots())) == 1
    copy.close()
    doc.close()


def test_annotations_on_password_protected_pdf(make_pdf, tmp_path):
    from app.model.session import DocumentSession

    s = DocumentSession.open(make_pdf("s.pdf", texts=["segredo"], user_pw="1234"), password="1234")
    out = tmp_path / "s_anotado.pdf"
    save_annotated_pdf(s.doc, [Annotation(NOTE, 0, [note_rect(10, 10)], "x")], out)
    s.close()
    result = fitz.open(str(out))
    assert not result.needs_pass and len(list(result[0].annots())) == 1
    result.close()
