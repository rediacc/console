#!/usr/bin/env python3
"""Write one leg's `{file, outcome}` result for `ct-e2e-probe.yml`'s `probe-file` job.

Replaces `.ci/scripts/test/record-e2e-probe-outcome.sh` (deleted; ruling 7, 2026-09-06, refuses new bash under `.ci`). Called with `if: always()` after the leg's own E2E run, so it fires whether that run passed or failed. The second argument is the job's own conclusion so far (`${{ job.status }}`), read rather than the step's `continue-on-error` outcome -- that flag is banned by check:ci-workflows, and `job.status` already reflects a failed prior step without it.

Usage: `record-e2e-probe-outcome.py <file> <job-status>`

Writes `$RUNNER_TEMP/e2e-probe/result.json` (default `/tmp` when `RUNNER_TEMP` is unset, matching the twin's `${RUNNER_TEMP:-/tmp}`), one line, `{"file":"<file>","outcome":"pass"|"fail"}`. The line is built the same way the twin's `printf` built it -- neither escapes the file argument -- because every real caller passes a bare spec path (`tests/13-postgres-fork-isolation.test.ts`) with no character that would need it.
"""

from __future__ import annotations

import os
import pathlib
import sys

USAGE = "usage: record-e2e-probe-outcome.py <file> <job-status>"


def outcome_for(job_status: str) -> str:
    """`pass` only on the exact string `success`; every other status, including `failure` and `cancelled`, is `fail`."""
    return "pass" if job_status == "success" else "fail"


def result_dir(env: dict[str, str] | None = None) -> pathlib.Path:
    """`${RUNNER_TEMP:-/tmp}/e2e-probe`, exported so a test can drive the fallback without touching the real `/tmp`."""
    e = os.environ if env is None else env
    return pathlib.Path(e.get("RUNNER_TEMP") or "/tmp") / "e2e-probe"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 1
    file_, job_status = argv[0], argv[1]

    out_dir = result_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    content = '{"file":"%s","outcome":"%s"}\n' % (file_, outcome_for(job_status))
    (out_dir / "result.json").write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
