"""Client for the Saathi citizen-guidance API behind https://web.umang.gov.in/citizenbot/ (protocol cg-ask/1).

POST {SAATHI_API}/ask with {"question", "clientId"[, "conversationId", "history", "clarifications"]}
returns a server-sent-events stream: ready, status, source, citation, answer.delta, answer.done, end.
Request shape captured from the web app on 16-Oct-2026.
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid

SAATHI_API = os.environ.get("SAATHI_API", "https://apigw-uat.umangapp.in/citizen-guidance-be/v1")
TIMEOUT = float(os.environ.get("BOT_TIMEOUT", "90"))
CLIENT_ID = str(uuid.uuid4())  # one anonymous client per run, like one browser


def parse_events(raw):
    """[(event_name, data_dict), ...] from an SSE body."""
    out = []
    for block in raw.split("\n\n"):
        name, data = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            try:
                out.append((name, json.loads("\n".join(data))))
            except ValueError:
                out.append((name, {"raw": "\n".join(data)}))
    return out


def ask(question, lang="en", conversation=None, clarifications=None):
    """One question -> snapshot dict. `conversation` ({"conversationId", "history"}) is updated in place."""
    body = {"question": question, "clientId": CLIENT_ID}
    if conversation and conversation.get("conversationId"):
        body["conversationId"] = conversation["conversationId"]
        body["history"] = conversation["history"]
    if clarifications:
        body["clarifications"] = clarifications
    req = urllib.request.Request(
        SAATHI_API + "/ask", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Accept": "text/event-stream", "Content-Type": "application/json", "Accept-Language": lang,
                 "Idempotency-Key": str(uuid.uuid4()), "Origin": "https://web.umang.gov.in",
                 "Referer": "https://web.umang.gov.in/", "User-Agent": "Mozilla/5.0 (NeGD golden-test harness)"})
    t0 = time.monotonic()
    first_token = None
    lines = []
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace")
                if first_token is None and line.startswith("event: answer.delta"):
                    first_token = time.monotonic() - t0
                lines.append(line)
    except urllib.error.HTTPError as e:
        return _snapshot_error(question, lang, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}", t0, e.code)
    except Exception as e:  # timeouts and network failures are findings, not crashes
        return _snapshot_error(question, lang, f"{type(e).__name__}: {e}", t0, None)
    raw = "".join(lines)
    total = time.monotonic() - t0
    events = parse_events(raw)
    ready = next((d for n, d in events if n == "ready"), {})
    done = next((d for n, d in events if n == "answer.done"), {})
    errors = [d for n, d in events if n and "error" in n]
    citations = done.get("citations") or [d for n, d in events if n == "citation"]
    suggested = done.get("suggestedLinks") or []
    checked = [{"domain": d["source"].get("domain"), "siteName": d["source"].get("siteName"), "state": d.get("state"),
                "pages": d["source"].get("pages", [])} for n, d in events if n == "source" and "source" in d]
    answer = done.get("text") or "".join(d.get("text", "") for n, d in events if n == "answer.delta")
    snap = {
        "answer": answer, "kind": done.get("kind"), "grounding": done.get("grounding"), "cached": done.get("cached"),
        "sources": list(dict.fromkeys([c["url"] for c in citations if c.get("url")] + [s["url"] for s in suggested if s.get("url")])),
        "citations": [{k: c.get(k) for k in ("n", "url", "title", "siteName", "lastUpdated", "fetchedAt", "trust", "snippet")}
                      for c in citations],
        "suggested_links": suggested, "sources_checked": checked, "follow_ups": done.get("followUps") or [],
        "clarify": done.get("clarify"), "answer_language": ready.get("answerLanguage"),
        "conversation_id": ready.get("conversationId"), "answer_id": done.get("answerId") or ready.get("answerId"),
        "request_id": ready.get("requestId"), "server_timings": done.get("timings"),
        "latency_s": round(total, 3), "first_token_s": round(first_token, 3) if first_token is not None else None,
        "status": status, "lang_sent": lang, "error": (json.dumps(errors, ensure_ascii=False)[:500] if errors else
                                                       None if done else "stream ended without answer.done"),
        "raw": raw[:200000],
    }
    if conversation is not None:
        conversation["conversationId"] = snap["conversation_id"] or conversation.get("conversationId")
        conversation.setdefault("history", []).extend([{"role": "user", "text": question},
                                                       {"role": "assistant", "text": answer}])
    return snap


def _snapshot_error(question, lang, message, t0, status):
    return {"answer": "", "kind": None, "sources": [], "citations": [], "latency_s": round(time.monotonic() - t0, 3),
            "status": status, "lang_sent": lang, "error": message, "raw": ""}


def resolve_clarify(question, first, lang="en"):
    """After a clarifying question, answer it like a user tapping the first chip of each field + Continue."""
    fields = (first.get("clarify") or {}).get("fields") or []
    picks = [{"key": f["key"], "answer": f["options"][0]} for f in fields if f.get("options")]
    if not picks:
        return None, []
    conv = {"conversationId": first.get("conversation_id"),
            "history": [{"role": "user", "text": question}, {"role": "assistant", "text": first.get("answer", "")}]}
    return ask(question, lang=lang, conversation=conv, clarifications=picks), picks


def registry():
    """The bot's own source registry (GET {SAATHI_API}/sources)."""
    req = urllib.request.Request(SAATHI_API + "/sources", headers={
        "Origin": "https://web.umang.gov.in", "Referer": "https://web.umang.gov.in/", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))
