"""Fetches cited pages once per URL (cached on disk), reusing check_sources.py."""
import csv
import hashlib
import json
import sys
import time
from urllib.parse import urlsplit

import config

sys.path.insert(0, str(config.ROOT))
from check_sources import API_SOURCES, bare, fetch, official  # noqa: E402


def ingested_domains(path=config.INGESTED_CSV):
    """Sources the bot can use: the crawled-site CSV plus the bot's own registry (eval/bot_sources.json, if saved)."""
    with open(path, encoding="utf-8-sig") as f:
        domains = {bare(r["Domain"].strip()) for r in csv.DictReader(f)}
    reg = config.HERE / "bot_sources.json"
    if reg.exists():
        domains |= {bare(i["domain"]) for i in json.loads(reg.read_text(encoding="utf-8"))["items"]}
    return frozenset(domains)


def index_domains(root=None):
    """Sites in the developers' export of the bot's live index (citizen-guide-indexed-data/*/_site.md 'domains' lines).
    The bot can cite these even when they are missing from the crawled-site CSV."""
    root = root or config.INDEX_EXPORT_DIR
    domains = set()
    for f in sorted(root.glob("*/_site.md")) if root.is_dir() else []:
        with f.open(encoding="utf-8", errors="replace") as fh:
            head = fh.read(3000)
        for line in head.splitlines():
            if line.startswith("- **domains:**"):
                domains |= {bare(d.strip()) for d in line.split(":**", 1)[1].split(",") if d.strip()}
    return frozenset(domains)


def available_to_bot(url, ingested, indexed=frozenset(), evidence=frozenset()):
    """Official and available to the bot. Official (QE decision 6 Nov 2026): a .gov.in / .nic.in or other official host,
    or a site in the bot's index export, its APIs or the ground-truth evidence. Available: the crawled list, the bot's
    registry, the APIs (DB/API), a subdomain of a crawled site, or the index export. Returns (ok, why)."""
    cls = host_class(url, ingested)
    host = bare(urlsplit(url).hostname or "")
    within = lambda sites: host in sites or any(host.endswith("." + d) for d in sites)
    in_index, in_evidence = within(indexed), within(evidence)
    if cls in ("crawled", "DB/API"):
        return True, ""
    if cls == "subdomain-of-crawled":
        return True, "" if in_index else "subdomain of a crawled site (confirm crawler coverage)"
    if in_index:
        return True, ("in the bot's index export, not in the crawled-site list" if cls != "NOT OFFICIAL" else
                      "in the bot's index export (counted as official), not in the crawled-site list")
    if cls == "NOT OFFICIAL" and not in_evidence:
        return False, "not an official or ingested host"
    why = "in the ground-truth evidence (counted as official)" if cls == "NOT OFFICIAL" else "official"
    return False, why + ", but not available to the bot (not in the crawled list, registry, index export or APIs)"


def get_page(url):
    """{"status", "final", "text", "tls", "error"} for a URL; cached under eval/page_cache."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    # Official pages change; a stale cache would hide exactly the freshness problems we test for.
    if path.exists() and time.time() - path.stat().st_mtime < config.PAGE_CACHE_HOURS * 3600:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if not cached.get("error"):  # a timeout is retried on the next run instead of being served for 12 hours
            return cached
    try:
        status, final, text, tls = fetch(url)
        page = {"status": status, "final": final, "text": " ".join(text.split()), "tls": tls.strip(), "error": None}
    except Exception as e:  # unreachable link is a finding, keep it
        page = {"status": getattr(e, "code", None), "final": url, "text": "", "tls": "", "error": str(e)[:300]}
    path.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    return page


def host_class(url, ingested):
    """crawled | DB/API | official-not-crawled | subdomain-of-crawled | NOT OFFICIAL."""
    host = bare(urlsplit(url).hostname or "")
    if host in API_SOURCES:
        return "DB/API"
    if host in ingested:
        return "crawled"
    if any(host.endswith("." + d) for d in ingested):
        return "subdomain-of-crawled"
    return "official-not-crawled" if official(host, ingested) else "NOT OFFICIAL"
