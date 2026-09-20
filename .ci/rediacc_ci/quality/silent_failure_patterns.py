"""Catch shell scripts that pipe a command which can exit non-zero on empty input.

Ported from `.ci/scripts/quality/check-silent-failure-patterns.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS.
-----------------------------------------------------------------------------

Catch shell scripts that pipe commands which can exit non-zero on empty input through a pipeline under `set -eo pipefail` without a guard.

Why: `aws s3 ls` returns exit 1 when the prefix has no contents. Combined
with `set -eo pipefail`, that propagates through any pipe (`| wc -l`,
`| awk ...`, `| head -1`, `| grep ...`) and aborts the calling script silently mid-execution. We hit this three times in one day:
  - scrub-sentinel.sh dry-run hung on empty cli/v1.0.7/ prefix
  - assert-r2-sentinel.sh would have aborted before flagging missing bytes
  - cleanup-versions.sh Phase 8 retention loop could die on a deleted-
    between-check-and-use race

The lint scans every .sh under .ci/scripts/, scripts/dev/ and scripts/ops/ that has `set -eo pipefail` (or `set -e ... pipefail`) and flags occurrences of `aws s3 ls`, `find ...`, `grep ...` piped into `wc -l` / `head` / `tail` / `awk` without a `|| true` / `|| echo ...` guard on the same logical pipeline.

Exit 0 on no findings, 1 on any unguarded match. The shared helper r2_count_objects in .ci/scripts/lib/common.sh is the recommended fix.

Whitelist: add `# silent-failure-ok: <reason>` on the line above the risky line if the unguarded pattern is intentional (e.g. an inner step that actually wants to fail the script on missing input).

TWO BUGS THAT EACH ALONE KEPT THIS GATE PERMANENTLY GREEN, both recorded in the twin's own comments and both preserved here as history:

  * The repo root was a hand-counted `../..` from the script's directory, which
    resolved to `.ci`, so the find scanned `.ci/.ci/scripts` and
    `.ci/scripts/dev` -- neither exists -- and the gate checked ZERO files from
    the day it was written. It now uses `get_repo_root`.
  * CHARACTER CLASSES, NEVER BACKSLASH ESCAPES, in every regex handed to awk
    via `-v`: awk rewrites `\\|` in a `-v` value to a plain `|`, which turned the
    old `'\\|\\| *(...)'` guard into an ERE with EMPTY alternations that matches
    every line. That made the unguarded test false everywhere, so this gate had
    never fired on anything since it was written (proven 2026-07-31 by a planted
    defect it could not see; the escape warnings were swallowed by the
    `2>/dev/null` on the awk call).

CLASS 2, the redaction-filter sink, from the twin's own comment: `cmd 2>&1 | grep -v X` under pipefail dies with ZERO error text when grep filters every line -- including on SUCCESS, when the head's whole output happens to be the redacted lines (live: clone-d1.sh's D1 export, run 30628110972: a 21-second gap, then cleanup, nothing else). The head's own failure text is also lost
when its output never flushes. Capture to a file, redact after, and test the head's own exit code instead.

A line is guarded if it contains `|| true`, `|| echo`, `|| return`, or a trailing `2>/dev/null` immediately after the head (the latter does not actually rescue exit codes but is the common operator habit; the twin treats it as a soft signal and still flags).

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

A DEFECT IN THE TWIN, FOUND WHILE PORTING AND DELIBERATELY NOT FIXED HERE.
This gate has NO ANTI-VACUITY FLOOR. If the two scan directories disappear or are renamed, `find` prints nothing, `findings` is empty, and the gate prints "No unguarded pipefail-risk pipelines found" and exits 0 -- which is exactly the failure mode its own sibling `check-swallowed-failures.sh` refuses with "This gate scanned nothing, so its verdict would be meaningless." The twin
was already green-for-the-wrong-reason once for this class of reason (the `../..` root bug above), so the shape is not hypothetical here.

It is NOT repaired in this port, because a port that changes the verdict on any tree is not a port: a floor added here would make the two implementations disagree on an empty tree, and the shadow ledger would be attesting to something that is no longer true of the twin CI actually runs. The fix belongs in a change that touches BOTH files. `selftest()` below carries a control that
pins the CURRENT behaviour and names it as the defect it is, so the day someone fixes the twin the control tells them this file needs the same edit.

THE FIND ORDER IS DIRECTORY ORDER, NOT SORTED. `find ... -print0` walks in readdir order and the twin never sorts, so the printed finding ORDER is filesystem-dependent. `os.walk` gives the same class of order. `scripts/lib/shadow-gate.ts` compares findings as an unordered multiset, so this cannot make the two sides disagree; it is stated because a reader diffing the raw streams may
see the same findings in a different order and should not go looking for a bug.

`[+\\-]` IS A THREE-CHARACTER CLASS, and it is worth pausing on. Inside a POSIX bracket expression a backslash is LITERAL, so the twin's `^set [+\\-]e` matches `set +e`, `set -e` and a backslash-e that is nonsense nothing writes. It is is carried across rather than tidied to `[+-]`, because tidying it is a change to the matcher, and a matcher change is the one thing a differential
cannot see on trees that contain no instance of the difference.

THE STRICT-MODE RULE DOES NOT `next`. The twin's `/^set [+\\-]e/` block updates `strict` and then falls through to the ordinary line handling, so the `set` line itself is scanned for pipeline shapes. It never matches one, but the fall-through is behaviour and is reproduced rather than "cleaned up" into an early return.

THE FILE-LEVEL PRE-FILTER AND THE PER-LINE TRACKER ARE DIFFERENT TESTS, and that asymmetry is the twin's. A file qualifies for scanning when ANY line matches the long `^set [+\\-](...)` alternation; within the file, `strict` is toggled by the much looser `^set [+\\-]e` plus a `pipefail` substring. A file that says `set -euo pipefail` at the top qualifies on both counts; one that
only says `set -e` qualifies on neither. Reproduced exactly, including the fact that `set -e` alone (with no trailing space) fails the pre-filter.

STREAMS. The twin's findings go through `log_error`, so they are `✗ <text>` on stderr, and its clean verdict through `log_info`. `rediacc_ci.log` produces byte-identical lines for both. The `--json` output is a bare `printf` on stdout and stays there.
"""

import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The scopes: every shell script under these three root-relative directories. scripts/ops joined on 2026-09-20, when W9 P2 moved the operator tools out of scripts/dev. A directory that stops existing contributes no files and the gate then reports success over the half of its corpus that moved, so the new home is named here in the same change as the move.
SCAN_DIRS = (".ci/scripts", "scripts/dev", "scripts/ops")

# The four matchers, transliterated from the twin's `-v` values. They are EREs there and are valid Python patterns unchanged, which is the whole reason they are quoted rather than rewritten: a "clearer" spelling is a different matcher.
PIPE_HEADS_RE = re.compile(r"(aws s3 ls|aws s3api list-objects-v2 +--query|find [^|]|grep [^|]+)")
# Class 2: a redaction filter as the pipeline SINK.
REDACT_SINK_RE = re.compile(r"2>&1 *[|] *grep -v")
# Sinks: pipeline endings that pipefail would propagate from.
SINK_RE = re.compile(r"[|] *(wc -l|head|tail|awk|jq)")
# A line is guarded if it carries one of these.
GUARD_RE = re.compile(r"[|][|] *(true|echo|return|exit|continue|:)")

# Condition heads are exempt from BOTH classes: an if/while pipeline is consumed as a test, so pipefail cannot abort the script there.
CONDITION_HEAD_RE = re.compile(r"^[ \t]*(if|elif|while|until) ")

# The waiver comment. Whitelists the NEXT non-blank, non-comment line.
WAIVER_RE = re.compile(r"# *silent-failure-ok")

# Blank and comment lines are skipped outright, and a comment also clears a dangling waiver only in the sibling gate; here a comment is simply `next`, so a waiver survives an intervening comment. That asymmetry between the two gates is real and is preserved.
BLANK_RE = re.compile(r"^[ \t]*$")
COMMENT_RE = re.compile(r"^[ \t]*#")

# The file-level pre-filter. See the port notes for why this differs from the per-line tracker and why the class has three characters in it.
STRICT_FILE_RE = re.compile(r"^set [+\\-]([euo]*pipefail|euo +pipefail|e |eu |eo |euo)")

# The per-line strict-mode tracker.
SET_LINE_RE = re.compile(r"^set [+\\-]e")

# The suffix the twin appends to a class-2 finding. Quoted whole because the parenthetical is advice the reader acts on, and re-wording it would change the finding text the differential compares.
REDACT_SUFFIX = " (redaction-filter sink: capture to a file, redact after, test the head's own rc)"


def file_is_strict(text: str) -> bool:
    """Does any line qualify this file for scanning at all?

    The twin's `grep -qE` over the whole file. A file with no strict-mode line is skipped entirely, which is the precondition that distinguishes this gate
    from `check-swallowed-failures.sh`: an abort is what this one is about, and
    a swallowed failure lies with or without strict mode.
    """
    return any(STRICT_FILE_RE.search(line) for line in text.split("\n"))


def scan_text(text: str, label: str) -> list[str]:
    """The awk pass over one file, as `<label>:<lineno>: <line>` strings.

    `label` is the path the twin's awk receives in `-v file=`, which is the
    ABSOLUTE path because `find` is given absolute directories. Passed in rather than derived so a test can drive the scanner without a filesystem.
    """
    findings: list[str] = []
    strict = False
    skip_next = False
    for number, line in enumerate(text.split("\n"), start=1):
        # NO `next` HERE. See the port notes: the twin falls through, so a `set` line is also scanned for pipeline shapes on the way past.
        if SET_LINE_RE.search(line) and "pipefail" in line:
            if "set -" in line:
                strict = True
            elif "set +" in line:
                strict = False
        if WAIVER_RE.search(line):
            skip_next = True
            continue
        if BLANK_RE.search(line) or COMMENT_RE.search(line):
            continue
        if skip_next:
            skip_next = False
            continue
        if not strict:
            continue
        if (
            PIPE_HEADS_RE.search(line)
            and SINK_RE.search(line)
            and not GUARD_RE.search(line)
            and not CONDITION_HEAD_RE.search(line)
        ):
            findings.append("%s:%d: %s" % (label, number, line))
        if (
            REDACT_SINK_RE.search(line)
            and not GUARD_RE.search(line)
            and not CONDITION_HEAD_RE.search(line)
        ):
            findings.append("%s:%d: %s%s" % (label, number, line, REDACT_SUFFIX))
    return findings


def discover(root: pathlib.Path) -> list[pathlib.Path]:
    """Every `*.sh` under the scan directories, in walk order.

    A missing directory is silently skipped, matching the twin's `find ... 2>/dev/null` inside a process substitution, whose exit status is discarded. That is a swallowed failure by the standards of the sibling gate, and it is preserved rather than repaired for the reason the module docstring gives at length.
    """
    out: list[pathlib.Path] = []
    for rel in SCAN_DIRS:
        base = root / rel
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in paths.walk_tree(base):
            for name in filenames:
                if name.endswith(".sh"):
                    candidate = pathlib.Path(dirpath) / name
                    if candidate.is_file():
                        out.append(candidate)
    return out


def collect(root: pathlib.Path) -> list[str]:
    """Every finding across the scanned corpus, in scan order."""
    findings: list[str] = []
    for path in discover(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # `grep -qE` on an unreadable file returns non-zero, so the twin skips it. Same outcome, same silence, same blind spot.
            continue
        if not file_is_strict(text):
            continue
        findings.extend(scan_text(text, str(path)))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 finding, 2 usage error.

    Argument handling is the twin's loop, including the fact that `--json` and `--help` may appear anywhere and that an unknown argument is exit 2 rather than exit 1. `--selftest` is the one addition, intercepted first.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    json_output = False
    for arg in args:
        if arg == "--json":
            json_output = True
        elif arg in ("--help", "-h"):
            # The twin prints its own header back with `sed -n '2,30p' | sed 's/^# \\?//'`. The equivalent here is the module docstring, which is where that header now lives.
            print(__doc__ or "")
            return 0
        else:
            log.error("unknown argument: %s" % arg)
            return 2

    findings = collect(paths.repo_root())

    if not findings:
        if json_output:
            print('{"findings": [], "ok": true}')
        else:
            log.info(
                "No unguarded pipefail-risk pipelines found in .ci/scripts/, scripts/dev/ or scripts/ops/"
            )
        return 0

    if json_output:
        # Assembled by hand in the twin with a `sed` escaping pass. `json.dumps` on each field produces the same document for every input the sed handles and the right one for the inputs it does not (a tab, a control character), so this is the one place the port is deliberately not a transliteration. Stated out loud because "the port fixed a bug" is a claim a reviewer must be able
        # to see.
        rows = []
        for finding in findings:
            path, _, rest = finding.partition(":")
            line, _, text = rest.partition(":")
            rows.append({"file": path, "line": int(line), "text": text})
        print(json.dumps({"ok": False, "findings": rows}, separators=(", ", ": ")))
        return 1

    log.error("Found %d unguarded pipefail-risk pipeline(s):" % len(findings))
    for finding in findings:
        log.error("  %s" % finding)
    log.error("")
    log.error("Each line pipes a command that may exit non-zero on empty input")
    log.error("through a pipeline. Under `set -eo pipefail` the script will")
    log.error("abort silently. Either:")
    log.error("  - Add `|| true` / `|| echo 0` to the pipeline.")
    log.error("  - Use the r2_count_objects helper in .ci/scripts/lib/common.sh.")
    log.error("  - Add `# silent-failure-ok: <reason>` on the line above if")
    log.error("    aborting is actually the intended behaviour.")
    return 1


# The specimen from the twin's header, in the shape it actually shipped in.
_STRICT = "#!/bin/bash\nset -euo pipefail\n"


def selftest() -> int:
    """Plant each violation, prove it fires; remove it, prove it does not.

    BOTH DIRECTIONS FOR EVERY CONTROL. This gate's history is two independent bugs that each made it match NOTHING while reporting a clean tree, so the mirrors here are not decoration: a matcher that fires on everything and a matcher that fires on nothing are both invisible to a positive-only suite.
    """
    ctl = Controls("silent-failure-patterns", floor=29, verbose=True)

    def hits(body: str) -> list[str]:
        return scan_text(_STRICT + body, "F")

    # -- class 1: an unguarded risky head into a propagating sink -----------
    ctl.check(
        "PLANT: aws s3 ls piped into wc -l is caught",
        len(hits("n=$(aws s3 ls s3://b/p | wc -l)\n")),
        1,
    )
    ctl.check("PLANT: find piped into head is caught", len(hits("find . -name x | head -1\n")), 1)
    ctl.check("PLANT: grep piped into awk is caught", len(hits("grep foo f | awk '{print}'\n")), 1)
    ctl.check(
        "PLANT: aws s3api list-objects-v2 --query into jq is caught",
        len(hits("aws s3api list-objects-v2  --query 'x' | jq .\n")),
        1,
    )

    # -- their mirrors, every one of which must stay SILENT ------------------
    ctl.check(
        "MIRROR: a `|| true` guard on the same line clears it",
        len(hits("n=$(find . | wc -l || true)\n")),
        0,
    )
    ctl.check("MIRROR: `|| echo 0` is a guard too", len(hits("n=$(find . | wc -l || echo 0)\n")), 0)
    ctl.check(
        "MIRROR: an `if` head is consumed as a test, so pipefail cannot abort",
        len(hits("if find . | wc -l; then :; fi\n")),
        0,
    )
    ctl.check(
        "MIRROR: a `while` head is exempt for the same reason",
        len(hits("while find . | head -1; do :; done\n")),
        0,
    )
    ctl.check(
        "MIRROR: a risky head with no sink is not a finding", len(hits("find . -name x\n")), 0
    )
    ctl.check("MIRROR: a sink with no risky head is not a finding", len(hits("cat f | wc -l\n")), 0)
    ctl.check("MIRROR: a comment naming the shape is prose", len(hits("# find . | wc -l\n")), 0)
    ctl.check("MIRROR: a blank line is not a finding", len(hits("\n\n")), 0)

    # -- the waiver ---------------------------------------------------------
    ctl.check(
        "MIRROR: a silent-failure-ok comment whitelists the next line",
        len(hits("# silent-failure-ok: aborting is the point here\nfind . | wc -l\n")),
        0,
    )
    ctl.check(
        "PLANT: the waiver covers ONE line, not the one after it",
        len(hits("# silent-failure-ok: r\nfind . | wc -l\nfind . | head -1\n")),
        1,
    )

    # -- class 2: the redaction-filter sink ---------------------------------
    ctl.check(
        "PLANT: a `2>&1 | grep -v` sink is caught (run 30628110972)",
        len(hits("wrangler d1 export 2>&1 | grep -v secret\n")),
        1,
    )
    ctl.truthy(
        "CONTROL: the class-2 finding carries its own advice suffix",
        REDACT_SUFFIX in hits("wrangler d1 export 2>&1 | grep -v secret\n")[0],
    )
    ctl.check(
        "MIRROR: a guarded redaction sink is not a finding",
        len(hits("wrangler export 2>&1 | grep -v secret || true\n")),
        0,
    )
    ctl.check(
        "MIRROR: `| grep -v` without the 2>&1 is not class 2",
        len(hits("cat f | grep -v secret\n")),
        0,
    )

    # -- strict mode is the precondition ------------------------------------
    ctl.check(
        "MIRROR: outside strict mode nothing is a finding",
        len(scan_text("#!/bin/bash\nfind . | wc -l\n", "F")),
        0,
    )
    ctl.check(
        "PLANT: `set +o pipefail` mid-file turns the scanner off again",
        len(hits("find . | wc -l\nset +euo pipefail\nfind . | head -1\n")),
        1,
    )
    ctl.truthy("CONTROL: `set -euo pipefail` qualifies a file", file_is_strict("set -euo pipefail"))
    ctl.truthy("CONTROL: `set -eo pipefail` qualifies a file", file_is_strict("set -eo pipefail"))
    ctl.falsy(
        "MIRROR: a bare `set -e` does NOT qualify a file (no trailing space)",
        file_is_strict("set -e"),
    )
    ctl.falsy("MIRROR: a file with no set line does not qualify", file_is_strict("echo hi"))

    # -- THE INHERITED DEFECT, PINNED SO IT CANNOT BE FORGOTTEN ------------- This gate has no anti-vacuity floor: a corpus that collapses to zero files produces "No unguarded pipefail-risk pipelines found" and exit 0. That is the twin's behaviour, and a port that changed it would be attesting to a verdict the twin does not reach. The control below asserts the CURRENT, WRONG answer
    # on purpose, so the day the twin grows a floor this line goes red and names the file that has to follow it.
    with tempfile.TemporaryDirectory() as tmp:
        empty = pathlib.Path(tmp)
        ctl.check(
            "INHERITED DEFECT: an empty corpus yields no findings (the twin has no floor)",
            collect(empty),
            [],
        )

    # -- the whole gate, end to end -----------------------------------------
    def run(root: pathlib.Path, args: list[str]) -> int:
        saved = os.environ.get(paths.ROOT_ENV)
        os.environ[paths.ROOT_ENV] = str(root)
        try:
            return main(args)
        finally:
            if saved is None:
                del os.environ[paths.ROOT_ENV]
            else:
                os.environ[paths.ROOT_ENV] = saved

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / ".ci" / "scripts").mkdir(parents=True)
        (root / ".ci" / "scripts" / "clean.sh").write_text(
            _STRICT + "n=$(find . | wc -l || true)\n", encoding="utf-8"
        )
        ctl.check("CONTROL: a clean corpus exits 0", run(root, []), 0)
        (root / ".ci" / "scripts" / "dirty.sh").write_text(
            _STRICT + "n=$(find . | wc -l)\n", encoding="utf-8"
        )
        ctl.check("PLANT: one unguarded pipeline exits 1", run(root, []), 1)
        ctl.check("CONTROL: --json also exits 1 on a finding", run(root, ["--json"]), 1)
        ctl.check("CONTROL: an unknown argument is exit 2, not 1", run(root, ["--nope"]), 2)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
