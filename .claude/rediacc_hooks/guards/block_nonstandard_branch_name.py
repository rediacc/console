"""A feature branch is `MMDD-N`. No suffixes, no words, no decoration.

WHY. `.claude/commands/pr-babysit.md` and `.claude/commands/pr-merge.md` both state the convention, and pr-merge's hand-back section warns that guessing a name produces stray refs the next `/pr-babysit` has to clean up. On 2026-08-26 a session created `0826-1-prerebase` in the console AND in a submodule, as safety copies before a rebase. Reasonable intent, wrong shape: the suffix
makes the ref sort next to a wave branch while belonging to no wave, and nothing downstream -- not pr-babysit's branch listing, not the submodule same-name matching in branch-rebase.md's submodule step, not pr-merge's coordinated-PR lookup -- can tell the two apart.

THE SUBMODULE POINT IS THE SHARP ONE. `/pr-merge` finds a submodule's PRs by matching the console branch name EXACTLY. A console branch carrying a suffix silently matches nothing, so a coordinated submodule PR is invisible to the merge path and gets left behind.

ONLY CREATION IS CHECKED. `git branch -d`, `-r`, `--list`, `--show-current` and `--contains` read; they are none of this hook's business. Blocking a read would be the over-matching that gets a guard switched off.

CITED BY HEADING, NOT LINE. Three of this file's original `:NNN` references rotted inside the same session that wrote them, because the files they point at were edited in the same working tree. block-blanket-git-add.sh adopted the heading convention for exactly this reason.

`main` is allowed because it is not a feature branch. Nothing else is special cased: if a name is neither `main` nor `MMDD-N`, the convention does not describe it, and the operator is the one who decides to widen the convention.

ONE PARSER FOR THE WHOLE ONE-BRANCH FAMILY (the commit-policy plan, F1 and T2). Until 2026-09-25 this guard found branch names with quote-blind regexes over the raw command, stripping heredoc bodies but deliberately not quoted strings. It refused a read-only `grep -n -e "checkout -b" -e "git branch [a-z0-9]"` live, reading the quoted PATTERN as a branch being created. It now asks `commit_policy.branch_creations`, which walks what bash would run through the shared lexer (`shellscan._analyse`), so a quoted pattern is an argument of `grep`, a heredoc body is data, a variable assignment runs nothing, and a `sh -c '...'` payload is still walked. `block_second_branch` reads the same parser, so the two guards agree by construction about what counts as creating a branch.

THE START-POINT CARVE-OUT IS GONE WITH THE REGEXES. The old reader could land on the start point of `checkout -b <name> <start>` and so skipped a SHA, `origin/...` or `refs/...` candidate. The parser takes the name from the flag's own value, so `checkout -b origin/x` is now judged as the branch `origin/x` it creates, which is not `MMDD-N`.
"""

import re

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
ORDER = 16

# The shape check itself. With it gone every name passes, which is the whole convention this guard exists for.
DEFECT = ('if name == "main" or SHAPE.match(name):', "if True:")

# `feature/x`, `0826-1-prerebase`: anything that is neither `main` nor this.
SHAPE = re.compile(r"^[0-9]{4}-[0-9]+$")

# The creation kinds this guard judges the NAME of. A push, a `gh pr create --head` and a `git/refs` POST name a REMOTE branch; whether that may exist at all is `block_second_branch`'s question, and it refuses every such name that is not the one live branch.
JUDGED = frozenset(("checkout-b", "switch-c", "branch", "rename", "copy"))

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
    # F1, refused live on 2026-09-25: a quoted grep PATTERN is not a branch being created.
    (
        "F1: a grep for the verbs runs grep",
        'grep -n -e "checkout -b" -e "git branch [a-z0-9]" x.py',
    ),
    ("a wrapper payload is still walked", "sh -c 'git checkout -b feature/x'"),
    ("a remote-looking name is a name being created", "git checkout -b origin/x"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW

    # ANOTHER PROJECT'S BRANCHES ARE NOT THIS REPO'S CONVENTION. Found 2026-09-24 restoring four branches in /home/developer/rovaip (a different project) with `git -C /home/developer/rovaip branch chore/... <sha>`: the MMDD-N rule refused them. Exempt only a target that resolves to a repository OUTSIDE this checkout; submodules under private/ are separate git roots but keep the rule, because /pr-merge matches their coordinated branch names exactly. A directory that resolves to no repository at all is judged as this one, the direction the old line-wide hint failed in too.
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    candidate = ""
    for creation in commit_policy.branch_creations(cmd, root, base):
        if creation.kind not in JUDGED:
            continue
        if creation.repo_root and not commit_policy.is_inside(creation.repo_root, root):
            continue
        # Strip quotes a wrapper payload happened to leave on the word.
        name = creation.name.strip("'\"")
        # `main` is not a feature branch. `MMDD-N` is the convention.
        if name == "main" or SHAPE.match(name):
            continue
        candidate = name
        break

    if candidate == "":
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
