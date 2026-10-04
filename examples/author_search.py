"""Export every paper Garuda lists for an author to RIS.

Run:  python examples/author_search.py
"""

import logging

from garuda2ris import crawl, dedupe, write_ris

logging.basicConfig(level=logging.INFO, format="%(message)s")

AUTHORS = ["Cendra Devayana Putra", "Bartolomeus Priya"]

articles = []
for name in AUTHORS:
    found = crawl(name, field="author", keywords=True, delay=1.0)
    print(f"{name}: {len(found)} records")
    articles += found

# a paper the two wrote together is found by both searches: keep it once
articles = dedupe(articles)
write_ris(articles, "authors.ris")

print(f"{len(articles)} records written to authors.ris")
for a in sorted(articles, key=lambda a: a.year or 0, reverse=True)[:5]:
    print(f"  {a.year or '----'}  {a.title[:80]}")
