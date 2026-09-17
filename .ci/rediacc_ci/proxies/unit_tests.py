"""Port of `.ci/scripts/test/proxies/proxy-unit-tests.sh`.

Local proxy for a workspace unit-test suite that CI runs and the local gate set
does not, wired as TWO registered gates over one script:
`check:test-provisioning` (`package.json:393`, `@rediacc/provisioning test`) and
`check:test-e2e-unit` (`package.json:394`, `@rediacc/e2e-tests test:unit`).

    python3 -m rediacc_ci.proxies.unit_tests <workspace> <npm script key>

WHY A WRAPPER AND NOT A BARE `npm run test -w <ws>`, preserved from the twin
because all three reasons are real failure shapes:

 1. THE 77 CONTRACT. A bare npm key cannot distinguish "the suite failed" from
    "vitest is not installed on this host". Both exit 1.
 2. `npm run <name>` FOR A SCRIPT THAT DOES NOT EXIST EXITS 1 WITH ZERO BYTES
    ON BOTH STREAMS under --silent, indistinguishable from a suite failing for
    a real reason. So the key's existence is checked FIRST, and its absence is
    a loud failure naming the workspace, never a 77.
 3. ANTI-VACUITY. `vitest run` over a glob that matches no file exits 0. The
    "Tests N passed" summary is read back and a run that executed zero tests is
    REFUSED.

-----------------------------------------------------------------------------
FIXED 2026-09-10: THE SUMMARY READER WAS COLOUR-BLIND AND TOOK THE WRONG TOKEN
-----------------------------------------------------------------------------
The twin's old `:122-133` (and this port's old `SUMMARY_RE`) had two bugs,
both measured against a real vitest on a scratch workspace:

1. COLOUR-BLIND. vitest's ANSI SGR escapes sit BETWEEN "Tests" and the number
   in any CI-shaped run (`CI=true GITHUB_ACTIONS=true`, no real TTY needed --
   only this sandbox's own `CLAUDECODE=1` env var happens to suppress it,
   which is why the bug was invisible here). The old regex matched the raw
   bytes, so it simply failed to match and the gate reported "no summary" on
   an otherwise-passing suite in `check:test-provisioning` and
   `check:test-e2e-unit`.
2. WRONG TOKEN. Even uncoloured, the old regex took the FIRST number on a
   mixed line (`Tests  1 failed | 10 passed (11)`), which is the FAILED
   count, not the total -- so a run of 11 reported as 1. On an ALL-failing
   suite this coincidentally matched the true count and only leaked one
   misleading PASS line inside an already-red run.

The fix strips ANSI SGR sequences first (`_ANSI_RE`), then reads the trailing
"(N)" total off the "Tests" line -- correct in the clean, coloured and mixed
cases alike, and does not depend on which side of "|" wins. Pinned by
`test_proxies_unit_tests.py::test_a_partly_failing_suite_reports_the_failed_
count_on_both_sides` and `test_the_summary_regex_cannot_see_a_coloured_
vitest_line`.

-----------------------------------------------------------------------------
THE WORKSPACE RESOLVER IS PYTHON, AND THE `npm query` IT AVOIDS STAYS AVOIDED
-----------------------------------------------------------------------------
`:65-74` resolves the workspace directory by globbing the root package.json's
own `workspaces` entries and reading each candidate's `name`, deliberately not
with `npm query` (same answer, 31 ms against 1,056 ms, and no dependency on
npm query's output schema). `resolve_workspace` does the same walk in Python;
the FIRST match wins and the search stops, as `process.exit(0)` does there.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-unit-tests.observations.jsonl`.
"""

from __future__ import annotations

import glob
import json
import pathlib
import re
import subprocess
import sys

from rediacc_ci.core import proxyx

# `grep -oE 'Tests +[0-9]+ (passed|failed)'` (:124).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
SUMMARY_RE = re.compile(r"^[ \t]*Tests[ \t].*\(([0-9]+)\)", re.MULTILINE)
# `grep -oE 'Test Files +[0-9]+ '` then `grep -oE '[0-9]+'` (:126). The trailing space is part of the pattern, so a count at end-of-line does not match.
FILES_RE = re.compile(r"Test Files +([0-9]+) ")


def _proxy_root() -> pathlib.Path:
    """`ROOT_DIR="$PROXY_DIR/../../../.."` (:31-32)."""
    return pathlib.Path(__file__).resolve().parents[3]


def resolve_workspace(root: pathlib.Path, name: str) -> str:
    """`:65-74`. The relative directory whose package.json `name` matches, or "".

    Relative, because `fs.globSync` is run with cwd at the repo root and returns
    relative paths -- which is why `${WS_DIR#"$ROOT_DIR"/}` at `:88` is a no-op
    in practice and is reproduced as one here.
    """
    try:
        workspaces = json.loads((root / "package.json").read_text(encoding="utf-8")).get(
            "workspaces", []
        )
    except (OSError, ValueError):
        return ""
    for pattern in workspaces:
        for d in glob.glob(pattern, root_dir=str(root)):
            pj = root / d / "package.json"
            if not pj.exists():
                continue
            try:
                if json.loads(pj.read_text(encoding="utf-8")).get("name") == name:
                    return d
            except ValueError:
                continue
    return ""


def has_script(root: pathlib.Path, ws_dir: str, key: str) -> bool:
    """`:93-97`, the node probe reading `scripts[key]` out of the package.json."""
    try:
        pkg = json.loads((root / ws_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    scripts = pkg.get("scripts")
    return bool(isinstance(scripts, dict) and scripts.get(key))


def summary_count(both: str) -> str:
    """FIXED 2026-09-10, mirroring `:122-133` of the twin. Strip vitest's ANSI
    SGR escapes first (they sit BETWEEN "Tests" and the number in any
    CI-shaped run, which made the old regex simply not match), then read the
    trailing "(N)" total off the "Tests" line -- correct whether the run is
    clean ("Tests  N passed (N)") or mixed ("Tests  F failed | P passed (N)"),
    since it no longer depends on which token comes first.
    """
    found = SUMMARY_RE.findall(_ANSI_RE.sub("", both))
    return found[-1] if found else ""


def files_count(both: str) -> str:
    """`grep -oE 'Test Files +[0-9]+ ' | grep -oE '[0-9]+' | tail -1` (:126,134
    of the twin). Also ANSI-stripped first, for the same reason as above.
    """
    found = FILES_RE.findall(_ANSI_RE.sub("", both))
    return found[-1] if found else ""


def run(workspace: str, script_key: str) -> int:
    root = _proxy_root()

    p = proxyx.Proxy(f"unit-tests/{workspace}#{script_key}", f"npm run {script_key} -w {workspace}")

    p.need_cmd("node", "./run.sh setup")
    p.need_cmd("npm", "./run.sh setup")
    p.need_file(str(root / "node_modules"), "npm install && npm run install:natives")
    p.need_file(
        str(root / "node_modules" / ".bin" / "vitest"), "npm install && npm run install:natives"
    )
    p.preflight()

    ws_dir = resolve_workspace(root, workspace)

    # THIS IS THE VACUITY REFUSAL for the workspace glob above, and it is worded to say so. check:ci-enumeration-vacuity could not SEE this guard until the word VACUOUS was in it: its detector keys on VACUOUS, a MIN_ name or the word floor, and a correct refusal in different words reads to it as no refusal at all. (:76-87)
    if not ws_dir or not (root / ws_dir / "package.json").is_file():
        p.bad(
            f"VACUOUS: workspace '{workspace}' resolves to no package.json in any "
            "workspace glob; npm run would exit 1 with no output at all"
        )
        return p.finish()
    p.ok(f"workspace {workspace} resolves to {ws_dir}")

    if has_script(root, ws_dir, script_key):
        p.ok(f"script key '{script_key}' exists in {workspace}")
    else:
        p.bad(
            f"script key '{script_key}' is NOT in {ws_dir}/package.json. "
            f"'npm run {script_key}' would exit 1 with zero bytes on both streams, which "
            "reads exactly like a failing suite. Fix the key, do not chase the empty failure."
        )
        return p.finish()

    sys.stdout.flush()
    proc = subprocess.run(
        ["npm", "run", script_key, "-w", workspace],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    rc = proc.returncode
    both = (proc.stdout + proc.stderr).rstrip("\n")

    if rc == 0:
        p.ok(f"npm run {script_key} -w {workspace} exited 0")
    else:
        p.bad(f"npm run {script_key} -w {workspace} exited {rc}")
        print("  --- stdout ---", file=sys.stderr)
        sys.stderr.write(proc.stdout)
        print("  --- stderr ---", file=sys.stderr)
        sys.stderr.write(proc.stderr)

    count = summary_count(both)
    files = files_count(both)
    if count == "":
        p.bad(
            "no 'Tests N passed' summary in either stream; the runner produced no readable "
            "count, so this run proves nothing"
        )
    elif int(count) == 0:
        p.bad(
            "the runner executed 0 tests; an empty include pattern exits 0 and is the "
            "vacuity this check exists for"
        )
    else:
        p.ok(f"{count} test(s) across {files or '?'} file(s) in {workspace}")

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    workspace = argv[0] if len(argv) > 0 else ""
    script_key = argv[1] if len(argv) > 1 else ""
    if not workspace or not script_key:
        print("usage: proxy-unit-tests.sh <workspace> <npm script key>", file=sys.stderr)
        return 2
    return run(workspace, script_key)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
