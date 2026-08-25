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
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _emit(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    v = payload["verdict"]
    head = (payload.get("head") or "")[:8]
    pr = payload.get("pr")
    where = "PR #%s @ %s" % (pr, head) if pr else payload.get("ref", "?")
    print("%s  %s" % (v.upper(), where))
    if payload.get("detail"):
        print("  %s" % payload["detail"])
    for row in payload.get("failing") or []:
        step = (" -> step %r" % row["step"]) if row.get("step") else ""
        att = (" (attempt %s)" % row["attempt"]) if row.get("attempt") else ""
        print("  %-9s %s%s%s" % (row["conclusion"], row["name"], step, att))
        if row.get("job"):
            print("      log: gh api repos/%s/%s/actions/jobs/%s/logs"
                  % (payload["owner"], payload["name"], row["job"]))
        elif row.get("url"):
            print("      %s" % row["url"])
    if payload.get("waiting"):
        print("  %d context(s) still running." % payload["waiting"])
    if payload.get("soft"):
        print("  %d failing job(s) are on the watchdog retry allowlist and may be"
              " retried; not actionable yet." % len(payload["soft"]))


def _snapshot(root, ref, cache):
    """One read -> a payload dict, or None with a reason when unreadable."""
    state, info = wl_ci.ci_rollup(root, ref)
    if state == "no-pr":
        return None, "no open PR for ref %r" % ref
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
            detail += "; %d cancelled alongside (watchdog killed the run for the" \
                      " failure above, not an independent problem)" % len(cancelled)
    elif live:
        verdict, detail = "running", "%d context(s) still in flight" % waiting
        if soft:
            detail += "; %d retryable failure(s) pending a watchdog rerun" % len(soft)
    elif cancelled:
        verdict = "red"
        detail = ("%d context(s) CANCELLED with nothing failing -- a newer push"
                  " superseded this run. Trace the newer head." % len(cancelled))
    else:
        verdict, detail = "green", "every context succeeded or was skipped"

    return {
        "verdict": verdict,
        "detail": detail,
        "ref": ref,
        "pr": info.get("pr"),
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
    ap.add_argument("--wait", action="store_true",
                    help="block until THIS head reaches a real terminal state")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--ref", default="", help="branch to trace (default: current)")
    ap.add_argument("--timeout", type=int, default=int(os.environ.get("CI_TRACE_TIMEOUT_S", "5400")),
                    help="--wait only: give up after N seconds (default 5400)")
    args = ap.parse_args(argv)

    root = REPO_ROOT
    ref = args.ref or _branch(root)
    if not ref or ref == "HEAD":
        print("no-verdict: could not determine the current branch", file=sys.stderr)
        return EXIT_NO_VERDICT

    cache, read_failures, pinned_head = {}, 0, None
    deadline = time.time() + args.timeout

    while True:
        payload, err = _snapshot(root, ref, cache)

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
            print("head-moved: was %s, now %s -- a push superseded the run being"
                  " watched. Re-run ci-trace against the new head."
                  % (pinned_head[:8], payload["head"][:8]), file=sys.stderr)
            return EXIT_HEAD_MOVED

        if payload["verdict"] == "red":
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
