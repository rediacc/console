"""Block git restore/checkout/rm of protected hook files.

THE VERB AND THE PATH MUST BE IN THE SAME CLAUSE. The original pattern joined them with `.*`, which spans `&&`, `;` and `|`, so a command that checked out a branch and then merely READ a protected file was refused:

  git checkout main && cat .claude/settings.json

Nothing there restores anything. `[^;&|]*` keeps the match inside one clause, which is the smallest change that tells "restore this file" apart from "restore something, then look at this file".

Verified on 2026-08-27, when this guard blocked the very command that was measuring it -- the probe's line contained the fixture text and never ran. A guard that cannot be measured without tripping over itself is one nobody measures, which is how it sat with a block case and no allow case.

ROUTED THROUGH lib/command-scan.sh 2026-08-27. Matching the raw command meant matching PROSE: `echo '<the banned command>'` was refused, and so was a worklist note or a doc quoting it. hook_scan_target removes heredoc bodies and quoted spans while still extracting `sh -c` / `eval` payloads, so a command hidden in a wrapper is scanned exactly as before -- this narrows what the guard
refuses, never what it catches.

PORT NOTE. `PROTECTED` is interpolated into the ERE by the bash, so the two paths keep their backslash-escaped dots here too. Escaping them a second time through `re.escape` would be a change in what is matched, which is the one thing this port may not make.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-protected-files.sh"
ORDER = 3

# Widening the gap back to `.*` is the exact over-block the header records: the verb and the path stop having to share a clause, so `git checkout main && cat .claude/settings.json` is refused for reading a file.
DEFECT = (r")[^;&|]*", r").*")

PROTECTED = r"(\.claude/settings\.json|scripts/pre-commit-check\.sh)"

VERB_AND_PATH = hookio.rx(r"(git restore|git checkout|(^|[{S};|&])rm[{S}])[^;&|]*") + PROTECTED

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
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if cmd == "":
        return hookio.ALLOW

    if hookio.grep_q(VERB_AND_PATH, scan):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
