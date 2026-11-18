"""Comparação de texto palavra por palavra."""

import fitz

from app.services.text_diff import ADDED, CHANGED, REMOVED, count_by_kind, diff_documents, diff_pair
from app.services.text_index import DocumentIndex


def _index(make_pdf, name, texts):
    doc = fitz.open(str(make_pdf(name, texts=texts)))
    try:
        return DocumentIndex.build(doc)
    finally:
        doc.close()


def _words(index, marks):
    """Texto marcado, reconstruído a partir das posições."""
    out = []
    for m in marks:
        words = [t.text for t in index.pages[m.page] if tuple(t.rects[0]) in m.rects]
        out.append((m.kind, " ".join(words)))
    return out


def test_identical_documents_have_no_differences(make_pdf):
    a = _index(make_pdf, "a.pdf", ["O contrato foi assinado\nem 2025"])
    b = _index(make_pdf, "b.pdf", ["O contrato foi assinado\nem 2025"])
    assert diff_pair(a, b) == ([], [])


def test_changed_word_is_marked_in_both(make_pdf):
    a = _index(make_pdf, "a.pdf", ["O prazo é de 30 dias corridos"])
    b = _index(make_pdf, "b.pdf", ["O prazo é de 45 dias corridos"])
    ma, mb = diff_pair(a, b)
    assert _words(a, ma) == [(CHANGED, "30")]
    assert _words(b, mb) == [(CHANGED, "45")]


def test_added_and_removed_words(make_pdf):
    a = _index(make_pdf, "a.pdf", ["multa de dez por cento ao mes"])
    b = _index(make_pdf, "b.pdf", ["multa de dez por cento"])
    ma, mb = diff_pair(a, b)
    assert _words(a, ma) == [(REMOVED, "ao mes")]
    assert mb == []

    ma, mb = diff_pair(b, a)
    assert ma == [] and _words(a, mb) == [(ADDED, "ao mes")]


def test_new_line_and_page_shift_do_not_create_false_differences(make_pdf):
    a = _index(make_pdf, "a.pdf", ["Clausula um\nClausula dois", "Clausula tres"])
    b = _index(make_pdf, "b.pdf", ["Capa", "Clausula um\nClausula dois", "Clausula tres"])
    ma, mb = diff_pair(a, b)
    assert ma == []
    assert _words(b, mb) == [(ADDED, "Capa")]
    assert mb[0].page == 0


def test_rewrapped_line_only_marks_real_change(make_pdf):
    a = _index(make_pdf, "a.pdf", ["as partes acordam que o valor\nsera pago em reais"])
    b = _index(make_pdf, "b.pdf", ["as partes acordam que o valor sera\npago em dolares"])
    ma, mb = diff_pair(a, b)
    assert _words(a, ma) == [(CHANGED, "reais")]
    assert _words(b, mb) == [(CHANGED, "dolares")]


def test_case_and_accents_count_by_default_but_can_be_ignored(make_pdf):
    a = _index(make_pdf, "a.pdf", ["Acao judicial"])
    b = _index(make_pdf, "b.pdf", ["acao judicial"])
    assert diff_pair(a, b) != ([], [])
    assert diff_pair(a, b, case_sensitive=False, ignore_accents=True) == ([], [])


def test_several_documents_compare_with_first(make_pdf):
    ref = _index(make_pdf, "ref.pdf", ["valor de 100 reais"])
    v2 = _index(make_pdf, "v2.pdf", ["valor de 200 reais"])
    v3 = _index(make_pdf, "v3.pdf", ["valor de 100 reais"])
    result = diff_documents([ref, v2, v3])
    assert len(result) == 3
    assert _words(ref, result[0]) == [(CHANGED, "100")]
    assert _words(v2, result[1]) == [(CHANGED, "200")]
    assert result[2] == []
    assert count_by_kind(result[1]) == {ADDED: 0, REMOVED: 0, CHANGED: 1}


def test_single_document_has_no_diff(make_pdf):
    assert diff_documents([_index(make_pdf, "a.pdf", ["x"])]) == [[]]


def test_samples_contracts_have_differences():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "samples"
    docs = [fitz.open(str(root / n)) for n in ("contrato_v1.pdf", "contrato_v2.pdf")]
    try:
        result = diff_documents([DocumentIndex.build(d) for d in docs])
    finally:
        for d in docs:
            d.close()
    assert result[0] and result[1]
