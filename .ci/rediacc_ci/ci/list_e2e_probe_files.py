#!/usr/bin/env python3
"""List the E2E Workers units the committed shard manifest ships today, one probe leg each.

Replaces `.ci/scripts/test/list-e2e-probe-files.sh` (deleted; ruling 7, 2026-09-06, refuses new bash under `.ci`). Called from `.github/workflows/ct-e2e-probe.yml`'s `list-files` job to build the probe matrix.

`.ci/config/shards/test-e2e-workers.json` (T2.10's committed shard manifest) is the source of truth: the probe asks "does the unit THIS SHARD PLAN ships today need a `needs` edge", never a fresh enumeration that could silently disagree with what actually ships. A unit the manifest does not run yet has no "passes in the full suite" baseline to probe against.

ONE ENTRY PER MANIFEST UNIT, not per file (2026-10-14). The describe-group buckets `13-postgres-fork-isolation.test.ts#part1/2/3` are three units the shard plan already places on three different legs, so each must pass without its siblings, and that is what the probe now asks of it. The whole-file shape this replaced ran that file as one leg: 15.7 minutes on run 36311800722, over the 12-minute leg budget and past the 15-minute timeout the job carries today, so an always-on probe in that shape would time out on every run. A bucket is selected exactly as E2E Workers selects it, through `rediacc_ci.testrun.e2e.SHARD_GREP_BUCKETS`; a bucket that table does not know is refused rather than run whole.

Each entry is an object for the matrix: `unit` (the manifest id without its `e2e-workers:` prefix, which `e2e-probe-edges.ts` turns back into a unit id), `test` (the spec file), `grep` (the bucket's pattern, or empty for a whole-file unit) and `slug` (`unit` with `#` spelled `-`, for artifact names).

Prints one line, `units=<JSON array>`, appended to `$GITHUB_OUTPUT` when set, or to stdout otherwise -- so it runs the same way locally:

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.list_e2e_probe_files
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

from rediacc_ci import paths
from rediacc_ci.testrun.e2e import SHARD_GREP_BUCKETS

MANIFEST_REL = pathlib.Path(".ci/config/shards/test-e2e-workers.json")
UNIT_PREFIX = "e2e-workers:"


class VacuousError(Exception):
    """The manifest named zero e2e-workers units -- a corpus this small must refuse rather than probe nothing."""


class UnknownBucketError(ValueError):
    """A `#<bucket>` suffix `SHARD_GREP_BUCKETS` has no pattern for: running the whole file instead would probe a different unit than the one shipped."""


def probe_units(manifest_path: pathlib.Path) -> list[dict[str, str]]:
    """One matrix entry per manifest id, sorted and deduplicated by unit."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    units: dict[str, dict[str, str]] = {}
    for leg in data["legs"]:
        for entry_id in leg["ids"]:
            unit = entry_id.removeprefix(UNIT_PREFIX)
            test, separator, bucket = unit.partition("#")
            grep = ""
            if separator:
                # The separator, not the bucket, decides: `a.test.ts#` names an empty bucket, which is refused like any other unknown one (review 729e29cc.1).
                grep = SHARD_GREP_BUCKETS.get(bucket, "")
                if not grep:
                    raise UnknownBucketError(
                        "%s: bucket '%s' of %s has no entry in rediacc_ci.testrun.e2e.SHARD_GREP_BUCKETS"
                        % (manifest_path, bucket, test)
                    )
            units[unit] = {
                "unit": unit,
                "test": test,
                "grep": grep,
                "slug": unit.replace("#", "-"),
            }
    if not units:
        raise VacuousError("VACUOUS: %s named zero e2e-workers units" % manifest_path)
    return [units[u] for u in sorted(units)]


def main(argv: list[str]) -> int:
    del argv
    manifest_path = paths.repo_root() / MANIFEST_REL
    try:
        units = probe_units(manifest_path)
    except (OSError, ValueError, KeyError, VacuousError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # Compact separators keep the output one short line; `fromJson` in the workflow parses either form identically.
    line = "units=%s" % json.dumps(units, separators=(",", ":"))

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        print(line)
    print("list-e2e-probe-files: %d unit(s) from %s" % (len(units), MANIFEST_REL), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
