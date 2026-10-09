"""Block git restore/checkout/rm of protected hook files.

THE VERB AND THE PATH MUST BE IN THE SAME CLAUSE. The original pattern joined them with `.*`, which spans `&&`, `;` and `|`, so a command that checked out a branch and then merely READ a protected file was refused:

  git checkout main && cat .claude/settings.json

Nothing there restores anything. `[^;&|]*` keeps the match inside one clause, which is the smallest change that tells "restore this file" apart from "restore something, then look at this file".

Verified on 2026-08-27, when this guard blocked the very command that was measuring it -- the probe's line contained the fixture text and never ran. A guard that cannot be measured without tripping over itself is one nobody measures, which is how it sat with a block case and no allow case.

ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant matching PROSE: `echo '<the banned command>'` was refused, and so was a worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a command hidden in a wrapper is scanned exactly as before -- this narrows what the guard
refuses, never what it catches.

PORT NOTE. `PROTECTED` is interpolated into the ERE by the bash, so the two paths keep their backslash-escaped dots here too. Escaping them a second time through `re.escape` would be a change in what is matched, which is the one thing this port may not make.
"""

import itertools
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 3

# Widening the gap back to `.*` is the exact over-block the header records: the verb and the path stop having to share a clause, so `git checkout main && cat .claude/settings.json` is refused for reading a file.
DEFECT = (r")[^;&|]*", r").*")

PROTECTED = r"(\.claude/settings\.json|scripts/pre-commit-check\.sh)"

# COMMAND POSITION ON EVERY ARM. The verb group used to be `(git restore|git checkout|(^|[{S};|&])rm[{S}])`, which anchored only the `rm` arm, and that to any whitespace: `echo the docs say never to run git restore .claude/settings.json in this repo` was refused, and so was `echo never rm .claude/settings.json here` (found by check:ci-guard-mention-anchoring, 2026-10-09).
# Now the whole alternation sits behind one anchor, the line start or a separator, then an optional directory on the program (`/bin/rm`). `git` admits global flags before its verb the way block_worktree_add's GIT_AT_CMD does, so `git -C . restore` and `git  restore` are reached; both were ALLOWED before, because the verb was the literal `git restore`. Prefix commands
# (`sudo`, `xargs`, `time`, an assignment, `if ... then`) reach it through `shellscan.lifted_commands`, and so does `find ... -exec`, a launcher shellscan walks (`shellscan._launched`, #ec63ff8c): every `-exec` lands on a line of its own, so `find . -exec true {} \; -exec rm .claude/settings.json \;`, allowed before, is refused with the single `-exec` spelling.
VERB_AND_PATH = (
    hookio.rx(
        r"(^|[;&|(`{!])[{S}]*([^{S};|&()`]*/)?(git([{S}]+-[A-Za-z-]+([{S}]+[^{S};&|-][^{S};&|]*)?)*[{S}]+(restore|checkout)[{S}]|rm[{S}])[^;&|]*"
    )
    + PROTECTED
)

MESSAGE = "❌ BLOCKED: Cannot delete or restore protected hook files"

EDGE_CASES = [
    ("a restore of the settings file", "git restore .claude/settings.json"),
    ("a checkout of the settings file", "git checkout .claude/settings.json"),
    ("an rm of the pre-commit script", "rm scripts/pre-commit-check.sh"),
    ("rm after a separator", "true; rm .claude/settings.json"),
    # The over-block the clause fix exists for.
    (
        "checking out a branch then READING the file",
        "git checkout main && cat .claude/settings.json",
    ),
    ("reading the file on its own", "cat .claude/settings.json"),
    ("a restore of an unprotected path", "git restore packages/cli/src/x.ts"),
    ("a wrapper payload is still scanned", "sh -c 'git restore .claude/settings.json'"),
    # Command position on every arm: these sentences were refused before 2026-10-09.
    (
        "a sentence naming the restore is not running it",
        "echo the docs say never to run git restore .claude/settings.json in this repo",
    ),
    ("a sentence naming rm is not running it", "echo never rm .claude/settings.json here"),
    ("git global flags before the verb", "git -C . restore .claude/settings.json"),
    ("a prefix command still reaches rm", "sudo rm .claude/settings.json"),
    (
        "find -exec is a launcher shellscan walks",
        r"find . -exec rm .claude/settings.json \;",
    ),
    (
        "every find -exec is walked, not only the first",
        r"find . -name x -exec true {} \; -exec rm .claude/settings.json \;",
    ),
    # The path on the producer side of a pipe into xargs (#ec63ff8c): each was allowed before 2026-10-09.
    ("xargs rm fed the path on stdin", "echo .claude/settings.json | xargs rm"),
    (
        "xargs git restore fed the path on stdin",
        "printf '%s' scripts/pre-commit-check.sh | xargs git restore",
    ),
    ("xargs -I with the path on stdin", "echo .claude/settings.json | xargs -I{} rm -f {}"),
    (
        "an earlier stage of the pipe feeds xargs too",
        "echo .claude/settings.json | sort | xargs git checkout --",
    ),
    # ... and the consumer has to be destructive, and fed by THIS pipe.
    ("piping the path to cat reads it", "echo .claude/settings.json | cat"),
    ("xargs cat reads it", "echo .claude/settings.json | xargs cat"),
    ("xargs rm of an unprotected path", "echo packages/cli/src/x.ts | xargs rm"),
    ("a separator ends the pipe before xargs", "echo .claude/settings.json; ls | xargs rm"),
    ("xargs behind sudo", "echo .claude/settings.json | sudo xargs rm"),
    ("xargs git rm", "git ls-files .claude/settings.json | xargs git rm"),
    ("a tee between the producer and xargs", "echo .claude/settings.json | tee /tmp/l | xargs rm"),
    (
        "git reads its pathspec from stdin",
        "echo .claude/settings.json | git restore --pathspec-from-file=-",
    ),
    ("a heredoc fed to xargs", "cat <<'EOF' | xargs rm\n.claude/settings.json\nEOF"),
    ("inside a wrapper payload", "sh -c 'echo .claude/settings.json | xargs rm'"),
    ("find -exec rm of the path find names", r"find .claude/settings.json -exec rm {} \;"),
    ("xargs echo prints it", "grep -n .claude/settings.json docs/x.md | xargs echo"),
    ("xargs ls lists it", "echo .claude/settings.json | xargs ls -l"),
    ("find -exec cat reads it", r"find .claude/settings.json -exec cat {} \;"),
    (
        "git restore of stdin with no protected path",
        "echo packages/x.ts | git restore --pathspec-from-file=-",
    ),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if cmd == "":
        return hookio.ALLOW

    if hookio.grep_q(VERB_AND_PATH, scan) or fed_by_stdin(cmd):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW


# THE PATH CAN ARRIVE ON STDIN (#ec63ff8c). `echo .claude/settings.json | xargs rm` deletes the file, and no clause of it holds both the verb and the path, so it was allowed (rc 0, 2026-10-09). `shellscan` records, per command, the literal text arriving on its stdin (`_Run.feed`: the earlier pipeline stages' words, its own here-string or heredoc, and `find`'s words for a `find -exec` command) and the prefixes in front of it
# (`_Run.via`). A protected path in that text counts only when the text BECOMES the destructive command's operands: through `xargs`, through `find -exec ... {}`, or through git's `--pathspec-from-file=-`. `echo .claude/settings.json | cat` and `| xargs cat` read the file and stay allowed. What a producer prints is not computed, so `ls .claude | xargs rm` is outside this reach, and a protected path anywhere in a producer's words counts even
# when it is not what reaches the command, the direction a guard fails safe in. The verbs are the ones VERB_AND_PATH names plus `git rm`, which deletes exactly as `rm` does.
DESTRUCTIVE_GIT = ("restore", "checkout", "rm")
OPERAND_FEEDERS = ("xargs", "find")


def _pathspec_from_stdin(argv):
    return "--pathspec-from-file=-" in argv or any(
        a == "--pathspec-from-file" and b == "-" for a, b in itertools.pairwise(argv)
    )


def fed_by_stdin(cmd):
    for run_ in shellscan.every_run(cmd):
        if run_.feed is None or not re.search(PROTECTED, run_.feed):
            continue
        base = run_.name.rsplit("/", 1)[-1]
        git_verb = base == "git" and run_.git_sub in DESTRUCTIVE_GIT
        if not (base == "rm" or git_verb):
            continue
        if any(v in run_.via for v in OPERAND_FEEDERS) or (
            git_verb and _pathspec_from_stdin(run_.argv)
        ):
            return True
    return False
