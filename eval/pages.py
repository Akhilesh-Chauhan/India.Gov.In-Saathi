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


def get_page(url):
    """{"status", "final", "text", "tls", "error"} for a URL; cached under eval/page_cache."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    # Official pages change; a stale cache would hide exactly the freshness problems we test for.
    if path.exists() and time.time() - path.stat().st_mtime < config.PAGE_CACHE_HOURS * 3600:
        return json.loads(path.read_text(encoding="utf-8"))
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
