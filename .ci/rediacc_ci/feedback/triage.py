"""Feedback triage entry (PLAN-rdc-feedback D5, box T1: export, cursor, Stage 1 quarantine and the verdict writer).

    PYTHONPATH=.ci python3 -m rediacc_ci.feedback.triage run [--region eu|us|asia|bench] [--dry-run] [--status <list>] [--cursor <path>]

Without `--region` the three production regions run in turn; `bench` (the eu bench) runs only when named. Per region:

  1. Open the root session (`client.open_region`); a dry run does not elevate bench.
  2. Export the items reported since the region's cursor with a status in `--status` (default `new`).
  3. Stage 1 (`quarantine.screen`): an item that matches a rule gets a `quarantined` verdict whose triage note names the rule and the field; a clean `new` item moves to `screening`, the queue of Stage 2.
  4. Write the verdicts in batches and advance the region's cursor to the newest `lastSeenAt` exported. `--dry-run` prints the same lines and writes neither verdicts nor the cursor.

One line per item names the region, the short fingerprint and the decision; no report field is ever printed.

CREDENTIALS. The run re-executes itself under the Bitwarden profile its regions need (`root-login` for eu, us and asia; `bench-login-eu` for bench) through `rediacc_ci.core.bws_env exec`, unless that profile is already bound; production and bench in one process are refused, because each needs its own profile. Nothing secret reaches argv or output.

EXIT. 0 every region done; 1 a failed step in some region (the others still run); 2 a refusal before any request (usage, a missing credential, an unreadable cursor).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rediacc_ci import log, paths
from rediacc_ci.feedback import client, quarantine
from rediacc_ci.ops import bench_preflight, login_bench

SELF = "rediacc_ci.feedback.triage"
PROFILES_ENV = "REDIACC_BWS_PROFILES"
DEFAULT_STATUSES = ("new",)
SHORT_FP = 12

Runner = Callable[[Sequence[str], Mapping[str, str]], int]


@dataclass
class Options:
    regions: tuple[str, ...]
    dry_run: bool = False
    statuses: tuple[str, ...] = DEFAULT_STATUSES
    cursor: Path | None = None


@dataclass
class RegionResult:
    """What one region's run decided: the exported items, the Stage 1 hits by fingerprint, the verdicts and the clean items Stage 2 takes."""

    region: str
    items: list[dict[str, Any]] = field(default_factory=list)
    hits: dict[str, quarantine.Hit] = field(default_factory=dict)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    survivors: list[dict[str, Any]] = field(default_factory=list)
    written: client.VerdictResult | None = None


@dataclass
class Deps:
    """The seams `run` calls through; a test replaces them."""

    open_region: Callable[..., client.Transport] = client.open_region
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    out: Callable[[str], None] = print


def parse_args(argv: Sequence[str]) -> Options:
    parser = argparse.ArgumentParser(prog=SELF, description="feedback triage")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_p = sub.add_parser("run", help="export, screen and write verdicts")
    run_p.add_argument("--region", choices=client.REGIONS)
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--status", default=",".join(DEFAULT_STATUSES))
    run_p.add_argument("--cursor", type=Path)
    try:
        ns = parser.parse_args(list(argv))
    except SystemExit as exc:
        raise client.FeedbackError(parser.format_usage().strip(), rc=2) from exc
    statuses = tuple(s for s in ns.status.split(",") if s)
    unknown = [s for s in statuses if s not in client.STATUSES]
    if unknown or not statuses:
        raise client.FeedbackError(
            "--status takes a comma list of %s" % ", ".join(client.STATUSES), rc=2
        )
    regions = (ns.region,) if ns.region else client.PRODUCTION_REGIONS
    return Options(regions, ns.dry_run, statuses, ns.cursor)


def decide(region: str, items: Sequence[dict[str, Any]]) -> RegionResult:
    """Stage 1 over the exported items: a hit is quarantined (unless it already is), a clean `new` item moves to `screening`, and every clean item is a survivor for Stage 2."""
    result = RegionResult(region, list(items))
    for item in items:
        fp = item["fingerprint"]
        hit = quarantine.screen(item)
        if hit is not None:
            result.hits[fp] = hit
            if item["status"] != "quarantined":
                result.verdicts.append(
                    client.verdict(fp, status="quarantined", triageNote=hit.note)
                )
            continue
        result.survivors.append(item)
        if item["status"] == "new":
            result.verdicts.append(client.verdict(fp, status="screening"))
    return result


def _line(result: RegionResult, item: Mapping[str, Any]) -> str:
    fp = item["fingerprint"]
    hit = result.hits.get(fp)
    if hit is not None:
        return "%s %s quarantined rule=%s field=%s" % (
            result.region,
            fp[:SHORT_FP],
            hit.rule,
            hit.field,
        )
    return "%s %s screening" % (result.region, fp[:SHORT_FP])


def run_region(region: str, opts: Options, cursor: Path, deps: Deps) -> RegionResult:
    rows = client.read_cursor(cursor)
    since = client.cursor_since(rows, region)
    transport = deps.open_region(region, not opts.dry_run)
    items = client.export(transport, since, opts.statuses)
    result = decide(region, items)
    for item in items:
        deps.out(_line(result, item))
    if opts.dry_run:
        deps.out(
            "%s dry run: %d item(s), %d quarantined, %d verdict(s) not written, cursor not advanced"
            % (region, len(items), len(result.hits), len(result.verdicts))
        )
        return result
    if result.verdicts:
        result.written = client.write_verdicts(transport, result.verdicts)
    stamp = deps.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    client.write_cursor(cursor, region, client.next_since(items, since), stamp)
    written = result.written or client.VerdictResult()
    deps.out(
        "%s %d item(s), %d quarantined, %d verdict(s) written over %d report(s)%s"
        % (
            region,
            len(items),
            len(result.hits),
            written.fingerprints,
            written.reports,
            ", %d missing" % len(written.missing) if written.missing else "",
        )
    )
    return result


def run(opts: Options, deps: Deps | None = None) -> tuple[int, list[RegionResult]]:
    """Every region of `opts` in turn; a region's failure is reported and the next region still runs. Returns the worst exit status and the per-region results."""
    deps = deps or Deps()
    cursor = opts.cursor or client.cursor_path()
    rc = 0
    results: list[RegionResult] = []
    for region in opts.regions:
        try:
            results.append(run_region(region, opts, cursor, deps))
        except client.FeedbackError as exc:
            log.error("%s: %s" % (region, exc))
            rc = max(rc, exc.rc)
    return rc, results


def required_profile(regions: Sequence[str]) -> str:
    """The one Bitwarden profile the regions need; production and bench together are refused."""
    profiles = {client.profile_for(r) for r in regions}
    if len(profiles) != 1:
        raise client.FeedbackError(
            "production regions and bench need different Bitwarden profiles: run them separately",
            rc=2,
        )
    return profiles.pop()


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    return subprocess.run(list(argv), env=dict(env), check=False).returncode


def reexec_under_profile(
    argv: Sequence[str], profile: str, env: Mapping[str, str], run_child: Runner
) -> int | None:
    """This entry point under `profile`; None when it is already bound. A foreign bench login profile is refused, since `bws_env exec` never overwrites a name already set."""
    bound = [p for p in (env.get(PROFILES_ENV) or "").split(",") if p]
    if profile in bound:
        return None
    foreign = bench_preflight.foreign_profiles(login_bench.PROFILE_ROLE, client.BENCH_REGION, bound)
    if foreign:
        raise client.FeedbackError(
            "refusing to run under %s: that profile binds another bench's credentials; run from "
            "an unbound shell" % ", ".join(foreign),
            rc=2,
        )
    child = dict(env)
    ci = str(paths.repo_root() / ".ci")
    child["PYTHONPATH"] = ci + (os.pathsep + child["PYTHONPATH"] if child.get("PYTHONPATH") else "")
    return run_child(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            profile,
            "--",
            sys.executable,
            "-m",
            SELF,
            *argv,
        ],
        child,
    )


def main(
    argv: Sequence[str] | None = None,
    run_child: Runner = _subprocess_runner,
    deps: Deps | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        opts = parse_args(args)
        profile = required_profile(opts.regions)
        rebound = reexec_under_profile(args, profile, os.environ, run_child)
        if rebound is not None:
            return rebound
    except client.FeedbackError as exc:
        log.error(str(exc))
        return exc.rc
    rc, _ = run(opts, deps)
    return rc


if __name__ == "__main__":
    sys.exit(main())
