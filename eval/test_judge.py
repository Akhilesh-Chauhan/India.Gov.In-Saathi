"""Tiny Bedrock connectivity / model-access test for the judge (one short graded call per model). Never prints keys.

Run: ../.venv/bin/python test_judge.py [model_id ...]   (default: Opus 5.5, Sonnet 5.5, Haiku 5.5)
"""
import sys
import time

import config
from judge import BedrockClaudeJudge, price_for
from metrics import PassFail

PROMPT = """You check FRESHNESS of a chatbot answer against a golden answer.
GOLDEN: Rs 2,610 per quintal for Rabi Marketing Season 2027-28 (CCEA, 30 Sep 2026). Fail if Rs 2,585 is given as current.
BOT ANSWER: The MSP of wheat for RMS 2027-28 is Rs 2,585 per quintal [1].
Verdict PASS, FAIL or NA with a one-sentence reason. violated_guardrails: IDs such as G04 if broken, else empty list."""

models = sys.argv[1:] or [config.JUDGE_MODEL]
print(f"Region: {config.AWS_REGION} | effort: {config.JUDGE_EFFORT}")
for m in models:
    judge = BedrockClaudeJudge(m)
    t0 = time.monotonic()
    try:
        v = judge.generate(PROMPT, schema=PassFail)
        u = judge.usage[-1]
        pin, pout = price_for(m)
        cost = (u["input_tokens"] / 1e6 * pin + u["output_tokens"] / 1e6 * pout) if pin is not None else None
        print(f"OK   {m}: verdict={v.verdict} guardrails={v.violated_guardrails} | {time.monotonic() - t0:.1f}s | "
              f"in={u['input_tokens']} out={u['output_tokens']} | served by {u['model']} | "
              f"~USD {cost:.5f} per call at list price" + "" if cost is not None else "")
        print(f"     reason: {v.reason}")
    except Exception as e:
        print(f"FAIL {m}: {type(e).__name__}: {str(e)[:300]}")
