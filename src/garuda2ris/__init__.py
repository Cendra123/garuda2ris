"""garuda2ris - crawl Garuda (Garba Rujukan Digital) searches into RIS files."""

__version__ = "0.2.0"

from .api import crawl, crawl_to_ris, dedupe, dedupe_groups
from .client import SEARCH_FIELDS, GarudaClient, GarudaError, GarudaMismatch, normalize_query
from .models import Article, SearchPage
from .parser import (
    clean_author,
    extract_keywords,
    parse_search_page,
    parse_source_line,
)
from .ris import article_to_ris, to_ris, write_ris

__all__ = [
    "Article",
    "GarudaClient",
    "GarudaError",
    "GarudaMismatch",
    "SEARCH_FIELDS",
    "SearchPage",
    "article_to_ris",
    "clean_author",
    "crawl",
    "crawl_to_ris",
    "dedupe",
    "dedupe_groups",
    "extract_keywords",
    "normalize_query",
    "parse_search_page",
    "parse_source_line",
    "to_ris",
    "write_ris",
    "__version__",
]
