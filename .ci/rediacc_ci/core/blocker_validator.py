"""The BLOCKER convention transport, ported from `.ci/scripts/lib/blocker-validator.sh`.

PORTED FROM `.ci/scripts/lib/blocker-validator.sh` (356 lines), which still exists, is untouched by this file, and has EIGHT real sourcers re-measured on 2026-09-10 (`grep -rnP '^\\s*(source|\\.)\\s+.*blocker-validator\\.sh'`): `.ci/scripts/quality/check-ci-job-aggregation.sh:52`, `.ci/scripts/quality/check-go-deps.sh:37`, `.ci/scripts/quality/check-profiler-coverage.sh:85`,
`.ci/scripts/quality/check-swallowed-failures.sh:86`, `.ci/scripts/security/audit.sh:36`, `.ci/scripts/test/gates/test-blocker-validator.sh:26`, `.ci/scripts/test/gates/test-emit-advisory.sh:141` and `:168` (one file, two heredoc-driven subshells), and `.ci/rediacc_ci/tests/test_core_allowlist.py:155` and `:183`, which drive the real library from bash snippets. This module does NOT
shim any of them: deletion and cutover are a later box, both implementations are live, and `.ci/rediacc_ci/tests/test_core_blocker_validator.py` is what says they agree.

WHAT THIS FILE IS NOT. It is not a second copy of the BLOCKER rule. The twin stopped being an implementation on 2026-09-09: its grammar, its two banned-phrase tables, its 30-character floor and all four message bodies live in `rediacc_ci.core.allowlist`, and `parse_blockered_list` / `verify_all_blockers` there are TRANSPORTS that decide nothing. This is the Python transport over
the same canonical module, so the hop the twin pays (bash -> python3 -m ... -> bash) collapses to a function call, and nothing about the verdict moves.

--------------------------------------------------------------------------
WHY THE PHRASE ARRAYS DO NOT CROSS OVER, WHICH IS NOT AN OVERSIGHT
--------------------------------------------------------------------------
The twin still carries `LOW_EFFORT_BLOCKER_PATTERNS` and `LOW_EFFORT_BLOCKER_SUBSTRINGS` as a TEXT MIRROR, because `.ci/scripts/test/gates/test-breakpoint-portability.sh:361` parses them out of THAT FILE'S TEXT to prove the vendored breakpoint copy is a subset. That justification is specific to the bash file and does not travel: a Python mirror would be read by nothing, and
`.ci/rediacc_ci/tests/test_blocker_implementations.py:207` fails BY NAME on any tracked file that carries ten or more of the canonical phrases as quoted literals. So the constants below are REFERENCES to `rediacc_ci.core.allowlist`, never copies, and `BLOCKER_MIN_LENGTH` is `allowlist.MIN_REASON_LENGTH` rather than the literal 30 the twin writes.

--------------------------------------------------------------------------
WHAT THE THREE PRECONDITION GUARDS BECOME
--------------------------------------------------------------------------
The twin opens with three refusals, and none of them has a counterpart here BY CONSTRUCTION rather than by choice. Said out loud so a reader does not read the absence as a dropped control:

  * `blocker-validator.sh:69-76`, bash 4.3. The `local -n` namerefs are what
    needs it; this module returns tables instead of aliasing the caller's
    variables, so there is no version to check.
  * `blocker-validator.sh:89-93`, "cannot find rediacc_ci under ...". A missing
    package here is an ImportError at import time, which is louder than the
    twin's `return 1` and cannot be mistaken for an empty allowlist. The
    `REDIACC_CI_ROOT` override the twin honours is `rediacc_ci.paths`' first
    rung and is honoured by every path this module resolves.
  * `blocker-validator.sh:94-98`, `command -v python3`. Self-evidently satisfied.

--------------------------------------------------------------------------
FOUR BEHAVIOURS OF THE TWIN REPRODUCED RATHER THAN TIDIED
--------------------------------------------------------------------------
  1. A MISSING FILE IS AN EMPTY TABLE AND EXIT 0 (`blocker-validator.sh:202`).
     The canonical module refuses that by default and calls it `missing_ok`; the
     permissiveness is five gates' historical contract, so it is spelled out at
     the call site in `parse_blockered_list` below, where a reviewer sees it. The
     test `[[ ! -f "$file" ]]` is true for a DIRECTORY as well as for an absent
     path, so `pathlib.Path.is_file()` is the right transliteration and a
     directory argument likewise yields empty tables and success.

  2. THE COUNTED RS FRAME (`blocker-validator.sh:106`, `:245-271`) survives the
     process boundary's removal. In-process there is nothing to frame, and the
     obvious port drops the protocol entirely; that would delete a live control,
     because the frame is a COUNT precisely so a BLOCKER reason cannot forge a
     sentinel and hide one rejection inside another's message. `verify_all_blockers`
     therefore still renders through `frame()` and still reads back through
     `replay_frames()`, which is the twin's own data flow with the fork removed.
     `frame()` is asserted equal to what `python3 -m rediacc_ci.core.allowlist
     verify-rows` really writes, so the two writers cannot drift.

  3. `_blocker_emit`'s ZERO-FRAME REFUSAL IS DEAD CODE IN THE TWIN, measured
     2026-09-10 on bash 5.3.9, and it is reproduced as dead code here rather
     than promoted into a reachable guard.

         $ bash -c 'f=0; while IFS= read -r l; do f=$((f+1)); done <<<""; echo $f'
         1

     A bash here-string always appends a newline, so `<<<"$stream"` yields at
     least ONE line even for the empty string. That line is not RS-prefixed, so
     `blocker-validator.sh:249-251` returns 1 with "unframed output from
     rediacc_ci.core.allowlist: " and an empty tail, and the `frames == 0` arm at
     `:266-269` ("reported a failure but emitted no message") can never be
     reached. `replay_frames("")` below produces the same unframed-output
     refusal, which is what the differential compares; the zero-frame message is
     kept, unreachable, so the two files still say the same words if a future
     change makes it reachable on either side.

  4. THE ITERATION ORDER IS THE TABLE'S, AND THE TWO TABLES ARE NOT THE SAME
     TABLE. `verify_all_blockers` hands rows over in `"${!_blocker_ref[@]}"`
     order, which is a bash hash order, while a Python dict is insertion order.
     Neither is sorted, both are stable within one implementation, and NEITHER
     IS PART OF THE CONTRACT: the twin's own comment at `:313-316` claims only
     that the rows come back in the order they were handed over. So a table with
     two bad entries prints the same two messages in a possibly different order,
     which is why the differential compares multisets for the multi-failure
     cases and exact bytes for the single-failure ones.

--------------------------------------------------------------------------
THE ONE PLACE THE TWIN'S TRANSPORT IS LOSSY, AND WHY IT COSTS NOTHING
--------------------------------------------------------------------------
`blocker-validator.sh:214` reads the canonical `pairs` output with
`IFS=$'\\t' read -r key value`, and TAB IS IFS WHITESPACE in bash, so consecutive
tabs collapse and leading and trailing tabs are stripped. Measured 2026-09-10:

    $ printf 'a\\t\\tb\\tc\\t\\n' | { IFS=$'\\t' read -r k v; printf '[%s][%s]' "$k" "$v"; }
    [a][b<TAB>c]

The comment at `:211-213` claims "everything after the first one is the reason, tabs and all", which is not what bash does. It costs nothing TODAY only because `allowlist.parse_text` `.strip()`s every reason, so no reason can begin or end
with a tab, and an interior tab run inside the remainder IS preserved (measured:
`x\\ta\\t\\tb` gives value `a\\t\\tb`). The port holds the reason verbatim, which agrees with the twin on every reason the canonical grammar can produce and disagrees only on reasons it cannot. Recorded because the claim in the twin is wrong even where the consequence is nil.
"""

import pathlib
import sys
from typing import NamedTuple

from rediacc_ci.core import advisory, allowlist

# `readonly BLOCKER_VALIDATOR_RS=$'\x1e'` (blocker-validator.sh:106). ASCII 30,
# RECORD SEPARATOR. A counted frame rather than a sentinel line, because a sentinel can be forged by a BLOCKER reason and a count cannot.
BLOCKER_VALIDATOR_RS = "\x1e"

# `readonly BLOCKER_MIN_LENGTH=30` (blocker-validator.sh:167), as a REFERENCE.
# The twin writes the literal because bash cannot import; this must not, or the
# floor would exist twice and could drift once.
BLOCKER_MIN_LENGTH = allowlist.MIN_REASON_LENGTH

USAGE = """blocker_validator -- the `blocker-validator.sh` transport verbs.

  pairs   <file> [comment_char]        the two tables, one `allowed`/`blocker`
                                       row each, sorted, TAB separated
  verify  <file> [comment_char]        parse then verify_all_blockers; exit 1
                                       when any entry lacks or fails a BLOCKER
  reason  <entry> <reason> <file>      validate one reason; exit 1 if low effort
  replay  <framed-file>                replay an RS-framed failure stream
"""


class Tables(NamedTuple):
    """What `parse_blockered_list`'s two namerefs hold when it returns.

    Two dicts and not one, because the twin populates two arrays and five gates read them independently: `allowed` answers "is this entry suppressed at all"
    and is what `audit.sh` tests with `[[ -n "${ALLOWED[$id]:-}" ]]`, while
    `blocker` answers "with what reason", and an entry with NO reason is present in both, mapped to 1 and to the empty string respectively. Collapsing them into one dict would make "absent" and "present with no reason" the same lookup, which is exactly the distinction `verify_all_blockers` fails on.
    """

    allowed: dict[str, int]
    blocker: dict[str, str]


class BrokenReaderError(RuntimeError):
    """The canonical reader could not parse a list that exists.

    `blocker-validator.sh:205-209` prints two lines and returns 1 here, and every bash caller invokes `parse_blockered_list` bare, so under the `errexit` those gates run with the script dies. Raising is the same contract: a caller that wants the twin's non-errexit behaviour (carry on with empty tables) catches it, and has to write that down to get it.

    THIS IS NOT THE MISSING-FILE CASE. A missing file is empty tables and
    success, on purpose; see behaviour 1 in the module docstring.
    """


def parse_blockered_list(file: str | pathlib.Path, comment_char: str = "#") -> Tables:
    """`parse_blockered_list <file> <allowed_var> <blocker_var> [<comment_char>]`.

    Returns the two tables instead of writing through namerefs, which is the one capability the port loses and the one class of caller error it removes: the twin's `local -n` is bash 4.3, and on 3.2 it fails with `local: -n: invalid option`, RETURNS ZERO, and every allowlist parses to zero entries while the gate exits 0 (`blocker-validator.sh:40-64`, measured on a real bash 3.2.0).

    A MISSING FILE RETURNS EMPTY TABLES AND SUCCESS. That is the twin's
    historical contract, `missing_ok=True` in the canonical module's vocabulary,
    and it is written here rather than inherited so it shows up in a diff.
    """
    path = pathlib.Path(file)
    # `[[ ! -f "$file" ]] && return 0` (blocker-validator.sh:202). True for an absent path AND for a directory, and `is_file()` is true for exactly the same set.
    if not path.is_file():
        return Tables({}, {})

    try:
        entries = allowlist.parse_file(path, comment_char)
    except (OSError, UnicodeDecodeError) as exc:
        # `blocker-validator.sh:205-209`. The twin sees a non-zero exit from the
        # canonical module; here the same failures (unreadable file, undecodable
        # bytes) arrive as exceptions. The words are the twin's.
        advisory.ci_error(
            "blocker-validator: rediacc_ci.core.allowlist could not parse %s (%s)"
            % (path, type(exc).__name__)
        )
        print(
            "  This is a broken reader, not an empty allowlist. Refusing to report zero entries.",
            file=sys.stderr,
        )
        raise BrokenReaderError(str(exc)) from exc

    # The `pairs` projection, which is what an associative array can hold: deduplicated entry -> reason, LAST write wins. Identical to the rows the twin reads off the canonical module's stdout, minus the TAB round trip.
    pairs = allowlist.pairs(entries)
    return Tables(dict.fromkeys(pairs, 1), dict(pairs))


def emit_message(message: str, *, out=None) -> None:
    """`_blocker_emit_message` (blocker-validator.sh:227-237).

    The stream split, which is the only part of the message contract that stayed in bash on that side and is the only part that has to be re-decided here: the FIRST line through `ci_error`, which is what turns it into a GitHub annotation under CI, the rest as a plain `echo` to stdout.

    Note what that means and reproduce it exactly: under `CI=true` the head line
    lands on STDOUT as `::error::...` and off CI on STDERR as `x ...`, while the continuation lines are on stdout either way. Three renderings in one failure, and `.ci/rediacc_ci/quality/profiler_coverage.py:988` records the same split after a cutover differential found a port that had lost it.
    """
    first = True
    # `while IFS= read -r line; do ... done <<<"$1"`. A here-string appends a
    # newline, so a trailing newline in the message does NOT produce an extra
    # empty line; splitting on "\n" and dropping one trailing empty is the same
    # set of lines.
    lines = message.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line in lines:
        if first:
            advisory.ci_error(line)
            first = False
        else:
            print(line, file=out)


def frame(messages: list[str]) -> str:
    """The RS writer: `\\x1e<line-count>` then exactly that many lines.

    A TRANSCRIPTION OF `rediacc_ci.core.allowlist.main`'s `verify-rows` writer, not a second protocol, and the reason it is transcribed rather than called is that the canonical writer is welded to `sys.stdin` and `sys.stdout` inside a CLI verb. `test_core_blocker_validator.py` runs the real `python3 -m rediacc_ci.core.allowlist verify-rows` and asserts its bytes equal this
    function's, so the two cannot drift without a red test.
    """
    out = []
    for message in messages:
        lines = message.split("\n")
        out.append("%s%d\n" % (BLOCKER_VALIDATOR_RS, len(lines)))
        out.append("".join(line + "\n" for line in lines))
    return "".join(out)


def replay_frames(stream: str, *, out=None) -> bool:
    """`_blocker_emit` (blocker-validator.sh:245-271). False on an unframed stream.

    Reads exactly `count` lines per frame, so a BLOCKER reason that contains a line starting with RS cannot open a frame of its own.
    """
    # `done <<<"$stream"`: the here-string's appended newline is why an EMPTY stream still yields one (empty, unframed) line. See behaviour 3 in the
    # module docstring; this is the line that makes the zero-frame arm below
    # unreachable, exactly as in the twin.
    lines = stream.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        lines = [""]

    index = 0
    frames = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.startswith(BLOCKER_VALIDATOR_RS):
            advisory.ci_error(
                "blocker-validator: unframed output from rediacc_ci.core.allowlist: %s" % line
            )
            return False
        count_text = line[len(BLOCKER_VALIDATOR_RS) :]
        # `((index < count))` on a non-numeric count is a bash arithmetic error on stderr and a FALSE comparison, so the frame renders as zero lines. Python has no such arithmetic-on-strings rule, so the same input has to be spelled: a count that is not a number counts as zero.
        try:
            count = int(count_text)
        except ValueError:
            count = 0
        frames += 1
        for offset in range(count):
            if index >= len(lines):
                break
            body = lines[index]
            index += 1
            if offset == 0:
                advisory.ci_error(body)
            else:
                print(body, file=out)
    if frames == 0:
        # UNREACHABLE, and kept. See behaviour 3 in the module docstring.
        advisory.ci_error(
            "blocker-validator: the canonical validator reported a failure but emitted no message"
        )
        return False
    return True


def validate_blocker_quality(entry: str, reason: str, file: str, *, out=None) -> bool:
    """`validate_blocker_quality <id> <reason> <file>`. True when acceptable.

    THE RULE AND THE WORDS ARE `allowlist.validate_reason`'s. The twin's third arm, `exit 2 is a usage error, not a verdict` (`blocker-validator.sh:284-290`), guards against a malformed CLI call and has
    no counterpart across a function call with three required arguments; a caller
    that gets the arity wrong gets a TypeError, which is the same refusal to fold a broken call into a finding about somebody's allowlist.

    UNFRAMED, and deliberately so. The single-reason answer is raw text; only the
    batch path frames, because only the batch path has more than one message to delimit. Feeding this to `replay_frames` was the twin's first cut's bug.
    """
    rejection = allowlist.validate_reason(entry, reason, file)
    if rejection is None:
        return True
    emit_message(rejection.message, out=out)
    return False


def verify_all_blockers(file: str, blocker: dict[str, str], *, out=None) -> bool:
    """`verify_all_blockers <file> <blocker_var>`. True when every entry passes.

    ONE pass over the whole table, not one per entry: the twin's first cut spawned an interpreter inside the loop and took `.ci/policy/.profiler-coverage-allowlist` (71 entries) from 0.06s to 3.4s. That cost is a bash cost and does not exist here, and the batch shape is kept anyway because it is what carries the RS frame, which is a control rather than an optimisation.

    AN EMPTY TABLE PASSES (`blocker-validator.sh:342`). That is not an anti-vacuity hole in this function: the caller decides whether an empty list is suspicious, and the twin's first cut of an emptiness guard HERE killed `.ci/scripts/security/audit.sh` on the spot, because `declare -A ALLOWED_DEV BLOCKER_DEV` at `audit.sh:52` has no initialiser and `.audit-allowlist` is empty.
    """
    rows = list(blocker.items())
    if not rows:
        return True

    failures: list[str] = []
    for entry, reason in rows:
        if not reason:
            failures.append(allowlist.missing_reason(entry, file))
            continue
        rejection = allowlist.validate_reason(entry, reason, file)
        if rejection is not None:
            failures.append(rejection.message)
    if not failures:
        return True

    replay_frames(frame(failures), out=out)
    return False


def main(argv: list[str]) -> int:
    if not argv or "--help" in argv or "-h" in argv:
        print(USAGE, file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]

    if verb == "pairs":
        if not rest:
            print("pairs needs a list path", file=sys.stderr)
            return 2
        comment_char = rest[1] if len(rest) > 1 and rest[1] else "#"
        try:
            tables = parse_blockered_list(rest[0], comment_char)
        except BrokenReaderError:
            return 1
        for key in sorted(tables.allowed):
            print("allowed\t%s\t%d" % (key, tables.allowed[key]))
        for key in sorted(tables.blocker):
            print("blocker\t%s\t%s" % (key, tables.blocker[key]))
        return 0

    if verb == "verify":
        if not rest:
            print("verify needs a list path", file=sys.stderr)
            return 2
        comment_char = rest[1] if len(rest) > 1 and rest[1] else "#"
        try:
            tables = parse_blockered_list(rest[0], comment_char)
        except BrokenReaderError:
            return 1
        return 0 if verify_all_blockers(rest[0], tables.blocker) else 1

    if verb == "reason":
        if len(rest) < 3:
            print("reason needs <entry> <reason> <file>", file=sys.stderr)
            return 2
        return 0 if validate_blocker_quality(rest[0], rest[1], rest[2]) else 1

    if verb == "replay":
        if not rest:
            print("replay needs a path holding an RS-framed stream", file=sys.stderr)
            return 2
        # `$(cat file)` is what a bash driver passes, and command substitution strips every trailing newline, so the reader is handed the same bytes on both sides.
        text = pathlib.Path(rest[0]).read_text(encoding="utf-8").rstrip("\n")
        return 0 if replay_frames(text) else 1

    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
