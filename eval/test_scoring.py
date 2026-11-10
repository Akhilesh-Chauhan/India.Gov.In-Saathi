"""Offline checks of the scoring rules (scoring.py, metrics.py): no bot, no network, no Bedrock.

Uses the examples the scoring rules were agreed with (6 Nov 2026): 3 correct links of 5 score 0.6, 4 expected pages of 6
score 0.67, 5 claims of 10 score 0.5, 1 good turn of 2 scores 0.5. Run: ../.venv/bin/python test_scoring.py
"""
import io
import sys
from contextlib import redirect_stderr
from types import SimpleNamespace

import metrics
from metrics import (Claim, ClaimReport, ConversationFlow, ConversationReport, CorrectnessBehaviour, FlowReport,
                     ResponseFlow, SourceGenuineness, SourceRecall, StepCheck, TurnVerdict, conversation_score, page_key)
from scoring import DEFAULT_WEIGHTS, band, band_of_score, bot_score, check_weights, composite, status, weights

OK = []


def check(name, got, want):
    OK.append(got == want)
    print(f"{'OK ' if got == want else 'BAD'} {name}: got {got!r}, want {want!r}")


class FakeJudge:
    def __init__(self, reply):
        self.reply = reply

    def get_model_name(self):
        return "fake-judge"

    def generate(self, prompt, schema=None):
        self.prompt = prompt
        return self.reply


def case(**md):
    base = {"row": {"Source availability": "Crawled", "Question type (concept note)": "Scheme / fact detail (6.2)"},
            "sources": [], "pages": {}, "answer": "an answer", "kind": "answer", "citations": [], "suggested": []}
    base.update(md)
    return SimpleNamespace(metadata=base, input="question", actual_output=base["answer"], expected_output="golden", turns=[])


ok_page = {"status": 200, "final": "", "text": "", "error": None}

# Source genuineness: correct unique links / unique links shown
links = ["https://uidai.gov.in/a", "http://www.uidai.gov.in/a/", "https://pib.gov.in/b", "https://www.myscheme.gov.in/c",
         "https://uidai-gov.in/x", "https://example.com/y"]
sg = SourceGenuineness(frozenset({"uidai.gov.in", "pib.gov.in"}), frozenset())
sg.measure(case(sources=links, pages={u: ok_page for u in links}))
check("links: 3 correct of 5 unique (a duplicate counted once)", sg.score, 0.6)
check("links: 0.6 is the partial band and not a pass", (band_of_score(sg.score), sg.success), ("PARTIAL", False))
check("links: look-alike and non-official named, G01", ("uidai-gov.in/x" in sg.reason and "example.com" in sg.reason, sg.violated), (True, ["G01"]))
sg = SourceGenuineness(frozenset({"uidai.gov.in"}), frozenset())
sg.measure(case(sources=["https://uidai.gov.in/a"], pages={"https://uidai.gov.in/a": {"status": None, "error": "timed out"}}))
check("links: a link that did not open still counts, with a note", (sg.score, "did not open" in sg.reason), (1.0, True))
sg = SourceGenuineness(frozenset(), frozenset({"parivahan.gov.in"}))
sg.measure(case(sources=["https://parivahan.gov.in/en/content/renewal"], pages={"https://parivahan.gov.in/en/content/renewal": ok_page}))
check("links: a site in the bot's index export is available to the bot", sg.score, 1.0)
sg = SourceGenuineness(frozenset(), frozenset())
sg.measure(case(sources=["https://somenew.gov.in/page"], pages={"https://somenew.gov.in/page": ok_page}))
check("links: official but not available to the bot is not correct", sg.score, 0.0)
sg = SourceGenuineness(frozenset(), frozenset())
sg.measure(case(sources=[]))
check("links: no link where one is needed scores 0", sg.score, 0.0)

# Source recall: expected indexed pages cited or retrieved / expected pages (English and /hi/ copies are one page)
metrics._INDEX_PAGES = frozenset(page_key(u) for u in ["https://x.gov.in/p%d" % n for n in range(1, 6)] + ["https://x.gov.in/en/p6"])
evidence = "\n".join(f'https://x.gov.in/p{n} - "words {n}" [index export 3 Nov 2026: x]' for n in range(1, 6)) + \
           '\nhttps://x.gov.in/en/p6 - "words 6" [index export]\nhttps://not-in-index.gov.in/q - "w" [crawled, copy 2026-10-28]'
sr = SourceRecall()
sr.measure(case(row={"Index chunk URL": "https://x.gov.in/p1"}, evidence=evidence,
                sources=["https://x.gov.in/p1", "https://www.x.gov.in/p2/", "https://x.gov.in/hi/p6"],
                checked_urls=["https://x.gov.in/p3"]))
check("recall: 4 of 6 expected pages (one only retrieved, one Hindi copy)", sr.score, 0.667)
check("recall: evidence page outside the index is not expected", "not-in-index" in sr.reason, False)
sr = SourceRecall()
sr.measure(case(row={}, evidence=evidence))
check("recall: applies only to index-seed rows", sr.score, None)

# Correctness & behaviour: claims met / claims
def claim(status_, kind="fact"):
    return Claim(kind=kind, claim="c", status=status_, note="")


ten = [claim("met")] * 4 + [claim("met", "behaviour")] + [claim("missing")] * 3 + [claim("wrong")] + [claim("missing", "behaviour")]
cb = CorrectnessBehaviour(FakeJudge(ClaimReport(claims=ten, fail_if_triggered=False, fail_if_detail="", no_usable_answer=False,
                                                violated_guardrails=["G07"], reason="r")))
cb.measure(case())
check("correctness: 5 claims met of 10 (a wrong claim counts as not met)", (cb.score, band_of_score(cb.score)), (0.5, "PARTIAL"))
extra = ten + [claim("met", "extra"), claim("wrong", "extra")]
cb = CorrectnessBehaviour(FakeJudge(ClaimReport(claims=extra, fail_if_triggered=False, fail_if_detail="", no_usable_answer=False,
                                                violated_guardrails=[], reason="r")))
cb.measure(case())
check("correctness: an extra correct fact is ignored, an extra wrong one counts", cb.score, round(5 / 11, 3))
cb = CorrectnessBehaviour(FakeJudge(ClaimReport(claims=[claim("met")] * 5, fail_if_triggered=True, fail_if_detail="invented helpline",
                                                no_usable_answer=False, violated_guardrails=["G03"], reason="r")))
cb.measure(case())
check("correctness: a triggered 'Fail if' or safety breach scores 0", cb.score, 0.0)
judge = FakeJudge(ClaimReport(claims=[claim("met", "behaviour")], fail_if_triggered=False, fail_if_detail="", no_usable_answer=False,
                              violated_guardrails=[], reason="r"))
CorrectnessBehaviour(judge).measure(case(kind="blocked"))
check("correctness: a fixed guardrail reply gets the owner's rule in the prompt", "FIXED GUARDRAIL REPLIES" in judge.prompt, True)

# Response flow: rubric steps met / steps that apply
rubric = "Use-case flow (deck slide 10): (1) a; (2) b; (3) c; (4) documents, exact official link that opens; (5) e."
steps = [StepCheck(step=1, status="met", reason=""), StepCheck(step=2, status="met", reason=""),
         StepCheck(step=3, status="not_applicable", reason=""), StepCheck(step=4, status="met", reason=""),
         StepCheck(step=5, status="not_met", reason="no next step")]
judge = FakeJudge(FlowReport(steps=steps, violated_guardrails=["G07"], reason="r"))
rf = ResponseFlow(judge)
rf.measure(case(row={"Expected response flow (deck slide 10)": rubric}))
check("flow: 3 of 4 applicable steps", rf.score, 0.75)
check("flow: 'link that opens' is judged as 'exact official link'", ("that opens" in judge.prompt, "exact official link" in judge.prompt), (False, True))
judge = FakeJudge(FlowReport(steps=steps, violated_guardrails=["G07"], reason="r"))
rf = ResponseFlow(judge)
rf.measure(case(kind="blocked", row={"Expected response flow (deck slide 10)": rubric}))
check("flow: a fixed guardrail reply is NA without a judge call", (rf.skipped, rf.score, hasattr(judge, "prompt")), (True, None, False))

# Conversation flow: turns passed / turns
cf = ConversationFlow(FakeJudge(ConversationReport(turns=[TurnVerdict(turn=1, verdict="PASS", reason="ok"),
                                                          TurnVerdict(turn=2, verdict="FAIL", reason="no next step")],
                                                   violated_guardrails=["G07"])), [("u1", "e1"), ("u2", "e2")])
cf.measure(SimpleNamespace(turns=[]))
check("conversation: 1 good turn of 2", cf.score, 0.5)
check("conversation: saved reason of the pass/fail grading", conversation_score("F", "Turn 2: no next step", 2), 0.5)
check("conversation: saved reason naming every turn", conversation_score("F", "Turn 1: x | Turn 2: y", 2), 0.0)

# Bands and the status of a test case: the band of its composite score (weights 52/21/8/6/5/5/3, composite_weights.json)
check("band: 0.80 passes, 0.79 is partial, 0.50 partial, 0.49 fails",
      [band_of_score(x) for x in (0.8, 0.79, 0.5, 0.49)], ["PASS", "PARTIAL", "PARTIAL", "FAIL"])
P, F = {"verdict": "P", "score": 1.0}, {"verdict": "F", "score": 0.0}
NA = {"verdict": "NA", "score": None}
check("weights: the file holds the agreed set", weights(), {"Correctness & behaviour": 52, "Freshness": 21, "Citation support": 8,
      "Response flow": 6, "Figures on cited pages": 5, "Source genuineness": 5, "Source recall": 3})
check("status: every check passes", status({"Correctness & behaviour": {"verdict": "P", "score": 0.9}, "Citation support": P}), "PASS")
check("status: correctness 0.9 with citation support failed: (46.8 + 0) / 60 = 0.78 -> partial",
      (composite({"Correctness & behaviour": {"verdict": "P", "score": 0.9}, "Citation support": F})[0],
       status({"Correctness & behaviour": {"verdict": "P", "score": 0.9}, "Citation support": F})), (0.78, "PARTIAL PASS"))
check("status: correctness 0.6 -> partial", status({"Correctness & behaviour": {"verdict": "F", "score": 0.6}, "Citation support": P}), "PARTIAL PASS")
check("status: correctness 0.4 -> fail", status({"Correctness & behaviour": {"verdict": "F", "score": 0.4}}), "FAIL")
check("status: source genuineness 0.4 is outweighed by correct facts -> pass (was fail before the composite)",
      status({"Correctness & behaviour": {"verdict": "P", "score": 1.0}, "Source genuineness": {"verdict": "F", "score": 0.4}}), "PASS")
check("status: correctness 1.0 and a stale value: 52 / 73 = 0.71 -> partial (was fail before the composite)",
      (composite({"Correctness & behaviour": {"verdict": "P", "score": 1.0}, "Freshness": F})[0],
       status({"Correctness & behaviour": {"verdict": "P", "score": 1.0}, "Freshness": F})), (0.712, "PARTIAL PASS"))
check("status: conversation 0.5 -> partial", status({"Conversation flow": {"verdict": "F", "score": 0.5}}), "PARTIAL PASS")
check("band: a judge error stays an error", band("Citation support", {"verdict": "ERROR"}), "ERROR")
# The release gates (6 Nov 2026) still count every answer on the Gates sheet, but in a test case's composite a low
# Source recall or Response flow is weighed with the rest instead of failing it on its own
good = {"Correctness & behaviour": {"verdict": "P", "score": 0.9}}
check("composite: source recall 0.33 with correctness 0.9: (46.8 + 1) / 55 = 0.87 -> pass",
      (composite({**good, "Source recall": {"verdict": "F", "score": 0.333}})[0],
       status({**good, "Source recall": {"verdict": "F", "score": 0.333}})), (0.869, "PASS"))
check("composite: response flow 0.40 with correctness 0.9: (46.8 + 2.4) / 58 = 0.85 -> pass",
      (composite({**good, "Response flow": {"verdict": "F", "score": 0.4}})[0],
       status({**good, "Response flow": {"verdict": "F", "score": 0.4}})), (0.848, "PASS"))
check("composite: response flow 0.40 with correctness 0.7 -> partial", status({"Correctness & behaviour": {"verdict": "F", "score": 0.7},
      "Response flow": {"verdict": "F", "score": 0.4}}), "PARTIAL PASS")
check("status: conversation 0.25 -> fail", status({"Conversation flow": {"verdict": "F", "score": 0.25}}), "FAIL")

# Composite score: weighted average over the checks that apply
check("composite: weights re-spread over the checks that apply (NA left out): (0.5 x 52 + 8) / 60",
      composite({"Correctness & behaviour": {"verdict": "F", "score": 0.5}, "Citation support": P, "Freshness": NA,
                 "Figures on cited pages": NA, "Response flow": NA}), (round(34 / 60, 3), ""))
ALL = {c: dict(P) for c in ("Freshness", "Citation support", "Response flow", "Figures on cited pages", "Source genuineness",
                            "Source recall", "Personal data not echoed")}
check("composite: correctness 0 with every other check at 1 (all applying) -> 0.48, fail",
      (composite({**ALL, "Correctness & behaviour": {"verdict": "F", "score": 0.0}})[0],
       status({**ALL, "Correctness & behaviour": {"verdict": "F", "score": 0.0}})), (0.48, "FAIL"))
check("composite: a lone freshness fail stays below 0.80 (0.79, partial)",
      (composite({**ALL, "Correctness & behaviour": P, "Freshness": F})[0],
       status({**ALL, "Correctness & behaviour": P, "Freshness": F})), (0.79, "PARTIAL PASS"))
check("composite: a lone freshness fail stays below 0.80 even when other checks do not apply",
      composite({"Correctness & behaviour": P, "Freshness": F, "Citation support": P})[0] < 0.80, True)
check("composite: personal data repeated is a gate -> 0, fail",
      (composite({**ALL, "Correctness & behaviour": P, "Personal data not echoed": F}),
       status({**ALL, "Correctness & behaviour": P, "Personal data not echoed": F})), ((0.0, "personal data repeated"), "FAIL"))
check("composite: a binary check with no saved score counts 1 for P, 0 for F",
      composite({"Correctness & behaviour": {"verdict": "P", "score": 1.0}, "Citation support": {"verdict": "F"}})[0], round(52 / 60, 3))
check("composite: a credited source recall uses its credited score",
      composite({"Correctness & behaviour": P, "Source recall": {"verdict": "P", "score": 1.0, "credited": True, "raw_score": 0.0}})[0], 1.0)
check("composite: correctness NA (no usable answer) -> 0, fail",
      (composite({"Correctness & behaviour": NA, "Citation support": P}), status({"Correctness & behaviour": NA, "Citation support": P})),
      ((0.0, "no usable answer"), "FAIL"))
check("composite pending: correctness graded pass/fail only -> earlier rule (facts right -> partial)",
      (composite({"Correctness & behaviour": {"verdict": "F"}}),
       status({"Correctness & behaviour": {"verdict": "F"}}, {"facts": "correct", "behaviour_met": False})), ((None, "pending re-grade"), "PARTIAL PASS"))
check("composite pending: earlier rule, facts wrong -> fail",
      status({"Correctness & behaviour": {"verdict": "F"}}, {"facts": "wrong", "behaviour_met": False}), "FAIL")
check("composite pending: response flow graded pass/fail only -> earlier rule (stops a pass, no fail)",
      (composite({**good, "Response flow": {"verdict": "F"}})[0], status({**good, "Response flow": {"verdict": "F"}})), (None, "PARTIAL PASS"))
check("composite pending: no correctness grade (no judge) -> earlier rule",
      (composite({"Source genuineness": P})[1], status({"Source genuineness": P}), status({"Source genuineness": F})),
      ("pending re-grade", "PASS", "FAIL"))
check("composite: a conversation's composite is its score", (composite({"Conversation flow": {"verdict": "F", "score": 0.25}}),
      status({"Conversation flow": {"verdict": "P", "score": 0.8}})), ((0.25, ""), "PASS"))
check("composite: any check ERROR -> status ERROR, no composite",
      (composite({"Correctness & behaviour": P, "Freshness": {"verdict": "ERROR"}})[0],
       status({"Correctness & behaviour": P, "Freshness": {"verdict": "ERROR"}})), (None, "ERROR"))
with redirect_stderr(io.StringIO()) as err:
    bad = check_weights({"Correctness & behaviour": 40, "Freshness": 20, "Citation support": 20, "Source recall": 20})
check("check_weights: warns when correctness does not outweigh the rest and freshness is 20% or less",
      (len(bad), "wrong facts could pass" in err.getvalue(), "stale value could pass" in err.getvalue()), (2, True, True))
with redirect_stderr(io.StringIO()) as err:
    good_set = check_weights(DEFAULT_WEIGHTS)
check("check_weights: the agreed set has no warning", (good_set, err.getvalue()), ([], ""))

# Chatbot score: the average composite of all test cases, each counting once, with a 95% range (QE decision 9 Nov 2026)
vals = [0.2, 0.4, 0.6, 0.8, 1.0]  # mean 0.6, sample SD 0.3162, half range 1.96 x 0.3162 / sqrt(5) = 0.2772
check("chatbot score: average, 95% range and median of a known list", bot_score(vals),
      {"n": 5, "missing": 0, "mean": 0.6, "low": 0.323, "high": 0.877, "median": 0.6})
check("chatbot score: a test case without a composite is counted as missing, not as 0",
      bot_score(vals + [None, None]), {"n": 5, "missing": 2, "mean": 0.6, "low": 0.323, "high": 0.877, "median": 0.6})
check("chatbot score: one score has no range", bot_score([0.7]),
      {"n": 1, "missing": 0, "mean": 0.7, "low": None, "high": None, "median": 0.7})
check("chatbot score: no scores at all", bot_score([None]),
      {"n": 0, "missing": 1, "mean": None, "low": None, "high": None, "median": None})
check("chatbot score: the range stays within 0 to 1", (bot_score([0.0, 0.0, 0.0, 0.9])["low"], bot_score([1.0, 1.0, 1.0, 0.1])["high"]),
      (0.0, 1.0))
convs_ = [{"verdict": "F", "score": 0.0}, {"verdict": "F", "score": 0.25}]
qs_ = [{"Correctness & behaviour": {"verdict": "P", "score": 1.0}}, {"Correctness & behaviour": {"verdict": "F", "score": 0.5}}]
check("chatbot score: a conversation counts as one test case, like a question",
      bot_score([composite(m)[0] for m in qs_] + [composite({"Conversation flow": c})[0] for c in convs_])["mean"],
      round((1.0 + 0.5 + 0.0 + 0.25) / 4, 3))
judge = FakeJudge(ClaimReport(claims=[claim("met")], fail_if_triggered=False, fail_if_detail="", no_usable_answer=False,
                              violated_guardrails=[], reason="r"))
CorrectnessBehaviour(judge).measure(case())
check("correctness: the prompt makes an omission named in 'Fail if' score 0", "This includes omissions" in judge.prompt, True)

# Source recall credit (QE decision 6 Nov 2026): facts right from other official pages it cited
from scoring import credit_recall
base = {"Source recall": {"verdict": "F", "score": 0.0, "reason": "0 of 2 expected indexed page(s) cited or retrieved"},
        "Citation support": P, "Source genuineness": P}
got = credit_recall({**base, "Correctness & behaviour": {"verdict": "P"}})
check("recall credit: facts right, supported by official cited pages -> 1.0", (got or {}).get("score"), 1.0)
check("recall credit: keeps the page count", ((got or {}).get("raw_score"), "0 of 2" in (got or {}).get("reason", "")), (0.0, True))
check("recall credit: pass/fail grade, second pass found the facts right",
      (credit_recall({**base, "Correctness & behaviour": {"verdict": "F"}}, {"facts": "correct"}) or {}).get("score"), 1.0)
check("recall credit: not when a cited page does not support the facts",
      credit_recall({**base, "Correctness & behaviour": {"verdict": "P"}, "Citation support": F}), None)
check("recall credit: not when a fact is missing",
      credit_recall({**base, "Correctness & behaviour": {"verdict": "F"}}, {"facts": "incomplete"}), None)
claims = {"claims": [{"kind": "fact", "status": "met"}, {"kind": "behaviour", "status": "missing"}], "fail_if_triggered": False}
check("recall credit: claim grades with every fact met",
      (credit_recall({**base, "Correctness & behaviour": {"verdict": "F", "score": 0.5, "detail": claims}}) or {}).get("score"), 1.0)
check("recall credit: not when a 'Fail if' was triggered",
      credit_recall({**base, "Correctness & behaviour": {"verdict": "F", "score": 0.0, "detail": {**claims, "fail_if_triggered": True}}}), None)
check("recall credit: lifts the status of a facts-right answer", status({**base, "Correctness & behaviour": {"verdict": "P", "score": 1.0},
      "Source recall": credit_recall({**base, "Correctness & behaviour": {"verdict": "P"}})}), "PASS")
# Official = also a site in the index export, the APIs or the ground-truth evidence (QE decision 6 Nov 2026)
from pages import available_to_bot
check("official: a non-government site in the index export counts", available_to_bot("https://mylpg.in/x", frozenset(), frozenset({"mylpg.in"}))[0], True)
check("official: a site only in the ground-truth evidence is official but not available",
      available_to_bot("https://someboard.org.in/x", frozenset(), frozenset(), frozenset({"someboard.org.in"})),
      (False, "in the ground-truth evidence (counted as official), but not available to the bot (not in the crawled list, registry, index export or APIs)"))

print("SCORING TESTS", "PASSED" if all(OK) else "FAILED", f"({sum(OK)} of {len(OK)})")
sys.exit(0 if all(OK) else 1)
