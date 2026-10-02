"""The published edge releases, newest first, for `check_soak_period`'s walk back (PLAN-plan-per-pr-loop R2).

With a release on every merge (operator ruling 2026-10-02) the newest edge is almost always younger than `SOAK_DAYS`, so judging only the newest one starves stable forever. `check_soak_period` therefore walks back from the newest edge to the newest one that HAS soaked, and it needs every candidate's version and release date to do that. This module supplies them.

The oracle is the GitHub Releases list: `gh release list --exclude-drafts --exclude-pre-releases --json tagName,publishedAt`. A draft or pre-release was never an edge release, so neither is a candidate. A tag that is not `v<major>.<minor>.<patch>` is dropped, not guessed at. The result is written as one compact JSON line, `releases=[{"version": "1.3.12", "date": "2026-09-07T02:54:33Z"}, ...]`, newest version first, to `$GITHUB_OUTPUT`.

"COULD NOT TELL" IS A FAILURE. A `gh` failure or unparseable output exits 1 with the reason on stderr and writes nothing, so the promote job goes red with a named cause instead of judging an empty list as "nothing has soaked".
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

SELF = "list-edge-releases.py"
RELEASE_TAG_RE = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")
# The walk back never needs more than the releases since the last stable one; 100 is a generous ceiling on that.
LIST_LIMIT = "100"


def semver(version: str) -> tuple[int, int, int] | None:
    """`1.3.12` or `v1.3.12` as a sortable triple; None for anything that is not a plain release version."""
    match = RELEASE_TAG_RE.match(version if version.startswith("v") else "v" + version)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def parse_releases(text: str) -> list[dict[str, str]]:
    """`gh release list --json tagName,publishedAt` output as `[{version, date}]`, newest version first. Raises ValueError or TypeError on output that is not that shape."""
    rows = json.loads(text)
    if not isinstance(rows, list):
        raise TypeError("expected a JSON list, got %s" % type(rows).__name__)
    found: list[tuple[tuple[int, int, int], dict[str, str]]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("expected a JSON object per release, got %r" % (row,))
        tag = str(row.get("tagName") or "")
        date = str(row.get("publishedAt") or "")
        key = semver(tag)
        if key is None or not date:
            continue
        found.append((key, {"version": tag[1:], "date": date}))
    found.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in found]


def main(argv: list[str]) -> int:
    del argv
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print(f"{SELF}: GITHUB_OUTPUT must be set", file=sys.stderr)
        return 1
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    args = ["gh", "release", "list", "--exclude-drafts", "--exclude-pre-releases"]
    args += ["--limit", LIST_LIMIT, "--json", "tagName,publishedAt"]
    if repo:
        args += ["--repo", repo]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        print(f"{SELF}: could not run gh: {exc.strerror}", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        print(
            f"{SELF}: gh release list failed (exit {proc.returncode}): {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return 1
    try:
        releases = parse_releases(proc.stdout)
    except (ValueError, TypeError) as exc:
        print(f"{SELF}: gh release list returned unreadable output: {exc}", file=sys.stderr)
        return 1
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write("releases=%s\n" % json.dumps(releases, separators=(",", ":")))
    print(
        "Edge releases listed: %d (%s)"
        % (len(releases), ", ".join("v" + r["version"] for r in releases[:5]) or "none")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
