"""Snapshot the two UMANG APIs the bot reads for schemes and services (shared by the owner on 4 Nov 2026).

  myScheme search:   https://myscheme-prod-api.umangapp.in/search/v7/schemes?size=100&lang=en&from=N&q=&sort=multiple_sort
  UMANG services:    https://cache.umang.gov.in/core-dept/1.0/allservices?lang=en&os=web&mod=app&ldate=&depttype=all&st=

Keys come from eval/.env (MYSCHEME_API_KEY, UMANG_API_KEY); never write them into artifacts.
Usage: .venv/bin/python artifacts/scripts/fetch_api_snapshots.py <repo root> [out dir, default artifacts/data/api_snapshots/<today>]
Writes myscheme_search.json (every record's 13 summary fields), myscheme_facets.json (the facet counts of the full set),
umang_allservices.json (the response's pd block), and snapshot.json (when, how many, which URLs).
"""
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timezone

R = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else f"{R}/artifacts/data/api_snapshots/{date.today():%Y%m%d}"
for line in open(f"{R}/eval/.env", encoding="utf-8"):
    line = line.split("#", 1)[0].strip()
    if "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
MYS = "https://myscheme-prod-api.umangapp.in/search/v7/schemes?size=100&lang=en&from={start}&q=&sort=multiple_sort"
UMG = "https://cache.umang.gov.in/core-dept/1.0/allservices?lang=en&os=web&mod=app&ldate=&depttype=all&st="
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"


def get(url, key, accept="application/json"):
    req = urllib.request.Request(url, headers={"x-api-key": key, "Referer": "https://web.umang.gov.in/", "User-Agent": UA, "Accept": accept})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - retry then give up
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1} after {type(e).__name__}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))


def main():
    os.makedirs(OUT, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mk, uk = os.environ.get("MYSCHEME_API_KEY"), os.environ.get("UMANG_API_KEY")
    if not (mk and uk):
        sys.exit("MYSCHEME_API_KEY and UMANG_API_KEY must be set in eval/.env")
    records, start, total, facets = [], 0, None, None
    while total is None or start < total:
        d = get(MYS.format(start=start), mk)
        hits = d["data"]["hits"]
        total = int(hits["page"]["total"])
        if facets is None:  # the facet counts (category, level, ministry, ...) that the search page shows for the full set
            facets = {f["identifier"]: {"label": f.get("label"), "entries": f.get("entries", [])} for f in d["data"].get("facets", [])}
        for h in hits["items"]:
            records.append({"id": h.get("id"), **h.get("fields", {})})
        start += 100
        print(f"  myScheme {len(records)}/{total}", flush=True)
    json.dump(records, open(f"{OUT}/myscheme_search.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(facets or {}, open(f"{OUT}/myscheme_facets.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    u = get(UMG, uk, "application/json, text/plain, */*")
    pd = u.get("pd") or {}
    json.dump(pd, open(f"{OUT}/umang_allservices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    meta = {"fetched_at": started, "myscheme_url": MYS.replace("{start}", "N"), "myscheme_records": len(records), "myscheme_total_reported": total,
            "umang_url": UMG, "umang_services": len(pd.get("addServiceList", [])), "umang_rc": u.get("rc"), "umang_rd": u.get("rd")}
    json.dump(meta, open(f"{OUT}/snapshot.json", "w", encoding="utf-8"), indent=1)
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
