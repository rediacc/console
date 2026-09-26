"""Block a `git commit` that names no pathspec, because it commits the INDEX.

WHY, and it is not the reason people expect. `git add -- <exact paths>` is correct and is NOT enough: a bare `git commit` afterwards writes whatever the index holds. The staging decision is scoped by intent and unscoped in execution.

AND IT WAS NOT A PEER SESSION, which is the part worth getting right. Both instances below were the authoring session's OWN SUB-AGENTS, which run as separate processes against the SAME index. So a single session with no peer at all is still exposed. The first instance was not even a `git add`: `git mv` stages by definition, measured, with nothing else run --

    $ git mv a.txt b.txt
    $ git diff --cached --name-status
    R100    a.txt   b.txt

The MOVE agent was told to move each policy list with `git mv`; it did exactly that; fifteen renames were sitting in the shared index before the driver typed anything. (A concurrent session would do the same, and on 2026-09-06 there really was a second one in this checkout, so that case is not hypothetical either. It just is not what happened.)

Found live, twice in one session, 2026-09-06:
  - `git add -- <six named paths>` then `git commit` also landed fifteen
    `git mv` renames a SUB-AGENT of that session had staged, moving every
    policy list into `.ci/policy/` WITHOUT any of their readers. HEAD then had
    the files at their new paths while scripts/lib/policy-paths.ts still read
    `const POLICY_DIR = '';` -- the exact half-landed state that seam exists to
    refuse, reached from outside it.
  - One hour later, and after the author had written the TRAPS.md entry about
    it: `git add -- <three directories>` then `git commit` swept three other
    agents' in-flight ports, landing 108 files where 33 were intended and
    committing one ledger mid-record.

WHY A HOOK. See block_blanket_git_add.py's own header: this repo's record is that a written rule protects only the session that reads it and remembers it at the right second. The second instance above happened AFTER the rule was written down, by the session that wrote it.

`-a` IS BLOCKED TOO, for the same reason and more directly: it stages every modified tracked file in a tree that routinely holds three other sessions' work.

THE ESCAPE IS IN THE MESSAGE, deliberately:

    git commit -F <message-file> -- <path> <path> ...

Options come BEFORE the `--`, or git reads `-F` as a pathspec and refuses with "pathspec '-F' did not match any file(s)", which is a confusing way to learn the argument order.

NOT BLOCKED: `--amend` (it rewrites a commit whose content is already chosen), and any commit that already carries a `--` pathspec.

PORT NOTE ON THE PAYLOAD DEADLINE, which has no counterpart here. The twin opens with `hook_read_payload`, a bounded read that REFUSES on its deadline because "a guard which cannot read the command cannot clear it either". A ported guard never reads stdin: `dispatch.py` reads the whole payload once for the chain and hands each module an `Event`. The branch is therefore
unreachable rather than dropped, and the differential drives both sides with the payload already on a closed stdin, where the twin's own deadline never fires.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
# Re-keyed from 43 to 44 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.
ORDER = 43

# The escape this guard advertises is the one line worth planting on: a `--` that requires a real pathspec after it is what separates the documented form from the bare one wearing its clothes.
DEFECT = (r'r"(^|[{S}])--[{S}]+[^{S};&|<>]"', r'r"(^|[{S}])--"')

# Command position: line start, or after ; & | ( $( or a backtick.
GIT_COMMIT = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+commit([{S}]|$)"
)

# THROWAWAY FIXTURE REPOS ARE EXEMPT, and this was a defect in the guard's first hour rather than a concession. The shadow-differential recipe every port agent follows REQUIRES `git init` plus a sealing commit inside a disposable repo under the session scratchpad, because a ledger row records `HEAD^{tree}` and a dirty tree is refused. Blocking that would have stopped the wave
# this guard was written during. Measured: the guard refused `git init ... && git commit -qm seed` in a scratch directory five minutes after it landed.
#
# THE MARKERS ARE STRUCTURAL, not a name allowlist: a command that creates a repository, or that reaches into one under /tmp, is not committing to this checkout. The real checkout is never under /tmp.
#
# THE LIMIT, stated rather than hidden: a `cd` into /tmp followed by a `cd` back would slip through. This guard defends against the accident it was written for, which is a correctly-scoped `git add` followed by an unscoped commit in the working checkout; it is not an adversarial control, and pretending otherwise would be the "check that cannot fail" this repo keeps a trap file
# about.
GIT_INIT = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git[{S}]+init([{S}]|$)")
CD_TMP = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*cd[{S}]+[\"']?/tmp/")
GIT_C_TMP = hookio.rx(r"git[{S}]+-C[{S}]+[\"']?/tmp/")

# An amend is choosing nothing new, so it is not this guard's business.
AMEND = hookio.rx(r"(^|[{S}])--amend([{S}]|$)")

# A `--` with a real pathspec after it is the shape this guard is asking for. `git commit --` with nothing after it is the bare form wearing the escape's clothes, exactly as in block_blanket_git_add.py.
DDASH_PATHSPEC = hookio.rx(r"(^|[{S}])--[{S}]+[^{S};&|<>]")

MESSAGE = (
    "❌ BLOCKED: `git commit` with no pathspec commits the INDEX, not the paths you just "
    "added. This checkout is shared, and your own SUB-AGENTS share the index too: `git mv` "
    "stages by definition, so their renames ride your commit with no `git add` anywhere. "
    "That has happened twice, and the second time was an hour after the trap was written "
    "down -- fifteen policy renames landed without their readers, then 108 files landed "
    "where 33 were intended. NAME WHAT YOU ARE COMMITTING: `git commit -F <message-file> -- "
    "<path> <path>`. Options go BEFORE the `--`, or git reads `-F` as a pathspec. `--amend` "
    "is not blocked. `-a` is: it stages every modified tracked file in a tree that holds "
    "other sessions' work."
)

EDGE_CASES = [
    ("the bare form", "git commit"),
    ("a message with no pathspec", 'git commit -m "x"'),
    ("-a stages every modified tracked file", 'git commit -a -m "x"'),
    ("a trailing -- with nothing after it", 'git commit -m "x" --'),
    ("the advertised escape", "git commit -F msg.txt -- a/b.ts"),
    ("several named paths", "git commit -q -F - -- .ci/x.sh agent/y.md"),
    ("an amend chooses no new content", "git commit --amend --no-edit"),
    ("a git add is another guard's business", "git add -- a.ts"),
    ("the sealing commit of a throwaway fixture repo", "git init -q && git commit -qm seed"),
    ("a commit inside /tmp is never this checkout", "cd /tmp/fx/r1; git commit -qm seed"),
    ("git -C into a scratch repo", "git -C /tmp/fx/r1 commit -qm seed"),
    # A /tmp MESSAGE FILE is not a /tmp repo, so this one is still refused.
    ("a message file under /tmp is not a scratch repo", "git commit -F /tmp/msg.txt"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if not hookio.grep_q(GIT_COMMIT, scan):
        return hookio.ALLOW

    for exempt in (GIT_INIT, CD_TMP, GIT_C_TMP, AMEND, DDASH_PATHSPEC):
        if hookio.grep_q(exempt, scan):
            return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
