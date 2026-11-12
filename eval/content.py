"""What the bot actually had for a cited URL (fix of 5 Nov 2026).

The bot answers from its crawled index (exported in citizen-guide-indexed-data/) and, for schemes and services, from
two UMANG APIs (myScheme search, UMANG all-services). Checking its answers against today's live page is unfair when the
page changed after the crawl, and impossible for myScheme pages (JavaScript only). content_for(url) returns the text the
bot had: the API record for myScheme / UMANG URLs, else the indexed copy of the page, else None (caller uses the live page).
"""
import json
import re
from functools import lru_cache
from urllib.parse import parse_qs, unquote, urlsplit

import config

META_URL = re.compile(r"^- \*\*url:\*\* (.*)$", re.M)
META_CRAWLED = re.compile(r"^- \*\*crawledAt:\*\* (.*)$", re.M)
CHUNK_HDR = re.compile(r"^## Chunk \d+ of \d+.*$", re.M)
CHUNK_ID = re.compile(r"^chunkId: `.*$", re.M)


def url_key(u):
    """host (no www) + decoded path (no trailing slash, no index.html) + sorted query; scheme and case of host ignored."""
    p = urlsplit((u or "").strip())
    host = (p.hostname or "").lower().removeprefix("www.")
    path = re.sub(r"/(index|default)\.(html?|aspx?|php)$", "", unquote(p.path)).rstrip("/")
    q = "&".join(sorted(p.query.split("&"))) if p.query else ""
    return host + path + ("?" + q if q else "")


@lru_cache(maxsize=1)
def _url_map():
    """{url_key: relative file} for every indexed page; cached on disk next to the page cache."""
    root = config.INDEX_EXPORT_DIR
    if not root.is_dir():
        return {}
    cache = config.CACHE_DIR / "index_url_map.json"
    files = sorted(p for p in root.glob("*/*.md") if p.name != "_site.md")
    stamp = f"{root}|{len(files)}"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("stamp") == stamp:
            return d["map"]
    m = {}
    for p in files:
        with p.open(encoding="utf-8", errors="replace") as f:
            head = f.read(2500)
        u = META_URL.search(head)
        if u:
            m.setdefault(url_key(u.group(1).strip()), str(p.relative_to(root)))
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"stamp": stamp, "map": m}), encoding="utf-8")
    return m


def _index_page_text(rel):
    t = (config.INDEX_EXPORT_DIR / rel).read_text(encoding="utf-8", errors="replace")
    head, _, body = t.partition("\n---\n")
    crawled = (META_CRAWLED.search(head).group(1)[:10] if META_CRAWLED.search(head) else "")
    text = ""
    for chunk in CHUNK_HDR.split(CHUNK_ID.sub("", body)):
        c = " ".join(chunk.split()).strip(" -")
        if not c:
            continue
        probe = c[:60]
        k = text.rfind(probe, max(0, len(text) - 3000)) if text and len(probe) == 60 else -1
        if k != -1 and c.startswith(text[k:]):  # the chunker repeats the tail of the previous chunk
            c = c[len(text) - k:]
        text = (text + " " + c).strip()
    return text, crawled


@lru_cache(maxsize=1)
def _myscheme():
    p = config.API_SNAPSHOT_DIR / "myscheme_search.json"
    return {r.get("slug"): r for r in json.loads(p.read_text(encoding="utf-8"))} if p.exists() else {}


@lru_cache(maxsize=1)
def _umang():
    p = config.API_SNAPSHOT_DIR / "umang_allservices.json"
    return {str(r.get("serviceId")): r for r in json.loads(p.read_text(encoding="utf-8")).get("addServiceList", [])} if p.exists() else {}


def _snapshot_day():
    p = config.API_SNAPSHOT_DIR / "snapshot.json"
    return json.loads(p.read_text(encoding="utf-8")).get("fetched_at", "")[:10] if p.exists() else ""


def _api_text(url):
    p = urlsplit(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    if host == "myscheme.gov.in":
        m = re.match(r"^/schemes/([^/?#]+)", p.path)
        r = _myscheme().get(m.group(1)) if m else None
        if r:
            fields = [f"{k}: {v}" for k, v in r.items() if k not in ("id", "priority") and v not in (None, "", "None", [])]
            return " | ".join(fields), f"myScheme API record '{r.get('slug')}' (snapshot {_snapshot_day()})"
    if host.endswith("umang.gov.in"):
        qs = parse_qs(p.query)
        dept = (qs.get("dept_id") or [None])[0]
        if not dept:
            m = re.search(r"dept/(\d+)", unquote(p.path + "?" + p.query))
            dept = m.group(1) if m else None
        r = _umang().get(str(dept)) if dept else None
        if r:
            keys = ("serviceName", "description", "categoryName", "multicatname", "alliases", "website", "contact", "email",
                    "workingHours", "url")
            return " | ".join(f"{k}: {r.get(k)}" for k in keys if r.get(k)), f"UMANG all-services API record dept {dept} (snapshot {_snapshot_day()})"
    return None


def content_for(url):
    """(text, label) of what the bot had for this URL, or (None, None)."""
    if not config.CONTENT_FROM_INDEX:
        return None, None
    api = _api_text(url)
    if api:
        return api
    rel = _url_map().get(url_key(url))
    if rel:
        text, crawled = _index_page_text(rel)
        return text, f"indexed copy (crawled {crawled}, citizen-guide-indexed-data/{rel})"
    return None, None
