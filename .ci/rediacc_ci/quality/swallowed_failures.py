r"""Catch a GATE that cannot tell a failed probe from a clean tree.

Ported from `.ci/scripts/quality/check-swallowed-failures.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS.
-----------------------------------------------------------------------------

THE CLASS. A gate captures a probe's output, discards the probe's exit status AND its stderr, and then reads the captured value. When the probe fails the value is empty, and empty is byte-identical to "nothing to report". The gate then prints its success message and exits 0. It is not reporting that things
are fine; it is reporting nothing, in the voice of success.

THE LIVE SPECIMEN, fixed 2026-07-28 in .ci/scripts/quality/check-go-deps.sh:

    outdated=$(go list -u -m -json all 2>/dev/null |
        jq -rs '...' 2>/dev/null || true)
    while IFS=' ' read -r path current latest uptime; do ... done <<<"$outdated"

`go list` was exiting 1 on the machine (go.mod wanted >= 1.25, PATH had 1.24).
The `2>/dev/null` hid the reason, the `|| true` hid the status, the loop ran zero times, and the gate printed "All Go direct dependencies are up-to-date" and exited 0 while CI failed on the same commit.

NOT THE SAME AS check-silent-failure-patterns.sh, and this is a SIBLING to it rather than an extension of it, for four reasons:
  1. Opposite polarity. That gate says "your probe is UNDER-guarded, a
     non-zero exit will abort the script"; this one says "your probe is
     OVER-guarded, a non-zero exit vanishes". One recommends adding `|| true`;
     the other flags it. Merging them makes a single script whose two halves
     give contradictory advice and whose one waiver comment is ambiguous about
     which direction is being waived.
  2. Different scan unit. That gate is strictly line-based. The specimen above
     spans three physical lines, with `2>/dev/null` on the first and
     `|| true` on the third, so a line-based scanner cannot see the shape at
     all. This gate joins continuations into logical lines first.
  3. Different precondition. That gate only inspects files that set
     `pipefail`, because an abort is what it is about. A swallowed failure
     lies with or without strict mode.
  4. Different scope. That gate is about any script aborting; this one is
     about a VERDICT being wrong, so it scans only the directories that hold
     gates.

WHAT IT FLAGS, precisely. All four must hold:
  a. The value is CAPTURED into a variable via $( ). A bare `cmd || true` on
     its own line is best-effort cleanup and is none of this gate's business.
  b. The capture ends in a fallback that discards the exit status AND yields a
     value indistinguishable from a legitimate empty result: `|| true`,
     `|| :`, `|| echo` with nothing, "", 0, [] or {}. A fallback with a
     DISTINGUISHABLE sentinel (`|| echo unknown`, `|| echo missing`,
     `|| echo 000`) is fine: the caller can still tell.
  c. stderr is not folded into the value. `2>&1` keeps the failure visible IN
     the captured data, so the caller can still tell.
  d. Nothing downstream distinguishes the empty case. Either no test of the
     variable follows at all, or the test's own branch treats empty as
     success (`exit 0` / `return 0` with no error reported inside it).

WHAT IT DELIBERATELY DOES NOT FLAG (precision over recall: a noisy gate gets suppressed, and a suppressed gate is the bug being fixed here)
  * Commands whose non-zero exit IS the answer rather than an error:
    `grep`, `command -v`, `type`, `which`, `hash`, `diff`, `cmp`. For these,
    "no match" and "failed" are the same event by design. Residual risk,
    stated rather than hidden: `grep` also exits 2 on an unreadable file or a
    bad pattern, and `2>/dev/null || true` swallows that too. Flagging it
    costs 8 false positives on the current tree, which is the trade taken.
  * Anything where the fallback is a real sentinel (rule b).
  * Captures that fold stderr in (rule c).

WAIVER. Put `# swallowed-failure-ok: <reason>` on the line above. The reason
is held to the same bar as a BLOCKER (>= 30 characters, no banned filler
phrase), because a waiver here re-opens the exact hole this gate closes.

TEST SEAM. SWALLOWED_SCAN_ROOT overrides the repo root; SWALLOWED_SCAN_DIRS
overrides the scanned directories (space-separated, root-relative).

Exits 0 on no findings, 1 on any finding.

THE PATTERNS LIVE INSIDE THE AWK PROGRAM rather than being passed with `-v`. awk processes backslash escapes when it assigns a `-v` value, so `\\(` arrived as a bare `(` and every regex became "Unmatched (". That is not a style point: the first version of this gate died on all 42 files and still printed "OK: no gate captures a probe...", because the empty output of a dead awk is
indistinguishable from the empty output of a clean scan. It committed the defect it polices, which is why `scan_file` treats a non-zero awk exit as fatal.

AND THE SCANNER MUST BE FATAL IN THE CALLER, not inside the scan function. The first version ran it inside `< <(scan_file "$f")`, and an `exit` inside a process substitution kills only that subshell: the gate carried on and reported a clean scan over files it had never read. That is the same shape as the defect being policed, which is why the caller checks the return value instead.

SCOPE. quality/ and security/ are where gates live; lib/ is where they get their
helpers, and a helper that swallows a failure lies on every caller's behalf (r2_count_objects in lib/common.sh is exactly that shape, which is why lib/ is not optional).

THE FUNCTION BOUNDARY IS PART OF THE WINDOW. Letting the 12-logical-line window run past the closing brace made a `log_error` in the NEXT function count as handling for this one, which silently cleared r2_count_objects in lib/common.sh: a genuine finding, and the one the sibling gate recommends as a remedy.

THE TEST PATTERN IS BUILT PER VARIABLE rather than templated once: an emptiness test on some OTHER variable says nothing about this one, and that distinction is what keeps the pre-fix check-go-deps probe flagged (its loop tests $path, never $outdated).

FOUR SHAPES COUNT AS "the author looked at the empty case":
    [[ -z/-n $VAR ]]           emptiness test
    [[ $VAR -eq/==/=~ ... ]]   value test, including the =~ normalisers that
                               lib/common.sh and the release-state validator use
    (( VAR ... ))              arithmetic test
    jq -e / jq empty <<<$VAR   validity test, which is how dependency-inventory
                               checks its npm trees

AN UNTERMINATED BUFFER (unbalanced parens through EOF) still has to be seen;
dropping it would let a defect hide behind a stray paren.

THE OPTIONAL QUOTE IN THE CAPTURE PATTERN IS LOAD-BEARING:
`tree_all="$(npm ls ... || true)"` is the commonest spelling in this repo, and
omitting it hid every quoted capture, including the dependency-inventory specimens.

A WAIVER MUST SIT IMMEDIATELY ABOVE the line it excuses: any other comment or a blank line clears a dangling one, or it drifts and starts excusing something nobody read.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE AWK PROGRAM IS TRANSLATED FUNCTION BY FUNCTION, with the original regex quoted above each Python compilation, because every one of them has an edge that a "sensible" rewrite loses. Two translation facts are worth naming:

  * `"\\047"` inside an awk string is a backslash followed by `047`, which the
    regex engine reads as the octal escape for `'`. The class `["\047]?` is
    therefore `["']?`, written out here.
  * awk's `gsub(/\(/, "(", tmp)` is a COUNT, not a substitution that changes
    anything: it replaces each `(` with `(`. The twin uses it purely for its
    return value, to balance parentheses. `str.count("(")` is the same number.

THE PARENTHESIS BALANCE IS COUNTED OVER THE WHOLE LOGICAL LINE INCLUDING QUOTED
TEXT, so a `(` inside a string keeps the folder swallowing lines. That is the twin's behaviour and the reason the END block has to flush an unterminated buffer at all.

`validate_blocker_quality` IS RE-IMPLEMENTED HERE from `.ci/scripts/lib/blocker-validator.sh`, with both banned-phrase lists and the 30-character floor copied verbatim, for the same reason `_gh_probe` is copied in `submodule_branches`: the port does not source `common.sh` and the exact messages are what a reader greps for. `rediacc_ci.core.allowlist` is the typed home this should
eventually move to.

`ci_error` PRINTS `::error::<msg>` ON STDOUT UNDER CI=true AND `✗ <msg>` ON
STDERR OTHERWISE. Both are reproduced, because `scripts/lib/shadow-gate.ts` strips either prefix to the same normalized finding and a port that always used one would still be equivalent, but a human reading a CI log would lose the annotation.

`find ... | sort` IS SORTED HERE, unlike the sibling gate, so the finding ORDER
is stable across machines. `sorted()` under `LC_ALL=C` is byte order, which is
what `sort` gives.

STREAMS. The banner, the quoted source line under each finding and the advice
block are bare `echo` on STDOUT; the finding identity lines are `log_error` on
stderr. The twin's own comment about this split is in `shadow-gate.ts`: "the stderr half carries the `<path>:<line>: <var>: <reason>` identity, which is the half that decides equivalence, so the split costs precision rather than soundness."
"""

import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls
from rediacc_ci.core import allowlist

# The seams the twin exposes so its own controls, and any gate test, can drive it against fixtures instead of the real tree.
ROOT_ENV = "SWALLOWED_SCAN_ROOT"
DIRS_ENV = "SWALLOWED_SCAN_DIRS"

DEFAULT_SCAN_DIRS = (".ci/scripts/quality", ".ci/scripts/security", ".ci/scripts/lib")

# How many logical lines after the capture count as downstream.
WINDOW = 12

# awk: "(^|[ \t]|\\()(local[ \t]+|export[ \t]+|readonly[ \t]+)?[A-Za-z_][A-Za-z0-9_]*=[\"\\047]?[$]\\("
CAPTURE_RE = re.compile(
    r"(^|[ \t]|\()(local[ \t]+|export[ \t]+|readonly[ \t]+)?[A-Za-z_][A-Za-z0-9_]*=[\"']?[$]\("
)

# awk: "\\|\\|[ \t]*(true|:|echo[ \t]*\\)|echo[ \t]+\"\"|echo[ \t]+0[ \t]*\\)|echo[ \t]+\"0\"
#       |echo[ \t]+.\\[\\].|echo[ \t]+.\\{\\}.|printf[ \t]+..[ \t]*\\))"
SWALLOW_RE = re.compile(
    r"\|\|[ \t]*(true|:|echo[ \t]*\)|echo[ \t]+\"\"|echo[ \t]+0[ \t]*\)|echo[ \t]+\"0\""
    r"|echo[ \t]+.\[\].|echo[ \t]+.\{\}.|printf[ \t]+..[ \t]*\))"
)

# awk: "(^|[ \t]|\\(|\\|)(grep|egrep|fgrep|rg|command -v|type -|which|hash|diff|cmp)[ \t]"
ANSWER_RE = re.compile(
    r"(^|[ \t]|\(|\|)(grep|egrep|fgrep|rg|command -v|type -|which|hash|diff|cmp)[ \t]"
)

# Tokens meaning the empty case was reported rather than passed over.
ESCALATE_RE = re.compile(
    r"(log_error|log_warn|log_fail|ci_error|ci_warn|die[ \t]|exit[ \t]+[1-9]"
    r"|return[ \t]+[1-9]|FAIL|ERROR|::error|::warning|PROBE_FAILED)"
)

# Tokens meaning the empty case ended the script successfully.
PASS_RE = re.compile(r"(exit[ \t]+0|return[ \t]+0)")

# The waiver comment, and the shapes that clear a dangling one.
WAIVER_RE = re.compile(r"^#[ \t]*swallowed-failure-ok:")
COMMENT_RE = re.compile(r"^#")

# End of the enclosing function, or the start of the next one.
BOUNDARY_CLOSE_RE = re.compile(r"^\}")
BOUNDARY_DEF_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\(\)[ \t]*\{")
BOUNDARY_FUNCTION_RE = re.compile(r"^function[ \t]")

# `if` recognition for `branch_of`. awk's [[:space:]] inside a single line is
# space and tab; the class is written out for the reason npmrc records.
IF_RE = re.compile(r"(^|[ \t])if[ \t]")
THEN_RE = re.compile(r";[ \t]*then")
FI_RE = re.compile(r"(^|[ \t])fi([ \t]|;|$)")
ELSE_RE = re.compile(r"^(else|elif)([ \t]|$)")

# A logical line's trailing continuation shapes: a pipe, an `&&`, a backslash.
CONTINUES_RE = re.compile(r"(\||&&|\\)$")

# The two verdict strings, and the default. Quoted as constants because each is a distinct diagnosis and a reader greps for them.
VERDICT_EXITS_OK = "the empty case exits successfully"
VERDICT_NO_REPORT = "nothing reports the empty case"
VERDICT_NO_TEST = "no test distinguishes a failed probe from an empty result"


class Logical:
    """One logical line: its text, the physical line it started on, its waiver.

    A small class rather than three parallel lists because the awk original has exactly that (LL, LN, WV) and keeping them in step by index is the kind of bookkeeping that goes wrong silently when an entry is appended in one place and not another.
    """

    __slots__ = ("line", "start", "waiver")

    def __init__(self, line: str, start: int, waiver: str) -> None:
        self.line = line
        self.start = start
        self.waiver = waiver


def fold(text: str) -> list[Logical]:
    """Pass 1: fold physical lines into logical ones.

    A logical line ends when its parentheses balance AND it does not end in a pipe, an `&&` or a backslash. Comments and blanks are dropped, and either clears a pending waiver.
    """
    out: list[Logical] = []
    buf = ""
    pending_waiver = ""
    start = 0
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.strip(" \t")
        if buf == "":
            if WAIVER_RE.search(line):
                pending_waiver = line
                continue
            if line == "" or COMMENT_RE.search(line):
                pending_waiver = ""
                continue
            start = number
            buf = line
        else:
            buf = buf + " " + line

        # gsub() used as a COUNT; see the port notes.
        if buf.count("(") > buf.count(")"):
            continue
        if CONTINUES_RE.search(buf):
            continue

        out.append(Logical(buf, start, pending_waiver))
        pending_waiver = ""
        buf = ""

    if buf != "":
        out.append(Logical(buf, start, pending_waiver))
    return out


def capture_var(s: str) -> str:
    """Name of the variable being assigned in a capture, or "".

    awk:
        sub(/=["\\047]?[$]\\(.*$/, "", t)   drop from the `=$(` to end of line
        sub(/^.*[[:space:](]/, "", t)       GREEDY: drop to the LAST space or `(`
        sub(/^(local|export|readonly)$/, "", t)
        if (t !~ /^[A-Za-z_][A-Za-z0-9_]*$/) return ""
    """
    t = re.sub(r"=[\"']?[$]\(.*$", "", s, count=1)
    # `^.*[ \t(]` is greedy in awk, so it eats up to the LAST separator.
    t = re.sub(r"^.*[ \t(]", "", t, count=1)
    t = re.sub(r"^(local|export|readonly)$", "", t, count=1)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t):
        return ""
    return t


def is_boundary(s: str) -> bool:
    """End of the enclosing function, or the start of the next one."""
    return bool(
        BOUNDARY_CLOSE_RE.search(s) or BOUNDARY_DEF_RE.search(s) or BOUNDARY_FUNCTION_RE.search(s)
    )


def test_pattern(var: str) -> re.Pattern[str]:
    """The four shapes that count as looking at the empty case, for ONE var.

    Built per variable rather than templated once; see the header for why.
    """
    return re.compile(
        r"(\[\[?[^]]*(-z|-n)[ \t]+.?[$]\{?%(v)s"
        r"|\[\[?[^]]*[$]\{?%(v)s[^]]*(-eq|-gt|-lt|==|!=|=~)"
        r"|\(\([^)]*%(v)s"
        r"|jq[ \t]+(-e|empty)[^|]*[$]\{?%(v)s)" % {"v": re.escape(var)}
    )


def branch_of(lines: list[Logical], j: int) -> str:
    """The body governed by the test on logical line `j` (0-based here).

    For an `if`, everything up to the matching else/elif/fi; for a one-line `&&`
    or `||` form, the rest of that same line. Index arithmetic is 0-based where
    awk's is 1-based; the shape is otherwise identical.
    """
    n = len(lines)
    if not IF_RE.search(lines[j].line) and not THEN_RE.search(lines[j].line):
        return lines[j].line
    body = lines[j].line
    depth = 0
    for k in range(j, n):
        opened = bool(IF_RE.search(lines[k].line))
        closed = bool(FI_RE.search(lines[k].line))
        if opened:
            depth += 1
        if closed:
            depth -= 1
        if k > j:
            body = body + " " + lines[k].line
        # `k > j` alone misses the ONE-LINE `if ...; then ...; fi` shape: it
        # opens and closes depth in the SAME iteration (k == j), so the guard
        # never fires there, and the loop absorbs the NEXT, unrelated logical
        # line into body before its k > j check finally sees depth <= 0.
        # `opened and closed` catches exactly that same-line close.
        if depth <= 0 and (k > j or (opened and closed)):
            break
        if depth == 1 and k > j and ELSE_RE.search(lines[k].line):
            break
    return body


def window_has_escalation(lines: list[Logical], i: int, limit: int) -> bool:
    """Does anything between `i` and `limit` report the problem at all?"""
    for j in range(i + 1, limit + 1):
        if is_boundary(lines[j].line):
            return False
        if ESCALATE_RE.search(lines[j].line):
            return True
    return False


def classify(lines: list[Logical], i: int, var: str) -> str:
    """ "" when the empty case is distinguished downstream; else the reason."""
    tre = test_pattern(var)
    n = len(lines)
    limit = min(i + WINDOW, n - 1)
    j = i + 1
    while j <= limit:
        if is_boundary(lines[j].line):
            break
        if not tre.search(lines[j].line):
            j += 1
            continue
        branch = branch_of(lines, j)
        if ESCALATE_RE.search(branch):
            return ""
        if PASS_RE.search(branch):
            return VERDICT_EXITS_OK
        # A test with neither an escalation nor an exit in its own branch: accept it if the surrounding window reports the problem at all.
        if window_has_escalation(lines, i, limit):
            return ""
        return VERDICT_NO_REPORT
    return VERDICT_NO_TEST


class Row:
    """One FINDING or WAIVER row, as the awk program prints it."""

    __slots__ = ("detail", "file", "kind", "line", "text", "var")

    def __init__(self, kind: str, file: str, line: int, var: str, detail: str, text: str) -> None:
        self.kind = kind
        self.file = file
        self.line = line
        self.var = var
        self.detail = detail
        self.text = text


def scan_text(text: str, file: str) -> list[Row]:
    """Pass 2: apply the four rules to every logical line.

    Order matters and is the twin's: capture, then swallow, then the two exemptions, then the variable name, then the waiver, then the classifier. A waiver is recorded WITHOUT running the classifier, so a waived line is never also a finding.
    """
    lines = fold(text)
    rows: list[Row] = []
    for i, entry in enumerate(lines):
        s = entry.line
        if not CAPTURE_RE.search(s):
            continue
        if not SWALLOW_RE.search(s):
            continue
        if "2>&1" in s:
            continue
        if ANSWER_RE.search(s):
            continue
        var = capture_var(s)
        if var == "":
            continue
        if entry.waiver != "":
            rows.append(Row("WAIVER", file, entry.start, var, entry.waiver, ""))
            continue
        verdict = classify(lines, i, var)
        if verdict != "":
            rows.append(Row("FINDING", file, entry.start, var, verdict, s))
    return rows


# -- the BLOCKER quality bar, from rediacc_ci.core.allowlist -------------------
#
# COLLAPSED 2026-09-09. This module used to carry its own copy of both banned-phrase tables, the 30-character floor and all four message bodies, 150 lines transcribed from `.ci/scripts/lib/blocker-validator.sh`. Two things had already drifted in that copy and neither was visible from here:
#
# * the messages spelled the separator `--` where the bash twin this module ports prints U+2014, so the two disagreed byte for byte on every rejection
#     from line 2 onward. It never reddened anything because `shadow-gate`
# classifies only the ci_error line as a FINDING and the rest as chatter. * the trim was `re.sub(r"^[ \t]*", ...)`, space and tab only, where the twin's
#     `sed 's/^[[:space:]]*//'` under LC_ALL=C also eats \v \f \r. A reason led by
# a carriage return normalised to a different length in the two.
#
# Both are gone by construction now: the phrases, the floor and the words are `rediacc_ci.core.allowlist`'s, which is the same module the bash twin and the TypeScript gates read.


def ci_error(message: str) -> None:
    """`::error::<msg>` on stdout under CI, `✗ <msg>` on stderr otherwise."""
    if os.environ.get("CI") == "true":
        print("::error::%s" % message)
    else:
        log.error(message)


def validate_blocker_quality(entry_id: str, reason: str, file: str) -> bool:
    """True when the waiver reason clears the bar. Prints why when it does not.

    THE RULE IS NOT HERE. `rediacc_ci.core.allowlist.validate_reason` decides and
    supplies the words; what stays in this module is the STREAM SPLIT, which is
    the twin's and not the rule's: the first line goes through `ci_error`, so it becomes a `::error::` annotation under CI, and the rest is plain stdout.
    """
    rejection = allowlist.validate_reason(entry_id, reason, file)
    if rejection is None:
        return True
    lines = rejection.message.split("\n")
    ci_error(lines[0])
    for line in lines[1:]:
        print(line)
    return False


def scan_dirs(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """The scanned directories: the seam, split on whitespace, or the default."""
    environ = os.environ if env is None else env
    override = environ.get(DIRS_ENV, "")
    if override:
        return tuple(override.split())
    return DEFAULT_SCAN_DIRS


def discover(root: pathlib.Path, dirs: tuple[str, ...]) -> list[pathlib.Path]:
    """Every `*.sh` under the scan dirs, SORTED. See the port notes."""
    out: list[str] = []
    for rel in dirs:
        base = root / rel
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in paths.walk_tree(base):
            for name in filenames:
                candidate = pathlib.Path(dirpath) / name
                if name.endswith(".sh") and candidate.is_file():
                    out.append(str(candidate))
    return [pathlib.Path(p) for p in sorted(out)]


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 finding or refusal, 2 usage error."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    json_output = False
    for arg in args:
        if arg == "--json":
            json_output = True
        elif arg in ("--help", "-h"):
            print(__doc__ or "")
            return 0
        else:
            log.error("unknown argument: %s" % arg)
            return 2

    override_root = os.environ.get(ROOT_ENV, "")
    root = pathlib.Path(override_root).resolve() if override_root else paths.repo_root()
    dirs = scan_dirs()

    files = discover(root, dirs)

    # ANTI-VACUITY. A gate that scans zero files reports "clean" forever, which is the exact failure mode this gate exists to police. Refuse to be that.
    if not files:
        log.error("No shell scripts found under: %s" % " ".join(dirs))
        log.error("This gate scanned nothing, so its verdict would be meaningless. Fix the scope.")
        return 1

    findings: list[Row] = []
    waivers: list[Row] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # The twin's awk would fail to open the file, `scan_file` would see a non-zero exit, and the whole gate would refuse. Same here: a dead scanner produces the same empty output as a clean file.
            log.error("could not read %s (%s):" % (path, exc))
            log.error("A dead scanner produces the same empty output as a clean file.")
            log.error("Refusing to report a verdict.")
            return 1
        for row in scan_text(text, str(path)):
            (waivers if row.kind == "WAIVER" else findings).append(row)

    # Every waiver reason is held to the BLOCKER quality bar. A waiver reopens the hole this gate closes, so "# swallowed-failure-ok: fine" must not pass.
    waiver_bad = False
    for waiver in waivers:
        reason = waiver.detail.split("swallowed-failure-ok:", 1)[-1]
        # `${reason# }`: ONE leading space, not a strip. A reason indented two
        # spaces keeps one of them, which is the twin's behaviour and matters because the length floor counts characters.
        reason = reason.removeprefix(" ")
        if not validate_blocker_quality(
            "%s:%d ($%s)" % (waiver.file, waiver.line, waiver.var), reason, waiver.file
        ):
            waiver_bad = True

    prefix = "%s/" % root

    if json_output:
        rows = [
            {
                "file": row.file.removeprefix(prefix),
                "line": row.line,
                "var": row.var,
                "reason": row.detail,
                "text": row.text,
            }
            for row in findings
        ]
        print(
            json.dumps(
                {
                    "ok": not findings and not waiver_bad,
                    "scanned": len(files),
                    "waived": len(waivers),
                    "findings": rows,
                },
                separators=(", ", ": "),
            )
        )
        return 0 if (not findings and not waiver_bad) else 1

    print()
    print("Swallowed Failures")
    print("============================================================")
    print(
        "%d gate script(s) scanned in %s; %d waived." % (len(files), " ".join(dirs), len(waivers))
    )
    print()

    if not findings and not waiver_bad:
        log.info(
            "OK: no gate captures a probe whose failure is indistinguishable from an empty result."
        )
        return 0

    if findings:
        log.error(
            "Found %d capture(s) whose failure is indistinguishable from an empty result:"
            % len(findings)
        )
        for row in findings:
            shown = row.file.removeprefix(prefix)
            log.error("  %s:%d: $%s: %s" % (shown, row.line, row.var, row.detail))
            print("      %s" % row.text)
        print()
        print("Each one discards both the exit status and stderr, so a failed probe")
        print("produces the same value as a clean result and the gate reports success.")
        print("Fix one of these ways:")
        print('  - Capture the status: raw=$(cmd 2>"$err") || status=$?, then act on it.')
        print("  - Fall back to a DISTINGUISHABLE sentinel (|| echo unavailable), not to empty.")
        print("  - Test the captured value and report the empty case as a failure.")
        print("  - Add '# swallowed-failure-ok: <reason>' above the line if empty genuinely")
        print("    means the same thing as failure here.")

    return 1


def selftest() -> int:
    """Both directions on every one of the four rules and on the classifier."""
    ctl = Controls("swallowed-failures", floor=36, verbose=True)

    def rows(body: str) -> list[Row]:
        return scan_text(body, "F")

    # -- rule a: the value must be CAPTURED --------------------------------
    ctl.check(
        "PLANT: the check-go-deps specimen, folded across three lines, is caught",
        len(
            rows(
                "outdated=$(go list -u -m -json all 2>/dev/null |\n"
                "    jq -rs '.' 2>/dev/null || true)\n"
                'while IFS=" " read -r path current latest uptime; do :; done <<<"$outdated"\n'
            )
        ),
        1,
    )
    ctl.check(
        "MIRROR: a bare `cmd || true` on its own line is cleanup, not a capture",
        len(rows("rm -rf /tmp/x || true\n")),
        0,
    )
    ctl.check(
        "CONTROL: the QUOTED capture spelling is seen too",
        len(rows('tree_all="$(npm ls --all || true)"\n')),
        1,
    )

    # -- rule b: the fallback must be indistinguishable from empty ----------
    ctl.check("PLANT: `|| true` swallows", len(rows("v=$(probe || true)\n")), 1)
    ctl.check("PLANT: `|| :` swallows", len(rows("v=$(probe || :)\n")), 1)
    ctl.check("PLANT: `|| echo` with nothing swallows", len(rows("v=$(probe || echo)\n")), 1)
    ctl.check('PLANT: `|| echo ""` swallows', len(rows('v=$(probe || echo "")\n')), 1)
    ctl.check("PLANT: `|| echo []` swallows", len(rows('v=$(probe || echo "[]")\n')), 1)
    ctl.check(
        "MIRROR: a DISTINGUISHABLE sentinel is fine, the caller can still tell",
        len(rows("v=$(probe || echo unavailable)\n")),
        0,
    )
    ctl.check(
        "MIRROR: `|| echo 000` is a sentinel, not an empty result",
        len(rows("v=$(probe || echo 000)\n")),
        0,
    )
    ctl.check("MIRROR: no fallback at all is not this defect", len(rows("v=$(probe)\n")), 0)

    # -- rule c: stderr folded in keeps the failure visible -----------------
    ctl.check(
        "MIRROR: `2>&1` keeps the failure IN the value, so it is not swallowed",
        len(rows("v=$(probe 2>&1 || true)\n")),
        0,
    )

    # -- the answer-command exemption --------------------------------------
    for cmd in ("grep -q x f", "command -v jq", "which node", "diff a b", "cmp a b"):
        ctl.check(
            "MIRROR: %r exits non-zero as an ANSWER, not an error" % cmd.split()[0],
            len(rows("v=$(%s || true)\n" % cmd)),
            0,
        )

    # -- rule d: the classifier --------------------------------------------
    ctl.check(
        "CONTROL: an emptiness test that ESCALATES clears the finding",
        len(rows('v=$(probe || true)\nif [[ -z "$v" ]]; then\nlog_error "probe failed"\nfi\n')),
        0,
    )
    ctl.check(
        "PLANT: an emptiness test whose branch exits 0 is 'the empty case exits successfully'",
        rows('v=$(probe || true)\nif [[ -z "$v" ]]; then\nexit 0\nfi\n')[0].detail,
        VERDICT_EXITS_OK,
    )
    ctl.check(
        "PLANT: no test at all is 'no test distinguishes ...'",
        rows("v=$(probe || true)\necho done\n")[0].detail,
        VERDICT_NO_TEST,
    )
    ctl.check(
        "PLANT: a test on a DIFFERENT variable does not answer for this one",
        rows('v=$(probe || true)\nif [[ -z "$other" ]]; then\nlog_error x\nfi\n')[0].detail,
        VERDICT_NO_TEST,
    )
    ctl.check(
        "CONTROL: an arithmetic test counts as looking at the empty case",
        len(rows('v=$(probe || true)\nif ((v > 0)); then\nlog_error "bad"\nfi\n')),
        0,
    )
    ctl.check(
        "CONTROL: a `jq -e` validity test counts too",
        len(rows('v=$(probe || true)\nif jq -e . <<<"$v"; then\nlog_error x\nfi\n')),
        0,
    )
    ctl.check(
        "PLANT: the FUNCTION BOUNDARY stops the window, so the next function's "
        "log_error does not answer for this capture",
        len(rows('f() {\nv=$(probe || true)\n}\ng() {\nlog_error "unrelated"\n}\n')),
        1,
    )

    # -- the waiver ---------------------------------------------------------
    waived = rows(
        "# swallowed-failure-ok: the empty case genuinely means the same thing here, "
        "see the note above\nv=$(probe || true)\n"
    )
    ctl.check("CONTROL: a waived capture is a WAIVER row, not a FINDING", waived[0].kind, "WAIVER")
    ctl.check(
        "PLANT: a waiver one line too high does not cover the capture",
        rows("# swallowed-failure-ok: reason\n# an intervening comment\nv=$(probe || true)\n")[
            0
        ].kind,
        "FINDING",
    )

    # -- the BLOCKER bar on waiver reasons ---------------------------------
    ctl.truthy(
        "CONTROL: a substantive waiver reason clears the bar",
        validate_blocker_quality("x", "the empty case genuinely means the same thing here", "f"),
    )
    ctl.falsy(
        "PLANT: a banned filler phrase is rejected",
        validate_blocker_quality("x", "todo", "f"),
    )
    ctl.falsy(
        "PLANT: a reason under 30 characters is rejected",
        validate_blocker_quality("x", "it is fine really", "f"),
    )
    ctl.falsy(
        "PLANT: a routine-bump deferral substring is rejected",
        validate_blocker_quality(
            "x", "not needed by this change and we can revisit it another time", "f"
        ),
    )

    # -- capture_var --------------------------------------------------------
    ctl.check("CONTROL: capture_var reads a plain name", capture_var("v=$(probe || true)"), "v")
    ctl.check(
        "CONTROL: capture_var strips a `local` qualifier",
        capture_var("local v=$(probe || true)"),
        "v",
    )
    ctl.check("MIRROR: a line with no assignment yields no name", capture_var("echo $(probe)"), "")

    # -- the whole gate, over a fixture tree -------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        scan = root / ".ci" / "scripts" / "quality"
        scan.mkdir(parents=True)

        def run() -> int:
            saved_root = os.environ.get(ROOT_ENV)
            saved_dirs = os.environ.get(DIRS_ENV)
            os.environ[ROOT_ENV] = str(root)
            os.environ[DIRS_ENV] = ".ci/scripts/quality"
            try:
                return main([])
            finally:
                for name, value in ((ROOT_ENV, saved_root), (DIRS_ENV, saved_dirs)):
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

        (scan / "clean.sh").write_text(
            'v=$(probe || echo unavailable)\nif [[ -z "$v" ]]; then\nlog_error "x"\nfi\n',
            encoding="utf-8",
        )
        ctl.check("CONTROL: a clean corpus exits 0", run(), 0)
        (scan / "dirty.sh").write_text("v=$(probe || true)\necho done\n", encoding="utf-8")
        ctl.check("PLANT: one swallowed capture exits 1", run(), 1)

    with tempfile.TemporaryDirectory() as tmp:
        empty_root = pathlib.Path(tmp)

        def run_empty() -> int:
            saved_root = os.environ.get(ROOT_ENV)
            saved_dirs = os.environ.get(DIRS_ENV)
            os.environ[ROOT_ENV] = str(empty_root)
            os.environ[DIRS_ENV] = "nowhere"
            try:
                return main([])
            finally:
                for name, value in ((ROOT_ENV, saved_root), (DIRS_ENV, saved_dirs)):
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

        ctl.check(
            "VACUITY: a corpus that collapsed to zero files is REFUSED, never passed",
            run_empty(),
            1,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
