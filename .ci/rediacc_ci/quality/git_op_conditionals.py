"""A git-identity capture that reaches a conditional must be guarded first.

Ported from `.ci/scripts/quality/check-git-op-conditionals.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live side by side
until a committed differential ledger says otherwise.

WHY THE TWIN EXISTS, carried over from its header because the archaeology is the
half of a gate that cannot be recovered from the code:

  A git-identity assignment used later without checking whether it failed OR
  resolved to a KNOWN MISLEADING VALUE is a defect gates run git and observe
  success but never inspect what a CONDITIONAL later does with that output.

  Measured 2026-08-28: .claude/hooks/post-bash/cancel-old-ci.sh and
  .claude/hooks/post-bash/refresh-pr-body.sh both captured
  `git rev-parse --abbrev-ref HEAD` and guarded only `-z "$BRANCH"` and
  `"$BRANCH" == "main"`. `rev-parse --abbrev-ref HEAD` does not fail on a
  detached checkout the way `symbolic-ref` does; it returns the LITERAL STRING
  "HEAD" (documented at .claude/hooks/stop/wl_core.py:466, which chose
  symbolic-ref for exactly this reason). Neither guard catches that value, so
  both hooks fell through and treated "HEAD" as a real branch name -- harmless
  today only because no git branch can ever actually be named "HEAD", which is
  luck holding the door shut, not a check. check-swallowed-failures.sh does not
  cover this: it scans only .ci/scripts/{quality,security,lib}, never
  .claude/hooks where this defect lived, and its shape requires an explicit
  `2>/dev/null ... || true`-style discard, not a captured value that is simply
  never validated against the specific misleading strings git can return.

  WHAT IT FLAGS. A line assigning the output of a git command that resolves an
  IDENTITY (branch, ref, sha) to a shell variable -- or a BARE such command
  whose output becomes a function's de facto return value via stdout -- in a
  file under .claude/hooks/ or .ci/scripts/quality/, where the file does not
  ALSO -- anywhere -- guard that value before it reaches a conditional or
  comparison. .ci/scripts/quality specifically: check-submodule-branches.sh
  lived there with the second real defect and had no check:* key running it at
  all (defined-but-never-run, invoked only by a direct `run:` line in
  ci-quality.yml, outside the package.json/manifest.ts convention every other
  gate uses) -- fixed alongside this gate.

  NOT the whole .ci/scripts tree: widening past quality/ into ci/, autopilot/,
  release/ etc. surfaced false positives this gate cannot yet resolve --
  `|| { ... exit 0; }` block-style handlers and `||` continued onto the next
  physical line both clear a real guard that a single-line-oriented scanner
  cannot see. Precision over recall: a gate that flags safe code gets
  suppressed, which is the exact failure check-swallowed-failures.sh's own
  header names. Widening further needs a smarter guard search, not more scope.

  "Guard" means any of:
    * the assignment itself ends in a failure handler: `|| exit`, `|| return`,
      `|| continue`, `|| true`, `|| :`
    * a later `-z "$VAR"` or `-n "$VAR"` test (empty-checked before use)
    * for the specific `rev-parse --abbrev-ref HEAD` shape, an explicit
      `"$VAR" == "HEAD"` (or `= "HEAD"`) comparison, since empty-checking alone
      does not catch that command's detached-HEAD sentinel

  WHAT IT DELIBERATELY DOES NOT FLAG. `symbolic-ref` and `branch
  --show-current` calls: both fail closed to EMPTY on a detached HEAD (no
  misleading literal), so an adjacent `-z` check is the only guard either one
  needs, and that is already required above. A command whose captured value is
  never compared or branched on (used only for printing) is not this gate's
  business either -- scope stays "feeds a conditional", not "every git capture
  in the tree".

The twin's gate header carries a BLOCKER about WIRING rather than about git, so
it stays with the bash file: the step "runs before this lane's `- id: setup`
step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting
it into the region would move it below that guard and skip it whenever setup
fails." A port inherits no registration, so nothing here re-states that as a live
suppression.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SELF-EXEMPTION IS THE SUBTLE PART OF THIS PORT. The twin exempts its own
file with `SELF_REL="${BASH_SOURCE[0]#"$ROOT"/}"`, because its header quotes the
risky shapes verbatim as examples and its controls plant them in heredocs, and
both match the extraction regex. That is the "gate about a rule accidentally
judged by that same rule" trap, the same one check-toolchain-pins.sh documents
for itself.

A PORT CANNOT INHERIT THAT LINE, because `__file__` here is
`.ci/rediacc_ci/quality/git_op_conditionals.py`, which is not in the scan set at
all -- the globs cover `.sh` under `.claude/hooks/` and `.ci/scripts/quality/`.
The file that still needs exempting is the BASH TWIN, which is in the scan set
and does still contain the fixtures. So the exemption is written out BY NAME in
`EXEMPT_PATHS` below, with the reason, and the gate PRINTS it on every run. A
quiet exemption is how a gate stops meaning what its name says; this one cannot
be forgotten because it is in the output.

WHEN THE TWIN IS FINALLY DELETED, `EXEMPT_PATHS` must be emptied in the same
change. Left behind it would silently excuse a file that no longer exists, which
costs nothing today and is exactly the kind of stale allowlist entry that
survives for years.

THE GLOB SPELLINGS ARE ASYMMETRIC ON PURPOSE, and the twin pays six lines for
it: `.claude/hooks/**/*.sh` and `.ci/scripts/quality/*.sh`. Git's default
(non-`:(glob)`) pathspec uses wildmatch WITHOUT pathname mode, so `*` crosses
`/` -- which means `**/*.sh` still demands a literal slash between the prefix
and the filename, and `.ci/scripts/quality/` is FLAT. The `**` spelling matched
ZERO files there while the gate reported "71 shell file(s) scanned", and it was
caught only because a mutation-proof on the real defect the widening existed to
catch still passed clean. `.claude/hooks` DOES have subdirectories, so `**/*.sh`
was already correct there.

THE PORT DOES NOT REIMPLEMENT WILDMATCH. It hands the same two pathspecs to the
same `git ls-files`, twice each (tracked, then `--others --exclude-standard`),
exactly as the twin does. Reimplementing git's matcher in Python would be a
second matcher to keep in step with the first, and the whole finding above is
what happens when a matcher's behaviour is assumed rather than measured.

UNTRACKED FILES ARE IN SCOPE HERE, unlike check-go-tool-path.sh. That is
deliberate in the twin (`--others --exclude-standard` is spelled out) and it is
right for this subject: a hook added but not yet committed is running on the
developer's machine already.

`grep -o` CAN EMIT SEVERAL MATCHES FROM ONE LINE, all carrying that line's
number, and the loop then re-reads the FULL line with `sed -n "${lineno}p"`. So
two captures on one physical line are judged against the same guard text, and a
`|| exit 0` at the end of the line clears BOTH. Preserved. The twin's own
comment explains why the full line is re-read rather than using the matched
text: `grep -oE` truncates at the closing paren of `$(...)`, which silently
dropped a trailing `|| exit 0` on the very shape this gate exists to require and
produced three false positives before it was caught.

NO FILE-WIDE EXEMPTION FOR THE BARE SHAPE, and this is a measured decision
rather than an oversight. The twin's comment: "does a HEAD-literal comparison
appear ANYWHERE in the file" was tried and PROVEN WRONG by the real defect it
was meant to catch -- check-submodule-branches.sh has an unrelated
`"$sm_branch" == "HEAD"` check on a DIFFERENT variable elsewhere in the file,
which cleared the finding even with the real unguarded shape reintroduced
verbatim. A mutation-proof caught this gate lying about its own coverage before
it shipped. So the bare shape is banned outright.

THE GUARD SEARCHES ARE FILE-WIDE AND TEXTUAL, which over-clears on purpose. A
`-z "$BRANCH"` anywhere in the file clears every `BRANCH=$(git ...)` in it, even
one on a path the check never runs on, and a `"$BRANCH" == "HEAD"` inside a
comment or a heredoc counts. For a gate whose false POSITIVE gets it suppressed,
over-clearing is the right direction to err, and it is stated rather than
discovered.

`[[:space:]]` IS NOT `\\s`; see `rediacc_ci.quality.npmrc` for the same note. The
class is written out.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# POSIX [[:space:]], written out. grep works line by line, so the `\n` member
# can never participate in a match; it is present so the class is the same set.
SPACE = r"[ \t\n\v\f\r]"

# The two pathspecs, handed to git unchanged. See the port notes on why the two
# spellings differ and why neither is a typo.
SCAN_GLOBS = (".claude/hooks/**/*.sh", ".ci/scripts/quality/*.sh")

# THE ONE EXEMPTION, BY NAME AND WITH ITS REASON, PRINTED EVERY RUN.
#
# The bash twin quotes the risky shapes verbatim in its header and plants them
# in heredoc control fixtures, so it matches its own extraction regex. The twin
# exempts itself with `${BASH_SOURCE[0]#"$ROOT"/}`; a Python port has no such
# line to inherit, so the path is written out. DELETE THIS ENTRY IN THE SAME
# CHANGE THAT DELETES THE TWIN.
EXEMPT_PATHS = {
    ".ci/scripts/quality/check-git-op-conditionals.sh": (
        "the bash twin of this gate: its header quotes the risky shapes as examples "
        "and its controls plant them in heredocs"
    ),
}

# Every `VAR=$(git ... rev-parse|symbolic-ref|branch ...)` capture. `git` and its
# subcommand are NOT required to be adjacent: `git -C "$dir" rev-parse ...` is
# the ACTUAL shape of the real defect, and an adjacency-requiring pattern missed
# it silently on the real tree while the synthetic control fixture, written
# without `-C`, still passed -- a gate proving its own harness works and nothing
# about the tree it was supposed to be reading.
_CAPTURE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*=\$\(git\b[^)]*\b(?:rev-parse|symbolic-ref|branch)\b[^)]*\)"
)

# The variable name out of a matched capture. `sed -nE 's/^(...)=\$\(.*/\1/p'`.
_VARNAME = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=\$\(")

# Guard 0: the assignment is itself the CONDITION of an if/elif/while, whose
# failure branch IS the guard (`elif ! head_sha=$(...); then`).
_GUARD_CONDITION = r"^%s*(if|elif|while)%s+!?%s*%s="

# Guard 1: the assignment line itself ends in a failure handler.
_GUARD_HANDLER = re.compile(r"\|\|%s*(exit|return|continue|true|:)(%s|$)" % (SPACE, SPACE))

# The special case. `rev-parse --abbrev-ref HEAD` does not fail on a detached
# checkout; it prints the literal string "HEAD".
_ABBREV_REF = re.compile(r"rev-parse%s+--abbrev-ref%s+HEAD" % (SPACE, SPACE))

# SECOND SHAPE: a BARE statement, not an assignment at all --
# `git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"` as a function's
# last line, its stdout becoming the function's de facto return value at the
# CALL SITE (`current_branch="$(get_current_branch)"`). The `|| echo <fallback>`
# reads as a guard but is not one: it fires only when git itself FAILS, and this
# command SUCCEEDS on a detached checkout, printing "HEAD" straight past it.
# Found 2026-08-28 in check-submodule-branches.sh's get_current_branch() and
# get_submodule_branch(), where two independently-detached checkouts (the
# superproject and a submodule) would both return "HEAD" and compare EQUAL,
# reporting a branch match that was not real.
_BARE = re.compile(
    r"git\b[^|;&]*\brev-parse\b[^|;&]*--abbrev-ref[^|;&]*\bHEAD\b[^|;&]*\|\|%s*echo\b" % SPACE
)


def head_literal_guard(varname: str) -> re.Pattern[str]:
    """`"$VAR" == "HEAD"` or `"$VAR" = "HEAD"`, anywhere in the file."""
    return re.compile(r'"\$%s"%s*(==|=)%s*"HEAD"' % (re.escape(varname), SPACE, SPACE))


def empty_check_guard(varname: str) -> re.Pattern[str]:
    """`-z "$VAR"` or `-n "$VAR"`, anywhere in the file.

    Sufficient for `symbolic-ref` and `branch --show-current`, both of which fail
    closed to EMPTY on a detached checkout with no misleading literal to also
    guard against.
    """
    return re.compile(r'(-z|-n)%s+"\$%s"' % (SPACE, re.escape(varname)))


def scan_text(body: str, label: str) -> list[str]:
    """The twin's `scan_file`, as `<label>:<varname>` findings. Empty means clean.

    Takes TEXT rather than a path so a test can drive it on a string, which is
    the whole reason the ports expose their helpers. `label` is what the twin
    prints, `${f#"$ROOT"/}` -- the repo-relative path.
    """
    findings: list[str] = []
    lines = body.split("\n")

    for line in lines:
        for match in _CAPTURE.finditer(line):
            name = _VARNAME.match(match.group(0))
            if name is None:
                continue
            varname = name.group(1)
            # THE FULL SOURCE LINE, not the matched text. `sed -n "${lineno}p"`
            # in the twin; see the port notes for the three false positives the
            # truncated form produced.
            if re.search(_GUARD_CONDITION % (SPACE, SPACE, SPACE, re.escape(varname)), line):
                continue
            if _GUARD_HANDLER.search(line):
                continue
            if _ABBREV_REF.search(line):
                # Checked BEFORE the general empty-check guard: emptiness alone
                # does not catch the detached-HEAD sentinel this command returns.
                if head_literal_guard(varname).search(body):
                    continue
                findings.append("%s:%s" % (label, varname))
                continue
            if empty_check_guard(varname).search(body):
                continue
            findings.append("%s:%s" % (label, varname))

    for index, line in enumerate(lines, start=1):
        findings.extend("%s:bare-statement-line-%d" % (label, index) for _ in _BARE.finditer(line))

    return findings


def scan_file(path: pathlib.Path, label: str) -> list[str]:
    """`scan_text` over a file. An unreadable file is not a finding.

    The twin's `cat "$f" 2>/dev/null || return 0` swallows a read error, and a
    port that turned it into an error would report findings the twin never
    reports -- on this repo's own tree, where a path in the index but deleted
    from disk is an ordinary state.
    """
    try:
        return scan_text(path.read_text(encoding="utf-8", errors="replace"), label)
    except OSError:
        return []


def scan_files(root: pathlib.Path) -> list[str]:
    """Every file in scope, tracked and untracked, sorted and de-duplicated.

    Four `git ls-files` invocations, matching the twin's two per glob. Sorted in
    Python, which is C collation for these ASCII paths and therefore agrees with
    the `sort -u` the twin pipes into under LC_ALL=C.
    """
    seen: set[str] = set()
    for glob in SCAN_GLOBS:
        for extra in ([], ["--others", "--exclude-standard"]):
            proc = subprocess.run(
                ["git", "-C", str(root), "ls-files", *extra, glob],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                continue
            seen.update(line for line in proc.stdout.split("\n") if line)
    return sorted(seen)


# --- the control fixtures, byte for byte from the twin's heredocs -----------
#
# Each one is a shape that broke this gate, or the mirror that proves the fix
# did not break the correct shape. The `-C` and bare-statement fixtures are the
# two REAL defects; the rest are their mirrors.
_CONTROLS: tuple[tuple[str, str, bool, str], ...] = (
    (
        "bad.sh",
        (
            "#!/usr/bin/env bash\n"
            "BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)\n"
            '[[ -z "$BRANCH" || "$BRANCH" == "main" ]] && exit 0\n'
            'echo "on $BRANCH"\n'
        ),
        True,
        (
            "CONTROL FAILED: an unguarded rev-parse --abbrev-ref HEAD "
            "(missing the HEAD-literal check) was NOT flagged."
        ),
    ),
    (
        "good.sh",
        (
            "#!/usr/bin/env bash\n"
            "BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)\n"
            '[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "HEAD" ]] && exit 0\n'
            'echo "on $BRANCH"\n'
        ),
        False,
        "CONTROL FAILED: a properly guarded assignment (checks the HEAD literal) WAS flagged.",
    ),
    (
        "good-symbolic.sh",
        (
            "#!/usr/bin/env bash\n"
            "BRANCH=$(git symbolic-ref --short -q HEAD) || exit 0\n"
            '[ -n "$BRANCH" ] || exit 0\n'
            'echo "on $BRANCH"\n'
        ),
        False,
        "CONTROL FAILED: a symbolic-ref call with a trailing || exit WAS flagged.",
    ),
    (
        "bad-dashC.sh",
        (
            "#!/usr/bin/env bash\n"
            'BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)\n'
            '[[ -z "$BRANCH" || "$BRANCH" == "main" ]] && exit 0\n'
            'echo "on $BRANCH"\n'
        ),
        True,
        (
            "CONTROL FAILED: git -C <dir> rev-parse --abbrev-ref HEAD "
            "(the real defect's exact shape) was NOT flagged."
        ),
    ),
    (
        "bad-bare.sh",
        (
            "#!/usr/bin/env bash\n"
            "get_current_branch() {\n"
            '    git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"\n'
            "}\n"
            'current_branch="$(get_current_branch)"\n'
            'echo "on $current_branch"\n'
        ),
        True,
        (
            "CONTROL FAILED: a bare rev-parse --abbrev-ref HEAD || echo fallback "
            "(the second real defect's shape) was NOT flagged."
        ),
    ),
    (
        "good-bare.sh",
        (
            "#!/usr/bin/env bash\n"
            "get_current_branch() {\n"
            "    local b\n"
            '    b="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || b=""\n'
            '    if [[ -z "$b" || "$b" == "HEAD" ]]; then\n'
            '        echo "main"\n'
            "    else\n"
            '        echo "$b"\n'
            "    fi\n"
            "}\n"
            'current_branch="$(get_current_branch)"\n'
            'echo "on $current_branch"\n'
        ),
        False,
        (
            "CONTROL FAILED: a properly guarded bare-statement function "
            "(checks the HEAD literal) WAS flagged."
        ),
    ),
)

# The four `pass` lines the twin prints after its controls, in its order.
_CONTROL_PASS_LINES = (
    "control: an unguarded rev-parse --abbrev-ref HEAD is detected",
    "control: the HEAD-literal guard clears it",
    "control: a fail-closed symbolic-ref assignment is not flagged",
    "control: the git -C <dir> shape (the real defect) is detected too",
)
_BARE_PASS_LINES = (
    "control: the bare-statement || echo fallback (the second real defect) is detected",
    "control: an explicit HEAD-literal check in the guarded version clears it",
)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation or control failure.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments
    at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    def ok(message: str) -> None:
        # STDOUT, matching the twin's `pass()`.
        print("ok   %s" % message)

    # --- controls first: a gate nobody has watched fail is not a gate -------
    #
    # INLINE, on every invocation, exactly as the twin runs them. A control
    # failure is fatal and immediate: everything after it would be a verdict
    # from an instrument that has just been shown not to work.
    with tempfile.TemporaryDirectory() as ctl_dir:
        ctl_root = pathlib.Path(ctl_dir)
        for name, text, must_fire, message in _CONTROLS:
            target = ctl_root / name
            target.write_text(text, encoding="utf-8")
            fired = bool(scan_file(target, str(target)))
            if fired != must_fire:
                log.error(message)
                return 1
            if name == "bad-dashC.sh":
                for line in _CONTROL_PASS_LINES:
                    ok(line)
    for line in _BARE_PASS_LINES:
        ok(line)

    # --- the real scan ------------------------------------------------------
    files = scan_files(root)
    if not files:
        log.error(
            "found ZERO .sh files under %s -- this gate is not seeing the tree, "
            "its green would mean nothing." % " ".join(SCAN_GLOBS)
        )
        return 1

    findings: list[str] = []
    for rel in files:
        if rel in EXEMPT_PATHS:
            # VISIBLE, EVERY RUN. A quiet exemption is how a gate stops meaning
            # what its name says.
            ok("exempt: %s -- %s" % (rel, EXEMPT_PATHS[rel]))
            continue
        findings.extend(scan_file(root / rel, rel))

    if not findings:
        ok(
            "%d shell file(s) scanned under %s, no unguarded git-identity conditional found"
            % (len(files), " ".join(SCAN_GLOBS))
        )
        print(
            "✓ every git-identity capture under .claude/hooks and .ci/scripts is guarded "
            "before it reaches a conditional."
        )
        return 0

    for finding in findings:
        log.error(
            "%s: captures a git identity command with no guard against failure "
            "or the misleading HEAD literal" % finding
        )
    print(file=sys.stderr)
    log.error("%d unguarded git-identity assignment(s)." % len(findings))
    print(
        '  Fix: check emptiness before use (`[[ -z "$VAR" ]] && exit 0`), and for', file=sys.stderr
    )
    print(
        '  rev-parse --abbrev-ref HEAD specifically, also guard the literal "HEAD"', file=sys.stderr
    )
    print("  value it returns on a detached checkout.", file=sys.stderr)
    return 1


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. This gate's false POSITIVE is the
    expensive one -- it flags correct code, gets suppressed, and then protects
    nothing -- so the mirrors outnumber the plants on purpose.
    """
    ctl = Controls("git-op-conditionals", floor=30, verbose=True)

    # -- the twin's own six fixtures, driven directly ------------------------
    for name, text, must_fire, _message in _CONTROLS:
        got = bool(scan_text(text, name))
        ctl.check("FIXTURE %s: fires=%s" % (name, must_fire), got, must_fire)

    # -- guard 0: the assignment as an if/elif/while condition ---------------
    ctl.check(
        "GUARD 0: `if ! sha=$(git rev-parse HEAD); then` is cleared",
        scan_text("if ! sha=$(git rev-parse HEAD); then\n  exit 1\nfi\n", "f"),
        [],
    )
    ctl.check(
        "GUARD 0: `elif` too",
        scan_text("elif sha=$(git rev-parse HEAD); then\n  :\nfi\n", "f"),
        [],
    )
    # ITS MIRROR: the same capture NOT in a condition is flagged.
    ctl.check(
        "GUARD 0 MIRROR: the same capture outside a condition is flagged",
        scan_text("sha=$(git rev-parse HEAD)\n", "f"),
        ["f:sha"],
    )

    # -- guard 1: a trailing failure handler ---------------------------------
    for handler in ("|| exit 1", "|| return 1", "|| continue", "|| true", "|| :"):
        ctl.check(
            "GUARD 1: a trailing `%s` clears it" % handler,
            scan_text("sha=$(git rev-parse HEAD) %s\n" % handler, "f"),
            [],
        )
    # ITS MIRROR: `|| echo` is NOT a failure handler, and that is the whole
    # point of the second real defect.
    ctl.check(
        "GUARD 1 MIRROR: `|| echo main` is not a handler",
        scan_text('sha=$(git rev-parse HEAD) || echo "main"\n', "f"),
        ["f:sha"],
    )

    # -- guard 2: a file-wide empty check ------------------------------------
    ctl.check(
        'GUARD 2: `-z "$B"` anywhere clears a symbolic-ref capture',
        scan_text('B=$(git symbolic-ref --short HEAD)\n[ -z "$B" ] && exit 0\n', "f"),
        [],
    )
    ctl.check(
        "GUARD 2: `-n` counts too",
        scan_text('B=$(git symbolic-ref --short HEAD)\n[ -n "$B" ] || exit 0\n', "f"),
        [],
    )
    # THE SPECIAL CASE: an empty check does NOT clear `--abbrev-ref HEAD`,
    # because that command returns the literal "HEAD" rather than failing.
    ctl.check(
        "SPECIAL: an empty check alone does NOT clear --abbrev-ref HEAD",
        scan_text('B=$(git rev-parse --abbrev-ref HEAD)\n[ -z "$B" ] && exit 0\n', "f"),
        ["f:B"],
    )
    ctl.check(
        "SPECIAL: the HEAD-literal comparison does clear it",
        scan_text('B=$(git rev-parse --abbrev-ref HEAD)\n[[ "$B" == "HEAD" ]] && exit 0\n', "f"),
        [],
    )
    ctl.check(
        "SPECIAL: single `=` counts as well as `==`",
        scan_text('B=$(git rev-parse --abbrev-ref HEAD)\n[ "$B" = "HEAD" ] && exit 0\n', "f"),
        [],
    )
    # AND IT IS PER-VARIABLE. A HEAD check on a DIFFERENT name must not clear
    # this one; that over-clearing is what the twin measured on
    # check-submodule-branches.sh.
    ctl.check(
        "SPECIAL: a HEAD check on ANOTHER variable does not clear it",
        scan_text('B=$(git rev-parse --abbrev-ref HEAD)\n[[ "$other" == "HEAD" ]]\n', "f"),
        ["f:B"],
    )

    # -- the bare shape, which has NO file-wide exemption --------------------
    ctl.check(
        "BARE: the `|| echo` fallback is flagged by line number",
        scan_text('git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"\n', "f"),
        ["f:bare-statement-line-1"],
    )
    ctl.check(
        "BARE: a HEAD check elsewhere does NOT clear it (measured, not assumed)",
        scan_text(
            'git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"\n'
            '[[ "$sm_branch" == "HEAD" ]]\n',
            "f",
        ),
        ["f:bare-statement-line-1"],
    )
    # ITS MIRROR: routed through a captured, explicitly-checked variable.
    ctl.check(
        "BARE MIRROR: the good-bare.sh shape is silent",
        scan_text(_CONTROLS[5][1], "f"),
        [],
    )

    # -- scope mirrors: things this gate must NOT flag -----------------------
    ctl.check(
        "SCOPE: a plain `git status` capture is not an identity",
        scan_text("s=$(git status)\n", "f"),
        [],
    )
    ctl.check(
        "SCOPE: a bare `git rev-parse HEAD` statement is not the bare shape",
        scan_text("git rev-parse HEAD\n", "f"),
        [],
    )
    ctl.check("SCOPE: an empty file is silent", scan_text("", "f"), [])

    # -- the whole gate, over real git repositories --------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        hooks = root / ".claude" / "hooks" / "pre-bash"
        hooks.mkdir(parents=True)

        def run() -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        # THE VACUITY CASE. No files in scope must be a refusal, never a clean
        # verdict: a gate whose subject is absent has checked nothing.
        ctl.check("VACUITY: zero files in scope is refused", run(), 1)

        (hooks / "clean.sh").write_text(_CONTROLS[1][1], encoding="utf-8")
        ctl.check("CONTROL: one guarded hook passes (UNTRACKED is in scope)", run(), 0)

        (hooks / "dirty.sh").write_text(_CONTROLS[0][1], encoding="utf-8")
        ctl.check("PLANT: an unguarded hook reds", run(), 1)

        # THE EXEMPTION, PROVEN IN BOTH DIRECTIONS. The named path is skipped;
        # the same content under any other name is not.
        (hooks / "dirty.sh").unlink()
        quality = root / ".ci" / "scripts" / "quality"
        quality.mkdir(parents=True)
        (quality / "check-git-op-conditionals.sh").write_text(_CONTROLS[0][1], encoding="utf-8")
        ctl.check("EXEMPT: the named twin is skipped", run(), 0)
        (quality / "check-other-thing.sh").write_text(_CONTROLS[0][1], encoding="utf-8")
        ctl.check("EXEMPT MIRROR: the same content under another name is flagged", run(), 1)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
