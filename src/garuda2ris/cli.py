"""Command line: ``garuda2ris "kawasan tanpa rokok" --field abstract -o out.ris``."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from . import __version__
from .api import crawl_to_ris
from .client import SEARCH_FIELDS, GarudaClient, GarudaError
from .parser import DEFAULT_BASE_URL


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="garuda2ris",
        description="Crawl a Garuda (Garba Rujukan Digital) search and save it as .ris",
    )
    p.add_argument("query", help="search words, or a full Garuda search URL copied from the browser")
    p.add_argument("-o", "--output", default="garuda.ris", help="output file (default: garuda.ris)")
    p.add_argument("-f", "--field", default="title", choices=SEARCH_FIELDS,
                   help="what to search in (ignored when a URL is given; default: title)")
    p.add_argument("--publisher", help="restrict to a publisher (ignored when a URL is given)")
    p.add_argument("--raw-query", action="store_true",
                   help="send the search words exactly as typed (by default hyphens inside "
                        "words and double quotes are removed, because Garuda misreads them)")
    p.add_argument("--year-from", type=int, metavar="YYYY", help="keep records from this year on")
    p.add_argument("--year-to", type=int, metavar="YYYY", help="keep records up to this year")
    p.add_argument("--drop-unknown-year", action="store_true",
                   help="with a year filter, also drop records whose year Garuda does not show")
    p.add_argument("--dedupe", action="store_true", help="merge records Garuda lists twice")
    p.add_argument("--keywords", action="store_true",
                   help="copy a trailing 'Keywords: ...' list from the abstract into KW fields")
    p.add_argument("--invert-names", action="store_true",
                   help="write 'First Last' author names as 'Last, First'")
    p.add_argument("--native", action="store_true",
                   help="use Garuda's own RIS export per record (one extra request each)")
    p.add_argument("--no-pdf-links", action="store_true", help="leave PDF links (L1) out")
    p.add_argument("--max-pages", type=int, metavar="N", help="stop after N result pages")
    p.add_argument("--max-records", type=int, metavar="N", help="stop after N records")
    p.add_argument("--delay", type=float, default=1.0, metavar="SEC",
                   help="pause between requests (default: 1.0)")
    p.add_argument("--timeout", type=float, default=30.0, metavar="SEC")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Garuda origin, if it moves again")
    p.add_argument("--encoding", default="utf-8", help="output encoding (utf-8-sig adds a BOM)")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress messages")
    p.add_argument("--version", action="version", version=f"garuda2ris {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    client = GarudaClient(args.base_url, delay=args.delay, timeout=args.timeout)
    try:
        articles = crawl_to_ris(
            args.query,
            args.output,
            client=client,
            field=args.field,
            publisher=args.publisher,
            normalize=not args.raw_query,
            year_from=args.year_from,
            year_to=args.year_to,
            keep_unknown_year=not args.drop_unknown_year,
            remove_duplicates=args.dedupe,
            keywords=args.keywords,
            invert_names=args.invert_names,
            native=args.native,
            include_pdf_links=not args.no_pdf_links,
            max_pages=args.max_pages,
            max_records=args.max_records,
            encoding=args.encoding,
        )
    except GarudaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    total = client.total_records
    reported = f" (Garuda reports {total} for this search)" if total is not None else ""
    print(f"wrote {len(articles)} records to {args.output}{reported}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
