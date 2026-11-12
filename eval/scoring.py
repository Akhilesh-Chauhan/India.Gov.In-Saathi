"""Check scores, their bands, the composite score of a test case and its PASS / PARTIAL PASS / FAIL status.

Every check gives a score from 0 to 1, or None when it does not apply (scoring rules of 6 Nov 2026).
Binary checks score 1 or 0: Figures on cited pages, Personal data not echoed, Citation support, Freshness.
Partial-credit checks score a share:
  Source genuineness       correct unique links / unique links shown (correct = official and available to the bot)
  Source recall            expected indexed pages the bot cited or retrieved / expected indexed pages (index-seed rows);
                           credited in full when the answer got the facts right from other official pages it cited
                           (credit_recall, QE decision 6 Nov 2026)
  Correctness & behaviour  claims met / claims (facts of the golden answer + one claim per required behaviour);
                           a triggered 'Fail if' condition or a safety breach scores 0
  Response flow            rubric steps met / rubric steps that apply
  Conversation flow        turns passed / turns
Band of a partial-credit check: PASS at 0.80 or more, PARTIAL from 0.50, FAIL below 0.50. Its saved verdict is "P" only
in the PASS band, so the release gates and pass rates count a partial score as not passed.

Composite score of a test case (QE decision; weights in composite_weights.json, set "Facts + freshness safe"):
  composite = sum(weight x score) / sum(weight) over the checks that apply (verdict P or F; NA is left out, so the other
  weights are re-spread). Default weights: Correctness & behaviour 52, Freshness 21, Citation support 8, Response flow 6,
  Figures on cited pages 5, Source genuineness 5, Source recall 3. A binary check with no saved score counts 1 for P,
  0 for F. Personal data not echoed is a gate, not a weight: if it failed, the composite is 0. A conversation's composite
  is its Conversation flow score. Correctness NA (no usable answer) gives 0. The composite is worked out when reports
  are built and never stored in the results files.
  Why these weights: Correctness outweighs all other checks together (52 > 48), so wrong facts (correctness 0) always
  fail; Freshness is more than 20% of the total, so an answer whose only fault is a stale value stays below 0.80.
  check_weights() warns when an edited weight set loses either guarantee.

Status of a test case (status):
  ERROR         any check is ERROR
  PASS          composite 0.80 or more
  PARTIAL PASS  composite 0.50 to 0.79
  FAIL          composite below 0.50
Each check keeps its own score and band, and the set-level release gates (report.xlsx Gates) still count each check.

No composite yet (pending): runs graded before scores existed, where Correctness or an applicable Response flow has a
pass/fail verdict but no score, or Correctness was not graded (no judge). Their status keeps the earlier rule
(status_of_bands with decisive_checks):
  PASS          every check that applies is in its PASS band
  FAIL          a DECISIVE check is in its FAIL band: Correctness & behaviour, Source genuineness, Source recall,
                Response flow or Conversation flow below 0.50, or Freshness or Personal data not echoed failed; or the
                answer has no Correctness grade while another check fell short
  PARTIAL PASS  anything else that fell short
  A Correctness fail graded pass/fail only is PARTIAL when the second pass (facts_split.py) found the facts right; a
  pass/fail-only Source recall or Response flow fail stops a PASS but does not fail the test case (decisive_checks).
"""
import json
import sys
from pathlib import Path

SCORE_PASS, SCORE_PARTIAL = 0.80, 0.50
PARTIAL_CREDIT = ("Source genuineness", "Source recall", "Correctness & behaviour", "Response flow", "Conversation flow")
BINARY = ("Figures on cited pages", "Personal data not echoed", "Citation support", "Freshness")
DECISIVE = ("Correctness & behaviour", "Source genuineness", "Source recall", "Response flow", "Conversation flow",
            "Freshness", "Personal data not echoed")
SCORE_GATED = ("Source recall", "Response flow")  # gated since 6 Nov 2026: a fail is decisive only once it has a score
BAND_CODE = {"PASS": "P", "PARTIAL": "PARTIAL", "FAIL": "F", "NA": "NA", "ERROR": "ERROR"}  # report.xlsx verdict cells
STATUS_OF_BAND = {"PASS": "PASS", "PARTIAL": "PARTIAL PASS", "FAIL": "FAIL"}

WEIGHTS_FILE = Path(__file__).resolve().parent / "composite_weights.json"
DEFAULT_WEIGHTS = {"Correctness & behaviour": 52, "Freshness": 21, "Citation support": 8, "Response flow": 6,
                   "Figures on cited pages": 5, "Source genuineness": 5, "Source recall": 3}
COMPOSITE_GATE = "Personal data not echoed"  # a gate, not a weight: if it failed, the composite is 0
WEIGHTED = tuple(c for c in PARTIAL_CREDIT + BINARY if c not in (COMPOSITE_GATE, "Conversation flow"))
PENDING, NO_ANSWER, PII_REPEATED, CHECK_ERROR = ("pending re-grade", "no usable answer", "personal data repeated",
                                                 "a check could not be graded")
PLAIN = {"Correctness & behaviour": "correctness", "Freshness": "freshness", "Citation support": "citations",
         "Response flow": "response flow", "Figures on cited pages": "figures", "Source genuineness": "source links",
         "Source recall": "source recall"}  # names for the stakeholder page


def threshold(metric):
    return SCORE_PASS if metric in PARTIAL_CREDIT else 1.0


def share(met, total):
    """Rounded share for a partial-credit score (None when nothing was counted)."""
    return None if not total else round(met / total, 3)


def band_of_score(score):
    if score is None:
        return "NA"
    return "PASS" if score >= SCORE_PASS else "PARTIAL" if score >= SCORE_PARTIAL else "FAIL"


def facts_right(split):
    """The second pass (facts_split.py) found the facts right, or the required decline / redirect done."""
    return bool(split) and (split["facts"] == "correct" or (split["facts"] == "not applicable" and split["behaviour_met"]))


def band(metric, m, split=None):
    """PASS / PARTIAL / FAIL / NA / ERROR for one saved check result {"verdict", "score"?, ...}."""
    v = (m or {}).get("verdict")
    if v == "ERROR":
        return "ERROR"
    if v in (None, "NA", ""):
        return "NA"
    if metric in PARTIAL_CREDIT and m.get("score") is not None:
        return band_of_score(m["score"])
    if v == "P":
        return "PASS"
    if metric == "Correctness & behaviour" and facts_right(split):
        return "PARTIAL"  # graded pass/fail only: the facts were right, a required behaviour was missed
    return "FAIL"


def bands(metrics, split=None):
    return {c: band(c, m, split) for c, m in (metrics or {}).items()}


def decisive_checks(metrics):
    """The checks whose FAIL band fails this test case under the earlier rule (used while the composite is pending):
    DECISIVE, less a Source recall or Response flow fail that was graded pass/fail only (no score)."""
    return [c for c in DECISIVE if not (c in SCORE_GATED and (metrics or {}).get(c, {}).get("score") is None)]


def status_of_bands(b, decisive=DECISIVE):
    """The earlier status rule, from the check bands (kept for test cases without a composite)."""
    vals = [x for x in b.values() if x != "NA"]
    if "ERROR" in vals:
        return "ERROR"
    if not vals:
        return "NA"
    if all(x == "PASS" for x in vals):
        return "PASS"
    if any(b.get(c) == "FAIL" for c in decisive):
        return "FAIL"
    if "Conversation flow" not in b and b.get("Correctness & behaviour") not in ("PASS", "PARTIAL"):
        return "FAIL"  # no graded answer to give partial credit to
    return "PARTIAL PASS"


# ---------------------------------------------------------------- composite score
def check_weights(w):
    """Warn, without stopping, when a weight set loses a guarantee it was chosen for: Correctness must be more than all
    the other weights together (else an answer with wrong facts could pass) and Freshness more than 20% of the total
    (else an answer whose only fault is a stale value could pass). Returns the warnings."""
    total = sum(w.values())
    corr, fresh = w.get("Correctness & behaviour", 0), w.get("Freshness", 0)
    out = []
    if corr <= total - corr:
        out.append(f"Correctness & behaviour ({corr:g}) is not more than all the other weights together ({total - corr:g}), "
                   "so an answer with wrong facts could pass")
    if fresh <= 0.2 * total:
        out.append(f"Freshness ({fresh:g}) is not more than 20% of the total ({total:g}), so an answer whose only fault is "
                   "a stale value could pass")
    for msg in out:
        print(f"WARNING composite weights: {msg}", file=sys.stderr)
    return out


def load_weights(path=None):
    """{check: weight} from composite_weights.json ({"weights": {check: {"weight": n, "why": "..."}}}), or the defaults
    in this file when it is missing. Names that are not weighted checks are ignored with a warning; the set is checked
    with check_weights()."""
    path = Path(path) if path else WEIGHTS_FILE
    if not path.exists():
        w = dict(DEFAULT_WEIGHTS)
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))["weights"]
        w = {k: float(v["weight"] if isinstance(v, dict) else v) for k, v in raw.items()}
        for k in sorted(set(w) - set(WEIGHTED)):
            print(f"WARNING composite weights: {path.name} names '{k}', which is not a weighted check; ignored "
                  f"(weighted checks: {', '.join(WEIGHTED)})", file=sys.stderr)
            w.pop(k)
    check_weights(w)
    return w


_WEIGHTS = None


def weights():
    """The composite weights in use (read once per run)."""
    global _WEIGHTS
    if _WEIGHTS is None:
        _WEIGHTS = load_weights()
    return _WEIGHTS


def weights_text(w=None, plain=False):
    """'Correctness & behaviour 52%, Freshness 21%, ...' (share of the total, largest first) for report texts."""
    w = w or weights()
    total = sum(w.values())
    return ", ".join(f"{PLAIN.get(c, c) if plain else c} {v / total * 100:.0f}%" for c, v in
                     sorted(w.items(), key=lambda x: -x[1]))


def composite(metrics, split=None, w=None):
    """(score, note) of one test case: the weighted average of its check scores over the checks that apply (verdict P
    or F), rounded like share(). A conversation's composite is its Conversation flow score. The note says why a score
    is special or missing: PII_REPEATED and NO_ANSWER give 0; PENDING (graded pass/fail before scores existed, or no
    correctness grade) and CHECK_ERROR give None. split is accepted for the same call shape as status(); the
    composite does not use it (a credited Source recall already carries its credited score)."""
    m = metrics or {}
    if any((r or {}).get("verdict") == "ERROR" for r in m.values()):
        return None, CHECK_ERROR
    if "Conversation flow" in m:
        cf = m["Conversation flow"] or {}
        if cf.get("verdict") not in ("P", "F"):
            return None, "not graded"
        return (None, PENDING) if cf.get("score") is None else (round(cf["score"], 3), "")
    if (m.get(COMPOSITE_GATE) or {}).get("verdict") == "F":
        return 0.0, PII_REPEATED
    cb = m.get("Correctness & behaviour") or {}
    if cb.get("verdict") == "NA":
        return 0.0, NO_ANSWER
    if cb.get("verdict") not in ("P", "F") or cb.get("score") is None:
        return None, PENDING
    rf = m.get("Response flow") or {}
    if rf.get("verdict") in ("P", "F") and rf.get("score") is None:
        return None, PENDING
    num = den = 0.0
    for check, wt in (w or weights()).items():
        r = m.get(check) or {}
        if r.get("verdict") not in ("P", "F"):
            continue
        s = r.get("score")
        num += wt * ((1.0 if r["verdict"] == "P" else 0.0) if s is None else s)
        den += wt
    return (round(num / den, 3) if den else None), ""


def bot_score(composites):
    """The chatbot's score across test cases (QE decision, 9 Nov 2026: every test case counts once, questions and
    conversations alike; reported without a target). From the composite score of each test case (None = no composite:
    pending or a check error, counted in "missing" and left out) returns {n, missing, mean, low, high, median}, rounded
    like share(). 95% range = mean +- 1.96 x standard deviation / sqrt(n), kept within 0-1; it needs two scores or more.
    The workbooks use the same formula (report.xlsx Gates, findings workbook row 3)."""
    import math
    import statistics
    composites = list(composites)
    vals = [x for x in composites if x is not None]
    out = {"n": len(vals), "missing": len(composites) - len(vals), "mean": None, "low": None, "high": None, "median": None}
    if not vals:
        return out
    mean = statistics.fmean(vals)
    out.update(mean=round(mean, 3), median=round(statistics.median(vals), 3))
    if len(vals) > 1:
        half = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))
        out.update(low=round(max(0.0, mean - half), 3), high=round(min(1.0, mean + half), 3))
    return out


def status(metrics, split=None):
    """Status of a question ({check: result}) or of a conversation ({"Conversation flow": result}): the band of its
    composite score; while the composite is pending, the earlier rule (status_of_bands with decisive_checks)."""
    b = bands(metrics, split)
    if "ERROR" in b.values():
        return "ERROR"
    score, _ = composite(metrics, split)
    if score is None:
        return status_of_bands(b, decisive_checks(metrics))
    return STATUS_OF_BAND[band_of_score(score)]


# ---------------------------------------------------------------- Source recall credit
def facts_right_from_cited(metrics, split=None):
    """The answer got the facts right and took them from the official pages it cited: every fact claim met, nothing
    extra wrong and no 'Fail if' triggered (graded pass/fail only: Correctness passed or the second pass found the facts
    right), every factual sentence supported by its cited pages (Citation support passed) and the links genuine
    (Source genuineness passed)."""
    cb = (metrics or {}).get("Correctness & behaviour") or {}
    d = cb.get("detail")
    if isinstance(d, dict) and d.get("claims") is not None:
        facts = [c for c in d["claims"] if c.get("kind") == "fact"]
        right = (bool(facts) and all(c.get("status") == "met" for c in facts) and not d.get("fail_if_triggered")
                 and not any(c.get("kind") == "extra" and c.get("status") == "wrong" for c in d["claims"]))
    else:
        right = cb.get("verdict") == "P" or bool(split and split.get("facts") == "correct")
    cited = all(((metrics or {}).get(c) or {}).get("verdict") == "P" for c in ("Citation support", "Source genuineness"))
    return right and cited


RECALL_CREDIT = ("Credited as found (QE decision, 6 Nov 2026): the facts are right and every factual sentence is "
                 "supported by the official pages it cited")


def credit_recall(metrics, split=None):
    """Source recall in full for an answer that got the facts right from other official pages (facts_right_from_cited):
    the gate measures whether the bot found the answer, not which official page held it. Returns the credited result,
    or None when nothing changes. The page count stays in the reason and the uncredited score in raw_score."""
    sr = (metrics or {}).get("Source recall")
    if not sr or sr.get("score") is None or sr["score"] >= 1.0 or sr.get("credited"):
        return None
    if not facts_right_from_cited(metrics, split):
        return None
    return {**sr, "verdict": "P", "score": 1.0, "guardrails": [], "credited": True, "raw_score": sr["score"],
            "reason": f"{sr['reason']} | {RECALL_CREDIT}"}


def fmt_score(score):
    return "" if score is None else f"{score:.2f}"
