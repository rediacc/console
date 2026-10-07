#!/usr/bin/env python3
"""Entry point for check:ci-gh-retry-reads; the logic lives in `rediacc_ci.quality.gh_retry_reads` (Python) and `rediacc_ci.quality.gh_retry_shell` (shell).

Every non-test GitHub READ made through `gh` under `.ci/rediacc_ci` and `.ci/scripts` must go through `rediacc_ci.core.gh_retry` (or a `ghx` helper with `attempts>=2`, or a spawn inside `retry_transient`), so a one-shot read that fails CI or releases the wrong build on a single 5xx cannot come back (agent/plans/PLAN-gh-retry.md box G9). The SHELL half holds the same line for `curl` calls to the GitHub API and `gh` calls in live shell scripts and workflow `run:` blocks: `curl --retry N`, or common.sh's `gh_retry`/`gh_json`.

BOTH HALVES ALWAYS RUN, and the exit code is the worse of the two (2 an instrument failed, then 1 a finding, then 0), so a red Python half never hides a shell finding or the other way round. `--write-baseline` and `--init-baseline` belong to the Python half's baseline file and run it alone. `--root` points the PYTHON half at a scratch tree (its gate tests copy only the Python roots there); `--shell-root` points the shell half at one, and without it the shell half scans the repository, because a Python-only copy has no shell tree and the shell half would rightly call it VACUOUS.

---- gate ----
step: GitHub reads retry transient faults
needs: none
lane: quality-static
selftest: true
why: one HTTP 502 failed CI Complete on PR #597 (run 37507913738), and an audit found
     20 modules reading GitHub through a one-shot `gh` spawn, three of which released
     the wrong build, bump or label set on a single 5xx instead of failing
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import gh_retry_reads, gh_retry_shell

_PYTHON_ONLY = ("--write-baseline", "--init-baseline")


def _split(argv: list[str]) -> tuple[list[str], str | None]:
    """(argv for the Python half, the --shell-root value or None)."""
    rest: list[str] = []
    shell_root: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--shell-root":
            if i + 1 >= len(argv):
                raise SystemExit("check_gh_retry_reads.py: --shell-root needs a directory")
            shell_root = argv[i + 1]
            i += 2
            continue
        if a.startswith("--shell-root="):
            shell_root = a.split("=", 1)[1]
        else:
            rest.append(a)
        i += 1
    return rest, shell_root


def main(argv: list[str]) -> int:
    rest, shell_root = _split(argv)
    rc_py = gh_retry_reads.main(rest)
    if any(a in _PYTHON_ONLY for a in rest):
        return rc_py
    shell_argv = [a for a in rest if a in ("--selftest", "--quiet-writes")]
    if shell_root is not None:
        shell_argv += ["--root", shell_root]
    rc_sh = gh_retry_shell.main(shell_argv)
    rc = 2 if 2 in (rc_py, rc_sh) else max(rc_py, rc_sh)
    verdict = "✓" if rc == 0 else "✗"
    print(
        "%s gh retry reads: python half rc=%d, shell half rc=%d" % (verdict, rc_py, rc_sh),
        file=sys.stdout if rc == 0 else sys.stderr,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
