"""The git-level half of the commit policy: `commit-msg`, `reference-transaction` and `pre-push`.

WHY A SECOND LAYER (the commit-policy plan in agent/plans, section 5.3; operator ruling 2, 2026-09-25: installed for everyone, with the `COMMIT_POLICY_OK=1` override). The pre-bash guards see only an agent's own Bash tool calls. Everything else that commits, cuts a branch or pushes never reaches them: the operator's terminal and `!` commands, and subprocesses (`worklist.py --git`, the per-commit reviewer, release scripts run locally; the 2026-09-22 push to `main` came from a script three process levels below the Bash call). Git runs these hooks for all of them once `core.hooksPath` points at this directory, which the `git-hooks-path` setup phase does in the console and in every checked-out submodule (`.ci/rediacc_ci/setup/githooks.py`). It is local config only, so `/tmp` fixtures and CI checkouts are unaffected.

WHAT EACH HOOK REFUSES (the rules are `commit_policy`'s, shared with the pre-bash guards):

  commit-msg              a CI skip token; a commit on `main` that is not a well-formed `[hotfix]`; `[hotfix]` off `main`; `[no-review]` on a non-writing path or on a `[hotfix]`.
  reference-transaction   in the `prepared` state, a new `refs/heads/*` (old oid all zeros) that breaks the one-branch rule: outside a submodule, only from `main`, with no other live branch and an `MMDD-N` name; in a submodule, only the console's current branch name. LOCAL FACTS ONLY: no `gh`, so a branch counts as live until its upstream is gone.
  pre-push                a push to `main` other than the fast-forward fallback (one ref, a real commit, the live branch's pushed tip, the remote `main` its ancestor; box M2 of PLAN-plan-per-pr-loop, operator ruling 2026-10-02) or the GitLab mirror push (below), a delete of `main` included; a push creating a remote branch that is not the current one.

THE PRE-BASH LAYER STAYS AUTHORITATIVE FOR AGENTS; this is the backstop. It reads no `gh`, so it cannot compute today's next name or know a PR merged; it checks shape and local liveness only.

`git branch -m` IS INVISIBLE HERE, and that is measured rather than assumed (T0(b), git 2.53, 2026-09-25): a rename reaches `reference-transaction` only as an aborted empty transaction and a DELETE of the old name; the new name is never shown as a creation. So a rename is always allowed at this layer, which is the rule anyway (the count stays at one).

THE OVERRIDE. `COMMIT_POLICY_OK=1` in the environment makes every hook here exit 0. It is the operator's; `block_git_hook_bypass` refuses an agent command that sets it, or that skips these hooks with `--no-verify`, `-n` or `-c core.hooksPath=`.

LOADED BY FILE, NOT BY PACKAGE. Git runs a hook as a plain executable with no package context, so each shim beside this file loads it with `importlib`, and this module loads `commit_policy.py` the same way. No `sys.path` entry is added anywhere, which `test_canonical_sys_path_hop.py` freezes.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
CONSOLE_ROOT = HERE.parents[2]


def _load_policy():
    spec = importlib.util.spec_from_file_location("commit_policy", HERE.parent / "commit_policy.py")
    if spec is None or spec.loader is None:
        raise SystemExit("commit-policy hook: %s/commit_policy.py is missing" % HERE.parent)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp = _load_policy()

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


def commit_msg(argv: list[str]) -> int:
    if not argv:
        return 0
    try:
        raw = pathlib.Path(argv[0]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    msg = "\n".join(line for line in raw.split("\n") if not line.startswith("#"))
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
    out = []
    for line in stdin.split("\n"):
        fields = line.split()
        if len(fields) != 3:
            continue
        old, new, ref = fields
        if old != cp.ZERO_OID or new == cp.ZERO_OID or new.startswith("ref:"):
            continue
        if ref.startswith("refs/heads/"):
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

    LOCAL FACTS ONLY, like every hook here: one ref in the whole push, a real commit (not a delete), the live branch's pushed tip (`<remote>/<live>`), and the remote's current `main` its ancestor. Whether that tip is the open PR's head with CI Complete green is the pre-bash guard's question (it reads `gh`); this layer stops every other shape from every source.
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


def pre_push(argv: list[str], stdin: str) -> int:
    repo = _repo()
    current = cp.current_branch(repo) if repo else ""
    remote = argv[0] if argv else "origin"
    lines = [line.split() for line in stdin.split("\n") if len(line.split()) == 4]
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
    for line in lines:
        _local_ref, local_oid, remote_ref, remote_oid = line
        if not remote_ref.startswith("refs/heads/"):
            continue
        name = remote_ref[len("refs/heads/") :]
        if name == "main":
            reason = _main_push_refusal(repo, remote, current, lines, line)
            if reason:
                return _refuse(
                    "this pushes to `main` and is not the fast-forward fallback (%s).\n"
                    "Landings go through `gh pr merge <n> --rebase --auto`. The one direct push\n"
                    "(operator ruling 2026-10-02) is a fast-forward of the live branch's pushed tip\n"
                    "that is the open PR's head with CI Complete green:\n"
                    "`git push origin origin/<live MMDD-N branch>:main`, one refspec, nothing forced."
                    % reason
                )
            continue
        if local_oid == cp.ZERO_OID:
            continue
        if remote_oid == cp.ZERO_OID and name != current:
            return _refuse(
                "this creates the remote branch `%s`, and the one live branch is `%s`."
                % (name, current or "(detached)")
            )
    return 0


def main(hook: str, argv: list[str]) -> int:
    if os.environ.get("COMMIT_POLICY_OK", "") == "1":
        return 0
    if hook == "commit-msg":
        return commit_msg(argv)
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
