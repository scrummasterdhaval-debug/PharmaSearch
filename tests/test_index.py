import json

import pytest

from app.corpus import Document, load_corpus
from app.index import SearchIndex, tokenize


@pytest.fixture(scope="module")
def index() -> SearchIndex:
    return SearchIndex(load_corpus())


def test_tokenizer_keeps_dotted_citations_intact():
    assert "211.192" in tokenize("See 21 CFR 211.192 for the requirement.")


def test_search_ranks_the_obvious_document_first(index):
    hits = index.search("investigation of batch discrepancies")
    assert hits[0].document.id == "us-cfr-211-192"


def test_jurisdiction_filter_excludes_other_regions(index):
    hits = index.search("audit trail", jurisdiction="EU")
    assert hits, "expected at least one EU audit-trail document"
    assert {hit.document.jurisdiction for hit in hits} == {"EU"}


def test_limit_is_respected(index):
    assert len(index.search("quality", limit=2)) <= 2


def test_empty_and_unmatched_queries_return_nothing(index):
    assert index.search("   ") == []
    assert index.search("zzzzqqq xxxyyy") == []


def test_common_words_rank_below_a_real_term(index):
    """BM25 has no stopword list, so `not`/`a` still match; IDF must keep them
    from outranking a genuine compliance term. Worth a stopword pass later."""
    noise = index.search("not a real term")
    signal = index.search("falsified")
    assert signal[0].score > noise[0].score


def test_ranking_is_stable_for_equal_scores():
    """Two replicas must page results identically, so ties break deterministically."""
    docs = [
        Document(f"doc-{n}", "Audit trail", "X", "US", "2020-01-01", ("audit",), "audit trail review")
        for n in range(5)
    ]
    index = SearchIndex(docs)
    first = [hit.document.id for hit in index.search("audit trail")]
    second = [hit.document.id for hit in SearchIndex(docs).search("audit trail")]
    assert first == second == sorted(first)


def test_snippet_centres_on_the_match(index):
    hit = next(h for h in index.search("falsified medicinal products") if h.document.id == "eu-gdp-2013-c343")
    assert "falsified" in hit.snippet.lower()


def test_corpus_rejects_duplicate_ids(tmp_path):
    bad = tmp_path / "dupes.json"
    entry = {
        "id": "a", "title": "t", "citation": "c",
        "jurisdiction": "US", "effective_date": "2020-01-01", "text": "x",
    }
    bad.write_text(json.dumps([entry, entry]))
    with pytest.raises(ValueError, match="duplicate document id"):
        load_corpus(bad)


def test_corpus_rejects_missing_fields(tmp_path):
    bad = tmp_path / "partial.json"
    bad.write_text(json.dumps([{"id": "a", "title": "t"}]))
    with pytest.raises(ValueError, match="missing fields"):
        load_corpus(bad)


def test_synonyms_bridge_colloquial_to_regulatory_vocabulary(index):
    """'counterfeit' must reach 'falsified' — users do not type like regulators."""
    hits = index.search("our supplier might be shipping counterfeit drugs", limit=3)
    assert "eu-gdp-2013-c343" in {hit.document.id for hit in hits}


def test_expansion_does_not_outrank_a_literal_match():
    """A weak synonym must never displace the document that literally matches."""
    from app.synonyms import expand

    weights = expand(["counterfeit"])
    assert weights["counterfeit"] == 1.0
    assert weights["falsified"] < weights["counterfeit"]


def test_regulatory_phrasing_is_unaffected_by_expansion(index):
    """Precise citation lookups must stay precise after vocabulary bridging."""
    assert index.search("preventing falsified medicines")[0].document.id == "eu-gdp-2013-c343"
