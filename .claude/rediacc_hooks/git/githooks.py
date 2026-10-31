"""The git-level half of the commit policy: `commit-msg`, `reference-transaction` and `pre-push`, plus the `pre-commit` checks of generated files (doc regions, and the artifacts of `.ci/config/generated-artifacts.json`).

WHY A SECOND LAYER (the commit-policy plan in agent/plans, section 5.3; operator ruling 2, 2026-09-25: installed for everyone, with the `COMMIT_POLICY_OK=1` override). The pre-bash guards see only an agent's own Bash tool calls. Everything else that commits, cuts a branch or pushes never reaches them: the operator's terminal and `!` commands, and subprocesses (`worklist.py --git`, the per-commit reviewer, release scripts run locally; the 2026-09-22 push to `main` came from a script three process levels below the Bash call). Git runs these hooks for all of them once `core.hooksPath` points at this directory, which the `git-hooks-path` setup phase does in the console and in every checked-out submodule (`.ci/rediacc_ci/setup/githooks.py`). It is local config only, so `/tmp` fixtures and CI checkouts are unaffected.

WHAT EACH HOOK REFUSES (the rules are `commit_policy`'s, shared with the pre-bash guards):

  commit-msg              a CI skip token; a commit on `main` that is not a well-formed `[hotfix]`; `[hotfix]` off `main`; `[no-review]` on a non-writing path or on a `[hotfix]`.
  reference-transaction   in the `prepared` state, a new `refs/heads/*` (old oid all zeros AND the name not yet resolving: a forced move of an existing branch also arrives with zeros, and is not a creation) that breaks the one-branch rule: outside a submodule, only from `main`, with no other live branch and an `MMDD-N` name; in a submodule, only the console's current branch name. LOCAL FACTS ONLY: no `gh`, so a branch counts as live until its upstream is gone.
  pre-commit              a commit that stages a gen-docs provider input and leaves a generated doc region drifted in the COMMITTED tree (the section above `gen_docs_pre_commit` says how it stays fast), and a commit that stages an input of a generated artifact enrolled in `.ci/config/generated-artifacts.json` and leaves that artifact stale in the committed tree (`artifacts.py` beside this file).
  pre-push                a push to `main` other than the fast-forward fallback (one ref, a real commit, the live branch's pushed tip, the remote `main` its ancestor; box M2 of PLAN-plan-per-pr-loop, operator ruling 2026-10-02) or the GitLab mirror push (below), a delete of `main` included; a push creating a remote branch that is not the current one; a push of the backup paths that no VERIFIED backup receipt covers (box J10 of PLAN-backup-program, `backup_receipt_refusal` below). A line a live release run lists is admitted instead (box W1-D of PLAN-local-release, `_release_admitted` below).

THE PRE-BASH LAYER STAYS AUTHORITATIVE FOR AGENTS; this is the backstop. It reads no `gh`, so it cannot compute today's next name or know a PR merged; it checks shape and local liveness only.

`git branch -m` IS INVISIBLE HERE, and that is measured rather than assumed (T0(b), git 2.53, 2026-09-25): a rename reaches `reference-transaction` only as an aborted empty transaction and a DELETE of the old name; the new name is never shown as a creation. So a rename is always allowed at this layer, which is the rule anyway (the count stays at one).

THE OVERRIDE. `COMMIT_POLICY_OK=1` in the environment makes every hook here exit 0. It is the operator's; `block_git_hook_bypass` refuses an agent command that sets it, or that skips these hooks with `--no-verify`, `-n` or `-c core.hooksPath=`.

LOADED BY FILE, NOT BY PACKAGE. Git runs a hook as a plain executable with no package context, so each shim beside this file loads it with `importlib`, and this module loads `commit_policy.py` and `artifacts.py` the same way. No `sys.path` entry is added anywhere, which `test_canonical_sys_path_hop.py` freezes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
CONSOLE_ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("commit-policy hook: %s is missing" % path)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `artifacts.py` declares dataclasses under postponed annotations, and `dataclasses` resolves a class's module through `sys.modules`.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cp = _load("commit_policy", HERE.parent / "commit_policy.py")
ga = _load("githook_artifacts", HERE / "artifacts.py")
rr = _load("githook_release_run", HERE / "release_run.py")

SHAPE = re.compile(r"^[0-9]{4}-[0-9]+$")

FOOTER = (
    "\n"
    "This is the git-level commit-policy hook (.claude/rediacc_hooks/git/). The operator\n"
    "overrides it for one command with COMMIT_POLICY_OK=1; an agent never does.\n"
)


def _refuse(text: str) -> int:
    sys.stderr.write("commit-policy: %s\n%s" % (text, FOOTER))
    return 1


def _git(args: list[str]) -> str:
    return cp.git(args) or ""


def _repo() -> str:
    return _git(["rev-parse", "--show-toplevel"])


# --------------------------------------------------------------------------- commit-msg ---------------------------------------------------------------------------


# A CLAUDE SESSION LINK OR SESSION TRAILER (operator incident 2026-10-30, PR-TASK 9f92c43e): console is PUBLIC, and 80 commits carried `Claude-Session: https://claude.ai/code/session_<id>`, four of them pushed. The pre-bash guard `block_commit_meta` refuses it in an agent's own commands; these two hooks refuse it for a commit or a push made any other way. The two patterns are
# the guard's own (`block_commit_meta.SESSION_TRAILER` / `SESSION_LINK`), copied because this module is loaded by file and cannot import the guard package; `test-block_commit_meta.py` fails if the copies differ. `CLAUDE_FOOTER` is the attribution footer, line-anchored the way the guard anchors it, and narrowed to `[Claude` so an honest "Generated with npm" line is not refused.
SESSION_TRAILER = r"claude[\w-]*session[\w-]*[ \t]*[:=]"
SESSION_LINK = r"claude\.(?:ai|com)/(?:[\w.~%-]+/)*(?:session|chat|artifact|share)s?(?:[_/][A-Za-z0-9]|-[A-Za-z0-9-]*[0-9])"
CLAUDE_FOOTER = r"^[ \t]*(?:[^0-9A-Za-z\s]{0,4}[ \t]*)?Generated with \[?Claude"
SESSION_LEAK = re.compile(
    "%s|%s|%s" % (SESSION_TRAILER, SESSION_LINK, CLAUDE_FOOTER), re.IGNORECASE | re.MULTILINE
)
SESSION_ADVICE = (
    "console is a PUBLIC repository: never put a Claude session link (claude.ai/code/session_...,\n"
    "claude.ai/chat/..., an artifact or share link), a Claude-Session trailer or the\n"
    "Generated-with-Claude-Code footer in a commit message. Strip that line."
)
SCISSORS = "# ------------------------ >8 ------------------------"


def session_leak(msg: str) -> str:
    """The first line of `msg` that carries a session link, a session trailer or the footer, "" when none."""
    match = SESSION_LEAK.search(msg)
    if not match:
        return ""
    start = msg.rfind("\n", 0, match.start()) + 1
    end = msg.find("\n", match.end())
    return msg[start : end if end >= 0 else len(msg)].strip()[:200]


def commit_msg(argv: list[str]) -> int:
    if not argv:
        return 0
    try:
        raw = pathlib.Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    # `git commit -v` appends the diff below the scissors line, and git drops it; a diff of THIS file would otherwise read as the message carrying what it bans.
    raw = raw.split("\n" + SCISSORS, 1)[0] if not raw.startswith(SCISSORS) else ""
    msg = "\n".join(line for line in raw.split("\n") if not line.startswith("#"))
    leaked = session_leak(msg)
    if leaked:
        return _refuse("the message carries `%s`.\n%s" % (leaked, SESSION_ADVICE))
    cfg = cp.load_config(CONSOLE_ROOT)
    found = cp.skip_tokens(msg, cfg)
    if found:
        return _refuse(
            "the message carries a CI skip token (%s). GitHub skips the workflow for it and\n"
            "the required CI Complete check then waits forever." % ", ".join(found)
        )
    repo = _repo()
    branch = cp.current_branch(repo) if repo else ""
    found_tags = cp.tags(msg)
    paths = cp.staged_paths(repo) if repo else []
    if branch == "main":
        ok, reason = cp.hotfix_ok(msg, paths, cfg)
        if not ok:
            return _refuse(
                "a commit on `main` must be a well-formed [hotfix] (%s). Work lands on the one\n"
                "MMDD-N branch; switch to it first (the uncommitted work comes along)." % reason
            )
    elif "hotfix" in found_tags:
        return _refuse(
            "[hotfix] is for commits on `main`; this branch is `%s`." % (branch or "(detached)")
        )
    if "no-review" in found_tags:
        if "hotfix" in found_tags:
            return _refuse("a [hotfix] is always reviewed; drop [no-review].")
        eligible, offenders = cp.no_review_eligible(paths, cfg)
        if not eligible:
            return _refuse(
                "[no-review] is for writing only; these paths are not: %s."
                % (", ".join(offenders[:8]) or "(no staged path)")
            )
    return 0


# --------------------------------------------------------------------------- reference-transaction ---------------------------------------------------------------------------


def _created_heads(stdin: str) -> list[str]:
    """The `refs/heads/*` names a `prepared` transaction CREATES.

    An all-zero old value does not by itself mean a creation. Git writes zeros for a forced update too, one that does not check the current value (`git branch -f <existing> <sha>`, `git update-ref <ref> <sha>`); measured on git 2.53, 2026-10-20, a forced move of an existing `1020-1` from a detached HEAD arrived as `0000... <new> refs/heads/1020-1` and was refused as "creating branch". In the `prepared` state the ref still holds its pre-transaction value, so a name that already resolves is a MOVE of an existing branch, which the one-branch rule does not judge (the branch count is unchanged).
    """
    out = []
    for line in stdin.split("\n"):
        fields = line.split()
        if len(fields) != 3:
            continue
        old, new, ref = fields
        if old != cp.ZERO_OID or new == cp.ZERO_OID or new.startswith("ref:"):
            continue
        if not ref.startswith("refs/heads/"):
            continue
        if cp.git(["rev-parse", "--verify", "--quiet", ref]) is not None:
            continue
        out.append(ref[len("refs/heads/") :])
    return out


def reference_transaction(argv: list[str], stdin: str) -> int:
    if argv[:1] != ["prepared"]:
        return 0
    created = [n for n in _created_heads(stdin) if n != "main"]
    if not created:
        return 0
    repo = _repo()
    if not repo:
        return 0
    live = cp.live_branches(repo, gh=False)
    parent = cp.superproject(repo)
    for name in created:
        others = [b for b in live if b != name]
        if parent:
            console_branch = cp.current_branch(parent, foreign=True)
            if name != console_branch or others:
                return _refuse(
                    "creating branch `%s` in a submodule. Its branch carries the console's name\n"
                    "(`%s`), and it may hold no other live branch (live: %s)."
                    % (name, console_branch or "(detached)", ", ".join(live) or "none")
                )
            continue
        if not SHAPE.match(name):
            return _refuse("`%s` is not an MMDD-N branch name." % name)
        if others:
            return _refuse(
                "creating branch `%s` while `%s` is live. One branch per repository: continue\n"
                "on it (`git switch %s`)." % (name, others[0], others[0])
            )
        current = cp.current_branch(repo)
        if current != "main":
            return _refuse(
                "creating branch `%s` from `%s`. A new branch is cut from `main`."
                % (name, current or "(detached)")
            )
    return 0


# --------------------------------------------------------------------------- pre-push ---------------------------------------------------------------------------


def _main_push_refusal(
    repo: str, remote: str, current: str, lines: list[list[str]], line: list[str]
) -> str:
    """ "" when this update of `main` is the fast-forward fallback (box M2 of PLAN-plan-per-pr-loop), else why not.

    LOCAL FACTS ONLY, like every hook here: one ref in the whole push, a real commit (not a delete), the pushed tip of an `MMDD-N` branch on the remote (`commit_policy.pushed_live_branches`; the refspec, not the checkout, names it), and the remote's current `main` its ancestor. Whether that tip is the open PR's head with CI Complete green is the pre-bash guard's question (it reads `gh`); this layer stops every other shape from every source.
    """
    _local_ref, local_oid, _remote_ref, remote_oid = line
    if local_oid == cp.ZERO_OID:
        return "this deletes `main`"
    if len(lines) != 1:
        return "this pushes %d refs; the fallback is one refspec" % len(lines)
    if remote_oid == cp.ZERO_OID:
        return "`main` does not exist on `%s`, so this is no fast-forward" % remote
    return cp.ff_fallback_refusal(repo, remote, current, local_oid, remote_oid)


# THE GITLAB MIRROR PUSH (operator ruling 2026-10-03, worklist #1cad85a1: "Allow the agent to push it"). Step 6b of .claude/commands/pr-merge.md copies GitHub's `main` to the self-hosted mirror after each merge with `git push gitlab refs/heads/main:refs/heads/main --follow-tags`. It moves no history GitHub does not already hold, so it is admitted here and in `block_push_to_protected_branch`, which loads these helpers from this file rather than keeping a second copy.
#
# THE URL IS PINNED HERE, not read from .ci/config/well-known.env: the registry holds no GitLab value, and the remote itself lives only in local `.git/config` (pr-merge.md says so), so the one thing that can say "this remote is the console mirror" is a literal both layers compare against. Only the https spelling is admitted; an `insteadOf` rewrite that sends the push elsewhere fails the comparison, because git hands this hook the rewritten location.
MIRROR_REMOTE = "gitlab"
MIRROR_HOST = "gitlab.rediacc.io"
MIRROR_PATH = "/rediacc-org/github/console.git"


def mirror_url_refusal(url: str) -> str:
    """ "" when `url` is the console's GitLab mirror, else why not. Credentials in the URL are never echoed."""
    try:
        parts = urllib.parse.urlsplit(url or "")
        port = parts.port
        host = parts.hostname
    except ValueError:
        return "the `%s` URL cannot be parsed" % MIRROR_REMOTE
    want = "https://%s%s" % (MIRROR_HOST, MIRROR_PATH)
    if (
        parts.scheme != "https"
        or host != MIRROR_HOST
        or port is not None
        or parts.path != MIRROR_PATH
        or parts.query
        or parts.fragment
    ):
        shown = (
            "%s://%s%s" % (parts.scheme, host or "", parts.path)
            if parts.scheme
            else "(a local path)"
        )
        return "`%s` points at %s, not the console mirror %s" % (MIRROR_REMOTE, shown, want)
    return ""


def mirror_main_refusal(repo: str, sha: str) -> str:
    """ "" when `sha` is local `main` and local `main` is exactly `origin/main`, in the console checkout, else why not.

    The mirror only ever copies what GitHub's `main` already has: a local `main` ahead of `origin/main` would publish commits no PR merged, and one behind would rewind nothing but still mirror a stale `main`.
    """
    if not repo:
        return "the repository cannot be read"
    if cp.superproject(repo):
        return "this checkout is a submodule, and only the console's own `main` has a mirror"
    local = cp.git(["rev-parse", "--verify", "-q", "refs/heads/main^{commit}"], cwd=repo)
    origin = cp.git(["rev-parse", "--verify", "-q", "refs/remotes/origin/main^{commit}"], cwd=repo)
    if not local or not origin:
        return "local `main` or `origin/main` does not resolve here"
    if local != origin:
        ahead = cp.git(["merge-base", "--is-ancestor", origin, local], cwd=repo) is not None
        return (
            "local `main` (`%s`) is %s `origin/main` (`%s`); the mirror copies only what GitHub's `main` already has"
            % (
                local[:12],
                "ahead of" if ahead else "behind or beside",
                origin[:12],
            )
        )
    if sha != local:
        return "the pushed commit `%s` is not local `main` (`%s`)" % (sha[:12], local[:12])
    return ""


def _mirror_push_refusal(repo: str, url: str, lines: list[list[str]]) -> str:
    """ "" when this push to `gitlab` is the mirror push of `main` (plus tags `--follow-tags` adds), else why not."""
    why = mirror_url_refusal(url)
    if why:
        return why
    heads = [line for line in lines if line[2].startswith("refs/heads/")]
    if len(heads) != 1 or heads[0][0] != "refs/heads/main" or heads[0][2] != "refs/heads/main":
        return "the mirror push is `refs/heads/main:refs/heads/main` and no other branch"
    _local_ref, local_oid, _remote_ref, remote_oid = heads[0]
    if local_oid == cp.ZERO_OID:
        return "this deletes `main` on the mirror"
    if remote_oid == cp.ZERO_OID:
        return "`main` does not exist on `%s`, so this is no mirror update" % MIRROR_REMOTE
    for local_ref, oid, remote_ref, old in lines:
        if remote_ref.startswith("refs/heads/"):
            continue
        if not remote_ref.startswith("refs/tags/") or local_ref != remote_ref:
            return "`%s` is not part of the mirror push (main, plus new tags)" % remote_ref
        if oid == cp.ZERO_OID or old != cp.ZERO_OID:
            return "the tag `%s` is deleted or moved, and the mirror only adds tags" % remote_ref
    if cp.git(["merge-base", "--is-ancestor", remote_oid, local_oid], cwd=repo) is None:
        return (
            "the mirror's `main` (`%s`) is not an ancestor of `%s`: GitLab has diverged, report it and never force"
            % (
                remote_oid[:12],
                local_oid[:12],
            )
        )
    return mirror_main_refusal(repo, local_oid)


# THE RELEASE RUN (box W1-D of agent/plans/PLAN-local-release.md). A local release, `python3 -m rediacc_ci.release.local`, pushes what CD pushed: the tap repository's formula commit and the like, some of them to `main`. A line is admitted only when `REDIACC_RELEASE_RUN` names a record under `.ci/cache/release/` of the console root whose pid is a live ancestor of this hook with a matching start time and argv, that provably ran the console's tracked, unmodified entry, whose tree is the console's `HEAD^{tree}`, and which lists that exact `(toplevel, remote, remote_ref, oid)`, `remote` being the first argument git hands this hook; `release_run.py` beside this file is the record format, its writer and its reader. An admitted line skips the branch rules and the backup check (the release gates judged both before any push); every other line meets the rules below unchanged. When the variable is set, a failed record says why on stderr at once, and a line the record does not list says so beside the refusal of that line, and only then: a tag or an ordinary branch push the rules admit anyway prints no release-run noise.
def _release_admitted(
    repo: str, remote: str, lines: list[list[str]]
) -> tuple[set[int], dict[int, str]]:
    """The `id()`s of the pushed lines a live release run admits, and for each line a valid record does not list, the note `_refuse_lines` prints if that line is refused; both empty when the variable is unset or the record fails."""
    if not os.environ.get(rr.ENV) or not repo:
        return set(), {}
    try:
        keys = rr.admitted_pushes(CONSOLE_ROOT)
    except rr.RecordError as exc:
        sys.stderr.write("commit-policy: the release run admits nothing (%s)\n" % exc)
        return set(), {}
    admitted: set[int] = set()
    notes: dict[int, str] = {}
    for line in lines:
        if rr.admits(keys, repo, remote, line[2], line[1]):
            admitted.add(id(line))
            continue
        notes[id(line)] = (
            "commit-policy: the release run does not list (%s, %s, %s, %s); this line meets the ordinary rules\n"
            % rr.admission_key(repo, remote, line[2], line[1])
        )
    return admitted, notes


def _refuse_lines(notes: dict[int, str], refused: list[list[str]], message: str) -> int:
    """`_refuse(message)`, after the release-run note of each refused line a valid record did not list."""
    for line in refused:
        if id(line) in notes:
            sys.stderr.write(notes[id(line)])
    return _refuse(message)


def outgoing_session_leaks(repo: str, lines: list[list[str]]) -> tuple[list[str], str]:
    """`(offenders, unchecked)`: each outgoing commit or annotated tag whose message carries a session link, a session trailer or the footer (`session_leak`), as `<sha12> <subject>: <line>`, and a non-empty `unchecked` when the range could not be read.

    OUTGOING MEANS NO REMOTE HAS IT YET: each pushed tip's commits `--not --remotes`, so a commit some remote-tracking ref already holds (the four that reached GitHub before this hook existed) does not block every later push, while every NEW one does, whichever remote it is going to. A deleted ref sends nothing. An unreadable range is UNCHECKED and refused by the caller: an unknown is not a pass.
    """
    if not repo:
        return [], "the repository cannot be read"
    offenders: list[str] = []
    tips: list[str] = []
    for _local_ref, local_oid, remote_ref, _remote_oid in lines:
        if local_oid == cp.ZERO_OID:
            continue
        kind = cp.git(["cat-file", "-t", local_oid], cwd=repo)
        if kind is None:
            return [], "`git cat-file -t %s` failed" % local_oid[:12]
        if kind == "tag":
            body = cp.git(["cat-file", "tag", local_oid], cwd=repo)
            if body is None:
                return [], "the tag object %s cannot be read" % local_oid[:12]
            leaked = session_leak(body.split("\n\n", 1)[-1])
            if leaked:
                offenders.append("%s %s: %s" % (local_oid[:12], remote_ref, leaked))
        tips.append(local_oid)
    if not tips:
        return offenders, ""
    log = cp.git(["log", "--format=%H%x1f%s%x1f%B%x1e", *tips, "--not", "--remotes"], cwd=repo)
    if log is None:
        return [], "`git log <tips> --not --remotes` failed"
    for record in log.split("\x1e"):
        fields = record.strip("\n").split("\x1f", 2)
        if len(fields) != 3:
            continue
        sha, subject, body = fields
        leaked = session_leak(body)
        if leaked:
            offenders.append("%s %s: %s" % (sha[:12], subject[:60], leaked))
    return offenders, ""


def pre_push(argv: list[str], stdin: str) -> int:
    repo = _repo()
    current = cp.current_branch(repo) if repo else ""
    remote = argv[0] if argv else "origin"
    lines = [line.split() for line in stdin.split("\n") if len(line.split()) == 4]
    # FIRST, before every admission below (the mirror push, a release run): none of them makes a session link fit to publish.
    leaks, unchecked = outgoing_session_leaks(repo, lines)
    if unchecked:
        return _refuse(
            "UNCHECKED: the outgoing commit messages could not be read for Claude session links (%s).\n"
            "An unknown is not a pass." % unchecked
        )
    if leaks:
        return _refuse(
            "%d outgoing commit(s) carry a Claude session link, Claude-Session trailer or\n"
            "Claude Code footer:\n  %s%s\n%s\n"
            "These commits are not on any remote yet: reword each one (a history rewrite of the\n"
            "unpushed range is the operator's call) before this push can go."
            % (
                len(leaks),
                "\n  ".join(leaks[:20]),
                "\n  ... and %d more" % (len(leaks) - 20) if len(leaks) > 20 else "",
                SESSION_ADVICE,
            )
        )
    if remote == MIRROR_REMOTE and any(line[2] == "refs/heads/main" for line in lines):
        reason = _mirror_push_refusal(repo, argv[1] if len(argv) > 1 else "", lines)
        if reason:
            return _refuse(
                "this pushes to `main` on `%s` and is not the mirror push (%s).\n"
                "The one admitted shape (operator ruling 2026-10-03) is\n"
                "`git push gitlab refs/heads/main:refs/heads/main --follow-tags` from the console checkout,\n"
                "with local `main` exactly `origin/main` and `gitlab` the console mirror; nothing forced."
                % (MIRROR_REMOTE, reason)
            )
        return 0
    released, notes = _release_admitted(repo, remote, lines)
    for line in lines:
        _local_ref, local_oid, remote_ref, remote_oid = line
        if not remote_ref.startswith("refs/heads/"):
            continue
        if id(line) in released:
            continue
        name = remote_ref[len("refs/heads/") :]
        if name == "main":
            reason = _main_push_refusal(repo, remote, current, lines, line)
            if reason:
                return _refuse_lines(
                    notes,
                    [line],
                    "this pushes to `main` and is not the fast-forward fallback (%s).\n"
                    "Landings go through `gh pr merge <n> --rebase --auto`. The one direct push\n"
                    "(operator ruling 2026-10-02) is a fast-forward of the live branch's pushed tip\n"
                    "that is the open PR's head with CI Complete green:\n"
                    "`git push origin origin/<live MMDD-N branch>:main`, one refspec, nothing forced."
                    % reason,
                )
            continue
        if local_oid == cp.ZERO_OID:
            continue
        if remote_oid == cp.ZERO_OID and name != current:
            return _refuse_lines(
                notes,
                [line],
                "this creates the remote branch `%s`, and the one live branch is `%s`."
                % (name, current or "(detached)"),
            )
    unreleased = [line for line in lines if id(line) not in released]
    reason = backup_receipt_refusal(repo, unreleased)
    if reason:
        return _refuse_lines(
            notes,
            [line for line in unreleased if line[2].startswith("refs/heads/")],
            "this push touches the backup paths and no VERIFIED backup receipt covers it.\n"
            "%s\n"
            "The pre-bash guard `block_backup_unverified_push` admits the same push with an\n"
            "operator answer: %s='<drill-unavailable|not-runtime|deadline>: <why, %d+ chars>\n"
            "ASKED:<YYYY-MM-DDTHH:MM>Z' on the push. This hook checks its shape only; the guard\n"
            "proves the ASKED minute." % (reason, BACKUP_REASON_ENV, BACKUP_MIN_WHY),
        )
    return 0


# THE BACKUP RECEIPT AT THE GIT LAYER (box J10 of agent/plans/PLAN-backup-program.md). `block_backup_unverified_push` (box J4) refuses an agent's Bash `git push` of the backup paths without a VERIFIED backup receipt; a push from the operator's terminal or from a subprocess never reaches it, so this hook asks the same question of every pushed `refs/heads/*` commit.
#
# ONE DEFINITION, RUN AS A PROCESS. The trigger and the admission rule are `rediacc_ci.drills.backup_check_trigger`, and this module adds no `sys.path` entry (`test_canonical_sys_path_hop.py`), so it runs `python3 -m rediacc_ci.drills.backup_check_trigger check` with `.ci` of THIS checkout on `PYTHONPATH`, against the pushing repository. Exit 0 admits; 1 is the refusal it prints; anything else, a timeout included, is UNCHECKED and refused too, never a pass.
#
# WHAT IS NOT JUDGED: a submodule push (the console pointer push carries its range), a delete, a non-branch ref, and a commit some remote-tracking ref already contains (it was judged when it was first pushed; the fast-forward of `main` and the mirror copy are such pushes). The base is the remote's old tip when it is a commit here, else the merge-base with `refs/remotes/origin/main`.
#
# THE ESCAPE is the guard's own variable, checked for shape (a kind, a why of `BACKUP_MIN_WHY`+ characters, an `ASKED:` minute). No transcript reaches a git hook, so the minute is proven only by the guard for an agent's push; from the operator's terminal it is the operator's own word, like `COMMIT_POLICY_OK=1`.
BACKUP_MODULE = "rediacc_ci.drills.backup_check_trigger"
BACKUP_REASON_ENV = "BACKUP_CHECK_PUSH_REASON"
BACKUP_KINDS = ("drill-unavailable", "not-runtime", "deadline")
BACKUP_MIN_WHY = 40
BACKUP_TIMEOUT = 120
_BACKUP_REASON_RE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$", re.DOTALL)
_BACKUP_ASKED_RE = re.compile(r"\bASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")


def backup_escape_shaped(reason: str) -> bool:
    """True when `reason` has the shape the guard's escape needs: a known kind, a why of `BACKUP_MIN_WHY`+ characters once the `ASKED:` token is removed, and the token itself."""
    m = _BACKUP_REASON_RE.match(reason or "")
    if not m or m.group(1).lower() not in BACKUP_KINDS:
        return False
    why = re.sub(r"\s*\bASKED:\S*", "", m.group(2)).strip()
    return len(why) >= BACKUP_MIN_WHY and bool(_BACKUP_ASKED_RE.search(reason))


def _published(repo: str, oid: str) -> bool:
    return bool(
        cp.git(
            ["for-each-ref", "--contains", oid, "--format=%(refname)", "refs/remotes/"], cwd=repo
        )
    )


def backup_receipt_refusal(repo: str, lines: list[list[str]]) -> str:
    """ "" when no pushed branch commit needs the backup receipt or a receipt admits each, else the refusal text."""
    if not repo or cp.superproject(repo):
        return ""
    if backup_escape_shaped(os.environ.get(BACKUP_REASON_ENV, "")):
        return ""
    env = dict(os.environ, PYTHONPATH=str(CONSOLE_ROOT / ".ci"))
    for _local_ref, local_oid, remote_ref, remote_oid in lines:
        if not remote_ref.startswith("refs/heads/") or local_oid == cp.ZERO_OID:
            continue
        if _published(repo, local_oid):
            continue
        argv = [sys.executable, "-m", BACKUP_MODULE, "check", "--root", repo, "--tip", local_oid]
        if (
            remote_oid != cp.ZERO_OID
            and cp.git(["cat-file", "-e", "%s^{commit}" % remote_oid], cwd=repo) is not None
        ):
            argv += ["--base", remote_oid]
        try:
            proc = subprocess.run(
                argv,
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                timeout=BACKUP_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "UNCHECKED: the backup check of %s did not run (%s)" % (local_oid[:12], exc)
        if proc.returncode == 0:
            continue
        said = (proc.stderr.strip() or proc.stdout.strip())[-2000:]
        if proc.returncode != 1:
            return "UNCHECKED: the backup check of %s exited %d: %s" % (
                local_oid[:12],
                proc.returncode,
                said or "(no output)",
            )
        return said
    return ""


# --------------------------------------------------------------------------- pre-commit ---------------------------------------------------------------------------
#
# A COMMIT THAT LEAVES A GENERATED DOC REGION STALE IS REFUSED HERE, NOT 17 MINUTES LATER. On branch 1006-1, 1fb9eefe7 edited `.ci/policy/.audit-prod-allowlist` and 7f2ece4c1 edited `.ci/config/env-manifest.json`, both inputs of `scripts/gen/gen-docs.ts`, and neither re-ran `--write`. Each surfaced only in the pre-push run, as check:ci-doc-region-parity and three test_gate_docs_gen failures, and each needed a fix commit (423397221,
# 84cfe4e55). A pre-push red costs the whole pre-push; this costs the commit.
#
# TWO PATHS, AND THE FAST ONE IS THE COMMON ONE. Verify is about 6 s plus a 0.7 s checkout, too slow for every commit, so `gen-docs.ts --affected` first asks which staged paths could move a row, from each provider's declared `inputs` in `scripts/lib/doc-providers.ts` (about 0.15 s, no provider runs). Only a hit pays for verify. The declarations cannot go stale silently: `--selftest` traces every
# provider's real reads against them, and when the generator's own modules are staged this hook runs that trace too (`--check-inputs`).
#
# THE COMMIT'S TREE, NOT THE WORKING TREE. `git commit -F <msg> -- <paths>` commits those paths' working-tree content through a temporary index that git names in GIT_INDEX_FILE, and a plain commit commits the index; either way the committed tree is the index this hook sees, and the working tree may hold other sessions' unstaged edits. So verify runs on a full `checkout-index` of that
# index into a scratch tree (0.7 s with parallel checkout, against 2.3 s serial), with the generator's own committed copy. A partial commit that leaves its regeneration unstaged is refused, which is the case a working-tree check would wave through. The tradeoff was measured, not assumed: an overlay of only the changed files is cheaper but wrong whenever the working tree differs from
# the index anywhere a provider reads, which on this shared checkout is the normal state.
#
# UNKNOWN IS A REFUSAL. A missing `node`, a timeout or a generator that cannot run is reported as UNCHECKED and refused with the fix; `shim()`'s fail-open on a git error never sees them. There is no escape hatch of its own: the one override is `COMMIT_POLICY_OK=1`, the operator's, shared by every hook here.

GEN_ENTRY = "scripts/gen/gen-docs.ts"
GEN_FIX = "npx tsx scripts/gen/gen-docs.ts --write"
_IMPORT_RE = re.compile(r"""(?:from|import)\s*\(?\s*['"](\.[^'"\n]+)['"]""")
_DRIFT_RE = re.compile(r"^DRIFT (\S+)", re.MULTILINE)
SELECT_TIMEOUT = 60
VERIFY_TIMEOUT = 600


class UncheckedError(Exception):
    """The staged change could not be judged: never a pass."""


def _run(args: list[str], cwd: str, env: dict | None = None, timeout: int = 60):
    return subprocess.run(
        args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
    )


def _index_text(repo: str, rel: str) -> str | None:
    proc = _run(["git", "cat-file", "blob", ":" + rel], repo)
    return proc.stdout if proc.returncode == 0 else None


def generator_closure(repo: str) -> list[str]:
    """`scripts/gen/gen-docs.ts` and its relative imports, transitively, as the COMMIT's index holds them.

    The committed copy, never the working tree's: another session's half-written provider module must not decide, or break, this commit.
    """
    seen: list[str] = []
    queue = [GEN_ENTRY]
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        text = _index_text(repo, rel)
        if text is None:
            raise UncheckedError("%s is not in the commit's index" % rel)
        seen.append(rel)
        for match in _IMPORT_RE.finditer(text):
            if match.group(1).endswith(".js"):
                # Plain node strips types but never maps a `.js` specifier onto a `.ts` file, so this import would die as ERR_MODULE_NOT_FOUND inside the selector. Named here instead.
                raise UncheckedError(
                    "%s imports %s; plain node cannot resolve a .js specifier to the .ts file, spell it %s"
                    % (rel, match.group(1), match.group(1).removesuffix(".js") + ".ts")
                )
            base = posixpath.normpath(posixpath.join(posixpath.dirname(rel), match.group(1)))
            stem = base.removesuffix(".js")
            hit = next(
                (c for c in (base, stem + ".ts", base + ".ts") if _index_text(repo, c) is not None),
                None,
            )
            if hit is None:
                raise UncheckedError(
                    "%s imports %s, and the index holds no such file" % (rel, match.group(1))
                )
            queue.append(hit)
    return sorted(seen)


def _git_path(repo: str, name: str) -> str:
    out = _git(["rev-parse", "--git-path", name])
    return os.path.join(repo, out) if out and not os.path.isabs(out) else out


def _gen_env(repo: str, scratch: str) -> dict:
    """The environment every generator run gets: the commit's index named ABSOLUTE, no test override, a stable compile cache."""
    env = {k: v for k, v in os.environ.items() if k != "GEN_DOCS_OVERRIDE_FILE"}
    index = env.get("GIT_INDEX_FILE") or _git_path(repo, "index")
    env["GIT_INDEX_FILE"] = os.path.join(repo, index) if not os.path.isabs(index) else index
    # Keyed by file path, so it only pays off because the scratch paths below are FIXED per worktree: 0.29 s -> 0.14 s measured for `--affected`.
    env["NODE_COMPILE_CACHE"] = os.path.join(scratch, "node-cache")
    return env


def scratch_for(git_dir: str) -> str:
    """One scratch directory per worktree, at a fixed path, so a killed hook's leftovers are removed by the next run."""
    key = hashlib.sha1(git_dir.encode("utf-8")).hexdigest()[:12]
    return os.path.join(tempfile.gettempdir(), "gen-docs-precommit-%s" % key)


def _hits_table(hits: list[dict]) -> str:
    rows = []
    for hit in hits[:12]:
        why = {"machinery": "the generator itself", "target": "a document carrying a region"}.get(
            hit["why"], ", ".join(hit["providers"])
        )
        rows.append("    %s  (%s)" % (hit["path"], why))
    if len(hits) > 12:
        rows.append("    ... and %d more" % (len(hits) - 12))
    return "\n".join(rows)


def _unchecked(why: str) -> int:
    return _refuse(
        "UNCHECKED: this commit could not be checked against the generated doc regions (%s).\n"
        "An unknown is not a pass. Fix the cause, or run `%s` and commit the result."
        % (why, GEN_FIX)
    )


def pre_commit(_argv: list[str]) -> int:
    """Both generated-file checks, cheapest refusal first: the doc regions, then the registry's artifacts."""
    code = gen_docs_pre_commit()
    if code != 0:
        return code
    return artifacts_pre_commit()


def gen_docs_pre_commit() -> int:
    started = time.monotonic()
    repo = _repo()
    entry = _index_text(repo, GEN_ENTRY) if repo else None
    if entry is None:
        return 0  # a submodule, or any repository without the generator: nothing here reads it
    if "'--affected'" not in entry:
        # THE COMMITTED GENERATOR PREDATES THIS HOOK: it declares no provider inputs and has no `--affected` mode, so there is nothing to judge by, and running it under plain node fails on its `.js` specifiers (measured 2026-10-06, ERR_MODULE_NOT_FOUND, blocking every commit until this branch existed). Said, never silent.
        sys.stderr.write(
            "gen-docs pre-commit: the committed %s has no --affected mode yet; not checked\n"
            % GEN_ENTRY
        )
        return 0
    node = shutil.which("node")
    if node is None:
        return _unchecked(
            "`node` is not on PATH; install Node 24 (.devcontainer/toolchain.env pins it) or commit from the devbox"
        )
    git_dir = _git(["rev-parse", "--absolute-git-dir"])
    if not git_dir:
        return _unchecked(
            "`git rev-parse --absolute-git-dir` answered nothing, so there is no scratch tree to verify in"
        )
    scratch = scratch_for(git_dir)
    sel = os.path.join(scratch, "sel")
    tree = os.path.join(scratch, "tree")
    try:
        closure = generator_closure(repo)
        env = _gen_env(repo, scratch)
        shutil.rmtree(sel, ignore_errors=True)
        _run(["git", "checkout-index", "-f", "--prefix=%s/" % sel, "--", *closure], repo, env)
        proc = _run([node, os.path.join(sel, GEN_ENTRY), "--affected"], repo, env, SELECT_TIMEOUT)
        if proc.returncode != 0:
            return _unchecked(
                "`gen-docs.ts --affected` exited %d: %s"
                % (proc.returncode, proc.stderr.strip()[-600:])
            )
        verdict = json.loads(proc.stdout)
        hits = verdict["hits"]
        if not hits:
            if os.environ.get("GEN_DOCS_PRECOMMIT_VERBOSE") == "1":
                sys.stderr.write(
                    "gen-docs pre-commit: %d staged path(s), none read by any of %d providers (%.2fs)\n"
                    % (verdict["staged"], verdict["providers"], time.monotonic() - started)
                )
            return 0
        shutil.rmtree(tree, ignore_errors=True)
        out = _run(
            ["git", "-c", "checkout.workers=-1", "checkout-index", "-a", "--prefix=%s/" % tree],
            repo,
            env,
            VERIFY_TIMEOUT,
        )
        if out.returncode != 0:
            return _unchecked(
                "checking out the commit's tree failed: %s" % out.stderr.strip()[-600:]
            )
        tree_env = dict(env, GIT_DIR=git_dir, GIT_WORK_TREE=tree)
        runs: list[list[str]] = [[]] + ([["--check-inputs"]] if verdict["machinery"] else [])
        for extra in runs:
            proc = _run(
                [node, os.path.join(tree, GEN_ENTRY), *extra], tree, tree_env, VERIFY_TIMEOUT
            )
            if proc.returncode == 0:
                continue
            drifted = _DRIFT_RE.findall(proc.stderr)
            if extra or not drifted:
                return _unchecked(
                    "`gen-docs.ts %s` exited %d on the commit's tree:\n%s"
                    % (
                        " ".join(extra) or "(verify)",
                        proc.returncode,
                        (proc.stderr or proc.stdout).strip()[-1500:],
                    )
                )
            return _refuse(
                "this commit leaves a generated doc region stale.\n\n"
                "  It stages what a gen-docs provider reads:\n%s\n\n"
                "  and gen-docs, run against the commit's own tree, reports:\n%s\n\n"
                "  Fix: regenerate, then commit the regenerated file(s) WITH the input(s):\n"
                "    %s\n"
                "    git commit -F <msg> -- <the same paths> %s\n"
                "  (or `git add -- %s` before a plain commit). If the drift persists after --write, the\n"
                "  working tree holds an unstaged edit to another provider input that this commit leaves\n"
                "  out; `git status` names it."
                % (
                    _hits_table(hits),
                    "\n".join("    " + line for line in proc.stderr.strip().splitlines()[:12]),
                    GEN_FIX,
                    " ".join(drifted),
                    " ".join(drifted),
                )
            )
        sys.stderr.write(
            "gen-docs pre-commit: %d of %d staged path(s) touch a region's inputs; the commit's tree verified clean%s (%.1fs)\n"
            % (
                len(hits),
                verdict["staged"],
                ", provider inputs re-traced" if verdict["machinery"] else "",
                time.monotonic() - started,
            )
        )
        return 0
    except subprocess.TimeoutExpired as exc:
        return _unchecked(
            "`%s` timed out after %ss" % (" ".join(str(a) for a in exc.cmd[:3]), exc.timeout)
        )
    except (UncheckedError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return _unchecked(str(exc) or type(exc).__name__)
    finally:
        shutil.rmtree(tree, ignore_errors=True)


# THE REGISTRY'S ARTIFACTS (`artifacts.py` carries the why and the rules). The same shape as the doc-region check above, for every generated file that declares its inputs in `.ci/config/generated-artifacts.json`: no staged input is two git calls and silence; a staged input runs the entry's checker on a checkout of the commit's index, under the entry's budget. The scratch tree is this worktree's fixed directory, so a killed run's leftovers are removed by the next one, and it holds only LINKS to the working tree's build products, which `shutil.rmtree` unlinks and never follows.


def artifacts_pre_commit() -> int:
    started = time.monotonic()
    repo = _repo()
    if not repo:
        return 0
    git_dir = _git(["rev-parse", "--absolute-git-dir"])
    scratch = scratch_for(git_dir or repo)
    env = _gen_env(repo, scratch)
    try:
        verdicts, staged, enrolled = ga.judge(
            repo, git_dir, env, os.path.join(scratch, "artifacts-tree")
        )
    except ga.RegistryError as exc:
        return _refuse(
            "UNCHECKED: this commit could not be checked against the generated artifacts.\n%s\n"
            "An unknown is not a pass." % exc
        )
    except subprocess.TimeoutExpired as exc:
        return _refuse(
            "UNCHECKED: `%s` timed out after %ss while the generated artifacts were being checked. An unknown is not a pass."
            % (" ".join(str(a) for a in exc.cmd[:3]), exc.timeout)
        )
    except OSError as exc:
        return _refuse(
            "UNCHECKED: the generated artifacts could not be checked (%s). An unknown is not a pass."
            % (str(exc) or type(exc).__name__)
        )
    for verdict in verdicts:
        if verdict.kind == "stale":
            return _refuse(ga.stale_message(verdict))
        if verdict.kind != "clean":
            return _refuse(ga.unchecked_message(verdict))
        sys.stderr.write(ga.clean_line(verdict, staged))
    if not verdicts and enrolled and os.environ.get("GEN_DOCS_PRECOMMIT_VERBOSE") == "1":
        sys.stderr.write(
            "%s: %d staged path(s), none an input of the %d enrolled artifact(s) (%.2fs)\n"
            % (ga.LABEL, staged, enrolled, time.monotonic() - started)
        )
    return 0


def main(hook: str, argv: list[str]) -> int:
    if os.environ.get("COMMIT_POLICY_OK", "") == "1":
        return 0
    if hook == "commit-msg":
        return commit_msg(argv)
    # Before the stdin read below: git gives pre-commit no stdin, so reading it would block on a terminal.
    if hook == "pre-commit":
        return pre_commit(argv)
    stdin = sys.stdin.read()
    if hook == "reference-transaction":
        return reference_transaction(argv, stdin)
    if hook == "pre-push":
        return pre_push(argv, stdin)
    return 0


def shim(path: str) -> None:
    """The entry every hook file calls: its own basename names the hook."""
    try:
        code = main(pathlib.Path(path).name, sys.argv[1:])
    except subprocess.SubprocessError as exc:
        sys.stderr.write("commit-policy: hook failed to run git (%s); allowing\n" % exc)
        code = 0
    sys.exit(code)
