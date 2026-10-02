#!/usr/bin/env python3
"""ci-trace: the ONE way an agent reads this repo's CI.

WHY THIS EXISTS. Watching CI used to mean hand-writing a `gh` polling loop from prose in a skill file. Landing console#574 on 2026-08-25 that failed four ways in a single afternoon:

  1. The recipe was stale in NINE places. A manual sweep found six; a gate found
     three more in hook SCRIPTS the sweep's *.md grep could not see. Two of them
     printed a loop their own neighbouring prose contradicted.
  2. A watch reported a SUPERSEDED ATTEMPT's verdict as final. The watchdog
     re-ran a transient failure, run_attempt went to 2, and a loop keyed on
     `status == completed` had already latched onto attempt 1.
  3. A watch reported on a run a later push had already cancelled.
  4. A watch ate a `network is unreachable` blip and survived only because its
     retry arm happened to be written correctly.

Each was patched by hand, and each patch was more prose. So: one script, and the ad-hoc form is blocked at the pre-bash guard and at the Stop hook.

HOW 2 AND 3 BECOME IMPOSSIBLE RATHER THAN HANDLED. This keys on the PR's HEAD COMMIT, never on a run id, and reads GitHub's `statusCheckRollup`, which exposes the LATEST check run per context. A watchdog rerun therefore REPLACES the failed attempt instead of appearing beside it, and a run belonging to an older head is not in the rollup at all. There is no attempt number to get
wrong.

ONE IMPLEMENTATION. Every rule here already existed inside the Stop hook's wl_ci.py, whose own docstrings describe failures 2 and 3 verbatim -- it was just unreachable from a shell, so agents kept rebuilding a worse version. This imports that module rather than restating it, so the CLI and the Stop hook cannot disagree about what red means.
"""

import argparse
import contextlib
import datetime
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# THE sys.path HOP, stated rather than hidden. wl_ci lives with the Stop hook because that is where it is consumed on every turn. Copying its ~200 lines of rollup/classify logic here would recreate exactly the duplication this script exists to end -- the nine divergent copies above. One import, one truth.
sys.path.insert(0, str(REPO_ROOT / ".claude" / "hooks" / "stop"))
import wl_ci  # noqa: E402

# The registry reader is loaded by file: this script has no `.ci` hop and the canonical-hop ledger pins the one it has.
_WK_SPEC = importlib.util.spec_from_file_location(
    "well_known", REPO_ROOT / ".ci" / "rediacc_ci" / "well_known.py"
)
if _WK_SPEC is None or _WK_SPEC.loader is None:
    raise ImportError("cannot load .ci/rediacc_ci/well_known.py")
_WK = importlib.util.module_from_spec(_WK_SPEC)
sys.modules["well_known"] = _WK
_WK_SPEC.loader.exec_module(_WK)
GH_REPO = _WK.GH_REPO

# The diagnosis verbs (--why, --job, --watchdog, ...) live in rediacc_ci.ci.ci_diagnose so the CI-side publisher answers from the same code. Loaded by file for the same reason as well_known above.
_DG_SPEC = importlib.util.spec_from_file_location(
    "ci_diagnose", REPO_ROOT / ".ci" / "rediacc_ci" / "ci" / "ci_diagnose.py"
)
if _DG_SPEC is None or _DG_SPEC.loader is None:
    raise ImportError("cannot load .ci/rediacc_ci/ci/ci_diagnose.py")
D = importlib.util.module_from_spec(_DG_SPEC)
sys.modules["ci_diagnose"] = D
_DG_SPEC.loader.exec_module(D)

POLL_SECONDS = int(os.environ.get("CI_TRACE_POLL_S", "25"))
MAX_READ_FAILURES = int(os.environ.get("CI_TRACE_MAX_READ_FAILURES", "5"))

EXIT_GREEN = 0
EXIT_RED = 1
EXIT_NO_VERDICT = 2
EXIT_HEAD_MOVED = 3
EXIT_NO_CI = 4

# How long a branch head must have gone with no rollup-feeding run before it reads NO-CI rather than RUNNING. GitHub registers a push's runs asynchronously, normally within seconds; the grace absorbs a slow registration so a just-pushed head is never called NO-CI.
NOCI_GRACE_S = int(os.environ.get("CI_TRACE_NOCI_GRACE_S", "180"))

# `--timeout` TAKES A MANDATORY UNIT SUFFIX. A bare number is the one spelling a reader has to guess the unit of, and a long-lived background process with a guessed timeout is relaunched or abandoned on the wrong schedule. The suffix makes the unit part of the token, so nothing is read off a convention. The CI_TRACE_TIMEOUT_S environment default keeps its bare number: its
# name carries the unit.
TIMEOUT_UNITS = {"s": 1, "m": 60, "h": 3600}


def _timeout_seconds(text):
    """Seconds from a suffixed --timeout token. Raises argparse's own error type on a bare number."""
    token = str(text).strip()
    if not token or token[-1] not in TIMEOUT_UNITS:
        msg = (
            "%r needs an explicit unit: write 5400s, 90m or 1h. A bare number is refused because "
            "its unit would have to be guessed." % token
        )
        raise argparse.ArgumentTypeError(msg)
    try:
        value = float(token[:-1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            "%r is not a number followed by s, m or h" % token
        ) from None
    return int(value * TIMEOUT_UNITS[token[-1]])


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
    """(status, conclusion, jobs, workflow) for ONE run id, or (None, None, err, "").

    Reads per-JOB conclusions, not the run-level conclusion alone: a run whose status is `completed` can still carry a failed job, and the run-level field is the same coarse signal ci_classify refuses to treat as a verdict.
    """
    try:
        out = subprocess.run(
            [
                "gh",
                "run",
                "view",
                str(run_id),
                "--repo",
                GH_REPO,
                "--json",
                "status,conclusion,jobs,workflowName",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(root),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, None, "could not read run %s: %s" % (run_id, exc), ""
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
            "",
        )
    try:
        d = json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return None, None, "unparseable run payload for %s" % run_id, ""
    return d.get("status"), d.get("conclusion"), d.get("jobs") or [], d.get("workflowName") or ""


def _jobs_as_contexts(jobs):
    """`gh run view --json jobs` rows in the rollup's CheckRun shape, so ONE green rule (wl_ci.ci_gate) judges both reads."""
    return [
        {
            "__typename": "CheckRun",
            "name": j.get("name") or "?",
            "status": (j.get("status") or ("completed" if j.get("conclusion") else "")).upper(),
            "conclusion": (j.get("conclusion") or "").upper() or None,
            "databaseId": j.get("databaseId"),
            "detailsUrl": j.get("url") or "",
            "checkSuite": {"workflowRun": {"databaseId": None}},
        }
        for j in jobs
    ]


def _trace_run(root, run_id, wait, timeout, as_json):
    """Trace one run id to a terminal state. Mirrors the branch reader's codes."""
    deadline = time.time() + timeout
    read_failures = 0
    while True:
        status, conclusion, jobs, workflow = _run_snapshot(root, run_id)
        if status is None:
            # A read that cannot complete is NEVER green -- the same rule the branch reader applies. Absorb a blip, then say so out loud.
            read_failures += 1
            err = jobs if isinstance(jobs, str) else "unreadable"
            if not wait or read_failures >= MAX_READ_FAILURES:
                print("no-verdict: %s" % err, file=sys.stderr)
                return EXIT_NO_VERDICT
            time.sleep(POLL_SECONDS)
            continue
        read_failures = 0

        # SAME FILTER AS ci_classify, and this path needed it independently: `--run <id>` reads the run's OWN jobs endpoint directly rather than going through wl_ci.ci_classify's GraphQL contexts, so the CI_NONBLOCKING_CONTEXTS fix landed on the branch-tracing path (_snapshot below) and never touched this one -- proven live on PR #579 commit 9cbcf7d9's own rerun, which this trace
        # called RED on a run GitHub itself scored "success" once "Review Complete" (a check-run whose own summary says it can never block Console CI) was excluded.
        jobs = [j for j in jobs if j.get("name") not in wl_ci.CI_NONBLOCKING_CONTEXTS]
        failed = [j["name"] for j in jobs if j.get("conclusion") == "failure"]
        live = [j["name"] for j in jobs if not j.get("conclusion")]
        # THE SAME GREEN RULE AS THE BRANCH READ: a Console CI run is green only once CI Complete reported success. A run of another workflow (the Release dispatch) has no such job, so it is judged on its jobs alone.
        gate = wl_ci.ci_gate(
            {"contexts": _jobs_as_contexts(jobs), "rollup": "", "truncated": False},
            require_complete=workflow == wl_ci.CONSOLE_CI_WORKFLOW,
        )

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
            if failed or conclusion not in ("success", "skipped") or gate["verdict"] != "green":
                print("RED  run %s -> %s" % (run_id, conclusion or "?"), file=sys.stderr)
                for n in failed:
                    print("  failed: %s" % n, file=sys.stderr)
                if not failed and gate["verdict"] != "green":
                    print("  %s" % gate["reason"], file=sys.stderr)
                if gate["cancelled"] and not failed:
                    print("  %s" % _run_cause_line(root, run_id), file=sys.stderr)
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


def _fetcher(root):
    return D.GhFetcher(GH_REPO, cwd=root)


def _cause_text(cause):
    if not cause:
        return ""
    extra = " [watchdog run %s]" % cause["watchdog_run"] if cause.get("watchdog_run") else ""
    return "cause: %s: %s%s" % (cause.get("kind"), cause.get("detail"), extra)


def _run_cause_line(root, run_id):
    """`cause: <kind>: <detail>` for a cancelled run, read through ci_diagnose (three to five reads)."""
    fetch = _fetcher(root)
    run, err = D.run_info(fetch, run_id)
    if run is None:
        return "cause: unreadable (%s)" % err
    jobs, _err = D.run_jobs(fetch, run_id, run.get("run_attempt"))
    return _cause_text(D.cancel_cause(fetch, run, jobs=jobs))


def _emit(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    v = payload["verdict"]
    head = (payload.get("head") or "")[:8]
    pr = payload.get("pr")
    if v == "no-ci":
        where = ("PR #%s" % pr) if pr else ("branch %s" % payload.get("ref", "?"))
        print("NO-CI  %s @ %s: %s" % (where, head, payload["detail"]))
        return
    # Two SOURCES, never one undifferentiated channel. A branch read and a PR read answer different questions, and a reader who cannot tell which one arrived will draw the wrong conclusion from an identical-looking line.
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
            # THE TRACER'S OWN VERB, never a raw `gh api .../logs` recipe. That recipe needed --allow-escape-sequences, whose absence printed NOTHING and exited 1 (measured 2026-08-28 on job 98788324965), and every session that copied it paid for a full log in context. `--errors` prints the failing step's excerpt and caches the log.
            print("      errors: %s --job %s --errors" % (D.TRACE_CMD, row["job"]))
        elif row.get("url"):
            print("      %s" % row["url"])
    if payload.get("cause"):
        print("  %s" % _cause_text(payload["cause"]))
        print("  why: %s --why" % D.TRACE_CMD)
    if payload.get("waiting"):
        print("  %d context(s) still running." % payload["waiting"])
    # The review gate is NOT part of GREEN (it starts after green + ready), so it gets its own line rather than a say in the verdict.
    if payload.get("review") and payload.get("pr"):
        print("  review: %s (Review Complete; never part of the CI verdict)" % payload["review"])

    # THE FINISH SEQUENCE, NAMED AT THE MOMENT IT BECOMES POSSIBLE.
    #
    # Green is not the finish line -- the PR still has to be flipped ready, reviewed, and its threads resolved. That step depends on the agent REMEMBERING it, and agents forget: the loop reports "CI is green", the turn ends, and the PR sits in draft with every check passing. This watch exits exactly when green lands and re-invokes the agent with its output in hand, so this is the
    # one place the reminder cannot be missed.
    #
    # It PRINTS, it does not act. Flipping ready triggers a real Claude review that spends budget, several watches can be armed at once and would race each other, and a PR is sometimes held in draft deliberately. An observer that silently mutates PR state is a different tool with different risks.
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


def _parse_iso(text):
    try:
        return datetime.datetime.fromisoformat(text or "").timestamp()
    except ValueError:
        return None


def _noci_settled(pushed_at, first_seen, now, grace):
    """Whether a head with no rollup-feeding run has waited out the grace, so NO-CI is safe to say.

    THE ONE FALSE-VERDICT RISK here is a head pushed seconds ago whose runs GitHub has not registered yet: it looks exactly like a [skip ci] head. Two independent lower bounds on the head's age, either one sufficient:

      * the repository's `pushedAt` is its LAST push to ANY branch, so the ref's head has existed on the remote at least that long;
      * this process has seen the no-run state continuously since `first_seen` (a --wait on a busy repo, where pushedAt keeps moving).

    The commit's own date is deliberately NOT one of them: pushing an old local commit keeps its old committer date.
    """
    pushed = _parse_iso(pushed_at)
    if pushed is not None and now - pushed >= grace:
        return True
    return first_seen is not None and now - first_seen >= grace


def _judge_ancestor(root, info, ref):
    """ "<sha8> <verdict>" for the nearest ancestor with checks, judged with the same ownership filter, or a short reason it was not."""
    owner, name, sha = info.get("owner"), info.get("name"), info.get("sha") or ""
    anc, err = wl_ci.nearest_checked_ancestor(root, owner, name, sha)
    if err:
        return "unreadable (%s)" % err
    if not anc:
        return "none within 10 commits"
    state, ainfo = wl_ci.ci_commit_rollup(root, owner, name, anc, ref)
    if state != "ok":
        return "%s unreadable (%s)" % (anc[:8], ainfo)
    gate = wl_ci.ci_gate(ainfo)
    if gate["hard"]:
        verdict = "red (%d job(s) failed)" % len(gate["hard"])
    elif not ainfo.get("contexts"):
        verdict = "no checks from %s's own runs" % ref
    elif gate["verdict"] == "red" and gate["cancelled"]:
        verdict = "red (cancelled context)"
    elif gate["verdict"] == "green":
        verdict = "green"
    else:
        verdict = "%s (%s)" % (gate["verdict"], gate["reason"])
    return "%s %s" % (anc[:8], verdict)


def _no_ci_check(root, ref, info, seen):
    """For a branch head with NO context from its own runs: ("no-ci" | "running", detail).

    Without this, a [skip ci] head read RUNNING with 0 contexts forever, and `--wait --ref main` polled it to the timeout (measured 2026-09-30 on main 0dfd4a04, a release-state commit).
    """
    sha = info.get("sha") or ""
    runs, err = wl_ci.commit_ci_runs(root, info.get("owner"), info.get("name"), sha)
    if runs is None:
        return "running", "no checks on this head yet, and its runs could not be listed: %s" % err
    if runs:
        return "running", "%d run(s) on this commit have not reported checks yet: %s" % (
            len(runs),
            ", ".join("%s (%s, %s)" % (r[1], r[2], r[3]) for r in runs[:3]),
        )
    now = time.time()
    first_seen = seen.setdefault(sha, now) if seen is not None else now
    if not _noci_settled(info.get("pushed_at"), first_seen, now, NOCI_GRACE_S):
        return "running", (
            "no run registered for this commit yet; waiting out the %ds registration grace"
            " before calling it NO-CI" % NOCI_GRACE_S
        )
    return "no-ci", (
        "no run exists for this commit ([skip ci] or path-filtered); nearest judged ancestor: %s"
        % _judge_ancestor(root, info, ref)
    )


def _registering(root, info, seen, detail):
    """("running" | "no-ci", detail) for a head whose CI Complete has not reported, naming what IS there."""
    sha = info.get("sha") or ""
    runs, err = wl_ci.commit_ci_runs(root, info.get("owner"), info.get("name"), sha)
    if runs is None:
        return "running", "%s; its runs could not be listed: %s" % (detail, err)
    console = [r for r in runs if r[1] == wl_ci.CONSOLE_CI_WORKFLOW]
    if console:
        r = console[0]
        return "running", "%s; %s run %s is %s (attempt %s)" % (detail, r[1], r[0], r[3], r[4])
    now = time.time()
    first_seen = seen.setdefault(sha, now) if seen is not None else now
    if info.get("contexts") and _noci_settled(info.get("pushed_at"), first_seen, now, NOCI_GRACE_S):
        return "no-ci", (
            "no %s run exists for this commit ([skip ci] or path-filtered), so %s will never"
            " report; %d other context(s) are not a verdict"
            % (
                wl_ci.CONSOLE_CI_WORKFLOW,
                wl_ci.CI_COMPLETE_CONTEXT,
                len(info.get("contexts") or []),
            )
        )
    return "running", "%s; no %s run registered yet (waiting out the %ds registration grace)" % (
        detail,
        wl_ci.CONSOLE_CI_WORKFLOW,
        NOCI_GRACE_S,
    )


def _snapshot(root, ref, cache, allow_branch=False, seen=None):
    """One read -> a payload dict, or None with a reason when unreadable."""
    state, info = wl_ci.ci_rollup(root, ref, allow_branch=allow_branch)
    if state == "no-pr":
        return None, "no open PR for ref %r" % ref
    if state == "no-ref":
        # Distinct from no-pr on purpose: a ref that does not exist is a typo or a deleted branch, not a branch that merely lacks a PR.
        return None, "no branch %r on the remote" % ref
    if state == "unreadable":
        return None, str(info)

    gate = wl_ci.ci_gate(info)
    live, hard, soft = gate["live"], gate["hard"], gate["soft"]
    if hard:
        wl_ci.ci_steps(root, info, hard, cache)

    waiting = 0
    for c in info.get("contexts") or []:
        if c.get("__typename") == "StatusContext":
            if (c.get("state") or "").upper() in ("PENDING", "EXPECTED"):
                waiting += 1
        elif (c.get("status") or "").upper() != "COMPLETED":
            waiting += 1
    cause = None

    # CANCELLED IS NOT A PASS, and the two shapes mean different things. A cancelled context beside a real failure is the watchdog killing the run for that failure. Cancelled with nothing failing is a gate that did NOT report: a newer push is the usual cause, but it is NOT proof of one -- on 2026-09-05 a032863c7 had a cancelled Review Status while being the branch head itself.
    # Confirm a newer head exists before concluding one does.
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
    elif gate["verdict"] == "red" and gate["cancelled"]:
        verdict = "red"
        # ATTRIBUTED, NOT GUESSED. This once said "a newer push superseded this run" unconditionally, and on 2026-09-05 a032863c7 WAS the branch head. Then it said "a newer push is the usual cause", and on 2026-10-02 run 36953549081 was cancelled by the watchdog's job budget on the PR head itself. The cause is now read from the evidence (ci_diagnose.cancel_cause: watchdog annotations, then a newer head,
        # then a timeout kill, then a person), and when none proves it the line says so.
        cause = wl_ci.ci_cancel_cause(root, info, gate)
        detail = (
            "%d context(s) CANCELLED with nothing failing -- each is a gate that did NOT report"
            % len(cancelled)
        )
    elif gate["verdict"] == "green":
        verdict, detail = "green", gate["reason"]
    else:
        verdict, detail = gate["verdict"], gate["reason"]
        if gate["ci_complete"] == "absent":
            verdict, detail = _registering(root, info, seen, detail)

    # A BRANCH HEAD WITH NOTHING OF ITS OWN is either still registering or never going to run. PR heads are excluded: a PR's head always runs.
    if info.get("source") == "branch" and not info.get("contexts"):
        verdict, detail = _no_ci_check(root, ref, info, seen)

    # A branch read judges only the runs OF that branch (wl_ci.branch_owns_context). Saying how many contexts on the SHA were set aside keeps a foreign PR run's failures visible as a count rather than silently absent.
    if info.get("foreign"):
        detail += "; %d context(s) on this SHA from another branch's run ignored" % info["foreign"]

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
        "foreign": info.get("foreign") or 0,
        "cause": cause,
        "ci_complete": gate["ci_complete"],
        "run": gate["run"],
        "review": wl_ci.review_gate_row(info)[0] if info.get("source") != "branch" else "",
    }, None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="ci-trace.py",
        description="Read this repo's CI for the current branch's open PR.",
        epilog=(
            "exit codes:\n"
            "  0  green       CI Complete succeeded on this head and nothing failed\n"
            "  1  red         a job failed, or a gate was cancelled (the cause is named)\n"
            "  2  no verdict  still in flight or still registering (without --wait), a\n"
            "                 truncated read, no open PR, or unreadable\n"
            "  3  head moved  --wait only: a push replaced the head being watched\n"
            "  4  no CI       no Console CI run exists for the head ([skip ci] or\n"
            "                 path-filtered), after a registration grace; for a branch\n"
            "                 head the nearest ancestor with checks is named and judged\n"
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
        type=_timeout_seconds,
        default=int(os.environ.get("CI_TRACE_TIMEOUT_S", "5400")),
        help="--wait only: give up after this long. UNIT SUFFIX REQUIRED: 90m, 5400s, 1h (default 5400s)",
    )
    verbs = ap.add_argument_group("diagnosis (one read, then exit; --json for structure)")
    verbs.add_argument(
        "--why",
        action="store_true",
        help="why the PR head's Console CI run (or --run <id>) is red, cancelled or slow: cause, failing step, category, silences",
    )
    verbs.add_argument(
        "--runs", action="store_true", help="the newest Console CI runs on the branch"
    )
    verbs.add_argument(
        "--jobs",
        action="store_true",
        help="with --run: every job that did not pass, durations against p90",
    )
    verbs.add_argument("--attempt", type=int, default=None, help="with --run: one specific attempt")
    verbs.add_argument(
        "--job", metavar="JOB_ID", help="one job: pair with --errors, --steps or --log"
    )
    verbs.add_argument(
        "--errors",
        action="store_true",
        help="with --job: the failing step's excerpt, category and silences",
    )
    verbs.add_argument(
        "--steps",
        action="store_true",
        help="with --job: every step with its duration, and the silences",
    )
    verbs.add_argument(
        "--log",
        action="store_true",
        help="with --job: the whole log (ANSI stripped, cached once complete)",
    )
    verbs.add_argument("--history", metavar="JOB_NAME", help="that job's last 5 completed runs")
    ap.add_argument(
        "--worklist-item",
        metavar="ID",
        help="with --wait: append the final verdict to this worklist item (needs --session)",
    )
    ap.add_argument(
        "--session",
        metavar="SID8",
        help="with --worklist-item: the session prefix that owns the item",
    )
    # The worklist CLI to call, for the gate test's fake only; hidden because a session has no reason to point it anywhere else.
    ap.add_argument("--worklist-script", help=argparse.SUPPRESS)
    verbs.add_argument(
        "--watchdog",
        nargs="?",
        const="",
        default=None,
        metavar="RUN_ID",
        help="the Watchdog Monitor runs for a run (default: the PR head's) and their annotations",
    )
    args = ap.parse_args(argv)

    root = REPO_ROOT

    if args.job:
        mode = "log" if args.log else ("steps" if args.steps else "errors")
        return verb_job(root, args.job, mode, args.json)
    if args.history:
        return verb_history(root, args.history, args.json)
    if args.watchdog is not None:
        return verb_watchdog(root, args.watchdog or args.run, args.ref or _branch(root), args.json)
    if args.why:
        return verb_why(root, args.run, args.attempt, args.ref or _branch(root), args.json)
    if args.runs:
        return verb_runs(root, args.ref or _branch(root), args.json)
    if args.run and args.jobs:
        return verb_jobs(root, args.run, args.attempt, args.json)

    # A DISPATCHED RUN IS NOT IN THE BRANCH ROLLUP, and that is why this branch exists. Measured 2026-08-26 on Release run 32968110599 (v1.3.1, head 1c006e53): the REST check-runs API for that exact commit showed `in_progress Tag & Release`, while the GraphQL statusCheckRollup for refs/heads/main returned 81 contexts, state SUCCESS, NONE in flight, and no Tag & Release among them.
    # So `--wait --ref main` printed "GREEN ... every context succeeded or was skipped" and exited 0 while the release was mid-flight -- twice, including with --until-final.
    #
    # That is the worst shape of wrong: /pr-merge step 5 tells the operator to watch the release land exactly that way, so the documented procedure could certify a release that had not run. The obvious CLI alternative is banned by block-adhoc-sanctioned.sh (it dropped 4/4 in one campaign and has exited 1 mid-run), which left NO working instrument for that step at all.
    if args.run:
        return _trace_run(root, args.run, args.wait, args.timeout, args.json)

    # Only an EXPLICIT --ref opts into the branch fallback. On the implicit current-branch default, "no open PR yet" is a useful answer and must not be silently replaced by a branch read that looks like a verdict.
    allow_branch = bool(args.ref)
    ref = args.ref or _branch(root)
    if not ref or ref == "HEAD":
        print("no-verdict: could not determine the current branch", file=sys.stderr)
        return EXIT_NO_VERDICT

    cache, read_failures, pinned_head = {}, 0, None
    seen: dict[str, float] = {}
    deadline = time.time() + args.timeout

    while True:
        payload, err = _snapshot(root, ref, cache, allow_branch=allow_branch, seen=seen)

        if payload is None:
            # A read that cannot complete is NEVER green. Failure 4 was a `network is unreachable` blip; a bounded retry absorbs that without ever letting silence read as success.
            read_failures += 1
            if not args.wait or read_failures >= MAX_READ_FAILURES:
                print("no-verdict: %s" % err, file=sys.stderr)
                return EXIT_NO_VERDICT
            time.sleep(POLL_SECONDS)
            continue
        read_failures = 0

        # FAILURE 3, made structural. Pin the head from the first good read; if the PR's head changes underneath us, a later push superseded what we were watching and the old verdict is meaningless.
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

        if payload["verdict"] == "red" and _red_is_final(payload, args.wait, args.until_final):
            _emit(payload, args.json)
            d = None
            if args.wait and payload.get("run"):
                # A watch that ends red ends WITH the diagnosis, so the next turn starts from the cause instead of from a round of raw reads.
                d = D.diagnose(_fetcher(root), payload["run"], pr_head=payload.get("head") or None)
                if not args.json:
                    print()
                    print(D.render(d))
            if args.wait:
                _record_final(
                    root, ref, payload, "cancelled" if payload.get("cause") else "red", args, d
                )
            return EXIT_RED
        if payload["verdict"] == "green":
            _emit(payload, args.json)
            if args.wait:
                _record_final(root, ref, payload, "green", args)
            return EXIT_GREEN
        if payload["verdict"] == "no-ci":
            _emit(payload, args.json)
            if args.wait:
                _record_final(root, ref, payload, "no-ci", args)
            return EXIT_NO_CI

        if not args.wait:
            _emit(payload, args.json)
            return EXIT_NO_VERDICT
        if time.time() > deadline:
            print("no-verdict: still running after %ds" % args.timeout, file=sys.stderr)
            return EXIT_NO_VERDICT
        time.sleep(POLL_SECONDS)


# ---- diagnosis verbs (PLAN-ci-verdict box B) ------------------------------------
#
# Every one of these replaces a raw `gh` read a session used to hand-write. They print compact text by default and the full structure with --json. All of them read through ci_diagnose, which is also what the CI-side publisher runs, so a local answer and the posted `CI Verdict` cannot disagree.


def _out(data, text, as_json):
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, default=str))
    else:
        print(text)


def _head_run(root, ref):
    """(run_id, head_sha, error): the Console CI run on the current PR head (or --ref head)."""
    state, info = wl_ci.ci_rollup(root, ref, allow_branch=True)
    if state == "no-pr":
        return None, "", "no open PR for ref %r" % ref
    if state == "no-ref":
        return None, "", "no branch %r on the remote" % ref
    if state != "ok":
        return None, "", str(info)
    gate = wl_ci.ci_gate(info)
    if gate["run"] and gate["ci_complete"] != "absent":
        return gate["run"], info.get("sha") or "", ""
    runs, err = wl_ci.commit_ci_runs(
        root, info.get("owner"), info.get("name"), info.get("sha") or ""
    )
    console = [r for r in runs or [] if r[1] == wl_ci.CONSOLE_CI_WORKFLOW]
    if console:
        return console[0][0], info.get("sha") or "", ""
    if gate["run"]:
        return gate["run"], info.get("sha") or "", ""
    return None, info.get("sha") or "", err or "no %s run on this head" % wl_ci.CONSOLE_CI_WORKFLOW


def verb_why(root, run_id, attempt, ref, as_json):
    pr_head = ""
    if not run_id:
        run_id, pr_head, err = _head_run(root, ref)
        if not run_id:
            print("no-verdict: %s" % err, file=sys.stderr)
            return EXIT_NO_VERDICT
    d = D.diagnose(_fetcher(root), run_id, attempt=attempt, pr_head=pr_head or None)
    _out(d, D.render(d), as_json)
    return {
        "green": EXIT_GREEN,
        "red": EXIT_RED,
        "cancelled": EXIT_RED,
    }.get(d["verdict"], EXIT_NO_VERDICT)


def verb_runs(root, ref, as_json):
    data, err = _fetcher(root).json("actions/workflows/ci.yml/runs?branch=%s&per_page=10" % ref)
    runs = (data or {}).get("workflow_runs") if isinstance(data, dict) else None
    if runs is None:
        print("no-verdict: %s" % (err or "no workflow_runs"), file=sys.stderr)
        return EXIT_NO_VERDICT
    rows = [
        {
            "run_id": r.get("id"),
            "attempt": r.get("run_attempt"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "sha": (r.get("head_sha") or "")[:8],
            "event": r.get("event"),
            "created_at": r.get("created_at"),
        }
        for r in runs
    ]
    text = "\n".join(
        ["%s runs on %s (newest first):" % (wl_ci.CONSOLE_CI_WORKFLOW, ref)]
        + [
            "  %s  a%s  %-11s %-10s %s  %s  %s"
            % (
                r["run_id"],
                r["attempt"],
                r["status"],
                r["conclusion"] or "-",
                r["sha"],
                r["event"],
                r["created_at"],
            )
            for r in rows
        ]
    )
    _out(rows, text, as_json)
    return 0


def _mins(s):
    return "-" if s is None else "%dm%02ds" % (s // 60, s % 60)


def verb_jobs(root, run_id, attempt, as_json):
    jobs, err = D.run_jobs(_fetcher(root), run_id, attempt)
    if not jobs:
        print("no-verdict: %s" % (err or "run %s has no jobs" % run_id), file=sys.stderr)
        return EXIT_NO_VERDICT
    p90 = D._p90_table()
    counts: dict[str, int] = {}
    rows = []
    for j in jobs:
        concl = j.get("conclusion") or j.get("status") or "?"
        counts[concl] = counts.get(concl, 0) + 1
        dur = D.durations(j, p90)
        rows.append(
            {
                "job_id": j.get("id"),
                "name": j.get("name"),
                "conclusion": concl,
                "s": dur["job_s"],
                "p90_s": dur["p90_s"],
                "tag": ""
                if D._blocking(j.get("name")) and not D._aggregator(j.get("name"))
                else ("  [aggregator]" if D._aggregator(j.get("name")) else "  [non-blocking]"),
            }
        )
    bad = [r for r in rows if r["conclusion"] not in ("success", "skipped")]
    # COMPACT: every failure, but cancelled jobs (29 of them on run 36953549081 attempt 1) only the 8 that ran longest past their p90 -- the rest were stopped BY the cancel, not the reason for it.
    over = lambda r: (r["s"] or 0) - (r["p90_s"] or 0)  # noqa: E731
    shown = [r for r in bad if r["conclusion"] != "cancelled"] + sorted(
        (r for r in bad if r["conclusion"] == "cancelled"), key=over, reverse=True
    )[:8]
    slow = sorted(
        (r for r in rows if r["s"] and r["p90_s"] and r["s"] > 1.5 * r["p90_s"] and r not in bad),
        key=lambda r: r["s"] - r["p90_s"],
        reverse=True,
    )[:3]
    lines = [
        "run %s%s: %d job(s): %s"
        % (
            run_id,
            " attempt %s" % attempt if attempt else "",
            len(rows),
            ", ".join("%d %s" % (n, k) for k, n in sorted(counts.items(), key=lambda kv: -kv[1])),
        )
    ]
    lines.extend(
        "  %-10s %s (%s)  %s%s%s"
        % (
            r["conclusion"],
            r["name"],
            r["job_id"],
            _mins(r["s"]),
            " vs p90 %s" % _mins(r["p90_s"]) if r["p90_s"] else "",
            r["tag"],
        )
        for r in shown
    )
    if len(bad) > len(shown):
        lines.append(
            "  ... %d more cancelled, shown longest-over-p90 first; --json lists all"
            % (len(bad) - len(shown))
        )
    lines.extend(
        "  slow       %s (%s)  %s vs p90 %s"
        % (r["name"], r["job_id"], _mins(r["s"]), _mins(r["p90_s"]))
        for r in slow
    )
    if bad:
        lines.append("  errors: %s --job <id> --errors" % D.TRACE_CMD)
    _out(rows, "\n".join(lines), as_json)
    return 0


def _job(root, job_id):
    data, err = _fetcher(root).json("actions/jobs/%s" % job_id)
    if not isinstance(data, dict) or not data.get("id"):
        return None, err or "job %s unreadable" % job_id
    return data, ""


def verb_job(root, job_id, mode, as_json):
    job, err = _job(root, job_id)
    if job is None:
        print("no-verdict: %s" % err, file=sys.stderr)
        return EXIT_NO_VERDICT
    fetch = _fetcher(root)
    if mode == "steps":
        rows = [
            {
                "number": st.get("number"),
                "name": st.get("name"),
                "conclusion": st.get("conclusion") or st.get("status"),
                "s": D._span(st.get("started_at"), st.get("completed_at")),
            }
            for st in job.get("steps") or []
        ]
        lines = [
            "JOB %s  %s  %s" % (job_id, job.get("name"), job.get("conclusion") or job.get("status"))
        ]
        for r in rows:
            if r["conclusion"] == "skipped":
                continue
            flag = "  <-- long" if (r["s"] or 0) >= 120 else ""
            lines.append(
                "  %3s %-9s %7s  %s%s"
                % (r["number"], r["conclusion"], _mins(r["s"]), _clip(r["name"]), flag)
            )
        log, _err = D.job_log(fetch, job_id, completed=job.get("status") == "completed")
        gaps = D.log_gaps(log or "")
        lines.extend(_gap_line(g) for g in gaps)
        _out({"job": job_id, "steps": rows, "gaps": gaps}, "\n".join(lines), as_json)
        return 0
    log, err = D.job_log(fetch, job_id, completed=job.get("status") == "completed")
    if log is None:
        print("no-verdict: could not read the log of job %s: %s" % (job_id, err), file=sys.stderr)
        return EXIT_NO_VERDICT
    if mode == "log":
        sys.stdout.write(log if log.endswith("\n") else log + "\n")
        return 0
    step, lines = D.failing_step_slice(log, job)
    category, sig = D.classify(lines)
    ex = D.excerpt(lines)
    gaps = D.log_gaps(log)
    dur = D.durations(job)
    data = {
        "job_id": job_id,
        "name": job.get("name"),
        "conclusion": job.get("conclusion"),
        "run_id": job.get("run_id"),
        "attempt": job.get("run_attempt"),
        "step": step,
        "step_s": dur["step_s"],
        "job_s": dur["job_s"],
        "p90_s": dur["p90_s"],
        "category": category,
        "signature": sig,
        "excerpt": ex,
        "gaps": gaps,
    }
    out = [
        "JOB %s  %s  %s  (run %s attempt %s)"
        % (
            job_id,
            job.get("name"),
            job.get("conclusion") or job.get("status"),
            job.get("run_id"),
            job.get("run_attempt"),
        ),
        "  step: %r %s (job %s%s)"
        % (
            step or "?",
            _mins(dur["step_s"]),
            _mins(dur["job_s"]),
            "; p90 %s" % _mins(dur["p90_s"]) if dur["p90_s"] else "",
        ),
        "  category: %s%s" % (category, " (%s: %s)" % (sig, D.signature_label(sig)) if sig else ""),
    ]
    out += ["    " + ln for ln in ex] or [
        "    (no error line or known signature in the failing step)"
    ]
    out += [_gap_line(g) for g in gaps]
    out.append("  full log: %s --job %s --log" % (D.TRACE_CMD, job_id))
    _out(data, "\n".join(out), as_json)
    return 0


def _clip(text, n=90):
    text = str(text or "")
    return text if len(text) <= n else text[: n - 3] + "..."


def _gap_line(g):
    return "  gap: %ss silent%s after %s %r -> %r" % (
        g["s"],
        " on vm=%s" % g["stream"] if g.get("stream") else "",
        g["at"],
        _clip(g["before"], 80),
        _clip(g["after"], 80),
    )


def verb_history(root, job_name, as_json):
    rows = D.history(_fetcher(root), job_name)
    p90 = D._p90_table().get(job_name)
    lines = ["%s: last %d run(s)%s" % (job_name, len(rows), "; p90 %.1fm" % p90 if p90 else "")]
    lines.extend(
        "  %-10s %7s  run %s a%s  %s %s  job %s"
        % (
            r["conclusion"],
            _mins(r["s"]),
            r["run_id"],
            r["attempt"],
            r["branch"],
            r["sha"],
            r["job_id"],
        )
        for r in rows
    )
    if not rows:
        lines.append(
            "  (no completed run of a job with that exact name among the 20 newest Console CI runs)"
        )
    _out(rows, "\n".join(lines), as_json)
    return 0 if rows else EXIT_NO_VERDICT


def verb_watchdog(root, run_id, ref, as_json):
    if not run_id:
        run_id, _sha, err = _head_run(root, ref)
        if not run_id:
            print("no-verdict: %s" % err, file=sys.stderr)
            return EXIT_NO_VERDICT
    fetch = _fetcher(root)
    run, err = D.run_info(fetch, run_id)
    if run is None:
        print("no-verdict: %s" % err, file=sys.stderr)
        return EXIT_NO_VERDICT
    data, err = fetch.json("actions/runs?head_sha=%s&per_page=100" % run.get("head_sha"))
    runs = (data or {}).get("workflow_runs") if isinstance(data, dict) else None
    if runs is None:
        print("no-verdict: %s" % (err or "no workflow_runs"), file=sys.stderr)
        return EXIT_NO_VERDICT
    title = D.WATCHDOG_TITLE_RE % run_id
    watchers = sorted(
        (r for r in runs if (r.get("display_title") or r.get("name") or "").startswith(title)),
        key=lambda r: r.get("created_at") or "",
    )
    rows = []
    lines = ["Watchdog Monitor runs for run %s (%d):" % (run_id, len(watchers))]
    for w in watchers:
        wj, _err = fetch.json("actions/runs/%s/jobs?per_page=100" % w.get("id"))
        notes = []
        for job in (wj.get("jobs") or []) if isinstance(wj, dict) else []:
            ann, _err = fetch.json("check-runs/%s/annotations?per_page=100" % job.get("id"))
            for a in ann if isinstance(ann, list) else []:
                msg = str(a.get("message") or "")
                if "Retention days" in msg:
                    continue
                notes.append(
                    {
                        "level": a.get("annotation_level"),
                        "title": a.get("title") or "",
                        "message": D.sanitize(msg),
                    }
                )
        rows.append(
            {
                "run_id": w.get("id"),
                "title": w.get("display_title"),
                "conclusion": w.get("conclusion"),
                "created_at": w.get("created_at"),
                "annotations": notes,
            }
        )
        lines.append(
            "  %s  %s  %s  %s"
            % (
                w.get("id"),
                w.get("created_at"),
                w.get("conclusion") or w.get("status"),
                w.get("display_title"),
            )
        )
        lines.extend(
            "    %-8s %s"
            % (n["level"], _clip((n["title"] + ": " if n["title"] else "") + n["message"], 200))
            for n in notes[:6]
        )
    _out(rows, "\n".join(lines), as_json)
    return 0


# ---- the final verdict, kept where a later turn or another session finds it (PLAN-ci-verdict box G) ----------
#
# The operator disabled the Stop hook on 2026-10-02, so a verdict that only reached the session through it reached nobody. A `--wait` that ends on a FINAL verdict therefore writes it to the branch-keyed cache beside the worklist (wl_civerdict's file and writer, so the hook side and the SessionStart line read the same bytes with no network call) and, when the watch was armed for a
# worklist item, onto that item through the worklist's own `--update` verb.

WORKLIST_SCRIPT = str(REPO_ROOT / ".claude" / "hooks" / "stop" / "worklist.py")


def _final_record(payload, verdict, diag=None):
    """The ci-verdict/v1 dict for a final verdict: the diagnosis when one was made, else built from the read itself."""
    if diag:
        d = dict(diag)
    else:
        d = D._blank(payload.get("run") or "", None, None)
        d.update(
            head_sha=payload.get("head") or "",
            workflow=wl_ci.CONSOLE_CI_WORKFLOW,
            conclusion=verdict,
            verdict=verdict,
            cause=payload.get("cause"),
        )
        if payload.get("failing") and payload["failing"][0].get("job"):
            d["next"] = "%s --job %s --errors" % (D.TRACE_CMD, payload["failing"][0]["job"])
        elif verdict in ("red", "cancelled"):
            d["next"] = "%s --why" % D.TRACE_CMD
    d["generator"] = "ci-trace.py --wait"
    return d


def _record_final(root, ref, payload, verdict, args, diag=None):
    """Write the final verdict to the branch cache and the leased worklist item. Never raises: a failed write is said on stderr."""
    record = _final_record(payload, verdict, diag)
    headline = D.render(record).splitlines()[0]
    try:
        import wl_civerdict  # noqa: PLC0415
        import wl_core  # noqa: PLC0415 -- the hook's own modules, on sys.path above

        worklist = wl_core.worklist_for(root)
        wl_civerdict.write_cache(
            worklist,
            ref,
            record.get("head_sha") or "",
            record,
            title=headline,
            summary=D.render(record),
            source="ci-trace",
        )
    except Exception as exc:  # noqa: BLE001
        print("ci-trace: the branch verdict cache was not written: %s" % exc, file=sys.stderr)
    if args.worklist_item and args.session:
        cause = record.get("cause") or {}
        text = "CI %s @ %s run %s attempt %s%s%s" % (
            str(record.get("verdict")).upper(),
            (record.get("head_sha") or "?")[:8],
            record.get("run_id") or "?",
            record.get("attempt") or "?",
            "; cause %s: %s" % (cause.get("kind"), cause.get("detail")) if cause else "",
            "; next: %s" % record["next"] if record.get("next") else "",
        )
        try:
            done = subprocess.run(
                [
                    sys.executable,
                    args.worklist_script or WORKLIST_SCRIPT,
                    "--update",
                    args.session,
                    args.worklist_item,
                    text,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                cwd=str(root),
            )
            if done.returncode != 0:
                print(
                    "ci-trace: worklist --update exited %d: %s"
                    % (done.returncode, (done.stderr or done.stdout).strip()[-200:]),
                    file=sys.stderr,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            print("ci-trace: worklist --update failed: %s" % exc, file=sys.stderr)
    return record


def _red_is_final(payload, wait, until_final):
    """Whether a red verdict ends the watch now.

    --until-final promises to wait "until nothing is in flight", so it keys on `waiting` (every context not yet completed) as well as `live`
    (the blocking ones ci_classify keeps). Keyed on `live` alone it returned on run 36520331675 while Quality / Branch's retry and the
    non-blocking macOS OPS leg were still running (waiting=2), which ended a watch armed to collect those jobs' durations.
    """
    return not (wait and until_final and (payload["live"] or payload["waiting"]))


def _selftest():
    """Controls for _trace_run's CI_NONBLOCKING_CONTEXTS filter.

    Review-found live on PR #579: `--run <id>` reads a run's jobs endpoint DIRECTLY rather than through wl_ci.ci_classify's GraphQL contexts, so the filter fixing ci_classify (see wl_ci.py --selftest) never touched this path -- proven by ci-trace.py itself calling a run GitHub scored "success" RED, because "Review Complete" (a check-run that can never
    block Console CI) showed up as conclusion=failure in the jobs list.
    """
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        if not cond:
            ok = False
        print(
            "  %s  %s%s" % ("PASS" if cond else "FAIL", label, "" if cond else "  <- %s" % detail)
        )

    review_complete_job = {"name": "Review Complete", "conclusion": "failure"}
    real_failure_job = {"name": "Quality / Code", "conclusion": "failure"}
    pending_job = {"name": "Stage Artifacts", "conclusion": None}

    def run_it(jobs, status="completed", run_conclusion="success", workflow=""):
        def fake_snapshot(_root, _run_id):
            return status, run_conclusion, jobs, workflow

        orig = globals()["_run_snapshot"]
        globals()["_run_snapshot"] = fake_snapshot
        try:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                rc = _trace_run(pathlib.Path("."), 1, wait=False, timeout=1, as_json=False)
            return rc, buf_out.getvalue() + buf_err.getvalue()
        finally:
            globals()["_run_snapshot"] = orig

    rc, out = run_it([review_complete_job])
    check(
        "THE REAL 2026-08-30 DEFECT: a run whose only failing job is "
        "'Review Complete' reports GREEN, not RED",
        rc == EXIT_GREEN,
        "rc=%r out=%r" % (rc, out),
    )

    rc, out = run_it([review_complete_job, real_failure_job])
    check(
        "REGRESSION CONTROL: a genuine failure beside Review Complete is "
        "still reported RED, naming the real job",
        rc == EXIT_RED and "Quality / Code" in out and "Review Complete" not in out,
        "rc=%r out=%r" % (rc, out),
    )

    rc, out = run_it([review_complete_job, pending_job], status="in_progress")
    check(
        "CONTROL: the filter does not interfere with the in-flight path -- a "
        "run that is genuinely still running reports no-verdict, not GREEN, "
        "even though its only completed job is the filtered-out one",
        rc == EXIT_NO_VERDICT,
        "rc=%r out=%r" % (rc, out),
    )

    check(
        "--until-final keeps waiting on a red run while a non-blocking context is still running (live empty, waiting 1)",
        not _red_is_final({"live": [], "waiting": 1}, True, True),
    )
    check(
        "CONTROL: --until-final returns on a red run once nothing is in flight",
        _red_is_final({"live": [], "waiting": 0}, True, True),
    )
    check(
        "CONTROL: --wait alone returns on the first red even with contexts still running",
        _red_is_final({"live": ["x"], "waiting": 3}, True, False),
    )

    # THE UNIT SUFFIX, paired with its control. Refusing the bare form is worth nothing unless the suffixed form still works, so both are asserted.
    bare = None
    try:
        _timeout_seconds("5400")
    except argparse.ArgumentTypeError as exc:
        bare = str(exc)
    check(
        "a bare --timeout is refused and the refusal asks for an explicit unit",
        bare is not None and "needs an explicit unit" in bare,
        "refusal=%r" % bare,
    )
    check(
        "CONTROL: the suffixed forms are accepted and convert to seconds",
        (_timeout_seconds("5400s"), _timeout_seconds("90m"), _timeout_seconds("1h"))
        == (5400, 5400, 3600),
        "got %r" % ((_timeout_seconds("5400s"), _timeout_seconds("90m"), _timeout_seconds("1h")),),
    )

    # ---- THE 2026-10-02 FALSE GREEN (PLAN-ci-verdict box A). At 02:01Z `--wait --until-final` printed GREEN for PR #591 head a7f30558 a minute after Console CI run 36953549081 was created, because the only contexts registered (from CI - OBS Mirror) were green and none was in flight. Driven through the REAL _snapshot with the network stubbed at wl_ci's two reads.
    def snap(contexts, runs, truncated=False):
        info = {
            "owner": "rediacc",
            "name": "console",
            "source": "pr",
            "pr": 591,
            "draft": True,
            "url": "u",
            "sha": "a7f305585530b61da88faf297b9d5805e5eb2b98",
            "rollup": "SUCCESS",
            "total": len(contexts),
            "contexts": contexts,
            "foreign": 0,
            "has_rollup": True,
            "truncated": truncated,
        }
        saved = (wl_ci.ci_rollup, wl_ci.commit_ci_runs, wl_ci.ci_cancel_cause)
        wl_ci.ci_rollup = lambda *_a, **_k: ("ok", info)
        wl_ci.commit_ci_runs = lambda *_a, **_k: (runs, "")
        wl_ci.ci_cancel_cause = lambda *_a, **_k: {
            "kind": "watchdog-budget",
            "detail": "'Tests + Infra / E2E Workers (fedora-43, 1/8)' ran 20.1m (budget 20m)",
            "job": "Tests + Infra / E2E Workers (fedora-43, 1/8)",
            "watchdog_run": 36956399799,
        }
        try:
            payload, _err = _snapshot(pathlib.Path("."), "0930-1", {}, seen={})
        finally:
            wl_ci.ci_rollup, wl_ci.commit_ci_runs, wl_ci.ci_cancel_cause = saved
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _emit(payload, False)
        return payload, buf.getvalue()

    def ctx(name, conclusion="SUCCESS", status="COMPLETED", run=36953549081):
        return {
            "__typename": "CheckRun",
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "databaseId": 7,
            "checkSuite": {"workflowRun": {"databaseId": run}},
        }

    console_run = [(36953549081, "Console CI", "pull_request", "queued", 1, "2026-10-02T01:59:55Z")]
    p, out = snap([ctx("OBS Mirror (opensuse-16.0)", run=36953548680)], console_run)
    check(
        "THE 2026-10-02 FALSE GREEN: only OBS Mirror contexts, all green -> RUNNING, naming CI Complete and the queued Console CI run",
        p["verdict"] == "running"
        and "CI Complete" in p["detail"]
        and "36953549081" in p["detail"]
        and "GREEN" not in out,
        "payload=%r out=%r" % (p, out),
    )
    p, out = snap(
        [
            ctx("Quality / Code"),
            ctx("CI Complete"),
            ctx("Review Complete", "FAILURE", run=1),
            ctx("CI Verdict", None, "IN_PROGRESS", run=2),
        ],
        console_run,
    )
    check(
        "CONTROL: CI Complete successful, Review Complete red and CI Verdict in flight -> GREEN, with a separate review: line",
        p["verdict"] == "green" and "review: red" in out,
        "payload=%r out=%r" % (p, out),
    )
    p, out = snap([ctx("Quality / Code"), ctx("CI Complete")], console_run, truncated=True)
    check(
        "CONTROL: a truncated read is no-verdict, never green",
        p["verdict"] == "no-verdict",
        "payload=%r" % (p,),
    )
    p, out = snap(
        [ctx("Quality / Code")] * 104
        + [ctx("E2E / x", "CANCELLED")] * 29
        + [ctx("Init", "SKIPPED")] * 33,
        console_run,
    )
    check(
        "THE ATTRIBUTION: 104 success / 33 skipped / 29 cancelled -> RED, the watchdog budget and the job named, no 'newer push'",
        p["verdict"] == "red"
        and "watchdog-budget" in out
        and "fedora-43, 1/8" in out
        and "newer push" not in out,
        "out=%r" % (out,),
    )
    p, out = snap([ctx("OBS Mirror (opensuse-16.0)", run=36953548680)], [])
    check(
        "CONTROL: no Console CI run registered yet on a just-seen head stays RUNNING (the grace), never NO-CI",
        p["verdict"] == "running" and "registration grace" in p["detail"],
        "payload=%r" % (p,),
    )
    rc, out = run_it([{"name": "Quality / Code", "conclusion": "success"}], workflow="Console CI")
    check(
        "--run: a completed Console CI run without CI Complete is not GREEN",
        rc == EXIT_RED and "CI Complete" in out,
        "rc=%r out=%r" % (rc, out),
    )
    rc, out = run_it(
        [
            {"name": "Quality / Code", "conclusion": "success"},
            {"name": "CI Complete", "conclusion": "success"},
        ],
        workflow="Console CI",
    )
    check(
        "CONTROL: --run with CI Complete successful is GREEN",
        rc == EXIT_GREEN,
        "rc=%r out=%r" % (rc, out),
    )

    print("  %s" % ("all ci-trace controls passed" if ok else "*** FAILURES ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
