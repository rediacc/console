"""Port of `.ci/scripts/release/assert-artifact-version.sh`.

Asserts that the CI run CD is about to promote actually BUILT the version CD is
about to publish. `cd-v2.yml:216` runs it in the init job, before any registry
mutation, and the twin's header records what it is for: a stale `ci_run_id`
whose artifacts were built against a previous tag would be retagged with the
new version label, and only Docker's runtime `--version` check would notice,
hours later. It happened -- "the second published 1.2.16 binaries as 1.2.17".

IT DOES NOT COMPUTE THE VERSION, AND THAT IS THE FIRST THING TO KNOW ABOUT IT.
The twin does NO "latest tag + bump" arithmetic of its own: `VERSION` arrives
already computed, from `resolve-version.sh --bump-type` by way of the init
job's outputs, and this script's whole contribution is the COMPARISON. So the
version-arithmetic edge cases live upstream; the edge cases that live HERE are
in the extraction and the comparison, and they are these four:

  1. `jq -r '.version // empty'` -- an absent, null or false `.version` yields
     the empty string, which is the refusal below. `false` is worth naming
     because `//` is jq's alternative operator, not a null-coalesce.
  2. jq's own EXIT CODE becomes the script's. `ARTIFACT_VERSION="$(jq ...)"`
     under `set -e` propagates it: measured against this tree's jq 1.8.1 on
     2026-09-10, malformed JSON and a top-level array BOTH exit 5 ("parse
     error: Invalid numeric literal", "Cannot index array with string"). The
     code is not 1, it is not fixed across jq releases either, and neither path
     prints a `::error::` line -- a CD log for those cases shows jq's message
     and nothing else. Reproduced exactly, by SHELLING OUT to the
     same jq rather than reimplementing the filter in Python -- the twin's own
     `require_cmd jq` already makes jq a hard dependency of this step, and a
     `json.loads` port would have to invent its own exit codes for both cases
     and would then disagree with the live script on the two paths hardest to
     test.
  3. NORMALISATION IS ONE-SIDED. `${ARTIFACT_VERSION#v}` strips a leading `v`
     from the ARTIFACT's version only. `VERSION` is compared raw, so
     `VERSION=v1.2.3` against an artifact carrying `1.2.3` is a MISMATCH. The
     twin's own comment says the promotion target has "no leading v"; the
     asymmetry is a contract, not an oversight, and the differential pins it.
  4. THE COMPARISON IS STRING EQUALITY, never semver equality. `1.02.3` and
     `1.2.3` are different versions here, and `01.2.3` is not `1.2.3`. Leading
     zeros therefore fail loudly rather than being normalised away, which is
     the right direction for a check whose whole job is to catch two versions
     that were supposed to be the same string. The same applies to a version
     written as a JSON NUMBER: `{"version": 1.20}` reaches the comparison as
     the literal text `1.20` (jq 1.8 preserves the source spelling of a number
     literal), so it does NOT equal `1.2` -- driven, both sides, 2026-09-10.

ABSENCE IS A HARD FAILURE, DELIBERATELY, and the twin's HARDENED 2026-08-07
note is the reason. This check spent its whole life taking the artifact
not-found branch -- nothing produced an artifact named `cli-manifest` -- and
warning-and-exiting-0, so it verified nothing for months while looking green.
`cd-stage.yml` now uploads it (`cd-stage.yml:288` names the artifact for this
script), so absence means something is genuinely wrong.

THE DOWNLOAD DIRECTORY IS A FIXED PATH AND IS NEVER CLEARED, which is the
twin's behaviour and is carried across unchanged: `mkdir -p
/tmp/cd-artifact-check` and nothing else. A second invocation in the same
job with an artifact that has no `manifest.json` would read the FIRST
invocation's leftover file and compare against a stale version. Not reachable
from `cd-v2.yml`, which runs this once per job on a fresh runner, and reported
rather than silently corrected here, because correcting it in the port alone
would make the port and the twin disagree on the one path a differential
cannot then prove.

NOT A REGISTERED GATE: `grep -n assert-artifact-version package.json` matches
nothing. It is a workflow `run:` step (`cd-v2.yml:216`), so there is no
`check:ci-*` id to cite and no manifest entry to keep in step.

REWORDED, NOT BYTE-IDENTICAL, on the three missing-variable paths only: the
twin's `${VAR:?msg}` diagnostic carries a bash line number, same reasoning as
every other port in this package. Every `::error::` and `::notice::` line is
byte-identical, because those are the lines a CD log actually shows.

K=5 LEDGER: `.ci/shadow/w7p6-assert-artifact-version.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "assert-artifact-version.py"

# `.ci/scripts/release/assert-artifact-version.sh:48`, verbatim. A constant
# rather than a parameter because the twin has no override hook either, and
# inventing one here would be a behaviour the bash side cannot match.
CHECK_DIR = "/tmp/cd-artifact-check"
ARTIFACT_NAME = "cli-manifest"


def _require_cmd(name: str) -> int | None:
    """`require_cmd` (common.sh:141-147): log and exit 1, message byte-identical."""
    try:
        common.require_cmd(name)
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1
    return None


def _require_var(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print("%s: %s must be set" % (SELF, name), file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv

    for cmd in ("gh", "jq"):
        rc = _require_cmd(cmd)
        if rc is not None:
            return rc

    version = _require_var("VERSION")
    ci_run_id = _require_var("CI_RUN_ID")
    repository = _require_var("GITHUB_REPOSITORY")

    check_dir = pathlib.Path(CHECK_DIR)
    check_dir.mkdir(parents=True, exist_ok=True)

    # `2>/dev/null` on gh ONLY. gh's stdout is left alone, exactly as the twin
    # leaves it, so a chatty download still reaches the CD log.
    download = subprocess.run(
        [
            "gh",
            "run",
            "download",
            ci_run_id,
            "--repo",
            repository,
            "--name",
            ARTIFACT_NAME,
            "--dir",
            CHECK_DIR,
        ],
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if download.returncode != 0:
        print(
            "::error::cli-manifest artifact not found on CI run %s, so the artifact "
            "version CANNOT be compared." % ci_run_id
        )
        print(
            "::error::Refusing to publish on an unverified version. cd-stage.yml uploads "
            "this artifact on every push run, so its absence means the CI run is older "
            "than that change, was not a push run, or its artifacts expired (retention "
            "is 1 day)."
        )
        print(
            "::error::Dispatch again with no ci_run_id to auto-derive the latest green "
            "CI on main, or re-run CI on current main."
        )
        return 1

    manifest = check_dir / "manifest.json"
    if not manifest.is_file():
        print(
            "::error::cli-manifest artifact present but manifest.json missing; "
            "refusing to publish unverified."
        )
        return 1

    # THE SAME jq, NOT A REIMPLEMENTATION. See the module docstring, point 2:
    # jq's exit code IS the twin's exit code on malformed input, and its stderr
    # is the only message those paths ever print.
    extract = subprocess.run(
        ["jq", "-r", ".version // empty", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if extract.returncode != 0:
        sys.stderr.write(extract.stderr)
        return extract.returncode

    # `$(...)` strips ALL trailing newlines from the substitution.
    artifact_version = extract.stdout.rstrip("\n")
    if not artifact_version:
        print("::error::manifest.json has no .version field; refusing to publish unverified.")
        return 1

    # `${ARTIFACT_VERSION#v}`: ONE leading `v`, and only from the artifact side.
    artifact_version = artifact_version.removeprefix("v")

    if artifact_version != version:
        print(
            "::error::Artifact-version mismatch: CI run %s produced v%s, but CD is "
            "promoting as v%s." % (ci_run_id, artifact_version, version)
        )
        print(
            "::error::This means ci_run_id is stale -- the artifacts were built before "
            "the latest tag bump."
        )
        print(
            "::error::Either dispatch again with no ci_run_id (auto-derive latest green "
            "CI on main), or re-run CI on current main to produce fresh artifacts."
        )
        return 1

    print(
        "::notice::Artifact version v%s matches promotion target v%s." % (artifact_version, version)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
