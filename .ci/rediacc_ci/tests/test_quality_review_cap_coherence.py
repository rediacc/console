"""`rediacc_ci.quality.review_cap_coherence` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. Three of this gate's
moving parts are shell semantics rather than logic, and every one of them has
already produced a wrong answer in a draft of this port:

  * `out="$( ... )"` STRIPS trailing newlines. The port returned
    `subprocess.stdout` unchanged, so the finding read "(got: GUARD_MISSED\\n"
    and the shadow differential scored MISMATCH_FINDINGS. Pinned below.
  * `grep -cE "^fn\\(\\) \\{" <<<"$g$s"` concatenates two files with NO separator,
    because `$(cat f)` has already eaten the trailing newline. The spliced line
    is a real, if currently harmless, blind spot.
  * `awk '/anchor/{f=1} f{print} f&&/^fi$/{exit}'` prints the terminating line
    and THEN exits, which is what makes the extracted block parseable.

A table of expected strings would be a table of what the port does, asserted
against itself. The bash fragments below are lifted from
`.ci/scripts/quality/check-review-cap-coherence.sh` with nothing changed but the
substitution of their arguments.

They are NOT the whole gate: the whole gate is what the committed shadow ledger
`.ci/shadow/w7p2-reviewcap.observations.jsonl` compares over five distinct
trees. This file covers the seams that ledger cannot isolate.
"""

import pathlib
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import review_cap_coherence as rcc
from rediacc_ci.tests import differential as diff

# The awk extraction, verbatim from the twin.
_GUARD_AWK = (
    """awk '/^if \\[\\[ "\\$currency_ok" == true \\]\\]/{f=1} f{print} f&&/^fi$/{exit}' status.sh"""
)

# Every shape the anchor scan has to survive, with the property each is for.
GUARD_CASES = [
    (rcc._STATUS, "the reference status script"),
    ("echo hi\n", "no anchor at all"),
    ('    if [[ "$currency_ok" == true ]]; then\n    fi\n', "an INDENTED anchor is not the anchor"),
    (
        'if [[ "$currency_ok" == true ]]; then\n    :\nfi\nif [[ "$currency_ok" == true ]]; then\n    :\nfi\n',
        "the FIRST complete range only, so a second copy is not appended",
    ),
    (
        'if [[ "$currency_ok" == true ]]; then\n    :\n',
        "an UNTERMINATED block is returned as far as it goes",
    ),
    (
        'if [[ "$currency_ok" == true ]]; then\n    if x; then\n    fi\nfi\n',
        "the first column-0 `fi` ends it, nested or not",
    ),
    ("", "the empty file"),
]


@pytest.mark.parametrize(("content", "why"), GUARD_CASES)
def test_extract_guard_matches_the_awk(tmp_path: pathlib.Path, content: str, why: str) -> None:
    (tmp_path / "status.sh").write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams(_GUARD_AWK, cwd=str(tmp_path))
    assert code == 0, err
    # `$( )` strips trailing newlines, and the twin puts the awk inside one.
    assert rcc.extract_guard(content) == out.rstrip("\n"), why


def test_the_guard_table_exercises_both_directions() -> None:
    extracted = [rcc.extract_guard(c) for c, _why in GUARD_CASES]
    assert any(extracted), "no case extracts; the table tests nothing"
    assert any(e == "" for e in extracted), "every case extracts; the table has no negatives"


# The wrapper the extracted branch runs inside, verbatim, with the same five
# pinned variables. `%s` is the branch.
_GUARD_RUN = """
review_count=3 MAX_REVIEWS_PER_PR=3 currency_ok=false currency_detail=x head_sha=y last_sha=z \
    bash -c '
        warnings=(); failures=()
        log_info() { :; }; log_warn() { :; }; log_error() { :; }
        %s
        if [[ ${#warnings[@]} -gt 0 ]]; then echo GUARD_FIRED; fi
        if [[ ${#failures[@]} -gt 0 ]]; then echo GUARD_MISSED; fi
    ' 2>/dev/null
"""

RUN_CASES = [
    (rcc._STATUS, "the healthy guard warns at the cap"),
    (rcc._STATUS.replace("warnings+=(", "failures+=("), "the #553 shape fails at the cap"),
    (rcc._STATUS.replace("-ge", "-gt"), "an off-by-one puts the run in the else branch"),
]


@pytest.mark.parametrize(("status", "why"), RUN_CASES)
def test_run_guard_matches_the_bash_subrun(status: str, why: str) -> None:
    """The behavioural half, run for real on both sides.

    THE ASSERTION IS ON THE WHOLE STRING, not on a substring. A substring test
    is exactly what let the missing `rstrip` through: `"GUARD_MISSED" in out`
    was true for both `GUARD_MISSED` and `GUARD_MISSED\\n`, and the difference
    was only visible once the value was interpolated into a finding.
    """
    guard = rcc.extract_guard(status)
    code, out, err = diff.bash_streams(_GUARD_RUN % guard)
    assert code == 0, err
    assert rcc.run_guard(guard) == out.rstrip("\n"), why


def test_the_run_table_exercises_both_verdicts() -> None:
    seen = {rcc.run_guard(rcc.extract_guard(s)) for s, _why in RUN_CASES}
    assert "GUARD_FIRED" in seen
    assert "GUARD_MISSED" in seen


def test_the_stripped_result_is_what_the_finding_interpolates() -> None:
    """The regression itself, as its own case rather than folded into a table.

    The finding text is `(got: %s)`. With a trailing newline the closing paren
    lands on the next line, which the shadow comparator reads as a DIFFERENT
    finding. That is how this was caught, and this is what stops it returning.
    """
    broken = rcc._STATUS.replace("warnings+=(", "failures+=(")
    findings = rcc.evaluate(rcc._GATE, broken, rcc._LIB)
    guard_findings = [f for f in findings if f.startswith("GUARD-REACHABLE")]
    assert guard_findings, "the plant did not reach the behavioural assertion"
    assert "(got: GUARD_MISSED)" in guard_findings[0]
    assert "\n" not in guard_findings[0]


# The ONE-DEFINITION scan's `grep -cE ... <<<"$g$s"`, verbatim.
_REDEF_GREP = (
    """g="$(cat gate.sh)"; s="$(cat status.sh)"; grep -cE "^%s\\(\\) \\{" <<<"$g$s" || true"""
)

REDEF_CASES = [
    ("#!/bin/bash\necho a\n", "#!/bin/bash\necho b\n", "review_cap_for", "neither defines it"),
    (
        "#!/bin/bash\nreview_cap_for() {\n    echo 3\n}\n",
        "#!/bin/bash\necho b\n",
        "review_cap_for",
        "the gate defines it",
    ),
    (
        "#!/bin/bash\necho a\n",
        "#!/bin/bash\nreview_cap_for() {\n    echo 3\n}\n",
        "review_cap_for",
        "the status script defines it",
    ),
    (
        "#!/bin/bash\nreview_cap_for() {\n    echo 3\n}\n",
        "#!/bin/bash\nreview_cap_for() {\n    echo 4\n}\n",
        "review_cap_for",
        "both define it, so the count is two",
    ),
    (
        "#!/bin/bash\necho a\n",
        "review_cap_for() {\n    echo 3\n}\n",
        "review_cap_for",
        (
            "THE SPLICE: the status script's FIRST line is joined to the gate's last, "
            "so a definition on line 1 is invisible to the ^ anchor"
        ),
    ),
    (
        "#!/bin/bash\n    review_cap_for() {\n",
        "#!/bin/bash\n",
        "review_cap_for",
        "an INDENTED definition is not anchored",
    ),
    (
        "#!/bin/bash\nreview_cap_for(){\n",
        "#!/bin/bash\n",
        "review_cap_for",
        "the twin's pattern demands a space before the brace",
    ),
]


@pytest.mark.parametrize(("gate", "status", "fn", "why"), REDEF_CASES)
def test_the_redefinition_count_matches_bash(
    tmp_path: pathlib.Path, gate: str, status: str, fn: str, why: str
) -> None:
    """Including the splice, which is a twin defect the port preserves."""
    (tmp_path / "gate.sh").write_text(gate, encoding="utf-8")
    (tmp_path / "status.sh").write_text(status, encoding="utf-8")
    code, out, err = diff.bash_streams(_REDEF_GREP % fn, cwd=str(tmp_path))
    assert code == 0, err
    expected = int(out.strip())

    joined = gate.rstrip("\n") + status.rstrip("\n")
    pattern = re.compile(r"^%s\(\) \{" % re.escape(fn))
    got = sum(1 for line in joined.split("\n") if pattern.search(line))
    assert got == expected, why


def test_the_splice_case_is_really_a_splice() -> None:
    """The blind spot, asserted so the report's claim about it is checked.

    A definition on line 1 of the status script vanishes because the gate's
    last line is glued to it. This is the twin's behaviour; the port keeps it
    and it is reported rather than fixed, because fixing it would change the
    verdict and a port does not get to do that.
    """
    gate = "#!/bin/bash\necho a"
    status = "review_cap_for() {\n    echo 3\n}"
    findings = rcc.evaluate(gate, status, rcc._LIB)
    assert not any("is redefined in a review script" in f for f in findings)


# The `review_count=.*review_report_count` scan, per line, verbatim.
_NUMERATOR_GREP = (
    """grep -qE 'review_count=.*review_report_count' status.sh && echo yes || echo no"""
)

NUMERATOR_CASES = [
    'review_count="$(review_report_count "$pr")"\n',
    "review_count=$(review_report_count $pr)\n",
    'review_count="$(review_spend_total "$pr" "$P")"\n',
    "# review_count= from review_report_count is the old shape\n",
    "review_report_count feeds review_count\n",
    "review_count=1\nreview_report_count=2\n",
    "",
]


@pytest.mark.parametrize("content", NUMERATOR_CASES)
def test_the_local_numerator_scan_matches_grep(tmp_path: pathlib.Path, content: str) -> None:
    (tmp_path / "status.sh").write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams(_NUMERATOR_GREP, cwd=str(tmp_path))
    assert code == 0, err
    got = any(rcc._LOCAL_NUMERATOR.search(line) for line in content.split("\n"))
    assert got is (out.strip() == "yes")


def test_the_numerator_table_exercises_both_directions() -> None:
    verdicts = {
        any(rcc._LOCAL_NUMERATOR.search(line) for line in c.split("\n")) for c in NUMERATOR_CASES
    }
    assert verdicts == {True, False}


def test_the_control_mutation_still_matches_the_real_review_status() -> None:
    """The gate refuses when the mutant cannot be planted, so the string matters.

    Asserted against the REAL file rather than the fixture, because this is the
    one part of the gate that rots silently: an unrelated edit to
    review-status.sh's numerator line turns the whole gate into a refusal, and
    the message it prints then blames the gate rather than the edit.
    """
    status = paths.repo_root() / rcc.STATUS_REL
    assert status.is_file(), status
    assert rcc._MUTANT_FROM in status.read_text(encoding="utf-8")


def test_selftest_passes() -> None:
    assert rcc.selftest() == 0
