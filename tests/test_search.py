import fitz
import pytest

from app.services.search import SearchOptions, search_index
from app.services.text_index import DocumentIndex, fold


def _index(path):
    doc = fitz.open(str(path))
    index = DocumentIndex.build(doc)
    doc.close()
    return index


def test_fold_removes_accents_and_case():
    assert fold("AÇÃO Contrátual") == "acao contratual"
    assert fold("AÇÃO", case_sensitive=True) == "ACAO"
    assert fold("ação", ignore_accents=False) == "ação"


def test_default_search_ignores_case_and_accents(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["Ação de COBRANÇA judicial"]))
    assert len(search_index(index, "acao")) == 1
    assert len(search_index(index, "cobranca")) == 1
    assert len(search_index(index, "Cobrança")) == 1


def test_accent_sensitive_option(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["Ação de cobrança"]))
    opts = SearchOptions(ignore_accents=False)
    assert search_index(index, "acao", opts) == []
    assert len(search_index(index, "ação", opts)) == 1


def test_case_sensitive_option(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["COBRANÇA e cobrança"]))
    opts = SearchOptions(case_sensitive=True)
    assert len(search_index(index, "COBRANÇA", opts)) == 1
    assert len(search_index(index, "cobrança", opts)) == 1
    assert len(search_index(index, "cobrança")) == 2


def test_whole_word_option(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["contrato contratual contratos"]))
    assert len(search_index(index, "contrat")) == 3
    assert search_index(index, "contrat", SearchOptions(whole_word=True)) == []
    assert len(search_index(index, "contrato", SearchOptions(whole_word=True))) == 1


def test_punctuation_is_ignored(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["Fim. (contrato), assinado;"]))
    opts = SearchOptions(whole_word=True)
    assert len(search_index(index, "fim", opts)) == 1
    assert len(search_index(index, "contrato", opts)) == 1


def test_phrase_search_returns_one_hit_with_all_words(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["contrato de prestação de serviços gerais"]))
    hits = search_index(index, "prestação de serviços")
    assert len(hits) == 1
    assert len(hits[0].rects) == 3


def test_hits_report_pages_in_order(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["nada", "multa aqui", "outra multa e multa"]))
    hits = search_index(index, "multa")
    assert [h.page for h in hits] == [1, 2, 2]


def test_hyphenated_word_across_lines(make_pdf):
    index = _index(make_pdf("a.pdf", texts=["este docu-\nmento segue"]))
    hits = search_index(index, "documento")
    assert len(hits) == 1
    assert len(hits[0].rects) == 2


@pytest.mark.parametrize("query", ["", "   ", "...", ","])
def test_empty_queries_return_nothing(make_pdf, query):
    index = _index(make_pdf("a.pdf", texts=["texto"]))
    assert search_index(index, query) == []


def test_hit_snippet_shows_context(make_pdf):
    import fitz

    from app.services.search import hit_snippet
    from app.services.text_index import DocumentIndex

    doc = fitz.open(str(make_pdf("s.pdf", texts=["um dois tres quatro cinco seis sete oito nove dez onze"])))
    index = DocumentIndex.build(doc)
    doc.close()
    hit = search_index(index, "seis sete")[0]
    assert hit_snippet(index, hit, context=2) == "… quatro cinco [seis sete] oito nove …"
    first = search_index(index, "um")[0]
    assert hit_snippet(index, first, context=1) == "[um] dois …"
