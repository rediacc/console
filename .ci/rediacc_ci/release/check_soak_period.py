"""Ported from `.ci/scripts/release/check-soak-period.sh`, which W7 P5 batch B5 retired once `.ci/shadow/w7p5a-check-soak-period.observations.jsonl` asserted equivalence over five distinct trees.

Decides whether an edge release has soaked long enough to promote to stable,
from the manifest's own `releaseDate` and the workflow's `SOAK_DAYS`. Emits
`ready=true|false`, `path=force|nightly|soak` (which rule decided) and a human-readable line to stdout.
With `PROMOTE_TRIGGER=workflow_run` the soak is waived only when `nightly_tested_edge` proves `EDGE_VERSION`'s tagged commit is contained in `NIGHTLY_HEAD_SHA`; every other outcome falls back to the soak rule.

DATE PARSING IS SHELLED OUT, NOT REIMPLEMENTED. The twin tries GNU `date -d` first, then BSD `date -j -f "%Y-%m-%dT%H:%M:%S"`, so it accepts a wider set of `EDGE_DATE` spellings than a hand-rolled `datetime.fromisoformat` would (GNU `date -d` parses far more than ISO-8601). Re-deriving that parser would be a second implementation of a contract the system `date` binary already owns,
and would drift from it silently on some future EDGE_DATE this port never saw during review. Running the *exact* twin expression through `bash -c` keeps the two sides looking at the same parse, byte for byte.

THE SILENT ABORT IS NOT REPRODUCED: IT NOW NAMES ITSELF (Rule T delta). In bash,
`EDGE_EPOCH=$(cmd1 || cmd2)` is a simple command consisting only of a variable
assignment, so its exit status is the exit status of the last command substitution performed -- and `set -e` therefore aborted the *whole twin* right there if both date attempts failed, before any output was produced. Measured against the twin while it existed, with `EDGE_DATE=not-a-date SOAK_DAYS=7`: exit 1, nothing on stdout, nothing on stderr, `$GITHUB_OUTPUT` untouched, so a promote job went red with no reason in its log. The port keeps the
exit code and the untouched stdout and `$GITHUB_OUTPUT`, and says on stderr which variable it could not read and what the value was. A non-numeric `SOAK_DAYS` is refused the same way, before anything is decided, instead of surfacing as a Python traceback. Pinned by `test_delta_an_unparseable_date_is_named` and `test_delta_a_non_numeric_soak_days_is_named_not_a_traceback`.

INTEGER ARITHMETIC MATCHES BASH'S TRUNCATION, NOT PYTHON'S FLOOR. Bash `$(())` trutruncates toward zero; Python's `//` floors toward negative infinity. The two differ only when `EDGE_DATE` is in the future (a negative age), which the scripts do not defend against either way, so this port uses `int(delta / 86400)` -- `int()` on a float also truncates toward zero -- to keep that
(mis)behaviour identical rather than accidentally fixing it here.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci.release.nightly_tested_edge import edge_tested_by_nightly

SELF = "check-soak-period.py"

# The exact twin expression, run verbatim so both sides parse EDGE_DATE through the identical `date` invocation chain. `$1` is the edge date, substituted positionally rather than interpolated into the script text so a value containing shell metacharacters cannot change what runs.
_DATE_EXPR = 'date -d "$1" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$1" +%s 2>/dev/null'


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    output_path = _require("GITHUB_OUTPUT")
    edge_date = _require("EDGE_DATE")
    soak_days_word = _require("SOAK_DAYS")
    try:
        soak_days = int(soak_days_word)
    except ValueError:
        print(
            f"{SELF}: SOAK_DAYS must be a whole number of days (got {soak_days_word!r})",
            file=sys.stderr,
        )
        return 1
    force = os.environ.get("FORCE", "")

    edge_epoch_proc = subprocess.run(
        ["bash", "-c", _DATE_EXPR, "_", edge_date],
        capture_output=True,
        text=True,
        check=False,
    )
    now_epoch_proc = subprocess.run(["date", "+%s"], capture_output=True, text=True, check=False)
    if edge_epoch_proc.returncode != 0 or now_epoch_proc.returncode != 0:
        # The twin's `set -e` aborted here with no message; this one names the value -- see the module docstring.
        print(
            f"{SELF}: EDGE_DATE could not be parsed as a date (got {edge_date!r})", file=sys.stderr
        )
        return 1

    edge_epoch = int(edge_epoch_proc.stdout.strip())
    now_epoch = int(now_epoch_proc.stdout.strip())
    age_days = int((now_epoch - edge_epoch) / 86400)

    print(f"Edge release age: {age_days} days (soak: {soak_days} days)")

    # The nightly waiver (operator ruling 2026-09-30): a green scheduled Console CI run releases edge to stable without the soak, but only when that run's head provably contains the edge version's tagged commit. Anything short of proof falls through to the soak rule below.
    nightly_proven = False
    if force != "true" and os.environ.get("PROMOTE_TRIGGER", "") == "workflow_run":
        nightly_proven, reason = edge_tested_by_nightly(
            os.environ.get("EDGE_VERSION", ""), os.environ.get("NIGHTLY_HEAD_SHA", "")
        )
        print(f"Nightly check: {reason}")

    with open(output_path, "a", encoding="utf-8") as fh:
        if force == "true":
            print("Force promotion requested, skipping soak check")
            fh.write("ready=true\n")
            fh.write("path=force\n")
        elif nightly_proven:
            print("Decided by: green nightly contains the edge commit, skipping soak check")
            fh.write("ready=true\n")
            fh.write("path=nightly\n")
        elif age_days < soak_days:
            print(f"Edge needs {soak_days - age_days} more day(s) of soak")
            fh.write("ready=false\n")
            fh.write("path=soak\n")
        else:
            print("Soak period complete")
            fh.write("ready=true\n")
            fh.write("path=soak\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
