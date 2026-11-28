"""The shared PR-loop Stop fixture: a checkout with a gh shim answering the PR read, the rollup and the job, and a Stop driver with WORKLIST_PUBLISH_REF unset.

It came out of test_wl_focus.py, deleted with the phase verb (agent/plans/PLAN-simple-two-tree-loop.md B10); test_wl_loop_next and test_wl_pr_scope_stop drive the real hook through it.
"""

from __future__ import annotations

import datetime
import json

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import band_env
from rediacc_hooks.tests.test_wl_ci_status import (
    CI_FRESH_PAYLOAD,
    CI_JOB_PAYLOAD,
    ci_job,
    write_exec,
)
from rediacc_hooks.tests.test_wl_ci_status import ci_rollup as ci_status_rollup

__all__ = ["CI_RED", "PLAN_PAD", "band_env", "merged_nodes", "stamp", "stop", "world"]

ME = wlfix.ME
SAID = "working the PR\n\n## Remaining\n- the PR"
CI_RED = "CI IS RED ON PR #543"

PLAN_PAD = "Context paragraph that exists only so this fixture clears the minimum plan length and is read at all by the plan parser. "

# The gh shim: the one PR read (wl_ci.pr_link) ahead of the rollup, both from files so a case can swap them.
GH_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        *'states:[OPEN,MERGED,CLOSED]'*) cat "%(base)s/ci-merged.json"; exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""


def stamp(minutes_ago: float = 0.0) -> str:
    t = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def merged_nodes(fix, nodes: list[dict]) -> None:
    body = {"data": {"repository": {"pullRequests": {"nodes": nodes}}}}
    (fix.base / "ci-merged.json").write_text(json.dumps(body) + "\n", encoding="utf-8")
    fix.stem(".prlink-%s" % ME).unlink(missing_ok=True)


def world(fix, ci: bool = False, red: bool = False) -> None:
    """The fixture: fresh brief and handover, the gh shim, and optionally a git repo whose origin/pub PR #543 has a red job."""
    if ci:
        fix.git("init", "-q", "-b", "main")
        fix.git("config", "user.email", "t@t")
        fix.git("config", "user.name", "t")
        fix.git("remote", "add", "origin", wlfix.FAKE_ORIGIN)
        (fix.proj / "a.txt").write_text("a\n", encoding="utf-8")
        fix.git("add", "-A")
        fix.git("commit", "-qm", "base")
        head = fix.git("rev-parse", "HEAD").stdout.strip()
        if not head:
            raise RuntimeError("the fixture's base commit did not resolve a HEAD sha")
        fix.git("update-ref", "refs/remotes/origin/pub", head)
    fix.brief_now()
    fix.hand_now()
    (fix.base / "ci-fresh.json").write_text(json.dumps(CI_FRESH_PAYLOAD) + "\n", encoding="utf-8")
    (fix.base / "ci-job.json").write_text(json.dumps(CI_JOB_PAYLOAD) + "\n", encoding="utf-8")
    merged_nodes(fix, [])
    write_exec(fix.base / "binonly" / "gh", GH_SHIM % {"base": fix.base})
    if red:
        ci_status_rollup(fix, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    elif ci:
        ci_status_rollup(fix, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))


def stop(fix, extra: dict | None = None, judge: bool = False) -> wlfix.Result:
    """A Stop with the gh shim on PATH and WORKLIST_PUBLISH_REF UNSET: only the live loop state can arm the CI read."""
    env = dict(extra) if extra and "CTX_BAND_STATE_DIR" in extra else band_env(fix, 0)
    env.update(extra or {})
    env["PATH"] = "%s:%s" % (fix.base / "binonly", fix.env.get("PATH", ""))
    fix.say(SAID)
    if judge:
        return fix.runj(env)
    return fix.run(env)
