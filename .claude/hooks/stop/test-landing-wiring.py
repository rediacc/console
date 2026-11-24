#!/usr/bin/env python3
"""Controls for the two-tree wiring of the real Stop hook (agent/plans/PLAN-two-track-merge-dev.md LT15, LT19).

    python3 .claude/hooks/stop/test-landing-wiring.py

Every case runs the real Stop hook, copied with its effort table into a fixture, over two real trees of one repository: the main checkout on the development branch and a linked landing tree on the PR branch, bound by a landing record in the common git dir. A gh shim answers the PR read per branch, and origin is redirected (`url.<bare>.insteadOf`) to a local bare repository, so the stack's fetch of origin/main reads a planted main.

LT15: `wl_checks.loop_next_text` picks the no-PR-ahead and finish arms through `worklist_messages.loop_next_variant`: the development tree's commits with no PR name the backup push and open none, its finished branch waits on an open landing PR without blocking, and with no landing PR open the merge is offered.
B2 (agent/plans/PLAN-simple-two-tree-loop.md D1): the landing tree's stop names its state machine's step instead (`wl_checks.landing_next_text`): after the merge it watches the release (L-RELEASE), a red Console CI on main is a hotfix (L-HOTFIX), and a green release blocks once with the `cd-done` notice and then idles; the development tree names promote once that release is green.
B7 (D5): the handover contract by tree role: an open stuck handover blocks the development stop and not the landing one, an answer naming a lease moves the block to the landing stop, `done` clears both, a lesson only advises, and a checkout with no record reads none.
LT19: the `landing-stack` FLOOR check blocks the development stop at every effort level while the landing branch is merged and unpromoted; `landing-behind` is advisory; a landing tree's own stop and a checkout with no record read nothing.

Each fire case has a control without the record, and each wiring is run once more against a mutant of the hook copy that must turn its checks red.
"""

import importlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

_REAL = pathlib.Path(__file__).resolve()
_CI = _REAL.parents[3] / ".ci" / "rediacc_ci"
_CLAUDE = _REAL.parents[2]
sys.path[:0] = [str(_CI.parent), str(_CLAUDE), str(_REAL.parent)]


def _by_file(name):
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")
wlfix = importlib.import_module("rediacc_hooks.tests.wlfix")
T = controls.Controls("landing-wiring", floor=30)

PR_BRANCH = "1120-1"
DEV_BRANCH = "1120-2"
OWN = "agent/plans/PLAN-own.md"
NEXT = "agent/plans/PLAN-next.md"
LEVELS = ("quiet", "low", "smart", "high")

GH_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        *'states:[OPEN,MERGED,CLOSED]'*)
            b=$(printf '%%s' "$a" | sed -n 's/.*headRefName:"\\([^"]*\\)".*/\\1/p')
            if [ -f "%(base)s/pr-$b.json" ]; then cat "%(base)s/pr-$b.json"; else echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'; fi
            exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *"pr list"*) echo '[]'; exit 0 ;;
    *"pr view"*mergeCommit*) cat "%(base)s/pr-view.json" 2>/dev/null || echo '{}'; exit 0 ;;
    *"run list"*"--workflow ci.yml"*) cat "%(base)s/run-ci.json" 2>/dev/null || echo '[]'; exit 0 ;;
    *"run list"*"--workflow cd-release-edge.yml"*) cat "%(base)s/run-edge.json" 2>/dev/null || echo '[]'; exit 0 ;;
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""
CI_FRESH = (
    '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,'
    '"lastEditedAt":"2999-01-01T00:00:00Z","updatedAt":"2999-01-01T00:00:00Z"}]}}}}\n'
)
CI_JOB = '{"run_id":30514648812,"run_attempt":1,"steps":[{"name":"Shell format","conclusion":"success"}]}\n'
CI_GREEN = (
    '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,"url":"u",'
    '"commits":{"nodes":[{"commit":{"oid":"deadsha0000","statusCheckRollup":'
    '{"state":"SUCCESS","contexts":{"totalCount":1,"pageInfo":{"hasNextPage":false,'
    '"endCursor":null},"nodes":[{"__typename":"CheckRun","name":"Quality / Static",'
    '"status":"COMPLETED","conclusion":"SUCCESS","databaseId":90784763855,'
    '"detailsUrl":"https://x/job/90784763855","checkSuite":{"workflowRun":'
    '{"databaseId":30514648812}}}]}}}}]}}]}}}}\n'
)


def plan_text(name, opened):
    boxes = "- [x] D0 the ticked %s fixture box\n" % name
    boxes += "".join("- [ ] T%d the open %s fixture box\n" % (i, name) for i in range(opened))
    return (
        "# PLAN: %s fixture\n\nStatus: approved\nOwner: %s\n"
        "Depends-On: no-dep -- a fixture plan that stands alone\n\n## Tasks\n\n%s"
        % (name, wlfix.ME, boxes)
    )


def pr_nodes(*nodes):
    return json.dumps({"data": {"repository": {"pullRequests": {"nodes": list(nodes)}}}}) + "\n"


def node(state, body, number, draft=False):
    return {
        "number": number,
        "state": state,
        "body": body,
        "isDraft": draft,
        "mergedAt": "2026-11-20T10:00:00Z" if state == "MERGED" else None,
        "closedAt": None if state == "OPEN" else "2026-11-20T10:00:00Z",
    }


class World:
    """One fixture: the hook copy, the main checkout on DEV_BRANCH, the landing tree on PR_BRANCH, the bare origin."""

    def __init__(self, tmp, name, mutate=None):
        self.fix = fix = wlfix.Fixture(tmp / name)
        fix.setup()
        fix.brief_now()
        fix.hand_now()
        hooks = fix.base / "claude" / "hooks"
        junk = shutil.ignore_patterns("__pycache__", "state")
        shutil.copytree(wlfix.STOP_DIR, hooks / "stop", ignore=junk)
        shutil.copytree(wlfix.STOP_DIR.parent / "context", hooks / "context", ignore=junk)
        shutil.copytree(
            wlfix.STOP_DIR.parents[1] / "rediacc_hooks", hooks.parent / "rediacc_hooks", ignore=junk
        )
        # The effort table beside the copy: without it every check blocks, and the levels would prove nothing.
        (hooks.parent / "config").mkdir()
        shutil.copy(_CLAUDE / "config" / "effort.json", hooks.parent / "config" / "effort.json")
        (hooks.parents[1] / ".ci").symlink_to(wlfix.STOP_DIR.parents[2] / ".ci")
        for rel, old, new in mutate or ():
            path = hooks.parent / rel
            text = path.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise SystemExit("mutant: %r is not exactly once in %s" % (old, rel))
            path.write_text(text.replace(old, new), encoding="utf-8")
        fix.hook = hooks / "stop" / "worklist.py"

        self.bare = fix.base / "origin.git"
        self.git(fix.base, "init", "-q", "--bare", "-b", "main", self.bare)
        main = fix.proj
        self.git(main, "init", "-q", "-b", "main")
        self.git(main, "remote", "add", "origin", wlfix.FAKE_ORIGIN)
        self.git(main, "config", "url.%s.insteadOf" % self.bare, wlfix.FAKE_ORIGIN)
        plans = main / "agent" / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        (main / OWN).write_text(plan_text("own", 0), encoding="utf-8")
        (main / NEXT).write_text(plan_text("next", 1), encoding="utf-8")
        queue = (plans / "QUEUE.md").read_text(encoding="utf-8")
        (plans / "QUEUE.md").write_text(queue.rstrip("\n") + "\n\n1. %s\n" % NEXT, encoding="utf-8")
        # A /writers-now round of this session now: the Promoted NEXT plan has an open box, and the development tree keeps `writers-now-due` (wl_standdown._BUILD_ONLY), which would otherwise block ahead of the wiring under test for the first hour.
        wn = wlfix.import_wl("wl_writersnow")
        wn.append_round(main, fix.sid, "/tmp/s.md", wn.C.utcnow())
        (main / ".gitignore").write_text("agent/deadbeef/\n.agent/\n", encoding="utf-8")
        (main / "a.txt").write_text("a\n", encoding="utf-8")
        self.git(main, "add", "-A")
        self.git(main, "commit", "-qm", "base")
        self.base_sha = self.git(main, "rev-parse", "HEAD")
        self.git(main, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.git(main, "fetch", "-q", "origin")
        self.git(main, "update-ref", "refs/remotes/origin/pub", self.base_sha)
        self.git(main, "branch", PR_BRANCH)
        self.landing = pathlib.Path(os.path.realpath(fix.base)) / "console-landing"
        self.git(main, "worktree", "add", "-q", self.landing, PR_BRANCH)
        self.git(main, "switch", "-q", "-c", DEV_BRANCH)
        common = pathlib.Path(self.git(main, "rev-parse", "--git-common-dir"))
        self.record = (common if common.is_absolute() else main / common) / "rediacc-landing.json"
        (fix.base / "ci-fresh.json").write_text(CI_FRESH, encoding="utf-8")
        (fix.base / "ci-job.json").write_text(CI_JOB, encoding="utf-8")
        (fix.base / "ci-rollup.json").write_text(CI_GREEN, encoding="utf-8")
        shim = fix.base / "binonly" / "gh"
        shim.write_text(GH_SHIM % {"base": fix.base}, encoding="utf-8")
        shim.chmod(0o755)
        self.prs({})

    @staticmethod
    def git(cwd, *args):
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *map(str, args)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            raise SystemExit("fixture: git %s: %s" % (" ".join(map(str, args)), done.stderr))
        return done.stdout.strip()

    def bind(self, on=True):
        if on:
            self.record.write_text(
                json.dumps({"path": str(self.landing), "branch": PR_BRANCH}), encoding="utf-8"
            )
        else:
            self.record.unlink(missing_ok=True)

    def prs(self, by_branch):
        for old in self.fix.base.glob("pr-*.json"):
            old.unlink()
        for branch, nodes in by_branch.items():
            (self.fix.base / ("pr-%s.json" % branch)).write_text(pr_nodes(*nodes), encoding="utf-8")
        for sidecar in self.fix.base.rglob("*.prlink-*"):
            sidecar.unlink()

    def release(self, sha="", ci="", edge=""):
        """Plant the merged PR's merge commit and the main runs of Console CI and the edge deploy at it ("" leaves a workflow with no run)."""
        base = self.fix.base
        (base / "pr-view.json").write_text(
            json.dumps({"mergeCommit": {"oid": sha}} if sha else {}), encoding="utf-8"
        )
        for name, conclusion in (("run-ci.json", ci), ("run-edge.json", edge)):
            rows = []
            if conclusion:
                rows.append(
                    {
                        "databaseId": 4242,
                        "headSha": sha,
                        "status": "completed",
                        "conclusion": conclusion,
                        "createdAt": "2026-11-20T10:05:00Z",
                    }
                )
            (base / name).write_text(json.dumps(rows), encoding="utf-8")
        # A planted release is a new world: the release sidecar (wl_prscope.RELEASE_VERDICT_TTL_S) must not answer for the previous one.
        (base / "tmp" / "claude-worklist" / ".landing-release.json").unlink(missing_ok=True)

    def effort(self, level):
        self.fix.settings(effort=level)

    def settle(self):
        """After one priming stop, commit the tracked QUEUE.md edits `effort` and the stop's own in-flight render (`wl_planqueue.refresh_inflight`) leave behind: promote's dirty preflight refuses a tracked non-record change, and the stop then stands the block down to a peer-dirt advisory (agent/plans/PLAN-stop-hook-retro-20261123.md D2), so a clean tree is what lets the block stand."""
        self.stop(self.fix.proj)
        self.git(self.fix.proj, "add", "--", "agent/plans/QUEUE.md")
        self.git(self.fix.proj, "commit", "-q", "--allow-empty", "-m", "settle effort")

    def commit(self, tree, name):
        (tree / name).write_text(name + "\n", encoding="utf-8")
        self.git(tree, "add", "--", name)
        self.git(tree, "commit", "-qm", name)
        return self.git(tree, "rev-parse", "HEAD")

    def stop(self, tree):
        fix = self.fix
        for stale in list(fix.base.rglob("*.cistate-*")) + list(fix.base.rglob("*.blocks-*")):
            stale.unlink()
        payload = json.dumps(
            {
                "session_id": fix.sid,
                "cwd": str(tree),
                "last_assistant_message": "working\n\n## Remaining\n- nothing",
                "session_crons": [],
                "background_tasks": wlfix.with_waker([], fix.waker),
            }
        )
        env = dict(fix.env)
        env.update(
            PATH="%s:%s" % (fix.base / "binonly", fix.env.get("PATH", "")),
            TMPDIR=str(fix.base / "tmp"),
            CLAUDE_PROJECT_DIR=str(tree),
            WORKLIST_TASKS_DIR=str(fix.base / "tasks"),
            WORKLIST_JUDGE="off",
            GITHUB_ACTIONS="",
            GIT_TERMINAL_PROMPT="0",
        )
        return fix.python([], stdin=payload, env=env)

    def blocked(self, got, needle):
        """True when the stop blocked on `needle`'s check (its blocklog row names the key) and says `needle`; a queued advisory's first line in the reason is no block."""
        if got.decision != "block" or needle not in got.out:
            return False
        logs = sorted(self.fix.base.rglob("*.blocklog-*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not logs:
            return False
        rows = [json.loads(x) for x in logs[-1].read_text(encoding="utf-8").splitlines() if x]
        return KEY_OF[needle] in {rows[-1].get("key"), *(rows[-1].get("named") or ())}


# ---- LT15: the loop-next arms ------------------------------------------------
PROMOTE = "worktree landing --promote"
TODAY_MERGED = "git switch main && git pull --ff-only"
DRAFT = "The development tree opens none"
OPEN_IT = "has no PR. Open it:"
WAIT = "never run /pr-merge here"
MERGE = "The finish condition is the merge: run /pr-merge"
RELEASE = "LANDING L-RELEASE:"
HOTFIX = "LANDING L-HOTFIX:"
IDLE = "LANDING L-IDLE:"
CD_DONE = "CD DONE:"


def loopnext_cases(tmp, tag, mutate=None):
    """[(label, got, want)] for the LT15 arms over one world."""
    w = World(tmp, "loopnext-%s" % tag, mutate)
    out = []

    # The landing tree after its PR merged: the release watch, not the branch cut (B2, D1 L-RELEASE).
    w.prs({PR_BRANCH: [node("MERGED", "Plan: %s\n" % OWN, 7)]})
    w.release("feedface0001")
    w.bind()
    got = w.stop(w.landing)
    out.append(("landing merged: the release watch blocks", w.blocked(got, RELEASE), True))
    out.append(("landing merged: no branch cut", TODAY_MERGED in got.out, False))
    out.append(("landing merged, release pending: no cd-done", CD_DONE in got.out, False))
    # Console CI red on main at the merged sha: the hotfix (D1 L-HOTFIX).
    w.release("feedface0001", ci="failure", edge="success")
    got = w.stop(w.landing)
    out.append(("landing merged, main red: the hotfix blocks", w.blocked(got, HOTFIX), True))
    # The release green: one blocking stop carries the cd-done notice, then the tree idles.
    w.release("feedface0001", ci="success", edge="success")
    got = w.stop(w.landing)
    out.append(("landing released: the cd-done notice blocks once", w.blocked(got, CD_DONE), True))
    got = w.stop(w.landing)
    out.append(("landing released: the next stop idles unblocked", w.blocked(got, IDLE), False))
    out.append(("landing released: the next stop names no cd-done", CD_DONE in got.out, False))
    # The development tree reads the same green release and names promote.
    got = w.stop(w.fix.proj)
    out.append(("development, landing released: promote is named", CD_DONE in got.out, True))
    w.release("feedface0001", ci="success")
    got = w.stop(w.fix.proj)
    out.append(
        ("CONTROL development, edge deploy pending: no promote notice", CD_DONE in got.out, False)
    )
    w.release("feedface0001", ci="success", edge="success")
    w.bind(False)
    got = w.stop(w.landing)
    out.append(
        ("CONTROL landing merged, no record: today's cut", w.blocked(got, TODAY_MERGED), True)
    )
    out.append(("CONTROL landing merged, no record: no promotion", PROMOTE in got.out, False))
    out.append(
        ("CONTROL landing merged, no record: no landing step", "LANDING L-" in got.out, False)
    )

    # The development tree with a commit and no PR while the landing PR is open: a backup push, no PR.
    w.commit(w.fix.proj, "d.txt")
    w.prs({PR_BRANCH: [node("OPEN", "Plan: %s\n" % OWN, 7)]})
    w.bind()
    got = w.stop(w.fix.proj)
    out.append(("development no PR: the backup text blocks", w.blocked(got, DRAFT), True))
    w.bind(False)
    got = w.stop(w.fix.proj)
    out.append(
        ("CONTROL development no PR, no record: today's text", w.blocked(got, OPEN_IT), True)
    )
    out.append(("CONTROL development no PR, no record: no backup note", DRAFT in got.out, False))

    # The development tree's finished draft: it waits on the open landing PR and never blocks on it.
    w.prs(
        {
            PR_BRANCH: [node("OPEN", "Plan: %s\n" % OWN, 7)],
            DEV_BRANCH: [node("OPEN", "Plan: %s\n" % OWN, 8, draft=True)],
        }
    )
    w.bind()
    got = w.stop(w.fix.proj)
    out.append(("development finish: the wait is said", WAIT in got.out, True))
    out.append(("development finish: the wait never blocks", w.blocked(got, WAIT), False))
    out.append(("development finish: no merge offer", MERGE in got.out, False))
    # No landing PR open: the draft is the one to merge.
    w.prs({DEV_BRANCH: [node("OPEN", "Plan: %s\n" % OWN, 8, draft=True)]})
    got = w.stop(w.fix.proj)
    out.append(
        ("development finish, landing closed: the merge blocks", w.blocked(got, MERGE), True)
    )
    w.bind(False)
    got = w.stop(w.fix.proj)
    out.append(
        ("CONTROL development finish, no record: the merge blocks", w.blocked(got, MERGE), True)
    )
    out.append(("CONTROL development finish, no record: no wait", WAIT in got.out, False))
    return out


# ---- LT19: the landing stack -------------------------------------------------
STACK_MERGED = "LANDING MERGED (blocks from effort low; an advisory at quiet)"
STACK_BEHIND = "LANDING AHEAD"
STACK_PENDING = "LANDING MERGED, RELEASE PENDING"
# B7: the handover verdicts' first words (wl_handover).
HO_OPEN = "FROM THE LANDING TREE"
HO_LAND = "ANSWERED WITH LEASE"
HO_LESSON = "HANDOVER LESSON"


KEY_OF = {
    **dict.fromkeys(
        (PROMOTE, TODAY_MERGED, DRAFT, OPEN_IT, WAIT, MERGE, RELEASE, HOTFIX, IDLE, CD_DONE),
        "loop-next",
    ),
    HO_OPEN: "handover-open",
    HO_LAND: "handover-land",
    HO_LESSON: "handover-lesson",
    STACK_MERGED: "landing-stack",
    STACK_BEHIND: "landing-behind",
    STACK_PENDING: "landing-behind",
}


# ---- B7: the handover contract -------------------------------------------------


def handover_cases(tmp, tag, mutate=None):
    """[(label, got, want)] for the handover verdicts of each tree (wl_handover)."""
    out = []
    w = World(tmp, "handover-%s" % tag, mutate)
    w.prs({PR_BRANCH: [node("OPEN", "Plan: %s\n" % OWN, 7)]})
    w.bind()
    made = w.fix.cli("--handover", wlfix.ME, "stuck", "Quality / Pytest (3/3)", "rounds 4 5 6")
    out.append(("handover: the verb records it", made.rc, 0))
    hid = made.out.split("#", 1)[1][:8] if "#" in made.out else "?"
    got = w.stop(w.fix.proj)
    out.append(("handover stuck: the development stop blocks", w.blocked(got, HO_OPEN), True))
    got = w.stop(w.landing)
    out.append(("handover stuck: the landing stop does not", HO_OPEN in got.out, False))

    w.fix.cli("--handover-answer", wlfix.ME, hid, "lease:fix-ci-1")
    got = w.stop(w.landing)
    out.append(
        ("handover lease: the landing stop blocks on landing it", w.blocked(got, HO_LAND), True)
    )
    got = w.stop(w.fix.proj)
    out.append(("handover lease: the development stop is free of it", HO_OPEN in got.out, False))

    w.fix.cli("--handover-answer", wlfix.ME, hid, "done")
    got = w.stop(w.landing)
    out.append(("handover done: the landing stop is free of it", HO_LAND in got.out, False))

    w.fix.cli("--handover", wlfix.ME, "lesson", "Quality / Static", "a CI-only failure")
    got = w.stop(w.fix.proj)
    out.append(("handover lesson: named on the development stop", HO_LESSON in got.out, True))
    out.append(("handover lesson: never a block", w.blocked(got, HO_LESSON), False))

    w.fix.cli("--handover", wlfix.ME, "churn", "Quality / Static", "two regressions in four rounds")
    w.bind(False)
    got = w.stop(w.fix.proj)
    out.append(("CONTROL handover, no record: no role reads none", HO_OPEN in got.out, False))
    return out


def stack_cases(tmp, tag, mutate=None):
    """[(label, got, want)] for the LT19 checks."""
    out = []
    # The landing branch holds one commit whose copy sits on origin/main; the development branch lacks it.
    w = World(tmp, "stack-merged-%s" % tag, mutate)
    sha = w.commit(w.landing, "l.txt")
    tree = w.git(w.landing, "rev-parse", "%s^{tree}" % sha)
    copy = w.git(w.fix.proj, "commit-tree", tree, "-p", w.base_sha, "-m", "l.txt (rebase-merged)")
    w.git(w.fix.proj, "push", "-q", "origin", "%s:refs/heads/main" % copy)
    w.prs({PR_BRANCH: [node("MERGED", "Plan: %s\n" % OWN, 7)]})
    w.bind()
    # The release at the merged sha still in flight: reported, never blocked on (agent/plans/PLAN-simple-two-tree-loop.md D3).
    w.release("feedface0001", ci="success")
    got = w.stop(w.fix.proj)
    out.append(("merged landing, release pending: no block", w.blocked(got, STACK_MERGED), False))
    out.append(("merged landing, release pending: reported", STACK_PENDING in got.out, True))
    w.release("feedface0001", ci="success", edge="success")
    # Not on the FLOOR (operator ruling 2026-11-22: "effort: quiet" must let the stop through): quiet stands it down to an
    # advisory, every other level blocks.
    # The tree is clean (every [writer] box ticked, no dirt), so promote would proceed and the block stands.
    for level in LEVELS:
        w.effort(level)
        w.settle()
        got = w.stop(w.fix.proj)
        out.append(
            (
                "merged landing at %s: the development stop %s"
                % (level, "stands down" if level == "quiet" else "blocks"),
                w.blocked(got, STACK_MERGED),
                level != "quiet",
            )
        )
    w.effort("low")
    w.settle()
    got = w.stop(w.fix.proj)
    out.append(
        (
            "CONTROL merged landing, effort low: the development stop does say LANDING MERGED",
            "LANDING MERGED" in got.out,
            True,
        )
    )
    got = w.stop(w.landing)
    out.append(
        (
            "merged landing: the landing tree's own stop reads no stack",
            "LANDING MERGED" in got.out,
            False,
        )
    )
    w.bind(False)
    got = w.stop(w.fix.proj)
    out.append(("CONTROL merged, no record: silent", "LANDING " in got.out, False))

    b = World(tmp, "stack-behind-%s" % tag, mutate)
    b.commit(b.landing, "l.txt")
    b.prs({PR_BRANCH: [node("OPEN", "Plan: %s\n" % OWN, 7)]})
    b.bind()
    got = b.stop(b.fix.proj)
    out.append(("behind: the advisory is said", STACK_BEHIND in got.out, True))
    out.append(("behind: it never blocks", b.blocked(got, STACK_BEHIND), False))
    out.append(("behind: no merged block", STACK_MERGED in got.out, False))
    b.bind(False)
    got = b.stop(b.fix.proj)
    out.append(("CONTROL behind, no record: silent", STACK_BEHIND in got.out, False))
    return out


CHECKS_REL = "hooks/stop/wl_checks.py"
MUTANTS = (
    (
        "a blocking handover only advises",
        handover_cases,
        [
            (
                CHECKS_REL,
                '                    vadd("handover-open", False, _ho_text)\n',
                "                    pass\n",
            )
        ],
    ),
    (
        "the landing tree runs the queue loop's arms",
        loopnext_cases,
        [
            (
                CHECKS_REL,
                '_landing_tree = getattr(_loop, "role", "") == wl_prscope.LANDING',
                "_landing_tree = False",
            )
        ],
    ),
    (
        "the release reads green without the edge deploy",
        loopnext_cases,
        [
            (
                "hooks/stop/wl_prscope.py",
                "    pend = [n for n, v, _r in verdicts if v != CI_GREEN]",
                "    pend = [n for n, v, _r in verdicts[:1] if v != CI_GREEN]",
            )
        ],
    ),
    (
        "the cd-done notice is never latched",
        loopnext_cases,
        [(CHECKS_REL, '        state_doc["landing"] = {"cd_done": step.sha}\n', "")],
    ),
    (
        "the no-PR arm ignores the role",
        loopnext_cases,
        [
            (
                CHECKS_REL,
                "M.loop_next_variant(role, False, landing_open, M.ARM_OPEN)",
                "M.V_LOOP_NEXT_NO_PR_OPEN",
            )
        ],
    ),
    (
        "the finish arm reads no open landing PR",
        loopnext_cases,
        [
            (
                CHECKS_REL,
                "M.loop_next_variant(role, False, landing_open, M.ARM_FINISH)",
                "M.loop_next_variant(role, False, False, M.ARM_FINISH)",
            )
        ],
    ),
    (
        "the loop state reads the mapped root",
        loopnext_cases,
        [
            (
                CHECKS_REL,
                "_loop = wl_prscope.loop_state(own, worklist, session_id)",
                "_loop = wl_prscope.loop_state(root, worklist, session_id)",
            )
        ],
    ),
    (
        "landing-stack blocks from low, not only from smart",
        stack_cases,
        [
            (
                "config/effort.json",
                '"landing-stack": {\n      "block": "low",',
                '"landing-stack": {\n      "block": "smart",',
            ),
        ],
    ),
    (
        "the stack is read from the mapped root",
        stack_cases,
        [
            (
                CHECKS_REL,
                "wl_stack.stack_verdict(\n        own, ",
                "wl_stack.stack_verdict(\n        root, ",
            ),
            (CHECKS_REL, "wl_stack.stack_report(own, ", "wl_stack.stack_report(root, "),
        ],
    ),
    (
        "the merged block ignores the release",
        stack_cases,
        [
            (
                CHECKS_REL,
                "own, released=_ls_released, own_paths=_ls_own",
                "own, released=True, own_paths=_ls_own",
            )
        ],
    ),
    (
        "the behind report is never queued",
        stack_cases,
        [(CHECKS_REL, '"landing-behind", _ls_report, 1', '"landing-behind", "", 1')],
    ),
)


def main():
    tmp = pathlib.Path(runtmp.run_dir("landing-wiring-")).resolve()
    for label, got, want in (
        loopnext_cases(tmp, "real") + stack_cases(tmp, "real") + handover_cases(tmp, "real")
    ):
        T.check(label, got, want)
    for n, (label, runner, mutate) in enumerate(MUTANTS):
        wrong = [c[0] for c in runner(tmp, "mutant%d" % n, mutate) if c[1] != c[2]]
        T.check("MUTANT %s: turns a check red" % label, bool(wrong), True)
    T.exit()


if __name__ == "__main__":
    main()
