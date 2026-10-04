"""Turn a Garuda search-result page into :class:`Article` objects.

The parser deliberately does not depend on Garuda's CSS class names. It keys
on things that are part of how the site works rather than how it is styled:

* every record links to ``/documents/detail/<id>``
* every author links to ``/author/view/<id>``
* DOIs link to ``doi.org``
* the action row uses the labels "Download Original", "Original Source"
  and "Full PDF"
* the publisher is introduced by the label "Publisher :" and the line above
  it is "Journal name Vol x, No y (yyyy): issue title"

A redesign that keeps those conventions will keep working.
"""

from __future__ import annotations

import copy
import html as _html
import re
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString
from requests.utils import requote_uri

from .models import Article, SearchPage

DEFAULT_BASE_URL = "https://garuda.kemdiktisaintek.go.id"

DETAIL_RE = re.compile(r"/documents/detail/(\d+)")
AUTHOR_RE = re.compile(r"/author/view/\d+")
JOURNAL_RE = re.compile(r"/journal/view/\d+")
PAGER_RE = re.compile(
    r"Page\s+(\d+)\s+of\s+(\d+)\s*\|\s*Total\s+Record\s*:\s*([\d.,]+)", re.I
)
FOUND_RE = re.compile(r"Found\s+([\d.,]+)\s+documents?", re.I)
ECHO_RE = re.compile(
    r"Found\s+[\d.,]+\s+documents?\s+Search\s+(.{0,500}?)\s*,\s*by\s+([A-Za-z]+)",
    re.I | re.S,
)
PUBLISHER_RE = re.compile(r"^Publisher\s*:\s*(.*)$", re.I)
DOI_HREF_RE = re.compile(r"doi\.org/(10\..+)$", re.I)
DOI_TEXT_RE = re.compile(r"DOI\s*:?\s*(10\.\d{4,9}/[^\s|]+)", re.I)

_NUM = r"((?:\d[0-9A-Za-z]*|[IVXLCDM]+\b)(?:[./-][0-9A-Za-z]+)*)"
_VOL_RE = re.compile(r"\b(?i:vol(?:ume)?)\b\.?\s*" + _NUM)
_ISS_RE = re.compile(r"\b(?i:no(?:mor)?|issue|iss|edisi)\b\.?\s*" + _NUM)
_YEAR_PAREN_RE = re.compile(r"\(\s*((?:19|20)\d{2})\s*\)")
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_BLOCK_TAGS = frozenset(
    "address article aside blockquote dd div dl dt fieldset figure footer form "
    "h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section table tbody td "
    "tfoot th thead tr ul xmp".split()
)
_STRAY_TAG_RE = re.compile(
    r"</?(?:p|br|i|b|em|strong|span|div|sub|sup|u|a|font|h[1-6]|ul|ol|li|"
    r"table|tr|td|o:p)\b[^>]*>",
    re.I,
)
_KEYWORD_LABEL_RE = re.compile(r"(?:key\s*-?\s*words?|kata\s+kunci)\s*[:：]\s*", re.I)
_ABSTRACT_MARK_RE = re.compile(r"\b(?:ABSTRAK|ABSTRACT|Abstrak|Abstract)\b")


# --------------------------------------------------------------------------
# small text helpers
# --------------------------------------------------------------------------

def _ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_text(text: str) -> str:
    """Collapse whitespace, drop leftover HTML tags and decode entities."""
    text = _STRAY_TAG_RE.sub(" ", text or "")
    return _ws(_html.unescape(text))


def clean_author(name: str) -> str:
    """Tidy an author name as shown by Garuda.

    Garuda inherits placeholder junk from OJS metadata: ``"Minollah -"``,
    ``'", Hasanuddin'``, ``"NIM. A1011161020, SIGIT PURWADI"``. This removes
    the placeholders and keeps whatever real name parts remain, in the order
    and ``Last, First`` form the source used.
    """
    s = _ws(name)
    s = re.sub(r"\bNIM\b\.?\s*[A-Za-z]{0,3}\d[\w.]*\s*,?\s*", "", s, flags=re.I)
    s = re.sub(r"[\"“”]", "", s)
    parts = []
    for part in s.split(","):
        tokens = [t for t in part.split() if not re.fullmatch(r"[-–—_.]+", t)]
        if tokens:
            parts.append(" ".join(tokens))
    return ", ".join(parts)


def clean_doi(value: str) -> Optional[str]:
    """Return a bare DOI (``10.xxxx/...``) from a DOI or a doi.org URL."""
    s = _ws(unquote(value or ""))
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi\s*:\s*", "", s, flags=re.I)
    return s if s.startswith("10.") else None


def parse_source_line(
    line: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int], Optional[str]]:
    """Split ``"Journal Vol 16, No 4 (2025): Oktober-Desember 2025"``.

    Returns ``(journal, volume, issue, year, issue_title)``. Any part Garuda
    does not show comes back as ``None``; nothing is guessed.
    """
    line = _ws(line)
    if not line:
        return None, None, None, None, None

    vol = _VOL_RE.search(line)
    iss = _ISS_RE.search(line, vol.end() if vol else 0) or (
        None if vol else _ISS_RE.search(line)
    )
    starts = [m.start() for m in (vol, iss) if m]
    paren = _YEAR_PAREN_RE.search(line, min(starts) if starts else 0)

    if starts:
        start = min(starts)
    elif paren:
        start = paren.start()
    else:
        return line, None, None, None, None

    journal = line[:start].strip(" ,:;-–") or None
    tail = line[start:]

    year: Optional[int] = None
    if paren:
        year = int(paren.group(1))
    else:
        years = _YEAR_RE.findall(tail)
        if years:
            year = int(years[-1])

    rest = tail
    for m in (vol, iss):
        if m:
            rest = rest.replace(m.group(0), " ", 1)
    rest = _YEAR_PAREN_RE.sub(" ", rest, count=1)
    issue_title = _ws(rest).strip(" ,:;-–") or None

    return (
        journal,
        vol.group(1) if vol else None,
        iss.group(1) if iss else None,
        year,
        issue_title,
    )


def extract_keywords(abstract: Optional[str]) -> List[str]:
    """Pull a trailing ``Keywords: a; b; c`` list out of an abstract.

    Garuda has no keyword field; authors' keywords usually sit at the end of
    the abstract text (once per language in bilingual abstracts). This is
    conservative: a keyword run is only used when it is short and clearly
    delimited.
    """
    if not abstract:
        return []
    found: List[str] = []
    for m in _KEYWORD_LABEL_RE.finditer(abstract):
        tail = abstract[m.end():]
        # bilingual abstracts continue with "ABSTRAK ..." after the keywords
        cut = _ABSTRACT_MARK_RE.search(tail)
        if cut:
            tail = tail[: cut.start()]
        tail = tail.strip()
        if not tail or len(tail) > 300:
            continue
        sep = ";" if ";" in tail else ","
        for word in tail.split(sep):
            word = word.strip(" .;,")
            if word and len(word) <= 80 and word.lower() not in (w.lower() for w in found):
                found.append(word)
    return found


# --------------------------------------------------------------------------
# DOM helpers
# --------------------------------------------------------------------------

def _lines(node: Tag) -> List[str]:
    """Visible text of ``node`` as lines, breaking only at block tags / <br>."""
    buf: List[str] = []

    def walk(n: Tag) -> None:
        for child in n.children:
            if isinstance(child, PreformattedString):  # comments, doctype, ...
                continue
            if isinstance(child, NavigableString):
                buf.append(re.sub(r"\s+", " ", str(child)))
                continue
            if child.name in ("script", "style"):
                continue
            if child.name == "br":
                buf.append("\n")
                continue
            block = child.name in _BLOCK_TAGS
            if block:
                buf.append("\n")
            walk(child)
            if block:
                buf.append("\n")

    walk(node)
    return [ln for ln in (_ws(x) for x in "".join(buf).split("\n")) if ln]


def _detail_ids(tag: Tag) -> set:
    ids = set()
    anchors = tag.find_all("a", href=DETAIL_RE)
    if tag.name == "a" and DETAIL_RE.search(tag.get("href", "") or ""):
        anchors = [tag] + anchors
    for a in anchors:
        ids.add(DETAIL_RE.search(a["href"]).group(1))
    return ids


def _is_furniture(tag: Tag) -> bool:
    """True for page chrome (search form, pager, footer) rather than a record."""
    if tag.name in ("form", "nav", "footer", "header"):
        return True
    if tag.find(["form", "nav", "footer"]) is not None:
        return True
    text = tag.get_text(" ")
    if PAGER_RE.search(text) or FOUND_RE.search(text):
        return True
    for a in tag.find_all("a", href=True):
        if re.search(r"[?&]page=\d+", a["href"]):
            return True
    return False


def _item_nodes(anchor: Tag, gid: str) -> List[Union[Tag, NavigableString]]:
    """Collect the DOM nodes that belong to one record.

    Climb from the title link to the largest ancestor that still holds only
    this record, then add following siblings until the next record or page
    chrome starts. That covers both "one wrapper per record" layouts and flat
    layouts where records are just consecutive siblings.
    """
    node: Tag = anchor
    while True:
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        if _detail_ids(parent) != {gid} or _is_furniture(parent):
            break
        node = parent

    nodes: List[Union[Tag, NavigableString]] = [node]
    for sib in node.next_siblings:
        if isinstance(sib, Tag):
            other = _detail_ids(sib)
            if other and other != {gid}:
                break
            if _is_furniture(sib):
                break
        nodes.append(sib)
    return nodes


def _abstract_from(item: Tag, lines: List[str]) -> Optional[str]:
    # 1) any element whose class mentions "abstract"
    best = ""
    for el in item.find_all(True):
        classes = " ".join(el.get("class") or []).lower()
        if "abstract" not in classes:
            continue
        text = clean_text(el.get_text(" "))
        text = re.sub(r"^Abstract\s*:?\s*", "", text)
        if text.lower() in ("show abstract", "hide abstract", ""):
            continue
        if len(text) > len(best):
            best = text
    # 2) otherwise, whatever follows a line that just says "Abstract"
    if len(best) < 30:
        for i, ln in enumerate(lines):
            if re.fullmatch(r"abstracts?\s*:?", ln, re.I):
                rest = [x for x in lines[i + 1:] if not PAGER_RE.search(x)]
                candidate = clean_text(" ".join(rest))
                if len(candidate) > len(best):
                    best = candidate
                break
    best = best.strip()
    return best if best and best not in ("-", "--", "N/A") else None


def _parse_item(item: Tag, gid: str, base_url: str) -> Article:
    # ---- title -----------------------------------------------------------
    title = ""
    for a in item.find_all("a", href=DETAIL_RE):
        text = clean_text(a.get_text(" "))
        if len(text) > len(title):
            title = text

    # ---- authors ---------------------------------------------------------
    raw_authors = [_ws(a.get_text(" ")) for a in item.find_all("a", href=AUTHOR_RE)]
    authors: List[str] = []
    for raw in raw_authors:
        name = clean_author(raw)
        if name and name not in authors:
            authors.append(name)

    # ---- links -----------------------------------------------------------
    doi = url = pdf_url = garuda_pdf_url = None
    for a in item.find_all("a", href=True):
        href = a["href"].strip()
        label = _ws(a.get_text(" ")).lower()
        if not href or href.startswith(("#", "javascript:")):
            continue
        m = DOI_HREF_RE.search(href)
        if m and not doi:
            doi = clean_doi(m.group(1))
            continue
        if "scholar.google" in href:
            continue
        full = requote_uri(urljoin(base_url + "/", href))
        if "full pdf" in label or "download.garuda" in href:
            garuda_pdf_url = garuda_pdf_url or full
        elif "download original" in label:
            pdf_url = pdf_url or full
        elif "original source" in label:
            url = url or full

    lines = _lines(item)
    if not doi:
        m = DOI_TEXT_RE.search(" ".join(lines))
        if m:
            doi = clean_doi(m.group(1))

    # ---- journal / volume / issue / year / publisher ---------------------
    def is_meta(candidate: str) -> bool:
        """A line that can be the journal line (not title, authors or links)."""
        if not candidate or candidate == title or candidate.startswith(title + " "):
            return False
        if "show abstract" in candidate.lower() or PUBLISHER_RE.match(candidate):
            return False
        stripped = candidate
        for raw in sorted(raw_authors, key=len, reverse=True):
            stripped = stripped.replace(raw, "")
        return bool(stripped.strip(" ;,"))

    publisher = source_line = None
    pub_idx = next((i for i, ln in enumerate(lines) if PUBLISHER_RE.match(ln)), None)
    if pub_idx is not None:
        publisher = PUBLISHER_RE.match(lines[pub_idx]).group(1).strip() or None
        if publisher is None and pub_idx + 1 < len(lines):
            nxt = lines[pub_idx + 1]
            if "show abstract" not in nxt.lower():
                publisher = nxt
        above = [ln for ln in lines[:pub_idx] if is_meta(ln)]
        if above:
            source_line = above[-1]
            # journal name and "Vol ..." rendered as two separate blocks
            if len(above) > 1 and parse_source_line(source_line)[0] is None:
                source_line = above[-2] + " " + source_line
    else:
        # no publisher label: look above the action row for a "Vol ... (yyyy)" line
        stop = next(
            (i for i, ln in enumerate(lines)
             if "show abstract" in ln.lower() or re.fullmatch(r"abstracts?\s*:?", ln, re.I)),
            len(lines),
        )
        for ln in lines[:stop]:
            if is_meta(ln) and (_VOL_RE.search(ln) or _YEAR_PAREN_RE.search(ln)):
                source_line = ln
                break

    journal, volume, issue, year, issue_title = parse_source_line(source_line or "")
    journal_link = item.find("a", href=JOURNAL_RE)
    if journal_link is not None and _ws(journal_link.get_text(" ")):
        journal = clean_text(journal_link.get_text(" "))

    return Article(
        garuda_id=gid,
        title=title,
        authors=authors,
        journal=clean_text(journal) if journal else None,
        volume=volume,
        issue=issue,
        year=year,
        issue_title=issue_title,
        source_line=source_line,
        publisher=clean_text(publisher) if publisher else None,
        doi=doi,
        abstract=_abstract_from(item, lines),
        url=url,
        pdf_url=pdf_url,
        garuda_pdf_url=garuda_pdf_url,
        garuda_url=f"{base_url}/documents/detail/{gid}",
    )


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

def _to_int(text: str) -> int:
    return int(re.sub(r"[.,]", "", text))


def parse_search_page(
    html: Union[str, bytes], base_url: str = DEFAULT_BASE_URL
) -> SearchPage:
    """Parse one ``/documents?...`` result page."""
    base_url = base_url.rstrip("/")
    if isinstance(html, bytes):
        soup = BeautifulSoup(html, "html.parser", from_encoding="utf-8")
    else:
        soup = BeautifulSoup(html, "html.parser")

    page_text = soup.get_text(" ")
    page = total_pages = total_records = None
    m = PAGER_RE.search(page_text)
    if m:
        page, total_pages, total_records = int(m.group(1)), int(m.group(2)), _to_int(m.group(3))
    else:
        m = FOUND_RE.search(page_text)
        if m:
            total_records = _to_int(m.group(1))

    query_echo = field_echo = None
    m = ECHO_RE.search(page_text)
    if m:
        query_echo, field_echo = _ws(m.group(1)), m.group(2).lower()

    first_anchor: Dict[str, Tag] = {}
    for a in soup.find_all("a", href=DETAIL_RE):
        first_anchor.setdefault(DETAIL_RE.search(a["href"]).group(1), a)

    articles: List[Article] = []
    for gid, anchor in first_anchor.items():
        holder = BeautifulSoup("<div></div>", "html.parser").div
        for node in _item_nodes(anchor, gid):
            holder.append(copy.copy(node))
        article = _parse_item(holder, gid, base_url)
        if article.title:
            articles.append(article)

    return SearchPage(
        articles=articles,
        page=page,
        total_pages=total_pages,
        total_records=total_records,
        query_echo=query_echo,
        field_echo=field_echo,
    )
