"""Ported from `.ci/scripts/release/check-soak-period.sh`, which W7 P5 batch B5 retired once `.ci/shadow/w7p5a-check-soak-period.observations.jsonl` asserted equivalence over five distinct trees.

Selects the edge release to promote to stable and says whether it can be promoted. Emits `ready=true|false`, `path=force|nightly|soak` (which rule decided), `version=` / `date=` (the selected release, empty when none), `blocked=r2-channel-snapshot` when the selection cannot be promoted, and human-readable lines to stdout.

THE WALK BACK (PLAN-plan-per-pr-loop R2). With a release on every merge the newest edge is almost always younger than `SOAK_DAYS`, so judging only the newest one starved stable from 2026-09-15 on. The candidates are the newest edge (`EDGE_VERSION`, dated by the manifest's `EDGE_DATE`) and every older release in `EDGE_RELEASES` (`list_edge_releases`' JSON) that is still newer than `STABLE_VERSION`; the selection is the NEWEST candidate that has soaked. `FORCE=true` selects the newest edge. With `PROMOTE_TRIGGER=workflow_run` the soak is waived for the newest candidate whose tagged commit `nightly_tested_edge` proves is contained in `NIGHTLY_HEAD_SHA`; every other outcome falls back to the soak rule.

A NIGHTLY THAT CONCLUDED `failure` (`NIGHTLY_CONCLUSION`) reaches the waiver only when `nightly_tested_edge.nightly_failures_are_drift_only` accepts its jobs (read for `NIGHTLY_RUN_ID` in `GITHUB_REPOSITORY`); otherwise it decides `ready=false` with no soak fallback, exactly as the workflow's `if:` refused every red nightly before. Any other non-success conclusion is refused the same way.

An older selection is NOT promotable today, and says so (`blocked=`): R2's `<dir>/edge/` channel trees carry the newest edge's signed metadata only, and the bucket holds no per-version snapshot of it. See the R2 note in `main`.

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

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from rediacc_ci.core import ghx
from rediacc_ci.release import nightly_tested_edge
from rediacc_ci.release.list_edge_releases import semver
from rediacc_ci.release.nightly_tested_edge import edge_tested_by_nightly

SELF = "check-soak-period.py"

# The `blocked=` value written when the selected version is older than the edge R2 carries; see the R2 note in `main`.
R2_SNAPSHOT_BLOCK = "r2-channel-snapshot"

# The exact twin expression, run verbatim so both sides parse EDGE_DATE through the identical `date` invocation chain. `$1` is the edge date, substituted positionally rather than interpolated into the script text so a value containing shell metacharacters cannot change what runs.
_DATE_EXPR = 'date -d "$1" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$1" +%s 2>/dev/null'


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def _epoch(value: str) -> int | None:
    """`value` as epoch seconds through the twin's own `date` chain, or None when neither `date` form parses it."""
    proc = subprocess.run(
        ["bash", "-c", _DATE_EXPR, "_", value], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return None
    return int(proc.stdout.strip())


def _candidates(text: str) -> list[tuple[str, str]]:
    """`EDGE_RELEASES` (`list_edge_releases`' JSON) as `(version, date)` pairs. Raises ValueError or TypeError on anything else."""
    if not text.strip():
        return []
    rows = json.loads(text)
    if not isinstance(rows, list):
        raise TypeError("expected a JSON list")
    pairs: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("version") or not row.get("date"):
            raise TypeError("expected {version, date} per release, got %r" % (row,))
        pairs.append((str(row["version"]), str(row["date"])))
    return pairs


@dataclass(frozen=True)
class Edge:
    version: str
    date: str
    age_days: int


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
    edge_version = os.environ.get("EDGE_VERSION", "")
    if not edge_version:
        print(f"{SELF}: EDGE_VERSION must be set", file=sys.stderr)
        return 1
    force = os.environ.get("FORCE", "")
    stable_version = os.environ.get("STABLE_VERSION", "")
    releases_text = os.environ.get("EDGE_RELEASES", "")

    edge_epoch = _epoch(edge_date)
    now_proc = subprocess.run(["date", "+%s"], capture_output=True, text=True, check=False)
    if edge_epoch is None or now_proc.returncode != 0:
        # The twin's `set -e` aborted here with no message; this one names the value -- see the module docstring.
        print(
            f"{SELF}: EDGE_DATE could not be parsed as a date (got {edge_date!r})", file=sys.stderr
        )
        return 1
    now_epoch = int(now_proc.stdout.strip())

    try:
        listed = _candidates(releases_text)
    except (ValueError, TypeError) as exc:
        print(f"{SELF}: EDGE_RELEASES is not a release list ({exc})", file=sys.stderr)
        return 1

    newest_key = semver(edge_version)
    stable_key = semver(stable_version)
    newest = Edge(edge_version, edge_date, int((now_epoch - edge_epoch) / 86400))
    # The walk's candidates, newest first: the newest edge (R2's manifest, its own date), then every older listed release that is still newer than stable. A listed release above the newest edge is not an edge release yet.
    older: list[Edge] = []
    for version, date in listed:
        key = semver(version)
        if key is None or newest_key is None or key >= newest_key:
            continue
        if stable_key is not None and key <= stable_key:
            continue
        epoch = _epoch(date)
        if epoch is None:
            print(
                f"{SELF}: EDGE_RELEASES date for v{version} could not be parsed (got {date!r})",
                file=sys.stderr,
            )
            return 1
        older.append(Edge(version, date, int((now_epoch - epoch) / 86400)))
    older.sort(key=lambda e: semver(e.version) or (0, 0, 0), reverse=True)
    newest_in_bounds = stable_key is None or newest_key is None or newest_key > stable_key
    walk = ([newest] if newest_in_bounds else []) + older

    print(f"Edge release age: {newest.age_days} days (soak: {soak_days} days)")

    selected: Edge | None = None
    path = "soak"
    if force == "true":
        print("Force promotion requested, skipping soak check")
        selected, path = newest, "force"
    else:
        # The nightly waiver (operator ruling 2026-09-30): a green scheduled Console CI run releases edge to stable without the soak, but only for an edge whose tagged commit that run's head provably contains -- the newest such edge. Anything short of proof falls through to the soak rule below.
        nightly = os.environ.get("PROMOTE_TRIGGER", "") == "workflow_run"
        if nightly:
            tested, reason = _nightly_tested()
            print(f"Nightly verdict: {reason}")
            if not tested:
                print("Decided by: the nightly did not pass its tests, not promoting")
                _write(output_path, None, "nightly", blocked=False)
                return 0
            head_sha = os.environ.get("NIGHTLY_HEAD_SHA", "")
            for edge in walk:
                proven, reason = edge_tested_by_nightly(edge.version, head_sha)
                print(f"Nightly check: {reason}")
                if proven:
                    print("Decided by: green nightly contains the edge commit, skipping soak check")
                    selected, path = edge, "nightly"
                    break
        if selected is None:
            if newest.age_days >= soak_days and newest_in_bounds:
                print("Soak period complete")
                selected = newest
            else:
                if newest.age_days < soak_days:
                    print(f"Edge needs {soak_days - newest.age_days} more day(s) of soak")
                for edge in older:
                    print(f"Older edge v{edge.version}: {edge.age_days} days")
                    if edge.age_days >= soak_days:
                        print(
                            f"Soak period complete for v{edge.version}, the newest edge release that has soaked"
                        )
                        selected = edge
                        break
                if selected is None and stable_key is not None:
                    print(
                        f"No edge release newer than stable v{stable_version} has soaked {soak_days} days"
                    )

    # R2 CARRIES ONLY THE NEWEST EDGE. `promote_r2_to_stable` copies each `<dir>/edge/` tree, whose signed channel metadata (apt Release/InRelease, rpm repomd.xml, APKINDEX, the pacman db, cli/edge/manifest.json) describes `EDGE_VERSION` alone; no per-version snapshot of that metadata exists in the bucket (listed 2026-10-02: `cli/v<ver>/` keeps binaries only). Promoting an older selection from edge/ would ship the newest edge's packages under the older version's name while Docker and the Workers got the older one, a split release, so the older selection is named and not promoted.
    blocked = selected is not None and selected.version != edge_version
    if blocked and selected is not None:
        print(
            f"Not promoting v{selected.version}: R2's <dir>/edge/ channel trees carry only v{edge_version}, "
            f"and no per-version channel snapshot of v{selected.version} exists"
        )

    _write(output_path, selected, path, blocked=blocked)
    return 0


def _write(output_path: str, selected: Edge | None, path: str, *, blocked: bool) -> None:
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write("ready=%s\n" % ("true" if selected is not None and not blocked else "false"))
        fh.write(f"path={path}\n")
        fh.write("version=%s\n" % (selected.version if selected is not None else ""))
        fh.write("date=%s\n" % (selected.date if selected is not None else ""))
        if blocked:
            fh.write(f"blocked={R2_SNAPSHOT_BLOCK}\n")


def _nightly_tested() -> tuple[bool, str]:
    """Whether the triggering nightly counts as having passed its tests. `success` (or no conclusion given) does; `failure` does only when its failures are all drift gates; anything else, or a job list that cannot be read, does not."""
    conclusion = os.environ.get("NIGHTLY_CONCLUSION", "")
    if conclusion in ("", "success"):
        return True, "the nightly concluded %s" % (
            conclusion or "without a conclusion given, read as success"
        )
    if conclusion != "failure":
        return False, f"the nightly concluded {conclusion}, which is not a pass"
    run_id = os.environ.get("NIGHTLY_RUN_ID", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not run_id.isdigit() or not repo:
        return (
            False,
            f"the nightly failed and its jobs cannot be read (run id {run_id!r}, repository {repo!r})",
        )
    try:
        jobs = nightly_tested_edge.fetch_run_jobs(repo, run_id)
    except ghx.GhError as exc:
        return False, f"the nightly failed and its jobs could not be read: {exc}"
    return nightly_tested_edge.nightly_failures_are_drift_only(jobs)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
