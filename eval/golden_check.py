"""Evidence for every expected (golden) answer: each key fact tied to an official page, the exact words on that page and
a dated copy of it, so an expected answer can be shown to be right as of the day it was checked.

Checkers follow golden_check.md and write runs/<run>/out/<ID>.json, one file per test case. The code fetches every cited
page itself, keeps a copy (runs/<run>/snapshots/) and confirms each quote is on the page word for word (evidence/).

  python golden_check.py export --run golden-20261027 [--size 20]      batch files of the test cases not done yet, by site
  python golden_check.py page --run golden-20261027 URL [--find fee]    the page text the quote check reads
  python golden_check.py check --run golden-20261027 [--ids Q-004]      fetch cited pages, keep copies, confirm the quotes
  python golden_check.py status --run golden-20261027                   progress and every open problem
  python golden_check.py audit --run golden-20261027 [--parts 4]       review packs: does each quote state its fact?
  python golden_check.py signoff --run golden-20261027                  golden_signoff.xlsx: every change, for the owner
  python golden_check.py apply --run golden-20261027                    write the checked answers into the golden workbook
      [--out FILE --provisional]   write a new workbook instead; --provisional includes changes still awaiting sign-off
  python golden_check.py selftest --run x                               offline check of the quote matching
Finished test cases are skipped, so the work can stop at any point and resume with the same commands.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

import config
from pages import host_class, ingested_domains
from workbook import load_rows, load_scenarios
from check_sources import UA, bare, official  # pages puts golden-tests/ on sys.path

STATUSES = ("confirmed", "changed", "added", "conflict", "unsupported", "manual")
NEED_QUOTE = ("confirmed", "changed", "added", "conflict")  # the code must find these quotes on an official page
REWRITE = ("changed", "added", "conflict", "unsupported")  # any of these replaces the expected answer text
OWNER = ("changed", "conflict", "unsupported", "manual")  # the owner approves or rejects each of these
MIN_QUOTE = 15  # letters and digits; shorter quotes ("Rs 75") prove nothing on their own
IST = timezone(timedelta(hours=5, minutes=30))
# Firewall and error pages some gov sites serve instead of the page; never keep these as the copy of a page.
BLOCKED = re.compile(r"web page blocked|access denied|request rejected|attack id|page not found|404 not found|forbidden", re.I)
DECISIONS = ("Approve", "Reject")


def is_official(url, ingested):
    """Official for an expected answer: check_sources.official, or a subdomain of a site the bot crawls (sdmis.nios.ac.in)."""
    return official(urlsplit(url).hostname or "", ingested) or host_class(url, ingested) == "subdomain-of-crawled"


def now():
    return datetime.now(IST).isoformat(timespec="seconds")


def squash(text):
    """Letters, digits and vowel signs only, lower case: survives whitespace, punctuation and markup differences."""
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return "".join(ch for ch in text if ch.isalnum() or unicodedata.category(ch).startswith("M"))


def on_page(quote, text):
    """Quote found in the page text, also where a PDF's bold text came out with every letter doubled ("TThhee")."""
    q, s = squash(quote), squash(text)
    return q in s or q in re.sub(r"(.)\1", r"\1", s)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)  # atomic: several checkers share snapshots/


def test_cases():
    """Every question and conversation in the golden workbook, with the expected answer as it stands."""
    rows, out = load_rows(), {}
    for i, r in rows.items():
        out[i] = {"id": i, "kind": "question", "site": bare(str(r.get("Expected source domain") or "")), "row": r,
                  "golden": str(r.get("Expected behaviour / golden answer") or "")}
    for s, sc in load_scenarios().items():
        refs = re.findall(r"Q-\d+", str(sc["ref"] or ""))
        site = out[refs[0]]["site"] if refs and refs[0] in out else ""
        out[s] = {"id": s, "kind": "conversation", "site": site, "row": sc, "refs": refs,
                  "golden": "\n".join(f"Turn {n}: {exp}" for n, (_, exp) in enumerate(sc["turns"], 1))}
    return out


def _seed_facts(seed_run):
    path = config.RUNS_DIR / seed_run / "checklist.jsonl" if seed_run else None
    if not path or not path.exists():
        return {}
    return {c["id"]: [x["item"] for x in c["items"] if x["type"] == "fact"]
            for c in map(json.loads, path.read_text(encoding="utf-8").splitlines())}


def export(run, size, seed_run):
    run_dir = config.RUNS_DIR / run
    (run_dir / "out").mkdir(parents=True, exist_ok=True)
    cases, seeds = test_cases(), _seed_facts(seed_run)
    todo = sorted((c for c in cases.values() if not (run_dir / "out" / f"{c['id']}.json").exists()),
                  key=lambda c: (c["site"], c["kind"], c["id"]))
    wave = 1 + max((int(p.name.split("_")[1]) for p in (run_dir / "batches").glob("wave_*")), default=0)
    wdir = run_dir / "batches" / f"wave_{wave:02d}"
    wdir.mkdir(parents=True)
    for b in range(0, len(todo), size):
        lines = []
        for c in todo[b:b + size]:
            r = c["row"]
            if c["kind"] == "question":
                chunk = " ".join(str(r.get(k) or "") for k in ("Index chunk URL", "Index chunk last updated")).strip()
                lines += [f"=== {c['id']} | {r.get('Priority')} | {r.get('Language')} | {r.get('Question type (concept note)')} "
                          f"| expected site: {c['site'] or 'none'} ({r.get('Source availability')})",
                          f"GOLDEN-FACT STATUS: {r.get('Golden-fact status')}",
                          f"QUESTION: {r.get('Query (type exactly)')}",
                          f"EXPECTED ANSWER NOW:\n{c['golden']}"]
                if r.get("Verification notes"):
                    lines.append(f"VERIFICATION NOTES: {r['Verification notes']}")
                if r.get("Golden sources (verified URLs)"):
                    lines.append(f"SOURCES FOUND EARLIER:\n{r['Golden sources (verified URLs)']}")
                if chunk:
                    lines.append(f"PAGE IN THE BOT'S INDEX: {chunk}")
            else:
                lines += [f"=== {c['id']} | conversation | {r['lang']} | {r['title']} | facts from {', '.join(c['refs']) or 'none'} "
                          f"| expected site: {c['site'] or 'none'}",
                          "USER TURNS: " + " / ".join(str(u) for u, _ in r["turns"]),
                          f"EXPECTED ANSWER NOW (one line per turn):\n{c['golden']}"]
            if seeds.get(c["id"]):
                lines.append("FACTS GRADED ON 19 OCT (a starting point, not evidence): " + " | ".join(seeds[c["id"]]))
            lines.append("")
        n = b // size + 1
        (wdir / f"batch_{n:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
        sites = Counter(c["site"] for c in todo[b:b + size])
        print(f"{wdir.name}/batch_{n:02d}.txt: {min(size, len(todo) - b)} test cases, sites {dict(sites.most_common(3))}")
    print(f"{len(todo)} of {len(cases)} test cases still to check")


# --- page copies -------------------------------------------------------------------------------------------------

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        resp, tls = urllib.request.urlopen(req, timeout=40), ""
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        # Many gov sites ship incomplete certificate chains; keep the page, flag it.
        resp, tls = urllib.request.urlopen(req, timeout=40, context=ssl._create_unverified_context()), "TLS certificate problem"
    return resp.read(), resp.status, resp.geturl(), tls, resp.headers.get_content_charset()


def _html_text(html):
    return " ".join(unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S | re.I)).split())


def _pdf_text(body):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(body)
        f.flush()
        # Layout mode keeps table rows together, raw mode keeps sentences together; a quote may match either.
        return "\n\n".join(subprocess.run(["pdftotext", *mode, f.name, "-"], capture_output=True, text=True).stdout
                           for mode in (["-layout"], []))


def _ocr(pdf_path, pages=25):
    """English text of a scanned PDF, read with Tesseract from the saved copy (first `pages` pages)."""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", "300", "-l", str(pages), "-png", str(pdf_path), f"{d}/p"], capture_output=True, check=True)
        return "\n\n".join(subprocess.run(["tesseract", str(img), "-", "-l", "eng"], capture_output=True, text=True).stdout
                           for img in sorted(Path(d).glob("p*.png")))


def _render(url, settle_ms=1500):
    """(html, text, final url) from headless Chrome, for pages that build their text with JavaScript."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        chrome = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome")  # else Playwright's own Chromium
        browser = p.chromium.launch(executable_path=chrome if os.path.exists(chrome) else None, headless=True)
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="en-IN", ignore_https_errors=True)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if resp is None or resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status if resp else 'no response'} in the browser")
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # pages that keep polling never go idle; take what has rendered
                pass
            page.wait_for_timeout(settle_ms)
            text = " ".join(page.inner_text("body").split())
            if len(text) < 2000 and BLOCKED.search(text):
                raise RuntimeError(f"the site served an error or firewall page: {text[:120]}")
            return page.content(), text, page.url
        finally:
            browser.close()


def snapshot(run_dir, url, render=False, ocr=False):
    """Fetch a page once per run and keep the copy: {url, final, http, fetched_at, sha256, file, text_file, rendered?}."""
    sdir = run_dir / "snapshots"
    key = hashlib.sha1(url.encode()).hexdigest()[:20]
    meta_path = sdir / f"{key}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    error = None
    if meta is None:
        try:
            body, status, final, tls, charset = _get(url)
            pdf = body[:4] == b"%PDF"
            text = _pdf_text(body) if pdf else _html_text(body.decode(charset or "utf-8", "replace"))
            if not pdf and len(text) < 2000 and BLOCKED.search(text):
                raise RuntimeError(f"the site served an error or firewall page: {text[:120]}")
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / f"{key}.{'pdf' if pdf else 'html'}").write_bytes(body)
            (sdir / f"{key}.txt").write_text(text, encoding="utf-8")
            meta = {"url": url, "final": final, "http": status, "tls": tls, "fetched_at": now(),
                    "sha256": hashlib.sha256(body).hexdigest(), "file": f"{key}.{'pdf' if pdf else 'html'}",
                    "text_file": f"{key}.txt", "pdf": pdf}
        except Exception as e:  # blocked, missing or broken: the browser may still get it
            error = f"{type(e).__name__}: {e}"[:300]
    small = meta is not None and meta.get("text_file") and not meta["pdf"] and \
        len((sdir / meta["text_file"]).read_text(encoding="utf-8")) < 800  # browser-only copies have no plain text
    thin = bool(meta and meta.get("rendered")) and \
        len((sdir / meta["rendered"]["text_file"]).read_text(encoding="utf-8")) < 800
    if (meta is None or render or small) and (not (meta or {}).get("rendered") or (render and thin)):
        try:
            html, text, final = _render(url, 8000 if thin else 1500)  # a near-empty copy: give the page's data time to load
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / f"{key}.rendered.html").write_text(html, encoding="utf-8")
            (sdir / f"{key}.rendered.txt").write_text(text, encoding="utf-8")
            rendered = {"final": final, "fetched_at": now(), "sha256": hashlib.sha256(html.encode()).hexdigest(),
                        "file": f"{key}.rendered.html", "text_file": f"{key}.rendered.txt"}
            meta = meta or {"url": url, "final": final, "http": None, "tls": "", "fetched_at": rendered["fetched_at"],
                            "sha256": None, "file": None, "text_file": None, "pdf": False, "plain_error": error}
            meta["rendered"] = rendered
        except Exception as e:
            if meta is None:
                return {"url": url, "error": error or f"{type(e).__name__}: {e}"[:300]}
    # OCR a PDF with no text layer, or on request (scanned pages behind a text annex, e.g. a Hindi gazette page)
    if meta.get("pdf") and "ocr" not in meta and (ocr or len(squash((sdir / meta["text_file"]).read_text(encoding="utf-8"))) < 200):
        try:  # a scanned PDF has no text layer: read the saved copy with OCR
            (sdir / f"{key}.ocr.txt").write_text(_ocr(sdir / meta["file"]), encoding="utf-8")
            meta["ocr"] = {"text_file": f"{key}.ocr.txt", "read_at": now()}
        except Exception as e:
            meta["ocr"] = {"error": f"{type(e).__name__}: {e}"[:200]}
    _write_json(meta_path, meta)
    return meta


def page_texts(run_dir, meta):
    sdir = run_dir / "snapshots"
    files = [meta.get("text_file"), (meta.get("rendered") or {}).get("text_file"), (meta.get("ocr") or {}).get("text_file")]
    return [(sdir / f).read_text(encoding="utf-8") for f in files if f]


def page(run, url, find, limit, render):
    run_dir = config.RUNS_DIR / run
    meta = snapshot(run_dir, url, render, ocr=render)  # --render also OCRs a PDF
    if meta.get("error"):
        raise SystemExit(f"could not fetch {url}: {meta['error']}")
    print(f"URL {url}\nFINAL {meta['final']} | HTTP {meta['http']} | fetched {meta['fetched_at']} | "
          f"official: {'yes' if is_official(meta['final'], ingested_domains()) else 'NO'} | site: {host_class(meta['final'], ingested_domains())}"
          f" | rendered: {'yes' if meta.get('rendered') else 'no'}{' | ' + meta['tls'] if meta.get('tls') else ''}")
    for n, text in enumerate(page_texts(run_dir, meta)):
        print(f"--- text {n + 1} of the copy ({len(text):,} characters; the last one is OCR if the PDF is scanned)")
        if not find:
            print(text[:limit])
            continue
        hits, shown = [m.start() for m in re.finditer(re.escape(find), text, re.I)], -10 ** 9
        print(f"{len(hits)} matches for {find!r}")
        for h in hits:
            if h - shown < 500:  # already inside the text printed for the previous match
                continue
            shown = h
            print(f"... {text[max(0, h - 300):h + 300]} ...\n")


# --- checking the checkers' files ----------------------------------------------------------------------------------

def verify_quote(run_dir, url, quote, ingested, ev):
    """Fetch the page, record its copy in ev, and return a problem or None."""
    if not url or not is_official(url, ingested):
        return f"{url or 'no url'} is not an official site"
    if len(squash(quote)) < MIN_QUOTE:
        return "quote too short; copy the whole sentence or table row that states the fact"
    meta = snapshot(run_dir, url)
    found = not meta.get("error") and any(on_page(quote, t) for t in page_texts(run_dir, meta))
    if not found and not meta.get("error") and not meta.get("pdf") and not meta.get("rendered"):
        meta = snapshot(run_dir, url, render=True)  # the words may only appear once JavaScript has run
        found = any(on_page(quote, t) for t in page_texts(run_dir, meta))
    if not found and meta.get("pdf") and "ocr" not in meta:
        meta = snapshot(run_dir, url, ocr=True)  # some pages of the PDF may be scanned
        found = any(on_page(quote, t) for t in page_texts(run_dir, meta))
    if meta.get("error"):
        return f"page could not be fetched ({meta['error']})"
    rendered = meta.get("rendered") or {}
    ev.update({"final": meta["final"], "http": meta["http"], "fetched_at": meta["fetched_at"],
               "sha256": meta["sha256"] or rendered.get("sha256"), "copy": meta["file"] or rendered.get("file"),
               "rendered": bool(rendered), "ocr": bool((meta.get("ocr") or {}).get("text_file")),
               "site": host_class(meta["final"], ingested), "quote_found": found})
    if not is_official(meta["final"], ingested):
        return f"{url} redirects to {meta['final']}, not an official site"
    if not found:
        return f"quote not found on {url}; copy it from `golden_check.py page` output"
    return None


def check_one(run_dir, case, d, ingested):
    problems, facts = [], []
    if d.get("id") != case["id"]:
        problems.append(f"id inside the file is {d.get('id')!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("checked_on", ""))):
        problems.append("checked_on must be the date checked, YYYY-MM-DD")
    items = d.get("facts")
    if not isinstance(items, list):
        return {"id": case["id"], "checked_at": now(), "facts": [], "problems": problems + ["facts must be a list"]}
    if not items and not str(d.get("no_facts_reason") or "").strip():
        problems.append("no facts: give no_facts_reason (for example a decline with nothing to look up)")
    for n, x in enumerate(items, 1):
        st, url, quote = x.get("status"), str(x.get("url") or "").strip(), str(x.get("quote") or "")
        ev = {"n": n, "status": st, "url": url}
        facts.append(ev)
        if st not in STATUSES or not str(x.get("fact") or "").strip():
            problems.append(f"fact {n}: needs a fact and a status from {STATUSES}")
            continue
        if st == "changed" and not str(x.get("was") or "").strip():
            problems.append(f"fact {n}: changed, so 'was' must give the old expected value")
        if st in ("unsupported", "manual") and not str(x.get("note") or "").strip():
            problems.append(f"fact {n}: {st}, so 'note' must say where you looked or why the code cannot read it")
        if st == "manual" and not url:
            problems.append(f"fact {n}: manual, so give the official url where a person can see it")
        if st not in NEED_QUOTE:
            continue
        also = x.get("also") or []
        if st == "conflict" and not (isinstance(also, list) and also):
            problems.append(f"fact {n}: conflict, so 'also' must give the other official page and its exact words")
            continue
        p = verify_quote(run_dir, url, quote, ingested, ev)
        problems += [f"fact {n}: {p}"] if p else []
        ev["also"] = []
        for a in also if st == "conflict" else []:
            ev["also"].append({"url": str(a.get("url") or "").strip()})
            p = verify_quote(run_dir, ev["also"][-1]["url"], str(a.get("quote") or ""), ingested, ev["also"][-1])
            problems += [f"fact {n} (other page): {p}"] if p else []
    rewrite = any(x.get("status") in REWRITE for x in items)
    if rewrite and not str(d.get("behaviour") or "").strip():
        problems.append("the expected answer is rewritten, so 'behaviour' must carry over what the bot must do")
    if rewrite and case["kind"] == "conversation":
        turns = d.get("turns")
        if not isinstance(turns, list) or len(turns) != len(case["row"]["turns"]) or not all(str(t).strip() for t in turns):
            problems.append(f"conversation rewritten, so 'turns' must give all {len(case['row']['turns'])} turn texts")
    return {"id": case["id"], "checked_at": now(), "facts": facts, "problems": problems}


def _out_files(run_dir):
    return {p.stem: p for p in sorted((run_dir / "out").glob("*.json"))}


def _evidence(run_dir, i):
    p = run_dir / "evidence" / f"{i}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _current(run_dir, i, out_path):
    """Evidence for this test case if it was made from the latest version of its out file."""
    p = run_dir / "evidence" / f"{i}.json"
    return _evidence(run_dir, i) if p.exists() and p.stat().st_mtime >= out_path.stat().st_mtime else None


def check(run, ids):
    run_dir, cases, ingested = config.RUNS_DIR / run, test_cases(), ingested_domains()
    for i, path in _out_files(run_dir).items():
        if ids and i not in ids:
            continue
        old = _current(run_dir, i, path)
        if not ids and old and not old["problems"]:
            continue
        if i not in cases:
            print(f"{i}: PROBLEM - not a test case in the golden workbook")
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            ev = {"id": i, "checked_at": now(), "facts": [], "problems": [f"not valid JSON ({e})"]}
        else:
            ev = check_one(run_dir, cases[i], d, ingested)
        _write_json(run_dir / "evidence" / f"{i}.json", ev)
        print(f"{i}: OK ({len(ev['facts'])} facts)" if not ev["problems"] else f"{i}: PROBLEM - " + " | ".join(ev["problems"]))


def _load_out(run_dir):
    return {i: json.loads(p.read_text(encoding="utf-8")) for i, p in _out_files(run_dir).items()}


def _numbers(text):
    """Figures of two or more digits, without thousands commas: "Rs 1,750 by 31.12.2026" -> {"1750", "31", "12", "2026"}."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*\d", str(text or ""))}


def uncovered_figures(case, d):
    """Figures in an expected answer that is kept as it is, which no listed fact or quote mentions: likely unchecked."""
    if any(x.get("status") in REWRITE for x in d.get("facts") or []):
        return set()  # rewritten answers contain only the listed facts
    listed = " ".join(" ".join(str(v) for v in [x.get("fact"), x.get("quote"), x.get("was"), x.get("note")]
                               + [a.get("quote") for a in x.get("also") or []]) for x in d.get("facts") or [])
    claims = re.split(r"\bFail if\b", case["golden"])[0]  # "Fail if" holds stale values the bot must not give
    return _numbers(re.sub(r"\bG\d{2}\b", "", claims)) - _numbers(listed)  # G05 etc. are guardrail labels


def status(run):
    run_dir, cases = config.RUNS_DIR / run, test_cases()
    outs = _out_files(run_dir)
    ok, problems, unchecked = [], [], []
    facts, sites, rewritten = Counter(), Counter(), 0
    for i, path in outs.items():
        ev = _current(run_dir, i, path)
        if ev is None:
            unchecked.append(i)
            continue
        (problems if ev["problems"] else ok).append(i)
        for p in ev["problems"]:
            problems.append(f"  {i}: {p}")
        sites.update(f.get("site", "-") for f in ev["facts"] if f.get("quote_found"))
    uncovered = {}
    for i, d in _load_out(run_dir).items():
        if i in cases and isinstance(d.get("facts"), list) and (u := uncovered_figures(cases[i], d)):
            uncovered[i] = sorted(u)
        if isinstance(d.get("facts"), list):
            facts.update(str(x.get("status")) for x in d["facts"])
            rewritten += any(x.get("status") in REWRITE for x in d["facts"])
    missing = sorted(set(cases) - set(outs))
    extra = sorted(set(outs) - set(cases))
    print(f"{len(outs)} of {len(cases)} test cases have a checker file; {len(ok)} checked with every quote found; "
          f"{len(unchecked)} not checked since last edit; {len(missing)} not started")
    print(f"facts: {dict(facts)} | expected answers to rewrite: {rewritten} | quotes found by site: {dict(sites)}")
    print(f"page copies kept: {len(list((run_dir / 'snapshots').glob('*.json'))) if (run_dir / 'snapshots').exists() else 0}")
    for line in [x for x in problems if x.startswith("  ")][:60]:
        print(line)
    if unchecked:
        print("not checked:", ", ".join(unchecked[:40]))
    if uncovered:
        print(f"{len(uncovered)} kept expected answers have figures no listed fact covers (check they are not unchecked claims):")
        for i, u in list(uncovered.items())[:40]:
            print(f"  {i}: {', '.join(u[:12])}")
    if extra:
        print("files that are not test cases:", ", ".join(extra))
    if len(ok) == len(cases) and not extra:
        print(f"ALL {len(cases)} TEST CASES CHECKED, EVERY QUOTE FOUND ON AN OFFICIAL PAGE")


# --- owner sign-off and applying the result ------------------------------------------------------------------------

def audit(run, parts, sample, seed=1):
    """Review packs for a second reader (golden_audit.md): every test case with a changed, added, conflicting,
    unsupported or manual fact, every list question, and a random sample of the rest. Split by test case, so two
    reviewers never edit the same file. Also lists, for each unsupported or manual fact, confirmed facts elsewhere
    that share most of its words (a sign another checker found the evidence)."""
    import random
    run_dir, cases, outs = config.RUNS_DIR / run, test_cases(), _load_out(config.RUNS_DIR / run)
    words = lambda s: {w for w in re.findall(r"[a-z0-9]{4,}", str(s).lower())}  # noqa: E731
    confirmed = [(i, x) for i, d in outs.items() for x in d.get("facts") or [] if x.get("status") in NEED_QUOTE]
    picked = [i for i, d in outs.items() if any(x.get("status") != "confirmed" for x in d.get("facts") or [])
              or "discovery" in str(cases[i]["row"].get("Question type (concept note)", "")).lower()]
    rest = sorted(set(outs) - set(picked))
    picked = sorted(picked + random.Random(seed).sample(rest, min(sample, len(rest))))
    adir = run_dir / "audit"
    adir.mkdir(exist_ok=True)
    for k in range(parts):
        lines = []
        for i in picked[k::parts]:
            d, c = outs[i], cases[i]
            q = c["row"].get("Query (type exactly)") if c["kind"] == "question" else c["row"]["title"]
            lines += [f"=== {i} | {c['row'].get('Question type (concept note)', 'conversation')} | {q}",
                      f"EXPECTED ANSWER BEFORE: {c['golden'][:1500]}"]
            for n, x in enumerate(d.get("facts") or [], 1):
                lines.append(f"  [{n}] {x.get('status')}{' (example)' if x.get('example') else ''}: {x.get('fact')}")
                if x.get("quote"):
                    lines.append(f"      QUOTE: {x['quote']}\n      PAGE: {x.get('url')}")
                for a in x.get("also") or []:
                    lines.append(f"      OTHER PAGE QUOTE: {a.get('quote')}\n      OTHER PAGE: {a.get('url')}")
                if x.get("note"):
                    lines.append(f"      NOTE: {x['note']}")
                if x.get("status") in ("unsupported", "manual"):
                    near = [(j, y) for j, y in confirmed if j != i and len(words(x["fact"]) & words(y["fact"])) >= max(3, len(words(x["fact"])) // 2)]
                    for j, y in near[:3]:
                        lines.append(f"      CONFIRMED ELSEWHERE? {j}: {y['fact']} | QUOTE: {y.get('quote', '')[:200]} | {y.get('url')}")
            if d.get("behaviour"):
                lines.append(f"  BEHAVIOUR: {d['behaviour']}\n  FAIL IF: {d.get('fail_if') or '-'}")
            lines.append("")
        (adir / f"part_{k + 1}.txt").write_text("\n".join(lines), encoding="utf-8")
        print(f"audit/part_{k + 1}.txt: {len(picked[k::parts])} test cases")
    print(f"{len(picked)} test cases to audit ({min(sample, len(rest))} sampled from {len(rest)} confirmed-only)")


def _day(d):
    return datetime.strptime(d["checked_on"], "%Y-%m-%d").strftime("%d %b %Y")


def new_golden(d, day):
    """The rewritten expected answer: only facts that were found on official pages, then the required behaviour."""
    live = [x for x in d["facts"] if x["status"] != "unsupported" and not x.get("_rejected")]
    sentence = lambda x: x["fact"].strip() if x["fact"].strip().endswith(".") else x["fact"].strip() + "."  # noqa: E731
    facts, examples = [sentence(x) for x in live if not x.get("example")], [sentence(x) for x in live if x.get("example")]
    parts = [f"Answer (official sources, checked {day}): " + " ".join(facts)] if facts else []
    if examples:  # list questions: any one correct, cited example satisfies the answer, not all of them
        parts.append("Acceptable examples (any one of these, or another correct scheme with its official criteria cited): "
                     + " ".join(examples))
    parts.append("Behaviour: " + d["behaviour"].strip())
    if str(d.get("fail_if") or "").strip():
        parts.append("Fail if: " + d["fail_if"].strip())
    return "\n".join(parts)


def _quote_line(x, ev):
    lines = []
    for src, e in [(x, ev or {})] + list(zip(x.get("also") or [], (ev or {}).get("also") or [])):
        copy = (f"{'OCR of scanned ' if e.get('ocr') else ''}copy {e['fetched_at'][:10]}" if e.get("fetched_at") else "no copy")
        lines.append(f"{src.get('url')} - \"{str(src.get('quote', ''))[:240]}\" [{e.get('site', '-')}, {copy}]")
    return "\n".join(lines)


SIGNOFF_COLUMNS = [("Test case", 10), ("Question", 40), ("Fact", 50), ("What happened", 13), ("Was (old expected value)", 34),
                   ("Official page", 40), ("Exact words on the page", 60), ("Page copied on", 18), ("Checker's note", 40),
                   ("Decision", 11), ("Owner's comment", 34)]


def signoff(run):
    run_dir, cases = config.RUNS_DIR / run, test_cases()
    outs = _load_out(run_dir)
    wb = Workbook()
    head = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")
    sheets = {"Changed or removed": OWNER, "Facts added": ("added",)}
    for k, (title, statuses) in enumerate(sheets.items()):
        ws = wb.active if k == 0 else wb.create_sheet()
        ws.title = title
        for n, (h, w) in enumerate(SIGNOFF_COLUMNS, 1):
            c = ws.cell(1, n, h)
            c.font, c.fill, c.alignment = head, PatternFill("solid", fgColor="1F3864"), wrap
            ws.column_dimensions[c.column_letter].width = w
        rows = []
        for i, d in outs.items():
            evs = {e["n"]: e for e in (_evidence(run_dir, i) or {}).get("facts", [])}
            q = cases[i]["row"].get("Query (type exactly)") if cases[i]["kind"] == "question" else cases[i]["row"]["title"]
            for n, x in enumerate(d.get("facts") or [], 1):
                if x.get("status") not in statuses:
                    continue
                ev = evs.get(n) or {}
                others = x.get("also") or []
                copied = (ev.get("fetched_at") or "") + (" (OCR of scanned copy)" if ev.get("ocr") else "")
                rows.append([i, q, x.get("fact"), x.get("status"), x.get("was"),
                             "\n".join([x.get("url") or ""] + [a.get("url", "") for a in others]),
                             "\n".join([x.get("quote") or ""] + [a.get("quote", "") for a in others]),
                             copied, x.get("note")])
        # by what happened, then by page: manual facts on one page sit together, so one look settles them all
        rows.sort(key=lambda v: (OWNER.index(v[3]) if v[3] in OWNER else 0, v[5], v[0]))
        r = 1
        for values in rows:
            r += 1
            for col, v in enumerate(values, 1):
                ws.cell(r, col, str(v or "")).alignment = wrap
                for col in (10, 11):
                    ws.cell(r, col).fill = PatternFill("solid", fgColor="FFF2CC")
        dv = DataValidation(type="list", formula1='"Approve,Reject"', allow_blank=True)
        dv.add(f"J2:J{max(r, 2)}")
        ws.add_data_validation(dv)
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = f"A1:K{max(r, 1)}"
        print(f"{title}: {r - 1} facts for the owner to decide")
    guide = wb.create_sheet("How to use", 0)
    guide.column_dimensions["A"].width = 120
    for r, line in enumerate([
            f"Expected answers checked against official pages (run {run}). Every quote below was found word for word on a "
            "dated copy of the official page that the code fetched and kept (runs/<run>/snapshots/).",
            "Changed or removed: decide every row (Approve or Reject in column J). Approve a 'changed' or 'conflict' row to "
            "use the new wording; Reject keeps the old expected answer for that test case. Approve an 'unsupported' row to "
            "remove the claim; Reject keeps it. 'manual' rows are on an official page the code could not read (image, "
            "scanned page it could not OCR, login, site down): open the page, then Approve to keep the fact or Reject to drop it.",
            "Facts added: facts taken from official pages for expected answers that had no fixed value. Blank counts as "
            "Approve; Reject a row to leave that fact out.",
            "New expected answers: the old and new text of every rewritten expected answer, with its evidence.",
            "Nothing is written into the golden workbook until every row in 'Changed or removed' has a decision "
            "(golden_check.py apply)."], 1):
        guide.cell(r, 1, line).alignment = wrap
    ws = wb.create_sheet("New expected answers")
    for n, (h, w) in enumerate([("Test case", 10), ("Question", 40), ("Expected answer before", 60),
                                ("Expected answer after", 60), ("Evidence (page, exact words, copy date)", 80)], 1):
        c = ws.cell(1, n, h)
        c.font, c.fill, c.alignment = head, PatternFill("solid", fgColor="1F3864"), wrap
        ws.column_dimensions[c.column_letter].width = w
    r = 1
    for i, d in outs.items():
        if not any(x.get("status") in REWRITE for x in d.get("facts") or []):
            continue
        r += 1
        evs = {e["n"]: e for e in (_evidence(run_dir, i) or {}).get("facts", [])}
        after = "\n".join(d["turns"]) if cases[i]["kind"] == "conversation" else new_golden(d, _day(d))
        q = cases[i]["row"].get("Query (type exactly)") if cases[i]["kind"] == "question" else cases[i]["row"]["title"]
        ev_text = "\n".join(_quote_line(x, evs.get(n)) for n, x in enumerate(d["facts"], 1) if x.get("url"))
        for col, v in enumerate([i, q, cases[i]["golden"], after, ev_text], 1):
            ws.cell(r, col, v).alignment = wrap
    print(f"New expected answers: {r - 1} rewritten")
    out = run_dir / "golden_signoff.xlsx"
    wb.save(out)
    print(f"wrote {out}")


def _decisions(run_dir):
    """{(test case, fact text): 'Approve' | 'Reject' | None} from the owner's sign-off workbook."""
    wb = load_workbook(run_dir / "golden_signoff.xlsx", read_only=True)
    return {(r[0], r[2]): (r[9] if r[9] in DECISIONS else None)
            for t in ("Changed or removed", "Facts added") for r in wb[t].iter_rows(min_row=2, values_only=True) if r[0]}


def apply(run, workbook_path, out=None, provisional=False):
    run_dir, cases = config.RUNS_DIR / run, test_cases()
    outs, decisions = _load_out(run_dir), _decisions(run_dir)
    to_decide = {(i, x["fact"]) for i, d in outs.items() for x in d["facts"] if x["status"] in OWNER}
    undecided = sorted(k for k in to_decide if decisions.get(k) is None)  # also catches a sign-off sheet older than the files
    bad = [i for i in cases if (ev := _evidence(run_dir, i)) is None or ev["problems"]]
    if bad or (undecided and not provisional):
        raise SystemExit(f"not ready: {len(bad)} test cases not checked clean (e.g. {bad[:5]}); "
                         f"{len(undecided)} changed/removed facts without a decision (e.g. {undecided[:3]})")
    pending = Counter(i for i, _ in undecided)  # provisional: these changes are in, as proposed, until the owner decides
    if out is None:
        backup = workbook_path.with_name(f"{workbook_path.stem}.before-{run}.xlsx")
        if not backup.exists():
            shutil.copy2(workbook_path, backup)
    wb = load_workbook(workbook_path)
    ws = wb["Test Queries"]
    col = {c.value: c.column for c in ws[1]}
    row_of = {ws.cell(r, col["Test ID"]).value: r for r in range(2, ws.max_row + 1)}
    sc_ws = wb["Conversation Scenarios"]
    sc_col = {c.value: c.column for c in sc_ws[1]}
    if "Owner sign-off" not in col:
        col["Owner sign-off"] = ws.max_column + 1
        ws.cell(1, col["Owner sign-off"], "Owner sign-off")
    signoff_text = lambda i: (f"PENDING: {pending[i]} changed/removed fact(s) in golden_signoff.xlsx" if pending[i]  # noqa: E731
                              else "approved" if any(x["status"] in OWNER for x in outs[i]["facts"]) else "not needed")
    kept, rewritten = [], 0
    for i, d in outs.items():
        evs = {e["n"]: e for e in _evidence(run_dir, i)["facts"]}
        for x in d["facts"]:
            x["_rejected"] = decisions.get((i, x["fact"])) == "Reject"
        if any(x["_rejected"] and x["status"] in ("changed", "conflict", "unsupported") for x in d["facts"]):
            kept.append(i)  # the owner kept the old value: leave this expected answer as it was
            continue
        day = _day(d)
        live = [x for x in d["facts"] if not x["_rejected"] and x["status"] != "unsupported"]
        rewrite = any(x["status"] in REWRITE for x in d["facts"])
        sources = "\n".join(_quote_line(x, evs.get(n)) for n, x in enumerate(d["facts"], 1) if x in live and x.get("url"))
        unsupported = [x["fact"] for x in d["facts"] if x["status"] == "unsupported" and not x["_rejected"]]
        notes = "; ".join(filter(None, [d.get("summary"), "removed, no official page states it: " + "; ".join(unsupported)
                                        if unsupported else ""]))
        if cases[i]["kind"] == "conversation":
            if rewrite:
                turn_rows = [r for r in range(2, sc_ws.max_row + 1) if sc_ws.cell(r, sc_col["Scenario"]).value == i]
                for r, text in zip(turn_rows, d["turns"]):
                    sc_ws.cell(r, sc_col["Expected bot behaviour at this turn"], text)
                rewritten += 1
            continue
        r = row_of[i]
        if rewrite:
            ws.cell(r, col["Expected behaviour / golden answer"], new_golden(d, day))
            rewritten += 1
        ws.cell(r, col["Golden sources (verified URLs)"], sources or None)
        ws.cell(r, col["Golden-fact status"], f"Verified on official page ({day}); exact words on a saved copy" if live
                else f"Behaviour only, no facts to check ({day}): {d.get('no_facts_reason') or 'every fact removed'}")
        ws.cell(r, col["Verification notes"], notes or None)
        ws.cell(r, col["Owner sign-off"], signoff_text(i))
    _final_sheet(wb, outs, signoff_text, run)
    target = out or workbook_path
    wb.save(target)
    print(f"{rewritten} expected answers rewritten; {len(kept)} kept as before by the owner: {kept[:20]}; "
          f"{len(pending)} test cases with changes still awaiting sign-off\n"
          + (f"backup of the old workbook: {backup}\n" if out is None else "") + f"wrote {target}")


def _final_sheet(wb, outs, signoff_text, run):
    """A readable first sheet: one row per test case with the expected answer the evaluation will use and its evidence."""
    q_rows = _sheet_rows(wb["Test Queries"])
    turns = {}
    for r in _sheet_rows(wb["Conversation Scenarios"]):
        turns.setdefault(r["Scenario"], []).append(r)
    ws = wb.create_sheet("Final golden", 0)
    head = [("Test case", 10), ("Type", 14), ("Priority", 8), ("Category", 20), ("Language", 14), ("Question / user turns", 45),
            ("Expected answer used in the evaluation", 80), ("Evidence: official page, exact words, copy date", 80),
            ("Golden status", 26), ("Owner sign-off", 22), ("Notes", 40)]
    for n, (h, w) in enumerate(head, 1):
        c = ws.cell(1, n, h)
        c.font, c.fill = Font(name="Arial", size=10, bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = w
    rows = [[r["Test ID"], r.get("Question type (concept note)"), r.get("Priority"), r.get("Category"), r.get("Language"),
             r.get("Query (type exactly)"), r.get("Expected behaviour / golden answer"), r.get("Golden sources (verified URLs)"),
             r.get("Golden-fact status"), r.get("Owner sign-off"), r.get("Verification notes")] for r in q_rows]
    for s, ts in turns.items():
        rows.append([s, "Multi-turn conversation", "", ts[0].get("Title"), ts[0].get("Language"),
                     "\n".join(f"Turn {n}: {t['User says (type exactly)']}" for n, t in enumerate(ts, 1)),
                     "\n".join(f"Turn {n}: {t['Expected bot behaviour at this turn']}" for n, t in enumerate(ts, 1)),
                     "", f"Facts from {ts[0].get('Golden facts in')}", signoff_text(s) if s in outs else "", outs.get(s, {}).get("summary")])
    for r, values in enumerate(rows, 2):
        for n, v in enumerate(values, 1):
            ws.cell(r, n, clean_cell(v)).alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:K{len(rows) + 1}"
    ws.cell(len(rows) + 3, 1, f"Built from run {run} by golden_check.py apply. The 'Test Queries' and 'Conversation "
            "Scenarios' sheets are what the evaluation reads; this sheet shows the same content for reading.")


def _sheet_rows(ws):
    it = ws.iter_rows(values_only=True)
    head = [str(h) if h is not None else "" for h in next(it)]
    return [dict(zip(head, r)) for r in it if any(v is not None for v in r)]


def clean_cell(v):
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    return ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v


def selftest():
    """Offline: quotes match across spacing, punctuation and scripts; words not on the page, short quotes and
    non-official sites are rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir, url = Path(tmp), "https://uidai.gov.in/en/selftest"
        key = hashlib.sha1(url.encode()).hexdigest()[:20]
        (run_dir / "snapshots").mkdir()
        (run_dir / "snapshots" / f"{key}.txt").write_text("filler " * 150 + "(iii) If done otherwise: ₹125* "
                                                           "आधार में पता अपडेट करने का शुल्क ₹75 है।", encoding="utf-8")
        _write_json(run_dir / "snapshots" / f"{key}.json", {
            "url": url, "final": url, "http": 200, "tls": "", "fetched_at": now(), "sha256": "-", "file": f"{key}.html",
            "text_file": f"{key}.txt", "pdf": False, "rendered": {"text_file": f"{key}.txt"}})  # rendered: no browser
        check = lambda u, q: verify_quote(run_dir, u, q, frozenset(), {})  # noqa: E731
        assert check(url, "(iii)  If done otherwise :\n ₹125*") is None
        assert check(url, "पता अपडेट करने का शुल्क ₹75 है") is None
        assert "not found" in check(url, "(iii) If done otherwise: ₹100 only")
        assert "not found" in check(url, "पता अपडेट करने का शुल्क ₹50 है")
        assert "too short" in check(url, "₹125*")
        assert on_page("Child Welfare Committee", "the CChhiilldd  WWeellffaarree  CCoommmmiitttteeee shall")
        assert not on_page("Child Welfare Board", "the CChhiilldd  WWeellffaarree  CCoommmmiitttteeee shall")
        assert "not an official site" in check("https://cleartax.in/aadhaar", "(iii) If done otherwise: ₹125*")
    print("GOLDEN CHECK SELFTEST PASSED")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["export", "page", "check", "status", "audit", "signoff", "apply", "selftest"])
    ap.add_argument("url", nargs="?", help="page: the URL to show")
    ap.add_argument("--run", required=True)
    ap.add_argument("--size", type=int, default=20, help="export: test cases per batch")
    ap.add_argument("--seed-run", default="umang-20261019", help="export: run whose checklist facts are shown as a start")
    ap.add_argument("--find", help="page: show only the text around these words")
    ap.add_argument("--limit", type=int, default=6000, help="page: characters to show without --find")
    ap.add_argument("--render", action="store_true", help="page: also open the page in headless Chrome (or OCR a PDF)")
    ap.add_argument("--ids", help="check: comma-separated test cases to (re)check")
    ap.add_argument("--parts", type=int, default=4, help="audit: number of review packs")
    ap.add_argument("--sample", type=int, default=60, help="audit: confirmed-only test cases to sample")
    ap.add_argument("--out", help="apply: write this new workbook instead of changing the golden workbook")
    ap.add_argument("--provisional", action="store_true", help="apply: include changes still awaiting sign-off, marked PENDING")
    a = ap.parse_intermixed_args()  # lets the URL come after the options
    if a.step == "page" and not a.url:
        ap.error("page needs a URL")
    {"export": lambda: export(a.run, a.size, a.seed_run),
     "page": lambda: page(a.run, a.url, a.find, a.limit, a.render),
     "check": lambda: check(a.run, set(a.ids.split(",")) if a.ids else None),
     "status": lambda: status(a.run), "signoff": lambda: signoff(a.run),
     "audit": lambda: audit(a.run, a.parts, a.sample),
     "apply": lambda: apply(a.run, config.WORKBOOK, Path(a.out) if a.out else None, a.provisional),
     "selftest": selftest}[a.step]()


if __name__ == "__main__":
    main()
