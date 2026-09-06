r"""The Claude-review turn budget cannot starve a review it is willing to route.

Ported from `.ci/scripts/quality/check-review-turn-capacity.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THIS EXISTS, in the twin's own words, because the incident IS the design:

    On 2026-08-07 the review of PR #553 died with `error_max_turns` and posted
    ZERO findings, then recorded a SPENT ATTEMPT -- burning a finite allowance
    while claiming nothing about the code. Two samples from that day, same
    reviewer, same tier:

        PR #552  2270 lines / 39 files  -> completed, full report
        PR #553  2802 lines / 36 files  -> starved, nothing posted

    The 50-turn tier stretched to 5000 lines, so a 4999-line diff was routed with
    10 turns per 1000 lines while a 2270-line diff got 22. Nothing noticed,
    because every existing gate checked that the tiers EXIST and that routing
    PICKS one, never that the picked budget is survivable. That is the blind spot
    this gate closes: capacity, not routing.

    WHAT IT CANNOT DO, stated plainly. Whether N turns actually suffices for a
    given diff is empirical and model-dependent; no static check can know it. So
    this asserts the four structural properties that made the incident possible,
    and pins the one measured fact:

      1. MONOTONIC   -- a larger diff never receives fewer turns than a smaller
                        one.
      2. TOTAL       -- every routable size yields a positive budget (no gap, no
                        zero).
      3. DENSITY     -- up to the largest size at which the floor is ACHIEVABLE
                        within the budget's own ceiling, every size must clear
                        MIN_TURNS_PER_KLOC.
      4. CEILING     -- past that point the floor is arithmetically impossible,
                        so it is not demanded; instead the budget must BE the
                        ceiling. This is the half that catches a huge diff
                        quietly routed to less than the most the system is
                        willing to spend. The ceiling is read from the function's
                        own behaviour, so changing MAX_TURNS moves the split
                        automatically rather than silently widening the
                        exemption.
      5. REGRESSION  -- the measured failure point stays fixed: a 2802-line diff
                        must receive strictly more than the 50 turns that starved
                        it.

    Properties 3 and 4 exist as a pair because the first fix for this incident was
    WRONG in a way property 3 alone would have missed: replacing the 5000-line
    rung with a 2000-line one left a 2000..29999 tier whose top edge got 2.6
    turns/KLOC, the same hole, fifteen times wider. Rungs starve at their top by
    construction, which is why the budget is now a continuous function and this
    gate probes sizes rather than thresholds.

    CONTROL-FIRST. The gate mutates the real function (collapsing turns-per-KLOC
    to a value that cannot sustain any diff) and requires its own assertions to
    FAIL against that mutant. If the planted defect passes, the gate reports
    ITSELF broken and exits non-zero, so a green run means the checks can fire,
    not merely that nothing tripped them.

THE FLOOR IS ANCHORED TO MEASUREMENT, NOT TASTE, and the twin says how:

    2802 lines starved at 50 turns (17.8/KLOC) and 2270 survived at 50
    (22.0/KLOC), so the floor sits between them, nearer the survivor. Raising it
    is safe; lowering it below 17.8 would re-admit the exact diff that failed.

THE EXTRACTION IS BY ANCHOR ON PURPOSE: "so a rename or rewrite breaks THIS gate
loudly instead of silently leaving it testing a stale copy pasted in here." That
is the whole reason the gate reads the real file rather than carrying its own
copy of the budget function.

THE `|| true` INSIDE `turns_for` IS LOAD-BEARING, and the twin records why:

    grep exits 1 when the function emitted no review_turns at all, and that must
    reach the caller as an EMPTY result -- which turns_for maps to 0 and the TOTAL
    property then reports loudly. Letting the pipeline abort here would hide "the
    function produced nothing" behind a dead subshell, i.e. the exact
    silent-failure shape this gate exists to catch, inside the gate itself.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE PORT STILL RUNS BASH, AND THAT IS THE POINT. `emit_review_turns` is a bash
function in a bash file; the gate's claim is about what THAT function does, not
about a Python re-derivation of its arithmetic. Re-implementing the budget here
would produce a gate that agrees with itself and says nothing about the file it
names. So the port assembles the same harness the twin assembles -- `gh` stubbed
to echo a size, `log_info` silenced, `GITHUB_OUTPUT` a temporary file -- and runs
the extracted text.

COLOUR IS UNCONDITIONAL IN THIS GATE, exactly as in the twin, which assigns
`RED=$'\033[0;31m'` with no tty test and never sources `common.sh`. Using
`rediacc_ci.log` would decide colour by `isatty` and change the bytes on every
non-tty run, so the port prints raw with the twin's own sequences. Reported as an
inconsistency in the twin rather than repaired here.

`printf '  %s\n' "$REAL_OUT"` INDENTS ONLY THE FIRST LINE. A single multi-line
argument is one `%s`, so the second and later findings come out flush left. That
reads as a bug and is carried, because the differential compares finding text and
"fixing" it here would be a behaviour change wearing a tidy-up's clothes.

INTEGER DIVISION IS FLOOR DIVISION ON BOTH SIDES. Bash `$((a / b))` truncates
toward zero and every operand here is non-negative, so Python's `//` agrees. The
density figure is therefore the same integer on both sides, including at the
boundary where a rounding difference would move one probe size across the floor.

THE 2>/dev/null ON THE INNER bash IS PRESERVED as a discarded stderr. Without it
a stubbed-out `gh` writing to stderr, or a syntax error in a rewritten function,
would leak into the gate's own output and be scored as a finding by anything
parsing it.
"""

import os
import re
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The twin's escape sequences, verbatim and unconditional. See the port notes.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# The file whose function is the subject. Spelled as the twin spells it, because
# the spelling lands in every refusal message.
GATE_SRC_REL = ".ci/scripts/review/claude-review-gate.sh"

# The measured starvation point and the budget that failed it. Both are facts
# about PR #553 on 2026-08-07, not tuning knobs.
STARVED_LINES = 2802
STARVED_TURNS = 50

# Default worst-case density a bounded tier must clear. Overridable, as in the
# twin, so a future measurement can raise it without editing the file.
MIN_TURNS_PER_KLOC_ENV = "MIN_TURNS_PER_KLOC"
DEFAULT_MIN_TURNS_PER_KLOC = 22

# "Deliberately includes every boundary neighbourhood plus the two measured PRs,
# so a moved threshold cannot slip between samples."
PROBE_SIZES = (
    0,
    1,
    500,
    1999,
    2000,
    2001,
    2269,
    2270,
    2802,
    4999,
    5000,
    5001,
    9999,
    29999,
    30000,
    30001,
    100000,
)

# `awk '/^emit_review_turns\(\) \{/,/^\}/'`: an inclusive line range from the
# opening line to the first line that is exactly `}` at column 0.
FN_OPEN = re.compile(r"^emit_review_turns\(\) \{")
FN_CLOSE = re.compile(r"^\}")

# The mutant the control plants: "Restores the pre-incident shape (the 2000 rung
# pushed back out to 5000)." A global replacement, as `${FN//a/b}` is.
MUTANT_FROM = "per_kloc=25"
MUTANT_TO = "per_kloc=8"

# `[[ ! "$turns" =~ ^[0-9]+$ ]]`.
NUMERIC = re.compile(r"^[0-9]+$")


def extract_function(text: str) -> str:
    """The `emit_review_turns` body, by anchors, exactly as awk ranges it.

    RETURNS THE EMPTY STRING when the anchors do not match, which is what makes
    the twin's "renamed? rewritten?" refusal reachable. An exception here would
    turn a rename into a stack trace, and a stack trace reads as flake rather
    than as the loud breakage the anchor exists to produce.
    """
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if not inside:
            if FN_OPEN.search(line):
                inside = True
                out.append(line)
            continue
        out.append(line)
        if FN_CLOSE.search(line):
            break
    # awk prints each selected line followed by a newline; `$(...)` then strips
    # the trailing newlines. The join reproduces both steps.
    return "\n".join(out)


def harness(fn: str) -> str:
    """The bash program `turns_for` runs, with `fn` spliced in.

    EVERY STUB HERE IS LOAD-BEARING. `gh` must be a FUNCTION rather than a script
    on PATH, so the real `gh` cannot be reached even if it is installed and
    authenticated; `log_info` must exist because the subject calls it and an
    unbound command would take the whole probe down; `GITHUB_OUTPUT` must be a
    real file because the subject appends to it and reads nothing back.
    """
    return (
        "GITHUB_OUTPUT=$(mktemp); GITHUB_REPOSITORY=x/y\n"
        "log_info() { :; }\n"
        'gh() { echo "$FAKE_SIZE"; }\n'
        "%s\n"
        "emit_review_turns 1\n"
        # `|| true`: see the module docstring. An empty result must reach the
        # caller as empty, where TOTAL reports it, rather than aborting here.
        'grep -o "review_turns=[0-9]*" "$GITHUB_OUTPUT" | head -1 | cut -d= -f2 || true\n'
        'rm -f "$GITHUB_OUTPUT"\n'
    ) % fn


def turns_for(size: int, fn: str) -> str:
    """Run the REAL function with `gh` stubbed to report `size` lines changed.

    Returns the budget as the STRING the twin's command substitution produces, or
    `"0"` when nothing came back. A string rather than an int because TOTAL's
    message quotes the raw value (`routed to a non-positive budget ('$turns')`),
    and a port that parsed early would have to invent a spelling for the
    unparseable case.
    """
    env = dict(os.environ)
    env["FAKE_SIZE"] = str(size)
    try:
        proc = subprocess.run(
            ["bash", "-c", harness(fn)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return "0"
    # `$(...)` strips trailing newlines; `${out:-0}` supplies the default.
    return proc.stdout.strip("\n") or "0"


def evaluate(fn: str, min_per_kloc: int) -> list[str]:
    """Every property violation, one message per line. Empty means all four hold.

    RETURNS A LIST, NOT AN EXIT STATUS. The twin prints to stdout and the caller
    tests emptiness; a list cannot be truncated by a shell taking a count mod 256
    and it is directly assertable from a test.
    """
    findings: list[str] = []
    prev_size = -1
    prev_turns = 0
    for size in PROBE_SIZES:
        turns = turns_for(size, fn)
        # 2. TOTAL
        if not NUMERIC.match(turns) or int(turns) <= 0:
            findings.append("TOTAL: size %d routed to a non-positive budget ('%s')" % (size, turns))
            continue
        value = int(turns)
        # 1. MONOTONIC
        if prev_size >= 0 and value < prev_turns:
            findings.append(
                "MONOTONIC: size %d got %d turns, fewer than size %d which got %d"
                % (size, value, prev_size, prev_turns)
            )
        prev_size = size
        prev_turns = value

    # 4. REGRESSION -- the measured starvation point must be strictly better
    # resourced now. Numbered 4 in the twin's code and 5 in its header; the
    # discrepancy is carried rather than silently renumbered, because the header
    # is what a reader quotes.
    turns = turns_for(STARVED_LINES, fn)
    if NUMERIC.match(turns) and int(turns) <= STARVED_TURNS:
        findings.append(
            "REGRESSION: %d lines still routes to %s turns; %d is the budget that starved "
            "PR #553" % (STARVED_LINES, turns, STARVED_TURNS)
        )
    elif not NUMERIC.match(turns):
        # `[[ "$turns" -le "$STARVED_TURNS" ]]` on a non-numeric value is a bash
        # ARITHMETIC context, which evaluates an unset name as 0 and therefore
        # takes the branch. Reproduced rather than corrected.
        findings.append(
            "REGRESSION: %d lines still routes to %s turns; %d is the budget that starved "
            "PR #553" % (STARVED_LINES, turns, STARVED_TURNS)
        )

    # 3. DENSITY, split honestly at the point where the cost ceiling makes it
    # impossible. The ceiling is DERIVED from the function's own largest observed
    # budget, never hard-coded, "so raising or lowering MAX_TURNS moves the split
    # automatically".
    ceiling = 0
    for size in PROBE_SIZES:
        turns = turns_for(size, fn)
        if NUMERIC.match(turns) and int(turns) > ceiling:
            ceiling = int(turns)
    density_max_lines = ceiling * 1000 // min_per_kloc
    for size in PROBE_SIZES:
        if size < 1000:
            continue  # density is meaningless sub-KLOC
        turns = turns_for(size, fn)
        value = int(turns) if NUMERIC.match(turns) else 0
        if size <= density_max_lines:
            dens = value * 1000 // size
            if dens < min_per_kloc:
                findings.append(
                    "DENSITY: %d lines gives %s turns = %d/KLOC, under the %d/KLOC floor "
                    "(achievable here: the ceiling is %d)"
                    % (size, turns, dens, min_per_kloc, ceiling)
                )
        elif value < ceiling:
            findings.append(
                "CEILING: %d lines is past the density-achievable range (%d lines) yet gets "
                "only %s turns, below the %d the budget is willing to spend"
                % (size, density_max_lines, turns, ceiling)
            )
    return findings


def fail(message: str) -> int:
    """The twin's `fail`: one red line on stderr, status 1."""
    print("%s✗%s %s" % (RED, NC, message), file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when all four properties hold, 1 otherwise.

    `--selftest` is intercepted BEFORE the subject file is even read, so a tree
    whose review gate has been renamed can still prove this file's own logic.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    gate_src = root / GATE_SRC_REL
    min_per_kloc = int(os.environ.get(MIN_TURNS_PER_KLOC_ENV) or DEFAULT_MIN_TURNS_PER_KLOC)

    if not gate_src.is_file():
        return fail(
            "check-review-turn-capacity: %s not found; the gate cannot judge a function it "
            "cannot read" % gate_src
        )

    fn = extract_function(gate_src.read_text(encoding="utf-8", errors="replace"))
    if not fn:
        return fail(
            "check-review-turn-capacity: could not extract emit_review_turns() from %s "
            "(renamed? rewritten?). Refusing to pass while measuring nothing." % gate_src
        )
    if "review_turns=" not in fn:
        return fail(
            "check-review-turn-capacity: extracted emit_review_turns() never assigns "
            "review_turns; the extraction is wrong"
        )

    # ---- the control: a planted defect MUST be caught -----------------------
    mutant = fn.replace(MUTANT_FROM, MUTANT_TO)
    if mutant == fn:
        return fail(
            "check-review-turn-capacity: the control could not plant its defect (no "
            "'per_kloc=25' in emit_review_turns -- the budget was rewritten). Update the "
            "mutant in this gate to match the new shape. Refusing to report a green that "
            "proves nothing."
        )
    control_out = evaluate(mutant, min_per_kloc)
    if not control_out:
        return fail(
            "check-review-turn-capacity: CONTROL DID NOT FIRE. The pre-incident tiering "
            "passed every property, so this gate cannot detect the defect it exists for."
        )

    # ---- the real run -------------------------------------------------------
    real_out = evaluate(fn, min_per_kloc)
    if real_out:
        print(
            "%s✗%s review turn budget can starve a review it routes:" % (RED, NC), file=sys.stderr
        )
        # ONLY THE FIRST LINE IS INDENTED, because the twin passes one multi-line
        # argument to a single `%s`. See the port notes.
        print("  %s" % "\n".join(real_out), file=sys.stderr)
        print(file=sys.stderr)
        print(
            "  Fix emit_review_turns() in .ci/scripts/review/claude-review-gate.sh.",
            file=sys.stderr,
        )
        print(
            "  A starved review burns its whole budget, posts nothing, and still spends an",
            file=sys.stderr,
        )
        print(
            "  attempt against a finite allowance -- it is the expensive outcome, not the "
            "cheap one.",
            file=sys.stderr,
        )
        return 1

    print(
        "%s✓%s review turn budget: %d sizes monotonic and total; %d+ turns/KLOC wherever "
        "that is achievable, and the full ceiling beyond"
        % (GREEN, NC, len(PROBE_SIZES), min_per_kloc)
    )
    print(
        "  control fired on the pre-incident tiering (%d finding(s)), so this green means "
        "the checks can fail" % len(control_out)
    )
    return 0


# A budget function written here rather than read, for the selftest ONLY. It is
# never used against the real tree: the whole argument of this gate is that it
# must read the file it names, and a copy pasted into the gate is exactly what
# the anchor-based extraction exists to prevent. This one is a FIXTURE, and it is
# labelled as such so a future reader does not mistake it for a second source of
# truth.
_FIXTURE_HEALTHY = """emit_review_turns() {
    local changed
    changed=$(gh) || changed=0
    local per_kloc=25 max_turns=140 min_turns=50
    local kloc=$(((${changed:-0} + 999) / 1000))
    local turns=$((kloc * per_kloc))
    [[ "$turns" -lt "$min_turns" ]] && turns="$min_turns"
    [[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"
    echo "review_turns=$turns" >>"$GITHUB_OUTPUT"
    log_info "x"
}"""


def selftest() -> int:
    """Both directions on the extraction and on all four properties.

    THE FLOOR IS DERIVED, not typed: it counts the cases below, so a case that
    stops running turns the suite red rather than quietly shortening it.
    """
    extraction = [
        ("the whole body, anchors included", _FIXTURE_HEALTHY, True),
        (
            "a renamed function extracts nothing",
            _FIXTURE_HEALTHY.replace("emit_review_turns", "emit_turns"),
            False,
        ),
        ("an empty file extracts nothing", "", False),
        (
            "text before and after the function is excluded",
            "before\n%s\nafter\n" % _FIXTURE_HEALTHY,
            True,
        ),
    ]
    # (label, function text, must produce findings)
    properties = [
        # THE NEGATIVE HALF. A healthy continuous budget must be SILENT, or the
        # gate is a blanket refusal and its red says nothing.
        ("a healthy continuous budget passes every property", _FIXTURE_HEALTHY, False),
        # THE POSITIVE HALF, and it is the founding defect: the pre-incident
        # density.
        (
            "the pre-incident density is caught",
            _FIXTURE_HEALTHY.replace("per_kloc=25", "per_kloc=8"),
            True,
        ),
        (
            "a budget that emits nothing is caught by TOTAL",
            _FIXTURE_HEALTHY.replace('echo "review_turns=$turns" >>"$GITHUB_OUTPUT"', ":"),
            True,
        ),
        (
            "a budget that shrinks with size is caught by MONOTONIC",
            _FIXTURE_HEALTHY.replace(
                "local turns=$((kloc * per_kloc))", "local turns=$((200 - kloc))"
            ),
            True,
        ),
        (
            "a budget that never reaches its own ceiling is caught by CEILING",
            _FIXTURE_HEALTHY.replace("max_turns=140", "max_turns=140").replace(
                '[[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"',
                '[[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"\n'
                '    [[ "${changed:-0}" -gt 29999 ]] && turns=60',
            ),
            True,
        ),
    ]

    floor = len(extraction) + len(properties) + 3
    ctl = Controls("review-turn-capacity", floor=floor)

    for label, text, want in extraction:
        ctl.check("extract: %s" % label, bool(extract_function(text)), want)
    for label, text, want in properties:
        ctl.check("evaluate: %s" % label, bool(evaluate(text, DEFAULT_MIN_TURNS_PER_KLOC)), want)

    # THE MUTANT MUST BE A REAL MUTATION. A control that plants nothing is the
    # failure this gate's own refusal message names, so it is asserted here too.
    ctl.check(
        "the control's mutation actually changes the text",
        _FIXTURE_HEALTHY.replace(MUTANT_FROM, MUTANT_TO) != _FIXTURE_HEALTHY,
        True,
    )
    # THE MEASURED FACTS ARE NOT TUNING KNOBS.
    ctl.check("the starvation point is PR #553's diff size", STARVED_LINES, 2802)
    ctl.check("the starving budget is 50 turns", STARVED_TURNS, 50)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
