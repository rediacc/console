"""WARNING ONLY. Always exits 0. Never blocks.

The hooks are the enforcement layer, and until 2026-08-25 nothing at all guarded changing them: block-protected-files.sh covers only settings.json and pre-commit-check.sh, and only against restore/checkout/rm. One session changed 5 hook files across 6 commits with no friction. A session that finds a guard inconvenient can weaken it AND delete its controls in the same commit.

The operator chose WARN over BLOCK here (2026-08-25): a hard block would have fired six times that day on legitimate hook work. The teeth are in CI instead -- check:ci-hook-integrity holds a shrink-only inventory and requires every guard to keep controls in BOTH directions. This is the reminder at the moment of the act; the gate is what actually refuses.

PORT NOTE ON THE `|| exit 0` AFTER THE jq. The bash reads
`CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command' 2>/dev/null) || exit 0`,
where the `||` tests the PIPELINE's status, i.e. jq's. That arm is unobservable here and stays unobservable in the port: a jq failure yields the empty string, the empty string does not contain `git commit`, and the `case` below allows just as the `|| exit 0` would have. It is reproduced as an explicit early
return anyway, because the next reader should not have to re-derive that the
two paths coincide.

PORT NOTE ON WHERE `git` RUNS. The bash never `cd`s, so `git diff --cached` reads whatever directory the harness invoked the hook from -- the session's cwd, not `CLAUDE_PROJECT_DIR`. The port keeps that exactly: `git_out` is called
with no `cwd`, so it inherits this process's directory the way a forked `git`
inherited the shell's. That is also why this module's ENVS point `GIT_DIR` at its fixtures rather than `CLAUDE_PROJECT_DIR`, which this guard never reads.
"""

from rediacc_hooks import hookio
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "warn_hook_change", "EDGE_CASES", "ENVS", "FIXTURES", "_fixture_git", "_repo_with_staged"
)

CHAIN = "pre-bash"
ORDER = 35

# Without the `git commit` test the note fires on every Bash call the session makes while anything under .claude/hooks/ is staged -- which, during hook work, is most of them. That is the difference between "the reminder at the moment of the act" and a banner nobody reads.
DEFECT = ('if not hookio.case_glob(cmd, "*git commit*"):', "if False:")

# The staged paths that count. `grep '^\\.claude/hooks/'` in the original is a BRE, and this pattern means the same thing under ERE, so no translation is needed beyond the escaping Python already requires.
HOOK_PATH = r"^\.claude/hooks/"


def run(ev):
    cmd = ev.raw("tool_input", "command")
    # `... 2>/dev/null) || exit 0`: a jq failure gives "" and allows. See the port note in the module docstring for why this arm cannot be observed.
    if cmd == "":
        return hookio.ALLOW

    if not hookio.case_glob(cmd, "*git commit*"):
        return hookio.ALLOW

    # `git diff --cached --name-only 2>/dev/null | grep '^\\.claude/hooks/' || true`. The `|| true` only stops the pipeline's failure status from escaping; the substitution keeps grep's (possibly empty) output either way, which is what the `[ -n "$STAGED" ]` below then tests.
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
