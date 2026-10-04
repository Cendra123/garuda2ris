from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def classes_html() -> bytes:
    return (FIXTURES / "search_classes.html").read_bytes()


@pytest.fixture
def flat_html() -> bytes:
    return (FIXTURES / "search_flat.html").read_bytes()


class FakeResponse:
    def __init__(self, content=b"", status_code=200):
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")
        self.status_code = status_code


class FakeSession:
    """Stands in for requests.Session; ``handler(url, params)`` builds replies."""

    def __init__(self, handler):
        self.handler = handler
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, list(params or [])))
        return self.handler(url, dict(params or []))


def result_page(ids, page, total_pages, total_records, echo=None):
    """Minimal result page with one record per id.

    ``echo=(query, field)`` adds Garuda's "Search <query>, by <field>" line.
    """
    said = f"<div>Search <i>{echo[0]}</i> <i>, by {echo[1]}</i></div>" if echo else ""
    items = "".join(
        f"""
        <div class="article-item">
          <a href="/documents/detail/{i}">Title number {i}</a>
          <a href="/author/view/{i}">Author {i}</a><br>
          Jurnal Uji Vol {page} No 1 ({2000 + int(i) % 30})<br>
          <i>Publisher :</i> Penerbit {i}
          <p>Show Abstract | <a href="http://j.example/view/{i}">Original Source</a></p>
          <h4>Abstract</h4><p>Abstract text for record {i}, long enough to count.</p>
        </div>"""
        for i in ids
    )
    return FakeResponse(
        f"<html><body><h2>Found {total_records} documents</h2>{said}{items}"
        f"<div>Page {page} of {total_pages} | Total Record : {total_records}</div>"
        "</body></html>"
    )
