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

  Each admitted command appends one JSON line per push or create to agent/ledgers/turbo-push-reasons.jsonl in the console checkout (ts, branch, repo, act, kind, why, head, open_promoted), written only once every act in the command is admitted. This guard runs LAST in the chain (ORDER below), so every other guard has already admitted the same command when the line is written.

SCOPE. Every `git push` (any remote or refspec, `-C`/`cd` included) in this checkout or a submodule under it, and every `gh pr create`. NOT judged: a `--dry-run` push (publishes nothing); a delete push (`--delete`, `:<branch>`: the M6 cleanup after a merge); a push whose every destination is `main` (the fast-forward fallback and the GitLab mirror push, which `block_push_to_protected_branch` admits only on a merged-ready PR); a repository outside this checkout.

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
# Last in the pre-bash chain: the ledger line is the admission record, so it is written only after every other guard has let the command through.
ORDER = 57

# The open-plan test, read the other way round: planted, the guard admits every push once the queue has been read, reason or none, which is the guard body switched off.
DEFECT = ("if not open_plans:", "if True:")

REASON_ENV = "TURBO_PUSH_REASON"
KINDS = ("ci-cd", "red-fix", "deadline", "backup")
MIN_WHY = 20
DEFAULT_BACKUP_H = 4
LEDGER_REL = "agent/ledgers/turbo-push-reasons.jsonl"
QUEUE_REL = plan_gate.QUEUE_REL
REASON_RE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$", re.DOTALL)

UNREAD = "block-turbo-early-push: %s; this push passed UNEXAMINED."


def _git(path, *argv, env_date=None):
    import os  # noqa: PLC0415 -- fixture builders only
    import subprocess  # noqa: PLC0415

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
    "# Queue\n\n## Settings\n\n```stop-hook\nturbo: %s\nbackup_push_h: 4\n```\n\n"
    "## Promoted\n\n1. agent/plans/PLAN-fx-a.md -- a fixture plan\n"
)
FIXTURE_PLAN = (
    "# PLAN: fx\n\nStatus: in-progress\nDepends-On: no-dep -- a fixture plan\n\n## Tasks\n\n%s"
)


def world(path, turbo="on", box="- [ ] FX1 an open box\n", date="2026-01-01T00:00:00+00:00"):
    """A console-shaped repository on `1008-1`: QUEUE.md with `turbo`, one Promoted plan holding `box`, `origin/main` at the seed and one unpushed commit made at `date`."""
    path = pathlib.Path(path)
    (path / "agent" / "plans").mkdir(parents=True)
    (path / QUEUE_REL).write_text(FIXTURE_QUEUE % turbo, encoding="utf-8")
    (path / "agent/plans/PLAN-fx-a.md").write_text(FIXTURE_PLAN % box, encoding="utf-8")
    _git(path, "init", "-q", "--initial-branch=main")
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
}

GH_OPEN_PR = {"gh": "#!/bin/sh\necho 599\n"}
GH_NO_PR = {"gh": "#!/bin/sh\nexit 0\n"}

ENVS = [
    ("open-old-pr", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-open-old}"}, GH_OPEN_PR),
    ("open-fresh-nopr", {"CLAUDE_PROJECT_DIR": "{FIXTURE:turbo-open-fresh}"}, GH_NO_PR),
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
        out.append(("push", repo or root, run.env.get(REASON_ENV), " ".join(["git push", *args])))
    for run in shellscan.gh_pr_runs(cmd, "create"):
        repo = commit_policy.toplevel(commit_policy.run_dir(run, base)) or root
        if not commit_policy.is_inside(repo, root):
            continue
        out.append(("pr-create", repo, run.env.get(REASON_ENV), " ".join(["gh", *run.argv])))
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
        import wl_planqueue  # noqa: PLC0415 -- the one reader of the queue's format
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


def _oldest_unpushed_age_h(repo):
    """(hours, range) of the oldest commit not yet on the remote, or (None, why)."""
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
    span = "%s..HEAD" % base
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
Open Promoted plans:
%(plans)s
An operational reason goes on the command itself, `<kind>: <why, %(min)d+ chars>`:

    ci-cd     a plan needs a check only CI/CD runs; name the plan and its box
    red-fix   a fix for a red on the live PR (an open PR for the branch is required)
    deadline  production or CD state that cannot wait; name it
    backup    the oldest unpushed commit is older than backup_push_h (%(h)s h here);
              a plain push only, never `gh pr create`

    TURBO_PUSH_REASON='ci-cd: %(example)s needs the VM E2E matrix, box <id>' git push -u origin <branch>

Each admitted reason is appended to %(ledger)s. Otherwise keep committing locally.
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
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        # plan_gate._read catches OSError only, so a QUEUE.md that is not UTF-8 raises out of settings_at (measured 2026-10-08).
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
    for act, repo, reason, spelling in acts:
        kind, why = _judge(ev, act, repo, reason, open_plans, backup_h)
        if kind is None:
            refusals.append("  %s\n    refused: %s\n" % (spelling, why))
            continue
        rows.append(
            {
                "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "branch": commit_policy.current_branch(repo),
                "repo": "." if repo == root else str(pathlib.Path(repo).relative_to(root)),
                "act": act,
                "kind": kind,
                "why": why,
                "head": commit_policy.git(["rev-parse", "HEAD"], cwd=repo) or "",
                "open_promoted": len(open_plans),
            }
        )
    if refusals:
        ev.warn_raw(
            REFUSAL
            % {
                "n": len(open_plans),
                "what": "push" if all(a[0] == "push" for a in acts) else "push or PR",
                "lines": "".join(refusals),
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
