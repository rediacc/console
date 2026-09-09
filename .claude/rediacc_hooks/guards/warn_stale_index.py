"""WARN when a commit is about to capture a STALE staged version of a file.

`git commit` commits THE INDEX, not the working tree. Stage a path, edit it
afterwards, and the commit takes the version from `git add` time while the
message you just wrote describes what is on disk. Nothing in git says so: the
commit succeeds, the file list looks right, and the diff is quietly one
revision behind.

THIS COST TWO REAL DEFECTS IN A SINGLE SESSION (2026-08-28):

  1. `git commit -F <file>` after `git add <paths>` swept in two files a PEER
     session had staged, because -F commits the whole INDEX and not the paths
     named on the preceding `git add`. They landed under someone else's
     commit message.
  2. worklist_messages.py was staged, THEN edited (ten DEFAULT placeholders
     reworded), then committed. The commit message claimed the rewording; the
     commit did not contain it. Caught only by grepping the commit afterwards.

WHY WARN AND NOT BLOCK. Staging a deliberately partial version is legitimate
(`git add -p` exists). The failure here is not that it is possible, it is that
it is SILENT -- so the fix is to say it out loud, not to forbid it. A block
would be wrong on a real workflow; a warning is right on every case.

ROUTED THROUGH lib/command-scan.sh so prose quoting `git commit` is not
matched -- a worklist note or a doc mentioning the command is not a commit.

PORT NOTE ON `comm -12 <(sort -u) <(sort -u)`. Two process substitutions and a
set intersection, which Python spells directly. What must survive the
translation is the ORDER and the DEDUPLICATION: `sort -u` under `LC_ALL=C`
(which the harness exports, and which a hook inherits from the session) sorts
by BYTE, not by locale collation, so the result is ordered by the UTF-8
encoding of each path and not by Python's default code-point comparison. The
two agree on ASCII and can disagree on anything else, so the key is spelled
out rather than left to the default.

PORT NOTE ON `grep -c .`. That is a count of records matching the regex `.`,
i.e. NON-EMPTY lines, not a line count. It happens to equal the number of
paths here because `comm` never emits a blank line, but the two are different
questions and the port answers the one the bash asked.
"""

import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/warn-stale-index.sh"
ORDER = 22

# `git commit <pathspec>` and `-a` both take the WORKING TREE for those paths,
# so the staleness this guard is about cannot arise for them. Dropping the test
# makes the advisory fire on the one commit form that is provably NOT at risk,
# which is how a warning stops being read.
DEFECT = ("if hookio.grep_q(WORKING_TREE_FORM, scan):", "if False:")

# COMMAND POSITION, not mere mention. The first draft of this guard matched
# `git commit` after ANY whitespace, so `echo do not run git commit here` warned
# -- prose read as a command. That is the same mention-vs-target defect fixed in
# block-bash-write-to-running-script.sh and block-roundlog-truncate.sh on
# 2026-08-28, reintroduced here within the hour, which is why it is anchored
# rather than remembered. hook_scan_target strips QUOTED spans and extracts
# `sh -c` payloads; unquoted prose survives it, so the anchor is what separates
# a command from a sentence.
COMMIT_AT_COMMAND_POS = hookio.rx(r"(^|[;&|(]|&&|\|\|)[{S}]*git[{S}]+commit")

# `-a` / `--all`: the index is not what gets committed, so there is nothing to
# be stale.
WORKING_TREE_FORM = hookio.rx(r"git +commit[^|;&]*(-a[{S}]|--all\b)")


def _fixture_git(cwd, *args):
    """`git` for the fixture builders, with the ambient config shut out."""
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


def _seeded(path, names):
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    for name in names:
        (path / name).write_text("v1\n", encoding="utf-8")
    _fixture_git(path, "add", "-A")
    _fixture_git(path, "commit", "-qm", "seed")
    return path


def _stale_tree(path):
    """staged {a, b}, unstaged {a, c} -- the intersection is exactly {a}.

    `b` and `c` are not padding: without `b` the intersection would equal the
    staged set and without `c` it would equal the unstaged set, and a port that
    printed either whole set instead of the intersection would still pass.
    """
    _seeded(path, ["a.txt", "b.txt", "c.txt"])
    (path / "a.txt").write_text("v2\n", encoding="utf-8")
    (path / "b.txt").write_text("v2\n", encoding="utf-8")
    _fixture_git(path, "add", "a.txt", "b.txt")
    # THEN edited, which is the whole defect this guard exists for.
    (path / "a.txt").write_text("v3\n", encoding="utf-8")
    (path / "c.txt").write_text("v2\n", encoding="utf-8")
    return path


def _disjoint_tree(path):
    """staged {b}, unstaged {c}: both sets non-empty, no overlap.

    The ALLOW side that a fixture with nothing staged could not provide, since
    that one leaves through the earlier `-n` test and never reaches `comm`.
    """
    _seeded(path, ["a.txt", "b.txt", "c.txt"])
    (path / "b.txt").write_text("v2\n", encoding="utf-8")
    _fixture_git(path, "add", "b.txt")
    (path / "c.txt").write_text("v2\n", encoding="utf-8")
    return path


FIXTURES = {"stale-index": _stale_tree, "disjoint-index": _disjoint_tree}

# BOTH variables, not just GIT_WORK_TREE. This guard's `git diff` calls take no
# `-C` and run in whatever directory the harness invoked it in, so leaving
# GIT_DIR to discovery would diff THIS checkout's index against the fixture's
# work tree -- a comparison of two unrelated trees, and a very large one.
ENVS = [
    (
        "stale",
        {
            "GIT_DIR": "{FIXTURE:stale-index}/.git",
            "GIT_WORK_TREE": "{FIXTURE:stale-index}",
        },
        {},
    ),
    (
        "disjoint",
        {
            "GIT_DIR": "{FIXTURE:disjoint-index}/.git",
            "GIT_WORK_TREE": "{FIXTURE:disjoint-index}",
        },
        {},
    ),
]

EDGE_CASES = [
    ("the plain commit", "git commit -m x"),
    # Defect 1 above, in the form it took.
    ("the -F form the first defect took", "git commit -F /tmp/msg.txt"),
    ("a commit after &&", "git add -A && git commit -m x"),
    # `-a` and `--all` commit the WORKING TREE for those paths.
    ("-a takes the working tree", "git commit -a -m x"),
    ("--all takes the working tree", "git commit --all -m x"),
    # The mention-vs-target anchor, in both directions.
    ("quoted prose is not a command", "echo 'do not run git commit here'"),
    ("a wrapper payload is still a command", "sh -c 'git commit -m x'"),
    ("a different git verb", "git status"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if not hookio.grep_q(COMMIT_AT_COMMAND_POS, scan):
        return hookio.ALLOW

    if hookio.grep_q(WORKING_TREE_FORM, scan):
        return hookio.ALLOW

    # An unreadable probe is never a pass, but this is an ADVISORY: it must never
    # fail a command because git was unavailable. Stay silent instead.
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
    # `printf '%s\n' "$stale" | sed 's/^/      /'`
    for path in stale:
        ev.warn("      %s" % path)
    ev.warn("   If the message describes the edits, re-stage first: git add -- <those paths>")
    ev.warn("   (Verify afterwards against the COMMIT, not the tree: git show <sha>:<path>)")
    return hookio.ALLOW
