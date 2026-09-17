"""Port of `.ci/scripts/release/check-stable-manifest.sh`.

Reads the live stable CLI manifest and decides whether it already matches `EDGE_VERSION`. A missing stable manifest is not an error (the very first promotion has nothing to compare against), so `STABLE_VERSION` stays empty
and `same=false`.

SHELLS OUT TO THE REAL `curl`, same reasoning as the `check_edge_manifest` sibling: the twin's URL is a hardcoded literal with no override hook, so parity is proved by putting a fake `curl` first on PATH for both sides, never the real `releases.rediacc.com`.

REWORDED, NOT BYTE-IDENTICAL, on the missing-env-var paths only; see the
`check_edge_manifest` sibling's module docstring for why.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SELF = "check-stable-manifest.py"
MANIFEST_URL = "https://releases.rediacc.com/cli/stable/manifest.json"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    output_path = _require("GITHUB_OUTPUT")
    edge_version = _require("EDGE_VERSION")

    proc = subprocess.run(
        ["curl", "-sf", MANIFEST_URL],
        capture_output=True,
        text=True,
        check=False,
    )
    manifest_text = proc.stdout if proc.returncode == 0 else ""

    stable_version = ""
    if manifest_text.strip():
        try:
            data = json.loads(manifest_text)
        except json.JSONDecodeError:
            return 1  # silent abort, same reasoning as check_edge_manifest.py
        value = data.get("version")
        stable_version = "null" if value is None else value

    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"version={stable_version}\n")
        if stable_version == edge_version:
            print(f"Edge and stable are the same version ({stable_version}), skipping")
            fh.write("same=true\n")
        else:
            fh.write("same=false\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
