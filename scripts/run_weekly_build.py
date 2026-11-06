#!/usr/bin/env python3
"""
Weekly build step for the scheduled Friday run.

    python3 scripts/run_weekly_build.py data/week-YYYY-MM-DD.json

1. Builds the Detail Pack (index.html) with scripts/build_report.py, unchanged.
   If this fails, the run stops with a non-zero exit, same as before.
2. Then builds the Organic Brief (organic-brief_YYYY-MM-DD.html) with
   scripts/build_brief.py. A Brief failure is logged and returns exit code 2,
   but never touches or rolls back the Detail Pack.

Every run appends to logs/weekly-run.log (commit it with the run).
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
LOG_PATH = REPO_ROOT / "logs" / "weekly-run.log"


def log(lines):
    LOG_PATH.parent.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG_PATH, "a") as f:
        for line in lines:
            f.write(f"{stamp} {line}\n")
            print(line)


def run(step, cmd):
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    out = [f"  {l}" for l in (proc.stdout + proc.stderr).strip().splitlines() if l.strip()]
    status = "OK" if proc.returncode == 0 else f"FAILED (exit {proc.returncode})"
    log([f"[{step}] {status}"] + out)
    return proc.returncode == 0


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(64)
    data_file = sys.argv[1]
    log([f"=== weekly build start: {data_file} ==="])
    if not run("detail-pack", [sys.executable, str(SCRIPTS / "build_report.py"), data_file]):
        log(["=== weekly build end: Detail Pack FAILED, Brief skipped ==="])
        sys.exit(1)
    ok = run("organic-brief", [sys.executable, str(SCRIPTS / "build_brief.py"), data_file])
    log([f"=== weekly build end: Detail Pack OK, Organic Brief {'OK' if ok else 'FAILED'} ==="])
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
