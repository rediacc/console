#!/usr/bin/env python3
"""ci-trace: the ONE way an agent reads this repo's CI.

WHY THIS EXISTS. Watching CI used to mean hand-writing a `gh` polling loop from
prose in a skill file. Landing console#574 on 2026-08-25 that failed four ways
in a single afternoon:

  1. The recipe was stale in NINE places. A manual sweep found six; a gate found
     three more in hook SCRIPTS the sweep's *.md grep could not see. Two of them
     printed a loop their own neighbouring prose contradicted.
  2. A watch reported a SUPERSEDED ATTEMPT's verdict as final. The watchdog
     re-ran a transient failure, run_attempt went to 2, and a loop keyed on
     `status == completed` had already latched onto attempt 1.
  3. A watch reported on a run a later push had already cancelled.
  4. A watch ate a `network is unreachable` blip and survived only because its
     retry arm happened to be written correctly.

Each was patched by hand, and each patch was more prose. So: one script, and the
ad-hoc form is blocked at the pre-bash guard and at the Stop hook.

HOW 2 AND 3 BECOME IMPOSSIBLE RATHER THAN HANDLED. This keys on the PR's HEAD
COMMIT, never on a run id, and reads GitHub's `statusCheckRollup`, which exposes
the LATEST check run per context. A watchdog rerun therefore REPLACES the failed
attempt instead of appearing beside it, and a run belonging to an older head is
not in the rollup at all. There is no attempt number to get wrong.

ONE IMPLEMENTATION. Every rule here already existed inside the Stop hook's
wl_ci.py, whose own docstrings describe failures 2 and 3 verbatim -- it was just
unreachable from a shell, so agents kept rebuilding a worse version. This imports
that module rather than restating it, so the CLI and the Stop hook cannot
disagree about what red means.
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# THE sys.path HOP, stated rather than hidden. wl_ci lives with the Stop hook
# because that is where it is consumed on every turn. Copying its ~200 lines of
# rollup/classify logic here would recreate exactly the duplication this script
# exists to end -- the nine divergent copies above. One import, one truth.
sys.path.insert(0, str(REPO_ROOT / ".claude" / "hooks" / "stop"))
import wl_ci  # noqa: E402

POLL_SECONDS = int(os.environ.get("CI_TRACE_POLL_S", "25"))
MAX_READ_FAILURES = int(os.environ.get("CI_TRACE_MAX_READ_FAILURES", "5"))

EXIT_GREEN = 0
EXIT_RED = 1
EXIT_NO_VERDICT = 2
EXIT_HEAD_MOVED = 3


def _branch(root):
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _run_snapshot(root, run_id):
    """(status, conclusion, jobs) for ONE run id, or (None, None, err).

    Reads per-JOB conclusions, not the run-level conclusion alone: a run whose
    status is `completed` can still carry a failed job, and the run-level field
    is the same coarse signal ci_classify refuses to treat as a verdict.
    """
    try:
        out = subprocess.run(
            [
                "gh",
                "run",
                "view",
                str(run_id),
                "--repo",
                "rediacc/console",
                "--json",
                "status,conclusion,jobs",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, None, "could not read run %s: %s" % (run_id, exc)
    if out.returncode != 0:
        return (
            None,
            None,
            "gh exited %d for run %s: %s"
            % (
                out.returncode,
                run_id,
                (out.stderr or "").strip()[:200],
            ),
        )
    try:
        d = json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return None, None, "unparseable run payload for %s" % run_id
    return d.get("status"), d.get("conclusion"), d.get("jobs") or []


def _trace_run(root, run_id, wait, timeout, as_json):
    """Trace one run id to a terminal state. Mirrors the branch reader's codes."""
    deadline = time.time() + timeout
    read_failures = 0
    while True:
        status, conclusion, jobs = _run_snapshot(root, run_id)
        if status is None:
            # A read that cannot complete is NEVER green -- the same rule the
            # branch reader applies. Absorb a blip, then say so out loud.
            read_failures += 1
            err = jobs if isinstance(jobs, str) else "unreadable"
            if not wait or read_failures >= MAX_READ_FAILURES:
                print("no-verdict: %s" % err, file=sys.stderr)
                return EXIT_NO_VERDICT
            time.sleep(POLL_SECONDS)
            continue
        read_failures = 0

        failed = [j["name"] for j in jobs if j.get("conclusion") == "failure"]
        live = [j["name"] for j in jobs if not j.get("conclusion")]

        if as_json:
            print(
                json.dumps(
                    {
                        "run": run_id,
                        "status": status,
                        "conclusion": conclusion,
                        "failing": failed,
                        "waiting": live,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        if status == "completed":
            if failed or conclusion not in ("success", "skipped"):
                print("RED  run %s -> %s" % (run_id, conclusion or "?"), file=sys.stderr)
                for n in failed:
                    print("  failed: %s" % n, file=sys.stderr)
                return EXIT_RED
            print("GREEN  run %s -> %s" % (run_id, conclusion))
            return EXIT_GREEN
        if not wait:
            print("no-verdict: run %s still %s" % (run_id, status), file=sys.stderr)
            return EXIT_NO_VERDICT
        if time.time() > deadline:
            print(
                "no-verdict: run %s still %s after %ds" % (run_id, status, timeout), file=sys.stderr
            )
            return EXIT_NO_VERDICT
        if not as_json:
            print(
                "  run %s %s; %d job(s) in flight%s"
                % (run_id, status, len(live), (": " + ", ".join(live[:3])) if live else "")
            )
        time.sleep(POLL_SECONDS)


def _emit(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    v = payload["verdict"]
    head = (payload.get("head") or "")[:8]
    pr = payload.get("pr")
    # Two SOURCES, never one undifferentiated channel. A branch read and a PR
    # read answer different questions, and a reader who cannot tell which one
    # arrived will draw the wrong conclusion from an identical-looking line.
    if pr:
        where = "PR #%s @ %s" % (pr, head)
    elif payload.get("source") == "branch":
        where = "branch %s @ %s (no PR)" % (payload.get("ref", "?"), head)
    else:
        where = payload.get("ref", "?")
    print("%s  %s" % (v.upper(), where))
    if payload.get("detail"):
        print("  %s" % payload["detail"])
    for row in payload.get("failing") or []:
        step = (" -> step %r" % row["step"]) if row.get("step") else ""
        att = (" (attempt %s)" % row["attempt"]) if row.get("attempt") else ""
        print("  %-9s %s%s%s" % (row["conclusion"], row["name"], step, att))
        if row.get("job"):
            print(
                "      log: gh api repos/%s/%s/actions/jobs/%s/logs"
                % (payload["owner"], payload["name"], row["job"])
            )
        elif row.get("url"):
            print("      %s" % row["url"])
    if payload.get("waiting"):
        print("  %d context(s) still running." % payload["waiting"])

    # THE FINISH SEQUENCE, NAMED AT THE MOMENT IT BECOMES POSSIBLE.
    #
    # Green is not the finish line -- the PR still has to be flipped ready,
    # reviewed, and its threads resolved. That step depends on the agent
    # REMEMBERING it, and agents forget: the loop reports "CI is green", the
    # turn ends, and the PR sits in draft with every check passing. This watch
    # exits exactly when green lands and re-invokes the agent with its output in
    # hand, so this is the one place the reminder cannot be missed.
    #
    # It PRINTS, it does not act. Flipping ready triggers a real Claude review
    # that spends budget, several watches can be armed at once and would race
    # each other, and a PR is sometimes held in draft deliberately. An observer
    # that silently mutates PR state is a different tool with different risks.
    if v == "green" and payload.get("pr") and payload.get("draft"):
        print()
        print("  NEXT: this PR is still a DRAFT. Green is not the finish line.")
        print(
            "    gh pr ready %s --repo %s/%s" % (payload["pr"], payload["owner"], payload["name"])
        )
        print("  Then watch for the review, address its threads, and resolve them.")
        print("  (block-premature-ready allows the flip only while CI Complete is")
        print("   green on this head, so it will refuse if this verdict goes stale.)")
    if payload.get("soft"):
        print(
            "  %d failing job(s) are on the watchdog retry allowlist and may be"
            " retried; not actionable yet." % len(payload["soft"])
        )


def _snapshot(root, ref, cache, allow_branch=False):
    """One read -> a payload dict, or None with a reason when unreadable."""
    state, info = wl_ci.ci_rollup(root, ref, allow_branch=allow_branch)
    if state == "no-pr":
        return None, "no open PR for ref %r" % ref
    if state == "no-ref":
        # Distinct from no-pr on purpose: a ref that does not exist is a typo or
        # a deleted branch, not a branch that merely lacks a PR.
        return None, "no branch %r on the remote" % ref
    if state == "unreadable":
        return None, str(info)

    live, hard, soft = wl_ci.ci_classify(info)
    if hard:
        wl_ci.ci_steps(root, info, hard, cache)

    waiting = 0
    for c in info.get("contexts") or []:
        if c.get("__typename") == "StatusContext":
            if (c.get("state") or "").upper() in ("PENDING", "EXPECTED"):
                waiting += 1
        elif (c.get("status") or "").upper() != "COMPLETED":
            waiting += 1

    # CANCELLED IS NOT A PASS, and the two shapes mean opposites. A cancelled
    # context beside a real failure is the watchdog killing the run for that
    # failure; cancelled with nothing failing means a newer push superseded it.
    cancelled = [
        c.get("name") or c.get("context") or "?"
        for c in info.get("contexts") or []
        if (c.get("conclusion") or "").upper() == "CANCELLED"
    ]

    if hard:
        verdict, detail = "red", "%d job(s) failed" % len(hard)
        if cancelled:
            detail += (
                "; %d cancelled alongside (watchdog killed the run for the failure"
                " above, not an independent problem)" % len(cancelled)
            )
    elif live:
        verdict, detail = "running", "%d context(s) still in flight" % waiting
        if soft:
            detail += "; %d retryable failure(s) pending a watchdog rerun" % len(soft)
    elif cancelled:
        verdict = "red"
        detail = (
            "%d context(s) CANCELLED with nothing failing -- a newer push"
            " superseded this run. Trace the newer head." % len(cancelled)
        )
    else:
        verdict, detail = "green", "every context succeeded or was skipped"

    return {
        "verdict": verdict,
        "detail": detail,
        "ref": ref,
        "source": info.get("source") or "pr",
        "pr": info.get("pr"),
        "draft": bool(info.get("draft")),
        "url": info.get("url"),
        "owner": info.get("owner"),
        "name": info.get("name"),
        "head": info.get("sha") or "",
        "live": live,
        "waiting": waiting,
        "failing": hard,
        "soft": soft,
        "cancelled": cancelled,
        "truncated": info.get("truncated"),
    }, None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ci-trace.py",
        description="Read this repo's CI for the current branch's open PR.",
        epilog=(
            "exit codes:\n"
            "  0  green       head is final and nothing failed\n"
            "  1  red         at least one job failed, or the run was superseded\n"
            "  2  no verdict  still in flight (without --wait), no open PR, or unreadable\n"
            "  3  head moved  --wait only: a push replaced the head being watched\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--wait", action="store_true", help="block until THIS head reaches a real terminal state"
    )
    ap.add_argument(
        "--until-final",
        action="store_true",
        help=(
            "with --wait: keep waiting even after a job fails, until nothing is "
            "in flight. --wait alone exits on the FIRST hard failure, which is "
            "right for 'is it red' and wrong for babysitting: you cannot rerun a "
            "run that has not finished, and a red reported while 20 jobs are "
            "still running is not the whole picture."
        ),
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--ref",
        default="",
        help=(
            "branch to trace (default: current). An explicit --ref also reads a"
            " branch that has no open PR, which is what post-merge `main` is."
        ),
    )
    ap.add_argument(
        "--run",
        metavar="RUN_ID",
        help=(
            "trace ONE run by id instead of a branch. Required for a"
            " workflow_dispatch run (the Release workflow): a branch's"
            " statusCheckRollup does not contain it, so a --ref read reports"
            " GREEN while it is still in flight."
        ),
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("CI_TRACE_TIMEOUT_S", "5400")),
        help="--wait only: give up after N seconds (default 5400)",
    )
    args = ap.parse_args(argv)

    root = REPO_ROOT

    # A DISPATCHED RUN IS NOT IN THE BRANCH ROLLUP, and that is why this branch
    # exists. Measured 2026-08-26 on Release run 32968110599 (v1.3.1, head
    # 1c006e53): the REST check-runs API for that exact commit showed
    # `in_progress  Tag & Release`, while the GraphQL statusCheckRollup for
    # refs/heads/main returned 81 contexts, state SUCCESS, NONE in flight, and
    # no Tag & Release among them. So `--wait --ref main` printed
    # "GREEN ... every context succeeded or was skipped" and exited 0 while the
    # release was mid-flight -- twice, including with --until-final.
    #
    # That is the worst shape of wrong: /pr-merge step 5 tells the operator to
    # watch the release land exactly that way, so the documented procedure could
    # certify a release that had not run. The obvious CLI alternative is banned
    # by block-adhoc-sanctioned.sh (it dropped 4/4 in one campaign and has
    # exited 1 mid-run), which left NO working instrument for that step at all.
    if args.run:
        return _trace_run(root, args.run, args.wait, args.timeout, args.json)

    # Only an EXPLICIT --ref opts into the branch fallback. On the implicit
    # current-branch default, "no open PR yet" is a useful answer and must not be
    # silently replaced by a branch read that looks like a verdict.
    allow_branch = bool(args.ref)
    ref = args.ref or _branch(root)
    if not ref or ref == "HEAD":
        print("no-verdict: could not determine the current branch", file=sys.stderr)
        return EXIT_NO_VERDICT

    cache, read_failures, pinned_head = {}, 0, None
    deadline = time.time() + args.timeout

    while True:
        payload, err = _snapshot(root, ref, cache, allow_branch=allow_branch)

        if payload is None:
            # A read that cannot complete is NEVER green. Failure 4 was a
            # `network is unreachable` blip; a bounded retry absorbs that
            # without ever letting silence read as success.
            read_failures += 1
            if not args.wait or read_failures >= MAX_READ_FAILURES:
                print("no-verdict: %s" % err, file=sys.stderr)
                return EXIT_NO_VERDICT
            time.sleep(POLL_SECONDS)
            continue
        read_failures = 0

        # FAILURE 3, made structural. Pin the head from the first good read; if
        # the PR's head changes underneath us, a later push superseded what we
        # were watching and the old verdict is meaningless.
        if pinned_head is None:
            pinned_head = payload["head"]
        elif payload["head"] and payload["head"] != pinned_head:
            print(
                "head-moved: was %s, now %s -- a push superseded the run being"
                " watched. Re-run ci-trace against the new head."
                % (pinned_head[:8], payload["head"][:8]),
                file=sys.stderr,
            )
            return EXIT_HEAD_MOVED

        if payload["verdict"] == "red" and not (args.wait and args.until_final and payload["live"]):
            _emit(payload, args.json)
            return EXIT_RED
        if payload["verdict"] == "green":
            _emit(payload, args.json)
            return EXIT_GREEN

        if not args.wait:
            _emit(payload, args.json)
            return EXIT_NO_VERDICT
        if time.time() > deadline:
            print("no-verdict: still running after %ds" % args.timeout, file=sys.stderr)
            return EXIT_NO_VERDICT
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
