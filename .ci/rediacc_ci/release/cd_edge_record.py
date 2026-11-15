"""Write the edge release record of a CD edge release (cd-release-edge.yml, job `edge-record`).

    PYTHONPATH=.ci python3 -m rediacc_ci.release.cd_edge_record --version V --sha SHA --run-id ID --needs NEEDS.json --jobs JOBS.jsonl

WHY. `release-records/v<V>/edge.json` is the record `local_gates` (the stable soak) and `rings_run` (bench and the fast tier of a ring release) read. A full `release:local` writes it (`local.internal_release_record`); before this module CD's edge path wrote only the per-target deploy records, so a CD-shipped version could never satisfy the rings (`release-records/v3.0.1/edge.json` answered 404 on 2026-11-15).

ONE SCHEMA, ONE WRITER. The record is `local.record_document` with kind `release-cd`, and it is put through `deploy_record.write_record_once`, the conditional put a local release uses, under `local.edge_record_key`.

ONLY A WHOLE RELEASE IS RECORDED. NEEDS.json is the job's `toJSON(needs)`: every job in REQUIRED (the version, publish, both edge deploys, the smoke, the post-publish install validation and tag-and-release, the same sections a local record's `failed_step: null` covers) must have result `success`, and init's `workers_only` output must not be `true`. Anything else refuses with exit 1 and writes nothing. A workers-only deploy, CD or local, cuts no version: the version it redeploys was recorded by its own release, so neither path writes the record for it.

STEPS AND TIMING. JOBS.jsonl is this run's jobs across every attempt, one JSON object per line (`gh api 'repos/<repo>/actions/runs/<id>/jobs?filter=all' --paginate --jq '.jobs[]'`). Each REQUIRED job's display name (DISPLAY, pinned to the workflow by the test) selects its rows, a reusable workflow's jobs included (`<caller name> / <callee job>`); the latest attempt that holds a successful row is the one recorded, as one step with that attempt's earliest start and its wall seconds. A job with no successful row refuses, since the record would claim a step it cannot show.

IDEMPOTENT. Before the put, the key is read. Present with this version: exit 0, unchanged, so a rerun of the job or a retry dispatch is safe. Present with any other version, or unreadable: exit 1 and nothing is written. The put itself is conditional, so a record is never overwritten.

ENVIRONMENT. `CLOUDFLARE_R2_ENDPOINT`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` for the releases bucket.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Callable
from typing import Any

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_record, executor_artifacts
from rediacc_ci.release import local

SELF = "rediacc_ci.release.cd_edge_record"
KIND = "release-cd"

# Job id -> (its `name:` in cd-release-edge.yml, the local release section it stands for).
DISPLAY: dict[str, tuple[str, str]] = {
    "init": ("Initialize", "version"),
    "publish": ("Tag & Release", "publish"),
    "deploy-marketing-edge": ("Deploy edge Marketing", "deploy"),
    "deploy-account-edge": ("Deploy edge Account (all regions)", "deploy"),
    "smoke-test": ("Smoke Test", "smoke"),
    "validate-install-published": ("Validate Install (post-publish)", "smoke"),
    "tag-and-release": ("Tag & GitHub Release", "release"),
}
REQUIRED = tuple(DISPLAY)

Reader = Callable[[str], "dict[str, Any] | None"]
Writer = Callable[[dict[str, Any], str], None]


class RefusedError(Exception):
    """The record cannot be written truthfully; the message names why."""


def needs_refusals(needs: dict[str, Any]) -> list[str]:
    """One line per reason this run is not a whole edge release; empty when it is."""
    out: list[str] = []
    for job in REQUIRED:
        entry = needs.get(job)
        result = entry.get("result") if isinstance(entry, dict) else None
        if result != "success":
            out.append("job %s is %s, not success" % (job, result or "absent from needs"))
    init = needs.get("init")
    outputs = init.get("outputs") if isinstance(init, dict) else None
    if isinstance(outputs, dict) and outputs.get("workers_only") == "true":
        out.append("a workers-only deploy cuts no version; its version's own release records it")
    return out


def _at(raw: object) -> datetime.datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def _stamp(at: datetime.datetime) -> str:
    return at.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def step_rows(jobs: list[dict[str, Any]]) -> list[local.StepResult]:
    """One StepResult per REQUIRED job, from the latest attempt holding a successful row of it."""
    out: list[local.StepResult] = []
    for job in REQUIRED:
        name, section = DISPLAY[job]
        mine = [
            j
            for j in jobs
            if isinstance(j.get("name"), str)
            and (j["name"] == name or j["name"].startswith(name + " / "))
        ]
        won = [j for j in mine if j.get("conclusion") == "success"]
        if not won:
            raise RefusedError(
                "no successful row of job %s (%r) in the jobs list (%d row(s) carry that name)"
                % (job, name, len(mine))
            )
        attempt = max(int(j.get("run_attempt") or 1) for j in won)
        rows = [j for j in mine if int(j.get("run_attempt") or 1) == attempt]
        starts = [s for s in (_at(j.get("started_at")) for j in rows) if s is not None]
        ends = [e for e in (_at(j.get("completed_at")) for j in rows) if e is not None]
        if not starts or not ends:
            raise RefusedError(
                "job %s attempt %d has no started_at/completed_at to time it" % (job, attempt)
            )
        first, last = min(starts), max(ends)
        out.append(
            local.StepResult(
                id=job,
                section=section,
                rc=0,
                seconds=round((last - first).total_seconds(), 3),
                started_at=_stamp(first),
                attempts=attempt,
            )
        )
    return out


def build(
    *,
    version: str,
    sha: str,
    tree: str,
    run_id: str,
    regions: list[str],
    steps: list[local.StepResult],
) -> dict[str, Any]:
    """The CD edge release record: `local.record_document` with kind `release-cd`; the smoke-test job passed, so `smoke_rc` is 0."""
    return local.record_document(
        kind=KIND,
        version=version,
        sha=sha,
        tree=tree,
        run_id=run_id,
        regions=regions,
        smoke_rc=0,
        failed_step=None,
        steps=steps,
    )


def publish(record: dict[str, Any], key: str, *, read: Reader, write: Writer) -> str:
    """`written` after a first put, `unchanged` when this version's record is already there; RefusedError otherwise."""
    existing = read(key)
    if existing is not None:
        if existing.get("version") == record["version"]:
            return "unchanged"
        raise RefusedError(
            "%s already holds a record of version %r, not %s; nothing written"
            % (key, existing.get("version"), record["version"])
        )
    try:
        write(record, key)
    except deploy_record.RecordError as exc:
        raise RefusedError(str(exc)) from None
    return "written"


def live_read(key: str) -> dict[str, Any] | None:
    """The record at `key` in the releases bucket, None when absent; any other failure refuses."""
    with tempfile.TemporaryDirectory(prefix="cd-edge-record-") as tmp:
        dest = pathlib.Path(tmp) / "record.json"
        try:
            found = executor_artifacts.get_object(key, dest)
        except executor_artifacts.ArtifactError as exc:
            raise RefusedError("cannot read %s: %s" % (key, exc)) from None
        if not found:
            return None
        try:
            doc = json.loads(dest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RefusedError("%s exists but is not JSON: %s" % (key, exc)) from None
    if not isinstance(doc, dict):
        raise RefusedError("%s exists but is not a JSON object" % key)
    return doc


def git_tree(root: pathlib.Path, sha: str) -> str:
    """The tree of `sha`, refusing when the checkout's HEAD is not that commit."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    if head.returncode != 0 or head.stdout.strip() != sha:
        raise RefusedError(
            "the checkout's HEAD is %r, not the released sha %s"
            % (head.stdout.strip() or head.stderr.strip(), sha)
        )
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, capture_output=True, text=True, check=False
    )
    if tree.returncode != 0:
        raise RefusedError("git rev-parse HEAD^{tree} failed: %s" % tree.stderr.strip())
    return tree.stdout.strip()


def read_jobs(path: pathlib.Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RefusedError("cannot read the jobs list %s: %s" % (path, exc)) from None
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise RefusedError("%s line %d is not JSON: %s" % (path, n, exc)) from None
        if not isinstance(row, dict):
            raise RefusedError("%s line %d is not a JSON object" % (path, n))
        out.append(row)
    return out


def read_needs(path: pathlib.Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RefusedError("cannot read the needs %s: %s" % (path, exc)) from None
    if not isinstance(doc, dict):
        raise RefusedError("the needs %s is not a JSON object" % path)
    return doc


def main(
    argv: list[str] | None = None,
    *,
    root: pathlib.Path | None = None,
    read: Reader = live_read,
    write: Writer = deploy_record.write_record_once,
    tree_of: Callable[[pathlib.Path, str], str] = git_tree,
) -> int:
    parser = argparse.ArgumentParser(prog=SELF)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--needs", required=True, type=pathlib.Path)
    parser.add_argument("--jobs", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    base = root or paths.repo_root()
    try:
        executor_artifacts.check_version(args.version)
    except executor_artifacts.ArtifactError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 2
    key = local.edge_record_key(args.version)
    try:
        refusals = needs_refusals(read_needs(args.needs))
        if refusals:
            for why in refusals:
                print("%s: no edge record for v%s: %s" % (SELF, args.version, why), file=sys.stderr)
            return 1
        record = build(
            version=args.version,
            sha=args.sha,
            tree=tree_of(base, args.sha),
            run_id="gh-%s" % args.run_id,
            regions=list(local.read_regions(base)),
            steps=step_rows(read_jobs(args.jobs)),
        )
        outcome = publish(record, key, read=read, write=write)
    except RefusedError as exc:
        print("%s: no edge record for v%s: %s" % (SELF, args.version, exc), file=sys.stderr)
        return 1
    if outcome == "unchanged":
        print("%s: %s already records v%s; unchanged" % (SELF, key, args.version))
    else:
        print("%s: wrote %s" % (SELF, key))
    return 0


if __name__ == "__main__":
    sys.exit(main())
