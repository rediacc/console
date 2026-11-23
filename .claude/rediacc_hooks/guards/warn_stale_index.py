"""WARN when a commit is about to capture a STALE staged version of a file.

`git commit` commits THE INDEX, not the working tree. Stage a path, edit it afterwards, and the commit takes the version from `git add` time while the message you just wrote describes what is on disk. Nothing in git says so: the commit succeeds, the file list looks right, and the diff is quietly one revision behind.

THIS COST TWO REAL DEFECTS IN A SINGLE SESSION (2026-08-28):

  1. `git commit -F <file>` after `git add <paths>` swept in two files a PEER
     session had staged, because -F commits the whole INDEX and not the paths
     named on the preceding `git add`. They landed under someone else's
     commit message.
  2. worklist_messages.py was staged, THEN edited (ten DEFAULT placeholders
     reworded), then committed. The commit message claimed the rewording; the
     commit did not contain it. Caught only by grepping the commit afterwards.

WHY WARN AND NOT BLOCK. Staging a deliberately partial version is legitimate (`git add -p` exists). The failure here is not that it is possible, it is that it is SILENT -- so the fix is to say it out loud, not to forbid it. A block would be wrong on a real workflow; a warning is right on every case.

ROUTED THROUGH lib/command-scan.sh so prose quoting `git commit` is not matched -- a worklist note or a doc mentioning the command is not a commit.

PORT NOTE ON `comm -12 <(sort -u) <(sort -u)`. Two process substitutions and a set intersection, which Python spells directly. What must survive the
translation is the ORDER and the DEDUPLICATION: `sort -u` under `LC_ALL=C`
(which the harness exports, and which a hook inherits from the session) sorts by BYTE, not by locale collation, so the result is ordered by the UTF-8 encoding of each path and not by Python's default code-point comparison. The two agree on ASCII and can disagree on anything else, so the key is spelled out rather than left to the default.

PORT NOTE ON `grep -c .`. That is a count of records matching the regex `.`, i.e. NON-EMPTY lines, not a line count. It happens to equal the number of paths here because `comm` never emits a blank line, but the two are different questions and the port answers the one the bash asked.
"""

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "warn_stale_index",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "_disjoint_tree",
    "_fixture_git",
    "_seeded",
    "_stale_tree",
)

CHAIN = "pre-bash"
ORDER = 21

# `git commit <pathspec>` and `-a` both take the WORKING TREE for those paths, so the staleness this guard is about cannot arise for them. Dropping the test makes the advisory fire on the one commit form that is provably NOT at risk, which is how a warning stops being read.
DEFECT = ("if hookio.grep_q(WORKING_TREE_FORM, scan):", "if False:")

# COMMAND POSITION, not mere mention. The first draft of this guard matched `git commit` after ANY whitespace, so `echo do not run git commit here` warned -- prose read as a command. That is the same mention-vs-target defect fixed in block-bash-write-to-running-script.sh and block-roundlog-truncate.sh on 2026-08-28, reintroduced here within the hour, which is why it is anchored
# rather than remembered. hook_scan_target strips QUOTED spans and extracts `sh -c` payloads; unquoted prose survives it, so the anchor is what separates a command from a sentence.
COMMIT_AT_COMMAND_POS = hookio.rx(r"(^|[;&|(]|&&|\|\|)[{S}]*git[{S}]+commit")

# `-a` / `--all`: the index is not what gets committed, so there is nothing to be stale.
WORKING_TREE_FORM = hookio.rx(r"git +commit[^|;&]*(-a[{S}]|--all\b)")


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if not hookio.grep_q(COMMIT_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    if hookio.grep_q(WORKING_TREE_FORM, scan):
        return hookio.ALLOW

    # An unreadable probe is never a pass, but this is an ADVISORY: it must never fail a command because git was unavailable. Stay silent instead.
    staged = hookio.git_out(["diff", "--cached", "--name-only"], want_rc=True)
    if staged is None:
        return hookio.ALLOW
    unstaged = hookio.git_out(["diff", "--name-only"], want_rc=True)
    if unstaged is None:
        return hookio.ALLOW
    if staged == "" or unstaged == "":
        return hookio.ALLOW

    stale = sorted(
        set(staged.split("\n")) & set(unstaged.split("\n")),
        key=lambda path: path.encode("utf-8", "surrogateescape"),
    )
    if not stale:
        return hookio.ALLOW

    n = len(stale)
    ev.warn(
        "⚠️  STALE INDEX: %d path(s) were staged and then EDITED. This commit takes the "
        "STAGED version, not what is on disk:" % n
    )
    # `printf '%s\n' "$stale" | sed 's/^/ /'`
    for path in stale:
        ev.warn("      %s" % path)
    ev.warn("   If the message describes the edits, re-stage first: git add -- <those paths>")
    ev.warn("   (Verify afterwards against the COMMIT, not the tree: git show <sha>:<path>)")
    return hookio.ALLOW
