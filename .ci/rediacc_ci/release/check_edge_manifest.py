"""Port of `.ci/scripts/release/check-edge-manifest.sh`.

Reads the live edge CLI manifest and emits `version` / `date` / `skip` step
outputs. A missing manifest is not an error (a brand-new bucket has nothing to
promote yet), so it emits `skip=true` and exits 0.

SHELLS OUT TO THE REAL `curl` AND `jq`, same reasoning as
`rediacc_ci.release.check_soak_period`'s date-parsing subprocess: the twin's
URL (`https://releases.rediacc.com/cli/edge/manifest.json`) is a HARDCODED
literal with no override hook, so there is no way to point either side at a
fixture except by putting a fake `curl` in front of both of them on PATH.
Reimplementing the HTTP call with `urllib` (as `wait_for_preview_worker.py`
does) would not help here -- there is nothing to inject a fixture URL through,
so the twin and a from-scratch client could each drift from `curl`'s own
exit/retry/redirect semantics unnoticed. Shelling out to the identical `curl
-sf <url>` command keeps both sides looking at the same client, and the
differential test proves parity by putting a fake `curl` first on PATH for
BOTH the bash run and this port's run -- never the real
`releases.rediacc.com`.

REWORDED, NOT BYTE-IDENTICAL, on the missing-GITHUB_OUTPUT path only: the
twin's `${VAR:?msg}` diagnostic carries a bash line number that is not worth
reproducing (same reasoning as every other port's module docstring). The
manifest-found and manifest-missing paths are byte-identical, because those
are this port's own literal strings, matching the twin's.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SELF = "check-edge-manifest.py"
MANIFEST_URL = "https://releases.rediacc.com/cli/edge/manifest.json"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    output_path = _require("GITHUB_OUTPUT")

    proc = subprocess.run(
        ["curl", "-sf", MANIFEST_URL],
        capture_output=True,
        text=True,
        check=False,
    )
    manifest_text = proc.stdout if proc.returncode == 0 else ""

    with open(output_path, "a", encoding="utf-8") as fh:
        if not manifest_text.strip():
            print("No edge manifest found, skipping")
            fh.write("skip=true\n")
            return 0

        try:
            data = json.loads(manifest_text)
        except json.JSONDecodeError:
            # `jq -r '.version'` on non-JSON input exits 5; under `set -euo
            # pipefail` that aborts the twin silently, before any output. Same silence here, same reasoning as check_soak_period.py's own silent-abort note.
            return 1
        # jq -r prints the literal string "null" for an absent/null field, never Python's "None".
        version = data.get("version")
        version_out = "null" if version is None else version
        date = data.get("releaseDate")
        date_out = "null" if date is None else date
        fh.write(f"version={version_out}\n")
        fh.write(f"date={date_out}\n")
        fh.write("skip=false\n")

    print(f"Edge version: {version_out} (released: {date_out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
