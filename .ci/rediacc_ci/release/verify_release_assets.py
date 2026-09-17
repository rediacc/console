"""Port of `.ci/scripts/release/verify-release-assets.sh`.

Asserts a GitHub Release exists for `VERSION` and carries at least one
`rdc-*` CLI asset -- the cheapest proof the build that made the release
actually ran, before the R2 `.released` sentinel gets written for it.

`gh release view ... --json tagName,assets` IS SHELLED OUT TO, not
reimplemented against the REST API directly: the twin's exact invocation
(including which JSON fields it asks for) is what the differential proves
parity against, and a from-scratch REST call would be a second, independent
opinion about the same endpoint. `jq` IS ALSO SHELLED OUT TO, with the exact
same filter expressions the twin uses (`[.assets[] | select(...)] | length`
and `.assets | map(.name)`), rather than reimplemented in Python: the second
filter's failure debug line is pretty-printed multi-line JSON, and matching
that byte-for-byte is simpler by running the same `jq` than by re-deriving
its formatting rules.

REWORDED, NOT BYTE-IDENTICAL, on the missing-env-var paths only. The
`gh release view` failure and asset-count paths reproduce the twin's `echo`
lines byte-for-byte, since those are hand-chosen strings, not a bash
diagnostic wrapper.
"""

from __future__ import annotations

import os
import subprocess
import sys

SELF = "verify-release-assets.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv
    version = _require("VERSION")
    github_repository = _require("GITHUB_REPOSITORY")

    view = subprocess.run(
        ["gh", "release", "view", version, "--repo", github_repository, "--json", "tagName,assets"],
        capture_output=True,
        text=True,
        check=False,
    )
    if view.returncode != 0:
        print(f"::error::no GitHub Release found for {version}")
        # `cat /tmp/release.err` in the twin, unredirected: goes to STDOUT.
        sys.stdout.write(view.stderr)
        return 1

    release_json = view.stdout
    count_out = subprocess.run(
        ["jq", '[.assets[] | select(.name | startswith("rdc-"))] | length'],
        input=release_json,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    asset_count = int(count_out)
    if asset_count < 1:
        print(f"::error::Release {version} has no rdc-* CLI assets")
        print("::error::refusing to seal a version that was never built/published")
        names_out = subprocess.run(
            ["jq", ".assets | map(.name)"],
            input=release_json,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        print(names_out, end="")
        return 1

    print(f"✓ Release {version} has {asset_count} rdc-* CLI asset(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
