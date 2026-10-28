"""Settings from environment variables, optionally loaded from eval/.env (KEY=VALUE lines)."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

_env = HERE / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.split(" #", 1)[0].strip().strip("\"'")  # drop inline comments
            if _v:  # an empty AWS key would break the AWS credential chain
                os.environ.setdefault(_k.strip(), _v)

# Keep test data on this machine: no DeepEval telemetry or cloud upload.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")

# The checked expected answers (golden_check.py apply); golden_test_cases_phase1.xlsx is the version before the check
WORKBOOK = Path(os.environ.get("GOLDEN_WORKBOOK", ROOT / "golden_test_cases_final_20261028.xlsx"))
INGESTED_CSV = Path(os.environ.get(
    "INGESTED_CSV", ROOT / "ingested-websites.csv"))  # the bot's crawled-site list (team export of 14-Oct-2026)

BOT_ADAPTER = os.environ.get("BOT_ADAPTER", "saathi")  # "saathi" (UMANG citizenbot API) or "curl"
BOT_CURL_FILE = Path(os.environ.get("BOT_CURL_FILE", HERE / "bot_curl.txt"))
BOT_ANSWER_PATH = os.environ.get("BOT_ANSWER_PATH", "")    # e.g. "data.answer"; empty = auto-detect
BOT_SOURCES_PATH = os.environ.get("BOT_SOURCES_PATH", "")  # e.g. "data.sources"; empty = auto-detect
BOT_TIMEOUT = float(os.environ.get("BOT_TIMEOUT", "60"))
BOT_INSECURE_TLS = os.environ.get("BOT_INSECURE_TLS", "") == "1"  # only for staging hosts with self-signed certs

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "global.anthropic.claude-opus-5-5")  # Bedrock inference profile
JUDGE_EFFORT = os.environ.get("JUDGE_EFFORT", "high")
JUDGE_FALLBACK_MODEL = os.environ.get("JUDGE_FALLBACK_MODEL", "global.anthropic.claude-opus-5")  # empty = no fallback
_pin, _pout = os.environ.get("JUDGE_PRICE_IN"), os.environ.get("JUDGE_PRICE_OUT")  # USD per million tokens
JUDGE_PRICE_IN = float(_pin) if _pin else None
JUDGE_PRICE_OUT = float(_pout) if _pout else None
PAGE_CHAR_LIMIT = int(os.environ.get("PAGE_CHAR_LIMIT", "150000"))  # per cited page sent to the judge

PAGE_CACHE_HOURS = float(os.environ.get("PAGE_CACHE_HOURS", "12"))

RUNS_DIR = HERE / "runs"
CACHE_DIR = HERE / "page_cache"
