"""Fills the automatic columns of the 'Source Check' sheet in golden_test_cases.xlsx.

For each pasted cited URL: is the host official, does it open, where does it redirect,
does the page text contain the claimed figure/text, and is it in the ingested URL set.

Usage: python3 check_sources.py golden_test_cases_phase1.xlsx [ingested-websites.csv]
"""
import csv
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from html import unescape
from urllib.parse import urlsplit

from openpyxl import load_workbook

# Official service providers outside gov.in/nic.in (PAN, NPS, RBI). Extend as needed.
EXTRA_OFFICIAL = {"rbi.org.in", "protean-tinfopvt.com", "nsdl.co.in", "utiitsl.com", "licindia.in"}
# Not crawled, but served to the bot from internal DB/API (developers, 14-Oct-2026).
API_SOURCES = {"myscheme.gov.in", "umang.gov.in", "web.umang.gov.in"}
UA = "Mozilla/5.0 (golden-test source checker; NeGD)"


def bare(host):
    return host.lower().split(":")[0].removeprefix("www.")


def official(host, ingested=frozenset()):
    host = bare(host)
    return host.endswith((".gov.in", ".nic.in")) or host in ("gov.in", "nic.in") or host in ingested or \
        any(host == d or host.endswith("." + d) for d in EXTRA_OFFICIAL)


def norm(text):
    # Compare without commas, currency marks and extra spaces: "Rs. 1,750" ~ "1750".
    text = re.sub(r"(rs\.?|₹|inr)", "", text.lower())
    return re.sub(r"\s+", " ", text.replace(",", "")).strip()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        tls = ""
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        # Many gov sites ship incomplete cert chains; still check content but flag it.
        resp = urllib.request.urlopen(req, timeout=30, context=ssl._create_unverified_context())
        tls = " (TLS cert problem)"
    body = resp.read()
    if body[:4] == b"%PDF":
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(body)
            f.flush()
            text = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    else:
        html = body.decode(resp.headers.get_content_charset() or "utf-8", "replace")
        text = unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S | re.I))
    return resp.status, resp.geturl(), text, tls


def main(xlsx, ingested_file=None):
    ingested = frozenset()
    if ingested_file:  # ingested list is per domain: the CSV's Domain column is the trust boundary
        with open(ingested_file, encoding="utf-8-sig") as f:
            ingested = frozenset(bare(r["Domain"].strip()) for r in csv.DictReader(f))
    wb = load_workbook(xlsx)
    ws = wb["Source Check"]
    for row in ws.iter_rows(min_row=2):
        test_id, url, claim = (c.value for c in row[:3])
        if not url or test_id == "EXAMPLE":
            continue
        url = str(url).strip()
        row[3].value = "YES" if official(urlsplit(url).hostname or "", ingested) else "NO - NOT OFFICIAL"
        try:
            status, final, text, tls = fetch(url)
            row[4].value = f"{status}{tls}"
            row[5].value = final
            if row[3].value == "YES" and not official(urlsplit(final).hostname or "", ingested):
                row[3].value = "NO - REDIRECTS OFF-GOV"
            if claim:
                found = norm(str(claim)) in norm(text)
                # SPA pages (e.g. Passport Seva) render content with JavaScript, so raw HTML may lack it.
                row[6].value = "YES" if found else "NOT IN RAW TEXT - check manually"
        except Exception as e:  # report every failure in the sheet instead of stopping the run
            row[4].value = f"ERROR: {getattr(e, 'code', '')} {e}"[:200]
        if ingested:
            host = bare(urlsplit(url).hostname or "")
            row[7].value = ("YES (DB/API)" if host in API_SOURCES else "YES (crawled)" if host in ingested
                            else "SUBDOMAIN of crawled - confirm with devs" if any(host.endswith("." + d) for d in ingested)
                            else "NO")
        print(test_id, row[3].value, row[4].value, row[6].value, sep=" | ")
    wb.save(xlsx)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:3])
