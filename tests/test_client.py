import pytest
import requests

from conftest import FakeResponse, FakeSession, result_page
from garuda2ris import (
    GarudaClient,
    GarudaError,
    GarudaMismatch,
    crawl,
    dedupe,
    dedupe_groups,
    normalize_query,
)
from garuda2ris.models import Article


def three_pages(url, params):
    page = int(params["page"])
    ids = {1: range(1, 11), 2: range(11, 21), 3: range(21, 26)}[page]
    return result_page([str(i) for i in ids], page, 3, 25)


def make_client(handler, **kw):
    session = FakeSession(handler)
    sleeps = []
    client = GarudaClient(session=session, sleep=sleeps.append, **kw)
    return client, session, sleeps


def test_walks_all_pages_and_stops():
    client, session, sleeps = make_client(three_pages, delay=1.5)
    articles = list(client.search("kawasan tanpa rokok", field="abstract"))
    assert len(articles) == 25
    assert client.total_records == 25
    assert [dict(p)["page"] for _, p in session.calls] == ["1", "2", "3"]
    url, params = session.calls[0]
    assert url == "https://garuda.kemdiktisaintek.go.id/documents"
    assert params == [("page", "1"), ("q", "kawasan tanpa rokok"), ("select", "abstract")]
    assert sleeps == [1.5, 1.5]  # between requests, not before the first


def test_max_pages_and_max_records():
    client, session, _ = make_client(three_pages, delay=0)
    assert len(list(client.search("x", max_pages=2))) == 20
    assert len(session.calls) == 2
    client, session, _ = make_client(three_pages, delay=0)
    assert len(list(client.search("x", max_records=13))) == 13
    assert len(session.calls) == 2


def test_search_url_passes_filters_through_and_ignores_page():
    client, session, _ = make_client(three_pages, delay=0)
    url = ("https://garuda.kemdiktisaintek.go.id/documents"
           "?page=3&q=%20Smoke-Free%20Area%20Policy&select=abstract&pub=&pdf=")
    assert len(list(client.search_url(url))) == 25
    assert session.calls[0][1] == [
        ("page", "1"), ("q", " Smoke-Free Area Policy"), ("select", "abstract"),
        ("pub", ""), ("pdf", ""),
    ]


def test_search_url_follows_the_urls_own_domain():
    client, session, _ = make_client(three_pages, delay=0)
    list(client.search_url("https://garuda.kemdikbud.go.id/documents?q=x&select=title", max_pages=1))
    assert session.calls[0][0] == "https://garuda.kemdikbud.go.id/documents"


def test_stops_when_server_repeats_records():
    """No pager on the page and the same records again: stop, do not loop."""
    def stuck(url, params):
        resp = result_page(["1", "2"], 1, 9, 90)
        resp.content = resp.content.replace(b"Page 1 of 9 | Total Record : 90", b"")
        return resp

    client, session, _ = make_client(stuck, delay=0)
    assert len(list(client.search("x"))) == 2
    assert len(session.calls) == 2


def test_wrong_page_number_is_an_error_not_silent_data_loss():
    def stuck(url, params):
        return result_page(["1", "2"], 1, 9, 90)  # always answers "Page 1 of 9"

    client, session, _ = make_client(stuck, delay=0)
    with pytest.raises(GarudaMismatch, match="asked for page 2, got page 1"):
        list(client.search("x"))
    # page 1, page 2 on /documents, page 2 again on the fresh address
    assert len(session.calls) == 3
    assert "/documents/index/r" in session.calls[2][0]


def test_stale_answer_is_detected_and_refetched_on_fresh_address():
    """What the live site did on 4 Oct 2026: /documents kept answering with an
    old search, /documents/index/<token> answered correctly."""
    def handler(url, params):
        if url.endswith("/documents"):
            return result_page(["900"], 2, 5, 47, echo=("Smoke-Free Area Policy", "abstract"))
        page = int(params["page"])
        ids = {1: ["1", "2"], 2: ["3"]}[page]
        return result_page(ids, page, 2, 3, echo=(params["q"], params["select"]))

    client, session, _ = make_client(handler, delay=0)
    found = [a.garuda_id for a in client.search("kawasan tanpa rokok puskesmas", field="title")]
    assert found == ["1", "2", "3"]  # nothing from the stale page leaked in
    assert client.total_records == 3
    urls = [u for u, _ in session.calls]
    assert urls[0].endswith("/documents")
    assert all("/documents/index/r" in u for u in urls[1:])  # stays on the fresh address
    assert len(set(urls[1:])) == 2  # a new token per request
    assert len(urls) == 3

    # the next search with the same client goes straight to the fresh address
    list(client.search("kawasan tanpa rokok puskesmas", field="title"))
    assert all("/documents/index/r" in u for u, _ in session.calls[3:])


def test_cache_bust_modes():
    def always_stale(url, params):
        return result_page(["900"], 1, 1, 1, echo=("something else", "title"))

    client, session, _ = make_client(always_stale, delay=0, cache_bust=False)
    with pytest.raises(GarudaMismatch, match='asked for "x", got "something else"'):
        list(client.search("x"))
    assert len(session.calls) == 1

    def honest(url, params):
        return result_page(["1"], 1, 1, 1, echo=(params["q"], params["select"]))

    client, session, _ = make_client(honest, delay=0, cache_bust=True)
    assert len(list(client.search("x", field="abstract"))) == 1
    assert "/documents/index/r" in session.calls[0][0]

    def wrong_field(url, params):
        return result_page(["1"], 1, 1, 1, echo=(params["q"], "title"))

    client, _, _ = make_client(wrong_field, delay=0)
    with pytest.raises(GarudaMismatch, match="asked to search by abstract, got by title"):
        list(client.search("x", field="abstract"))


def test_echo_comparison_ignores_quotes_case_and_spacing():
    def handler(url, params):
        return result_page(["1"], 1, 1, 1, echo=('  "Kawasan  Tanpa Rokok"  PUSKESMAS', "Title"))

    client, _, _ = make_client(handler, delay=0, cache_bust=False)
    assert len(list(client.search("kawasan tanpa rokok puskesmas"))) == 1


@pytest.mark.parametrize(
    "typed, sent",
    [
        ('"smoke-free" hospital', "smoke free hospital"),
        ('"smoke-free area" healthcare', "smoke free area healthcare"),
        ('"smoke-free" "health facilities"', "smoke free health facilities"),
        ('"non-smoking area" hospital', "non smoking area hospital"),
        ('kepatuhan "kawasan tanpa rokok"', "kepatuhan kawasan tanpa rokok"),
        ("\u201ckawasan tanpa rokok\u201d  puskesmas", "kawasan tanpa rokok puskesmas"),
        ("rokok -elektrik", "rokok -elektrik"),  # deliberate exclusion is kept
        ("COVID-19 vaksin", "COVID 19 vaksin"),
        ("stunting", "stunting"),
    ],
)
def test_normalize_query(typed, sent):
    assert normalize_query(typed) == sent


def test_search_normalizes_but_search_url_does_not():
    def handler(url, params):
        return result_page(["1"], 1, 1, 1, echo=(params["q"], params["select"]))

    client, session, _ = make_client(handler, delay=0)
    list(client.search('"smoke-free" hospital', field="abstract"))
    assert dict(session.calls[-1][1])["q"] == "smoke free hospital"
    assert client.last_query_sent == "smoke free hospital"

    list(client.search('"smoke-free" hospital', field="abstract", normalize=False))
    assert dict(session.calls[-1][1])["q"] == '"smoke-free" hospital'

    list(client.search_url("https://garuda.kemdiktisaintek.go.id/documents?q=%22smoke-free%22+hospital&select=abstract"))
    assert dict(session.calls[-1][1])["q"] == '"smoke-free" hospital'

    kept = crawl('"smoke-free" hospital', client=client, field="abstract")
    assert len(kept) == 1 and dict(session.calls[-1][1])["q"] == "smoke free hospital"


def test_retries_then_succeeds():
    attempts = []

    def flaky(url, params):
        attempts.append(1)
        if len(attempts) == 1:
            raise requests.ConnectionError("boom")
        if len(attempts) == 2:
            return FakeResponse(status_code=503)
        return result_page(["7"], 1, 1, 1)

    client, _, sleeps = make_client(flaky, delay=0)
    assert [a.garuda_id for a in client.search("x")] == ["7"]
    assert sleeps == [1.0, 2.0]  # exponential back-off


def test_gives_up_with_clear_error():
    client, session, _ = make_client(lambda u, p: FakeResponse(status_code=503), delay=0, max_retries=2)
    with pytest.raises(GarudaError, match="HTTP 503"):
        list(client.search("x"))
    assert len(session.calls) == 3
    # a 404 is not retried
    client, session, _ = make_client(lambda u, p: FakeResponse(status_code=404), delay=0)
    with pytest.raises(GarudaError, match="HTTP 404"):
        list(client.search("x"))
    assert len(session.calls) == 1


def test_native_ris_accepts_ris_and_rejects_html():
    def handler(url, params):
        if url.endswith("/citation/site/RIS/1"):
            return FakeResponse("﻿TY  - JOUR\r\nTI  - Native\r\nER  - \r\n")
        return FakeResponse("<html>Not found</html>")

    client, session, _ = make_client(handler, delay=0)
    assert client.native_ris("1") == "TY  - JOUR\nTI  - Native\nER  -"
    assert client.native_ris("2") is None
    assert session.calls[0][0] == "https://garuda.kemdiktisaintek.go.id/citation/site/RIS/1"


def test_crawl_year_filter_keeps_unknown_years_by_default():
    def handler(url, params):
        resp = result_page(["1", "2", "3"], 1, 1, 3)  # years 2001, 2002, 2003
        resp.content = resp.content.replace(b"Vol 1 No 1 (2003)", b"Vol 1 No 1")
        return resp

    client, _, _ = make_client(handler, delay=0)
    kept = crawl("x", client=client, year_from=2002)
    assert [(a.garuda_id, a.year) for a in kept] == [("2", 2002), ("3", None)]
    client, _, _ = make_client(handler, delay=0)
    kept = crawl("x", client=client, year_from=2002, keep_unknown_year=False)
    assert [a.garuda_id for a in kept] == ["2"]


def test_dedupe_by_doi_and_title_and_merges_fields():
    a = Article("1", "Indonesian Government Policy in Forest Fire Handling", doi="10.1/x")
    b = Article("2", "INDONESIAN GOVERNMENT POLICY IN FOREST FIRE HANDLING", doi="10.1/X",
                garuda_pdf_url="http://pdf")
    c = Article("3", "Hubungan Lingkungan terhadap Kebijakan")
    d = Article("4", "HUBUNGAN LINGKUNGAN TERHADAP KEBIJAKAN.", publisher="USM")
    e = Article("5", "A different paper")
    kept = dedupe([a, b, c, d, e])
    assert [x.garuda_id for x in kept] == ["1", "3", "5"]
    assert kept[0].garuda_pdf_url == "http://pdf"  # filled in from the duplicate
    assert kept[1].publisher == "USM"


def test_dedupe_groups_and_short_titles():
    a = Article("1", "Kepatuhan terhadap Kawasan Tanpa Rokok", doi="10.1/a")
    b = Article("2", "KEPATUHAN TERHADAP KAWASAN TANPA ROKOK")
    c = Article("3", "Editorial")
    d = Article("4", "Editorial")  # short generic title: not merged without a DOI
    e = Article("5", "Something else entirely here", doi="10.1/A")
    groups = dedupe_groups([a, b, c, d, e])
    assert [[x.garuda_id for x in g] for g in groups] == [["1", "2", "5"], ["3"], ["4"]]
