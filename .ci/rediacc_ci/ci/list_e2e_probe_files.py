#!/usr/bin/env python3
"""List the E2E Workers spec files the committed shard manifest ships today.

Replaces `.ci/scripts/test/list-e2e-probe-files.sh` (deleted; ruling 7, 2026-09-06, refuses new bash under `.ci`). Called from `.github/workflows/ct-e2e-probe.yml`'s `list-files` job to build the probe matrix.

`.ci/config/shards/test-e2e-workers.json` (T2.10's committed shard manifest) is the source of truth: the probe asks "does the file THIS SHARD PLAN ships today need a `needs` edge", never a fresh enumeration that could silently disagree with what actually ships. A file the manifest does not run yet has no "passes in the full suite" baseline to probe against.

One entry per FILE, not per manifest id: the describe-group buckets `13-postgres-fork-isolation.test.ts#part1/2/3` split one file into three shard units, and the probe runs that file whole, so an id's `#part` suffix is stripped before the set is built.

Prints one line, `files=<JSON array>`, appended to `$GITHUB_OUTPUT` when set, or to stdout otherwise -- so it runs the same way locally:

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.list_e2e_probe_files
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from rediacc_ci import paths

MANIFEST_REL = pathlib.Path(".ci/config/shards/test-e2e-workers.json")


class Vacuous(Exception):  # noqa: N818
    """The manifest named zero e2e-workers files -- a corpus this small must refuse rather than probe nothing."""


def probe_files(manifest_path: pathlib.Path) -> list[str]:
    """One file per manifest id, `#part` suffixes stripped, sorted and deduplicated."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files: set[str] = set()
    for leg in data["legs"]:
        for entry_id in leg["ids"]:
            rest = entry_id.removeprefix("e2e-workers:")
            files.add(rest.split("#", 1)[0])
    if not files:
        raise Vacuous("VACUOUS: %s named zero e2e-workers files" % manifest_path)
    return sorted(files)


def main(argv: list[str]) -> int:
    del argv
    manifest_path = paths.repo_root() / MANIFEST_REL
    try:
        files = probe_files(manifest_path)
    except (OSError, ValueError, KeyError, Vacuous) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # Compact separators, matching the twin's `JSON.stringify` (no inline whitespace); `fromJson` in the workflow parses either form identically.
    line = "files=%s" % json.dumps(files, separators=(",", ":"))

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
