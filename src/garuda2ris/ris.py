"""Serialise :class:`Article` objects as RIS."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Union

from .models import Article

_CONFERENCE_RE = re.compile(
    r"\b(conference|proceedings?|prosiding|seminar|simposium|symposium|konferensi)\b",
    re.I,
)
CRLF = "\r\n"


def _one_line(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _tag(tag: str, value: object) -> str:
    return f"{tag}  - {_one_line(value)}"


def ris_author(name: str, invert: bool = False) -> str:
    """Format one author for an ``AU`` line.

    Names that already contain a comma are kept as ``Last, First``. With
    ``invert=True`` a name without a comma is turned into ``Last, First``
    by treating its final word as the family name. Indonesian names often
    have no family name, so this is off by default.
    """
    name = _one_line(name)
    if invert and "," not in name:
        tokens = name.split()
        if len(tokens) > 1:
            return f"{tokens[-1]}, {' '.join(tokens[:-1])}"
    return name


def reference_type(article: Article) -> str:
    """``CONF`` when the venue name says conference/proceedings, else ``JOUR``."""
    return "CONF" if _CONFERENCE_RE.search(article.journal or "") else "JOUR"


def article_to_ris_lines(
    article: Article,
    *,
    invert_names: bool = False,
    include_pdf_links: bool = True,
    ty: str = "auto",
) -> List[str]:
    kind = reference_type(article) if ty == "auto" else ty
    lines = [_tag("TY", kind), _tag("ID", f"garuda{article.garuda_id}")]
    lines.append(_tag("TI", article.title))
    lines += [_tag("AU", ris_author(a, invert_names)) for a in article.authors]
    if article.year:
        lines.append(_tag("PY", article.year))
    if article.journal:
        lines.append(_tag("T2", article.journal))
        if kind == "JOUR":
            lines.append(_tag("JF", article.journal))
    if article.volume:
        lines.append(_tag("VL", article.volume))
    if article.issue:
        lines.append(_tag("IS", article.issue))
    if article.publisher:
        lines.append(_tag("PB", article.publisher))
    if article.doi:
        lines.append(_tag("DO", article.doi))
    if article.abstract:
        lines.append(_tag("AB", article.abstract))
    lines += [_tag("KW", k) for k in article.keywords]
    main_url = article.url or article.garuda_url
    if main_url:
        lines.append(_tag("UR", main_url))
    if include_pdf_links:
        for link in (article.pdf_url, article.garuda_pdf_url):
            if link:
                lines.append(_tag("L1", link))
    if article.garuda_url and article.garuda_url != main_url:
        lines.append(_tag("L2", article.garuda_url))
    lines.append(_tag("AN", article.garuda_id))
    lines.append(_tag("DB", "GARUDA"))
    lines.append(_tag("DP", "Garuda - Garba Rujukan Digital"))
    lines.append("ER  - ")
    return lines


def article_to_ris(article: Article, *, line_ending: str = CRLF, **options) -> str:
    return line_ending.join(article_to_ris_lines(article, **options)) + line_ending


def merge_into_native(native: str, article: Article) -> List[str]:
    """Add what Garuda's own RIS export leaves out (abstract, DOI, URL)."""
    lines = [ln.rstrip() for ln in native.split("\n") if ln.strip()]
    present = {ln[:2] for ln in lines if re.match(r"^[A-Z][A-Z0-9]\s+-", ln)}
    extra: List[str] = []
    if article.abstract and not present & {"AB", "N2"}:
        extra.append(_tag("AB", article.abstract))
    if article.doi and "DO" not in present:
        extra.append(_tag("DO", article.doi))
    if (article.url or article.garuda_url) and "UR" not in present:
        extra.append(_tag("UR", article.url or article.garuda_url))
    extra += [_tag("KW", k) for k in article.keywords if "KW" not in present]
    end = next((i for i, ln in enumerate(lines) if re.match(r"^ER\s+-", ln)), len(lines))
    return lines[:end] + extra + ["ER  - "]


def to_ris(
    articles: Iterable[Article],
    *,
    line_ending: str = CRLF,
    native: Optional[dict] = None,
    **options,
) -> str:
    """Render records as one RIS document.

    ``native`` maps ``garuda_id`` to Garuda's own RIS text for records where
    that export should be used instead of the record built from the listing.
    """
    blocks: List[str] = []
    for article in articles:
        raw = (native or {}).get(article.garuda_id)
        lines = merge_into_native(raw, article) if raw else article_to_ris_lines(article, **options)
        blocks.append(line_ending.join(lines) + line_ending)
    return line_ending.join(blocks)


def write_ris(
    articles: Iterable[Article],
    path: Union[str, Path],
    *,
    encoding: str = "utf-8",
    **options,
) -> Path:
    """Write records to ``path``. Use ``encoding="utf-8-sig"`` for old EndNote."""
    path = Path(path)
    path.write_bytes(to_ris(articles, **options).encode(encoding))
    return path
