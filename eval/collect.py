"""Send golden queries to the bot and snapshot the answers, or import answers testers pasted into the workbook.

Examples:
  python collect.py --run demo1 --priority P0            # ask the bot (needs eval/bot_curl.txt)
  python collect.py --run demo1 --scenarios              # multi-turn Conversation Scenarios
  python collect.py --run manual1 --import-workbook      # use the 'Actual response' / 'Sources shown' columns
  python collect.py --run demo1 --retry-errors           # ask again what the bot failed to answer (add --scenarios for
                                                         # conversations); run_all.sh does this once after collecting
Re-running the same --run skips IDs already collected, so an interrupted run can be resumed.
"""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone

import config
import saathi
from bot_client import URL_RE, ask
from workbook import load_rows, load_scenarios


def lang_for(language):
    """The Hindi interface sends accept-language: hi; Hinglish users typically type in the English interface."""
    return "hi" if str(language).startswith("Hindi") else "en"


def ask_bot(query, language, conversation=None, resolve_clarify=True):
    if config.BOT_ADAPTER != "saathi":
        return ask(query)
    lang = lang_for(language)
    snap = saathi.ask(query, lang=lang, conversation=conversation)
    if resolve_clarify and conversation is None and snap.get("kind") == "clarify":
        resolved, picks = saathi.resolve_clarify(query, snap, lang=lang)
        if resolved:  # keep the clarifying turn for the response-flow check, score the content of the answer after it
            first = {k: snap.get(k) for k in ("answer", "clarify", "latency_s", "first_token_s", "server_timings")}
            snap = {**resolved, "clarify_first": first, "clarify_choice": picks}
    return snap


def _done_ids(path):
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _append(path, rec):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def set_aside_errors(path):
    """Move the records whose bot call failed (an error, or a conversation turn without an answer) from `path` to
    errors_first_attempt.jsonl beside it, so the next collection asks them again. Returns their IDs."""
    if not path.exists():
        return []
    good, bad = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            failed = (any(t.get("error") or not (t.get("answer") or "").strip() for t in rec["turns"]) if "turns" in rec
                      else bool(rec.get("error")))
            (bad if failed else good).append(line)
    if bad:
        with (path.parent / "errors_first_attempt.jsonl").open("a", encoding="utf-8") as f:
            f.write("\n".join(bad) + "\n")
        path.write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")
    return [json.loads(x)["id"] for x in bad]


def select(rows, ids=None, priority=None, category=None, limit=None):
    picked = [r for r in rows.values()
              if (not ids or r["Test ID"] in ids)
              and (not priority or r["Priority"] in priority)
              and (not category or category.lower() in (r["Category"] or "").lower())]
    return picked[:limit] if limit else picked


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run name (folder under eval/runs)")
    ap.add_argument("--ids", help="comma-separated Test IDs, e.g. Q-001,Q-046 (with --scenarios: MT-12)")
    ap.add_argument("--priority", nargs="*", help="e.g. P0 P1")
    ap.add_argument("--category", help="substring of Category, e.g. 'Tax'")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between bot calls (be gentle with staging)")
    ap.add_argument("--scenarios", action="store_true", help="run the multi-turn Conversation Scenarios")
    ap.add_argument("--import-workbook", action="store_true", help="read tester-pasted answers instead of calling the bot")
    ap.add_argument("--no-resolve-clarify", action="store_true", help="do not answer the bot's clarifying chips")
    ap.add_argument("--retry-errors", action="store_true",
                    help="ask again the answers (or conversations) whose bot call failed; the failed attempts are kept in "
                         "errors_first_attempt.jsonl")
    a = ap.parse_args()

    run_dir = config.RUNS_DIR / a.run
    run_dir.mkdir(parents=True, exist_ok=True)
    if a.retry_errors:
        again = set_aside_errors(run_dir / ("conversations.jsonl" if a.scenarios else "responses.jsonl"))
        print(f"asking again {len(again)} {'conversation' if a.scenarios else 'answer'}(s) whose bot call failed"
              + (f": {', '.join(again)}" if again else ""))

    if a.scenarios:
        out = run_dir / "conversations.jsonl"
        done = _done_ids(out)
        wanted = set(a.ids.split(",")) if a.ids else None  # --ids picks conversations too (MT-12); none if it names none
        for sid, sc in load_scenarios().items():
            if sid in done or (wanted is not None and sid not in wanted):
                continue
            session, turns, conv = str(uuid.uuid4()), [], {}
            for user_text, _ in sc["turns"]:
                snap = (ask_bot(user_text, sc["lang"], conversation=conv) if config.BOT_ADAPTER == "saathi"
                        else ask(user_text, session_id=session))
                turns.append({"user": user_text, **{k: v for k, v in snap.items() if k != "raw"}})
                time.sleep(a.delay)
            _append(out, {"id": sid, "session_id": session, "turns": turns,
                          "collected_at": datetime.now(timezone.utc).isoformat()})
            print(f"{sid}: {len(turns)} turns")
        return

    out = run_dir / "responses.jsonl"
    done = _done_ids(out)
    rows = select(load_rows(), set(a.ids.split(",")) if a.ids else None, a.priority, a.category, a.limit)
    for r in rows:
        if r["Test ID"] in done:
            continue
        query = r["Query (type exactly)"]
        if a.import_workbook:
            answer = r.get("Actual response (summary / screenshot ref)") or ""
            if not answer:
                continue
            shown = str(r.get("Sources shown (URLs)") or "")
            snap = {"answer": answer, "sources": list(dict.fromkeys(URL_RE.findall(shown + " " + answer))),
                    "raw": "", "status": None, "latency_s": None, "error": None, "origin": "workbook"}
        else:
            snap = {**ask_bot(query, r["Language"], resolve_clarify=not a.no_resolve_clarify), "origin": "bot"}
            time.sleep(a.delay)
        _append(out, {"id": r["Test ID"], "query": query, **snap,
                      "collected_at": datetime.now(timezone.utc).isoformat()})
        print(f"{r['Test ID']}: {snap.get('error') or str(snap.get('kind')) + ', ' + str(len(snap['answer'])) + ' chars, '}"
              f"{len(snap['sources'])} sources, {snap.get('latency_s')}s", flush=True)


if __name__ == "__main__":
    main()
