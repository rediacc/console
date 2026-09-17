"""WARNING ONLY. Always exits 0. Never blocks.

The hooks are the enforcement layer, and until 2026-08-25 nothing at all guarded changing them: block-protected-files.sh covers only settings.json and pre-commit-check.sh, and only against restore/checkout/rm. One session changed 5 hook files across 6 commits with no friction. A session that finds a guard inconvenient can weaken it AND delete its controls in the same commit.

The operator chose WARN over BLOCK here (2026-08-25): a hard block would have fired six times that day on legitimate hook work. The teeth are in CI instead -- check:ci-hook-integrity holds a shrink-only inventory and requires every guard to keep controls in BOTH directions. This is the reminder at the moment
of the act; the gate is what actually refuses.

PORT NOTE ON THE `|| exit 0` AFTER THE jq. The bash reads
`CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command' 2>/dev/null) || exit 0`,
where the `||` tests the PIPELINE's status, i.e. jq's. That arm is unobservable here and stays unobservable in the port: a jq failure yields the empty string, the empty string does not contain `git commit`, and the `case` below allows just as the `|| exit 0` would have. It is reproduced as an explicit early
return anyway, because the next reader should not have to re-derive that the
two paths coincide.

PORT NOTE ON WHERE `git` RUNS. The bash never `cd`s, so `git diff --cached` reads whatever directory the harness invoked the hook from -- the session's cwd, not `CLAUDE_PROJECT_DIR`. The port keeps that exactly: `git_out` is called
with no `cwd`, so it inherits this process's directory the way a forked `git`
inherited the shell's. That is also why this module's ENVS point `GIT_DIR` at its fixtures rather than `CLAUDE_PROJECT_DIR`, which this guard never reads.
"""

import subprocess

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/warn-hook-change.sh"
ORDER = 36

# Without the `git commit` test the note fires on every Bash call the session makes while anything under .claude/hooks/ is staged -- which, during hook work, is most of them. That is the difference between "the reminder at the moment of the act" and a banner nobody reads.
DEFECT = ('if not hookio.case_glob(cmd, "*git commit*"):', "if False:")

# The staged paths that count. `grep '^\\.claude/hooks/'` in the original is a BRE, and this pattern means the same thing under ERE, so no translation is needed beyond the escaping Python already requires.
HOOK_PATH = r"^\.claude/hooks/"


def _fixture_git(cwd, *args):
    """`git` for the fixture builders below, with the ambient config shut out.

    GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM are pointed at /dev/null for the same reason the shared fixtures in the differential do it: a host `commit.gpgsign` or a `core.hooksPath` would otherwise reach into a tree that is supposed to be a controlled world.
    """
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/nonexistent",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )


def _repo_with_staged(path, hook_files):
    """A repo whose index holds `hook_files` plus one file that is not a hook.

    The non-hook file is not padding: it is the only thing that proves the `^\\.claude/hooks/` filter is doing any filtering, and a fixture that staged hooks alone would let the port drop the grep and still pass.
    """
    path.mkdir(parents=True)
    _fixture_git(path, "init", "--initial-branch=main", "-q")
    (path / "README.md").write_text("not a hook\n", encoding="utf-8")
    _fixture_git(path, "add", "README.md")
    for name in hook_files:
        target = path / ".claude" / "hooks" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        _fixture_git(path, "add", str(target))
    return path


FIXTURES = {
    # Two hook files, so the port's per-line indentation loop is exercised on more than one record.
    "hooks-staged": lambda p: _repo_with_staged(
        p, ["pre-bash/block-example.sh", "pre-edit/warn-example.sh"]
    ),
    # The same world with nothing under .claude/hooks/ staged: the ALLOW side, and the only reason the grep above is visible to the differential.
    "hooks-clean": lambda p: _repo_with_staged(p, []),
}

# WHY THE LIVE WORKTREE IS NOT ONE OF THESE. The guard's answer is a function of whatever happens to be in THIS checkout's index, and this tree is shared with other sessions and other agents. A `git add` landing between the bash sweep and the Python sweep would be reported here as a port defect, so both variants are controlled worlds built by the builders above.
ENVS = [
    (
        "staged",
        {
            "GIT_DIR": "{FIXTURE:hooks-staged}/.git",
            "GIT_WORK_TREE": "{FIXTURE:hooks-staged}",
        },
        {},
    ),
    (
        "clean",
        {
            "GIT_DIR": "{FIXTURE:hooks-clean}/.git",
            "GIT_WORK_TREE": "{FIXTURE:hooks-clean}",
        },
        {},
    ),
]

EDGE_CASES = [
    ("the plain commit", "git commit -m 'fix a guard'"),
    # `case "$CMD" in *"git commit"*)` is an UNANCHORED glob, so a commit in a later clause, in a wrapper, or inside quoted prose all reach the check. That is the original's behaviour and the port must keep it, warts and all.
    ("a commit in a later clause", "git add -A && git commit -m x"),
    ("quoted prose still counts as a commit", "echo 'then git commit -m x'"),
    ("git commit-tree is a substring match too", "git commit-tree HEAD^{tree}"),
    ("a non-commit git verb", "git status"),
    ("no git at all", "ls -la"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    # `... 2>/dev/null) || exit 0`: a jq failure gives "" and allows. See the port note in the module docstring for why this arm cannot be observed.
    if cmd == "":
        return hookio.ALLOW

    if not hookio.case_glob(cmd, "*git commit*"):
        return hookio.ALLOW

    # `git diff --cached --name-only 2>/dev/null | grep '^\\.claude/hooks/' || true`.
    # The `|| true` only stops the pipeline's failure status from escaping; the
    # substitution keeps grep's (possibly empty) output either way, which is what the `[ -n "$STAGED" ]` below then tests.
    staged = hookio.git_out(["diff", "--cached", "--name-only"])
    hooks = hookio.grep_lines(HOOK_PATH, staged)
    if not hooks:
        return hookio.ALLOW

    ev.warn("NOTE: this commit changes the enforcement layer itself:")
    # `printf '%s\n' "$STAGED" | while IFS= read -r f; do printf '  %s\n' "$f"; done`
    for path in hooks:
        ev.warn("  %s" % path)
    ev.warn("  A guard weakened is a rule deleted. If any of these relaxes a check,")
    ev.warn("  say so in the commit message and keep its controls in BOTH directions")
    ev.warn("  (one case asserting it blocks, one asserting it allows) -- a guard with")
    ev.warn("  only block-cases cannot detect over-blocking, which is how a guard ends")
    ev.warn("  up removed. check:ci-hook-integrity enforces this in CI.")
    return hookio.ALLOW
