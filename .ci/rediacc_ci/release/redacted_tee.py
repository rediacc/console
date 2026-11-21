"""Copy stdin to stdout and to the step summary, the summary copy with the company input replaced.

`::add-mask::` redacts the job LOG only; it never covers the file `$GITHUB_STEP_SUMMARY` names, which is public on a public repository. So the Enterprise release step pipes the runner's output through here (cd-enterprise-release.yml).

    <command> | PYTHONPATH=.ci python3 -m rediacc_ci.release.redacted_tee

Env: COMPANY (the dispatch input, may be empty) and GITHUB_STEP_SUMMARY (the summary file; when unset only stdout is written, which is the local run). Under bash's pipefail the producer's exit code survives this stage.
"""

from __future__ import annotations

import os
import pathlib
import sys

MASK = "***"


def redact(text: str, company: str) -> str:
    """`text` with every occurrence of the non-empty `company` replaced."""
    return text.replace(company, MASK) if company else text


def main() -> int:
    company = os.environ.get("COMPANY", "")
    summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    for line in sys.stdin:
        sys.stdout.write(line)
        sys.stdout.flush()
        if summary:
            with pathlib.Path(summary).open("a", encoding="utf-8") as out:
                out.write(redact(line, company))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
