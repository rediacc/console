"""`rediacc_ci.quality.review_turn_capacity` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-review-turn-capacity.sh` over a git fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-review-turn-capacity.observations.jsonl`.

THE SUBJECT IS A BASH FUNCTION, so every case below writes a whole `claude-review-gate.sh` into the specimen. That is the gate's own design: it extracts `emit_review_turns()` BY ANCHOR from the real file and runs it, "so a rename or rewrite breaks THIS gate loudly instead of silently leaving it testing a stale copy pasted in here". A test that fed it a Python re-derivation of the
budget would be testing the test.

THE CORPUS IS BOTH DIRECTIONS FOR ALL FIVE PROPERTIES, and the negative case is the load-bearing one: a healthy continuous budget must be SILENT. Without it, a gate that reported every budget as starving would pass every positive case here and would be switched off within a day of landing.

THE FOUR REFUSALS ARE CASES TOO. A missing file, a renamed function, an
extraction that finds no `review_turns=` assignment, and a mutant that cannot be
planted are four DIFFERENT messages in the twin, and collapsing any two of them would send a reader to the wrong file. The missing-file case is asserted here rather than in the ledger, because `scripts/lib/shadow-gate.ts` classifies its message as a REFUSAL (its `CANNOT READ` vocabulary matches "a function it cannot read") and therefore suspends the comparison instead of ruling on
it. That is the comparator working as designed, and it is exactly why the case belongs in a test that CAN rule on it.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.quality import review_turn_capacity as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-review-turn-capacity.sh"
MODULE = "review_turn_capacity"

HEALTHY = """#!/bin/bash
emit_review_turns() {
    local changed
    changed=$(gh) || changed=0
    local per_kloc=25 max_turns=140 min_turns=50
    local kloc=$(((${changed:-0} + 999) / 1000))
    local turns=$((kloc * per_kloc))
    [[ "$turns" -lt "$min_turns" ]] && turns="$min_turns"
    [[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"
    echo "review_turns=$turns" >>"$GITHUB_OUTPUT"
    log_info "x"
}
"""


def build(tmp_path: pathlib.Path, source: str | None) -> pathlib.Path:
    """A specimen holding BOTH implementations and one `claude-review-gate.sh`.

    `None` means the subject file is ABSENT, which is a distinct refusal from a renamed function: one says "I cannot read it", the other "I read it and the anchor is gone".
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "scripts" / "review").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    # `proc.py` is in the list because the port routes its `bash -c` harness
    # through the shared runner; without it the specimen dies at import and the
    # differential compares a traceback with the twin's verdict.
    for name in ("__init__.py", "log.py", "paths.py", "controls.py", "proc.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    if source is not None:
        (root / gate.GATE_SRC_REL).write_text(source, encoding="utf-8")
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old = diff.bash_streams("bash %s" % TWIN, cwd=str(root))
    new = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s" % MODULE,
        cwd=str(root),
    )
    return old, new


CASES = [
    # THE NEGATIVE HALF, first, because it is the one whose absence would make every other case meaningless.
    ("a healthy continuous budget is silent", HEALTHY, 0),
    (
        "the pre-incident rung shape starves at its top",
        HEALTHY.replace(
            "local kloc=$(((${changed:-0} + 999) / 1000))\n    local turns=$((kloc * per_kloc))",
            'local turns=$min_turns\n    [[ "${changed:-0}" -gt 5000 ]] && turns=$max_turns',
        ),
        1,
    ),
    (
        "a budget that shrinks with diff size is caught",
        HEALTHY.replace("local turns=$((kloc * per_kloc))", "local turns=$((200 - kloc))"),
        1,
    ),
    (
        "a budget that emits nothing is caught by TOTAL, not by a crash",
        HEALTHY.replace('echo "review_turns=$turns" >>"$GITHUB_OUTPUT"', ":"),
        1,
    ),
    (
        "a huge diff routed below the budget's own ceiling is caught",
        HEALTHY.replace(
            'echo "review_turns=$turns" >>"$GITHUB_OUTPUT"',
            '[[ "${changed:-0}" -gt 29999 ]] && turns=60\n'
            '    echo "review_turns=$turns" >>"$GITHUB_OUTPUT"',
        ),
        1,
    ),
    (
        "a renamed function breaks the gate loudly",
        HEALTHY.replace("emit_review_turns()", "emit_turns_for_review()"),
        1,
    ),
    (
        "an extraction with no review_turns assignment is refused",
        "#!/bin/bash\nemit_review_turns() {\n    local per_kloc=25\n    log_info x\n}\n",
        1,
    ),
    (
        "a budget the mutant cannot be planted into is refused",
        HEALTHY.replace("per_kloc=25 ", "").replace("kloc * per_kloc", "kloc * 25"),
        1,
    ),
    ("an absent subject file is refused, not skipped", None, 1),
]


@pytest.mark.parametrize(
    ("source", "want_exit"),
    [(c[1], c[2]) for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_differential(tmp_path, source, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, source)
    (old_rc, old_out, old_err), (new_rc, new_out, new_err) = run_both(root)
    assert old_rc == want_exit, "the twin's verdict moved: %s%s" % (old_out, old_err)
    assert new_rc == old_rc
    assert new_out == old_out
    assert new_err == old_err


def test_the_four_refusals_say_four_different_things(tmp_path):
    """A refusal that cannot be told from its neighbour sends readers to the wrong file.

    Collapsing "not found", "could not extract", "never assigns review_turns" and "could not plant its defect" into one message would be a behaviour change that no byte-equality case above would catch on its own, because each case only compares one message against itself.
    """
    messages = set()
    for source in (
        None,
        HEALTHY.replace("emit_review_turns()", "emit_turns_for_review()"),
        "#!/bin/bash\nemit_review_turns() {\n    local per_kloc=25\n    log_info x\n}\n",
        HEALTHY.replace("per_kloc=25 ", "").replace("kloc * per_kloc", "kloc * 25"),
    ):
        root = build(tmp_path / str(len(messages)), source)
        _rc, _out, err = diff.bash_streams(
            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s" % MODULE,
            cwd=str(root),
        )
        messages.add(err.strip())
    assert len(messages) == 4, "two refusals produced the same text: %r" % messages


def test_the_measured_facts_are_not_tunable():
    """2802 lines and 50 turns are facts about PR #553, not knobs.

    A port that "cleaned these up" into a parameter would let a future edit lower the regression bar back under the diff that starved, which is the exact hole property 5 exists to close.
    """
    assert gate.STARVED_LINES == 2802
    assert gate.STARVED_TURNS == 50
    assert gate.DEFAULT_MIN_TURNS_PER_KLOC == 22, "the floor sits above the 17.8 that starved"


def test_the_probe_sizes_bracket_both_measured_prs():
    """Both PRs from 2026-08-07 must be probed, or the regression is untested."""
    assert 2270 in gate.PROBE_SIZES, "PR #552, the survivor"
    assert 2802 in gate.PROBE_SIZES, "PR #553, the starved one"
    assert len(gate.PROBE_SIZES) == 17


def test_extraction_is_by_anchor_and_stops_at_the_closing_brace():
    """Text after the function must not leak into what gets executed."""
    body = gate.extract_function("noise\n%s\nmore noise\n" % HEALTHY)
    assert body.startswith("emit_review_turns() {")
    assert body.endswith("}")
    assert "more noise" not in body
    assert gate.extract_function("nothing here") == ""


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    # 11, DOWN FROM 12, and the reason matters because lowering a floor is normally the wrong move. The control that went was "the control's mutation actually changes the text", which asserted for ONE plant what `rediacc_ci.controls.plant()` now refuses for all five: coverage went UP while the count went down. If this number ever needs lowering again without a matching line in the
    # gate's own derived floor, that is controls quietly not running, which is what this asserts.
    assert int(out.split(" control(s)")[0].strip()) >= 11


def test_the_twin_is_still_present():
    """Invariant 5: a twin is never deleted in the change that ports it."""
    assert (pathlib.Path(diff.repo()) / TWIN).is_file()
    assert subprocess.run(["bash", "-c", "true"], check=False).returncode == 0
