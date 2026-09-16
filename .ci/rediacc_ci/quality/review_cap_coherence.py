"""The two review scripts measure the SAME thing against the SAME cap.

Ported from `.ci/scripts/quality/check-review-cap-coherence.sh`, which is not
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THE TWIN EXISTS, carried over from its own header because the incident IS
the specification. On 2026-08-07 PR #553 became green, ready, thread-clean and
PERMANENTLY UNMERGEABLE. `review-status.sh` carries an explicit DEADLOCK GUARD
for exactly that outcome: when the cap is reached the marker can never advance,
so it passes loudly instead of failing. The guard never fired, because the two
scripts counted different numerators against the same cap:

    claude-review-gate.sh   posted + spent attempts  -> 3/3, refuses to review
    review-status.sh        posted reports only      -> 0/3, guard stays mute

Each script's own logic was self-consistent and locally correct. The defect
lived BETWEEN them, where no single-script check could see it, which is why this
gate compares the two rather than validating either.

`lib/common.sh` was created to stop precisely this drift, and it half-worked: it
shared the DENOMINATOR (`review_cap_for`) while the numerator stayed split
across two files, one of which did not know spent attempts existed. Sharing a
file is not the same as sharing the computation, so this gate checks the
computation.

WHAT IT ASSERTS, unchanged by the port:

    1. DRY-NUMERATOR    both scripts obtain the spend total from the shared
                        review_spend_total(), and neither re-sums it locally.
    2. DRY-DENOMINATOR  both obtain the cap from the shared review_cap_for().
    3. ONE-DEFINITION   the shared helpers exist in lib/common.sh and nowhere
                        else, so a "helpful" local copy cannot silently shadow
                        them.
    4. GUARD-REACHABLE  with numerator == cap, review-status's deadlock guard is
                        the branch that runs. This is the behavioural half:
                        1 to 3 could all hold while the guard was dead code.

CONTROL-FIRST, and this is the property a port is most likely to lose. Before
judging the tree the gate PLANTS the original defect (review-status counting
posted reports alone) and requires the assertions to FAIL on it. If the planted
defect passes, the gate declares ITSELF broken and exits non-zero. A green here
therefore means the checks CAN fire, not merely that nothing tripped them.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE BEHAVIOURAL HALF STAYS IN BASH, AND IT HAS TO. Assertion 4 extracts the
`currency_ok` branch out of `review-status.sh` by anchor and EXECUTES it, with
`review_count` and `MAX_REVIEWS_PER_PR` both pinned to 3, inside a wrapper that
stubs the loggers and inspects the two arrays afterwards. That branch is bash:
it appends to a bash array, calls bash functions and reads bash parameter
expansions. Reimplementing it in Python would mean reimplementing the thing
under test, which is the one rewrite a differential cannot catch. So the port
shells out to `bash -c` exactly as the twin does, with the same wrapper text.

`$g$s` IS CONCATENATED WITHOUT A SEPARATOR, AND THAT IS CARRIED. The
ONE-DEFINITION scan greps `<<<"$g$s"`, and `$(cat file)` has already stripped
the trailing newline from `$g`, so the last line of claude-review-gate.sh and
the FIRST line of review-status.sh are joined into one line. A helper redefined
on line 1 of review-status.sh would therefore be invisible to the `^` anchor.
It is a shebang there today, so nothing is missed in practice; the port
reproduces the join rather than quietly fixing it, and the defect is reported
instead. Fixing it would change the verdict, which is not a port's business.

`printf '  %s\\n' "$REAL_OUT"` INDENTS ONLY THE FIRST LINE. printf receives ONE
argument holding embedded newlines, so the two-space prefix is applied once and
every subsequent finding is flush left. That is the twin's output and the port
prints the same bytes. Also reported.

COLOUR IS UNCONDITIONAL IN THE TWIN. `RED=$'\\033[0;31m'` and its siblings are
assigned with no `[ -t 1 ]` test and no `NO_COLOR` check, so escape sequences
land in a pipe, in a file, and in the GitHub log viewer, which renders them as
literal text. `rediacc_ci.log` exists to make that impossible, and this port
deliberately does NOT use it: the differential compares output, and swapping in
a tty-aware logger would make the two sides disagree for a reason that has
nothing to do with the gate's verdict. The escapes are reproduced byte for byte
and the defect is reported.

THE ROOT IS `paths.repo_root()`. The twin derives it from `${BASH_SOURCE[0]}`,
three directories up. Both resolve to the same place from their own file's
location, and the package-wide override is what lets the selftest point the gate
at a fixture without inventing a ninth `*_ROOT` variable.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls, plant

# The three subjects, relative to the repository root.
GATE_REL = ".ci/scripts/review/claude-review-gate.sh"
STATUS_REL = ".ci/scripts/review/review-status.sh"
LIB_REL = ".ci/scripts/lib/common.sh"

# The colours, assigned unconditionally, exactly as the twin does. See the port
# notes for why `rediacc_ci.log` is deliberately not used here.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# The four helpers that must be defined once, in the library, and nowhere else.
# ORDER IS THE TWIN'S `for fn in ...` ORDER, because it is the order the
# findings come out in and a reviewer diffs the two outputs side by side.
SHARED_HELPERS = (
    "review_spend_total",
    "review_spent_attempt_count",
    "review_cap_for",
    "review_report_count",
)

# THE 2026-08-07 SHAPE ITSELF: a caller deriving the numerator from
# `review_report_count` directly. That is how review-status.sh read 0/3 while
# the gate read 3/3, so it is named as its own failure rather than left to be
# inferred from the absence of `review_spend_total`.
_LOCAL_NUMERATOR = re.compile(r"review_count=.*review_report_count")

# The anchor the deadlock branch is extracted by. ANCHORED AT COLUMN 0 and
# stopped after the FIRST complete range: the same condition appears again,
# indented, further down the file, and an unanchored range restarts there and
# returns an unterminated block that cannot run.
_GUARD_START = re.compile(r'^if \[\[ "\$currency_ok" == true \]\]')
_GUARD_END = re.compile(r"^fi$")

# The mutation the control plants, and its replacement. Byte for byte from the
# twin's `${STATUS_SRC//.../...}`.
_MUTANT_FROM = 'review_count="$(review_spend_total "$pr" "$ATTEMPT_PREFIX")"'
_MUTANT_TO = 'review_count="$(review_report_count "$pr")"'

# The wrapper the extracted branch runs inside. `%s` is the branch.
#
# The five pinned variables are what put the run AT the cap: review_count == 3
# == MAX_REVIEWS_PER_PR, with currency_ok false so the else-branch is entered at
# all. The loggers are stubbed to `:` so the branch's own output does not reach
# the arrays' verdict.
_GUARD_WRAPPER = """
                    warnings=(); failures=()
                    log_info() { :; }; log_warn() { :; }; log_error() { :; }
                    %s
                    if [[ ${#warnings[@]} -gt 0 ]]; then echo GUARD_FIRED; fi
                    if [[ ${#failures[@]} -gt 0 ]]; then echo GUARD_MISSED; fi
                """

# The environment the wrapper runs under, over the inherited one. The twin sets
# these as a command prefix, which makes them environment variables for the
# child and therefore ordinary shell variables inside it.
_GUARD_ENV = {
    "review_count": "3",
    "MAX_REVIEWS_PER_PR": "3",
    "currency_ok": "false",
    "currency_detail": "x",
    "head_sha": "y",
    "last_sha": "z",
}


def _records(text: str) -> list[str]:
    """The lines awk would read as RECORDS, which is not `split("\\n")`.

    A file ending in a newline has N records, not N+1: `"a\\nb\\n"` is two lines
    to awk and three elements to `split`. The phantom third element is empty, so
    it never matches a pattern, and every per-line grep in this module is
    unaffected by it. `extract_guard` is NOT unaffected: it JOINS the records it
    kept, and a trailing empty element becomes a trailing newline that
    `$(awk ...)` would have stripped. That divergence shipped in a draft and the
    pytest differential caught it on the unterminated-block case.

    `splitlines()` is deliberately not used: it also splits on \\v, \\f, \\x1c and
    U+2028, none of which awk treats as a record separator, so it would make the
    port see records the twin does not.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def extract_guard(status_src: str) -> str:
    """The `currency_ok` branch of review-status.sh, or "" when it is gone.

    `awk '/^if \\[\\[ "\\$currency_ok" == true \\]\\]/{f=1} f{print} f&&/^fi$/{exit}'`,
    reproduced with its ordering intact: the terminating `fi` is PRINTED and
    then the scan exits, so the block is complete and runnable. An
    implementation that exited first would return a block with an unbalanced
    `if`, which fails to parse and looks exactly like a broken guard.

    Returns "" when the anchor is not found, which the caller reports as
    "rewritten?" rather than as a passing guard: an extraction that found
    nothing has tested nothing.
    """
    out: list[str] = []
    started = False
    for line in _records(status_src):
        if not started and _GUARD_START.search(line):
            started = True
        if started:
            out.append(line)
            if _GUARD_END.search(line):
                break
    # `$( )` strips trailing newlines; the twin puts this inside one.
    return "\n".join(out)


def run_guard(guard: str) -> str:
    """Execute the extracted branch at numerator == cap. Returns its stdout.

    STDERR IS DISCARDED, matching the twin's `2>/dev/null`. That is a real loss
    of information (a branch that failed to parse says so on stderr and is then
    indistinguishable from one that simply did not fire) and it is preserved
    because the finding text the gate prints, "got: nothing", is what a reader
    acts on either way.
    """
    env = dict(os.environ)
    env.update(_GUARD_ENV)
    proc = subprocess.run(
        ["bash", "-c", _GUARD_WRAPPER % guard],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # `out="$( ... )"` STRIPS EVERY TRAILING NEWLINE, and forgetting that is a
    # real bug this port shipped for one run. The finding text interpolates this
    # value -- "(got: GUARD_MISSED)" -- so an unstripped "\n" put the closing
    # paren on the next line and the shadow differential scored
    # MISMATCH_FINDINGS against the twin on the one fixture that reaches this
    # branch. The comparator earned its keep; the strip is the fix.
    return proc.stdout.rstrip("\n")


def evaluate(gate_src: str, status_src: str, lib_src: str) -> list[str]:
    """One string per failure, empty when the cap is measured coherently.

    RETURNS A LIST RATHER THAN PRINTING, which is the twin's shape too: it
    `echo`s findings on stdout and ALWAYS returns 0, with its own comment saying
    why ("a non-zero return here would abort the whole gate under `set -e`
    before it could print a single one"). The list makes that structural instead
    of conventional, and it is what lets the control plant be judged by the same
    code path as the real run.
    """
    findings: list[str] = []

    # 1 + 2. Both sides must reach for the shared helpers BY NAME.
    if "review_spend_total" not in gate_src:
        findings.append("DRY-NUMERATOR: claude-review-gate.sh does not call review_spend_total()")
    if "review_spend_total" not in status_src:
        findings.append("DRY-NUMERATOR: review-status.sh does not call review_spend_total()")
    if "review_cap_for" not in gate_src:
        findings.append("DRY-DENOMINATOR: claude-review-gate.sh does not call review_cap_for()")
    if "review_cap_for" not in status_src:
        findings.append("DRY-DENOMINATOR: review-status.sh does not call review_cap_for()")

    # 1b. The actual 2026-08-07 shape, named as its own failure.
    if any(_LOCAL_NUMERATOR.search(line) for line in status_src.split("\n")):
        findings.append(
            "DRY-NUMERATOR: review-status.sh derives its cap numerator from review_report_count "
            "(posted reports ONLY) -- spent attempts are invisible to it, which is the #553 "
            "deadlock"
        )
    if any(_LOCAL_NUMERATOR.search(line) for line in gate_src.split("\n")):
        findings.append(
            "DRY-NUMERATOR: claude-review-gate.sh derives its cap numerator from "
            "review_report_count directly"
        )

    # 3. The shared helpers must be defined once, in the lib.
    #
    # THE CONCATENATION IS DELIBERATE AND UNSEPARATED. See the port notes: `$g$s`
    # joins the last line of the gate to the first line of the status script.
    joined = gate_src + status_src
    for fn in SHARED_HELPERS:
        definition = re.compile(r"^%s\(\) \{" % re.escape(fn))
        if not any(definition.search(line) for line in lib_src.split("\n")):
            findings.append("ONE-DEFINITION: %s() is not defined in lib/common.sh" % fn)
        redefined = sum(1 for line in joined.split("\n") if definition.search(line))
        if redefined != 0:
            findings.append(
                "ONE-DEFINITION: %s() is redefined in a review script; a local copy is what "
                "drifted last time" % fn
            )

    # 4. Behavioural. Extracted from the real file by anchor, never transcribed.
    guard = extract_guard(status_src)
    if guard == "":
        findings.append(
            "GUARD-REACHABLE: could not extract the currency/deadlock branch from "
            "review-status.sh (rewritten?)"
        )
        return findings

    out = run_guard(guard)
    if "GUARD_FIRED" not in out:
        findings.append(
            "GUARD-REACHABLE: at numerator == cap the deadlock guard did NOT fire (got: %s). "
            "A capped PR would be reported as a required FAILURE and become unmergeable."
            % (out or "nothing")
        )
    if "GUARD_MISSED" in out:
        findings.append(
            "GUARD-REACHABLE: at numerator == cap review-status still recorded a hard failure"
        )
    return findings


def fail(message: str) -> int:
    """The twin's `fail()`: one coloured line on stderr, exit 1."""
    print("%s✗%s %s" % (RED, NC, message), file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 coherent, 1 otherwise.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no
    arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    gate = root / GATE_REL
    status = root / STATUS_REL
    lib = root / LIB_REL

    # A MISSING SUBJECT IS A REFUSAL, NOT AN ABSTENTION, and the twin's wording
    # says so: "refusing to pass while measuring nothing".
    for path in (gate, status, lib):
        if not path.is_file():
            return fail(
                "check-review-cap-coherence: %s not found; refusing to pass while measuring "
                "nothing" % path
            )

    gate_src = gate.read_text(encoding="utf-8", errors="replace")
    status_src = status.read_text(encoding="utf-8", errors="replace")
    lib_src = lib.read_text(encoding="utf-8", errors="replace")
    # `$(cat f)` strips every trailing newline. That is not cosmetic here: the
    # ONE-DEFINITION scan concatenates two of these three, and whether the join
    # produces a spliced line depends on exactly this.
    gate_src = gate_src.rstrip("\n")
    status_src = status_src.rstrip("\n")
    lib_src = lib_src.rstrip("\n")

    # -- control: plant the original defect and require detection -----------
    mutant_status = status_src.replace(_MUTANT_FROM, _MUTANT_TO)
    if mutant_status == status_src:
        return fail(
            "check-review-cap-coherence: the control could not plant its defect (the "
            "review_spend_total call in review-status.sh is not where it was). Update the "
            "mutant here to match. Refusing to report a green that proves nothing."
        )
    control_out = evaluate(gate_src, mutant_status, lib_src)
    if not control_out:
        return fail(
            "check-review-cap-coherence: CONTROL DID NOT FIRE. The pre-fix split numerator "
            "passed every assertion, so this gate cannot detect the defect it exists for."
        )

    # -- the real run -------------------------------------------------------
    real_out = evaluate(gate_src, status_src, lib_src)
    if real_out:
        print("%s✗%s the review cap is not measured coherently:" % (RED, NC), file=sys.stderr)
        # ONLY THE FIRST LINE IS INDENTED. `printf '  %s\n' "$REAL_OUT"` gets one
        # argument holding embedded newlines. Reproduced, and reported.
        print("  %s" % "\n".join(real_out), file=sys.stderr)
        print(file=sys.stderr)
        print(
            "  Both scripts must take the numerator from review_spend_total() and the",
            file=sys.stderr,
        )
        print(
            "  denominator from review_cap_for(), both in .ci/scripts/lib/common.sh.",
            file=sys.stderr,
        )
        print(
            "  When they disagree, the gate stops reviewing while review-status keeps",
            file=sys.stderr,
        )
        print("  demanding a review, and the PR becomes permanently unmergeable.", file=sys.stderr)
        return 1

    print(
        "%s✓%s review cap coherent: one numerator, one denominator, deadlock guard reachable "
        "at the cap" % (GREEN, NC)
    )
    # PRINT THE SHAPE, NOT JUST THE VERDICT. `wc -l <<<"$CONTROL_OUT"` counts the
    # herestring's lines, which for a non-empty findings list is exactly its
    # length: the herestring appends the final newline the list does not carry.
    print(
        "  control fired on the pre-fix split numerator (%d finding(s)), so this green means "
        "the checks can fail" % len(control_out)
    )
    return 0


# A minimal, COHERENT trio. Small enough to read, and every property the gate
# asserts is present exactly once, so each plant below removes exactly one.
_LIB = """#!/bin/bash
review_cap_for() {
    echo 3
}
review_report_count() {
    echo 0
}
review_spent_attempt_count() {
    echo 0
}
review_spend_total() {
    echo 3
}
"""

_GATE = """#!/bin/bash
review_count=$(review_spend_total "$pr" "$ATTEMPT_PREFIX")
MAX_REVIEWS_PER_PR=$(review_cap_for "$pr_loc")
"""

_STATUS = """#!/bin/bash
review_count="$(review_spend_total "$pr" "$ATTEMPT_PREFIX")"
MAX_REVIEWS_PER_PR="$(review_cap_for "$pr_loc")"
if [[ "$currency_ok" == true ]]; then
    log_info "ok"
else
    if [[ "${review_count:-0}" -ge "$MAX_REVIEWS_PER_PR" ]]; then
        warnings+=("**REVIEW CAP REACHED** (${review_count}/${MAX_REVIEWS_PER_PR})")
        log_warn "capped"
    else
        failures+=("Head \\`${head_sha}\\` has not been reviewed.")
        log_error "stale"
    fi
fi
"""


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY ASSERTION. The mirrors matter more here than in
    most gates: four of the five checks are substring or anchored-regex tests
    over shell source, and a substring test that has become too loose flags a
    correct tree while still passing every positive plant.
    """
    ctl = Controls("review-cap-coherence", floor=24, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for rel in (GATE_REL, STATUS_REL, LIB_REL):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)

        def run(gate: str | None, status: str | None, lib: str | None) -> int:
            """Write the trio into the fixture and judge it. None DELETES."""
            for rel, content in ((GATE_REL, gate), (STATUS_REL, status), (LIB_REL, lib)):
                target = root / rel
                if content is None:
                    if target.exists():
                        target.unlink()
                else:
                    target.write_text(content, encoding="utf-8")
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    del os.environ[paths.ROOT_ENV]
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("CONTROL: the coherent trio passes", run(_GATE, _STATUS, _LIB), 0)

        # THE VACUITY CASES. Each subject missing in turn, because a loop that
        # stopped checking one of the three looks identical to a clean tree.
        ctl.check("VACUITY: a missing gate script is refused", run(None, _STATUS, _LIB), 1)
        ctl.check("VACUITY: a missing status script is refused", run(_GATE, None, _LIB), 1)
        ctl.check("VACUITY: a missing lib is refused", run(_GATE, _STATUS, None), 1)

        # THE CONTROL ON THE CONTROL. If the mutant cannot be planted, the gate
        # must refuse rather than report the green it did not earn.
        ctl.check(
            "VACUITY: an unplantable control is refused",
            run(
                _GATE, plant(_STATUS, _MUTANT_FROM, "review_count=$(review_spend_total x y)"), _LIB
            ),
            1,
        )

        # PLANT 1: the #553 shape itself, in review-status.sh.
        ctl.check(
            "PLANT: the split numerator is caught",
            run(_GATE, plant(_STATUS, _MUTANT_FROM, _MUTANT_TO), _LIB),
            1,
        )
        # PLANT 2: the same shape in the gate script.
        ctl.check(
            "PLANT: the gate deriving its own numerator is caught",
            run(
                plant(
                    _GATE,
                    'review_count=$(review_spend_total "$pr" "$ATTEMPT_PREFIX")',
                    'review_count=$(review_report_count "$pr")',
                ),
                _STATUS,
                _LIB,
            ),
            1,
        )
        # PLANT 3: the denominator drift, the half lib/common.sh already fixed.
        ctl.check(
            "PLANT: a status script not calling review_cap_for is caught",
            run(_GATE, plant(_STATUS, "review_cap_for", "cap_for_local"), _LIB),
            1,
        )
        # PLANT 4: a helper missing from the library.
        for fn in SHARED_HELPERS:
            ctl.check(
                "PLANT: %s() missing from lib/common.sh is caught" % fn,
                run(_GATE, _STATUS, plant(_LIB, "%s() {" % fn, "%s_renamed() {" % fn)),
                1,
            )
        # PLANT 5: a local copy shadowing the shared one. This is the shape the
        # ONE-DEFINITION assertion exists for, and it is the one a substring
        # test would miss: the name is ALREADY present in both scripts.
        ctl.check(
            "PLANT: a helper redefined in a review script is caught",
            run(_GATE + "\nreview_cap_for() {\n    echo 9\n}\n", _STATUS, _LIB),
            1,
        )
        # PLANT 6: the behavioural half. The guard branch records a hard failure
        # at the cap instead of a warning, which is #553 exactly.
        ctl.check(
            "PLANT: a deadlock guard that does not fire is caught",
            run(_GATE, plant(_STATUS, "warnings+=(", "failures+=("), _LIB),
            1,
        )
        # PLANT 7: the anchor is gone, so nothing could be extracted. An
        # extraction that found nothing has tested nothing.
        ctl.check(
            "PLANT: an unextractable guard is caught",
            run(_GATE, plant(_STATUS, 'if [[ "$currency_ok" == true ]]', "if $ok"), _LIB),
            1,
        )

        # MIRRORS. Shapes that must stay GREEN.
        ctl.check(
            "MIRROR: an indented copy of the anchor does not break extraction",
            run(_GATE, _STATUS + '\n    if [[ "$currency_ok" == true ]]; then\n    fi\n', _LIB),
            0,
        )
        # THE MIRROR IS NARROW ON PURPOSE, and the first draft of it was WRONG.
        # `review_count=.*review_report_count` is a per-line ERE with no comment
        # awareness, so `# review_count= from review_report_count ...` DOES fire
        # it -- in the twin as much as in the port. Writing that case as a
        # must-not-fire mirror asserted a behaviour neither implementation has.
        # The honest mirror is a line naming both helpers in the other order,
        # which the regex cannot match and which a looser rewrite would.
        ctl.check(
            "MIRROR: review_report_count named BEFORE review_count is not the shape",
            run(
                _GATE,
                "# review_report_count feeds review_count only inside the lib\n" + _STATUS,
                _LIB,
            ),
            0,
        )

    # -- the pure helpers, driven directly ---------------------------------
    ctl.check(
        "extract_guard: the block ENDS with its own fi",
        extract_guard(_STATUS).split("\n")[-1],
        "fi",
    )
    ctl.check(
        "extract_guard: the block STARTS at the anchor",
        extract_guard(_STATUS).split("\n")[0],
        'if [[ "$currency_ok" == true ]]; then',
    )
    ctl.check(
        "extract_guard: no anchor yields the empty string, not a partial block",
        extract_guard("echo hi\nfi\n"),
        "",
    )
    ctl.check(
        "extract_guard: an INDENTED anchor is not the anchor",
        extract_guard('    if [[ "$currency_ok" == true ]]; then\n    fi\n'),
        "",
    )
    ctl.check(
        "run_guard: the extracted block fires at numerator == cap",
        "GUARD_FIRED" in run_guard(extract_guard(_STATUS)),
        True,
    )
    ctl.check(
        "run_guard: and it does NOT record a hard failure there",
        "GUARD_MISSED" in run_guard(extract_guard(_STATUS)),
        False,
    )
    # THE TRAILING NEWLINE, PINNED. `out="$( ... )"` strips it and the port did
    # not, which put the closing paren of "(got: GUARD_MISSED)" on its own line
    # and made the shadow differential report MISMATCH_FINDINGS. Asserted on the
    # exact string rather than on a substring, because a substring test is what
    # let it through.
    ctl.check(
        "run_guard: the result carries NO trailing newline, as $( ) does not",
        run_guard(extract_guard(plant(_STATUS, "warnings+=(", "failures+=("))),
        "GUARD_MISSED",
    )
    ctl.check("evaluate: the coherent trio has no findings", evaluate(_GATE, _STATUS, _LIB), [])

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
