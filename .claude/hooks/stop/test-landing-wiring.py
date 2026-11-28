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


_HERE = _REAL.parent


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
    # The lease landed and `worktree gc` removed its tree, so only its record stays: the hook's own `lease_landed` reads True and the landing stop is free of it, not only a unit test's injected `landed()` (review 62abd0bd.2).
    records = w.fix.proj / ".git" / "rediacc-worktrees"
    records.mkdir(exist_ok=True)
    landed_record = records / "fix-ci-1.json"
    landed_record.write_text(
        json.dumps(
            {"id": "fix-ci-1", "path": str(w.fix.proj / ".claude" / "worktrees" / "fix-ci-1")}
        ),
        encoding="utf-8",
    )
    got = w.stop(w.landing)
    out.append(("handover lease landed: the landing stop is free of it", HO_LAND in got.out, False))
    landed_record.unlink()

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
    # Its own level, not whatever an earlier step left: `high`, the fixture's fail-safe default, where the advisory queue delivers `landing-behind` (at `quiet` it does not, review 838eb2d2.1).
    w.effort("high")
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
            "merged landing: the landing tree's own stop never says LANDING MERGED",
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
        "a landed lease never clears the land block",
        handover_cases,
        [
            (
                "hooks/stop/wl_handover.py",
                "            if state is True:\n                continue\n",
                "",
            )
        ],
    ),
    (
        "the behind report is never queued",
        stack_cases,
        [(CHECKS_REL, '"landing-behind", _ls_report, 1', '"landing-behind", "", 1')],
    ),
)


def stop1_review_cases(check):
    """CL-W-HOOKS-STOP-1 review findings (round 40): one control per fix, each red on the shape it replaced. Every case drives the real function with only its outside seams replaced, each restored in a `finally`."""
    import atexit
    import contextlib
    import datetime
    import tempfile
    import types

    # Each hook module is named by its suffix, because the generated doc registry attributes a module to the first test file whose text names it, and this file is not their owner.
    def hook(suffix):
        return importlib.import_module("wl_" + suffix)

    wl_ci_mod = hook("ci")
    wl_core_mod = hook("core")
    gh_mod = hook("gh")
    git_mod = hook("git")
    hints_mod = hook("hints")
    wl_hr_mod = hook("hookreport")
    wl_lr_mod = hook("longred")
    worklist = importlib.import_module("work" + "list")

    # worklist binds the CLI verbs module to its sibling modules at import, so the verbs are only usable through its instance.
    wl_cli_mod = worklist.CLI
    s1_scratch = pathlib.Path(tempfile.mkdtemp(prefix="stop1-review-"))
    atexit.register(shutil.rmtree, s1_scratch, True)
    _case = [0]

    def scratch():
        _case[0] += 1
        d = s1_scratch / ("case%d" % _case[0])
        d.mkdir()
        return d

    @contextlib.contextmanager
    def swapped(obj, **attrs):
        saved = {k: getattr(obj, k) for k in attrs}
        for k, v in attrs.items():
            setattr(obj, k, v)
        try:
            yield
        finally:
            for k, v in saved.items():
                setattr(obj, k, v)

    # ---- ci: 91ecf84b.2, a stale diagnoser failure is not lent to a stubbed loader ---------------------
    wl_ci_mod._DIAGNOSE_ERROR[0] = "RuntimeError: from an earlier call"
    gate = {"run": 7, "cancelled": [{"run": 7}]}
    with swapped(wl_ci_mod, _load_diagnose=lambda: None):
        cause = wl_ci_mod.ci_cancel_cause(s1_scratch, {"owner": "o", "name": "n"}, gate)
    check(
        "stale diagnoser error: a loader that returns None reads as `unknown`",
        cause["kind"],
        "unknown",
    )
    wl_ci_mod._DIAGNOSE_ERROR[0] = ""

    # ---- ci: 65dcaec1.3 and b74a99a2.4, a ledger failure is named, not swallowed ---------------------------

    info: dict[str, object] = {"pr": 5, "contexts": []}

    def boom(*_a, **_k):
        raise RuntimeError("ledger exploded")

    with swapped(wl_lr_mod, read_rows=boom):
        got = wl_ci_mod.ci_longred(s1_scratch, info, "t" * 40, [])
    check("ci_longred failure: returns None", got, None)
    check(
        "ci_longred failure: the line names the error",
        "RuntimeError: ledger exploded" in str(info.get("longred", "")),
        True,
    )

    # ---- ci: c64cf479.1, a failed job or log read holds the round back -------------------------------------
    job_key = "1001"

    class Fetch:
        def __init__(self, job):
            self.job = job

        def json(self, _path):
            return (self.job, "") if self.job is not None else (None, "HTTP 502")

    def split_with(job, log):
        diag = types.SimpleNamespace(
            DOWNSTREAM_JOBS=(),
            GhFetcher=lambda *_a, **_k: Fetch(job),
            job_log=lambda *_a, **_k: (log, "" if log is not None else "HTTP 502"),
        )
        row = {"name": "Quality / Branch", "job": job_key}
        with swapped(wl_ci_mod, carried_at=lambda _r, _t: ({"check:x": ["K"]}, "")):
            wl_ci_mod.ci_carry_split(
                s1_scratch,
                {"owner": "o", "name": "n"},
                "t" * 40,
                [row],
                {},
                diag=diag,
                fetch=Fetch(job),
            )
        return row

    row = split_with(None, None)
    check("job read failed: the category is pending", row.get("category_pending"), True)
    row = split_with({"status": "completed"}, None)
    check("log read failed: the category is pending", row.get("category_pending"), True)
    check("log read failed: the carry stays unreadable", row["carry"]["verdict"], "unreadable")

    # ---- ci: b74a99a2.7, carried reds do not reach the long-red ledger as reds -----------------------------
    seen = []
    red = {
        "name": "Quality / Branch",
        "job": job_key,
        "carry": {"verdict": "carried", "keys": ["K"]},
    }
    base = scratch()
    with swapped(
        wl_ci_mod,
        ci_rollup=lambda *_a, **_k: (
            "ok",
            {"pr": 5, "sha": "t" * 40, "contexts": [], "owner": "o", "name": "n"},
        ),
        ci_classify=lambda _i: (False, [dict(red)], []),
        ci_watch_armed=lambda *_a, **_k: None,
        ci_steps=lambda *_a, **_k: None,
        ci_carry_split=lambda _r, _i, _t, _h, _s: ([], [dict(red)]),
        _ci_cache_write=lambda *_a, **_k: None,
        _git=lambda _r, *a: "t" * 40 if a[:1] == ("rev-parse",) else "",
        ci_longred=lambda _r, _i, _t, rows, **_k: seen.append(list(rows)),
    ):
        state, _detail = wl_ci_mod.ci_trouble(
            base, base / "wl.md", "deadbeef-test", [], "", ref="pub", owned=True
        )
    check("carried-only head: ci_trouble reads `carried`", state, "carried")
    check("carried-only head: ci_longred is handed no red rows", seen, [[]])

    # ---- core: 7f32cb0e.3 and 5f716ec0.2, the landing-record memo ------------------------------------------
    repo = scratch()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    dirs = wl_core_mod._git_dirs(repo)
    record = dirs[1] / wl_core_mod.LANDING_RECORD_NAME
    record.write_text("aaaa", encoding="utf-8")
    calls = []

    class Policy:
        @staticmethod
        def read_landing_record(tree):
            calls.append(tree)
            return ({"path": str(tree), "branch": "b"}, "")

    wl_core_mod._LANDING_READS.clear()
    with swapped(wl_core_mod, _commit_policy=lambda: Policy):
        wl_core_mod.read_landing_record(repo)
        wl_core_mod.read_landing_record(repo)
        check("memo: an unchanged record is read once", len(calls), 1)
        stamp = record.stat()
        record.unlink()
        record.write_text("bbbb", encoding="utf-8")
        os.utime(record, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        wl_core_mod.read_landing_record(repo)
        check("memo: a same-size rewrite with the old mtime is read again", len(calls), 2)
        # 76143e8e.1: each remaining key component alone moves the key. A chmod changes only ctime (same inode, size and mtime); a new file in `.git` changes only the `.git` entry's mtime.
        os.chmod(record, 0o600 if (record.stat().st_mode & 0o777) != 0o600 else 0o640)
        wl_core_mod.read_landing_record(repo)
        check("memo: a ctime-only change is read again", len(calls), 3)
        wl_core_mod.read_landing_record(repo)
        check("memo: CONTROL, with nothing moved the record is not read again", len(calls), 3)
        dot_git = repo / ".git"
        dot_before = dot_git.stat()
        (dot_git / "probe-file").write_text("x", encoding="utf-8")
        os.utime(dot_git, ns=(dot_before.st_atime_ns, dot_before.st_mtime_ns + 5_000_000_000))
        wl_core_mod.read_landing_record(repo)
        check("memo: a changed `.git` entry is read again", len(calls), 4)
        sub = s1_scratch / "link-to-repo"
        sub.symlink_to(repo)
        wl_core_mod.read_landing_record(sub)
        check("memo: another tree string over the same git dir is its own entry", len(calls), 5)

        def broken():
            raise RuntimeError("policy exploded")

    wl_core_mod._LANDING_READS.clear()
    with swapped(wl_core_mod, _commit_policy=broken):
        rec, why = wl_core_mod.read_landing_record(repo)
    check("commit_policy raising a non-OSError binds nothing", rec, None)
    check(
        "commit_policy raising a non-OSError names itself",
        "RuntimeError: policy exploded" in why,
        True,
    )
    wl_core_mod._LANDING_READS.clear()

    # ---- core: 9649ce27.1, a None stderr cannot change the exit code ---------------------------------------
    prefix = "wl_"
    probe = "import sys\nsys.modules[%r] = None\nsys.path.insert(0, %r)\nimport %s\n" % (
        prefix + "resprofile",
        str(_HERE),
        prefix + "core",
    )

    def _close_stderr():
        os.close(2)

    proc = subprocess.run(
        [sys.executable, "-c", probe],
        stdout=subprocess.PIPE,
        preexec_fn=_close_stderr,
        check=False,
    )
    check("stderr closed at startup: importing wl_core still exits 0", proc.returncode, 0)

    # ---- gh_mod: 5f716ec0.1, no os.getuid ----------------------------------------------------------------------
    cache = scratch() / "c.json"
    cache.write_text('{"a": 1}', encoding="utf-8")
    real_getuid = os.getuid
    del os.getuid
    try:
        got = gh_mod.cache_load(cache)
    finally:
        os.getuid = real_getuid
    check("cache_load without os.getuid reads the file", got, {"a": 1})
    check(
        "cache_load of a missing file without owner info is None",
        gh_mod.cache_load(scratch() / "nope"),
        None,
    )

    # ---- git_mod: e96e54fc.2, the documented fail-open on a git that cannot answer -----------------------------
    with swapped(git_mod, run_git=lambda *_a, **_k: (1, "", "fatal")):
        check(
            "operation_in_progress: a git error is no operation",
            git_mod.operation_in_progress(s1_scratch),
            "",
        )
    with swapped(git_mod, run_git=lambda *_a, **_k: (0, str(repo / ".git"), "")):
        (repo / ".git" / "MERGE_HEAD").write_text("x", encoding="utf-8")
        check(
            "operation_in_progress: control, a MERGE_HEAD reads as merge",
            git_mod.operation_in_progress(repo),
            "merge",
        )

    # ---- hints_mod: 06db238d.1, a future or impossible plan beside a real one ----------------------------------
    root = scratch()
    plans = root / "agent" / "plans"
    plans.mkdir(parents=True)
    for name in ("20260101", "20991231", "20261340"):
        (plans / ("PLAN-lessons-%s.md" % name)).write_text(
            "# plan\n\n- [ ] L1 first box\n", encoding="utf-8"
        )
    today = datetime.date(2026, 1, 20)
    check(
        "newest_lessons_plan skips future and impossible dates",
        hints_mod.newest_lessons_plan(root, today)[0],
        "20260101",
    )
    text = hints_mod.weekly_block(root, root / "wl.md", "deadbeef-test", today)
    check("weekly_block names the real plan", "PLAN-lessons-20260101.md" in text, True)
    check("weekly_block counts days from the real plan", "19 days old" in text, True)
    check("weekly_block never names the future plan", "20991231" in text, False)

    # ---- hookreport: 19df54c9.*, a0c83ac9.3 ----------------------------------------------------------------

    def ledger_root(rows=3):
        r = scratch()
        live = r.joinpath(*wl_hr_mod.LEDGER_REL)
        live.parent.mkdir(parents=True)
        live.write_text('{"chain": "c"}\n' * rows, encoding="utf-8")
        return r, live

    now_at = datetime.datetime(2026, 11, 26, 12, 0, 0, tzinfo=datetime.UTC)
    r, live = ledger_root()

    def link_gone(*_a, **_k):
        raise FileNotFoundError("a peer rolled it")

    with swapped(os, link=link_gone):
        archive, _deleted = wl_hr_mod.rotate(r, max_bytes=1, now=now_at)
    check("rotate: a peer's rotation between stat and link is no crash", archive, None)

    r, live = ledger_root()

    def link_unsupported(*_a, **_k):
        raise OSError(1, "Operation not permitted")

    with swapped(os, link=link_unsupported):
        archive, _deleted = wl_hr_mod.rotate(r, max_bytes=1, now=now_at)
    check(
        "rotate: no hard links falls back to a rename",
        archive is not None and archive.exists(),
        True,
    )
    check("rotate: the rename leaves no live ledger", live.exists(), False)

    r, live = ledger_root()
    real_unlink = pathlib.Path.unlink

    def unlink_refuses_live(self, *a, **k):
        if self.name == "chains.jsonl":
            raise PermissionError(13, "nope")
        return real_unlink(self, *a, **k)

    refused = False
    with swapped(pathlib.Path, unlink=unlink_refuses_live):
        try:
            wl_hr_mod.rotate(r, max_bytes=1, now=now_at)
        except wl_hr_mod.ReportError:
            refused = True
    check("rotate: a live unlink failure is refused", refused, True)
    check(
        "rotate: the link is undone, the rows are not doubled",
        sorted(p.name for p in live.parent.glob("chains*.jsonl")),
        ["chains.jsonl"],
    )

    check(
        "rotate docstring describes link and unlink",
        "LINK AND UNLINK" in wl_hr_mod.rotate.__doc__,
        True,
    )

    r, live = ledger_root()
    flip = [0]

    def unstable_paths(_root=None):
        flip[0] += 1
        return [live, live.with_name("chains-%d.jsonl" % flip[0])]

    unstable = False
    with swapped(wl_hr_mod, ledger_paths=unstable_paths):
        try:
            wl_hr_mod.read_ledger(r)
        except wl_hr_mod.ReportError:
            unstable = True
    check("read_ledger: three disagreeing passes is an error, not a silent partial", unstable, True)
    check(
        "read_ledger: control, a stable ledger reads its rows",
        len(wl_hr_mod.read_ledger(ledger_root(4)[0])),
        4,
    )

    r = scratch()
    rec_dir = r.joinpath(*wl_hr_mod.RECEIPTS_REL)
    rec_dir.mkdir(parents=True)
    (rec_dir / "ok.json").write_text("{}", encoding="utf-8")
    (rec_dir / "bad.json").write_text("{not json", encoding="utf-8")
    skipped: list[str] = []
    got = wl_hr_mod.read_receipts(r, skipped)
    check("read_receipts: the parsed receipt is kept", len(got), 1)
    check("read_receipts: the corrupt one is named", skipped, ["bad.json"])
    text = wl_hr_mod.report(r, rows=[], trap_base=scratch())
    check(
        "report: the dropped receipt shows in the text",
        "bad.json" in text and "did not read or parse" in text,
        True,
    )

    # ---- cli: 190c8ade.2, an arm on a lease whose hold cannot be ruled out ---------------------------------

    class RefusedError(Exception):
        pass

    def die(msg):
        raise RefusedError(msg)

    with swapped(wl_cli_mod.C, _git_dirs=lambda _p: None):
        why = ""
        try:
            wl_cli_mod._arm_one(
                s1_scratch / "wl.md",
                s1_scratch,
                types.SimpleNamespace(by_id={}, items=[]),
                "deadbeef-test",
                {"id": "abcd1234", "origin": "cli", "state": " "},
                ["PUSHED:head"],
                "",
                "true",
                "L1",
                "",
                die,
            )
        except RefusedError as exc:
            why = str(exc)
        except Exception as exc:  # the old shape went on to write the arm
            why = "UNEXPECTED %s: %s" % (type(exc).__name__, exc)
    check("--arm --lease with unresolvable git dirs is refused", "cannot be checked" in why, True)

    # ---- cli: 190c8ade.3, a survey draft outside the survey's directory and the repo -----------------------
    proj = scratch()
    surveys = scratch()
    survey = surveys / "survey.md"
    inside = surveys / "draft.md"
    inside.write_text("brief\n", encoding="utf-8")
    survey_text = (
        "## 10. Armed\n\n| blocker | dependent sigs | trigger | brief draft path |\n|---|---|---|---|\n"
        "| AA1 | 26dc6529 | `PUSHED:head` | %s |\n"
    )

    def survey_run(draft):
        survey.write_text(survey_text % draft, encoding="utf-8")
        err = []

        def wrote(*_a, **_k):
            err.append("WROTE")
            return "abcd1234"

        fold = types.SimpleNamespace(by_id={}, items=[])
        with (
            swapped(
                wl_cli_mod,
                _identity_or_die=lambda _me, _die: None,
            ),
            swapped(
                wl_cli_mod.C,
                project_start=lambda: proj,
                worklist_for=lambda _s: proj / "wl.md",
                project_root=lambda _s: proj,
                resolve_session_id=lambda: "deadbeef-test",
            ),
            swapped(wl_cli_mod.S, load=lambda *_a, **_k: fold),
            swapped(wl_cli_mod.S, add_item=wrote),
        ):
            try:
                wl_cli_mod._armed_cli(["--arm-from-survey", "deadbeef-test", str(survey)])
            except SystemExit:
                pass
            except Exception as exc:
                err.append("%s: %s" % (type(exc).__name__, exc))
        return err

    outside = survey_run("/etc/hostname")
    check(
        "survey draft outside the survey dir and repo: nothing is written",
        "WROTE" in outside,
        False,
    )
    check(
        "survey draft inside the survey dir: control, the row is accepted",
        "WROTE" in survey_run(inside),
        True,
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
    stop1_review_cases(T.check)
    T.exit()


if __name__ == "__main__":
    main()
