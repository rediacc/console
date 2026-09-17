"""Port of `.ci/scripts/release/check-soak-period.sh`.

Decides whether an edge release has soaked long enough to promote to stable,
from the manifest's own `releaseDate` and the workflow's `SOAK_DAYS`. Emits
`ready=true|false` and a human-readable line to stdout.

DATE PARSING IS SHELLED OUT, NOT REIMPLEMENTED. The twin tries GNU `date -d` first, then BSD `date -j -f "%Y-%m-%dT%H:%M:%S"`, so it accepts a wider set of `EDGE_DATE` spellings than a hand-rolled `datetime.fromisoformat` would (GNU `date -d` parses far more than ISO-8601). Re-deriving that parser would be a second implementation of a contract the system `date` binary already owns,
and would drift from it silently on some future EDGE_DATE this port never saw during review. Running the *exact* twin expression through `bash -c` keeps the two sides looking at the same parse, byte for byte.

THE SILENT-ABORT BEHAVIOUR IS REPRODUCED ON PURPOSE. In bash,
`EDGE_EPOCH=$(cmd1 || cmd2)` is a simple command consisting only of a variable
assignment, so its exit status is the exit status of the last command substitution performed -- and `set -e` therefore aborts the *whole script* right there if both date attempts fail, before any output is produced.
Measured directly: `EDGE_DATE=not-a-date SOAK_DAYS=7 bash check-soak-period.sh`
exits 1 with nothing on stdout, nothing on stderr, and `$GITHUB_OUTPUT` untouched. This port raises `SystemExit(1)` at the same point with the same silence, rather than "fixing" it with an error message the twin never printed.

INTEGER ARITHMETIC MATCHES BASH'S TRUNCATION, NOT PYTHON'S FLOOR. Bash `$(())` trutruncates toward zero; Python's `//` floors toward negative infinity. The two differ only when `EDGE_DATE` is in the future (a negative age), which the scripts do not defend against either way, so this port uses `int(delta / 86400)` -- `int()` on a float also truncates toward zero -- to keep that
(mis)behaviour identical rather than accidentally fixing it here.
"""

from __future__ import annotations

import os
import subprocess
import sys

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
    soak_days = _require("SOAK_DAYS")
    force = os.environ.get("FORCE", "")

    edge_epoch_proc = subprocess.run(
        ["bash", "-c", _DATE_EXPR, "_", edge_date],
        capture_output=True,
        text=True,
        check=False,
    )
    now_epoch_proc = subprocess.run(["date", "+%s"], capture_output=True, text=True, check=False)
    if edge_epoch_proc.returncode != 0 or now_epoch_proc.returncode != 0:
        # Silent, matching the twin's `set -e` abort on both date attempts failing -- see the module docstring.
        raise SystemExit(1)

    edge_epoch = int(edge_epoch_proc.stdout.strip())
    now_epoch = int(now_epoch_proc.stdout.strip())
    age_days = int((now_epoch - edge_epoch) / 86400)

    print(f"Edge release age: {age_days} days (soak: {soak_days} days)")

    with open(output_path, "a", encoding="utf-8") as fh:
        if force == "true":
            print("Force promotion requested, skipping soak check")
            fh.write("ready=true\n")
        elif age_days < int(soak_days):
            print(f"Edge needs {int(soak_days) - age_days} more day(s) of soak")
            fh.write("ready=false\n")
        else:
            print("Soak period complete")
            fh.write("ready=true\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
