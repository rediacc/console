"""Block a BLANKET `git add` -- `-A`/`--all` with no pathspec, a lone `.`, or `:/`.

WHY. This checkout is routinely shared by several live sessions, so "stage everything" does not mean "stage this session's work", it means "stage whatever every other session happens to have uncommitted right now". The tree is the shared surface; the index is not a private scratchpad.

Found live, twice, and the second one is why this exists as a HOOK rather than a paragraph:
  - docs/agent-reference/TRAPS.md, "A blanket `git add -A` sweep imports
    other sessions' half-landed work" (cited by heading, not line: the two
    trap corpora were merged into that one file and every line moved):
    sweep cefa43ca7 sucked in another session's
    check-solution-video-engine.ts, which then failed 273 of 273 on branch
    0730-2 (run 30554973713, job 90913300683). The sweep looked clean; the
    failure surfaced a full CI round later, on someone else's code.
  - 2026-08-09: a peer's private/renet submodule pointer and three of its
    deliberately-uncommitted gate scripts sat in the tree all afternoon
    while an unrelated PR was being built around them. A single `git add -A`
    would have shipped a submodule bump into a PR that never reviewed it.

WHY A HOOK AND NOT A RULE. CLAUDE.md session default 1 and the memory feedback_shared_checkout_hygiene have both said "never blanket-add in a shared tree" for months. The repo's own record is that written rules do not hold: the 2026-08-04 wave logged nine instances of one documented trap, three authored by the person who had just written the entry about it. A rule protects only the
session that reads it and remembers it at the right second.

THE ESCAPE IS IN THE MESSAGE, deliberately. A session that genuinely wants everything under one directory says so with a pathspec:
    git add -A -- packages/cli/src
That is one edit away, it is reviewable, and it cannot reach a path its author did not name. Blocking without naming the escape is how a guard becomes something sessions route around instead of using.

NO CROSS-TALK with block-worktree-add.sh: `git worktree add x` has `worktree` between `git` and `add`, so the pattern below cannot see it. Pinned by a case in test-hooks.sh, because two guards matching adjacent shapes is exactly where a regex change silently swallows the wrong one.
"""

import pathlib

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 29

# The PR #566 finding, undone: with `>` and a redirection out of the terminator set, `git add -A > /dev/null` and `git add -A 2>&1` stage the whole tree and walk straight past this guard, which is what they did before review caught it.
DEFECT = (r"($|[;&|<>]|[0-9]*>)", r"($|[;&|])")

# Command position: line start, or after ; & | ( $( or a backtick. Flags
# between `git` and `add` (-C <path>, -c k=v) stay matched, since they change
# where the command runs, not what it stages.
GIT_ADD = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+add[{S}]+"
)

# What counts as "nothing followed it". End of line, another command, OR a REDIRECTION: `git add -A > /dev/null` and `git add -A 2>&1` stage the entire tree exactly like the bare form, and an earlier version of this guard let both through because `>` was not in the terminator set. Caught in review of PR #566 and confirmed by running the guard: all three shapes exited 0.
END = hookio.rx(r"[{S}]*($|[;&|<>]|[0-9]*>)")

# A trailing `--` with NO pathspec after it is also blanket. git treats `git add -A --` as no restriction at all, so the escape this guard advertises (name a pathspec) must actually contain one; an empty pathspec list is the bare form wearing the escape's clothes.
BARE_DDASH = hookio.rx(r"([{S}]+--[{S}]*)?")

BLANKET_ALL = GIT_ADD + r"(-A|--all)" + BARE_DDASH + END
BLANKET_DOT = GIT_ADD + r"\." + BARE_DDASH + END
BLANKET_ROOT = GIT_ADD + r":/" + BARE_DDASH + END

MESSAGE = (
    "❌ BLOCKED: blanket `git add` stages every other live session's uncommitted work, not "
    "just yours. This checkout is shared, and a sweep has already shipped a peer's "
    "half-finished file into an unrelated PR once (it failed 273 of 273 a full CI round "
    "later, on code the author had never seen). NAME THE PATHSPEC instead -- `git add -A -- "
    "<dir>` and `git add <file>...` both pass this guard, are reviewable, and cannot reach a "
    "path you did not name. If you truly want the whole tree and know what is in it, say so "
    "explicitly with `git add -A -- .` and own that choice."
)

EDGE_CASES = [
    ("the bare all form", "git add -A"),
    ("the long spelling", "git add --all"),
    ("a lone dot", "git add ."),
    ("the repo-root pathspec", "git add :/"),
    # The PR #566 finding: a redirection is not a pathspec.
    ("a redirection does not restrict anything", "git add -A > /dev/null"),
    ("a stderr redirection is the same", "git add -A 2>&1"),
    # ...and the escape, which must keep working with a redirection on it.
    ("a real pathspec with a redirection", "git add -A -- . > /dev/null"),
    ("a trailing -- with no pathspec is still blanket", "git add -A --"),
    ("the advertised escape", "git add -A -- packages/cli/src"),
    ("a named file", "git add packages/cli/src/foo.ts"),
    # The cross-talk control.
    ("worktree add is another guard's business", "git worktree add /tmp/wt main"),
    # SCOPE, added 2026-09-09. A scratch repo under a session's own scratchpad is not this shared checkout and firing there only teaches sessions to route around the guard. A SUBMODULE is not that case: different toplevel, same shared tree.
    ("a foreign scratch repo is not this checkout", "git -C /tmp/scratch/plantree add -A"),
    ("a submodule IS this checkout and stays guarded", "git -C private/account add -A"),
    # RULE T (PLAN-retire-bash-oracles A4, A0 L9): the copied anchor missed a reserved word or a leading redirect.
    ("L9 then runs the next word", "if true; then git add -A; fi"),
    ("L9 a leading redirect", ">/dev/null git add -A"),
    ("control: command -v only prints", "command -v git add -A"),
]


def _is_inside(target, root):
    """Is `target` the project tree or a path beneath it?

    Compared as resolved paths and not as strings, so `/home/x/console-2` is not read as living inside `/home/x/console`. Unresolvable answers True -- keep guarding.
    """
    try:
        t = pathlib.Path(target).resolve()
        r = pathlib.Path(root).resolve()
    except OSError:
        return True
    return t == r or r in t.parents


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # THIS GUARD'S ARGUMENT IS ABOUT *THIS* CHECKOUT -- that it is shared, and that a sweep here reaches another live session's uncommitted work. Neither is true of a throwaway repo a session builds under its own scratchpad, and firing there spends the guard's credibility on a command that could not harm anything: measured 2026-09-09, a writer was refused in a scratch repo by a
    # message naming twelve files in a checkout it could not reach, and worked around the guard rather than being protected by it.
    #
    # `target_root` AND NOT THE EVENT'S CWD, which was the first fix and was wrong. This harness RESETS the shell's directory after every call, so `ev.cwd` is the project directory on every invocation and a cwd test can never fire. The directory that matters is the one spelled in the COMMAND -- `git -C <dir>` or a leading `cd <dir> &&` -- which is exactly what `target_root`
    # extracts. Its own comment records this same defect being found twice before, in block-untagged-commit and block-unverified-push.
    #
    # OUTSIDE THE PROJECT TREE, not merely a different toplevel. A SUBMODULE is a different toplevel and is emphatically not foreign: private/account is shared, frozen, and full of other people's work, and a `git -C private/account add -A` is the exact sweep this guard exists to refuse. Standing down on "different toplevel" alone allowed it -- caught by asking, before shipping,
    # which repos the new predicate had just stopped protecting.
    #
    # Empty target means "this root, or unresolvable", so the guard keeps guarding by default; a resolvable target under the project directory keeps guarding too.
    _target = shellscan.target_root(scan, shellscan.repo_root_env(), verb="add")
    if _target != "" and not _is_inside(_target, shellscan.repo_root_env()):
        return hookio.ALLOW

    for pat in (BLANKET_ALL, BLANKET_DOT, BLANKET_ROOT):
        if hookio.grep_q(pat, scan):
            ev.warn(MESSAGE)
            return hookio.DENY
    return hookio.ALLOW
