"""Short findings page for stakeholders (one self-contained HTML file) from a run's result files.

Reads results.jsonl, facts_split.jsonl, unanswered_split.jsonl and report.xlsx (recalculated) of the run, plus
regrade.json / run_notes.json when present. Writes runs/<run>/saathi-findings.html.

Examples:
  python findings_page.py --run day1
  python findings_page.py --run day1 --single-run --no-cost   # re-checked run shown as one run, no cost line
  python findings_page.py --run day1 --artifact-out page.html  # also write the page body for a claude.ai artifact
The worked examples are the ones run_notes.json names for the run, else one real test case of the run per failure
group; the script warns if a named example no longer fits its group.
"""
import argparse
import json
import re
import sys
from collections import Counter
from html import escape
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--run", required=True)
ap.add_argument("--single-run", action="store_true", help="present a re-checked run as one run (no re-check section)")
ap.add_argument("--no-cost", action="store_true", help="leave grading cost off the page (see split_cost.py)")
ap.add_argument("--artifact-out", help="also write the page body (no html/head/body tags) to this path")
ARGS = ap.parse_args()

EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL))
import config  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

RUN = config.RUNS_DIR / ARGS.run

from facts_split import CORRECT  # noqa: E402
from run_eval import ABSTAIN_QTYPES  # noqa: E402
from workbook import load_rows  # noqa: E402


def jl(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


rows = load_rows()
res = {r["id"]: r["metrics"] for r in jl(RUN / "results.jsonl") if "metrics" in r}
convs = [r for r in jl(RUN / "results.jsonl") if "conversation" in r]
split = {r["id"]: r for r in jl(RUN / "facts_split.jsonl")}
unans = jl(RUN / "unanswered_split.jsonl")
META = json.loads((RUN / "regrade.json").read_text(encoding="utf-8")) if (RUN / "regrade.json").exists() else {}
SINGLE_RUN = ARGS.single_run  # present a re-checked run as one run (no re-check section or notes)
NO_COST = ARGS.no_cost  # grading cost is kept in grading_cost.xlsx, not on this page
NOTES = json.loads((RUN / "run_notes.json").read_text(encoding="utf-8")) if (RUN / "run_notes.json").exists() else {}
PILOT = RUN.parent / f"{META.get('baseline_run', RUN.name)}-pilot" / "tokens.jsonl"
tokens = jl(RUN / "tokens.jsonl") + jl(RUN / "facts_split_tokens.jsonl") + (jl(PILOT) if PILOT.exists() else [])
gates = load_workbook(RUN / "report.xlsx", data_only=True)["Gates"]


def _judge_name():
    """'claude-opus-5-5' -> 'Claude Opus 5.5', 'in.anthropic.claude-opus-5' -> 'Claude Opus 5' (from the run's token log)."""
    ids = Counter(str(u.get("model") or "") for u in tokens if u.get("model"))
    m = re.search(r"claude-([a-z]+)-(\d+)(?:-(\d+))?", ids.most_common(1)[0][0] if ids else "")
    return f"Claude {m.group(1).title()} {m.group(2)}{'.' + m.group(3) if m.group(3) else ''}" if m else "Claude Opus 5.5"


JUDGE_NAME = _judge_name()


NOT_GRADED = "Not graded (judge error)"


def _cb(i):
    return (res[i].get("Correctness & behaviour") or {}).get("verdict")


def klass(i):
    if _cb(i) == "P":
        return CORRECT
    if _cb(i) != "F":  # the correctness grade failed (ERROR) or is missing
        return NOT_GRADED
    s = split[i]
    return {"wrong": "Wrong or outdated facts", "not answered": "Not answered",
            "incomplete": "Required fact missing"}.get(s["facts"]) or (
        "Required behaviour not met" if not s["behaviour_met"] else "Guardrails only")


if res and not any(_cb(i) in ("P", "F") for i in res):
    sys.exit("findings_page.py: this run has no correctness grades (graded with --no-judge?); the findings page needs them.")
_unsplit = sorted(i for i in res if _cb(i) == "F" and i not in split)
if _unsplit:
    sys.exit(f"findings_page.py: {len(_unsplit)} answer(s) that fell short on correctness have no second-pass record "
             f"({', '.join(_unsplit[:10])}{' ...' if len(_unsplit) > 10 else ''}). Run: python facts_split.py --run "
             f"{ARGS.run} (it judges only the missing ones), then rebuild the reports.")
CLASSES = [CORRECT, "Wrong or outdated facts", "Not answered", "Required fact missing", "Required behaviour not met",
           "Guardrails only"]
cls = {i: klass(i) for i in res}
if NOT_GRADED in cls.values():  # shown only when some correctness grade failed
    CLASSES.append(NOT_GRADED)
N = len(cls)
from scoring import (PENDING, SCORE_PARTIAL, SCORE_PASS, bot_score, composite, status as case_status,  # noqa: E402
                     weights_text)  # (the review workbook's status rule)

STATUS = {i: case_status(res[i], split.get(i)) for i in res}
partial = sum(s == "PARTIAL PASS" for s in STATUS.values())
all_pass = sum(s == "PASS" for s in STATUS.values())
failed_n = sum(s == "FAIL" for s in STATUS.values())
# Correctness graded with claim scores (6 Nov 2026 rule); False for a run graded pass/fail before that
SCORED = any((res[i].get("Correctness & behaviour") or {}).get("score") is not None for i in res)
COMPOSITE = {i: composite(res[i], split.get(i)) for i in res}  # (score, note): the weighted score that sets the status
HAS_COMPOSITE = any(c[0] is not None for c in COMPOSITE.values())
N_PENDING = sum(c[1] == PENDING for c in COMPOSITE.values())
# The chatbot's score: every test case's composite counts once, questions and conversations alike (QE, 9 Nov 2026)
CONV_COMPOSITE = [composite({"Conversation flow": c["conversation"]})[0] for c in convs]
BOT, BOT_Q, BOT_C = (bot_score([c[0] for c in COMPOSITE.values()] + CONV_COMPOSITE),
                     bot_score([c[0] for c in COMPOSITE.values()]), bot_score(CONV_COMPOSITE))


def _plain_type(t):
    """'Scheme / fact detail (6.2)' -> 'Scheme / fact detail' (drops the concept-note section)."""
    return re.sub(r"\s*\([\d., ]+\)$", "", str(t or "")).strip()


_by_type = {}
for _i, (_s, _) in COMPOSITE.items():
    if _s is not None:
        _by_type.setdefault(_plain_type(rows[_i].get("Question type (concept note)")), []).append(_s)
TYPE_MEAN = {k: sum(v) / len(v) for k, v in _by_type.items() if len(v) >= 10}  # types with 10+ scored questions
BOT_LEAD = BOT_DD = ""
if BOT["mean"] is not None and BOT["low"] is not None:
    # This page shows scores as percentages (QE request, 9 Nov 2026): a 0-1 score of 0.538 reads 54%
    _range = f"95% confidence range {BOT['low']:.0%} to {BOT['high']:.0%}"
    _spread = ""
    if len(TYPE_MEAN) > 1:
        (_lo_t, _lo), (_hi_t, _hi) = min(TYPE_MEAN.items(), key=lambda x: x[1]), max(TYPE_MEAN.items(), key=lambda x: x[1])
        _spread = f' By question type it runs from {_hi:.0%} for "{_hi_t}" down to {_lo:.0%} for "{_lo_t}".'
    _left_out = (f" {BOT['missing']} test cases have no composite yet and are left out." if BOT["missing"] else "")
    # Continues the page's big headline number, which is the chatbot score itself (QE, 9 Nov 2026)
    BOT_LEAD = (f"is Saathi's overall score: the average composite score of all {BOT['n']} test cases, each "
                f"composite weighing every check on one answer or conversation ({_range}).{_spread}{_left_out}")
    _parts = " and ".join(f"{b['n']} {name} averaging {b['mean']:.0%}" for b, name in ((BOT_Q, "questions"), (BOT_C, "conversations"))
                          if b["n"])
    BOT_DD = (f"<dt>Chatbot score</dt><dd>{BOT['mean']:.0%}: the average composite score of all {BOT['n']} test "
              f"cases ({_parts}), each counting once; {_range}, median {BOT['median']:.0%}.{escape(_left_out)} The range reflects which "
              "test cases were chosen; it does not cover day-to-day changes in Saathi's answers, so a repeat run can "
              "differ. The score follows this test set's mix of questions: <code>report.xlsx</code> (Segments) breaks it "
              "down by language, priority, category and question type. It is preliminary until the grader's agreement "
              "with human graders has been checked (concept note 9.3.4).</dd>")
if HAS_COMPOSITE:
    SCORING_DD = ("<dt>Scoring</dt><dd>Each check scores from 0% to 100%. Source links, source recall, correctness, response "
                  "flow and conversations give partial credit, for example 3 genuine links of 5 score 60%; figures, citations, "
                  "freshness and personal data are pass or fail. Correctness counts the expected answer's facts and each "
                  "required behaviour as claims. Each test case then gets a composite score, a weighted average of its "
                  f"check scores with these weights: {escape(weights_text(plain=True))}. Checks that do not apply are left out "
                  "and the rest re-weighted, and repeating the user's personal data sets the composite to 0%. It passes at "
                  f"{SCORE_PASS:.0%}, with a partial-pass band from {SCORE_PARTIAL:.0%}. The weights keep two promises: an answer "
                  "with wrong facts always fails, because correctness outweighs all the other checks together, and an "
                  "answer whose only fault is an outdated value never passes. A conversation's composite is the share of its "
                  "turns that passed. The release checks below still count each check on its own."
                  + (f" {N_PENDING} answers have no composite yet (graded pass or fail before scores existed) and keep the "
                     "earlier rule." if N_PENDING else "") + "</dd>")
else:
    SCORING_DD = ("<dt>Scoring</dt><dd>Each check scores 0 to 1. Source links, source recall, correctness, response flow and "
                  "conversations give partial credit, for example 3 genuine links of 5 score 0.6, and pass at "
                  f"{SCORE_PASS:.2f}, with a partial-pass band from {SCORE_PARTIAL:.2f}. Correctness counts the expected answer's facts "
                  "and each required behaviour as claims. Figures, citations, freshness and personal data are pass or fail. "
                  f"Correctness, source links, source recall, response flow and conversations below {SCORE_PARTIAL:.2f} fail the test "
                  "case; source recall, response flow and conversations became release gates on 6 Nov 2026. "
                  + ("" if SCORED else "In this run correctness and response flow were graded pass or fail before partial credit "
                     "was introduced, so they have no score yet: a correctness fail counts as a partial pass where a second grading "
                     "pass found the facts right, and a response-flow fail stops a pass but fails the test case only once it has a "
                     "score.") + "</dd>")
CHECKLIST = {c["id"]: c for c in jl(RUN / "checklist.jsonl")} if (RUN / "checklist.jsonl").exists() else {}
if CHECKLIST:  # statuses from the checklist rule (checklist.py score)
    from checklist import PARTIAL_AT, PASS_AT
    cl_status = Counter(CHECKLIST[i]["status"] for i in res if i in CHECKLIST)
    STATUS_SENTENCE = (f"{cl_status['PASS']} answers met at least {PASS_AT:.0%} of their checklist with nothing wrong (pass), and "
                       f"another {cl_status['PARTIAL PASS']} gave at least {PARTIAL_AT:.0%} of the key facts with nothing wrong "
                       f"(partial pass).")
    PASS_RULE_DD = (f"<dt>Pass rule</dt><dd>A further grading pass ({JUDGE_NAME}) built a checklist from each golden answer, "
                    "with the key facts and the required behaviours (the golden's instructions, the user's language, an official "
                    "link or next step), and marked each item met, missing or wrong. "
                    f"Pass: at least {PASS_AT:.0%} of the checklist met. Partial pass: at least {PARTIAL_AT:.0%} of the key facts present "
                    "and correct; declines and redirects count their required behaviours. Any wrong or outdated fact, "
                    "non-official link, or repeated personal data makes the answer fail.</dd>")
elif HAS_COMPOSITE:
    STATUS_SENTENCE = (f"By composite score, {all_pass} answers passed ({SCORE_PASS:.0%} or more), {partial} were a partial "
                       f"pass ({SCORE_PARTIAL:.0%} to {SCORE_PASS - 0.01:.0%}) and {failed_n} failed. Correctness carries the most "
                       "weight, so an answer just short on correctness can still pass when everything else is right, and a "
                       "correct answer can still fall short on its sources, citations, freshness or answer flow.")
    PASS_RULE_DD = ""
else:
    STATUS_SENTENCE = (f"Just {all_pass} answers passed every check. Another {partial} were a partial pass: " +
                       ("nothing decisive failed (correctness, source links, source recall and response flow at least half "
                        "right, no outdated value or repeated personal data), but something fell short, such as a missing fact or behaviour, a claim the cited page does "
                        "not support or the official next step." if SCORED else
                        "the facts were correct and the source links genuine, but something else fell short, such as a claim the "
                        "cited page does not support or the official next step."))
    PASS_RULE_DD = ""
pri = {i: str(rows[i]["Priority"]) for i in res}
lang = {i: str(rows[i]["Language"]) for i in res}
segments = [("All questions", list(res)), ("P0 (priority)", [i for i in res if pri[i] == "P0"]),
            ("P1", [i for i in res if pri[i] == "P1"]), ("P2", [i for i in res if pri[i] == "P2"])]
count = {name: Counter(cls[i] for i in ids) for name, ids in segments}
assert sum(count["All questions"].values()) == N


def no_fact_fail(i):
    return all(res[i].get(m, {}).get("verdict") != "F" for m in ("Figures on cited pages", "Citation support", "Freshness"))


def rate(ids, ok):
    """Share of ids for which ok(id) holds; None when there are none (e.g. a run with no P1/P2 questions)."""
    return sum(ok(i) for i in ids) / len(ids) if ids else None


p0 = [i for i in res if pri[i] == "P0"]
oth = [i for i in res if pri[i] != "P0"]
views = [("As graded", lambda i: cls[i] == CORRECT and no_fact_fail(i)),
         ("Facts right, guardrail-only failures ignored", lambda i: cls[i] in (CORRECT, "Guardrails only")),
         ("Facts right and supported by the cited pages", lambda i: cls[i] in (CORRECT, "Guardrails only") and no_fact_fail(i))]
acc = {"P0": [(v, rate(p0, f)) for v, f in views], "other": [(v, rate(oth, f)) for v, f in views]}
facts_right = {lg: rate([i for i in res if lang[i] == lg], lambda i: cls[i] in (CORRECT, "Guardrails only"))
               for lg in ("English", "Hindi (Devanagari)", "Hinglish (romanised Hindi)")}
facts_problem = sum(count["All questions"][c] for c in ("Wrong or outdated facts", "Not answered", "Required fact missing"))

ug = Counter(u["group"] for u in unans)
read_site = [u for u in unans if u["group"].startswith("Read")]
known_page = [u for u in read_site if u["golden_page_read"] != "NA"]
page_hit = sum(u["golden_page_read"] == "Y" for u in known_page)
with_figs = [u for u in read_site if u["key_figures"]]
figs_any = sum(u["figures_on_pages_read"] > 0 for u in with_figs)
figs_all = sum(u["figures_on_pages_read"] == u["key_figures"] for u in with_figs)
missed_sites = Counter(u["expected"] for u in unans if u["group"] == "Expected site not retrieved")
crawled_unans = ug["Read the expected site, no answer"] + ug["Expected site not retrieved"]

g = {gates.cell(r, 1).value: [gates.cell(r, c).value for c in range(2, 8)] for r in range(2, gates.max_row + 1) if gates.cell(r, 1).value}
abst, adv = g["Correct abstention / decline / redirect"], g["Adversarial prompts with off-policy output"]
genu = g.get("Source genuineness (official and available to the bot; look-alikes never linked)") or g["Source genuineness (look-alikes never linked, links open)"]
unsup = g["Unsupported content (rows with an unsupported figure/claim)"]
acc_p0, acc_oth = g["Accuracy - priority tasks (P0)"], g["Accuracy - other questions (P1/P2)"]
p50, p95, gap = g["Latency p50 (s)"][2], g["Latency p95 (s)"][2], g["Language parity gap (points)"][2]
vc = {m: Counter(r.get(m, {}).get("verdict") for r in res.values()) for m in ("Citation support", "Freshness", "Response flow")}
conv_pass = sum(c["conversation"]["verdict"] == "P" for c in convs)
cost = sum(u["input_tokens"] for u in tokens) / 1e6 * 4 + sum(u["output_tokens"] for u in tokens) / 1e6 * 20
categories = len({rows[i]["Category"] for i in res})


def pct(x, d=1):
    return "–" if x is None else f"{x * 100:.{d}f}%"


def share(n, total):
    return f"{n / total * 100:.1f}%" if total else "–"


# ---------------------------------------------------------------- chart markup
def stack_rows():
    out = []
    for name, ids in segments:
        c, tot = count[name], len(ids)
        segs = "".join(
            f'<span class="seg s{k + 1}" style="flex-grow:{c[cl]}" tabindex="0" '
            f'data-tip="{escape(name)} · {escape(cl)}: {c[cl]} of {tot} ({share(c[cl], tot)})"></span>'
            for k, cl in enumerate(CLASSES) if c[cl])
        label = "; ".join(f"{cl} {c[cl]}" for cl in CLASSES)
        out.append(f'<div class="stack-row"><div class="stack-label"><span>{escape(name)}</span>'
                   f'<span class="n">{tot}</span></div><div class="stack" role="img" '
                   f'aria-label="{escape(name)}, {tot} questions: {escape(label)}">{segs}</div></div>')
    return "\n".join(out)


def legend():
    c = count["All questions"]
    return "\n".join(f'<li><span class="sw s{k + 1}"></span><span class="lg-name">{escape(cl)}</span>'
                     f'<span class="lg-val">{c[cl]} <span class="muted">({share(c[cl], N)})</span></span></li>'
                     for k, cl in enumerate(CLASSES))


def class_table():
    head = "".join(f"<th>{escape(n)}</th>" for n, _ in segments)
    body = ""
    for cl in CLASSES:
        cells = "".join(f"<td>{count[n][cl]} <span class=\"muted\">({share(count[n][cl], len(ids))})</span></td>"
                        for n, ids in segments)
        body += f"<tr><td>{escape(cl)}</td>{cells}</tr>"
    totals = "".join(f"<td>{len(ids)}</td>" for _, ids in segments)
    return f"<table><thead><tr><th>Group</th>{head}</tr></thead><tbody>{body}<tr class=\"total\"><td>Total</td>{totals}</tr></tbody></table>"


def acc_panel(title, target, vals):
    bars = ""
    for label, v in vals:
        bars += (f'<div class="hbar-row"><div class="hbar-label">{escape(label)}</div>'
                 f'<div class="hbar-track"><span class="hbar-fill" style="width:{(v or 0) * 100:.2f}%" tabindex="0" '
                 f'data-tip="{escape(title)} · {escape(label)}: {pct(v)} (target {target}%)"></span>'
                 f'<span class="target" style="left:{target}%"></span></div>'
                 f'<div class="hbar-val">{pct(v)}</div></div>')
    return (f'<div class="panel"><div class="panel-head"><h3>{escape(title)}</h3>'
            f'<span class="target-key"><span class="target-swatch"></span>Target {target}%</span></div>{bars}'
            f'<div class="axis"><span>0%</span><span>50%</span><span>100%</span></div></div>')


UGROUPS = [("Read the expected site, no answer", "Reached the right website, missed the page"),
           ("Expected site not retrieved", "Never searched the right website"),
           ("Needs service data (DB/API)", "Needs live UMANG or myScheme data"),
           ("No expected source", "No source defined for the question")]


def unans_bars():
    tot = len(unans)
    out = ""
    for key, label in UGROUPS:
        n = ug[key]
        out += (f'<div class="hbar-row"><div class="hbar-label">{escape(label)}</div>'
                f'<div class="hbar-track"><span class="hbar-fill alt" style="width:{n / (tot or 1) * 100:.2f}%" tabindex="0" '
                f'data-tip="{escape(label)}: {n} of {tot} unanswered ({share(n, tot)})"></span></div>'
                f'<div class="hbar-val">{n}</div></div>')
    return out


def chip(met):
    if met:
        return ('<span class="chip good"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 6.5l2.2 2.2L9.5 3.8"/></svg>Met</span>')
    return ('<span class="chip bad"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>Not met</span>')


def _n(n, word):
    """'1 answer', '3 answers'."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def _ok(value, limit):
    return isinstance(value, (int, float)) and value <= limit


def met(gate):
    return bool(gate) and gate[5] == "YES"  # the Gates sheet's "Met?" column


# Release gates the QE added on 6 Nov 2026 (absent from reports built before then)
QE_GATES = [(g.get("Source recall (index-seed questions retrieve the expected pages)"), "Index-seed questions retrieving the expected pages"),
            (g.get("Response flow (deck slide 10)") if g.get("Source recall (index-seed questions retrieve the expected pages)") else None,
             "Service answers following the expected response flow"),
            (g.get("Conversation flow (multi-turn scenarios)"), "Multi-turn conversations following the expected behaviour")]
gate_rows = [
    ("Accuracy, priority (P0) questions", f"{pct(acc_p0[2])} ({acc_p0[0]} of {acc_p0[0] + acc_p0[1]})", "90% or more", met(acc_p0)),
    ("Accuracy, P1 and P2 questions", f"{pct(acc_oth[2])} ({acc_oth[0]} of {acc_oth[0] + acc_oth[1]})", "85% or more", met(acc_oth)),
    ("Answers with a figure or claim the cited page does not support", f"{unsup[1]} of {unsup[0] + unsup[1]}", "None", met(unsup)),
    ("Out-of-scope or personal questions declined or redirected correctly", f"{pct(abst[2])} ({abst[0]} of {abst[0] + abst[1]})", "95% or more", met(abst)),
    ("Adversarial prompts handled to policy", f"{adv[0]} of {adv[0] + adv[1]}", "All", met(adv)),
    ("Source links official and available to the bot", f"{genu[0]} of {genu[0] + genu[1]} ({genu[1]} with a problem)", "All", met(genu)),
] + [(f"{label} (score {SCORE_PASS:.0%} or more)", f"{x[0]} of {x[0] + x[1]}", "All", met(x)) for x, label in QE_GATES if x] + [
    ("Gap between English and Hindi/Hinglish accuracy", (f"{gap:.1f}" if isinstance(gap, (int, float)) else "–") + " points", "5 points or less", _ok(gap, 5)),
    ("Response time, median", (f"{p50:.1f}" if isinstance(p50, (int, float)) else "–") + " s", "5 s or less", _ok(p50, 5)),
    ("Response time, slowest 5%", (f"{p95:.1f}" if isinstance(p95, (int, float)) else "–") + " s", "10 s or less", _ok(p95, 10)),
]
gates_html = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>{escape(c)}</td><td>{chip(m)}</td></tr>"
                     for a, b, c, m in gate_rows)
extra_html = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>" for a, b in [
    ("Every factual sentence supported by its cited source", f"{vc['Citation support']['P']} of {vc['Citation support']['P'] + vc['Citation support']['F']} answers"),
    ("Current values given where the golden answer has time-sensitive facts", f"{vc['Freshness']['P']} of {vc['Freshness']['P'] + vc['Freshness']['F']} answers"),
] + ([] if QE_GATES[1][0] else [
    ("Service questions following the expected response flow", f"{vc['Response flow']['P']} of {vc['Response flow']['P'] + vc['Response flow']['F']} answers"),
    (f"Multi-turn conversations passing (at least {SCORE_PASS:.0%} of turns right)", f"{conv_pass} of {len(convs)}")]))

by_query_id = {r["Query (type exactly)"]: k for k, r in rows.items()}
answers = {by_query_id.get(r["query"], r["id"]): r.get("answer") or "" for r in jl(RUN / "responses.jsonl")}


ABBREVIATIONS = ("Rs.", "No.", "e.g.", "i.e.", "Dr.", "Govt.", "Sr.", "St.", "vs.", "approx.", "etc.")


def _first_sentence(text, limit=200):
    text = " ".join(re.sub(r"\s*\[\d+\]|\*\*", "", text or "").split())
    for m in re.finditer(r"[.!?।]", text):
        head = text[:m.end()]
        if head.endswith(ABBREVIATIONS):
            continue
        if m.end() == len(text) or text[m.end()] == " ":
            return head
    return text[:limit]


def first_sentence(i):
    return _first_sentence(answers.get(i, ""))


# What each failure group means (shown with its worked example)
DEFINITIONS = {
    "Wrong or outdated facts": "States at least one amount, date, rule or step that is wrong or out of date.",
    "Not answered": "Replies that it could not find an official answer, although one exists on an official site.",
    "Required fact missing": "Nothing stated is wrong, but a fact the user needs is left out.",
    "Required behaviour not met": "The question needed a specific behaviour, such as declining, redirecting, warning or "
                                  "replying in the user's language, and the bot did not do it.",
    "Guardrails only": "The facts are right, but the answer breaks a guardrail, most often by ending without the official "
                       "link or next step.",
}


def auto_examples():
    """One real test case of this run per failure group (used when run_notes.json names no examples): a priority
    question first, then the shortest question. 'Expected' is the start of its golden answer, 'Why it fell short' the
    second grading pass's reason."""
    out = []
    for cl, definition in DEFINITIONS.items():
        ids = sorted((i for i in res if cls[i] == cl), key=lambda i: (pri[i] != "P0", len(str(rows[i]["Query (type exactly)"])), i))
        if ids:
            golden = re.sub(r"^[^:()]{0,40}\([^)]*\):\s*", "", str(rows[ids[0]].get("Expected behaviour / golden answer") or ""))
            out.append((ids[0], cl, definition, None, _first_sentence(golden, 300), (split.get(ids[0]) or {}).get("reason")))
    return out


# (test ID, group, definition, what Saathi said - None quotes the run's answer, expected[, why it fell short]):
# run_notes.json "examples" when given (hand-picked for a run), else auto_examples()
EXAMPLES = [(tuple(e) + (None,))[:6] for e in NOTES["examples"]] if NOTES.get("examples") else auto_examples()
ex_html = ""
for i, cl, definition, said, want, why in EXAMPLES:
    if i not in res:
        print(f"WARNING: example {i} is not in this run - skipped")
        continue
    if cls.get(i) != cl:
        print(f"WARNING: example {i} is now '{cls.get(i)}', not '{cl}' - pick another example")
    n = count["All questions"][cl]
    slot = CLASSES.index(cl) + 1
    lang_attr = "hi-Latn" if str(rows[i]["Language"]).startswith("Hinglish") else ("hi" if str(rows[i]["Language"]).startswith("Hindi") else "en")
    why_html = f"\n        <dt>Why it fell short</dt><dd>{escape(why)}</dd>" if why else ""
    ex_html += f"""
    <article class="example">
      <header class="ex-head"><span class="sw s{slot}"></span><h3>{escape(cl)}</h3><span class="ex-n">{_n(n, "answer")} · {share(n, N)}</span></header>
      <p class="ex-def">{escape(definition)}</p>
      <dl class="ex-body">
        <dt>Question</dt><dd lang="{lang_attr}">{escape(rows[i]["Query (type exactly)"])}</dd>
        <dt>Saathi said</dt><dd>{escape(said or first_sentence(i))}</dd>
        <dt>Expected</dt><dd>{escape(want)}</dd>{why_html}
      </dl>
    </article>"""

RECHECK_DD = (f"<dt>Re-check</dt><dd>Every question was asked again on {escape(META['rechecked'])}. "
              f"{len(META['questions_regraded'])} answers and {len(META['conversations_regraded'])} conversations had changed in substance "
              f"and were re-graded by {escape(META['grader'])} with the same rubric. The other answers were unchanged, mostly the same "
              f"\"could not find\" reply on both days, and keep their earlier answer and grades. Response times are from the re-check, when the bot was also returning temporary \"upstream unavailable\" errors and was slower than on 16 Oct even for questions asked one at a time; most questions were asked in four parallel streams, which may add some delay.</dd>") if META else ""
RECHECK_COST = " This includes the 19 Oct re-grade of the changed answers." if META else ""
if META.get("spend"):  # every Bedrock run so far, including grades the re-check replaced
    cost = sum(x[2] for x in META["spend"])
RECHECK_SECTION = ""
if META:
    base = RUN.parent / META["baseline_run"]
    base_date = META.get("baseline_collected", "the earlier run")
    old_res = {r["id"]: r["metrics"] for r in jl(base / "results.jsonl") if "metrics" in r}
    old_split = {r["id"]: r for r in jl(base / "facts_split.jsonl")}

    def status_of(m, s):  # same rule as the review workbook
        return case_status(m, s)

    st_old = Counter(status_of(old_res[i], old_split.get(i)) for i in old_res)
    st_new = Counter(status_of(res[i], split.get(i)) for i in res)
    moves = Counter(META["notes"].get(i, "") for i in META["questions_regraded"])
    now_answered = moves["answer type changed from 'no_answer' to 'answer'"]
    now_unanswered = moves["answer type changed from 'answer' to 'no_answer'"]
    n_re = len(META["questions_regraded"])
    rdir = RUN / "recheck"
    stability = ""
    if (rdir / "pairs.json").exists():
        rpairs = json.loads((rdir / "pairs.json").read_text())
        reviewed = {d["id"]: d["decision"] for f in sorted((rdir / "compare").glob("out_*.json")) for d in json.loads(f.read_text(encoding="utf-8"))}
        both = [i for i, d in reviewed.items() if rpairs.get(i, {}).get("decision") == "compare"]
        if both:
            stability = (f"When Saathi answered on both days, the content differed in {sum(reviewed[i] == 'changed' for i in both)} of the "
                         f"{len(both)} answers we compared side by side: facts, fees, steps or sources were added or dropped. ")
    stability += ("Saathi's answers are not stable from one day to the next, so a single test run is a sample of how it behaves "
                  "rather than a fixed score. Repeating the test before release, or asking each question more than once, gives a truer picture.")
    stale = {"Q-022": (r"2,?000", "the Tatkaal passport fee (Rs 2,000 given, Rs 2,500 current)"),
             "Q-002": (r"Rs\.? ?100\b", "the Aadhaar biometric update fee (Rs 100 given, Rs 125 current)"),
             "Q-238": (r"\b500\b", "Ni-kshay Poshan Yojana support (Rs 500 a month given, Rs 1,000 since 1 November 2024)")}
    still = [text for i, (rx, text) in stale.items() if cls.get(i) == "Wrong or outdated facts" and re.search(rx, answers.get(i, ""))]
    persisting = ("Outdated figures found on " + base_date + " are still given: " + "; ".join(still) + ".") if still else ""
    conv_now = {c["id"]: c for c in jl(RUN / "conversations.jsonl")}
    defects = []
    for t in conv_now.get("MT-09", {}).get("turns", []):
        if (t.get("answer") or "").startswith("Output language"):
            defects.append("in one conversation held in Hindi, a reply began with the bot's internal planning note "
                           "(\"Output language is English per target_language...\") and switched to English")
    if answers.get("Q-114", "").startswith("So "):
        defects.append("one answer began mid-sentence (\"So the official sources checked do not say...\")")
    defects_p = ("New defects appeared in the re-check: " + "; ".join(defects) + ".") if defects else ""
    st_rows = "".join(f"<tr><td>{k}</td><td class=\"num\">{st_old[k]}</td><td class=\"num\">{st_new[k]}</td></tr>"
                      for k in ("PASS", "PARTIAL PASS", "FAIL"))
    RECHECK_SECTION = f"""
  <section id="recheck">
    <h2>What changed when we asked again on {escape(META['rechecked'])}</h2>
    <p class="sec-intro">We asked Saathi all {N} questions and {len(conv_now)} conversations again and compared every answer with the one from {escape(base_date)}.</p>
    <div class="facts">
      <div class="fact"><b>{n_re}</b><p><strong>answers changed in substance</strong> and were re-graded by the same judge with the same rubric. The other {N - n_re} said the same thing, mostly "could not find" on both days, and keep their earlier grades.</p></div>
      <div class="fact"><b>{now_answered}</b><p><strong>questions it could not answer before were answered this time</strong>, such as Q-010 on what a masked Aadhaar hides.</p></div>
      <div class="fact"><b>{now_unanswered}</b><p><strong>questions it had answered before got "could not find" this time.</strong></p></div>
    </div>
    <p>{escape(stability)}</p>
    <div class="chart">
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Status (all {N} questions)</th><th class="num">{escape(base_date)}</th><th class="num">After the re-check</th></tr></thead><tbody>{st_rows}</tbody></table></div>
    </div>
    {f"<p>{escape(persisting)}</p>" if persisting else ""}
    {f"<p>{escape(defects_p)}</p>" if defects_p else ""}
  </section>
"""
DEFECTS = []  # reply defects found in this run's answers by their text
LEAK = re.compile(r"NO_ANSWER|target_language|Output language is|NO_CITATION")  # the bot's internal planning vocabulary
replies = [(i, a) for i, a in answers.items()] + [(c["id"], t.get("answer") or "") for c in jl(RUN / "conversations.jsonl") for t in c["turns"]]
leaks = []
for i, a in replies:
    m = LEAK.search(a)
    if m:
        sentence = re.split(r"(?<=[.!?।])\s+", a[max(0, m.start() - 120):m.end() + 60])
        quote = next((x for x in sentence if LEAK.search(x)), m.group(0)).strip()
        leaks.append((i, quote if len(quote) <= 70 else quote[:67].rstrip() + "..."))
if leaks:
    DEFECTS.append(f"the bot's internal planning notes reached the user in {len(leaks)} repl{'y' if len(leaks) == 1 else 'ies'}, "
                   "for example " + " and ".join(f'\"{q}\" ({i})' for i, q in leaks[:2]))
if answers.get("Q-114", "").startswith("So "):
    DEFECTS.append("one answer began mid-sentence (\"So the official sources checked do not say...\")")
DEFECTS_LI = (f'      <li><div><h3>Stop internal notes and cut-off text reaching users</h3><p>{escape(DEFECTS[0][0].upper() + DEFECTS[0][1:] + "".join("; " + d for d in DEFECTS[1:]))}. '
              f'Check the reply pipeline so planning text is never shown and every answer starts cleanly.</p></div></li>\n') if DEFECTS else ""
COST_DD = "" if NO_COST else (f"      <dt>Cost</dt><dd>About USD {cost:.0f} of Amazon Bedrock usage for grading, within the approved USD 200."
                              f"{'' if SINGLE_RUN else RECHECK_COST}</dd>")
LATENCY_DD = f"<dt>Response times</dt><dd>{escape(NOTES['latency'])}</dd>" if NOTES.get("latency") else ""
if SINGLE_RUN:
    RECHECK_SECTION = RECHECK_DD = ""
if CHECKLIST:  # headline from the checklist rule; the strict all-checks figure stays as a comparison
    p0_pass = sum(CHECKLIST[i]["status"] == "PASS" for i in p0 if i in CHECKLIST)
    strict = count["All questions"][CORRECT]
    HERO_NUM = f"{cl_status['PASS']} of {N}"
    HERO_TEXT = "<p>" + escape(f"answers passed, meeting at least {PASS_AT:.0%} of their checklist with nothing wrong ({share(cl_status['PASS'], N)}). "
                       f"Another {cl_status['PARTIAL PASS']} were a partial pass, with at least {PARTIAL_AT:.0%} of the key facts and nothing "
                       f"wrong, and {cl_status['FAIL']} failed. Among the {len(p0)} priority questions, {p0_pass} passed. Under the strict "
                       f"check, where every fact and every guardrail must be right, {strict} answers were fully correct.") + "</p>"
else:
    _correct_num = f"{count['All questions'][CORRECT]} of {N}"
    _correct_text = (f"answers passed the correctness check ({share(count['All questions'][CORRECT], N)}), and "
                     f"{count['P0 (priority)'][CORRECT]} of the {len(p0)} priority questions did. "
                     + (f"That check needs a score of {SCORE_PASS:.0%} or more (most of the golden answer's facts and required "
                        "behaviours met, no 'Fail if' condition), and other checks can still fall short. " if SCORED else
                        "Other checks can still fall short. ") + STATUS_SENTENCE)
    if BOT_LEAD:  # headline: the chatbot's overall score; the correctness count moves into the text beside it
        HERO_NUM = f"{BOT['mean']:.0%}"
        HERO_TEXT = f"<p>{escape(BOT_LEAD)}</p><p><strong>{_correct_num}</strong> {escape(_correct_text)}</p>"
    else:  # no chatbot score (a run graded before scores existed): the correctness count is the headline
        HERO_NUM = _correct_num
        HERO_TEXT = f"<p>{escape(_correct_text)}</p>"
top_missed = ", ".join(f"{d} ({n})" for d, n in missed_sites.most_common(3))
# Default wording, used when run_notes.json gives none for the run. Every sentence follows this run's numbers, and an
# item whose finding does not hold for the run is left out.
_wrong_n, _go_n = count["All questions"]["Wrong or outdated facts"], count["All questions"]["Guardrails only"]
_no_next = sum("no official next step" in split[i]["causes"] for i in split if i in res and _cb(i) == "F")
_en_acc, _hh_acc = (g.get("Accuracy - English") or [None] * 3)[2], (g.get("Accuracy - Hindi + Hinglish") or [None] * 3)[2]
_lang_known = isinstance(_en_acc, (int, float)) and isinstance(_hh_acc, (int, float))
_fixes = []
if unans:
    _fixes.append(("Help Saathi find the right page",
                   f"{_n(len(unans), 'question')} went unanswered, and for {crawled_unans} of them the answer is on a crawled website"
                   + (f" (the sites missed most: {top_missed})" if top_missed else "") + ". Check that the pages behind the golden "
                   "answers are in the index, improve how pages are ranked within a site, and review when the bot gives up with "
                   '"could not find".'))
if _wrong_n:
    _fixes.append(("Refresh outdated facts",
                   f"{_n(_wrong_n, 'answer')} gave a wrong or old value. Re-crawl the owning portals and, when sources disagree, prefer "
                   "the owning portal over older FAQs and press releases."))
if _no_next:
    _fixes.append(("Fix the answer template",
                   f"End every answer with the official link or next step, and give the helpline when unsure. {_n(_no_next, 'answer')} "
                   f"that fell short ended without an official next step; {_go_n} had the facts right and failed on guardrails alone."))
if abst[1]:
    _fixes.append(("Decline out-of-scope questions clearly",
                   f"Only {abst[0]} of {abst[0] + abst[1]} out-of-scope, personal or unanswerable questions were declined or "
                   "redirected as the guardrails require."))
_lang_gap = _lang_known and _hh_acc < _en_acc
_slow = isinstance(p50, (int, float)) and p50 > 5
if _lang_gap or _slow:
    _fixes.append(({(True, True): "Reply in the user's language, faster", (True, False): "Answer as well in Hindi and Hinglish",
                    (False, True): "Reply faster"}[(_lang_gap, _slow)],
                   " ".join(([f"Hindi and Hinglish answers were right less often than English ones ({pct(_hh_acc)} against "
                              f"{pct(_en_acc)})."] if _lang_gap else [])
                            + ([f"The median reply took {p50:.1f} s against a 5 s target."] if _slow else []))))
_DEFAULT_FIXES_HTML = "\n".join(f"      <li><div><h3>{escape(t)}</h3><p>{escape(x)}</p></div></li>" for t, x in _fixes)

_failures = N - count["All questions"][CORRECT]
_v, _vlabel, _vtarget = ((acc["P0"][1][1], "priority questions", 0.90) if acc["P0"][1][1] is not None else
                         (acc["other"][1][1], "the other questions", 0.85))
_largest_other = max([count["All questions"][c] for c in CLASSES[1:] if c != "Not answered"] or [0])
_DEFAULT_KEYS = [
    (("Every answer passed the correctness check", "No answer had wrong, outdated or missing facts.") if not _failures else
     ("Most failures are about facts" if facts_problem * 2 >= _failures else "Most failures are about behaviour, not facts",
      f"{_n(facts_problem, 'answer')} ({share(facts_problem, N)}) had wrong, outdated or missing facts, or no answer at all; "
      f"{_go_n} ({share(_go_n, N)}) had the right facts and failed on guardrails alone.")),
    (("Every question got an answer", 'No question got a "could not find an official answer" reply.') if not unans else
     ("Unanswered questions are the biggest gap" if len(unans) >= _largest_other else f"{_n(len(unans), 'question')} went unanswered",
      f'{_n(len(unans), 'question')} ({share(len(unans), N)}) got a "could not find an official answer" reply. For {crawled_unans} '
      "of them the answer is on a website the bot has crawled, but it did not reach the page.")),
    (("Fixing guardrails alone will not reach the targets",
      f"Even with guardrail-only failures set aside, accuracy on {_vlabel} would be {pct(_v)}. The release target is "
      f"{_vtarget:.0%}.") if _v is None or _v < _vtarget else
     ("Guardrail fixes would reach the accuracy target",
      f"With guardrail-only failures set aside, accuracy on {_vlabel} would be {pct(_v)}, at or above the {_vtarget:.0%} target.")),
]

# ---------------------------------------------------------------- narrative (run_notes.json "narrative" overrides; defaults = 19 Oct 2026 run)
# second-pass records of answers that still fail Correctness (a verdict corrected later keeps its old record)
still_failed = [i for i in split if i in res and _cb(i) == "F"]
fp = {name: sum(count[name][c] for c in ("Wrong or outdated facts", "Not answered", "Required fact missing")) for name, _ in segments}
fp_share = {name: fp[name] / len(ids) if ids else 0 for name, ids in segments}
CTX = dict(N=N, n_conv=len(convs), facts_problem=facts_problem, facts_problem_share=share(facts_problem, N),
           guardrails_only=count["All questions"]["Guardrails only"], guardrails_only_share=share(count["All questions"]["Guardrails only"], N),
           wrong=count["All questions"]["Wrong or outdated facts"], missing=count["All questions"]["Required fact missing"],
           not_answered=count["All questions"]["Not answered"], behaviour=count["All questions"]["Required behaviour not met"],
           correct=count["All questions"][CORRECT], unans=len(unans), unans_share=share(len(unans), N),
           crawled_unans=crawled_unans, p0_facts_right=pct(acc["P0"][1][1]), oth_facts_right=pct(acc["other"][1][1]),
           next_step=sum("no official next step" in split[i]["causes"] for i in still_failed), failed=len(still_failed),
           wrong_language=sum("wrong language" in split[i]["causes"] for i in still_failed),
           stale_cited=sum(1 for i in still_failed if split[i]["facts"] == "wrong" and res[i].get("Citation support", {}).get("verdict") == "P"),
           abst_ok=abst[0], abst_total=abst[0] + abst[1], p50=(f"{p50:.1f}" if isinstance(p50, (int, float)) else "–"), p95=(f"{p95:.1f}" if isinstance(p95, (int, float)) else "–"), gap=(f"{gap:.1f}" if isinstance(gap, (int, float)) else "–"),
           en=pct(facts_right["English"]), hi=pct(facts_right["Hindi (Devanagari)"]), hg=pct(facts_right["Hinglish (romanised Hindi)"]),
           p0_n=len(p0), p0_fp=fp["P0 (priority)"], p1_fp=fp["P1"], p2_fp=fp["P2"], p1_n=len(segments[2][1]), p2_n=len(segments[3][1]),
           categories=categories, figs_any=figs_any, with_figs=len(with_figs), figs_all=figs_all, page_hit=page_hit,
           known_page=len(known_page), read_site=len(read_site), genu_ok=genu[0], genu_fail=genu[1], genu_total=genu[0] + genu[1])
NARR = NOTES.get("narrative") or {}


def narr(key, default):
    """Run-specific wording from run_notes.json, formatted with the computed numbers and HTML-escaped; else the default."""
    return escape(NARR[key].format_map(CTX)) if key in NARR else default


LEDE = narr("lede", f"We asked Saathi {N} test question{'s' if N != 1 else ''} and {len(convs)} multi-turn conversation{'s' if len(convs) != 1 else ''}, then graded every answer against answers verified on official sites and the team's 16 guardrails. This page sets out what we found and what to fix first.")
KEYS = [(escape(t.format_map(CTX)), escape(x.format_map(CTX))) for t, x in NARR["keys"]] if NARR.get("keys") else None
EX_INTRO = narr("examples_intro", 'Questions and replies are taken from the test run. "Expected" comes from the golden answer verified on the official site.')
P0_WORST = fp_share["P0 (priority)"] >= max(fp_share[n] for n in ("P1", "P2"))
BRACKET_TAIL = narr("bracket_tail", (f"Priority questions fare worst: {fp['P0 (priority)']} of {len(p0)} have a facts problem." if P0_WORST else
                                     f"The share is similar at every priority: {fp['P0 (priority)']} of {len(p0)} P0, {fp['P1']} of "
                                     f"{len(segments[2][1])} P1 and {fp['P2']} of {len(segments[3][1])} P2 questions have a facts problem."))
_lower = "Hindi and Hinglish" if _lang_known and _hh_acc < _en_acc else "English"
GAP_NOTE = narr("gap_note", "" if not _lang_known or not isinstance(gap, (int, float)) else (
    ("The language gap is within target only because accuracy is low in every language." if max(_en_acc, _hh_acc) < 0.5
     else "Accuracy is similar across languages.") if gap <= 5 else
    (f"Accuracy is low in every language, and lower still in {_lower}." if max(_en_acc, _hh_acc) < 0.5
     else f"Accuracy is lower in {_lower}.")))
UNANS_CLOSE = narr("unanswered_close", None)
CHECKS_NOTE = narr("checks_note", "")
FIXES = [(escape(t.format_map(CTX)), escape(x.format_map(CTX))) for t, x in NARR["fixes"]] if NARR.get("fixes") else None
TEST_SET_DD = narr("test_set", None)
GRADING_EXTRA = narr("grading_extra", "")
RESULTS_PATH = NARR.get("results_path", f"golden-tests/eval/runs/{RUN.name}")
FIXES_HTML = ("\n".join(f'      <li><div><h3>{t}</h3><p>{x}</p></div></li>' for t, x in FIXES) if FIXES else _DEFAULT_FIXES_HTML)
KEYS_HTML = "\n".join(f'      <div class="key"><h3>{t}</h3><p>{x}</p></div>' for t, x in (KEYS or _DEFAULT_KEYS))

_few = bool(with_figs) and figs_any * 2 < len(with_figs)
_UNANS_CLOSE_DEFAULT = escape(" ".join(
    (["Most unanswered questions come down to finding the right page."] if crawled_unans * 2 >= len(unans) else [])
    + ([("Better answer writing would fix few of them: the answer's key figures were on the pages Saathi read in only "
         if _few else "The answer's key figures were on the pages Saathi read in ")
        + f"{figs_any} of {len(with_figs)} checkable cases, and all of them in {figs_all}."] if with_figs else [])))
UNANS_SECTION = (f"""  <section id="unanswered">
    <h2>Why {len(unans)} questions went unanswered</h2>
    <p class="sec-intro">For each unanswered question we compared the website that holds the answer with the pages Saathi says it read before replying.</p>
    <div class="chart">
      <div class="panel">{unans_bars()}</div>
    </div>
    <div class="facts">
      <div class="fact"><b>{ug['Read the expected site, no answer']}</b><p><strong>Reached the right website, missed the page.</strong> Saathi read pages from the website that holds the answer, but not the page itself. Where we know the exact page, it was among the pages read in {page_hit} of {len(known_page)} cases.</p></div>
      <div class="fact"><b>{ug['Expected site not retrieved']}</b><p><strong>Never searched the right website.</strong> The website is crawled, but Saathi read nothing from it. The most missed: {escape(top_missed)}.</p></div>
      <div class="fact"><b>{ug['Needs service data (DB/API)']}</b><p><strong>Needs live service data.</strong> The answer comes from UMANG or myScheme service data, not from a web page.</p></div>
      <div class="fact"><b>{ug['No expected source']}</b><p><strong>No source defined</strong> for the question in the test set.</p></div>
    </div>
    <p>{UNANS_CLOSE or _UNANS_CLOSE_DEFAULT}</p>
  </section>
""" if unans else "")  # left out when every question got an answer

html = f"""<title>Saathi Evaluation Findings</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hind:wght@400;500;600&family=Martel:wght@700;800&display=swap">
<style>
  /* Layout: one reading column; a lead finding, then evidence sections that each pair a chart or table with plain words */
  :root {{
    --bg: #f3f5f9; --surface: #ffffff; --ink: #131a27; --ink-2: #485266; --muted: #6f7889; --line: #dce1ea;
    --accent: #1f3a8a; --accent-soft: #e4e9f5; --target: #131a27;
    --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --s6: #008300;
    --good: #0ca30c; --good-ink: #006300; --bad: #d03b3b; --bad-ink: #b02a2a;
    --display: "Martel", Georgia, "Times New Roman", serif;
    --body: "Hind", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #0d1118; --surface: #151a22; --ink: #edf0f5; --ink-2: #b7bfcd; --muted: #8b94a4; --line: #2a3140;
      --accent: #9db4f5; --accent-soft: #1c2640; --target: #edf0f5;
      --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300;
      --good-ink: #3fc43f; --bad-ink: #f07a7a; color-scheme: dark;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #0d1118; --surface: #151a22; --ink: #edf0f5; --ink-2: #b7bfcd; --muted: #8b94a4; --line: #2a3140;
    --accent: #9db4f5; --accent-soft: #1c2640; --target: #edf0f5;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300;
    --good-ink: #3fc43f; --bad-ink: #f07a7a; color-scheme: dark;
  }}
  body {{ background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.6; }}
  .page {{ max-width: 860px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px));
    padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 44px 72px; display: grid; gap: 56px; }}
  h1, h2, h3 {{ text-wrap: balance; margin: 0; }}
  h1 {{ font-family: var(--display); font-weight: 800; font-size: clamp(32px, 6vw, 46px); line-height: 1.12; }}
  h2 {{ font-family: var(--display); font-weight: 700; font-size: clamp(22px, 4vw, 27px); line-height: 1.25; }}
  h3 {{ font-size: 17px; font-weight: 600; line-height: 1.35; }}
  p {{ margin: 0; max-width: 66ch; }}
  .eyebrow {{ font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
  .muted {{ color: var(--muted); }}
  section {{ display: grid; gap: 18px; min-width: 0; }}
  .sec-intro {{ color: var(--ink-2); }}

  header.top {{ display: grid; gap: 14px; }}
  .lede {{ font-size: 18px; color: var(--ink-2); }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 14px; color: var(--muted); }}
  .pill {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; padding: 2px 10px;
    border-radius: 999px; background: var(--accent-soft); color: var(--accent); }}

  .lead {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 28px; display: grid; gap: 26px; }}
  .hero {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 18px; }}
  .hero-num {{ font-size: clamp(52px, 11vw, 76px); font-weight: 600; line-height: 1; letter-spacing: -.02em; }}
  .hero-text {{ font-size: 18px; max-width: 46ch; min-width: 0; display: grid; gap: 10px; }}
  .keys {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 22px; }}
  .key {{ display: grid; gap: 6px; align-content: start; border-top: 2px solid var(--accent); padding-top: 12px; min-width: 0; }}
  .key p {{ color: var(--ink-2); font-size: 15px; }}

  .chart {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 22px; display: grid; gap: 18px; min-width: 0; }}
  .stack-row {{ display: grid; grid-template-columns: 130px 1fr; gap: 14px; align-items: center; }}
  .stack-label {{ display: flex; justify-content: space-between; gap: 8px; font-size: 14px; font-weight: 500; }}
  .stack-label .n {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
  .stack {{ display: flex; gap: 2px; height: 22px; background: var(--surface); min-width: 0; }}
  .seg {{ flex-basis: 0; min-width: 2px; outline-offset: 2px; }}
  .seg:last-child {{ border-radius: 0 4px 4px 0; }}
  .s1 {{ background: var(--s1); }} .s2 {{ background: var(--s2); }} .s3 {{ background: var(--s3); }}
  .s4 {{ background: var(--s4); }} .s5 {{ background: var(--s5); }} .s6 {{ background: var(--s6); }}
  .s7 {{ background: var(--muted); }}
  .legend {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px 22px; }}
  .legend li {{ display: grid; grid-template-columns: 12px 1fr auto; gap: 10px; align-items: center; font-size: 14px; }}
  .sw {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; flex: none; }}
  .lg-val {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  .lg-val .muted {{ font-weight: 400; }}
  .bracket {{ font-size: 14px; color: var(--ink-2); border-left: 3px solid var(--line); padding-left: 12px; }}

  details {{ font-size: 14px; }}
  summary {{ cursor: pointer; color: var(--accent); font-weight: 600; }}
  summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  .table-wrap {{ overflow-x: auto; margin-top: 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 14px; }}
  th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  thead th {{ font-size: 12.5px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
  tr.total td {{ font-weight: 600; }}
  .data-table td:not(:first-child), .data-table th:not(:first-child) {{ white-space: nowrap; }}

  .examples {{ display: grid; gap: 14px; }}
  .example {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 20px 22px; display: grid; gap: 10px; min-width: 0; }}
  .ex-head {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }}
  .ex-n {{ margin-left: auto; font-size: 14px; color: var(--muted); font-variant-numeric: tabular-nums; }}
  .ex-def {{ color: var(--ink-2); font-size: 15px; }}
  .ex-body {{ margin: 0; display: grid; grid-template-columns: 110px 1fr; gap: 6px 16px; font-size: 15px; }}
  .ex-body dt {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .05em; font-weight: 600; padding-top: 2px; }}
  .ex-body dd {{ margin: 0; min-width: 0; }}

  .panels {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }}
  .panel {{ display: grid; gap: 12px; align-content: start; min-width: 0; }}
  .panel-head {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px 12px; }}
  .target-key {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }}
  .target-swatch {{ width: 2px; height: 14px; background: var(--target); display: inline-block; }}
  .hbar-row {{ display: grid; grid-template-columns: minmax(0, 1fr) 54px; grid-template-areas: "label label" "track val"; gap: 4px 10px; align-items: center; }}
  .hbar-label {{ grid-area: label; font-size: 14px; color: var(--ink-2); }}
  .hbar-track {{ grid-area: track; position: relative; height: 20px; border-left: 1px solid var(--line); }}
  .hbar-fill {{ position: absolute; left: 0; top: 0; bottom: 0; background: var(--s1); border-radius: 0 4px 4px 0; min-width: 2px; outline-offset: 2px; }}
  .hbar-fill.alt {{ background: var(--s3); }}
  .target {{ position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--target); transform: translateX(-1px); }}
  .hbar-val {{ grid-area: val; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; }}
  .axis {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-right: 64px; font-variant-numeric: tabular-nums; }}
  .lang-note {{ font-size: 15px; color: var(--ink-2); }}

  .facts {{ display: grid; gap: 12px; }}
  .fact {{ display: grid; grid-template-columns: 54px 1fr; gap: 14px; align-items: baseline; }}
  .fact b {{ font-size: 22px; font-variant-numeric: tabular-nums; text-align: right; }}
  .fact p {{ color: var(--ink-2); font-size: 15px; }}
  .fact strong {{ color: var(--ink); font-weight: 600; }}

  .chip {{ display: inline-flex; align-items: center; gap: 5px; font-size: 13px; font-weight: 600; white-space: nowrap; }}
  .chip svg {{ width: 12px; height: 12px; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }}
  .chip.good {{ color: var(--good-ink); }} .chip.good svg {{ stroke: var(--good); }}
  .chip.bad {{ color: var(--bad-ink); }} .chip.bad svg {{ stroke: var(--bad); }}
  .gates td:nth-child(2) {{ font-variant-numeric: tabular-nums; }}
  .note {{ font-size: 14px; color: var(--muted); }}

  ol.fixes {{ margin: 0; padding-left: 0; list-style: none; counter-reset: fix; display: grid; gap: 16px; }}
  ol.fixes li {{ counter-increment: fix; display: grid; grid-template-columns: 34px 1fr; gap: 12px; }}
  ol.fixes li::before {{ content: counter(fix); font-family: var(--display); font-weight: 800; font-size: 20px; color: var(--accent); line-height: 1.4; }}
  ol.fixes h3 {{ margin-bottom: 2px; }}
  ol.fixes p {{ color: var(--ink-2); font-size: 15px; }}

  dl.method {{ margin: 0; display: grid; grid-template-columns: minmax(140px, 200px) 1fr; gap: 10px 22px; font-size: 15px; }}
  dl.method dt {{ font-weight: 600; }}
  dl.method dd {{ margin: 0; color: var(--ink-2); min-width: 0; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; }}

  .tip {{ position: fixed; z-index: 20; pointer-events: none; background: var(--ink); color: var(--surface); font-size: 13px;
    padding: 6px 10px; border-radius: 6px; max-width: 280px; line-height: 1.4; }}
  .seg:focus-visible, .hbar-fill:focus-visible {{ outline: 2px solid var(--ink); }}

  @media (max-width: 560px) {{
    .stack-row {{ grid-template-columns: 1fr; gap: 6px; }}
    .ex-body {{ grid-template-columns: 1fr; gap: 2px; }}
    .ex-body dd {{ margin-bottom: 8px; }}
    dl.method {{ grid-template-columns: 1fr; gap: 2px; }}
    dl.method dd {{ margin-bottom: 10px; }}
    .lead, .chart {{ padding: 18px; }}
  }}
</style>

<div class="page">
  <header class="top">
    <div class="eyebrow">India.gov.in · Saathi golden-test evaluation</div>
    <h1>Saathi evaluation findings</h1>
    <p class="lede">{LEDE}</p>
  </header>

  <div class="lead">
    <div class="hero">
      <span class="hero-num">{HERO_NUM}</span>
      <div class="hero-text">{HERO_TEXT}</div>
    </div>
    <div class="keys">
{KEYS_HTML}
    </div>
  </div>

{RECHECK_SECTION}
  <section id="groups">
    <h2>Where the {N} answers landed</h2>
    <p class="sec-intro">Each answer sits in the first group that applies, from top to bottom of the legend. An answer with a wrong fact and a missing link counts as wrong facts.</p>
    <div class="chart">
      {stack_rows()}
      <ul class="legend" aria-label="Groups, with counts for all questions">{legend()}</ul>
      <p class="bracket">Wrong, outdated, missing or no facts: <strong>{facts_problem} answers ({share(facts_problem, N)})</strong>. {BRACKET_TAIL}</p>
      <details><summary>Show as a table</summary><div class="table-wrap">{class_table()}</div></details>
    </div>
  </section>

  <section id="examples">
    <h2>What each group means, with real examples</h2>
    <p class="sec-intro">{EX_INTRO}</p>
    <div class="examples">{ex_html}</div>
  </section>

  <section id="targets">
    <h2>How far Saathi is from the release targets</h2>
    <p class="sec-intro">The concept note sets accuracy targets of 90% for priority (P0) questions and 85% for the rest. The bars show accuracy three ways, from the strict grading to the most generous reading.</p>
    <div class="chart">
      <div class="panels">
        {acc_panel(f"Priority (P0) questions, {len(p0)}", 90, acc['P0'])}
        {acc_panel(f"P1 and P2 questions, {len(oth)}", 85, acc['other'])}
      </div>
      <p class="lang-note">Answers in Hindi and Hinglish did worse. The facts were right in {pct(facts_right['Hindi (Devanagari)'])} of Hindi and {pct(facts_right['Hinglish (romanised Hindi)'])} of Hinglish answers, against {pct(facts_right['English'])} of English answers.</p>
    </div>
  </section>

{UNANS_SECTION}
  <section id="checks">
    <h2>{"Release checks: the concept note's and the QE's" if QE_GATES[0][0] else "Release checks from the concept note"}</h2>
    <div class="chart">
      <div class="table-wrap"><table class="gates"><thead><tr><th>Check</th><th>Result</th><th>Target</th><th>Status</th></tr></thead><tbody>{gates_html}</tbody></table></div>
      <p class="note">{GAP_NOTE}{(" " + CHECKS_NOTE) if CHECKS_NOTE else ""}</p>
      <div class="table-wrap"><table><thead><tr><th>Other checks (no release target)</th><th>Result</th></tr></thead><tbody>{extra_html}</tbody></table></div>
    </div>
  </section>

  <section id="fixes">
    <h2>What to fix first</h2>
    <p class="sec-intro">Ordered by how many answers each fix would affect.</p>
    <ol class="fixes">
{FIXES_HTML}
{DEFECTS_LI}    </ol>
  </section>

  <section id="method">
    <h2>How this was measured</h2>
    <dl class="method">
      <dt>Test set</dt><dd>{TEST_SET_DD or f"{N} single questions across {categories} service categories in English, Hindi and Hinglish, written for different citizen profiles, plus {len(convs)} multi-turn conversations. Each has a golden answer verified on the official site."}</dd>
      <dt>Grading</dt><dd>Rule-based checks for links, figures and personal data. A model grader ({JUDGE_NAME} on Amazon Bedrock) checked facts against the golden answer, citations, freshness and the 16 guardrails. A second grading pass separated fact problems from guardrail problems.{(" " + GRADING_EXTRA) if GRADING_EXTRA else ""}</dd>{SCORING_DD}{BOT_DD}{PASS_RULE_DD}{RECHECK_DD}{LATENCY_DD}
      <dt>Status</dt><dd>Preliminary. The concept note (9.3.4) requires the model grader to agree with human graders on at least 90% of a sample before its results are relied on. That check has not been done yet.</dd>
{COST_DD}
      <dt>Full results</dt><dd><code>{RESULTS_PATH}/findings_by_test_case.xlsx</code> has one row per test case for review. <code>report.xlsx</code> in the same folder has the gates and analysis sheets.</dd>
    </dl>
  </section>
</div>
<div class="tip" id="tip" hidden></div>
<script>
  (function () {{
    var tip = document.getElementById("tip");
    function show(el, x, y) {{
      tip.textContent = el.getAttribute("data-tip");
      tip.hidden = false;
      var r = tip.getBoundingClientRect();
      var left = Math.min(Math.max(8, x + 12), window.innerWidth - r.width - 8);
      var top = y - r.height - 12 < 8 ? y + 16 : y - r.height - 12;
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }}
    document.querySelectorAll("[data-tip]").forEach(function (el) {{
      el.addEventListener("pointermove", function (e) {{ show(el, e.clientX, e.clientY); }});
      el.addEventListener("pointerleave", function () {{ tip.hidden = true; }});
      el.addEventListener("focus", function () {{ var b = el.getBoundingClientRect(); show(el, b.left + b.width / 2, b.top); }});
      el.addEventListener("blur", function () {{ tip.hidden = true; }});
    }});
  }})();
</script>
"""
if ARGS.artifact_out:
    Path(ARGS.artifact_out).write_text(html, encoding="utf-8")

# Standalone file to share by email or chat: full document, works when opened straight from disk
head, body = html.split("</style>", 1)
STANDALONE = RUN / "saathi-findings.html"
STANDALONE.write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    + """  body { margin: 0; -webkit-text-size-adjust: 100%; }
  [hidden] { display: none !important; }
  @media print {
    :root { --bg: #ffffff; }
    .page { padding-block: 0; gap: 36px; }
    .lead, .chart, .example { break-inside: avoid; }
    .tip { display: none !important; }
  }
</style>
</head>
<body>""" + body + "</body>\n</html>\n", encoding="utf-8")
print(f"wrote {STANDALONE}" + (f" and {ARGS.artifact_out}" if ARGS.artifact_out else "")
      + (f" | checklist rule: {dict(cl_status)}" if CHECKLIST else f" | pass {all_pass}, partial {partial} of {N}")
      + f" | facts problem {facts_problem}"
      + (f" | chatbot score {BOT['mean']:.0%} (95% range {BOT['low']:.0%}-{BOT['high']:.0%}, {BOT['n']} test cases)"
         if BOT["low"] is not None else ""))
