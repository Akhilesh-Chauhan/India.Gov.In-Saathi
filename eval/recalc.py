"""Recalculate the formulas of .xlsx workbooks with LibreOffice (headless) and check them for formula errors.

openpyxl writes formulas without their results, and report_html.py / findings_page.py read the results, so every
workbook is recalculated after it is written (build_reports.sh does this). Each file is recalculated as a copy in a
temporary folder (a LibreOffice lock file next to the original can hang it) with a throwaway LibreOffice profile
(never the user's own), then copied back. Needs LibreOffice: `soffice` on PATH.

  python recalc.py runs/day1/report.xlsx runs/day1/findings_by_test_case.xlsx [--timeout 300]

Prints one line per file (formulas, and any #DIV/0!, #NAME?, ... with their cells) and exits 1 if a file failed or
has formula errors.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
Sub RecalculateAndSave()
  ThisComponent.calculateAll()
  ThisComponent.store()
  ThisComponent.close(True)
End Sub
</script:module>
"""
MACRO_URL = "vnd.sun.star.script:Standard.Module1.RecalculateAndSave?language=Basic&location=application"
ERRORS = ("#VALUE!", "#DIV/0!", "#REF!", "#NAME?", "#NULL!", "#NUM!", "#N/A")


def _env():
    return {**os.environ, "SAL_USE_VCLPLUGIN": "svp"}  # headless: no display needed


def _profile(folder, timeout):
    """A LibreOffice profile in `folder` with the recalculate-and-save macro; returns its URL."""
    profile = Path(folder) / "profile"
    url = profile.as_uri()
    subprocess.run(["soffice", "--headless", "--terminate_after_init", f"-env:UserInstallation={url}"],
                   capture_output=True, timeout=timeout, env=_env())
    basic = profile / "user" / "basic" / "Standard"
    if not basic.is_dir():
        raise RuntimeError("LibreOffice did not create its profile")
    (basic / "Module1.xba").write_text(MACRO, encoding="utf-8")
    return url


def scan(path):
    """(number of formulas, {error: [cells]}) of a recalculated workbook."""
    formulas, values = load_workbook(path), load_workbook(path, data_only=True)
    count, errors = 0, {}
    for ws in formulas.worksheets:
        cached = values[ws.title]
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    count += 1
                    v = cached[cell.coordinate].value
                    if isinstance(v, str) and v in ERRORS:
                        errors.setdefault(v, []).append(f"{ws.title}!{cell.coordinate}")
    return count, errors


def recalc(path, timeout=300):
    """Recalculate one workbook in place; returns scan() of the result."""
    path = Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix="saathi-recalc-") as folder:
        url = _profile(folder, timeout)
        work = Path(folder) / path.name
        shutil.copy2(path, work)
        before = work.stat().st_mtime_ns
        done = subprocess.run(["soffice", "--headless", "--norestore", f"-env:UserInstallation={url}", MACRO_URL, str(work)],
                              capture_output=True, text=True, timeout=timeout, env=_env())
        if done.returncode != 0 or work.stat().st_mtime_ns == before:
            raise RuntimeError("LibreOffice did not recalculate the file (is another LibreOffice instance stuck?) "
                               + (done.stderr or "").strip()[:300])
        shutil.copy2(work, path)
    return scan(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--timeout", type=int, default=300, help="seconds LibreOffice may take per file")
    a = ap.parse_args()
    if not shutil.which("soffice"):
        sys.exit("recalc.py: LibreOffice is needed to recalculate the workbooks, but `soffice` is not on PATH")
    failed = False
    for f in a.files:
        try:
            count, errors = recalc(f, a.timeout)
        except Exception as e:  # report and go on with the other files
            print(f"FAILED  {f}: {e}")
            failed = True
            continue
        if errors:
            failed = True
            print(f"ERRORS  {f}: {count} formulas; " + "; ".join(f"{k} in {len(v)} cell(s): {', '.join(v[:10])}"
                                                               for k, v in errors.items()))
        else:
            print(f"OK      {f}: {count} formulas recalculated, no errors")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
