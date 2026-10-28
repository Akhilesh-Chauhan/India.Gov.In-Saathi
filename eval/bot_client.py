"""Calls the chatbot with the curl command the team shares.

Save the curl in eval/bot_curl.txt and replace the question text with {{QUERY}}
(optionally the conversation/session id with {{SESSION_ID}}).
"""
import json
import re
import shlex
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import config

URL_RE = re.compile(r"https?://[^\s\"'<>)\]\}]+")
ANSWER_KEYS = ("answer", "response", "output", "text", "message", "content", "result", "reply")
SOURCE_KEYS = ("sources", "citations", "references", "source_documents", "documents", "links", "source_cards")
_SKIP_VALUE = {"-o", "--output", "-m", "--max-time", "--connect-timeout", "-w", "--write-out", "-e", "--referer"}


def parse_curl(text):
    """curl command -> (method, url, headers, body)."""
    args = shlex.split(text.replace("\\\n", " ").replace("^\n", " "))
    if args and args[0] == "curl":
        args = args[1:]
    method = url = body = None
    headers = {}
    i = 0
    while i < len(args):
        a, nxt = args[i], args[i + 1] if i + 1 < len(args) else None
        if a in ("-X", "--request"):
            method = nxt
        elif a in ("-H", "--header"):
            k, _, v = nxt.partition(":")
            headers[k.strip()] = v.strip()
        elif a in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            body = nxt
        elif a == "--json":
            body = nxt
            headers.setdefault("Content-Type", "application/json")
            headers.setdefault("Accept", "application/json")
        elif a in ("-b", "--cookie"):
            headers["Cookie"] = nxt
        elif a in ("-A", "--user-agent"):
            headers["User-Agent"] = nxt
        elif a == "--url":
            url = nxt
        elif a.startswith(("http://", "https://")):
            url = a
            i += 1
            continue
        elif a not in _SKIP_VALUE:
            i += 1  # boolean flag such as -s, -L, -k, --compressed
            continue
        i += 2
    if not url:
        raise ValueError("No URL found in the curl command")
    return method or ("POST" if body is not None else "GET"), url, headers, body


def _fill(curl_parts, query, session_id):
    method, url, headers, body = curl_parts
    if "{{QUERY}}" not in (body or "") + url:
        raise ValueError("Put {{QUERY}} in the curl command where the question text goes")
    url = url.replace("{{QUERY}}", urllib.parse.quote(query)).replace("{{SESSION_ID}}", session_id or "")
    if body is not None:
        # The placeholder normally sits inside a JSON string, so insert the JSON-escaped text.
        body = body.replace("{{QUERY}}", json.dumps(query, ensure_ascii=False)[1:-1])
        body = body.replace("{{SESSION_ID}}", session_id or "")
    return method, url, headers, body


def _dig(obj, path):
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def _walk(obj):
    """Breadth-first (key, value) pairs of nested JSON."""
    queue = [obj]
    while queue:
        cur = queue.pop(0)
        items = cur.items() if isinstance(cur, dict) else enumerate(cur) if isinstance(cur, list) else []
        for k, v in items:
            yield k, v
            queue.append(v)


def _parse_payload(raw):
    """JSON body, or a list of JSON events from a server-sent-events stream."""
    try:
        return json.loads(raw)
    except ValueError:
        events = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    try:
                        events.append(json.loads(data))
                    except ValueError:
                        events.append(data)
        return events or raw


def extract(raw):
    """(answer, sources) from the bot response, using BOT_*_PATH settings or key heuristics."""
    payload = _parse_payload(raw)
    if isinstance(payload, str):
        answer = payload
    elif config.BOT_ANSWER_PATH:
        answer = str(_dig(payload, config.BOT_ANSWER_PATH))
    elif isinstance(payload, list) and payload and all(isinstance(e, (dict, str)) for e in payload):
        # Streamed tokens: join the text pieces of every event.
        answer = "".join(e if isinstance(e, str) else next(
            (str(v) for k, v in _walk(e) if k in ANSWER_KEYS + ("delta", "token") and isinstance(v, str)), "")
            for e in payload)
    else:
        answer = next((v for k, v in _walk(payload) if k in ANSWER_KEYS and isinstance(v, str) and v.strip()), "")
    if config.BOT_SOURCES_PATH and not isinstance(payload, str):
        source_blob = json.dumps(_dig(payload, config.BOT_SOURCES_PATH), ensure_ascii=False)
    elif not isinstance(payload, str):
        source_blob = json.dumps([v for k, v in _walk(payload) if k in SOURCE_KEYS], ensure_ascii=False)
    else:
        source_blob = ""
    sources = list(dict.fromkeys(u.rstrip(".,;") for u in URL_RE.findall(source_blob + " " + answer)))
    return answer, sources


def ask(query, session_id=None, curl_text=None):
    """Send one question; returns a snapshot dict (answer, sources, raw, latency, error)."""
    method, url, headers, body = _fill(parse_curl(curl_text or config.BOT_CURL_FILE.read_text(encoding="utf-8")),
                                       query, session_id)
    req = urllib.request.Request(url, data=body.encode("utf-8") if body is not None else None,
                                 method=method, headers=headers)
    ctx = ssl._create_unverified_context() if config.BOT_INSECURE_TLS else None
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=config.BOT_TIMEOUT, context=ctx) as resp:
            raw = resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:  # network failure is recorded, not fatal for the run
        return {"answer": "", "sources": [], "raw": "", "status": None,
                "latency_s": round(time.monotonic() - t0, 3), "error": str(e)}
    latency = round(time.monotonic() - t0, 3)
    answer, sources = extract(raw) if 200 <= status < 300 else ("", [])
    return {"answer": answer, "sources": sources, "raw": raw[:200000], "status": status,
            "latency_s": latency, "error": None if 200 <= status < 300 else f"HTTP {status}"}
