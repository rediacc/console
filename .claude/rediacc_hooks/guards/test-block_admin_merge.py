#!/usr/bin/env python3
"""Control harness for block_admin_merge's plan gate (box L2 of agent/plans/PLAN-plan-per-pr-loop.md).

WHY A SUITE BESIDE THE GOLDEN. The differential corpus runs this guard under the harness's default `gh` stub, which answers nothing, so every merge stops at "could not resolve the PR" and the plan gate is never reached (the guard's own PORT NOTE). This file puts a `gh` stub on PATH that answers `gh pr view` with a console PR whose body each case sets, and a fixture checkout whose committed plans the gate
reads at `origin/<head>`.

WHAT A CASE ASSERTS. Only the plan gate's own verdict: `plan` means the refusal is the plan gate's (its message carries PLAN_MARK), `past` means the merge got past the plan gate. A `past` case is still refused further down in this fixture (the per-commit review arm walks commits this fixture does not review), and that refusal is not this suite's subject; the review arm has its own suite in
`tests/test_wl_review_check.py`.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, as every guard suite here does.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
DISPATCH = str(HERE.parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_admin_merge"]

# The well-known repo slugs, read from .ci/config/well-known.env by the CI reader, loaded by file like runtmp below (check:ci-literal-sources forbids spelling them).
_WK = importlib.util.spec_from_file_location(
    "well_known_for_suite", HERE.parents[3] / ".ci" / "rediacc_ci" / "well_known.py"
)
if _WK is None or _WK.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/well_known.py is missing" % __file__)
well_known = importlib.util.module_from_spec(_WK)
_WK.loader.exec_module(well_known)
GH_REPO, RENET_REPO = well_known.GH_REPO, well_known.RENET_REPO

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-admin-merge-")

PLAN_MARK = "fails the plan gate"
BRANCH = "0914-1"
PLAN_DONE = "agent/plans/PLAN-fx-done.md"
PLAN_OPEN = "agent/plans/PLAN-fx-open.md"
PLANS = {
    PLAN_DONE: "# PLAN-fx-done\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n- [x] B the second box is finished and ticked\n",
    PLAN_OPEN: "# PLAN-fx-open\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n- [ ] B the second box is still open on this branch\n",
}

_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _git(repo, *args):
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False, env=_ENV
    )
    if proc.returncode != 0:
        raise SystemExit("fixture git %s failed in %s: %s" % (args, repo, proc.stderr))
    return proc.stdout.strip()


def _make_checkout():
    """A checkout on BRANCH whose plans are committed and published as `origin/<BRANCH>`; the open plan is ticked in the working tree only, which the gate must not count."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="checkout-", dir=RUN_TMP))
    _git(d, "init", "-q", "--initial-branch=%s" % BRANCH)
    for rel, text in PLANS.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    _git(d, "add", "--", *PLANS)
    _git(d, "commit", "-q", "-m", "plans")
    _git(d, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD")
    (d / PLAN_OPEN).write_text(PLANS[PLAN_OPEN].replace("- [ ]", "- [x]"), encoding="utf-8")
    return d


CHECKOUT = _make_checkout()

GH_STUB = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:2] == ["pr", "view"]:
    pr = {
        "number": 7,
        "statusCheckRollup": [{"name": "CI Complete", "conclusion": "SUCCESS"}],
        "headRefName": os.environ["FX_HEAD_REF"],
        "body": os.environ.get("FX_BODY", ""),
    }
    if os.environ.get("FX_GH") == "nobody":
        del pr["body"]
    print(json.dumps(pr))
    sys.exit(0)
if a[:2] == ["api", "graphql"]:
    print("0")
    sys.exit(0)
print("[]")
"""
STUB_DIR = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
(STUB_DIR / "gh").write_text(GH_STUB, encoding="utf-8")
(STUB_DIR / "gh").chmod(0o755)

MERGE = "gh pr merge 7 --repo %s --rebase --auto" % GH_REPO

CASES = [
    # (name, command, FX_BODY or None for an unreadable body, expected verdict)
    ("open boxes and no Operational-Reason", MERGE, "Plan: %s" % PLAN_OPEN, "plan"),
    (
        "open boxes with an Operational-Reason",
        MERGE,
        "Plan: %s\nOperational-Reason: the last box is a live run after merge" % PLAN_OPEN,
        "past",
    ),
    ("every box ticked", MERGE, "Prose first.\n\n**Plan:** `%s`" % PLAN_DONE, "past"),
    ("no Plan line and no Operational-Reason", MERGE, "Prose only.", "plan"),
    ("an empty body", MERGE, "", "plan"),
    ("the body cannot be read", MERGE, None, "plan"),
    (
        "two plans and no Operational-Reason",
        MERGE,
        "Plan: %s\nPlan: %s" % (PLAN_DONE, PLAN_OPEN),
        "plan",
    ),
    (
        "two plans with an Operational-Reason",
        MERGE,
        "Plan: %s, %s\nOperational-Reason: #591 finishes as-is" % (PLAN_DONE, PLAN_OPEN),
        "past",
    ),
    ("a Plan line naming no plan path", MERGE, "Plan: the one about merges", "plan"),
    ("a plan that does not exist", MERGE, "Plan: agent/plans/PLAN-fx-missing.md", "plan"),
    (
        "an immediate merge is judged too",
        "gh pr merge 7 --repo %s --rebase" % GH_REPO,
        "Plan: %s" % PLAN_OPEN,
        "plan",
    ),
    # A submodule PR names no plan; the gate is the console PR's.
    (
        "a submodule PR is not plan-gated",
        "gh pr merge 7 --repo %s --rebase --auto" % RENET_REPO,
        "",
        "past",
    ),
]


def run(command, body):
    env = dict(
        os.environ,
        PATH="%s:%s" % (STUB_DIR, os.environ["PATH"]),
        CLAUDE_PROJECT_DIR=str(CHECKOUT),
        FX_HEAD_REF=BRANCH,
    )
    if body is None:
        env["FX_GH"] = "nobody"
    else:
        env["FX_BODY"] = body
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(CHECKOUT)}
        ),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stderr


fails = 0
verdicts = set()
for name, command, body, want in CASES:
    rc, err = run(command, body)
    got = "plan" if (rc != 0 and PLAN_MARK in err) else "past"
    verdicts.add(got)
    ok = got == want
    fails += not ok
    print("%-60s want=%-5s got=%-5s %s" % (name, want, got, "ok" if ok else "*** FAIL ***"))
    if not ok:
        print("    rc=%d stderr: %s" % (rc, err.strip().splitlines()[:3]))

print()
# ANTI-VACUITY: a gate that answered one way on every input compared against a constant.
if len(verdicts) < 2:
    print(
        "*** FAIL *** every case got %s: the suite compared the guard against a constant" % verdicts
    )
    fails += 1
print("%d case(s)" % len(CASES))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
