"""The edge versions that have a complete channel snapshot in R2, for `check_soak_period` (PLAN-plan-per-pr-loop R2 follow-up).

`check_soak_period` may select an edge release OLDER than the newest one, and such a release can be promoted only from its own channel snapshot (`rediacc_ci.deploy.channel_snapshot`: `snapshots/v<ver>/`, complete when its `.complete` marker exists). This module lists the bucket's `snapshots/` prefix once and writes the versions whose marker exists as one compact JSON line, `snapshots=["1.4.2","1.4.1"]`, newest first, to `$GITHUB_OUTPUT`.

"COULD NOT TELL" IS A FAILURE. A failed listing exits 1 with aws's stderr and the reason, and writes nothing, so the promote job goes red with a named cause instead of reading "no snapshots" and blocking a release that has one. An EMPTY listing is a real answer (`snapshots=[]`): every release cut before snapshots existed has none.

The credentials are aws's own variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), which aws reads itself; this module reads only the endpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from rediacc_ci.deploy import channel_snapshot, r2_promote
from rediacc_ci.release.list_edge_releases import semver

SELF = "list-channel-snapshots.py"


def versions(listing_json: str) -> list[str]:
    """The versions whose `snapshots/v<ver>/.complete` is in a `list-objects-v2` JSON reply of `snapshots/`, newest first. A key that is not `v<semver>/.complete` is ignored."""
    root = channel_snapshot.SNAPSHOT_ROOT + "/"
    found = []
    for obj in r2_promote.parse_listing(listing_json, root):
        head, _, rest = obj.rel.partition("/")
        if rest != channel_snapshot.MARKER or not head.startswith("v"):
            continue
        key = semver(head[1:])
        if key is not None:
            found.append((key, head[1:]))
    return [version for _, version in sorted(found, reverse=True)]


def main(argv: list[str]) -> int:
    del argv
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
    for name, value in (("GITHUB_OUTPUT", output_path), ("CLOUDFLARE_R2_ENDPOINT", endpoint)):
        if not value:
            print(f"{SELF}: {name} must be set", file=sys.stderr)
            return 1
    args = r2_promote.list_argv(channel_snapshot.SNAPSHOT_ROOT + "/", endpoint)
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        print(f"{SELF}: could not run aws: {exc.strerror}", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        print(
            f"{SELF}: listing {channel_snapshot.SNAPSHOT_ROOT}/ failed (exit {proc.returncode}); "
            "that is not evidence that no snapshot exists",
            file=sys.stderr,
        )
        return 1
    try:
        found = versions(proc.stdout)
    except (ValueError, KeyError, TypeError) as exc:
        print(
            f"{SELF}: the listing of {channel_snapshot.SNAPSHOT_ROOT}/ is unreadable: {exc}",
            file=sys.stderr,
        )
        return 1
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write("snapshots=%s\n" % json.dumps(found, separators=(",", ":")))
    print(
        "Channel snapshots listed: %d (%s)"
        % (len(found), ", ".join("v" + v for v in found[:5]) or "none")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
