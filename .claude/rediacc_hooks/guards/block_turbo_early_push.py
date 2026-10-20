"""Refuse an early `git push` or `gh pr create` under turbo while a Promoted plan is unfinished, unless the command names an operational reason.

THE ORDER (operator, 2026-10-08): "push should be blocked when: a) turbo is on b) there are still plans that not completed at ## Promoted, QUEUE.md c) there is no real operational reason to push when a & b is there. For example, the plan may need CI/CD check etc." This is box LF-guard of agent/plans/PLAN-turbo-local-first.md. Under turbo, local completion is the default: a batch finishes on this machine and is pushed once.

THE THREE CONDITIONS, each read through the reader the Stop hook and the merge gate already use, never a second copy:

  (a) `turbo: on` in agent/plans/QUEUE.md `## Settings`, read by `plan_gate.settings_at` (the one parser, `wl_planqueue.settings`).
  (b) a plan listed under `## Promoted` (`wl_planqueue.entries`) with an open box, counted by `plan_gate.open_boxes` (`wl_planfile.plan_boxes` cross-checked against the raw line count; a `Moved-To:` stub is followed). An entry whose file is gone is looked for under `agent/plans/_done/`; a plan with no boxes has no open box.
  (c) no operational reason on the command. The reason is an environment assignment on the push itself, read from the shared lexer's walk (`run.env`), so a prefix, an `export` earlier in the same command and an `env NAME=value` all count, and prose naming it does not:

      TURBO_PUSH_REASON='<kind>: <why, 20+ chars>' git push -u origin <branch>

    ci-cd     a plan needs a check only CI/CD runs; the why names the plan (basename or slug) and its box
    red-fix   a fix for a red on the live PR; an OPEN PR for the branch must exist (`gh pr list --head`)
    deadline  production or CD state that cannot wait; the why names it
    backup    the oldest unpushed commit (`origin/<branch>..HEAD`, or `origin/main..HEAD` before the first push) is older than `backup_push_h` hours (QUEUE.md, default 4; 0 turns the valve off). Never admits `gh pr create`: a backup is a push with no PR, which triggers no CI.

  Each admitted command appends one JSON line per push or create to agent/ledgers/turbo-push-reasons.jsonl in the console checkout (ts, branch, repo, act, kind, why, head, open_promoted), written only once every act in the command is admitted. This guard is NOT last in the chain: guards at ORDER 58 to 62 run after it, so a line here records turbo's admission only, and a later guard (`block_vm_unverified_push` at 62, among others) can still refuse the push it logged.

A COMPLETE BATCH NEEDS NO REASON (operator ruling ASKED:2026-10-08T10:25Z, on "how should a finished turbo batch push?": "It should not be even askable also for other/future sessions as well"). Before this the Stop hook's V_LOOP_NEXT_BATCH_OPEN ordered the push and `gh pr create` of a finished local batch while this guard refused both for want of a reason (11 Promoted plans, batch_size 3), and that gap is what put the question to the operator. Now, when a command would be refused, the branch's local batch is read through the Stop hook's own predicates (`_batch`: `wl_prscope.loop_state`, `wl_checks.local_batch`, `wl_checks.local_batch_open`), and a complete batch admits every push and `gh pr create` of the command with ledger kind `batch-complete`. A batch still open keeps the refusal, which names its open boxes (and the queued plan it still takes, when every box is ticked) so the session works instead of asking. A live PR, `turbo_push: pr`, and a PR read that failed are not a filling local batch and keep today's rules. A batch reader that raises or will not import fails open, loudly, as the queue readers do. Push timing is therefore never the operator's question; `block_settled_questions` refuses it on the pre-ask chain.

SCOPE. Every `git push` (any remote or refspec, `-C`/`cd` included) in this checkout or a submodule under it, and every `gh pr create`. NOT judged: a `--dry-run` push (publishes nothing); a delete push (`--delete`, `:<branch>`: the M6 cleanup after a merge); a push whose every destination is `main` (the fast-forward fallback and the GitLab mirror push, which `block_push_to_protected_branch` admits only on a merged-ready PR); a repository outside this checkout.

THE MERGE PHASE'S POINTER BUMP NEEDS NO REASON (worklist item #8aad9216). `/pr-merge` step 2 pushes the console's submodule pointer bump (and the review records committed for it) to the PR branch, and under turbo that push was refused (`ci-cd` names no open Promoted plan) until a `deadline:` reason was borrowed for it. A plain push is now admitted, ledger kind `merge-pointer-bump`, when BOTH hold: the pushing session's newest phase event (`wl_store.phase_fold` and `wl_standdown.active_phase`, the read `block_focus_spawn` uses, lineage included, the 24-hour cap applied) is `merge` with `branch` equal to the checkout's branch; and every commit of the unpushed range (`origin/<branch>..HEAD`, or `origin/main..HEAD` before the first push), none of them a merge, changes only submodule gitlinks (mode 160000) and paths under `agent/reviews/`. Every destination of the push must be that branch. It FAILS CLOSED: a phase or range that cannot be read admits nothing and the push meets the rules above. Never `gh pr create`.

THE OPERATOR. There is no override token, the convention of every pre-bash guard (`block_second_branch`, `block_git_hook_bypass`): the operator's own `!` command bypasses PreToolUse hooks entirely, so it never reaches this guard.

FAILS OPEN, LOUDLY, when QUEUE.md or a plan cannot be read, or `wl_planqueue` cannot import: a note on stderr, the push allowed, like the sibling guards. `gh` failing on a `red-fix` admits with a note. A `backup` whose age cannot be read is REFUSED: the age is the claim, and an unread claim is not a checked one.
"""

import datetime
import json
import pathlib
import re
import time

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan, syspath

CHAIN = "pre-bash"
OWN_SUITE = True
# Not last in the pre-bash chain (58 to 62 follow): the ledger line records turbo's own admission, and a later guard can still refuse the command.
ORDER = 57

# The open-plan test, read the other way round: planted, the guard admits every push once the queue has been read, reason or none, which is the guard body switched off.
DEFECT = ("if not open_plans:", "if True:")

REASON_ENV = "TURBO_PUSH_REASON"
KINDS = ("ci-cd", "red-fix", "deadline", "backup")
# The ledger kind of a push or PR the hooks released because the local batch is complete; never a TURBO_PUSH_REASON kind, since it needs no reason.
BATCH_KIND = "batch-complete"
# The ledger kind of a `/pr-merge` pointer-bump push the merge phase released (see THE MERGE PHASE above); never a TURBO_PUSH_REASON kind.
MERGE_KIND = "merge-pointer-bump"
MERGE_PATH_PREFIX = "agent/reviews/"
GITLINK_MODES = ("160000", "000000")
REVIEW_MODES = {"100644", "100755", "000000"}
MIN_WHY = 20
DEFAULT_BACKUP_H = 4
LEDGER_REL = "agent/ledgers/turbo-push-reasons.jsonl"
QUEUE_REL = plan_gate.QUEUE_REL
REASON_RE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$", re.DOTALL)

UNREAD = "block-turbo-early-push: %s; this push passed UNEXAMINED."


def _git(path, *argv, env_date=None):
    # Fixture builders only; the imports stay inside the function that builds them.
    import os
    import subprocess

    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    if env_date:
        env["GIT_AUTHOR_DATE"] = env_date
        env["GIT_COMMITTER_DATE"] = env_date
    subprocess.run(["git", *argv], cwd=str(path), check=True, capture_output=True, env=env)


FIXTURE_QUEUE = (
    "# Queue\n\n## Settings\n\n```stop-hook\neffort: high\nturbo: %s\nbackup_push_h: 4\n```\n\n"
    "## Promoted\n\n1. agent/plans/PLAN-fx-a.md -- a fixture plan\n"
)
FIXTURE_PLAN = (
    "# PLAN: fx\n\nStatus: in-progress\nDepends-On: no-dep -- a fixture plan\n"
    "Owns: docs/fixture.md\nConcurrency: parallel\n\n## Tasks\n\n%s"
)


def world(
    path,
    turbo="on",
    box="- [ ] FX1 an open box\n",
    date="2026-01-01T00:00:00+00:00",
    more=(),
    settings="",
):
    """A console-shaped repository on `1008-1`: QUEUE.md with `turbo` (plus any `settings` lines), the Promoted plan PLAN-fx-a holding `box` and one more Promoted plan PLAN-fx-<slug> per `(slug, box)` in `more`, a GitHub-shaped `origin` URL (the Stop hook's PR read derives owner/name from it), `origin/main` at the seed and one unpushed commit made at `date`. With PLAN-fx-a ticked and `batch_size` 1 (the default) the branch's local batch is complete while a later Promoted plan is still open."""
    path = pathlib.Path(path)
    (path / "agent" / "plans").mkdir(parents=True)
    queue = FIXTURE_QUEUE % turbo
    if settings:
        queue = queue.replace("backup_push_h: 4\n", "backup_push_h: 4\n%s" % settings)
    for n, (slug, more_box) in enumerate(more, start=2):
        queue += "%d. agent/plans/PLAN-fx-%s.md -- a fixture plan\n" % (n, slug)
        (path / ("agent/plans/PLAN-fx-%s.md" % slug)).write_text(
            FIXTURE_PLAN % more_box, encoding="utf-8"
        )
    (path / QUEUE_REL).write_text(queue, encoding="utf-8")
    (path / "agent/plans/PLAN-fx-a.md").write_text(FIXTURE_PLAN % box, encoding="utf-8")
    _git(path, "init", "-q", "--initial-branch=main")
    _git(path, "remote", "add", "origin", "https://github.com/fixture/console.git")
    _git(path, "commit", "-q", "--allow-empty", "-m", "seed", env_date=date)
    _git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(path, "checkout", "-q", "-b", "1008-1")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "work", env_date=date)
    return path


FIXTURES = {
    "turbo-open-old": world,
    "turbo-open-fresh": lambda p: world(p, date=datetime.datetime.now(datetime.UTC).isoformat()),
    "turbo-done": lambda p: world(p, box="- [x] FX1 a ticked box\n"),
    "turbo-off": lambda p: world(p, turbo="off"),
    "turbo-batch-done": lambda p: world(
        p, box="- [x] FX1 a ticked box\n", more=[("b", "- [ ] FX2 an open box\n")]
    ),
}

# `gh api graphql` is the Stop hook's PR read (`wl_ci.pr_link`, through `wl_prscope.loop_state`); `gh pr list` is the red-fix check. Each stub answers both in the shape the real `gh` prints.
_GH = (
    "#!/bin/sh\n"
    'if [ "$1" = api ]; then echo \'{"data":{"repository":{"pullRequests":{"nodes":[%s]}}}}\'; '
    "exit 0; fi\n%s"
)
GH_OPEN_BODY = _GH % ('{"number":599,"state":"OPEN","body":""}', "echo 599\n")
GH_NONE_BODY = _GH % ("", "exit 0\n")
GH_OPEN_PR = {"gh": GH_OPEN_BODY}
GH_NO_PR = {"gh": GH_NONE_BODY}

ENVS = [
    ("open-old-pr", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-open-old}"}, GH_OPEN_PR),
    ("open-fresh-nopr", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-open-fresh}"}, GH_NO_PR),
    ("batch-done-nopr", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-batch-done}"}, GH_NO_PR),
    ("all-done", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-done}"}, GH_NO_PR),
    ("turbo-off", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-off}"}, GH_NO_PR),
]

_WHY = "the fixture batch needs the VM E2E matrix on PLAN-fx-a FX1"
EDGE_CASES = [
    ("a bare push", "git push -u origin 1008-1"),
    ("an implicit push", "git push"),
    ("gh pr create", "gh pr create --draft -t x -b y"),
    ("a -C push", "git -C . push origin 1008-1"),
    ("a wrapper payload", "sh -c 'git push origin 1008-1'"),
    ("an unknown kind", "TURBO_PUSH_REASON='because: %s' git push origin 1008-1" % _WHY),
    ("a short why", "TURBO_PUSH_REASON='deadline: soon' git push origin 1008-1"),
    ("ci-cd naming the plan", "TURBO_PUSH_REASON='ci-cd: %s' git push origin 1008-1" % _WHY),
    (
        "ci-cd naming no plan",
        "TURBO_PUSH_REASON='ci-cd: the batch needs the VM matrix to run' git push origin 1008-1",
    ),
    (
        "red-fix",
        "TURBO_PUSH_REASON='red-fix: lint red on the live PR, fixed here' git push origin 1008-1",
    ),
    (
        "deadline",
        "TURBO_PUSH_REASON='deadline: the 03:00Z CD run needs this fix in' git push origin 1008-1",
    ),
    (
        "backup",
        "TURBO_PUSH_REASON='backup: hours of local commits, no PR' git push -u origin 1008-1",
    ),
    (
        "backup on gh pr create",
        "TURBO_PUSH_REASON='backup: hours of local commits, no PR' gh pr create --draft",
    ),
    (
        "an exported reason",
        "export TURBO_PUSH_REASON='ci-cd: %s'; git push origin 1008-1" % _WHY,
    ),
    ("a dry run", "git push --dry-run origin 1008-1"),
    ("a delete push", "git push origin --delete 1007-1"),
    ("the mirror push of main", "git push gitlab refs/heads/main:refs/heads/main --follow-tags"),
    ("prose naming a push", "echo 'git push origin 1008-1'"),
    ("a scratch repo", "git -C /tmp push origin x"),
]


# --------------------------------------------------------------------------- what the command does


def _skipped(args):
    """Why one push is not this guard's business, "" when it is judged."""
    parsed = shellscan.git_push_args(args)
    if parsed.on("dry-run"):
        return "dry-run"
    specs = parsed.operands[1:]
    if parsed.on("delete") or (specs and all(s.startswith(":") for s in specs)):
        return "delete"
    dests = commit_policy.push_destinations(args)
    if dests and all(dst == "main" for _src, dst in dests):
        return "main"
    return ""


def _acts(cmd, root, base):
    """[(act, repo, reason-or-None, spelling)] for every judged push and create in `cmd`, in order."""
    created = commit_policy.created_dirs(cmd, base)
    out = []
    for run in commit_policy.git_runs(cmd, "push"):
        _, _, args = commit_policy.git_split(run.argv)
        if _skipped(args):
            continue
        repo = commit_policy.scoped_repo(run, base, root, created)
        if repo and not commit_policy.is_inside(repo, root):
            continue
        out.append(
            ("push", repo or root, run.env.get(REASON_ENV), " ".join(["git push", *args]), args)
        )
    for run in shellscan.gh_pr_runs(cmd, "create"):
        repo = commit_policy.toplevel(commit_policy.run_dir(run, base)) or root
        if not commit_policy.is_inside(repo, root):
            continue
        out.append(("pr-create", repo, run.env.get(REASON_ENV), " ".join(["gh", *run.argv]), []))
    return out


# --------------------------------------------------------------------------- the queue


def _open_promoted(ev, root):
    """[(plan, open, done)] for every Promoted plan with an open box, or None when the queue could not be read (the caller fails open)."""
    path = pathlib.Path(root) / QUEUE_REL
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        ev.warn(UNREAD % ("%s is unreadable (%s)" % (QUEUE_REL, exc)))
        return None
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_planqueue
    except ImportError as exc:
        ev.warn(UNREAD % ("wl_planqueue could not import (%s)" % exc))
        return None
    promoted, _generated = wl_planqueue.entries(text)
    found = []
    for rel in promoted:
        opened, done, why = plan_gate.open_boxes(str(root), rel)
        if why and not (pathlib.Path(root) / rel).is_file():
            moved = "agent/plans/_done/" + rel.rsplit("/", 1)[-1]
            if (pathlib.Path(root) / moved).is_file():
                opened, done, why = plan_gate.open_boxes(str(root), moved)
        if why and "has no boxes" not in why:
            ev.warn("block-turbo-early-push: Promoted entry %s not counted: %s." % (rel, why))
            continue
        if opened:
            found.append((rel, opened, done))
    return found


# --------------------------------------------------------------------------- the reason


def _unpushed_span(repo):
    """(span, "") for the commits not yet on the remote (`origin/<branch>..HEAD`, or `origin/main..HEAD` before the first push), or (None, why)."""
    branch = commit_policy.current_branch(repo)
    if not branch:
        return None, "the checkout is on no branch"
    base = "origin/%s" % branch
    if commit_policy.git(["rev-parse", "--verify", "-q", "refs/remotes/" + base], cwd=repo) is None:
        base = "origin/main"
        if (
            commit_policy.git(["rev-parse", "--verify", "-q", "refs/remotes/origin/main"], cwd=repo)
            is None
        ):
            return None, "neither origin/%s nor origin/main exists here" % branch
    return "%s..HEAD" % base, ""


def _oldest_unpushed_age_h(repo):
    """(hours, range) of the oldest commit not yet on the remote, or (None, why)."""
    span, why = _unpushed_span(repo)
    if span is None:
        return None, why
    out = commit_policy.git(["log", "--format=%ct", span], cwd=repo)
    if out is None:
        return None, "`git log %s` failed" % span
    stamps = [int(s) for s in out.split() if s.isdigit()]
    if not stamps:
        return None, "%s holds no commit, so there is nothing to back up" % span
    return (time.time() - min(stamps)) / 3600.0, span


def _named_plan(why, open_plans):
    for rel, _o, _d in open_plans:
        base = rel.rsplit("/", 1)[-1]
        slug = base[len("PLAN-") : -len(".md")]
        if re.search(r"(?<![\w-])(?:PLAN-)?%s(?:\.md)?(?![\w-])" % re.escape(slug), why):
            return rel
    return ""


def _judge(ev, act, repo, reason, open_plans, backup_h):
    """(kind, why) when admitted, else (None, the refusal line)."""
    if reason is None:
        return None, "no `%s=` on it" % REASON_ENV
    m = REASON_RE.match(reason)
    kind, why = (m.group(1).lower(), m.group(2)) if m else ("", reason)
    if kind not in KINDS:
        return None, "`%s=%r`: the kind must be one of %s" % (REASON_ENV, reason, ", ".join(KINDS))
    if len(why) < MIN_WHY:
        return None, "`%s`: the why is %d characters; at least %d say what it is" % (
            reason,
            len(why),
            MIN_WHY,
        )
    if kind == "ci-cd" and not _named_plan(why, open_plans):
        return None, "`ci-cd` names no open Promoted plan (its basename or slug, and the box)"
    if kind == "red-fix":
        branch = commit_policy.current_branch(repo)
        try:
            prs = commit_policy._gh_lines(
                repo,
                [
                    "pr",
                    "list",
                    "--head",
                    branch,
                    "--state",
                    "open",
                    "--json",
                    "number",
                    "--jq",
                    ".[].number",
                ],
            )
        except commit_policy.GhUnavailableError as exc:
            ev.warn(
                "block-turbo-early-push: `gh` could not say whether `%s` has an open PR (%s); "
                "the red-fix reason is admitted UNVERIFIED."
                % (branch, str(exc).split("\n")[0][:160])
            )
            return kind, why
        if not prs:
            return (
                None,
                "`red-fix`, but `%s` has no open PR, so there is no red on a live PR to fix"
                % (branch or "(detached)"),
            )
    if kind == "backup":
        if act == "pr-create":
            return None, "`backup` never opens a PR: a backup is a plain push, which runs no CI"
        if backup_h <= 0:
            return None, "`backup`, but `backup_push_h: 0` in %s turns the valve off" % QUEUE_REL
        age, span = _oldest_unpushed_age_h(repo)
        if age is None:
            return None, "`backup` could not be verified: %s" % span
        if age < backup_h:
            return (
                None,
                "`backup`: the oldest commit in %s is %.1fh old, under `backup_push_h: %d`"
                % (
                    span,
                    age,
                    backup_h,
                ),
            )
    return kind, why


# --------------------------------------------------------------------------- the merge phase


def _merge_phase(ev, root, session_id):
    """The session's live `merge` phase event, or None (no phase, another mode, expired, or unreadable: fails closed)."""
    if not session_id:
        return None
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_core
        import wl_standdown
        import wl_store

        worklist = wl_core.worklist_for(wl_core.project_start({"cwd": str(root)}))
        light = wl_store.phase_fold(worklist, pathlib.Path(root))
        wl_core.bind_lineage(session_id, light.aliases_of(session_id))
        focus = wl_standdown.active_phase(light.phase, lambda o: wl_core.owned_by_me(o, session_id))
        if focus is None or focus.get("mode") != "merge" or wl_standdown.expired(focus):
            return None
        return focus
    except Exception as exc:
        ev.warn(
            "block-turbo-early-push: the session phase could not be read (%s: %s); the merge-phase "
            "pointer-bump admission is not applied." % (type(exc).__name__, str(exc)[:160])
        )
        return None


def _bump_only(repo):
    """("", span) when every commit of the unpushed range changes only gitlinks and agent/reviews/ paths, else (why not, span)."""
    span, why = _unpushed_span(repo)
    if span is None:
        return why, ""
    parents = commit_policy.git(["rev-list", "--parents", span], cwd=repo)
    if parents is None:
        return "`git rev-list %s` failed" % span, span
    commits = [ln.split() for ln in parents.splitlines() if ln.strip()]
    if not commits:
        return "%s holds no commit" % span, span
    if any(len(c) > 2 for c in commits):
        return "%s holds a merge commit" % span, span
    for c in commits:
        raw = commit_policy.git(
            ["diff-tree", "-r", "--no-commit-id", "--no-renames", "--no-abbrev", "--root", c[0]],
            cwd=repo,
        )
        if raw is None:
            return "`git diff-tree %s` failed" % c[0][:12], span
        for line in raw.splitlines():
            if not line.startswith(":"):
                continue
            meta, _tab, path = line.partition("\t")
            fields = meta[1:].split()
            if len(fields) < 2 or not path:
                return "an unreadable diff line in %s" % c[0][:12], span
            if fields[0] in GITLINK_MODES and fields[1] in GITLINK_MODES:
                continue
            # A review record is a regular file, as in detect_pointer_bump: a symlink or gitlink under agent/reviews/ is not one.
            if path.startswith(MERGE_PATH_PREFIX) and {fields[0], fields[1]} <= REVIEW_MODES:
                continue
            return "%s changes `%s`, which is neither a gitlink nor under %s" % (
                c[0][:12],
                path,
                MERGE_PATH_PREFIX,
            ), span
    return "", span


def _merge_bump(ev, act, repo, args, focus):
    """The ledger why when the merge phase admits this act, else None."""
    if focus is None or act != "push":
        return None
    branch = commit_policy.current_branch(repo)
    if not branch or str(focus.get("branch") or "") != branch:
        return None
    dests = commit_policy.push_destinations(args)
    if any(dst != branch for _src, dst in dests):
        return None
    why_not, span = _bump_only(repo)
    if why_not:
        ev.warn(
            "block-turbo-early-push: merge phase on %s, but the pointer-bump admission does not "
            "apply: %s." % (branch, why_not)
        )
        return None
    return "merge phase on %s (PR %s): %s changes only gitlinks and %s" % (
        branch,
        focus.get("pr") or "?",
        span,
        MERGE_PATH_PREFIX,
    )


# --------------------------------------------------------------------------- the batch


class Batch:
    """What the Stop hook's own readers say about the branch's local batch. `local` is False off a filling local batch (a live PR, `turbo_push: pr`, a PR read that failed, a branch off the loop), and `why_not` then says which. `rows` is [(plan, open, done, first open box or "")] in the batch's set order; `more` names a queued plan the batch must still take, "" when none."""

    def __init__(self, local, complete=False, why_not="", branch="", finished=0, size=1):
        self.local = local
        self.complete = complete
        self.why_not = why_not
        self.branch = branch
        self.finished = finished
        self.size = size
        self.rows = []
        self.more = ""
        self.disagree = []


def _batch(ev, root, session_id):
    """The branch's local batch as the Stop hook reads it, or None when it could not be read (the caller fails open, loudly).

    ONE READING, NOT A SECOND COPY. `wl_prscope.loop_state` builds the state the Stop hook builds, `wl_checks.local_batch` says whether a local batch is filling, and `wl_checks.local_batch_open` (`wl_prscope.batch_ready` over the set's box read) says whether it is still open: the exact predicates `loop_next_text` uses to choose V_LOOP_NEXT_BATCH_OPEN, the block that orders this push. A guard that decided completion its own way would reopen the gap this function closes.

    `turbo_more` (whether the queue still holds a plan the batch must take) is the one input the Stop hook fills from its writer roster. It matters only when every plan of the set is finished and fewer than `batch_size` are, so the roster is read only then, through `wl_planconc.live_plans` (the pre-tool estimate `block_plan_concurrency` uses). Live writers only ever NARROW what `plan_gate.next_turbo` finds eligible, so `turbo_more` False with no writers proves it False with any, and the ~3 s roster read is skipped then too.
    """
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_checks
        import wl_core
        import wl_planenforce
        import wl_prscope

        worklist = wl_core.worklist_for(wl_core.project_start({"cwd": str(root)}))
        state = wl_prscope.loop_state(str(root), worklist, session_id, gh=False)
        if not wl_checks.local_batch(state):
            why = "the loop reads this branch as `%s`" % state.kind
            if state.turbo and wl_checks.turbo_push_mode(state) != "batch-end":
                why = "`turbo_push: %s` opens the PR at the first push" % state.turbo_push
            elif state.reason:
                why += " (%s)" % state.reason[:160]
            return Batch(False, why_not=why, branch=state.branch)
        rows = []
        for rel in state.plans:
            opened, done, _why = plan_gate.open_boxes(str(root), rel)
            box = wl_planenforce.first_box(str(root), rel)
            rows.append((rel, opened, done, "%s  %s" % (box[0], box[1][:100]) if box else ""))
        if not any(r[3] for r in rows) and state.finished < state.batch_size:
            state = wl_prscope.with_turbo(state, str(root), (), 0)
            if state.turbo_more:
                import wl_planconc
                import wl_store

                live = wl_planconc.live_plans(
                    str(root), session_id, wl_store.load(worklist, sync=False)
                )
                if live is None:
                    ev.warn(
                        "block-turbo-early-push: the live writers could not be counted, so the "
                        "batch is judged as if none were live (the queue's eligible plans count)."
                    )
                else:
                    state = wl_prscope.with_turbo(state, str(root), sorted(live), len(live))
        hook_complete = not wl_checks.local_batch_open(state, str(root))
        # THE STRICTER READ WINS. `local_batch_open` reads boxes through `wl_planenforce.first_box`, which follows no `Moved-To:` stub, while `loop_state`'s own `finished` count (`plan_gate.open_boxes`) does, and an empty set is vacuously finished. Where the two disagree the push is not released: a stub whose target still has an open box, or a batch of no plan, is not a completed batch.
        disagree = [r[0] for r in rows if r[1] > 0 and not r[3]]
        complete = hook_complete and bool(rows) and not disagree
    except Exception as exc:
        ev.warn(UNREAD % ("the batch state could not be read (%s: %s)" % (type(exc).__name__, exc)))
        return None
    out = Batch(
        True,
        complete=complete,
        branch=state.branch,
        finished=state.finished,
        size=state.batch_size,
    )
    out.rows = rows
    out.disagree = disagree
    # Only the batch_size arm names a plan to take: every box of the set ticked by both reads, fewer than batch_size finished, and the queue still holding an eligible plan.
    if not hook_complete and rows and not disagree and not any(r[3] for r in rows):
        out.more = (
            state.turbo_picks[0]
            if state.turbo_picks
            else "an eligible queued plan (the `plan_concurrency` ceiling holds it for now)"
        )
    return out


def _batch_lines(batch):
    """The refusal's account of the batch: what remains, so the session works it instead of asking."""
    if batch is None:
        return "The batch state could not be read (see the note above), so completion cannot\nrelease this push.\n\n"
    if not batch.local:
        return (
            "No local batch is filling on this branch (%s), so batch completion\ncannot release this push.\n\n"
            % batch.why_not
        )
    head = (
        "The local batch on %s is NOT complete: %d of batch_size %d plan(s) finished.\n"
        "What remains, and it is the work to do now (push timing is the hooks' call, never a\n"
        "question for the operator):\n" % (batch.branch, batch.finished, batch.size)
    )
    lines = [
        "  %s  %d open, %d done%s\n" % (rel, o, d, ("; next box %s" % box) if box else "")
        for rel, o, d, box in batch.rows
        if box or o
    ]
    if not batch.rows:
        lines.append(
            "  the batch holds no plan: no `## Promoted` entry of agent/plans/QUEUE.md exists\n"
            "  under agent/plans/, so there is nothing complete to push\n"
        )
    lines.extend(
        "  %s: its first box read finds none, but the plan it resolves to (a `Moved-To:`\n"
        "  target) still has an open box; tick it there or fix the stub\n" % rel
        for rel in batch.disagree
    )
    if batch.more:
        lines.append(
            "  every plan of the set is ticked, but fewer than batch_size are finished and the\n"
            "  batch still takes %s: start it on a free writer slot (the Stop hook's\n"
            "  turbo-next names it)\n" % batch.more
        )
    return (
        head
        + "".join(lines)
        + "Once it completes this guard admits `git push` and `gh pr create` with no reason\n(ledger kind `%s`).\n\n"
        % BATCH_KIND
    )


def _row(root, act, repo, kind, why, open_plans):
    """One ledger line for one admitted act."""
    return {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": commit_policy.current_branch(repo),
        "repo": "." if repo == root else str(pathlib.Path(repo).relative_to(root)),
        "act": act,
        "kind": kind,
        "why": why,
        "head": commit_policy.git(["rev-parse", "HEAD"], cwd=repo) or "",
        "open_promoted": len(open_plans),
    }


def _record(ev, root, rows):
    path = pathlib.Path(root) / LEDGER_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    except OSError as exc:
        ev.warn(
            "block-turbo-early-push: the admission was NOT recorded in %s (%s)." % (LEDGER_REL, exc)
        )


REFUSAL = """BLOCKED: turbo is on and %(n)d Promoted plan(s) in agent/plans/QUEUE.md are unfinished, so this %(what)s is early.

Operator ruling 2026-10-08: under turbo, local completion is the default. A batch is
finished and committed on this machine and pushed once; a push (and every CI cycle it
starts) needs a real operational reason while Promoted plans are still open.

%(lines)s
%(batch)sOpen Promoted plans:
%(plans)s
An operational reason goes on the command itself, `<kind>: <why, %(min)d+ chars>`:

    ci-cd     a plan needs a check only CI/CD runs; name the plan and its box
    red-fix   a fix for a red on the live PR (an open PR for the branch is required)
    deadline  production or CD state that cannot wait; name it
    backup    the oldest unpushed commit is older than backup_push_h (%(h)s h here);
              a plain push only, never `gh pr create`

    TURBO_PUSH_REASON='ci-cd: %(example)s needs the VM E2E matrix, box <id>' git push -u origin <branch>

Each admitted reason is appended to %(ledger)s. Otherwise keep committing locally.
A `/pr-merge` pointer bump needs no reason: in the session's `merge` phase for this branch, a push whose unpushed range changes only submodule gitlinks and agent/reviews/ is admitted.
When to push is decided here and by the Stop hook, so it is never asked of the operator.
The operator's own `!` command does not pass through this guard.
"""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if not root:
        return hookio.ALLOW
    base = ev.field("cwd") or root
    acts = _acts(cmd, root, base)
    if not acts:
        return hookio.ALLOW
    try:
        settings, problems = plan_gate.settings_at(root)
    except (OSError, ValueError) as exc:
        ev.warn(UNREAD % ("%s could not be parsed (%s: %s)" % (QUEUE_REL, type(exc).__name__, exc)))
        return hookio.ALLOW
    for problem in problems:
        if "unreadable" in problem or "could not import" in problem:
            ev.warn(UNREAD % problem)
    if not getattr(settings, "turbo", False):
        return hookio.ALLOW
    open_plans = _open_promoted(ev, root)
    if open_plans is None:
        return hookio.ALLOW
    if not open_plans:
        return hookio.ALLOW
    backup_h = int(getattr(settings, "backup_push_h", DEFAULT_BACKUP_H))

    rows = []
    refusals = []
    focus = False  # read once, only when a push would be refused
    for act, repo, reason, spelling, args in acts:
        kind, why = _judge(ev, act, repo, reason, open_plans, backup_h)
        if kind is None and act == "push":
            if focus is False:
                focus = _merge_phase(ev, root, str(ev.field("session_id") or ""))
            bump = _merge_bump(ev, act, repo, args, focus)
            if bump:
                kind, why = MERGE_KIND, bump
        if kind is None:
            refusals.append("  %s\n    refused: %s\n" % (spelling, why))
            continue
        rows.append(_row(root, act, repo, kind, why, open_plans))
    batch = None
    if refusals:
        # Read only now: a reasoned push never pays for the batch read. A complete batch releases every act of the command, PR included.
        batch = _batch(ev, root, str(ev.field("session_id") or ""))
        if batch is None:
            return hookio.ALLOW
        if batch.complete:
            why = "the local batch on %s is complete: %d of batch_size %d finished (%s)" % (
                batch.branch,
                batch.finished,
                batch.size,
                ", ".join(r[0].rsplit("/", 1)[-1] for r in batch.rows),
            )
            rows = [
                _row(root, act, repo, BATCH_KIND, why, open_plans) for act, repo, _r, _s, _a in acts
            ]
            refusals = []
    if refusals:
        ev.warn_raw(
            REFUSAL
            % {
                "n": len(open_plans),
                "what": "push" if all(a[0] == "push" for a in acts) else "push or PR",
                "lines": "".join(refusals),
                "batch": _batch_lines(batch),
                "plans": "".join(
                    "  %s  %d open, %d done\n" % (rel, o, d) for rel, o, d in open_plans
                ),
                "min": MIN_WHY,
                "h": backup_h,
                "example": open_plans[0][0].rsplit("/", 1)[-1],
                "ledger": LEDGER_REL,
            }
        )
        return hookio.DENY
    _record(ev, root, rows)
    return hookio.ALLOW
