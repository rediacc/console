"""Block `git worktree add` from the assistant's own Bash tool, unconditionally.

WHY UNCONDITIONAL. A hook has no reliable, verified way to tell "a live operator just approved this" from "an autonomous/cron-fired continuation
with nobody watching" -- there is no session field this codebase's other
hooks rely on for that distinction, and inventing one on an unverified guess is worse than not trying. So the policy is enforced by WHO can get the command to run at all, not by the hook reading intent:
  - An operator who wants a worktree created can run the command
    themselves via the `!` prefix (CLAUDE.md's documented escape hatch),
    which never reaches this hook -- that IS "asked the operator, they
    said yes", made structural rather than inferred.
  - An autonomous/cron-fired session has no live operator to relay that
    to, so the practical effect is worktree creation never happens there,
    which is exactly the "non-interactive: not allowed" requirement.

Found live 2026-08-01: a session created a throwaway worktree+branch for a small doc edit mid-/pr-merge, then a second one for a NUL-byte gate fix, after the operator had already twice said to keep changes local instead. The operator then found six PRE-EXISTING worktrees holding real, unrelated work from other sessions sitting untouched in the same repo. Worktrees are cheap to
create and easy to forget, and each one is a place uncommitted work can silently strand outside the one tree everyone actually watches.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-worktree-add.sh"
ORDER = 29

# THE WRAPPER SAILED STRAIGHT PAST THE FIRST CHECK, and removing the second one puts it back: `./run.sh worktree create` runs the banned command through a script whose text never contains it.
DEFECT = ("if hookio.grep_q(RUN_SH_CREATE, scan):", "if False:")

# Command position: line start (or wrapper-payload line start), or after ; & | ( $( or a backtick. `git -C <path> worktree add ...` still matches since -C is a flag between `git` and `worktree`, not a new command.
#
# PORT NOTE. The bash writes this pattern inside DOUBLE quotes, so `\\\$\\(` reaches grep as `\$\(` and the backtick is bare. Here the pattern is a raw Python string, so the same ERE is spelled once instead of twice.
GIT_AT_CMD = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+")

WORKTREE_ADD = GIT_AT_CMD + hookio.rx(r"worktree[{S}]+add([{S}]|$)")

# THE WRAPPER SAILED STRAIGHT PAST THE CHECK ABOVE. `./run.sh worktree create` reaches scripts/dev/worktree.sh, which runs `git worktree add -b ...` -- the exact command this hook exists to stop -- but the text the hook sees never contains "git worktree add", so it matched nothing. The block was literal, and the wrapper is not literal.
#
# This got more urgent, not less: `worktree create` now also brings a devbox up, so the bypass costs a multi-GB image pull and a held port block on top of the unwanted checkout.
#
# NO "am I an agent?" SNIFF, deliberately. The operator's `!`-prefixed command runs in the SAME session with the SAME environment, so any such test would block the sanctioned path too. The `!` prefix bypasses PreToolUse hooks entirely, which is the whole mechanism -- there is nothing here to detect. The `(bash|sh)[[:space:]]+` prefix is not decoration: `bash scripts/dev/worktree.sh
# create` puts the INTERPRETER in command position, not the script, so a command-position-anchored match misses it entirely. Caught by driving both forms through this hook rather than reading the regex.
RUN_SH_CREATE = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*((bash|sh)[{S}]+)?(\./)?(run\.sh|[A-Za-z0-9_./-]*worktree\.sh)[{S}]+(worktree[{S}]+)?create([{S}]|$)"
)

GIT_MESSAGE = (
    "❌ BLOCKED: git worktree add is not run from here. Worktree creation needs the "
    "operator to approve it explicitly THIS session, then run the command themselves via "
    "the `!` prefix (bypasses this hook) -- do not ask the operator through chat and then "
    "run it yourself, and never create one in an autonomous/cron-fired continuation with "
    "no live operator to ask. Prefer working directly in the current checkout, a plain "
    "`git clone`, or an existing worktree instead. If you believe you already have "
    "explicit sign-off, hand the exact command back to the operator to run with `!`."
)

RUN_SH_MESSAGE = (
    "❌ BLOCKED: `run.sh worktree create` creates a git worktree (and now a devbox "
    "container with it), so it is the same decision as `git worktree add` and carries the "
    "same rule: the operator approves it explicitly THIS session and runs it themselves "
    "via the `!` prefix, which bypasses this hook. Do not ask through chat and then run it "
    "yourself, and never in an autonomous/cron-fired continuation with no live operator to "
    "ask. Prefer the current checkout or an existing worktree. `worktree list`, `switch`, "
    "`remove` and `prune` are unaffected."
)

EDGE_CASES = [
    ("the plain shape", "git worktree add /tmp/wt main"),
    ("a -C flag between git and the verb", "git -C private/renet worktree add /tmp/wt"),
    ("after a separator", "true; git worktree add /tmp/wt"),
    # The wrapper the second arm exists for, in both spellings.
    ("the run.sh wrapper", "./run.sh worktree create 0901-1"),
    ("the script directly, through an interpreter", "bash scripts/dev/worktree.sh create x"),
    # Reads are none of this hook's business.
    ("listing worktrees is allowed", "git worktree list"),
    ("removing a worktree is allowed", "git worktree remove /tmp/wt"),
    ("run.sh doing something else", "./run.sh setup --check"),
    ("prose is stripped before the scan", "echo 'git worktree add /tmp/wt'"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if hookio.grep_q(WORKTREE_ADD, scan):
        ev.warn(GIT_MESSAGE)
        return hookio.DENY

    if hookio.grep_q(RUN_SH_CREATE, scan):
        ev.warn(RUN_SH_MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
