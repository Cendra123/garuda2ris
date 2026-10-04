"""Export one Garuda search to RIS.

Run:  python examples/smoke_free_area_policy.py
"""

import logging

from garuda2ris import crawl, write_ris

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Written with a hyphen on purpose: garuda2ris sends it as "smoke free area policy",
# because Garuda would read "smoke-free" as "smoke" WITHOUT "free".
articles = crawl(
    "smoke-free area policy",
    field="abstract",
    remove_duplicates=True,
    keywords=True,
    delay=1.0,
)
write_ris(articles, "smoke_free_area_policy.ris")

print(f"{len(articles)} records written to smoke_free_area_policy.ris")
for a in articles[:5]:
    print(f"  {a.year or '----'}  {a.title[:80]}")
