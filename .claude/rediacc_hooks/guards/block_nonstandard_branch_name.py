"""A feature branch is `MMDD-N`. No suffixes, no words, no decoration.

WHY. `.claude/commands/pr-babysit.md` and `.claude/commands/pr-merge.md` both state the convention, and pr-merge's hand-back section warns that guessing a name produces stray refs the next `/pr-babysit` has to clean up. On 2026-08-26 a session created `0826-1-prerebase` in the console AND in a submodule, as safety copies before a rebase. Reasonable intent, wrong shape: the suffix
makes the ref sort next to a wave branch while belonging to no wave, and nothing downstream -- not pr-babysit's branch listing, not the submodule same-name matching in branch-rebase.md's submodule step, not pr-merge's coordinated-PR lookup -- can tell the two apart.

THE SUBMODULE POINT IS THE SHARP ONE. `/pr-merge` finds a submodule's PRs by matching the console branch name EXACTLY. A console branch carrying a suffix silently matches nothing, so a coordinated submodule PR is invisible to the merge path and gets left behind.

ONLY CREATION IS CHECKED. `git branch -d`, `-r`, `--list`, `--show-current` and `--contains` read; they are none of this hook's business. Blocking a read would be the over-matching that gets a guard switched off.

CITED BY HEADING, NOT LINE. Three of this file's original `:NNN` references rotted inside the same session that wrote them, because the files they point at were edited in the same working tree. block-blanket-git-add.sh adopted the heading convention for exactly this reason.

`main` is allowed because it is not a feature branch. Nothing else is special cased: if a name is neither `main` nor `MMDD-N`, the convention does not describe it, and the operator is the one who decides to widen the convention.

PORT NOTE ON `read -ra TOKENS <<<"$BRANCH_ARGS"`. `read` splits on IFS (space, tab, newline -- NOT `\\r`, which Python's bare `str.split()` would also eat), performs no pathname expansion, and reads ONE line. `BRANCH_ARGS` has already been through `head -1`, so the single-line part is guaranteed; the split below is written out with the exact IFS set rather than delegated to
`split()`.
"""

import os
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 16

# The earlier draft, restored. Skipping any candidate that merely CONTAINS a slash silently let `checkout -b feature/x` through -- the exact shape this hook exists to refuse -- while still looking like a start-point carve-out.
DEFECT = (r"^[0-9a-f]{7,40}$|^origin/|^refs/", r"^[0-9a-f]{7,40}$|/")

# Cheap reject: no branch-creating verb anywhere.
HAS_BRANCH_VERB = hookio.rx(
    r"git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+(branch|checkout|switch)([{S}]|$)"
)

# -b/-B (checkout), -c/-C (switch): the new name is the next token.
#
# ANCHORED TO A COMMAND POSITION, and the anchor is not decoration. Without it the pattern matched a shell VARIABLE ASSIGNMENT whose value happened to hold
# the words -- `SLASH='git checkout -b some/name'` -- and refused a line that
# runs nothing. Requiring `git` after a command boundary is what makes this a guard on an act rather than on a vocabulary.
GIT_AT_CMD = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+")

NEW_BRANCH_FLAG = GIT_AT_CMD + hookio.rx(
    r"(checkout|switch)([{S}]+-[A-Za-z-]+)*[{S}]+-[bBcC][{S}]+[^{S};|&)]+"
)

LAST_FIELD = hookio.rx(r"[^{S}]+$")

BRANCH_TAIL = GIT_AT_CMD + hookio.rx(r"branch[{S}]+[^;|&]*")

# A read-only or delete invocation is not our business.
READ_ONLY = hookio.rx(
    r"(^|[{S}])-(d|D|r|a|v|-list|-show-current|-contains|-merged|-no-merged|-delete|-remotes|-all|-verbose|-set-upstream-to|-unset-upstream|-edit-description)"
)

RENAME = hookio.rx(r"(^|[{S}])-[mM]([{S}]|$)")

EDGE_CASES = [
    ("the 2026-08-26 shape", "git checkout -b 0826-1-prerebase"),
    ("a conforming name", "git checkout -b 0901-1"),
    ("a slashed name is still a name being created", "git checkout -b feature/x"),
    ("switch has its own flag letters", "git switch -c 0901-2-wip"),
    ("a start point is not a name being created", "git checkout -b 0901-3 origin/main"),
    # `git branch` reads are none of this hook's business.
    ("deleting a branch", "git branch -d 0826-1"),
    ("listing branches", "git branch --show-current"),
    ("a plain create", "git branch 0901-4"),
    ("a plain create with a bad name", "git branch prerebase-copy"),
    # The rename form judges the SECOND positional.
    ("a rename into a legal name", "git branch -m old 0901-5"),
    ("a rename into a suffixed one", "git branch -m old 0901-5-prerebase"),
    # The two things the anchor and the stripper exist for.
    ("a variable assignment runs nothing", "SLASH='git checkout -b some/name'"),
    ("a heredoc body is data", "cat > note.md <<'EOF'\ngit checkout -b some/name\nEOF"),
    ("switching to main", "git checkout main"),
]


def _tokens(text):
    """`read -ra TOKENS <<<"$text"` -- IFS words, no expansion, first line."""
    first = text.split("\n")[0] if text != "" else ""
    return [t for t in re.split(r"[ \t]+", first.strip(" \t")) if t != ""]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    # A HEREDOC BODY IS DATA, NOT A COMMAND. This hook blocked its own commit message for saying so: the message described the slashed-name shape the guard refuses, and the guard read the description as the act. It then blocked the edit that would have fixed it, for the same reason -- the fix had to come through the Edit tool. That is the fifth mention-vs-execution false positive
    # in one session, so this uses the SHARED stripper the rest of the pre-bash family already uses rather than inventing a fifth private one.
    #
    # Only heredoc BODIES are dropped, deliberately: hook_scan_target also strips quoted strings, and a branch name may legitimately be quoted, so using it would fail this open on `git branch "bad name"`.
    cmd = shellscan._command_substitution(shellscan._strip_heredocs(cmd))

    if not hookio.grep_q(HAS_BRANCH_VERB, cmd):
        return hookio.ALLOW

    # ANOTHER PROJECT'S BRANCHES ARE NOT THIS REPO'S CONVENTION. Found 2026-09-24 restoring four branches in /home/developer/rovaip (a different project) with `git -C /home/developer/rovaip branch chore/... <sha>`: the MMDD-N rule refused them. Exempt only a target OUTSIDE this checkout; submodules under private/ are separate git roots but keep the rule, because /pr-merge matches their coordinated branch names exactly.
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    other = shellscan.target_root(cmd, root) if root else ""
    if other and not os.path.realpath(other).startswith(os.path.realpath(root) + os.sep):
        return hookio.ALLOW

    candidate = ""
    spans = hookio.grep_o(NEW_BRANCH_FLAG, cmd)
    tails = hookio.grep_o(LAST_FIELD, hookio._grep_out(spans))
    name = tails[0] if tails else ""
    if name != "":
        candidate = name

    # `git branch [-m|-M] ...`: the new name is the LAST positional, because the rename form is `-m <old> <new>` and the create form is `branch <new> [start]`. Handled separately so a rename INTO a legal name passes while a rename INTO a suffixed one does not -- which is exactly how this session fixed its own.
    if candidate == "":
        cut = hookio.sed_sub(
            hookio.rx(r".*[{S}]branch[{S}]+"),
            "",
            hookio._grep_out(hookio.grep_o(BRANCH_TAIL, cmd)),
            count=1,
        )
        rows, _ = shellscan._records(cut)
        branch_args = shellscan._command_substitution(rows[0] + "\n") if rows else ""
        if not hookio.grep_q(READ_ONLY, branch_args):
            tokens = _tokens(branch_args)
            for tok in tokens:
                if tok.startswith("-"):
                    continue
                candidate = tok
            # `git branch <new> <start-point>`: the START POINT is an existing ref, not a name being created, so only the FIRST positional is judged -- unless this is a rename, where the new name is the SECOND.
            if not hookio.grep_q(RENAME, branch_args):
                for tok in tokens:
                    if tok.startswith("-"):
                        continue
                    candidate = tok
                    break

    if candidate == "":
        return hookio.ALLOW
    # Strip quotes the session happened to use.
    candidate = hookio.sed_sub(r"^['\"]", "", candidate, count=1)
    candidate = hookio.sed_sub(r"['\"]$", "", candidate, count=1)

    # `main` is not a feature branch. `MMDD-N` is the convention.
    if candidate == "main":
        return hookio.ALLOW
    if hookio.grep_q(r"^[0-9]{4}-[0-9]+$", candidate):
        return hookio.ALLOW
    # A SHA or a remote-tracking ref is a START POINT, not a name being created, so it is not this hook's call. NOTE the anchors: an earlier draft skipped any candidate containing a slash, which silently let `checkout -b feature/x` through -- the exact shape this hook exists to refuse. Caught by its own control, which is the argument for writing the controls first.
    if hookio.grep_q(r"^[0-9a-f]{7,40}$|^origin/|^refs/", candidate):
        return hookio.ALLOW

    ev.warn_raw(
        "BLOCKED: '%s' is not a branch name this repo uses.\n"
        "\n"
        "Feature branches are MMDD-N and carry NO suffix. pr-babysit.md and pr-merge.md\n"
        "both say so, and pr-merge's hand-back section warns that invented names\n"
        "leave stray refs for the next session to clean up.\n"
        "\n"
        "A suffix is not cosmetic here. /pr-merge finds a submodule's coordinated PR by\n"
        "matching the console branch name EXACTLY (branch-rebase.md's submodule step does\n"
        "the same),\n"
        "so a suffixed console branch matches no submodule branch and the submodule PR\n"
        "is silently left out of the merge.\n"
        "\n"
        "Pick MAX+1 for today. Compute MAX from PR HEADS, not from live remote branches:\n"
        "a merged PR's branch is DELETED, so `git branch -r` cannot see the name it\n"
        "consumed. That is exactly how 0826-1 got picked twice on 2026-08-26, the second\n"
        "time after PR #576 had already merged it that morning.\n"
        "\n"
        "  d=$(date +%%m%%d)\n"
        "  gh pr list --state all --limit 100 --json headRefName \\\n"
        '    --jq \'.[].headRefName\' | grep "^${d}-" | sed "s/^${d}-//" | sort -n | tail -1\n'
        "\n"
        "Then add one. If you need a throwaway safety ref before a rebase, take the next\n"
        "MMDD-N rather than decorating an existing name -- or use a TAG, which carries no\n"
        "branch convention at all:\n"
        "\n"
        "  git tag prerebase-$(date +%%m%%d) <branch>\n" % candidate
    )
    return hookio.DENY
