"""One-call helpers: crawl a search and write it to ``.ris``."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from .client import GarudaClient, GarudaError
from .models import Article
from .parser import extract_keywords
from .ris import write_ris

log = logging.getLogger("garuda2ris")


def _title_key(title: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", title.lower())


def dedupe_groups(articles: Iterable[Article]) -> List[List[Article]]:
    """Group records that are the same paper.

    Garuda indexes the same paper again when a journal is re-harvested, so a
    result set often holds the same title under two Garuda IDs. Two records
    belong together when they share a DOI or a normalised title (titles
    shorter than 15 letters, such as "Editorial", are matched by DOI only).
    Each group lists its records in the order they were given.
    """
    groups: List[List[Article]] = []
    by_doi: Dict[str, int] = {}
    by_title: Dict[str, int] = {}
    for article in articles:
        doi = (article.doi or "").lower()
        key = _title_key(article.title)
        if len(key) < 15:
            key = ""
        index = by_doi.get(doi) if doi else None
        if index is None and key:
            index = by_title.get(key)
        if index is None:
            groups.append([article])
            index = len(groups) - 1
        else:
            groups[index].append(article)
        if doi:
            by_doi.setdefault(doi, index)
        if key:
            by_title.setdefault(key, index)
    return groups


def dedupe(articles: Iterable[Article]) -> List[Article]:
    """Drop records Garuda lists more than once (see :func:`dedupe_groups`).

    The first record of each group is kept and any field it lacks is filled
    in from its duplicates.
    """
    kept: List[Article] = []
    for group in dedupe_groups(articles):
        first = group[0]
        for other in group[1:]:
            for name, value in other.to_dict().items():
                if value and not getattr(first, name):
                    setattr(first, name, value)
        kept.append(first)
    return kept


def crawl(
    query_or_url: str,
    *,
    field: str = "title",
    publisher: Optional[str] = None,
    normalize: bool = True,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    keep_unknown_year: bool = True,
    remove_duplicates: bool = False,
    keywords: bool = False,
    max_pages: Optional[int] = None,
    max_records: Optional[int] = None,
    client: Optional[GarudaClient] = None,
    **client_options,
) -> List[Article]:
    """Collect every record of a Garuda search.

    ``query_or_url`` is either search words or a full Garuda search URL
    copied from the browser. Search words are rewritten by
    :func:`garuda2ris.normalize_query` unless ``normalize=False`` (Garuda
    reads ``smoke-free`` as "smoke" without "free"); a URL is used as it is.
    ``year_from`` / ``year_to`` are applied to the
    year parsed from each record; records whose year Garuda does not show
    are kept unless ``keep_unknown_year=False``.
    """
    client = client or GarudaClient(**client_options)
    limits = {"max_pages": max_pages, "max_records": max_records}
    if re.match(r"^https?://", query_or_url.strip(), re.I):
        found = client.search_url(query_or_url.strip(), **limits)
    else:
        found = client.search(
            query_or_url, field=field, publisher=publisher, normalize=normalize, **limits
        )

    articles: List[Article] = []
    for article in found:
        if year_from is not None or year_to is not None:
            if article.year is None:
                if not keep_unknown_year:
                    continue
            elif (year_from is not None and article.year < year_from) or (
                year_to is not None and article.year > year_to
            ):
                continue
        if keywords and not article.keywords:
            article.keywords = extract_keywords(article.abstract)
        articles.append(article)

    if remove_duplicates:
        before = len(articles)
        articles = dedupe(articles)
        log.info("removed %d duplicate records", before - len(articles))
    return articles


def crawl_to_ris(
    query_or_url: str,
    path: Union[str, Path],
    *,
    native: bool = False,
    invert_names: bool = False,
    include_pdf_links: bool = True,
    encoding: str = "utf-8",
    line_ending: str = "\r\n",
    client: Optional[GarudaClient] = None,
    **crawl_options,
) -> List[Article]:
    """Crawl a search and save it as RIS. Returns the records written.

    With ``native=True`` each record is taken from Garuda's own RIS export
    (one extra request per record) and topped up with the abstract and DOI
    from the listing; records whose export fails fall back to the record
    built from the listing.
    """
    client_keys = (
        "base_url", "delay", "timeout", "max_retries", "user_agent", "session", "cache_bust", "sleep",
    )
    client = client or GarudaClient(
        **{k: crawl_options.pop(k) for k in client_keys if k in crawl_options}
    )
    articles = crawl(query_or_url, client=client, **crawl_options)

    native_text: Dict[str, str] = {}
    if native:
        for article in articles:
            try:
                text = client.native_ris(article.garuda_id)
            except GarudaError as exc:
                log.warning("native RIS for %s unavailable (%s)", article.garuda_id, exc)
                continue
            if text:
                native_text[article.garuda_id] = text

    write_ris(
        articles,
        path,
        encoding=encoding,
        line_ending=line_ending,
        native=native_text,
        invert_names=invert_names,
        include_pdf_links=include_pdf_links,
    )
    return articles
