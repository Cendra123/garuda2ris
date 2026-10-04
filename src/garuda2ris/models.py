"""Data containers used across the package."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Article:
    """One record from a Garuda search-result listing."""

    garuda_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    year: Optional[int] = None
    #: Free text Garuda shows after the volume/issue, e.g. "Oktober-Desember 2025".
    issue_title: Optional[str] = None
    #: The untouched "Journal Vol x, No y (yyyy): ..." line, kept for auditing.
    source_line: Optional[str] = None
    publisher: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    #: "Original Source" link (the article page on the journal's own site).
    url: Optional[str] = None
    #: "Download Original" link (PDF on the journal's own site).
    pdf_url: Optional[str] = None
    #: "Full PDF" link (copy hosted by Garuda), when Garuda has one.
    garuda_pdf_url: Optional[str] = None
    #: The record's detail page on Garuda.
    garuda_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchPage:
    """One parsed page of search results."""

    articles: List[Article] = field(default_factory=list)
    page: Optional[int] = None
    total_pages: Optional[int] = None
    total_records: Optional[int] = None
    #: The search Garuda says it ran ("Search <query>, by <field>"). Used to
    #: detect a stale page that belongs to somebody else's search.
    query_echo: Optional[str] = None
    field_echo: Optional[str] = None
