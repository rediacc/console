"""Console CI runs that share one commit: the duplicate-run skip and the release gate's sibling check.

WHY THIS EXISTS. On 2026-10-06 one merge to main (00db8bed) produced TWO Console CI push runs one second apart, 37437281526 and 37437282770, by the same actor; the cause (a duplicate delivery or a double push) is not visible in the events feed. The `ci-main` concurrency group queued the second behind the first. The first went green and released v1.8.0; the second then re-ran the whole pipeline on the same sha, re-staged and re-promoted edge for a version that was already released, and went red on a hung DNF install in Validate Promotion. The release had nothing to say about it: `finalize-release-sentinel` judges only its own run.

TWO DECISIONS, ONE READ.

`dedupe` (the `Duplicate Run Check` job, which `initialize` needs). On a push run, list the other Console CI push runs on the same sha with a LOWER run id (this run's own re-attempt shares its id, so it is never a sibling). If one of them is an ORIGINAL -- concluded `success`, or is still queued or in progress -- this run is a duplicate: it writes `duplicate_of=<id>`, `initialize` skips, every job downstream of it skips, and the run ends green with the original named in the summary. A sibling that failed or was cancelled does not count, so a new run after a red one proceeds normally: it may be a legitimate retry.

A sibling is an original only when its own `Initialize` job did not SKIP. A run whose Initialize skipped did no work (it was itself a duplicate, or a bot push), and a green no-op is not evidence that the sha passed CI: without this, a chain (run 1 in progress, run 2 a duplicate of it, run 1 then fails, run 3 arrives) would let run 3 skip on run 2's empty green. The jobs read is only made for a candidate original; a candidate whose jobs cannot be read is not counted.

`release-gate` (a step in `finalize-release-sentinel`, BEFORE the sentinel is sealed). Refuse to release when any OTHER Console CI push run on the same sha concluded `failure`, `timed_out` or `startup_failure`, naming each one. A job killed by its `timeout-minutes` ends `cancelled`, which CI Complete's soft tier rejects, so the run itself concludes `failure` and is caught here. A run-level `cancelled` on an EARLIER sibling (a person or the watchdog cancelled the whole run) refuses too, unless this run is the clean retry: its first attempt (`--run-attempt 1`) with no job of its own concluded failure, cancelled, timed_out or startup_failure (operator ruling 2026-10-06, /ask: "Block unless retry is clean"). A cancelled run says nothing about the commit, so a retry that passed outright is the evidence; a retry that needed a re-attempt, or carried a failed job, is not. A later cancelled sibling (a duplicate no-op cancelled behind this run) never counts. A sibling still queued behind `ci-main` is fine, because `dedupe` makes it a no-op.

FAILURE DIRECTIONS. Both decisions FAIL OPEN, deliberately and in the same direction as the rest of the release path:
  - `dedupe` that cannot read the API PROCEEDS (full CI). It never skips without a positively read original, so an unreadable API costs one redundant run, never a missing one.
  - `release-gate` that cannot read the API RELEASES, with a warning: `dispatch_release`'s doctrine is that a silently withheld release is worse than an extra one, and this run's own CI Complete is already green.
Each fail-open path prints one line saying so.

READS go through `rediacc_ci.core.gh_retry`: a 5xx or connection fault is retried, a 4xx or auth failure raises at once (and then fails open as above). `runner` is the injectable one-attempt `gh` seam the tests fill with a fake API.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import TYPE_CHECKING, Any

from rediacc_ci import log
from rediacc_ci.core import gh_retry, ghx

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# The Initialize job's display name in ci.yml (`name: Initialize`).
INITIALIZE_JOB = "Initialize"
OUTPUT_KEY = "duplicate_of"
ACTIVE_STATUSES = frozenset({"queued", "in_progress", "waiting", "requested", "pending"})
FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})
UNCLEAN_JOB_CONCLUSIONS = FAILED_CONCLUSIONS | {"cancelled"}


@dataclasses.dataclass(frozen=True)
class Run:
    id: int
    status: str
    conclusion: str
    event: str
    head_sha: str
    url: str = ""

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> Run:
        return cls(
            id=int(row.get("id") or 0),
            status=str(row.get("status") or ""),
            conclusion=str(row.get("conclusion") or ""),
            event=str(row.get("event") or ""),
            head_sha=str(row.get("head_sha") or ""),
            url=str(row.get("html_url") or ""),
        )

    def label(self) -> str:
        state = self.conclusion or self.status or "unknown"
        return "run %d (%s)%s" % (self.id, state, " " + self.url if self.url else "")


class Api:
    """The two reads, behind `gh_retry`. `runner` is the one-attempt `gh` seam."""

    def __init__(
        self,
        repo: str,
        workflow: str,
        *,
        runner: Callable[..., ghx.GhResult] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.repo = repo
        self.workflow = workflow
        self.runner = runner
        self.sleep = sleep

    def _get(self, path: str) -> Any:
        return gh_retry.api_json(path, runner=self.runner, sleep=self.sleep)

    def runs_on_sha(self, sha: str) -> list[Run]:
        data = self._get(
            "repos/%s/actions/workflows/%s/runs?head_sha=%s&event=push&per_page=100"
            % (self.repo, self.workflow, sha)
        )
        rows = data.get("workflow_runs") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ghx.GhBadOutputError(
                ["gh", "api", "runs"],
                0,
                "no workflow_runs list in the response",
                ghx.FAILURE_FAILED,
            )
        return [Run.from_api(r) for r in rows if isinstance(r, dict)]

    def latest_jobs(self, run_id: int) -> list[dict[str, Any]]:
        """Every job of that run's latest attempt."""
        data = self._get(
            "repos/%s/actions/runs/%d/jobs?filter=latest&per_page=100" % (self.repo, run_id)
        )
        jobs = data.get("jobs") if isinstance(data, dict) else None
        return [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []

    def initialize_conclusion(self, run_id: int) -> str:
        """The Initialize job's conclusion in that run's latest attempt, its status when it has none yet, or "" when the job is not listed."""
        data = self._get(
            "repos/%s/actions/runs/%d/jobs?filter=latest&per_page=100" % (self.repo, run_id)
        )
        jobs = data.get("jobs") if isinstance(data, dict) else None
        for job in jobs if isinstance(jobs, list) else []:
            if isinstance(job, dict) and job.get("name") == INITIALIZE_JOB:
                return str(job.get("conclusion") or job.get("status") or "")
        return ""


def siblings(runs: Iterable[Run], own_id: int, sha: str) -> list[Run]:
    """Other push runs of this workflow on this sha. A re-attempt of this run shares `own_id`, so it is excluded."""
    return [r for r in runs if r.id != own_id and r.event == "push" and r.head_sha == sha]


def is_candidate_original(run: Run) -> bool:
    return run.conclusion == "success" or (not run.conclusion and run.status in ACTIVE_STATUSES)


def find_original(
    runs: Iterable[Run], own_id: int, sha: str, initialize_of: Callable[[int], str]
) -> tuple[Run | None, list[str]]:
    """The earliest lower-id sibling that is an original, and one note per sibling considered. `initialize_of` may raise `ghx.GhError`; that sibling is then not counted."""
    notes: list[str] = []
    earlier = sorted((r for r in siblings(runs, own_id, sha) if r.id < own_id), key=lambda r: r.id)
    for run in earlier:
        if not is_candidate_original(run):
            notes.append(
                "%s: not an original (failed or cancelled runs may be retried)" % run.label()
            )
            continue
        try:
            init = initialize_of(run.id)
        except ghx.GhError as exc:
            notes.append("%s: its jobs could not be read (%s); not counted" % (run.label(), exc))
            continue
        if init == "skipped":
            notes.append("%s: its Initialize skipped, so it did no work; not counted" % run.label())
            continue
        if run.conclusion == "success" and init != "success":
            notes.append(
                "%s: green, but its Initialize reads %r; not counted"
                % (run.label(), init or "absent")
            )
            continue
        notes.append("%s: original" % run.label())
        return run, notes
    return None, notes


def failed_siblings(runs: Iterable[Run], own_id: int, sha: str) -> list[Run]:
    return [r for r in siblings(runs, own_id, sha) if r.conclusion in FAILED_CONCLUSIONS]


def cancelled_earlier(runs: Iterable[Run], own_id: int, sha: str) -> list[Run]:
    return [r for r in siblings(runs, own_id, sha) if r.id < own_id and r.conclusion == "cancelled"]


def unclean_jobs(jobs: Iterable[dict[str, Any]]) -> list[str]:
    """`<name> (<conclusion>)` for every job that ended failed, cancelled or timed out."""
    return [
        "%s (%s)" % (j.get("name") or "?", j.get("conclusion"))
        for j in jobs
        if j.get("conclusion") in UNCLEAN_JOB_CONCLUSIONS
    ]


# ---------------------------------------------------------------------------- commands


def _append(path: str, text: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def dedupe(args: argparse.Namespace, api: Api) -> int:
    if args.event != "push":
        log.info(
            "Event %r: duplicate detection applies to push runs only; proceeding." % args.event
        )
        return 0
    try:
        runs = api.runs_on_sha(args.sha)
    except ghx.GhError as exc:
        log.warn(
            "Could not list Console CI runs on %s (%s); proceeding with full CI, not skipping."
            % (args.sha, exc)
        )
        return 0
    original, notes = find_original(runs, args.run_id, args.sha, api.initialize_conclusion)
    for note in notes:
        log.info("  " + note)
    if original is None:
        log.info(
            "No earlier green or running Console CI push run on %s; this run proceeds." % args.sha
        )
        return 0
    log.warn(
        "DUPLICATE: Console CI %s already covers %s. Every job after this one skips."
        % (original.label(), args.sha)
    )
    _append(args.output, "%s=%d\n" % (OUTPUT_KEY, original.id))
    _append(
        args.summary,
        "### Duplicate run, nothing re-run\n\n"
        "Console CI %s already covers `%s`, so this run skips every job after the duplicate check "
        "and does not stage, promote or release anything.\n" % (original.label(), args.sha),
    )
    return 0


def release_gate(args: argparse.Namespace, api: Api) -> int:
    try:
        runs = api.runs_on_sha(args.sha)
    except ghx.GhError as exc:
        log.warn(
            "Could not list Console CI runs on %s (%s); releasing on this run's own green CI "
            "Complete (fail-open, as dispatch_release is)." % (args.sha, exc)
        )
        return 0
    failed = failed_siblings(runs, args.run_id, args.sha)
    if failed:
        log.error(
            "Refusing to release %s: another Console CI push run on the same commit failed."
            % args.sha
        )
        for run in failed:
            log.error("  " + run.label())
        log.error(
            "Investigate it first. A re-run of that run's failed jobs replaces its conclusion."
        )
        return 1
    cancelled = cancelled_earlier(runs, args.run_id, args.sha)
    if cancelled:
        refusal = _retry_refusal(args, api)
        if refusal:
            log.error(
                "Refusing to release %s: an earlier Console CI push run on the same commit was "
                "cancelled, and this run is not a clean retry (%s)." % (args.sha, refusal)
            )
            for run in cancelled:
                log.error("  " + run.label())
            log.error(
                "A cancelled run proves nothing about the commit, so only a retry that passed "
                "every job on its first attempt releases. Push a new commit, or dispatch the "
                "release by hand once the commit is known good."
            )
            return 1
        log.info(
            "An earlier run on %s was cancelled; this run is its clean retry (attempt 1, every "
            "job passed), so the release may proceed." % args.sha
        )
        return 0
    log.info(
        "No other Console CI push run on %s concluded failure; release may proceed." % args.sha
    )
    return 0


def _retry_refusal(args: argparse.Namespace, api: Api) -> str:
    """ "" when this run is a clean retry, else why it is not. An unreadable jobs list fails open, like every read here."""
    if args.run_attempt != 1:
        return (
            "this is attempt %d" % args.run_attempt
            if args.run_attempt
            else "the run attempt was not passed"
        )
    try:
        jobs = api.latest_jobs(args.run_id)
    except ghx.GhError as exc:
        log.warn(
            "Could not read this run's own jobs (%s); treating it as a clean retry "
            "(fail-open, as dispatch_release is)." % exc
        )
        return ""
    bad = unclean_jobs(jobs)
    return "its job(s) %s did not pass" % ", ".join(bad) if bad else ""


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rediacc_ci.ci.sibling_runs")
    parser.add_argument("command", choices=("dedupe", "release-gate"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--event", default="push")
    parser.add_argument("--run-attempt", default=0, type=int)
    parser.add_argument("--workflow", default="ci.yml")
    parser.add_argument("--output", default="")
    parser.add_argument("--summary", default="")
    return parser.parse_args(argv)


def main(argv: list[str], api: Api | None = None) -> int:
    args = parse(argv)
    api = api or Api(args.repo, args.workflow)
    if args.command == "dedupe":
        return dedupe(args, api)
    return release_gate(args, api)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
