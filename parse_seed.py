"""Parse the developer's QA seed file (qa-golden-set-seed-*.md) into index_seed.json.

Format expected (as in qa-golden-set-seed-top10-sources.md): '## N. <source>' sections with a '**sourceId**: `id`'
line, then '**Chunk X** — label' blocks carrying '- URL:', optional '- Title:', '- `lastUpdated`: ... · `docType`: ...'
and '- Text:' followed by '> ' quoted lines. 'same PDF as above' reuses the previous chunk's URL.
Usage: python3 parse_seed.py "<seed.md>" [index_seed.json]
"""
import json
import re
import sys
from pathlib import Path


def parse(text):
    sources, chunks = [], []
    src = chunk = None
    prev_url = None
    in_text = False
    for line in text.splitlines():
        if m := re.match(r"^## \d+\.\s+(.+)", line):
            src = {"name": m.group(1).strip(), "sourceId": None, "notes": []}
            sources.append(src)
            chunk, in_text = None, False
            continue
        if src is None:
            continue
        if m := re.search(r"\*\*sourceId\*\*:\s*`([^`]+)`", line):
            src["sourceId"] = m.group(1)
            src["summary"] = line.split("·", 1)[-1].strip(" -*")
            continue
        if m := re.match(r"^\*\*Chunk ([A-Z])\*\*\s*[—-]\s*(.+)", line):
            chunk = {"key": f"{src['sourceId']}#{m.group(1)}", "source": src["name"], "sourceId": src["sourceId"],
                     "label": m.group(2).strip(), "url": None, "title": None, "lastUpdated": None, "docType": None, "text": ""}
            chunks.append(chunk)
            in_text = False
            continue
        if chunk is None:
            if line.startswith("- **") and "QA note" in line or "Important finding" in line or "Correction" in line:
                src["notes"].append(re.sub(r"\*\*", "", line.lstrip("- ")).strip())
            continue
        if m := re.match(r"^- URL:\s*(\S+)", line):
            chunk["url"] = m.group(1) if m.group(1).startswith("http") else prev_url
            prev_url = chunk["url"]
        elif line.startswith("- URL:"):
            chunk["url"] = prev_url
        elif m := re.match(r"^- Title:\s*(.+?)(\s*·.*)?$", line):
            chunk["title"] = m.group(1).strip()
            if dm := re.search(r"`docType`:\s*(\w+)", line):
                chunk["docType"] = dm.group(1)
        elif "`lastUpdated`" in line or "`docType`" in line:
            if lm := re.search(r"`lastUpdated`:\s*([\d-]+)", line):
                chunk["lastUpdated"] = lm.group(1)
            if dm := re.search(r"`docType`:\s*(\w+)", line):
                chunk["docType"] = dm.group(1)
        elif line.startswith("- Text:"):
            in_text = True
        elif in_text and line.lstrip().startswith(">"):
            chunk["text"] += line.lstrip()[1:].strip() + " "
        elif line.startswith("---") or line.startswith("## "):
            chunk, in_text = None, False
    for c in chunks:
        c["text"] = c["text"].strip()
    return {"sources": sources, "chunks": chunks}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).with_name("index_seed.json"))
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data['sources'])} sources, {len(data['chunks'])} chunks -> {out}")
    for c in data["chunks"]:
        assert c["url"] and c["text"], f"chunk {c['key']} missing url/text"
