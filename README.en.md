# garuda2ris

**Crawl Garuda (Garba Rujukan Digital) search results into `.ris` files for
Zotero, Mendeley, EndNote, Rayyan and Covidence.**

[Garuda](https://garuda.kemdiktisaintek.go.id) is Indonesia's national index of
scholarly publications. It only offers RIS export one record at a time, from
each record's detail page, which makes it hard to use as a source in a
systematic literature review. `garuda2ris` walks all result pages of a search
and writes one file, with the abstract of every record.

- Python library and command-line tool
- Takes search words or a search URL copied from the browser
- Rewrites queries that Garuda's search box misreads (`smoke-free` *excludes*
  "free"; quotes are ignored)
- Checks every page against the search it asked for, so stale pages are not saved
- Merges records Garuda lists twice, and pulls keywords out of abstracts
- A ready-made notebook that runs several searches, merges the results and
  keeps a PRISMA-style search log:
  [`examples/garuda_multi_query.ipynb`](examples/garuda_multi_query.ipynb)

If you use it in your research, please [cite it](#citation).

*Bahasa Indonesia: [README.md](README.md)*

## Install

```bash
pip install git+https://github.com/Cendra123/garuda2ris.git
```

or from a copy of this repository:

```bash
git clone https://github.com/Cendra123/garuda2ris.git
pip install ./garuda2ris
```

Needs Python 3.9+, `requests` and `beautifulsoup4` (installed automatically).

## Command line

Give the search words and the field to search in. For example, every paper
Garuda lists for an author:

```bash
garuda2ris "Cendra Devayana Putra" --field author -o cendra.ris
garuda2ris "Bartolomeus Priya" --field author -o bartolomeus.ris
```

The tool prints its progress page by page and ends with the number of records
written next to the total Garuda reports, so you can see the result is
complete. (On 4 October 2026 Garuda listed 16 records for the first search.)

Add filters and clean-up as needed:

```bash
garuda2ris "Cendra Devayana Putra" --field author --year-from 2025 --dedupe --keywords -o cendra_2025.ris
```

Or paste the URL of a search you set up in the browser:

```bash
garuda2ris "https://garuda.kemdiktisaintek.go.id/documents?q=Cendra+Devayana+Putra&select=author" -o cendra.ris
```

| Option | What it does |
| --- | --- |
| `-o FILE` | Output file (default `garuda.ris`) |
| `-f, --field` | Search in `title` (default), `abstract`, `author` or `doi` |
| `--publisher NAME` | Garuda's "Publisher" search box |
| `--raw-query` | Send the search words exactly as typed (see "How Garuda reads a query") |
| `--year-from / --year-to` | Keep only records in this year range |
| `--drop-unknown-year` | With a year filter, also drop records that show no year |
| `--dedupe` | Merge records Garuda lists twice (same DOI or same title) |
| `--keywords` | Copy a trailing `Keywords: …` / `Kata kunci: …` list from the abstract into `KW` |
| `--invert-names` | Write `Rio Dewandika Putra` as `Putra, Rio Dewandika` |
| `--native` | Use Garuda's own RIS export for each record (see below) |
| `--no-pdf-links` | Leave PDF links (`L1`) out |
| `--max-pages N`, `--max-records N` | Stop early |
| `--delay SEC` | Pause between requests (default 1.0) |
| `--encoding utf-8-sig` | Add a BOM, for older EndNote on Windows |

## How Garuda reads a query (important)

Measured on the live site in October 2026:

| You type | What Garuda does |
| --- | --- |
| `kawasan tanpa rokok puskesmas` | Every word must be present, in any order. No phrase search. |
| `"kawasan tanpa rokok"` | Quotes change nothing: `"rokok tanpa kawasan" puskesmas` returns the same 22 titles. |
| `smoke-free hospital` | A hyphen **excludes** the next word: you get records with "smoke" and "hospital" that do **not** contain "free". |
| `no smoking` / `non smoking` | Very short words seem to be ignored: both return the same results. |

The hyphen rule was checked by counts in abstracts: `smoke hospital` = 242,
`smoke free hospital` = 34, `"smoke-free" hospital` = 208 = 242 - 34.

So search words given to this tool are rewritten first: hyphens between
letters become spaces and double quotes are dropped (`"smoke-free" hospital`
is sent as `smoke free hospital`). A leading hyphen (`rokok -elektrik`) is
kept, so deliberate exclusion still works. Use `--raw-query`
(`normalize=False` in Python) to send the words untouched. A pasted URL is
never rewritten; you get a warning instead.

## Python

```python
from garuda2ris import crawl, crawl_to_ris, write_ris

# one call
crawl_to_ris("Cendra Devayana Putra", "cendra.ris", field="author")

# or keep the records and work with them
articles = crawl("Cendra Devayana Putra", field="author", remove_duplicates=True, keywords=True)
articles += crawl("Bartolomeus Priya", field="author")

for a in articles[:3]:
    print(a.year, a.journal, "-", a.title)

recent = [a for a in articles if a.year and a.year >= 2025]
write_ris(recent, "cendra_bartolomeus_2025plus.ris")

import pandas as pd                      # optional: a spreadsheet of the records
pd.DataFrame(a.to_dict() for a in articles).to_excel("publications.xlsx", index=False)
```

Lower level:

```python
from garuda2ris import GarudaClient

client = GarudaClient(delay=2.0)
for article in client.search("Bartolomeus Priya", field="author", max_pages=3):
    print(article.title, article.authors)

page = client.fetch_page({"q": "Cendra Devayana Putra", "select": "author"}, page=2)
print(page.total_records, page.total_pages)
```

## What ends up in the RIS file

| RIS tag | Source on Garuda |
| --- | --- |
| `TY` | `JOUR`; `CONF` when the venue name says conference / proceeding / prosiding / seminar |
| `TI` | Title |
| `AU` | One per author, placeholder junk removed (`Minollah -` → `Minollah`) |
| `T2`, `JF` | Journal name |
| `VL`, `IS`, `PY` | Parsed from the "Vol 16, No 4 (2025): …" line |
| `PB` | Publisher |
| `DO` | DOI |
| `AB` | Abstract |
| `KW` | Only with `--keywords` |
| `UR` | "Original Source" link (the Garuda page if there is none) |
| `L1` | "Download Original" and Garuda "Full PDF" links |
| `L2` | The record's Garuda page |
| `AN`, `ID`, `DB` | Garuda record ID, database name |

Fields Garuda does not show are left out; nothing is guessed. Garuda's listing
has no page numbers, ISSN or publication date.

## How it works

1. Request `/documents?page=N&q=…&select=…` for N = 1, 2, … (10 records per page).
2. Read "Page X of Y | Total Record : N" to know when to stop. It also stops
   if a page brings no new records.
3. For each record, find the title link (`/documents/detail/<id>`), the author
   links (`/author/view/<id>`), the `doi.org` link, the labelled action links,
   the "Publisher :" line and the journal line above it, and the abstract.
4. Write the records as RIS (UTF-8, CRLF line endings).

The parser keys on those link patterns and labels, not on CSS class names, so
a restyle of the site should not break it.

### Stale pages

Garuda's `/documents` address sometimes answers with a leftover page from a
different search or a different page number. Every answer is therefore
checked against Garuda's own "Search *query*, by *field*" line and its
"Page X of Y" line. A wrong answer is fetched again from the equivalent
address `/documents/index/<token>`, which is then used for the rest of the
run. If that is wrong too, the search stops with `GarudaMismatch` instead of
saving records that belong to another search.

### `--native`

Each record's detail page has an "RIS" button
(`/citation/site/RIS/<id>`). With `--native` the file is assembled from those
official exports, adding the abstract and DOI from the listing when the export
lacks them. It costs one extra request per record, and any record whose export
cannot be fetched falls back to the record built from the listing.

## Limits and notes

- **Year filter is applied after download**, using the year parsed from each
  record. If you prefer Garuda's own "Filter By Year", set it in the browser
  and paste the resulting URL: all URL parameters are passed through unchanged.
- **Duplicates are common.** Garuda re-indexes journals, so the same paper can
  appear under two IDs. Use `--dedupe`, or let your reference manager do it.
- **Metadata is as good as the journal's OJS data.** Expect things like
  `Tukiman, MKM` (a degree in the name field) or a DOI containing spaces.
- **Author name order** is kept as Garuda shows it. `--invert-names` treats the
  last word as the family name, which is wrong for many Indonesian names.
- Be gentle: keep `--delay` at 1 second or more.
- If Garuda changes domain again, pass `--base-url` (or just paste a URL from
  the new domain).
- Behind a proxy or custom CA, pass your own session:
  `GarudaClient(session=my_requests_session)`.

## If the code does not work

If `garuda2ris` does not work as described, please contact
**Cendra Devayana Putra**:

- open an issue at <https://github.com/Cendra123/garuda2ris/issues>, or
- reach him through his GitHub profile, [@Cendra123](https://github.com/Cendra123).

Please include the command or query you ran, the full error message, the
output of `garuda2ris --version`, your Python version and the date of the
search. Garuda changes its pages and address from time to time, so a report
with these details is the fastest way to get a fix.

## Tests

```bash
pip install pytest rispy
pytest
```

The HTML files in `tests/fixtures/` are hand-built stand-ins for Garuda result
pages (two deliberately different layouts) filled with real records from the
live listing; they are not captured pages.

## Citation

If this software helps your work, for example to build the search set of a
literature review, please cite it:

> Putra, C. D., & Priya, B. (2026). *garuda2ris: Crawl Garuda (Garba Rujukan
> Digital) search results into RIS* (Version 0.2.0) [Computer software].
> https://github.com/Cendra123/garuda2ris

```bibtex
@software{putra_priya_garuda2ris_2026,
  author  = {Putra, Cendra Devayana and Priya, Bartolomeus},
  title   = {garuda2ris: Crawl Garuda (Garba Rujukan Digital) search results into RIS},
  year    = {2026},
  version = {0.2.0},
  url     = {https://github.com/Cendra123/garuda2ris}
}
```

GitHub also offers these under **Cite this repository** in the sidebar (it
reads [`CITATION.cff`](CITATION.cff)).

Please also name Garuda itself as the data source in your methods section,
with the date you ran each search.

## Responsible use

Garuda is a public service run by the Indonesian ministry responsible for
higher education. Keep the delay between requests at one second or more, do
not run searches in parallel, and use the data for research and reference
management.

## License

MIT. See [LICENSE](LICENSE).
