"""wl_ci: publish-ref divergence, PR-body freshness, submodule pointer moves, and the v10 open-PR CI-trouble check. Pure movement from worklist.py; every branch here is paid for by an observed failure, so nothing was "simplified" in the extraction."""

import contextlib
import datetime
import hashlib
import importlib.util
import os
import pathlib
import re
import sys
import time
import urllib.parse
from typing import Any

import wl_core as C
import wl_gh
import wl_store as S

_git = C._git


def publish_divergence(root):
    """(state, count, ref) -- has the branch we publish to moved without us?

    OPERATOR'S RULE, "do not trust, verify". This session commits on a LOCAL branch and publishes with `git push origin HEAD:<other-branch>`, so the two names can diverge silently: another session, or a merge on the remote, puts commits on the published ref that local HEAD does not contain, and the next push either fails confusingly or publishes over work nobody looked at.

    The dangerous direction is remote-ahead. Local-ahead is just unpushed work.
    """
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return "unknown", 0, ""
    # The published ref is whatever the PR is on; default to the sibling name the session pushes to, overridable for other setups.
    target = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not target:
        return "unset", 0, ""
    ref = "origin/%s" % target
    if not _git(root, "rev-parse", "--verify", "--quiet", ref):
        return "missing", 0, ref
    n = _git(root, "rev-list", "--count", "%s" % ref, "^HEAD")
    ahead = int(n) if n.isdigit() else 0
    if ahead:
        return "diverged", ahead, ref
    # THE SECOND TRAP, found by a verification agent rather than by reasoning: a LOCAL branch sharing the publish target's name, left behind by an earlier rename. Nothing in the publish flow touches it, so it rots invisibly; the cost lands on whoever checks it out next and pushes from a stale base.
    if _git(root, "rev-parse", "--verify", "--quiet", target):
        behind = _git(root, "rev-list", "--count", ref, "^%s" % target)
        unique = _git(root, "rev-list", "--count", target, "^%s" % ref)
        if behind.isdigit() and int(behind) > 0:
            return "stale-local", int(behind), "%s (local, %s unique)" % (target, unique or "?")
    return "ok", 0, ref


def pr_body_freshness(root, ref=None):
    """(state, detail) -- did we push after the last PR-description edit?

    FAIL FAST TO SAVE A CI ROUND. `Quality / Static` runs a PR-description freshness gate, and the cost of failing it is a full ~55-minute round for a mistake that takes ten seconds to fix. This session has made it twice, both times by treating the body refresh as a separate step instead of part of the push, which its own memory says not to do.

    Scoped to WORKLIST_PUBLISH_REF, so a session that has not opted in pays nothing. When it IS set and the lookup fails, that is reported as a hook-side inability rather than passing quietly.
    """
    # `ref` is a focus-mode PR branch (wl_standdown): the session declared the PR its own, so the opt-in is that declaration.
    target = ref or os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not target:
        return "unset", ""
    tip = _git(root, "log", "-1", "--format=%cI", "origin/%s" % target)
    if not tip:
        return "no-ref", "origin/%s" % target
    # GRAPHQL, NOT `gh pr list --json lastEditedAt`. That field does not exist on `pr list` OR on `pr view` -- both error out and print the valid-field list. This check found that itself on its first run, by reporting the failure as a blind read instead of passing quietly, which is the whole argument for making blindness its own verdict.
    slug = _git(root, "config", "--get", "remote.origin.url")
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", slug or "")
    if not m:
        return "unreadable", "could not derive owner/name from %r" % slug
    query = (
        '{repository(owner:"%s",name:"%s"){pullRequests('
        'headRefName:"%s",states:OPEN,first:1){nodes{number lastEditedAt updatedAt}}}}'
        % (m.group(1), m.group(2), target)
    )
    data, err = wl_gh.call(["api", "graphql", "-f", "query=" + query], cwd=root, timeout=25)
    if data is None:
        return "unreadable", err[-120:]
    try:
        rows = data["data"]["repository"]["pullRequests"]["nodes"]
    except (KeyError, TypeError):
        return "unreadable", "graphql response had no pullRequests.nodes"
    if not rows:
        return "no-pr", target
    pr = rows[0]
    edited = pr.get("lastEditedAt") or pr.get("updatedAt") or ""
    if not edited:
        return "unreadable", "PR carries neither lastEditedAt nor updatedAt"

    def parse(ts):
        try:
            return datetime.datetime.fromisoformat(ts)
        except ValueError:
            return None

    t_commit, t_edit = parse(tip), parse(edited)
    if t_commit is None or t_edit is None:
        return "unreadable", "could not parse %r / %r" % (tip, edited)
    if t_commit > t_edit:
        return "stale", "PR #%s body edited %s, tip pushed %s" % (
            pr.get("number", "?"),
            t_edit.strftime("%H:%M:%SZ"),
            t_commit.strftime("%H:%M:%SZ"),
        )
    return "ok", ""


# ---- v10: CI trouble on the open PR (operator request, 2026-07-30) ---------
#
# THE ASK: "if there is only one active session and if there is an open PR for the current branch, then stop hook should check the PR green/red status and give feedback to make it green ... if there is no gh cli watch in the background."
#
# WHAT THIS IS NOT. It is deliberately NOT "block while conclusion != success".
# That shape was tried in the head, against one night of real runs, and it nags four times about nothing:
#
# * CANCELLED IS NOT RED. Four runs that night ended `cancelled` with ZERO failed jobs, each superseded by this session's own next push. And the watchdog FORCE-CANCELS a run when a real gate fails, so `cancelled` also means "something genuinely failed". The run-level rollup cannot tell those apart, so nothing here ever reads it as a verdict: every judgement comes
#     from PER-JOB conclusions (run 30514648812 was `cancelled` with
#     `Quality / Static` = failure; run 30513152662 was `cancelled` with none).
# * A RUN THAT IS STILL GROWING IS NOT FINAL. Job count climbed 18 -> 37 -> 79 -> 92 -> 95 inside one run. So nothing here ever concludes GREEN from a partial list. It only ever speaks about jobs that have ALREADY COMPLETED
#     with a failing conclusion, which is a fact no later job can retract.
# * THE WATCHDOG MAY ALREADY BE FIXING IT. Jobs matching WATCHDOG_RETRY_ALLOWLIST_PATTERNS (.github/workflows/watchdog-monitor.yml) are auto-retried onto the SAME run as a later attempt. Telling the session
#     to investigate a leg that is about to be rerun burns a whole round; that
# night an opensuse E2E leg failed on a Docker Hub CDN reset, was retried, and the run went green at 95 jobs. Those failures are REPORTED, never blocked on, until the run is final and they are still red.
#
# The output is a HANDOVER OF FACTS, in the shape submodule_pointer_moves() uses: the failing job, its failing STEP, its run and attempt, and the exact command that reads its log. "CI is red" alone is noise; a session cannot brief a sub-agent with it.
CI_RETRY_PATTERNS = [
    p.strip()
    for p in os.environ.get(
        "WORKLIST_CI_RETRY_PATTERNS", "E2E,OPS,Fork Isolation,Migration Test"
    ).split(",")
    if p.strip()
]
# PER-JOB conclusions that mean "this genuinely failed". CANCELLED, SKIPPED, NEUTRAL and STALE are deliberately absent: see the CANCELLED note above.
CI_FAIL_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}
CI_LIVE_ROLLUP = {"PENDING", "EXPECTED"}
# NEVER A FAILURE, regardless of conclusion (PLAN-ci-verdict box D): "CI Verdict" is the neutral check-run .github/workflows/ci-verdict.yml posts on the head SHA AFTER Console CI completes, carrying the diagnosis (rediacc_ci.ci.ci_diagnose), and "Publish CI Verdict" is the job that posts it. Both arrive after the verdict they describe, so counting either as in flight would hold a finished head at RUNNING, and counting a crashed publisher as a failure would paint a green head red.
# "Review Status" and "Claude Review" are the PR review's jobs (PLAN-github-pr-review-restore): "Claude Review" runs the review and "Review Status" posts the "Review Complete" check-run. Neither is a result of its own, since a review error reaches the head through Review Complete's failed-run token.
# "Review Complete" is deliberately NOT here: the operator ruled on 2026-10-03 that it is a required check on main again (errors are investigated and fixed, an LLM outage being the one exception), so it holds a head at RUNNING while in flight and paints it red when it fails.
# An exact name match, not a SUBSTRING match like CI_RETRY_PATTERNS: a substring would risk swallowing a real job that merely contains "Verdict" or "Review" in its name, such as Console CI's own "Review Gate".
CI_NONBLOCKING_CONTEXTS = {
    "CI Verdict",
    "Publish CI Verdict",
    "Review Status",
    "Claude Review",
}
# THE REQUIRED CHECK. Console CI's last job (`ci-complete` in .github/workflows/ci.yml, `if: always() && !cancelled()`), and the only context that proves the whole run reported. See ci_gate().
CI_COMPLETE_CONTEXT = "CI Complete"
CONSOLE_CI_WORKFLOW = "Console CI"
# Cost control (this hook runs on EVERY stop, including a 5-minute poll cron). Keyed on the published tip SHA, so any push invalidates it immediately.
CI_CACHE_LIVE_S = int(os.environ.get("WORKLIST_CI_CACHE_LIVE_S", "180"))
CI_CACHE_FINAL_S = int(os.environ.get("WORKLIST_CI_CACHE_FINAL_S", "900"))
# THE DEADLOCK CEILING. See ci_trouble()'s docstring.
CI_MAX_BLOCKS = int(os.environ.get("WORKLIST_CI_MAX_BLOCKS", "2"))
CI_MAX_PAGES = 3
CI_STEP_LOOKUPS = 2


def _bare_branch(ref):
    """`origin/x`, `refs/heads/x` and `refs/remotes/origin/x` all name branch `x` for the runs API."""
    ref = ref.strip()
    for prefix in ("refs/remotes/origin/", "refs/heads/", "origin/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def repo_slug(root):
    """(owner, name) from remote.origin.url, or (None, None)."""
    url = _git(root, "config", "--get", "remote.origin.url")
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def ci_query(owner, name, ref, cursor):
    """The ONE read. statusCheckRollup rather than checkSuites.checkRuns on purpose: the rollup exposes the LATEST check run per context, so a watchdog rerun replaces the failed attempt rather than appearing beside it. That is what makes a rerun-in-flight read as IN_PROGRESS here, and this check go quiet by itself while the watchdog works."""
    after = ',after:"%s"' % cursor if cursor else ""
    return (
        '{repository(owner:"%s",name:"%s"){pushedAt pullRequests(headRefName:"%s",states:OPEN,first:1)'
        "{nodes{number url isDraft commits(last:1){nodes{commit{oid statusCheckRollup{state "
        "contexts(first:100%s){totalCount pageInfo{hasNextPage endCursor} nodes{__typename "
        "... on CheckRun{name status conclusion databaseId detailsUrl "
        "checkSuite{workflowRun{databaseId}}} "
        "... on StatusContext{context state targetUrl}}}}}}}}}}}"
    ) % (owner, name, ref, after)


def ci_branch_query(owner, name, ref, cursor):
    """The SAME rollup, read from the branch instead of from a PR.

    `main` after a merge has no open PR, so ci_query's pullRequests(...) selector returns zero nodes and the reader goes blind at exactly the point /pr-merge step 5 needs it. The context selection set below matches ci_query's plus TWO fields, `checkSuite.branch.name` and `workflowRun.event`, which branch_owns_context needs: a commit's rollup is per-SHA, not per-branch (see there).
    """
    after = ',after:"%s"' % cursor if cursor else ""
    # `pushedAt` (the repository's LAST PUSH, to any branch) bounds the head's age from below, which is what lets ci-trace tell a [skip ci] head from a just-pushed one whose runs have not registered yet (see ci-trace's _noci_settled).
    return (
        '{repository(owner:"%s",name:"%s"){pushedAt ref(qualifiedName:"refs/heads/%s")'
        "{target{... on Commit{oid statusCheckRollup{state " + _BRANCH_CONTEXTS + "}}}}}}"
    ) % (owner, name, ref, after)


# The context selection shared by the branch read and the per-commit read (ci_commit_query), so the ownership fields cannot be present in one and missing in the other.
_BRANCH_CONTEXTS = (
    "contexts(first:100%s){totalCount pageInfo{hasNextPage endCursor} nodes{__typename"
    " ... on CheckRun{name status conclusion databaseId detailsUrl"
    " checkSuite{branch{name} workflowRun{databaseId event}}}"
    " ... on StatusContext{context state targetUrl}}}"
)


def ci_commit_query(owner, name, oid, cursor):
    """The branch read's rollup, for ONE commit by oid (a no-CI head's nearest checked ancestor)."""
    after = ',after:"%s"' % cursor if cursor else ""
    return (
        '{repository(owner:"%s",name:"%s"){object(oid:"%s")'
        "{... on Commit{oid statusCheckRollup{state " + _BRANCH_CONTEXTS + "}}}}}"
    ) % (owner, name, oid, after)


def ci_commit_rollup(root, owner, name, oid, ref):
    """(state, info) for one commit, contexts filtered to runs OF `ref` exactly as a branch read is."""

    def extract(data):
        try:
            node = data["data"]["repository"]["object"]
        except (KeyError, TypeError):
            return "unreadable", "graphql response had no repository.object", None
        if not node or not node.get("oid"):
            return "unreadable", "commit %s not found" % oid[:8], None
        return None, node, None

    return _rollup_pages(
        root,
        owner,
        name,
        ref,
        lambda c: ci_commit_query(owner, name, oid, c),
        extract,
        "commit",
        keep=lambda c: branch_owns_context(c, ref),
    )


# Runs of these events never feed a commit's statusCheckRollup (measured 2026-08-26 for workflow_dispatch: Release run 32968110599 was absent from the rollup), so they cannot be what a null rollup is waiting for. main's head routinely carries Watchdog and VM Bake dispatch runs on a [skip ci] commit.
CI_ROLLUP_BLIND_EVENTS = {"workflow_dispatch", "workflow_run", "repository_dispatch"}


def commit_ci_runs(root, owner, name, sha):
    """(runs, error) -- the Actions runs on `sha` that CAN report into its rollup.

    Each run is (id, workflow name, event, status, attempt, created_at, conclusion). An empty list with no error is the [skip ci] / path-filtered answer: nothing is coming. The conclusion is "" while the run is in flight.
    """
    data, err = wl_gh.call(
        ["api", "repos/%s/%s/actions/runs?head_sha=%s&per_page=100" % (owner, name, sha)],
        cwd=root,
    )
    if data is None:
        return None, err
    runs = data.get("workflow_runs")
    if not isinstance(runs, list):
        return None, "actions/runs response had no workflow_runs list"
    return [
        (
            r.get("id"),
            r.get("name") or "?",
            r.get("event") or "?",
            r.get("status") or "?",
            r.get("run_attempt") or 1,
            r.get("created_at") or "",
            r.get("conclusion") or "",
        )
        for r in runs
        if (r.get("event") or "") not in CI_ROLLUP_BLIND_EVENTS
    ], ""


def nearest_checked_ancestor(root, owner, name, sha, depth=10):
    """(oid, error) -- the closest strict ancestor of `sha` whose rollup is non-null, within `depth` commits of first-parent history; (None, "") when none is."""
    data, err = wl_gh.call(
        [
            "api",
            "graphql",
            "-f",
            "query="
            + (
                '{repository(owner:"%s",name:"%s"){object(oid:"%s"){... on Commit'
                "{history(first:%d){nodes{oid statusCheckRollup{state}}}}}}}"
            )
            % (owner, name, sha, depth + 1),
        ],
        cwd=root,
    )
    if data is None:
        return None, err
    try:
        nodes = data["data"]["repository"]["object"]["history"]["nodes"]
    except (KeyError, TypeError):
        return None, "graphql response had no commit history"
    for node in nodes or []:
        if node.get("oid") and node["oid"] != sha and node.get("statusCheckRollup"):
            return node["oid"], ""
    return None, ""


def branch_owns_context(ctx, ref):
    """Whether one rollup context belongs to a run OF BRANCH `ref`.

    A COMMIT'S statusCheckRollup IS PER-SHA, NOT PER-BRANCH. Measured 2026-09-30 on 49e61a1a (main): the rollup read through refs/heads/main carried 63 check runs from Console CI run 36669944808 -- a `pull_request`-event run whose head_branch was 0923-1, the PR branch deleted mid-run when the PR fast-forwarded into main -- beside the 30 from push run 36670172984 on main. The PR run had 7
    failures, the push run none, and `ci-trace --ref main` printed RED for main.

    A check suite that names its branch is decided by that name. A suite with NO branch (the branch was deleted, which is exactly the fast-forward case) falls back to the run's event: a pull_request-family event belongs to the PR's head branch, never to a pushed ref. A StatusContext, and a check run with neither branch nor workflow run, carries no ownership signal and is kept: dropping an unattributable failure would be a false green.
    """
    if ctx.get("__typename") == "StatusContext":
        return True
    suite = ctx.get("checkSuite") or {}
    branch = (suite.get("branch") or {}).get("name")
    if branch:
        return branch == ref
    event = ((suite.get("workflowRun") or {}).get("event") or "").lower()
    return not event.startswith("pull_request")


def _branch_rollup_state(contexts):
    """The rollup state recomputed over the OWNED contexts only.

    GitHub's own `state` aggregates every context on the SHA, so a foreign PR run still in flight would hold the branch at PENDING and a foreign failure at FAILURE. ci_classify reads this only for liveness (CI_LIVE_ROLLUP). Nothing owned is EXPECTED, never SUCCESS: a branch whose own run has not registered yet is not green.
    """
    if not contexts:
        return "EXPECTED"
    for c in contexts:
        if c.get("__typename") == "StatusContext":
            if (c.get("state") or "").upper() in CI_LIVE_ROLLUP:
                return "PENDING"
        elif (c.get("status") or "").upper() != "COMPLETED":
            return "PENDING"
    return "SUCCESS"


def ci_rollup(root, ref, allow_branch=False, repo=None):
    """(state, info) -- one paged read of the check rollup for `ref`.

    state is ok | no-pr | no-ref | unreadable. `unreadable` is a real verdict, in the V_PR_UNREADABLE style: a check that cannot see must SAY SO.

    allow_branch DEFAULTS TO FALSE AND MUST STAY THAT WAY. The Stop hook reads `no-pr` as a meaningful answer -- "this branch has no PR to be current with" -- so silently substituting a branch read would CHANGE that check's meaning rather than extend it. Only a caller that explicitly named a ref opts in.
    """
    # `repo` ("owner/name") overrides the slug read from root's origin, so a caller tracing another repository (ci-trace --repo) names it instead of relying on the remote.
    owner, name = repo.split("/", 1) if repo and "/" in repo else repo_slug(root)
    if not owner:
        return "unreadable", "could not derive owner/name from remote.origin.url"
    state, info = _rollup_pr(root, owner, name, ref)
    if state == "no-pr" and allow_branch:
        return _rollup_branch(root, owner, name, ref)
    return state, info


def _rollup_pages(root, owner, name, ref, build_query, extract, source, keep=None):
    """Page ONE rollup source into the common payload.

    Both sources share this loop so CI_MAX_PAGES and the `truncated` flag cannot drift apart between them -- a partial read that forgot to say it was partial is the vacuity failure this reader exists to avoid.

    `extract(data)` returns (terminal_state, commit, pr) -- terminal_state is None to continue paging. `keep(ctx)`, when given, drops contexts that do not belong to this source and recomputes the rollup state over the rest (the branch source; see branch_owns_context).
    """
    contexts, cursor, commit, pr, roll = [], None, None, None, None
    truncated = True
    for _ in range(CI_MAX_PAGES):
        data, err = wl_gh.call(["api", "graphql", "-f", "query=" + build_query(cursor)], cwd=root)
        if data is None:
            return "unreadable", err
        terminal, commit, pr = extract(data)
        if terminal:
            return terminal, ref if terminal in ("no-pr", "no-ref") else commit
        roll = (commit or {}).get("statusCheckRollup")
        if not roll:
            # No checks registered on this head yet. Not a verdict and not blindness: an empty context list simply produces silence below.
            truncated = False
            break
        ctx = roll.get("contexts") or {}
        contexts.extend(ctx.get("nodes") or [])
        page = ctx.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            truncated = False
            break
        cursor = page.get("endCursor")
    rollup = (roll or {}).get("state") or "EXPECTED"
    total = ((roll or {}).get("contexts") or {}).get("totalCount") or len(contexts)
    foreign = 0
    if keep is not None:
        owned = [c for c in contexts if keep(c)]
        foreign = len(contexts) - len(owned)
        contexts = owned
        rollup = _branch_rollup_state(contexts)
        total = max(total - foreign, len(contexts))
    return "ok", {
        "owner": owner,
        "name": name,
        "source": source,
        "pr": (pr or {}).get("number"),
        "url": (pr or {}).get("url") or "",
        # Carried so a GREEN verdict can name the next action. A reader must not flip the PR itself -- several watches can be armed at once and the ready-flip is a one-way PR state change -- but it CAN stop the finish sequence depending on the agent remembering it exists.
        "draft": bool((pr or {}).get("isDraft")),
        "sha": (commit or {}).get("oid") or "",
        "rollup": rollup,
        "total": total,
        "contexts": contexts,
        # Contexts on this SHA dropped because they belong to another branch's run (branch source only; always 0 for a PR read).
        "foreign": foreign,
        # False when the commit carries no statusCheckRollup at all (nothing ever reported on it).
        "has_rollup": bool(roll),
        "truncated": truncated,
    }


def _rollup_pr(root, owner, name, ref):
    meta = {}

    def extract(data):
        try:
            nodes = data["data"]["repository"]["pullRequests"]["nodes"]
            meta["pushed_at"] = data["data"]["repository"].get("pushedAt")
        except (KeyError, TypeError):
            return "unreadable", "graphql response had no pullRequests.nodes", None
        if not nodes:
            return "no-pr", None, None
        pr = nodes[0]
        try:
            return None, pr["commits"]["nodes"][0]["commit"], pr
        except (KeyError, IndexError, TypeError):
            return (
                "unreadable",
                "PR #%s carries no head commit" % pr.get("number", "?"),
                None,
            )

    # `extract` returns its unreadable reason in the commit slot, which _rollup_pages passes straight through as `info`.
    state, info = _rollup_pages(
        root, owner, name, ref, lambda c: ci_query(owner, name, ref, c), extract, "pr"
    )
    if state == "ok":
        # The repository's last push bounds the head's age from below, so a zero-context head can be told from a just-pushed one (ci-trace's _noci_settled).
        info["pushed_at"] = meta.get("pushed_at") or ""
    return state, info


def _rollup_branch(root, owner, name, ref):
    meta = {}

    def extract(data):
        try:
            node = data["data"]["repository"]["ref"]
            meta["pushed_at"] = data["data"]["repository"].get("pushedAt")
        except (KeyError, TypeError, AttributeError):
            return "unreadable", "graphql response had no repository.ref", None
        if not node:
            # A ref that does not exist is NOT the same answer as a ref with no checks, and conflating them is how a typo reads as a clean run.
            return "no-ref", None, None
        target = node.get("target") or {}
        if not target.get("oid"):
            return "unreadable", "ref %r resolved to a non-commit target" % ref, None
        return None, target, None

    state, info = _rollup_pages(
        root,
        owner,
        name,
        ref,
        lambda c: ci_branch_query(owner, name, ref, c),
        extract,
        "branch",
        keep=lambda c: branch_owns_context(c, ref),
    )
    if state == "ok":
        info["pushed_at"] = meta.get("pushed_at") or ""
    return state, info


def ci_classify(info):
    """(live, hard, soft) from PER-JOB conclusions only.

    `live` means the head still has work in flight, which is the ONLY thing the run-level rollup is used for -- never as a pass/fail verdict.

    A completed failing job whose name matches the watchdog's retry allowlist is SOFT while the head is live, because a retry may be inbound. Once the head is final and it is STILL failing, the watchdog is done with it and it is hard, which is the difference between "wait" and "go read the log".
    """
    rows, pending, blocking_seen = [], 0, 0
    for c in info.get("contexts") or []:
        # Skipped BEFORE branching on shape, and before the pending count too: this context can be a StatusContext OR a CheckRun depending on how it was posted, and it must never contribute to "live" either -- it can
        # sit at conclusion=failure indefinitely (a crashed verdict publisher
        # never re-runs), which would otherwise wedge the rollup as perpetually in-flight rather than genuinely final.
        if (c.get("context") or c.get("name") or "?") in CI_NONBLOCKING_CONTEXTS:
            continue
        blocking_seen += 1
        if c.get("__typename") == "StatusContext":
            state = (c.get("state") or "").upper()
            if state in ("PENDING", "EXPECTED"):
                pending += 1
                continue
            if state not in ("FAILURE", "ERROR"):
                continue
            rows.append(
                {
                    "name": c.get("context") or "?",
                    "job": None,
                    "run": None,
                    "url": c.get("targetUrl") or "",
                    "conclusion": state,
                }
            )
            continue
        status = (c.get("status") or "").upper()
        concl = (c.get("conclusion") or "").upper()
        if status != "COMPLETED":
            pending += 1
            continue
        if concl not in CI_FAIL_CONCLUSIONS:
            continue
        rows.append(
            {
                "name": c.get("name") or "?",
                "job": c.get("databaseId"),
                "run": ((c.get("checkSuite") or {}).get("workflowRun") or {}).get("databaseId"),
                "url": c.get("detailsUrl") or "",
                "conclusion": concl,
            }
        )
    # LIVENESS OVER THE BLOCKING CONTEXTS ONLY. GitHub's aggregate `state` counts every context, so a non-blocking one still in flight ("CI Verdict" is posted AFTER Console CI completes) held a finished head at PENDING. The aggregate is consulted only when no blocking context exists at all, where it is the one signal that something is expected.
    live = pending > 0 or (
        not blocking_seen and str(info.get("rollup") or "").upper() in CI_LIVE_ROLLUP
    )
    hard, soft = [], []
    for row in rows:
        retryable = any(p.lower() in row["name"].lower() for p in CI_RETRY_PATTERNS)
        (soft if (live and retryable) else hard).append(row)
    return live, hard, soft


def _ctx_run(c):
    return ((c.get("checkSuite") or {}).get("workflowRun") or {}).get("databaseId")


def ci_gate(info, require_complete=True):
    """THE GREEN RULE, shared by ci-trace's branch/PR read, its --run read and ci_trouble below. Pure: no network.

    Returns {"verdict": green|running|red|no-verdict, "reason", "live", "hard", "soft", "cancelled", "waiting", "ci_complete", "run"}.

    WHY A CHECK-RUN AND NOT "NOTHING FAILED". On 2026-10-02 at 02:01Z `ci-trace.py --wait --until-final` printed GREEN for PR #591 head a7f30558 about a minute after Console CI run 36953549081 was created: the only contexts registered were from `CI - OBS Mirror`, all green, so nothing had failed and nothing was in flight. That run later ended cancelled with 29 jobs that never reported. "No failure among the contexts that exist" says nothing about the contexts that do not exist yet. `CI Complete` is the one context that exists only once every job has reported, so GREEN requires it present, completed and successful (`require_complete=False` only for a run of another workflow, which has no such job).

    In order: a failure is red (failures are irrevocable, even off a partial read); anything blocking in flight is running; a cancelled blocking context is red (the caller attributes the cause); a truncated read is no-verdict (a partial page proves nothing about the contexts it never reached); then `CI Complete` decides.
    """
    live, hard, soft = ci_classify(info)
    contexts = info.get("contexts") or []
    blocking = [
        c
        for c in contexts
        if (c.get("context") or c.get("name") or "?") not in CI_NONBLOCKING_CONTEXTS
    ]
    waiting = 0
    cancelled: list[dict] = []
    runs: dict[int, int] = {}
    complete = None
    for c in blocking:
        if c.get("__typename") == "StatusContext":
            if (c.get("state") or "").upper() in CI_LIVE_ROLLUP:
                waiting += 1
            continue
        if (c.get("status") or "").upper() != "COMPLETED":
            waiting += 1
        if (c.get("conclusion") or "").upper() == "CANCELLED":
            cancelled.append(
                {"name": c.get("name") or "?", "run": _ctx_run(c), "job": c.get("databaseId")}
            )
        rid = _ctx_run(c)
        if rid:
            runs[rid] = runs.get(rid, 0) + 1
        if c.get("name") == CI_COMPLETE_CONTEXT:
            complete = c
    if complete is None:
        ci_complete = "absent"
    elif (complete.get("status") or "").upper() != "COMPLETED":
        ci_complete = "pending"
    else:
        ci_complete = (complete.get("conclusion") or "").lower() or "pending"
    # The Console CI run: the one carrying CI Complete, else the run with the most contexts (Console CI's ~170 against a side workflow's one or two).
    run = _ctx_run(complete) if complete else (max(runs, key=lambda r: runs[r]) if runs else None)
    gate = {
        "live": live,
        "hard": hard,
        "soft": soft,
        "cancelled": cancelled,
        "waiting": waiting,
        "ci_complete": ci_complete,
        "run": run,
    }
    if hard:
        gate.update(verdict="red", reason="%d job(s) failed" % len(hard))
    elif live:
        gate.update(verdict="running", reason="%d context(s) still in flight" % waiting)
    elif cancelled:
        gate.update(
            verdict="red",
            reason="%d context(s) CANCELLED with nothing failing -- each is a gate that did NOT report"
            % len(cancelled),
        )
    elif info.get("truncated"):
        gate.update(
            verdict="no-verdict",
            reason="the read stopped at %d of %s contexts, so nothing can be called green"
            % (len(contexts), info.get("total", "?")),
        )
    elif not require_complete:
        gate.update(verdict="green", reason="every job succeeded or was skipped")
    elif ci_complete == "absent":
        gate.update(
            verdict="running",
            reason="%s has not reported on this head yet (%d blocking context(s) registered)"
            % (CI_COMPLETE_CONTEXT, len(blocking)),
        )
    elif ci_complete == "pending":
        gate.update(verdict="running", reason="%s is still running" % CI_COMPLETE_CONTEXT)
    elif ci_complete != "success":
        gate.update(verdict="red", reason="%s concluded %s" % (CI_COMPLETE_CONTEXT, ci_complete))
    else:
        gate.update(
            verdict="green",
            reason="%s succeeded and every blocking context succeeded or was skipped"
            % CI_COMPLETE_CONTEXT,
        )
    return gate


def _load_diagnose():
    """rediacc_ci.ci.ci_diagnose loaded by file path, or None. Lazy and defensive like _sanctioned_match: a missing module must not take the Stop hook down."""
    try:
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / ".ci"
            / "rediacc_ci"
            / "ci"
            / "ci_diagnose.py"
        )
        spec = importlib.util.spec_from_file_location("ci_diagnose", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 -- a broken diagnoser is not a verdict
        return None


def ci_cancel_cause(root, info, gate):
    """The ci_diagnose.cancel_cause dict for the run behind `gate["cancelled"]`, or an `unknown` one. Three to five `gh` reads, so callers cache it."""
    unknown = {
        "kind": "unknown",
        "detail": "cause unknown; not proven superseded",
        "job": None,
        "minutes": None,
        "budget_min": None,
        "watchdog_run": None,
    }
    run_id = next(
        (c["run"] for c in gate.get("cancelled") or [] if c.get("run")), None
    ) or gate.get("run")
    diag = _load_diagnose()
    if diag is None or not run_id or not info.get("owner"):
        return unknown
    # The Stop hook's budget: at most two reads and one 2 s pause on a transient 5xx (PLAN-gh-retry G8).
    fetch = diag.GhFetcher(
        "%s/%s" % (info["owner"], info["name"]), cwd=root, timeout=20, attempts=2, pause=2
    )
    run, _err = diag.run_info(fetch, run_id)
    if run is None:
        return unknown
    jobs, _err = diag.run_jobs(fetch, run_id, run.get("run_attempt"))
    try:
        return diag.cancel_cause(fetch, run, pr_head=info.get("sha") or None, jobs=jobs)
    except Exception:  # noqa: BLE001
        return unknown


def ci_cancel_note(detail):
    """The Stop-hook note for a `cancelled` ci_trouble state, or "" when the cause is not proven (unknown / superseded stay silent: test_122)."""
    cause = (detail or {}).get("cause") or {}
    if cause.get("kind") in (None, "unknown", "superseded"):
        return ""
    info = (detail or {}).get("info") or {}
    run = next((c.get("run") for c in ci_gate(info).get("cancelled") or [] if c.get("run")), None)
    return (
        "CI on PR #%s was CANCELLED with nothing failing: %s: %s%s.\n"
        "  Read it: .ci/scripts/ci/ci-trace.py --why%s"
        % (
            info.get("pr", "?"),
            cause.get("kind"),
            cause.get("detail"),
            " [watchdog run %s]" % cause["watchdog_run"] if cause.get("watchdog_run") else "",
            " (run %s)" % run if run else "",
        )
    )


# v12 (operator, 2026-07-30): "hook should detect that is current session sitting for CI pipeline? If so, it should FORCE current session to work on waiting items!!!" The shape of a CI watch, matched against a background task's command + description. Deliberately CONSERVATIVE: `gh run watch`, an Actions run URL/path, a run-id-sized number near "watch", or "CI" near "watch". A dev
# file-watcher (`npm run watch`) matches none of these, and a false positive here turns a working session's stop into an accusation.
CI_WATCH_RE = re.compile(
    r"gh\s+run\s+watch"
    r"|actions/runs/\d+"
    r"|\bci\b[^\n]{0,40}\bwatch|\bwatch\w*\b[^\n]{0,40}\bci\b"
    r"|\bwatch\w*\b[^\n]{0,40}\b\d{9,}\b|\b\d{9,}\b[^\n]{0,40}\bwatch\w*\b",
    re.IGNORECASE,
)


def ci_watch_only(live_bg):
    """(watching, description) -- is watching CI the ONLY thing in flight?

    True only when at least one RUNNING background task matches the CI-watch shape and EVERY running background task does. One non-watch worker means the session has real work delegated and is not merely sitting; no tasks at all means there is nothing being waited on and the idle detector owns that case. The description names the watches so the block can quote them.
    """
    names = []
    for b in live_bg or []:
        blob = "%s %s" % (b.get("command") or "", b.get("description") or "")
        if CI_WATCH_RE.search(blob):
            names.append(
                "%s: %s"
                % (b.get("id") or "?", (b.get("description") or b.get("command") or "")[:60])
            )
        else:
            return False, ""
    return bool(names), "; ".join(names)


# The sanctioned CI reader. A watch that is not this is a hand-rolled loop, and hand-rolled loops failed four ways on 2026-08-25 while landing console#574: a stale recipe in nine places, a verdict from a SUPERSEDED attempt, a verdict
# from a run a later push had cancelled, and a network blip that only a
# correctly-written retry arm survived. See .ci/scripts/ci/ci-trace.py.
def _sanctioned_match(blob):
    """True when the blob carries a shape the sanctioned registry replaces.

    Imported lazily and defensively: this module runs on every stop, and a missing or broken registry must not take the whole hook down with it.
    """
    try:
        lib = pathlib.Path(__file__).resolve().parent.parent / "lib" / "sanctioned.py"
        spec = importlib.util.spec_from_file_location("sanctioned", lib)
        if spec is None or spec.loader is None:
            return False
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.match(blob) is not None
    except Exception:  # noqa: BLE001 -- a broken registry is not a verdict
        return False


# Does this blob touch GitHub at all? Something that cannot be a CI watch is not one, however much it says "watch".
GH_EVIDENCE_RE = re.compile(r"\bgh\b|actions/runs/\d+|ci-trace", re.IGNORECASE)

CI_TRACE_RE = re.compile(r"ci-trace(?:\.py)?\b", re.IGNORECASE)


def adhoc_watch(live_bg):
    """(task_id, blob) for a RUNNING background task watching CI by hand, or ("","").

    "By hand" means: it looks like a CI watch (CI_WATCH_RE, the same shape the idle checks already use) and it is NOT ci-trace.py. The caller blocks the turn on this, which is safe to make unconditional -- unlike ci_trouble, the remedy is entirely within the session's reach: stop the task and run the script. Nothing another session's push or an infrastructure flake can do makes
    this unfixable, so there is no ceiling and no escape hatch.
    """
    for b in live_bg or []:
        blob = "%s %s" % (b.get("command") or "", b.get("description") or "")
        if CI_TRACE_RE.search(blob):
            continue
        # TWO detectors, because each alone has a hole. CI_WATCH_RE is deliberately conservative (it also drives the idle checks, where a false positive turns a working session's stop into an accusation) and misses a bare `gh run view` poll with no "watch" word in it. The sanctioned registry catches exactly that shape -- and sharing it is the point: the pre-bash guard and this
        # check then cannot disagree about what counts as hand-rolled, which is the class of drift this whole change exists to end. EVIDENCE OF GITHUB, not merely the word "watch". CI_WATCH_RE also matches "watch" sitting near any 9+ digit number, and a worklist fixture named `sleep 3717171718 silent watch` -- a generic background worker with no gh call anywhere in it -- was
        # blocking the turn. A guard that stops unrelated work is a guard that gets removed.
        if not GH_EVIDENCE_RE.search(blob):
            continue
        if CI_WATCH_RE.search(blob) or _sanctioned_match(blob):
            return str(b.get("id") or "?"), blob.strip()[:160]
    return "", ""


def ci_watch_armed(live_bg, rows, sha):
    """The id of a RUNNING background task watching THIS head, or "".

    NOT "is some task running". A completed watch reported `completed/cancelled`
    for a run that had since been superseded, and another reported a FALSE
    failure because a watchdog rerun flipped a terminal run back to in_progress. So the test is: still running (the caller passes only those) AND naming this head's run id or SHA. A bare `gh run watch` with no id does not count -- it cannot be shown to be about this run.
    """
    needles = [str(r["run"]) for r in rows if r.get("run")]
    if sha:
        needles.append(sha[:12])
    for b in live_bg or []:
        blob = "%s %s" % (b.get("command") or "", b.get("description") or "")
        # THE SANCTIONED READER IS ALWAYS ABOUT THIS HEAD, so it needs no needle. ci-trace.py resolves the PR from the current branch and pins the head it starts on, exiting 3 if a push moves it -- it cannot be watching a stale run, which is the only thing the needle test ever guarded against. An explicit --ref points it elsewhere, so that form still has to prove itself the
        # ordinary way.
        if CI_TRACE_RE.search(blob) and "--ref" not in blob:
            return str(b.get("id") or (b.get("description") or "")[:60])
        if any(n and n in blob for n in needles):
            return str(b.get("id") or (b.get("description") or "")[:60])
    return ""


def ci_steps(root, info, rows, cached):
    """Fill in `step` and `attempt` for the first few failing jobs.

    ONE bounded REST call per job, and only on the path that is about to speak. `gh run view --log-failed` is deliberately not used anywhere here: it is RUN-scoped even with --job, refuses while the run is in progress, and writes the reason to stderr, so a 2>/dev/null capture reads as an empty log.
    """
    for row in rows[:CI_STEP_LOOKUPS]:
        key = str(row.get("job") or "")
        if not key:
            continue
        if key in cached:
            row["step"], row["attempt"] = cached[key]
            continue
        data, _err = wl_gh.call(
            ["api", "repos/%s/%s/actions/jobs/%s" % (info["owner"], info["name"], key)],
            cwd=root,
            timeout=20,
        )
        if data is None:
            continue
        steps = data.get("steps") or []
        bad = [
            s.get("name") for s in steps if (s.get("conclusion") or "") in ("failure", "timed_out")
        ]
        if not bad:
            bad = [s.get("name") for s in steps if (s.get("conclusion") or "") == "cancelled"]
        row["step"] = bad[0] if bad else ""
        row["attempt"] = data.get("run_attempt")
        cached[key] = (row["step"], row["attempt"])


def cistate_path(worklist, session_id):
    return worklist.with_suffix(".cistate-%s" % (session_id or "unknown")[:8])


def cimark_path(worklist, session_id):
    return worklist.with_suffix(".cimark-%s" % (session_id or "unknown")[:8])


# ---- v13: CI-queue-aware backpressure --------------------------------------- OPERATOR (2026-07-31): "CI side has stuck because of many commits. They're in the queue. For that situation stop hook should be smart to avoid pushing the system in such cases... there could be possibility that allow us to work locally until we see CI result to save time." Observed live the same night:
# a Console CI run sat status=pending for 25+ minutes because pushes had queued
# runs behind each other; every further push made the jam strictly worse while buying nothing, since only the newest head's result matters.
CI_QUEUE_MIN = int(os.environ.get("WORKLIST_CI_QUEUE_MIN", "10"))
CI_QUEUE_DEPTH = int(os.environ.get("WORKLIST_CI_QUEUE_DEPTH", "2"))
CI_QUEUE_CACHE_S = int(os.environ.get("WORKLIST_CI_QUEUE_CACHE_S", "180"))
_QUEUED_STATUSES = {"queued", "waiting", "pending", "requested"}


def ciqueue_path(worklist, session_id):
    return worklist.with_suffix(".ciqueue-%s" % (session_id or "unknown")[:8])


def ci_queue_state(root, worklist, session_id):
    """(state, detail) -- is the publish ref's CI queue saturated?

    state: unset | clear | saturated | unknown. `detail` on unknown carries
    {"ref", "error"} when the gh call itself failed, so a blind read is
    distinguishable from a quiet queue. `detail` for saturated is
    {"ref", "queued", "newest_age_min"}.

    Reads `actions/runs?branch=` rather than the head-commit rollup ON PURPOSE:
    the observed failure is OLDER runs jamming the queue behind the newest push, and the rollup only sees the head. Saturated iff the newest run has sat in a queued-family status for CI_QUEUE_MIN minutes, or CI_QUEUE_DEPTH or more runs are queued at once. A newest run that is in_progress with an empty queue is `clear`: a result is coming, normal discipline stands.

    FAILURE MODE IS A DELIBERATE INVERSION of the blocks-when-blind rule that governs the other CI checks. This check only ever GRANTS slack (permission to hold pushes), so blindness must fail toward pressure: gh broken, slug underivable, or non-JSON all return `unknown`, which callers treat exactly like today's behavior -- no note, no relaxation. A blind slack-granter would be an
    escape hatch. `unknown` is cached too, so a broken gh costs one call per TTL, not one per stop.
    """
    ref = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not ref:
        return "unset", None
    cache_p = ciqueue_path(worklist, session_id)
    c = wl_gh.cache_read(cache_p, CI_QUEUE_CACHE_S, CI_QUEUE_CACHE_S)
    if c is not None:
        return c.get("state") or "unknown", c.get("detail")
    owner, name = repo_slug(root)
    state: str = "unknown"
    detail: dict[str, Any] | None = None
    if owner:
        data, err = wl_gh.call(
            # The runs API matches only the BARE branch name, URL-encoded: `origin/x` or `refs/heads/x` matched no run at all, the same class ci-trace's --runs had.
            [
                "api",
                "repos/%s/%s/actions/runs?branch=%s&per_page=10"
                % (owner, name, urllib.parse.quote(_bare_branch(ref), safe="/")),
            ],
            cwd=root,
            timeout=20,
        )
        runs = (data or {}).get("workflow_runs") if isinstance(data, dict) else None
        if runs is None and err:
            # SAY WHY, rather than reporting a bare "unknown". A failed gh call and a genuinely empty queue used to be indistinguishable here, which is the blindness this program refuses everywhere else.
            detail = {"ref": ref, "error": err}
        if isinstance(runs, list):
            queued, newest_age = 0, None
            for i, r in enumerate(runs):
                status = (r.get("status") or "").lower()
                if status in _QUEUED_STATUSES:
                    queued += 1
                if i == 0:
                    try:
                        created = datetime.datetime.fromisoformat(r.get("created_at") or "")
                        age = (datetime.datetime.now(datetime.UTC) - created).total_seconds() / 60.0
                    except ValueError:
                        age = None
                    if status in _QUEUED_STATUSES:
                        newest_age = age
            if not runs:
                state = "clear"
            elif (newest_age is not None and newest_age >= CI_QUEUE_MIN) or (
                queued >= CI_QUEUE_DEPTH
            ):
                state = "saturated"
                detail = {
                    "ref": ref,
                    "queued": queued,
                    "newest_age_min": int(newest_age or 0),
                }
            else:
                state = "clear"
    wl_gh.cache_write(cache_p, {"at": time.time(), "state": state, "detail": detail})
    return state, detail


def ci_trouble(root, worklist, session_id, live_bg, ack_text, ref=None, owned=False):
    """(state, detail) -- is the open PR in trouble nobody is on?

    state: unset | multi-session | no-pr | ok | pending | cancelled | watched | soft |
           trouble | downgraded | unreadable

    `ok` is ci_gate's GREEN (CI Complete present and successful), not merely "nothing failed". `pending` is a head with no failure that is not green yet; it carries the info dict and blocks nothing. `cancelled` is a head whose blocking contexts were cancelled with nothing failing; its detail carries the attributed `cause` (ci_cancel_note renders it).

    THE ESCAPE, and why this one. A check that demands what a session cannot produce deadlocks it: one did exactly that for a whole night here, blocking every stop until morning. So there are TWO exits, and the second is unconditional:

      1. ACKNOWLEDGEMENT. Naming the failing job in the stop message (or in a
         `- [?] ... DEFAULT:` line) clears the block. You cannot type
         "Quality / Static" without having seen that it failed, so this is
         awareness, not a bypass -- and a `- [?]` is reported to the operator on
         every single stop, so a deferral cannot hide.
      2. A HARD CEILING of CI_MAX_BLOCKS consecutive blocks per failure set.
         After that the same set can never block again; it downgrades to a loud
         report on the allowed stop. A bounded-N ceiling was chosen over
         "block until fixed" precisely because the failure may not be this
         session's to fix (another session's push, an infrastructure flake, a
         pre-existing red on a submodule harness), and over a silent bypass
         because the facts still have to reach the operator every stop.

    A NEW failure set (new head SHA, or a different set of failing jobs) re-arms the budget: a new red is worth interrupting for exactly once more.

    FOCUS MODE ARMS IT (agent/plans/PLAN-stop-hook-focus-mode.md section 3): the caller passes the focus's `ref` and `owned=True`. `--focus` is the session declaring the PR its own, which is the one fact the multi-session skip below could not know, so that skip does not apply. Both exits above still do.
    """
    ref = ref or os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not ref:
        return "unset", None  # not opted in: zero network cost, same as pr_body_freshness
    if not owned and not S.sole_live_session(worklist, session_id):
        # With a second live session, red may be their push, and nagging this session about someone else's work is the failure mode to avoid.
        return "multi-session", None
    tip = _git(root, "rev-parse", "origin/%s" % ref)
    if not tip:
        return "no-pr", "origin/%s" % ref
    cache_p, marker_p = cistate_path(worklist, session_id), cimark_path(worklist, session_id)
    cache: Any = None
    c = wl_gh.cache_load(cache_p)
    if c is not None and c.get("sha") == tip:
        ttl = CI_CACHE_FINAL_S if c.get("final") else CI_CACHE_LIVE_S
        cache = c if wl_gh.cache_fresh(c, ttl, ttl) else None
    if cache is not None:
        state, info, steps = cache["state"], cache.get("info"), cache.get("steps") or {}
    else:
        state, info = ci_rollup(root, ref)
        steps = {}
    if state != "ok":
        if cache is None:
            _ci_cache_write(cache_p, tip, state, info, steps, final=(state == "no-pr"))
        return state, info
    live, hard, soft = ci_classify(info)
    if not hard and not soft:
        # "Nothing failed" is not "green": ci_gate() requires CI Complete (the 2026-10-02 false green). A head that is not green yet is `pending`, which the caller reports as nothing, and a cancel with nothing failing is attributed once (cached on this tip) and handed over as `cancelled`.
        gate = ci_gate(info)
        if gate["verdict"] == "green":
            _ci_cache_write(cache_p, tip, state, info, steps, final=True)
            return "ok", info
        if gate["verdict"] == "red" and gate["cancelled"]:
            cause = steps.get("_cause") if isinstance(steps.get("_cause"), dict) else None
            if cause is None:
                cause = ci_cancel_cause(root, info, gate)
                steps["_cause"] = cause
            _ci_cache_write(cache_p, tip, state, info, steps, final=True)
            return "cancelled", {
                "info": info,
                "hard": [],
                "soft": [],
                "live": False,
                "cause": cause,
            }
        _ci_cache_write(cache_p, tip, state, info, steps, final=False)
        return "pending", info
    watcher = ci_watch_armed(live_bg, hard + soft, info.get("sha") or tip)
    if watcher:
        # The operator's own condition, and deliberately NOT gated on the run still being live. A watch keyed to this run is a wake-up whether the run is finishing or already finished; the window where a RUNNING watch coexists with a final run is the seconds before its last iteration prints, and firing into that window is a false alarm, not diligence.
        _ci_cache_write(cache_p, tip, state, info, steps, final=not live)
        return "watched", {"info": info, "hard": hard, "soft": soft, "watcher": watcher}
    ci_steps(root, info, hard or soft, steps)
    _ci_cache_write(cache_p, tip, state, info, steps, final=not live)
    if not hard:
        return "soft", {"info": info, "hard": hard, "soft": soft, "live": live}
    low = (ack_text or "").lower()
    acked = [r["name"] for r in hard if r["name"].lower() in low]
    sig = hashlib.sha1(
        ("%s|%s" % (tip, ",".join(sorted(r["name"] for r in hard)))).encode("utf-8", "replace")
    ).hexdigest()[:12]
    mark = wl_gh.cache_load(marker_p) or {}
    blocks = int(mark.get("blocks") or 0) if mark.get("sig") == sig else 0
    detail = {"info": info, "hard": hard, "soft": soft, "live": live, "acked": acked, "n": blocks}
    if acked or blocks >= CI_MAX_BLOCKS:
        return "downgraded", detail
    # Not a cache (no TTL), but written atomically like one: a half-written marker would reset the block budget.
    wl_gh.cache_write(marker_p, {"sig": sig, "blocks": blocks + 1})
    detail["n"] = blocks + 1
    return "trouble", detail


def prlink_path(worklist, session_id):
    return worklist.with_suffix(".prlink-%s" % (session_id or "unknown")[:8])


def pr_link(root, worklist, session_id, branch):
    """(nodes, error): every PR whose head is `branch`, newest update first, each {number, state, body, mergedAt, closedAt}.

    THE ONE PR READ of agent/plans/PLAN-stop-hook-one-plan-scope.md Design 1: a single GraphQL query over OPEN, MERGED and CLOSED, so the loop's scope (`wl_prscope.loop_state`) and focus mode's end (`focus_pr_end`) read the same node. Cached per branch for wl_standdown.FOCUS_PR_TTL_S in a `.prlink-<me8>` sidecar. A failed read returns ([], error) and is not cached, so the next stop asks again.
    """
    import wl_standdown  # noqa: PLC0415 -- sealed, stdlib only

    branch = str(branch or "")
    if not branch:
        return [], "no branch to read a PR for"
    cache_p = prlink_path(worklist, session_id)
    cache = wl_gh.cache_load(cache_p) or {}
    hit = cache.get(branch)
    if isinstance(hit, dict):
        with contextlib.suppress(TypeError, ValueError):
            if time.time() - float(hit.get("t") or 0) <= wl_standdown.FOCUS_PR_TTL_S:
                return list(hit.get("nodes") or []), ""
    owner, name = repo_slug(root)
    if not owner:
        return [], "could not derive owner/name from remote.origin.url"
    query = (
        '{repository(owner:"%s",name:"%s"){pullRequests(headRefName:"%s",'
        "states:[OPEN,MERGED,CLOSED],first:5,orderBy:{field:UPDATED_AT,direction:DESC})"
        "{nodes{number state body mergedAt closedAt}}}}"
    ) % (owner, name, branch)
    data, err = wl_gh.call(["api", "graphql", "-f", "query=" + query], cwd=root)
    if err:
        return [], err
    try:
        nodes = data["data"]["repository"]["pullRequests"]["nodes"] or []
    except (KeyError, TypeError):
        return [], "graphql response had no pullRequests.nodes"
    nodes = [n for n in nodes if isinstance(n, dict)]
    now = time.time()
    # Entries past their TTL are dropped on write, so the sidecar holds the live branches only.
    fresh = {}
    with contextlib.suppress(TypeError, ValueError):
        fresh = {
            k: v
            for k, v in cache.items()
            if isinstance(v, dict) and now - float(v.get("t") or 0) <= wl_standdown.FOCUS_PR_TTL_S
        }
    fresh[branch] = {"t": now, "nodes": nodes}
    wl_gh.cache_write(cache_p, fresh)
    return nodes, ""


def focus_pr_end(root, worklist, session_id, focus):
    """(reason, error): "merged", "closed" or "" -- has the focus's PR finished? (agent/plans/PLAN-stop-hook-focus-mode.md section 3.)

    Read through `pr_link`, the one PR read (cached per branch for wl_standdown.FOCUS_PR_TTL_S), and only while focus is on. Only MERGED and CLOSED nodes count. The node must be the focus's PR number, or, while that is unknown, the newest one closed AFTER the focus began, so a reused branch name cannot end it. A failed read returns ("", error): focus continues (the 24-hour cap bounds a permanently blind check) and the caller reports it.
    """
    branch = str((focus or {}).get("branch") or "")
    if not branch:
        return "", ""
    nodes, err = pr_link(root, worklist, session_id, branch)
    if err:
        return "", err
    want = (focus or {}).get("pr")
    since = str((focus or {}).get("at") or "")
    hit = None
    for n in nodes:
        if str(n.get("state")).upper() not in ("MERGED", "CLOSED"):
            continue
        if want not in (None, "", 0):
            if str(n.get("number")) == str(want):
                hit = n
                break
            continue
        closed = str(n.get("mergedAt") or n.get("closedAt") or "")
        # Both are ISO8601 UTC seconds with a Z (C.stamp_now and GitHub's DateTime), so text order is time order.
        if closed and closed >= since:
            hit = n
            break
    if hit is None:
        return "", ""
    return ("merged" if str(hit.get("state")).upper() == "MERGED" else "closed"), ""


def _ci_cache_write(path, sha, state, info, steps, final):
    wl_gh.cache_write(
        path,
        {
            "sha": sha,
            "at": time.time(),
            "state": state,
            "info": info,
            "steps": steps,
            "final": bool(final),
        },
    )


def ci_rows_text(rows, _info):
    """One line per failing job, plus the tracer command that reads its failing step (it fetches the log with the ANSI flag `gh` needs and caches it once the job is complete)."""
    out = []
    for r in rows[:6]:
        bits = ["    %s  %s" % (r["name"], r["conclusion"])]
        if r.get("step"):
            bits.append("(failing step: %s)" % r["step"])
        if r.get("run"):
            bits.append(
                "run %s%s" % (r["run"], " attempt %s" % r["attempt"] if r.get("attempt") else "")
            )
        out.append("  ".join(bits))
        if r.get("job"):
            out.append("        .ci/scripts/ci/ci-trace.py --job %s --errors" % r["job"])
        elif r.get("url"):
            out.append("        %s" % r["url"])
    return "\n".join(out)


def submodule_pointer_moves(root):
    """[(path, recorded_sha, worktree_sha, where)] for dirty gitlinks.

    DELIBERATELY LOCAL. Every fact here comes from git in the working tree, so this check cannot go "unreadable" on a network failure the way the PR freshness check can. `where` is the containing-remote-branch summary, which is the fact that actually decides the call: a pointer on the submodule's default branch is an ordinary bump, while one that exists only on a feature branch
    adds that branch's PR to this PR's merge chain.

    `git submodule status` marks a checked-out commit that differs from the index with a leading '+'. That is precisely the state a blind `git add -A` would convert into a committed dependency change.
    """
    out = _git(root, "submodule", "status", "--cached")
    if not out:
        return []
    moves = []
    for line in out.splitlines():
        if not line.startswith("+"):
            continue
        parts = line[1:].split()
        if len(parts) < 2:
            continue
        recorded, path = parts[0], parts[1]
        sub = pathlib.Path(root) / path
        live = _git(sub, "rev-parse", "HEAD") or "?"
        # --contains over REMOTE branches only: a local-only branch proves nothing about what CI can fetch.
        refs = _git(sub, "branch", "-r", "--contains", live) or ""
        names = [r.strip().lstrip("* ") for r in refs.splitlines() if r.strip()]
        names = [n for n in names if "->" not in n]
        head = _git(sub, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD") or ""
        default = head.rsplit("/", 1)[-1] if head else "main"
        on_default = any(n == "origin/%s" % default for n in names)
        if not names:
            where = "NOT PUSHED to any remote branch, so CI cannot fetch it"
        elif on_default:
            where = "on origin/%s (an ordinary bump)" % default
        else:
            where = (
                "only on %s, NOT on origin/%s, so this adds that branch's PR to the merge chain"
                % (
                    ", ".join(names[:3]),
                    default,
                )
            )
        moves.append((path, recorded[:9], live[:9], where))
    return moves


def _selftest():
    """Controls for ci_classify. Run: wl_ci.py --selftest

    Narrow on purpose: ci_classify is pure (info dict in, (live, hard, soft) out), so this proves the CI_NONBLOCKING_CONTEXTS filter on synthetic fixtures shaped like the real GraphQL contexts, not a live API read.
    """
    import wl_common  # noqa: PLC0415 -- the shared selftest checker, loaded only for a selftest

    check = wl_common.Checker()

    verdict_only = {
        "rollup": "SUCCESS",
        "contexts": [
            {
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "name": "CI Verdict",
                "databaseId": 1,
                "checkSuite": {"workflowRun": {"databaseId": 1}},
                "detailsUrl": "https://example/1",
            }
        ],
    }
    live, hard, soft = ci_classify(verdict_only)
    check(
        "THE REAL 2026-08-30 DEFECT SHAPE: a head whose ONLY context is a failing "
        "non-blocking 'CI Verdict' is not live and has no hard failures",
        live is False and hard == [] and soft == [],
        "live=%r hard=%r soft=%r" % (live, hard, soft),
    )

    verdict_plus_real_failure = {
        "rollup": "SUCCESS",
        "contexts": [
            verdict_only["contexts"][0],
            {
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "name": "Quality / Code",
                "databaseId": 2,
                "checkSuite": {"workflowRun": {"databaseId": 2}},
                "detailsUrl": "https://example/2",
            },
        ],
    }
    live, hard, soft = ci_classify(verdict_plus_real_failure)
    check(
        "REGRESSION CONTROL: a genuine failure beside CI Verdict is "
        "still reported, and CI Verdict is not swallowed into it",
        hard == [] or all(r["name"] != "CI Verdict" for r in hard),
        "hard=%r" % (hard,),
    )
    check(
        "REGRESSION CONTROL: the genuine failure IS the one hard failure",
        [r["name"] for r in hard] == ["Quality / Code"],
        "hard=%r" % (hard,),
    )

    verdict_plus_pending = {
        "rollup": "SUCCESS",
        "contexts": [
            verdict_only["contexts"][0],
            {"status": "IN_PROGRESS", "conclusion": "", "name": "Stage Artifacts"},
        ],
    }
    live, hard, soft = ci_classify(verdict_plus_pending)
    check(
        "CONTROL: a genuinely in-flight job beside CI Verdict still "
        "reads as live, and CI Verdict contributes nothing either way",
        live is True and hard == [],
        "live=%r hard=%r" % (live, hard),
    )

    status_context_verdict = {
        "rollup": "SUCCESS",
        "contexts": [
            {
                "__typename": "StatusContext",
                "state": "FAILURE",
                "context": "CI Verdict",
                "targetUrl": "https://example/3",
            }
        ],
    }
    live, hard, soft = ci_classify(status_context_verdict)
    check(
        "CONTROL: the filter matches on EITHER shape (StatusContext.context "
        "or CheckRun.name), since GitHub can post it as either",
        live is False and hard == [] and soft == [],
        "live=%r hard=%r soft=%r" % (live, hard, soft),
    )

    unrelated_verdict_named_job = {
        "rollup": "SUCCESS",
        "contexts": [
            {
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "name": "Verdict Gate",
                "databaseId": 4,
                "checkSuite": {"workflowRun": {"databaseId": 4}},
                "detailsUrl": "https://example/4",
            }
        ],
    }
    live, hard, soft = ci_classify(unrelated_verdict_named_job)
    check(
        "CONTROL: an EXACT match only -- a differently-named job that merely "
        "contains the word 'Verdict' is not swallowed by the filter",
        [r["name"] for r in hard] == ["Verdict Gate"],
        "hard=%r" % (hard,),
    )

    # ---- ci_gate: the GREEN rule (PLAN-ci-verdict box A).
    def run_ctx(name, status="COMPLETED", conclusion="SUCCESS", run=36953549081):
        return {
            "__typename": "CheckRun",
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "databaseId": abs(hash(name)) % 10**9,
            "checkSuite": {"workflowRun": {"databaseId": run}},
        }

    false_green = {
        "rollup": "SUCCESS",
        "truncated": False,
        "contexts": [run_ctx("OBS Mirror (opensuse-16.0)", run=36953548680)],
    }
    g = ci_gate(false_green)
    check(
        "THE 2026-10-02 FALSE GREEN: only a side workflow's contexts registered, all green -> "
        "running, never green, and the reason names CI Complete",
        g["verdict"] == "running" and "CI Complete" in g["reason"] and g["ci_complete"] == "absent",
        "gate=%r" % (g,),
    )
    full_ctx = [run_ctx("Quality / Code"), run_ctx("CI Complete")]
    full = {"rollup": "SUCCESS", "truncated": False, "contexts": full_ctx}
    check(
        "CONTROL: CI Complete present and successful -> green", ci_gate(full)["verdict"] == "green"
    )
    check(
        "CONTROL: a truncated read is no-verdict, never green",
        ci_gate(dict(full, truncated=True, total=400))["verdict"] == "no-verdict",
    )
    verdict_live = dict(
        full,
        rollup="PENDING",
        contexts=[
            *full_ctx,
            run_ctx("Publish CI Verdict", conclusion="FAILURE", run=1),
            run_ctx("CI Verdict", status="IN_PROGRESS", conclusion=None, run=2),
        ],
    )
    g = ci_gate(verdict_live)
    check(
        "CONTROL: Publish CI Verdict failing and CI Verdict in flight (GitHub rollup PENDING) is "
        "still green -- neither is live, neither is hard",
        g["verdict"] == "green" and not g["live"] and not g["hard"],
        "gate=%r" % (g,),
    )
    review_red = dict(
        full,
        contexts=[*full_ctx, run_ctx("Review Complete", conclusion="FAILURE", run=3)],
    )
    g = ci_gate(review_red)
    check(
        "operator ruling 2026-10-03: CI Complete green with Review Complete failing is red -- "
        "Review Complete is a required check again, and it is the one hard failure",
        g["verdict"] == "red" and [r["name"] for r in g["hard"]] == ["Review Complete"],
        "gate=%r" % (g,),
    )
    review_pending = dict(
        full,
        rollup="PENDING",
        contexts=[
            *full_ctx,
            run_ctx("Review Complete", status="IN_PROGRESS", conclusion=None, run=3),
        ],
    )
    g = ci_gate(review_pending)
    check(
        "operator ruling 2026-10-03: CI Complete green with Review Complete in flight is running",
        g["verdict"] == "running" and g["live"] and not g["hard"],
        "gate=%r" % (g,),
    )
    review_jobs = dict(
        full,
        rollup="PENDING",
        contexts=[
            *full_ctx,
            run_ctx("Claude Review", status="IN_PROGRESS", conclusion=None, run=4),
            run_ctx("Review Status", conclusion="FAILURE", run=5),
        ],
    )
    g = ci_gate(review_jobs)
    check(
        "CONTROL: CI Complete green with Review Status failing and Claude Review in flight is "
        "green -- the review's jobs report through Review Complete, never on their own",
        g["verdict"] == "green" and not g["live"] and not g["hard"],
        "gate=%r" % (g,),
    )
    review_gate_red = dict(
        full,
        contexts=[*full_ctx, run_ctx("Review Gate", conclusion="FAILURE")],
    )
    g = ci_gate(review_gate_red)
    check(
        "CONTROL: a failing Review Gate (a real Console CI job) still reads red",
        g["verdict"] == "red" and [r["name"] for r in g["hard"]] == ["Review Gate"],
        "gate=%r" % (g,),
    )
    cancelled = dict(
        full,
        contexts=[run_ctx("Quality / Code"), run_ctx("E2E / x", conclusion="CANCELLED")],
    )
    g = ci_gate(cancelled)
    check(
        "a cancelled blocking context with nothing failing is red and names its run",
        g["verdict"] == "red" and g["cancelled"][0]["run"] == 36953549081,
        "gate=%r" % (g,),
    )
    check(
        "CONTROL: require_complete=False (a Release run) is green without CI Complete",
        ci_gate(false_green, require_complete=False)["verdict"] == "green",
    )
    check(
        "ci_cancel_note stays SILENT on an unattributed cancel (test_122) and speaks on a budget one",
        ci_cancel_note({"info": cancelled, "cause": {"kind": "unknown"}}) == ""
        and "watchdog-budget"
        in ci_cancel_note(
            {"info": cancelled, "cause": {"kind": "watchdog-budget", "detail": "'x' ran 21m"}}
        ),
    )

    return check.verdict("ci")


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else 0)
