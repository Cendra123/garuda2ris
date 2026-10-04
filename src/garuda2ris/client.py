"""HTTP side: fetch Garuda search pages politely and walk the pagination."""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import parse_qsl, urlsplit

import requests

from .models import Article, SearchPage
from .parser import DEFAULT_BASE_URL, parse_search_page

log = logging.getLogger("garuda2ris")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; garuda2ris/0.2; academic reference export)"
)
#: Values the "Search By" radio buttons send in ``select=``.
SEARCH_FIELDS = ("title", "abstract", "author", "doi")
_RETRY_STATUS = {429, 500, 502, 503, 504}

Params = Union[Mapping[str, str], Sequence[Tuple[str, str]]]


class GarudaError(RuntimeError):
    """Raised when Garuda cannot be reached or answers with an error."""


class GarudaMismatch(GarudaError):
    """Garuda answered with a different search or page than the one asked for."""


def normalize_query(query: str) -> str:
    """Rewrite a query so Garuda reads it the way a person means it.

    Garuda's search box has two traps (measured on the live site, Oct 2026):

    * a hyphen inside a word **excludes** what follows it: ``smoke-free``
      returns records that contain "smoke" and do NOT contain "free";
    * double quotes do not make a phrase search: words are matched
      individually, in any order, and all of them must be present.

    So hyphens between letters become spaces and double quotes are dropped.
    A hyphen at the start of a word (``rokok -elektrik``) is left alone, so
    deliberate exclusion still works.
    """
    text = re.sub(r"[\"\u201c\u201d\u201e\u201f]", " ", query)
    text = re.sub(r"(?<=\w)[-\u2010\u2011\u2013](?=\w)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _squash(text: Optional[str]) -> str:
    return re.sub(r"[\W_]+", "", (text or "").lower())


class GarudaClient:
    """Small, polite client for ``garuda.kemdiktisaintek.go.id``.

    Parameters
    ----------
    base_url:
        Site origin. Garuda has moved domains before (ristekbrin ->
        kemdikbud -> kemdiktisaintek), so this is configurable.
    delay:
        Seconds to wait between requests. Keep it at 1s or more; this is a
        shared public service.
    timeout, max_retries:
        Per-request timeout and how often to retry on network errors or
        HTTP 429/5xx (with exponential back-off).
    session:
        Bring your own ``requests.Session`` (proxies, custom CA, ...).
    cache_bust:
        Garuda's ``/documents`` address can hand back a stale page that
        belongs to another search. Every answer is therefore checked against
        the search and page that were asked for. With ``"auto"`` (default) a
        wrong answer is retried on the equivalent address
        ``/documents/index/<token>``, which is then used for the rest of this
        client's life. ``True`` uses that address from the start; ``False``
        never does and raises :class:`GarudaMismatch` instead.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        delay: float = 1.0,
        timeout: float = 30.0,
        max_retries: int = 3,
        user_agent: str = DEFAULT_USER_AGENT,
        session: Optional[requests.Session] = None,
        cache_bust: Union[bool, str] = "auto",
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        if session is None:
            session = requests.Session()
            session.headers["User-Agent"] = user_agent
        self.session = session
        self._sleep = sleep
        self._requests_made = 0
        self.cache_bust = cache_bust
        self._stale_seen = False
        #: "Total Record" reported by the most recent search, if any.
        self.total_records: Optional[int] = None
        #: The query text actually sent by the most recent :meth:`search`.
        self.last_query_sent: Optional[str] = None

    # ------------------------------------------------------------------ http
    def _get(self, url: str, params: Optional[Sequence[Tuple[str, str]]] = None):
        last_error: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            if self._requests_made and self.delay > 0:
                self._sleep(self.delay)
            self._requests_made += 1
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    return resp
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code not in _RETRY_STATUS:
                    break
            if attempt < self.max_retries:
                wait = 2.0 ** attempt
                log.warning("%s for %s - retrying in %.0fs", last_error, url, wait)
                self._sleep(wait)
        raise GarudaError(f"GET {url} failed: {last_error}")

    # ---------------------------------------------------------------- search
    def _unique_path(self) -> str:
        return f"/documents/index/r{int(time.time())}n{self._requests_made}"

    @staticmethod
    def _mismatch(items: List[Tuple[str, str]], page: int, result: SearchPage) -> Optional[str]:
        """Say what is wrong when ``result`` is not the page that was asked for."""
        wanted = dict(items)
        if result.query_echo is not None and "q" in wanted:
            if _squash(result.query_echo) != _squash(wanted["q"]):
                return f'asked for "{wanted["q"].strip()}", got "{result.query_echo}"'
        if result.field_echo and wanted.get("select"):
            if result.field_echo.lower() != wanted["select"].lower():
                return f'asked to search by {wanted["select"]}, got by {result.field_echo}'
        if result.page is not None and result.page != page:
            return f"asked for page {page}, got page {result.page}"
        return None

    def fetch_page(self, params: Params, page: int = 1, *, verify: bool = True) -> SearchPage:
        """Fetch and parse one result page, checking it is the one asked for."""
        items = list(params.items()) if isinstance(params, Mapping) else list(params)
        items = [(k, v) for k, v in items if k != "page"]
        query = [("page", str(page))] + items
        bust = self.cache_bust is True or self._stale_seen
        while True:
            path = self._unique_path() if bust else "/documents"
            resp = self._get(self.base_url + path, params=query)
            result = parse_search_page(resp.content, base_url=self.base_url)
            problem = self._mismatch(items, page, result) if verify else None
            if problem is None:
                return result
            if bust or self.cache_bust is False:
                raise GarudaMismatch(f"Garuda returned the wrong page: {problem}")
            log.warning("stale answer from Garuda (%s) - retrying on a fresh address", problem)
            self._stale_seen = bust = True

    def iter_search(
        self,
        params: Params,
        *,
        start_page: int = 1,
        max_pages: Optional[int] = None,
        max_records: Optional[int] = None,
    ) -> Iterator[Article]:
        """Yield every record of a search, page after page."""
        seen = set()
        page, pages_done, count = start_page, 0, 0
        self.total_records = None
        while True:
            result = self.fetch_page(params, page)
            if result.total_records is not None:
                self.total_records = result.total_records
            fresh = [a for a in result.articles if a.garuda_id not in seen]
            log.info(
                "page %d/%s: %d records (%d new)",
                page, result.total_pages or "?", len(result.articles), len(fresh),
            )
            if not fresh:  # empty page, or the server is repeating itself
                return
            for article in fresh:
                seen.add(article.garuda_id)
                yield article
                count += 1
                if max_records is not None and count >= max_records:
                    return
            pages_done += 1
            if max_pages is not None and pages_done >= max_pages:
                return
            if result.total_pages is not None and page >= result.total_pages:
                return
            page += 1

    def search(
        self,
        query: str,
        *,
        field: str = "title",
        publisher: Optional[str] = None,
        normalize: bool = True,
        extra_params: Optional[Mapping[str, str]] = None,
        **kwargs,
    ) -> Iterator[Article]:
        """Search Garuda. ``field`` is one of :data:`SEARCH_FIELDS`.

        With ``normalize=True`` the query goes through
        :func:`normalize_query` first (hyphens inside words and double
        quotes are removed, because Garuda misreads them).
        """
        sent = normalize_query(query) if normalize else query
        if sent != query:
            log.info("query %r sent to Garuda as %r", query, sent)
        self.last_query_sent = sent
        params: Dict[str, str] = {"q": sent, "select": field}
        if publisher:
            params["pub"] = publisher
        if extra_params:
            params.update(extra_params)
        return self.iter_search(params, **kwargs)

    def search_url(self, url: str, **kwargs) -> Iterator[Article]:
        """Crawl a search you set up in the browser: paste its URL here.

        Every query parameter is passed through untouched, so whatever
        filters the page had (search field, publisher, PDF-only, ...) still
        apply and the query is NOT rewritten. The ``page`` parameter is
        ignored: crawling starts at ``start_page`` (default 1) and runs to
        the last page.
        """
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            self.base_url = f"{parts.scheme}://{parts.netloc}"
        params: List[Tuple[str, str]] = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"
        ]
        q = dict(params).get("q", "")
        self.last_query_sent = q
        if normalize_query(q) != re.sub(r"\s+", " ", q).strip():
            log.warning(
                "the query %r contains hyphens or quotes; Garuda reads 'smoke-free' as "
                "'smoke' WITHOUT 'free' and ignores quotes", q.strip(),
            )
        return self.iter_search(params, **kwargs)

    # ------------------------------------------------------------ native RIS
    def native_ris(self, garuda_id: str) -> Optional[str]:
        """Download Garuda's own RIS export for one record.

        This is the "RIS" button on a record's detail page
        (``/citation/site/RIS/<id>``). Returns ``None`` if the answer does
        not look like RIS.
        """
        resp = self._get(f"{self.base_url}/citation/site/RIS/{garuda_id}")
        text = resp.content.decode("utf-8-sig", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if re.search(r"^TY\s+-", text, re.M) and re.search(r"^ER\s+-", text, re.M):
            return text
        log.warning("native RIS for %s is not valid RIS; using built record", garuda_id)
        return None
