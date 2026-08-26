"""wl_ci: publish-ref divergence, PR-body freshness, submodule pointer moves,
and the v10 open-PR CI-trouble check. Pure movement from worklist.py; every
branch here is paid for by an observed failure, so nothing was "simplified"
in the extraction.
"""

import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import time

import wl_core as C
import wl_store as S

_git = C._git


def publish_divergence(root):
    """(state, count, ref) -- has the branch we publish to moved without us?

    OPERATOR'S RULE, "do not trust, verify". This session commits on a LOCAL
    branch and publishes with `git push origin HEAD:<other-branch>`, so the two
    names can diverge silently: another session, or a merge on the remote, puts
    commits on the published ref that local HEAD does not contain, and the next
    push either fails confusingly or publishes over work nobody looked at.

    The dangerous direction is remote-ahead. Local-ahead is just unpushed work.
    """
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return "unknown", 0, ""
    # The published ref is whatever the PR is on; default to the sibling name the
    # session pushes to, overridable for other setups.
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
    # THE SECOND TRAP, found by a verification agent rather than by reasoning: a
    # LOCAL branch sharing the publish target's name, left behind by an earlier
    # rename. Nothing in the publish flow touches it, so it rots invisibly; the
    # cost lands on whoever checks it out next and pushes from a stale base.
    if _git(root, "rev-parse", "--verify", "--quiet", target):
        behind = _git(root, "rev-list", "--count", ref, "^%s" % target)
        unique = _git(root, "rev-list", "--count", target, "^%s" % ref)
        if behind.isdigit() and int(behind) > 0:
            return "stale-local", int(behind), "%s (local, %s unique)" % (target, unique or "?")
    return "ok", 0, ref


def pr_body_freshness(root):
    """(state, detail) -- did we push after the last PR-description edit?

    FAIL FAST TO SAVE A CI ROUND. `Quality / Static` runs a PR-description
    freshness gate, and the cost of failing it is a full ~55-minute round for a
    mistake that takes ten seconds to fix. This session has made it twice, both
    times by treating the body refresh as a separate step instead of part of the
    push, which its own memory says not to do.

    Scoped to WORKLIST_PUBLISH_REF, so a session that has not opted in pays
    nothing. When it IS set and the lookup fails, that is reported as a hook-side
    inability rather than passing quietly.
    """
    target = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not target:
        return "unset", ""
    tip = _git(root, "log", "-1", "--format=%cI", "origin/%s" % target)
    if not tip:
        return "no-ref", "origin/%s" % target
    # GRAPHQL, NOT `gh pr list --json lastEditedAt`. That field does not exist on
    # `pr list` OR on `pr view` -- both error out and print the valid-field list.
    # This check found that itself on its first run, by reporting the failure as
    # a blind read instead of passing quietly, which is the whole argument for
    # making blindness its own verdict.
    slug = _git(root, "config", "--get", "remote.origin.url")
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", slug or "")
    if not m:
        return "unreadable", "could not derive owner/name from %r" % slug
    query = (
        '{repository(owner:"%s",name:"%s"){pullRequests('
        'headRefName:"%s",states:OPEN,first:1){nodes{number lastEditedAt updatedAt}}}}'
        % (m.group(1), m.group(2), target)
    )
    try:
        out = subprocess.run(
            ["gh", "api", "graphql", "-f", "query=" + query],
            capture_output=True,
            text=True,
            timeout=25,
            cwd=str(root),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "unreadable", str(exc)[:120]
    if out.returncode != 0:
        return "unreadable", (out.stderr or "")[-120:]
    try:
        rows = json.loads(out.stdout)["data"]["repository"]["pullRequests"]["nodes"]
    except (ValueError, KeyError, TypeError):
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
# THE ASK: "if there is only one active session and if there is an open PR for
# the current branch, then stop hook should check the PR green/red status and
# give feedback to make it green ... if there is no gh cli watch in the
# background."
#
# WHAT THIS IS NOT. It is deliberately NOT "block while conclusion != success".
# That shape was tried in the head, against one night of real runs, and it nags
# four times about nothing:
#
#   * CANCELLED IS NOT RED. Four runs that night ended `cancelled` with ZERO
#     failed jobs, each superseded by this session's own next push. And the
#     watchdog FORCE-CANCELS a run when a real gate fails, so `cancelled` also
#     means "something genuinely failed". The run-level rollup cannot tell those
#     apart, so nothing here ever reads it as a verdict: every judgement comes
#     from PER-JOB conclusions (run 30514648812 was `cancelled` with
#     `Quality / Static` = failure; run 30513152662 was `cancelled` with none).
#   * A RUN THAT IS STILL GROWING IS NOT FINAL. Job count climbed 18 -> 37 -> 79
#     -> 92 -> 95 inside one run. So nothing here ever concludes GREEN from a
#     partial list. It only ever speaks about jobs that have ALREADY COMPLETED
#     with a failing conclusion, which is a fact no later job can retract.
#   * THE WATCHDOG MAY ALREADY BE FIXING IT. Jobs matching
#     WATCHDOG_RETRY_ALLOWLIST_PATTERNS (.github/workflows/watchdog-monitor.yml)
#     are auto-retried onto the SAME run as a later attempt. Telling the session
#     to investigate a leg that is about to be rerun burns a whole round; that
#     night an opensuse E2E leg failed on a Docker Hub CDN reset, was retried,
#     and the run went green at 95 jobs. Those failures are REPORTED, never
#     blocked on, until the run is final and they are still red.
#
# The output is a HANDOVER OF FACTS, in the shape submodule_pointer_moves() uses:
# the failing job, its failing STEP, its run and attempt, and the exact command
# that reads its log. "CI is red" alone is noise; a session cannot brief a
# sub-agent with it.
CI_RETRY_PATTERNS = [
    p.strip()
    for p in os.environ.get(
        "WORKLIST_CI_RETRY_PATTERNS", "E2E,OPS,Fork Isolation,Migration Test"
    ).split(",")
    if p.strip()
]
# PER-JOB conclusions that mean "this genuinely failed". CANCELLED, SKIPPED,
# NEUTRAL and STALE are deliberately absent: see the CANCELLED note above.
CI_FAIL_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}
CI_LIVE_ROLLUP = {"PENDING", "EXPECTED"}
# Cost control (this hook runs on EVERY stop, including a 5-minute poll cron).
# Keyed on the published tip SHA, so any push invalidates it immediately.
CI_CACHE_LIVE_S = int(os.environ.get("WORKLIST_CI_CACHE_LIVE_S", "180"))
CI_CACHE_FINAL_S = int(os.environ.get("WORKLIST_CI_CACHE_FINAL_S", "900"))
# THE DEADLOCK CEILING. See ci_trouble()'s docstring.
CI_MAX_BLOCKS = int(os.environ.get("WORKLIST_CI_MAX_BLOCKS", "2"))
CI_MAX_PAGES = 3
CI_STEP_LOOKUPS = 2


def repo_slug(root):
    """(owner, name) from remote.origin.url, or (None, None)."""
    url = _git(root, "config", "--get", "remote.origin.url")
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _gh_json(root, args, timeout=25):
    """(data, error) from `gh <args>`. Never raises; an error is a STRING, so
    every caller can report blindness instead of guessing."""
    try:
        out = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)[:160]
    if out.returncode != 0:
        return None, (out.stderr or out.stdout or "gh exited %d" % out.returncode)[-160:]
    try:
        data = json.loads(out.stdout)
    except ValueError:
        return None, "non-JSON from `gh %s`: %r" % (" ".join(args[:2]), out.stdout[:80])
    # GraphQL reports field errors with exit 0 and an `errors` array.
    if (
        isinstance(data, dict)
        and data.get("errors")
        and not (data.get("data") or {}).get("repository")
    ):
        return None, json.dumps(data["errors"])[:160]
    return data, ""


def ci_query(owner, name, ref, cursor):
    """The ONE read. statusCheckRollup rather than checkSuites.checkRuns on
    purpose: the rollup exposes the LATEST check run per context, so a watchdog
    rerun replaces the failed attempt rather than appearing beside it. That is
    what makes a rerun-in-flight read as IN_PROGRESS here, and this check go
    quiet by itself while the watchdog works."""
    after = ',after:"%s"' % cursor if cursor else ""
    return (
        '{repository(owner:"%s",name:"%s"){pullRequests(headRefName:"%s",states:OPEN,first:1)'
        "{nodes{number url isDraft commits(last:1){nodes{commit{oid statusCheckRollup{state "
        "contexts(first:100%s){totalCount pageInfo{hasNextPage endCursor} nodes{__typename "
        "... on CheckRun{name status conclusion databaseId detailsUrl "
        "checkSuite{workflowRun{databaseId}}} "
        "... on StatusContext{context state targetUrl}}}}}}}}}}}"
    ) % (owner, name, ref, after)


def ci_branch_query(owner, name, ref, cursor):
    """The SAME rollup, read from the branch instead of from a PR.

    `main` after a merge has no open PR, so ci_query's pullRequests(...) selector
    returns zero nodes and the reader goes blind at exactly the point /pr-merge
    step 5 needs it. The context selection set below is deliberately identical to
    ci_query's: this is a second SOURCE for one payload, never a second
    implementation of the reader.
    """
    after = ',after:"%s"' % cursor if cursor else ""
    return (
        '{repository(owner:"%s",name:"%s"){ref(qualifiedName:"refs/heads/%s")'
        "{target{... on Commit{oid statusCheckRollup{state "
        "contexts(first:100%s){totalCount pageInfo{hasNextPage endCursor} nodes{__typename ... on CheckRun{name status conclusion databaseId detailsUrl checkSuite{workflowRun{databaseId}}} ... on StatusContext{context state targetUrl}}}}}}}}}"
    ) % (owner, name, ref, after)


def ci_rollup(root, ref, allow_branch=False):
    """(state, info) -- one paged read of the check rollup for `ref`.

    state is ok | no-pr | no-ref | unreadable. `unreadable` is a real verdict, in
    the V_PR_UNREADABLE style: a check that cannot see must SAY SO.

    allow_branch DEFAULTS TO FALSE AND MUST STAY THAT WAY. The Stop hook reads
    `no-pr` as a meaningful answer -- "this branch has no PR to be current with"
    -- so silently substituting a branch read would CHANGE that check's meaning
    rather than extend it. Only a caller that explicitly named a ref opts in.
    """
    owner, name = repo_slug(root)
    if not owner:
        return "unreadable", "could not derive owner/name from remote.origin.url"
    state, info = _rollup_pr(root, owner, name, ref)
    if state == "no-pr" and allow_branch:
        return _rollup_branch(root, owner, name, ref)
    return state, info


def _rollup_pages(root, owner, name, ref, build_query, extract, source):
    """Page ONE rollup source into the common payload.

    Both sources share this loop so CI_MAX_PAGES and the `truncated` flag cannot
    drift apart between them -- a partial read that forgot to say it was partial
    is the vacuity failure this reader exists to avoid.

    `extract(data)` returns (terminal_state, commit, pr) -- terminal_state is
    None to continue paging.
    """
    contexts, cursor, commit, pr, roll = [], None, None, None, None
    truncated = True
    for _ in range(CI_MAX_PAGES):
        data, err = _gh_json(root, ["api", "graphql", "-f", "query=" + build_query(cursor)])
        if data is None:
            return "unreadable", err
        terminal, commit, pr = extract(data)
        if terminal:
            return terminal, ref if terminal in ("no-pr", "no-ref") else commit
        roll = (commit or {}).get("statusCheckRollup")
        if not roll:
            # No checks registered on this head yet. Not a verdict and not
            # blindness: an empty context list simply produces silence below.
            truncated = False
            break
        ctx = roll.get("contexts") or {}
        contexts.extend(ctx.get("nodes") or [])
        page = ctx.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            truncated = False
            break
        cursor = page.get("endCursor")
    return "ok", {
        "owner": owner,
        "name": name,
        "source": source,
        "pr": (pr or {}).get("number"),
        "url": (pr or {}).get("url") or "",
        # Carried so a GREEN verdict can name the next action. A reader must not
        # flip the PR itself -- several watches can be armed at once and the
        # ready-flip spends real review budget -- but it CAN stop the finish
        # sequence depending on the agent remembering it exists.
        "draft": bool((pr or {}).get("isDraft")),
        "sha": (commit or {}).get("oid") or "",
        "rollup": ((roll or {}).get("state") or "EXPECTED"),
        "total": (((roll or {}).get("contexts") or {}).get("totalCount") or len(contexts)),
        "contexts": contexts,
        "truncated": truncated,
    }


def _rollup_pr(root, owner, name, ref):
    def extract(data):
        try:
            nodes = data["data"]["repository"]["pullRequests"]["nodes"]
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

    # `extract` returns its unreadable reason in the commit slot, which
    # _rollup_pages passes straight through as `info`.
    return _rollup_pages(
        root, owner, name, ref, lambda c: ci_query(owner, name, ref, c), extract, "pr"
    )


def _rollup_branch(root, owner, name, ref):
    def extract(data):
        try:
            node = data["data"]["repository"]["ref"]
        except (KeyError, TypeError):
            return "unreadable", "graphql response had no repository.ref", None
        if not node:
            # A ref that does not exist is NOT the same answer as a ref with no
            # checks, and conflating them is how a typo reads as a clean run.
            return "no-ref", None, None
        target = node.get("target") or {}
        if not target.get("oid"):
            return "unreadable", "ref %r resolved to a non-commit target" % ref, None
        return None, target, None

    return _rollup_pages(
        root,
        owner,
        name,
        ref,
        lambda c: ci_branch_query(owner, name, ref, c),
        extract,
        "branch",
    )


def ci_classify(info):
    """(live, hard, soft) from PER-JOB conclusions only.

    `live` means the head still has work in flight, which is the ONLY thing the
    run-level rollup is used for -- never as a pass/fail verdict.

    A completed failing job whose name matches the watchdog's retry allowlist is
    SOFT while the head is live, because a retry may be inbound. Once the head
    is final and it is STILL failing, the watchdog is done with it and it is
    hard, which is the difference between "wait" and "go read the log".
    """
    rows, pending = [], 0
    for c in info.get("contexts") or []:
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
    live = pending > 0 or str(info.get("rollup") or "").upper() in CI_LIVE_ROLLUP
    hard, soft = [], []
    for row in rows:
        retryable = any(p.lower() in row["name"].lower() for p in CI_RETRY_PATTERNS)
        (soft if (live and retryable) else hard).append(row)
    return live, hard, soft


# v12 (operator, 2026-07-30): "hook should detect that is current session
# sitting for CI pipeline? If so, it should FORCE current session to work on
# waiting items!!!" The shape of a CI watch, matched against a background
# task's command + description. Deliberately CONSERVATIVE: `gh run watch`,
# an Actions run URL/path, a run-id-sized number near "watch", or "CI" near
# "watch". A dev file-watcher (`npm run watch`) matches none of these, and a
# false positive here turns a working session's stop into an accusation.
CI_WATCH_RE = re.compile(
    r"gh\s+run\s+watch"
    r"|actions/runs/\d+"
    r"|\bci\b[^\n]{0,40}\bwatch|\bwatch\w*\b[^\n]{0,40}\bci\b"
    r"|\bwatch\w*\b[^\n]{0,40}\b\d{9,}\b|\b\d{9,}\b[^\n]{0,40}\bwatch\w*\b",
    re.IGNORECASE,
)


def ci_watch_only(live_bg):
    """(watching, description) -- is watching CI the ONLY thing in flight?

    True only when at least one RUNNING background task matches the CI-watch
    shape and EVERY running background task does. One non-watch worker means
    the session has real work delegated and is not merely sitting; no tasks
    at all means there is nothing being waited on and the idle detector owns
    that case. The description names the watches so the block can quote them.
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


# The sanctioned CI reader. A watch that is not this is a hand-rolled loop, and
# hand-rolled loops failed four ways on 2026-08-25 while landing console#574:
# a stale recipe in nine places, a verdict from a SUPERSEDED attempt, a verdict
# from a run a later push had cancelled, and a network blip that only a
# correctly-written retry arm survived. See .ci/scripts/ci/ci-trace.py.
def _sanctioned_match(blob):
    """True when the blob carries a shape the sanctioned registry replaces.

    Imported lazily and defensively: this module runs on every stop, and a
    missing or broken registry must not take the whole hook down with it.
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


# Does this blob touch GitHub at all? Something that cannot be a CI watch is not
# one, however much it says "watch".
GH_EVIDENCE_RE = re.compile(r"\bgh\b|actions/runs/\d+|ci-trace", re.IGNORECASE)

CI_TRACE_RE = re.compile(r"ci-trace(?:\.py)?\b", re.IGNORECASE)


def adhoc_watch(live_bg):
    """(task_id, blob) for a RUNNING background task watching CI by hand, or ("","").

    "By hand" means: it looks like a CI watch (CI_WATCH_RE, the same shape the
    idle checks already use) and it is NOT ci-trace.py. The caller blocks the
    turn on this, which is safe to make unconditional -- unlike ci_trouble, the
    remedy is entirely within the session's reach: stop the task and run the
    script. Nothing another session's push or an infrastructure flake can do
    makes this unfixable, so there is no ceiling and no escape hatch.
    """
    for b in live_bg or []:
        blob = "%s %s" % (b.get("command") or "", b.get("description") or "")
        if CI_TRACE_RE.search(blob):
            continue
        # TWO detectors, because each alone has a hole. CI_WATCH_RE is
        # deliberately conservative (it also drives the idle checks, where a
        # false positive turns a working session's stop into an accusation) and
        # misses a bare `gh run view` poll with no "watch" word in it. The
        # sanctioned registry catches exactly that shape -- and sharing it is
        # the point: the pre-bash guard and this check then cannot disagree
        # about what counts as hand-rolled, which is the class of drift this
        # whole change exists to end.
        # EVIDENCE OF GITHUB, not merely the word "watch". CI_WATCH_RE also
        # matches "watch" sitting near any 9+ digit number, and a worklist
        # fixture named `sleep 3717171718 silent watch` -- a generic background
        # worker with no gh call anywhere in it -- was blocking the turn. A
        # guard that stops unrelated work is a guard that gets removed.
        if not GH_EVIDENCE_RE.search(blob):
            continue
        if CI_WATCH_RE.search(blob) or _sanctioned_match(blob):
            return str(b.get("id") or "?"), blob.strip()[:160]
    return "", ""


def ci_watch_armed(live_bg, rows, sha):
    """The id of a RUNNING background task watching THIS head, or "".

    NOT "is some task running". A completed watch reported `completed/cancelled`
    for a run that had since been superseded, and another reported a FALSE
    failure because a watchdog rerun flipped a terminal run back to in_progress.
    So the test is: still running (the caller passes only those) AND naming this
    head's run id or SHA. A bare `gh run watch` with no id does not count -- it
    cannot be shown to be about this run.
    """
    needles = [str(r["run"]) for r in rows if r.get("run")]
    if sha:
        needles.append(sha[:12])
    for b in live_bg or []:
        blob = "%s %s" % (b.get("command") or "", b.get("description") or "")
        # THE SANCTIONED READER IS ALWAYS ABOUT THIS HEAD, so it needs no
        # needle. ci-trace.py resolves the PR from the current branch and pins
        # the head it starts on, exiting 3 if a push moves it -- it cannot be
        # watching a stale run, which is the only thing the needle test ever
        # guarded against. An explicit --ref points it elsewhere, so that form
        # still has to prove itself the ordinary way.
        if CI_TRACE_RE.search(blob) and "--ref" not in blob:
            return str(b.get("id") or (b.get("description") or "")[:60])
        if any(n and n in blob for n in needles):
            return str(b.get("id") or (b.get("description") or "")[:60])
    return ""


def ci_steps(root, info, rows, cached):
    """Fill in `step` and `attempt` for the first few failing jobs.

    ONE bounded REST call per job, and only on the path that is about to speak.
    `gh run view --log-failed` is deliberately not used anywhere here: it is
    RUN-scoped even with --job, refuses while the run is in progress, and writes
    the reason to stderr, so a 2>/dev/null capture reads as an empty log.
    """
    for row in rows[:CI_STEP_LOOKUPS]:
        key = str(row.get("job") or "")
        if not key:
            continue
        if key in cached:
            row["step"], row["attempt"] = cached[key]
            continue
        data, _err = _gh_json(
            root,
            ["api", "repos/%s/%s/actions/jobs/%s" % (info["owner"], info["name"], key)],
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


# ---- v13: CI-queue-aware backpressure ---------------------------------------
# OPERATOR (2026-07-31): "CI side has stuck because of many commits. They're in
# the queue. For that situation stop hook should be smart to avoid pushing the
# system in such cases... there could be possibility that allow us to work
# locally until we see CI result to save time." Observed live the same night:
# a Console CI run sat status=pending for 25+ minutes because pushes had queued
# runs behind each other; every further push made the jam strictly worse while
# buying nothing, since only the newest head's result matters.
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
    the observed failure is OLDER runs jamming the queue behind the newest
    push, and the rollup only sees the head. Saturated iff the newest run has
    sat in a queued-family status for CI_QUEUE_MIN minutes, or CI_QUEUE_DEPTH
    or more runs are queued at once. A newest run that is in_progress with an
    empty queue is `clear`: a result is coming, normal discipline stands.

    FAILURE MODE IS A DELIBERATE INVERSION of the blocks-when-blind rule that
    governs the other CI checks. This check only ever GRANTS slack (permission
    to hold pushes), so blindness must fail toward pressure: gh broken, slug
    underivable, or non-JSON all return `unknown`, which callers treat exactly
    like today's behavior -- no note, no relaxation. A blind slack-granter
    would be an escape hatch. `unknown` is cached too, so a broken gh costs
    one call per TTL, not one per stop.
    """
    ref = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not ref:
        return "unset", None
    cache_p = ciqueue_path(worklist, session_id)
    try:
        c = json.loads(cache_p.read_text(encoding="utf-8"))
        if time.time() - (c.get("at") or 0) <= CI_QUEUE_CACHE_S:
            return c.get("state") or "unknown", c.get("detail")
    except (OSError, ValueError, TypeError):
        pass
    owner, name = repo_slug(root)
    state, detail = "unknown", None
    if owner:
        data, err = _gh_json(
            root,
            ["api", "repos/%s/%s/actions/runs?branch=%s&per_page=10" % (owner, name, ref)],
            timeout=20,
        )
        runs = (data or {}).get("workflow_runs") if isinstance(data, dict) else None
        if runs is None and err:
            # SAY WHY, rather than reporting a bare "unknown". A failed gh call
            # and a genuinely empty queue used to be indistinguishable here,
            # which is the blindness this program refuses everywhere else.
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
    with contextlib.suppress(OSError, TypeError):
        cache_p.write_text(
            json.dumps({"at": time.time(), "state": state, "detail": detail}),
            encoding="utf-8",
        )
    return state, detail


def ci_trouble(root, worklist, session_id, live_bg, ack_text):
    """(state, detail) -- is the open PR in trouble nobody is on?

    state: unset | multi-session | no-pr | ok | watched | soft | trouble |
           downgraded | unreadable

    THE ESCAPE, and why this one. A check that demands what a session cannot
    produce deadlocks it: one did exactly that for a whole night here, blocking
    every stop until morning. So there are TWO exits, and the second is
    unconditional:

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

    A NEW failure set (new head SHA, or a different set of failing jobs) re-arms
    the budget: a new red is worth interrupting for exactly once more.
    """
    ref = os.environ.get("WORKLIST_PUBLISH_REF", "")
    if not ref:
        return "unset", None  # not opted in: zero network cost, same as pr_body_freshness
    if not S.sole_live_session(worklist, session_id):
        # With a second live session, red may be their push, and nagging this
        # session about someone else's work is the failure mode to avoid.
        return "multi-session", None
    tip = _git(root, "rev-parse", "origin/%s" % ref)
    if not tip:
        return "no-pr", "origin/%s" % ref
    cache_p, marker_p = cistate_path(worklist, session_id), cimark_path(worklist, session_id)
    cache = None
    try:
        c = json.loads(cache_p.read_text(encoding="utf-8"))
        ttl = CI_CACHE_FINAL_S if c.get("final") else CI_CACHE_LIVE_S
        if c.get("sha") == tip and time.time() - (c.get("at") or 0) <= ttl:
            cache = c
    except (OSError, ValueError, TypeError):
        cache = None
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
        _ci_cache_write(cache_p, tip, state, info, steps, final=not live)
        return "ok", info
    watcher = ci_watch_armed(live_bg, hard + soft, info.get("sha") or tip)
    if watcher:
        # The operator's own condition, and deliberately NOT gated on the run
        # still being live. A watch keyed to this run is a wake-up whether the
        # run is finishing or already finished; the window where a RUNNING watch
        # coexists with a final run is the seconds before its last iteration
        # prints, and firing into that window is a false alarm, not diligence.
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
    try:
        mark = json.loads(marker_p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        mark = {}
    blocks = int(mark.get("blocks") or 0) if mark.get("sig") == sig else 0
    detail = {"info": info, "hard": hard, "soft": soft, "live": live, "acked": acked, "n": blocks}
    if acked or blocks >= CI_MAX_BLOCKS:
        return "downgraded", detail
    with contextlib.suppress(OSError):
        marker_p.write_text(json.dumps({"sig": sig, "blocks": blocks + 1}), encoding="utf-8")
    detail["n"] = blocks + 1
    return "trouble", detail


def _ci_cache_write(path, sha, state, info, steps, final):
    with contextlib.suppress(OSError, TypeError):
        path.write_text(
            json.dumps(
                {
                    "sha": sha,
                    "at": time.time(),
                    "state": state,
                    "info": info,
                    "steps": steps,
                    "final": bool(final),
                }
            ),
            encoding="utf-8",
        )


def ci_rows_text(rows, info):
    """One line per failing job, plus the log incantation that actually works
    on a completed job inside a live run."""
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
            out.append(
                "        gh api repos/%s/%s/actions/jobs/%s/logs"
                % (info["owner"], info["name"], r["job"])
            )
        elif r.get("url"):
            out.append("        %s" % r["url"])
    return "\n".join(out)


def submodule_pointer_moves(root):
    """[(path, recorded_sha, worktree_sha, where)] for dirty gitlinks.

    DELIBERATELY LOCAL. Every fact here comes from git in the working tree, so
    this check cannot go "unreadable" on a network failure the way the PR
    freshness check can. `where` is the containing-remote-branch summary, which
    is the fact that actually decides the call: a pointer on the submodule's
    default branch is an ordinary bump, while one that exists only on a feature
    branch adds that branch's PR to this PR's merge chain.

    `git submodule status` marks a checked-out commit that differs from the
    index with a leading '+'. That is precisely the state a blind `git add -A`
    would convert into a committed dependency change.
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
        # --contains over REMOTE branches only: a local-only branch proves
        # nothing about what CI can fetch.
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
