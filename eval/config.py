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

# The golden set in use: the index-grounded v2 workbook (347 questions + 13 conversations; owner sign-off 5 Nov 2026).
# Earlier sets: golden_test_cases_final_20261028.xlsx (checked October set), golden_test_cases_phase1.xlsx.
WORKBOOK = Path(os.environ.get("GOLDEN_WORKBOOK", ROOT / "golden_test_cases_indexed_v2_20261105.xlsx"))
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
# What the bot actually reads (fix of 5 Nov 2026): the developers' export of its index and snapshots of the two UMANG APIs.
# Content checks (figures, citation support) use these texts for a cited URL when they hold it; the live page otherwise.
INDEX_EXPORT_DIR = Path(os.environ.get("INDEX_EXPORT_DIR", ROOT / "citizen-guide-indexed-data"))
API_SNAPSHOT_DIR = Path(os.environ.get("API_SNAPSHOT_DIR", "")) if os.environ.get("API_SNAPSHOT_DIR") else (
    sorted((ROOT / "artifacts" / "data" / "api_snapshots").glob("*/snapshot.json")) or [Path("")])[-1].parent
CONTENT_FROM_INDEX = os.environ.get("CONTENT_FROM_INDEX", "1") != "0"  # 0 = old behaviour (live pages only)
