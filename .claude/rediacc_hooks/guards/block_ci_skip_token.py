"""Refuse a commit message carrying a CI skip token.

WHY (the commit-policy plan in agent/plans, section 4.3, and F7). On a `pull_request` or `push` event GitHub reads the head commit for `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`, `[actions skip]` and a `skip-checks: true` trailer, and skips the workflow. A skipped workflow leaves its required checks pending: ruleset 12344707 requires `CI Complete` and `Review Complete`, so the PR sits at "Expected" until something else is pushed. On `main` a skip also skips the release, which is exactly why the two bot commits use it (`update_homebrew_tap.py`, `advance_contract_floor.py`); they run as subprocesses in CI and never reach this hook.

`[no-ci]` IS REFUSED TOO. The operator asked whether a `[no-ci]` tag was wanted; the plan rejected it: it would need a second skip path in `initialize` beside the attested scope-engine skip-plan and the pointer-bump fast path that already make cheap commits cheap, CI runs per push rather than per commit, and the `ci:quick` receipt is required before any push anyway. Refusing the spelling keeps anyone from believing it does something.

WHAT IS READ. The message of every `git commit` bash would run, in the three readable shapes (`-m`, `-F -` with a heredoc, `-F <file>`) plus `--trailer` values, which git writes into the same message. A mention in prose, `git log --grep`, or a commit in a repository outside this checkout is none of this guard's business.
"""

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 47

# The token finder. With it emptied every skip token reaches the PR head.
DEFECT = ("found = commit_policy.skip_tokens(msg, cfg)", "found = []")

EDGE_CASES = [
    ("[skip ci]", 'git commit -m "chore: x [skip ci]" -- a'),
    ("[ci skip]", 'git commit -m "chore: x [ci skip]" -- a'),
    ("[no ci]", 'git commit -m "chore: x [no ci]" -- a'),
    ("[skip actions]", 'git commit -m "chore: x [skip actions]" -- a'),
    ("[actions skip]", 'git commit -m "chore: x [actions skip]" -- a'),
    ("the rejected [no-ci]", 'git commit -m "chore: x [no-ci]" -- a'),
    ("the trailer form", 'git commit -m "chore: x\n\nskip-checks: true" -- a'),
    ("a --trailer value", 'git commit -m "chore: x" --trailer "skip-checks: true" -- a'),
    ("a heredoc message", "git commit -F - -- a <<'EOF'\nchore: x [skip ci]\nEOF"),
    ("a clean commit", 'git commit -m "chore: x" -- a'),
    ("prose naming the token", "echo 'never write [skip ci]'"),
    ("git log --grep", "git log --grep '[skip ci]'"),
    ("a scratch repo", 'git -C /tmp commit -m "x [skip ci]" -- a'),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    commits = commit_policy.git_runs(cmd, "commit")
    if not commits:
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    cfg = commit_policy.load_config(root)
    for commit in commits:
        repo = commit_policy.run_repo(commit, base)
        # A directory that resolves to no repository is one git itself will refuse; one outside this checkout is not this policy's business.
        if not repo or not commit_policy.is_inside(repo, root):
            continue
        msg = commit_policy.commit_message_text(cmd, base, run=commit)
        found = commit_policy.skip_tokens(msg, cfg)
        if found:
            ev.warn_raw(
                "BLOCKED: this commit message carries a CI skip token: %s.\n"
                "\n"
                "GitHub skips the workflow for a head commit carrying one, and the required\n"
                '`CI Complete` check then sits at "Expected" until something else is pushed.\n'
                "`[no-ci]` is refused as well: it was proposed and rejected, and it skips\n"
                "nothing. CI runs per push, not per commit, so committing often costs no CI;\n"
                "batch the pushes instead. Drop the token and commit again.\n"
                % ", ".join("`%s`" % t for t in found)
            )
            return hookio.DENY
    return hookio.ALLOW
