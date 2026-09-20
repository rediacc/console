"""Controls for rediacc_ci.controls -- the runner that replaces five copies.

THE THING BEING TESTED IS ITSELF A TEST HARNESS, so the usual asymmetry applies
with force: a harness that reported PASS unconditionally would satisfy every
"this passes" assertion in a suite written carelessly. Every case below is therefore paired against its opposite, and the FAILURE direction is asserted first wherever the two are written together.

THE OUTPUT STRINGS ARE PART OF THE CONTRACT, not incidental formatting. `.claude/hooks/test-hooks.sh` runs these programs and reads what they print, and the five files being migrated all print the same four shapes today. A migration that changed a message would be a silent behaviour change in the harness, so the exact bytes are asserted here rather than left to review.

WHY THE FLOOR GETS THE MOST CASES. Three of the five files carry no floor at all, and the floor is the only thing that catches a suite whose controls stopped executing -- a `sys.exit` slipped into the middle, an exception swallowed by an outer try, a fixture that stopped producing rows. All of those end with a small count, zero failures, and exit 0, which reads as green everywhere
it is reported.
"""

import pytest

from rediacc_ci.controls import Controls, VacuousPlantError, plant, plant_re


def test_a_clean_run_is_ok():
    c = Controls("clean", floor=1)
    c.check("one", 1, 1)
    assert c.ok


def test_a_failing_control_is_not_ok():
    """CONTROL for the case above: the harness must be able to go red at all."""
    c = Controls("dirty", floor=1)
    c.check("one", 1, 2)
    assert not c.ok


def test_a_failure_records_its_label_not_just_a_count():
    c = Controls("named", floor=1)
    c.check("the label that matters", "got", "want")
    assert c.failures == ["the label that matters"]


def test_a_pass_records_nothing():
    c = Controls("named", floor=1)
    c.check("the label that matters", "same", "same")
    assert c.failures == []


def test_every_assertion_increments_the_count():
    c = Controls("counting", floor=0)
    c.check("a", 1, 1)
    c.truthy("b", 1)
    c.falsy("c", 0)
    c.fail("d")
    assert c.count == 4


# --------------------------------------------------------------------------- The assertions return their outcome, which the copies do not ---------------------------------------------------------------------------


def test_check_returns_the_outcome():
    c = Controls("returns", floor=0)
    assert c.check("passes", 1, 1) is True
    assert c.check("fails", 1, 2) is False


def test_truthy_and_falsy_are_one_sided():
    c = Controls("sided", floor=0)
    assert c.truthy("a non-empty list is truthy", [0]) is True
    assert c.truthy("an empty list is not", []) is False
    assert c.falsy("an empty string is falsy", "") is True
    assert c.falsy("a non-empty one is not", "x") is False


def test_falsy_says_what_it_wanted(capsys):
    """The message the `control(..., bool(x), False)` workaround cannot produce.

    Squeezing a one-sided assertion through the two-sided one reports "got False, wanted False" on failure, which is a contradiction printed at a human who then has to read the test to find out what happened.
    """
    c = Controls("message", floor=0)
    c.falsy("a truthy value", "surprise")
    err = capsys.readouterr().err
    assert "wanted 'something falsy'" in err
    assert "got 'surprise'" in err


# --------------------------------------------------------------------------- raises(): the error paths none of the five copies could express ---------------------------------------------------------------------------


def test_raises_passes_when_the_expected_exception_arrives():
    c = Controls("raises", floor=0)

    def boom():
        raise ValueError("expected")

    assert c.raises("ValueError is raised", ValueError, boom) is True
    assert c.failures == []


def test_raises_fails_when_nothing_is_raised():
    c = Controls("raises", floor=0)
    assert c.raises("nothing raised", ValueError, lambda: None) is False
    assert c.failures == ["nothing raised"]


def test_raises_lets_an_unexpected_exception_through():
    """A DIFFERENT exception is a bug in the test, not a finding.

    Catching it here would turn "the code under test broke in a new way" into a tidy one-line FAIL, which is exactly the information a traceback carries and a label does not.
    """
    c = Controls("raises", floor=0)

    def boom():
        raise KeyError("not what was asked for")

    with pytest.raises(KeyError):
        c.raises("wrong type", ValueError, boom)


def test_raises_passes_arguments_through():
    c = Controls("raises", floor=0)

    def needs_args(a, b=0):
        raise RuntimeError("%d/%d" % (a, b))

    assert c.raises("args reach the callable", RuntimeError, needs_args, 1, b=2) is True


# --------------------------------------------------------------------------- The floor: the reason this class exists at all ---------------------------------------------------------------------------


def test_the_floor_refuses_a_suite_that_ran_too_few_controls():
    c = Controls("short", floor=5)
    c.check("only one ran", 1, 1)
    assert not c.floor_met
    assert not c.ok


def test_the_floor_is_satisfied_by_enough_controls():
    """CONTROL: the floor is a comparison, not a permanent refusal."""
    c = Controls("long enough", floor=2)
    c.check("a", 1, 1)
    c.check("b", 2, 2)
    assert c.floor_met
    assert c.ok


def test_a_short_suite_with_no_failures_is_still_red():
    """THE FAILURE THE FLOOR EXISTS FOR.

    Zero failures and a small count is precisely what a suite whose controls stopped executing looks like, and it is indistinguishable from a green run by every other measure.
    """
    c = Controls("silent", floor=10)
    assert c.failures == []
    assert not c.ok


def test_the_floor_message_is_the_one_the_copies_print(capsys):
    c = Controls("short", floor=3)
    c.check("a", 1, 1)
    assert c.report() is False
    err = capsys.readouterr().err
    assert "FAIL  only 1 control(s) ran; the file is not being executed as written" in err


def test_the_floor_counts_as_a_failure_in_the_summary(capsys):
    c = Controls("short", floor=3)
    c.check("a", 1, 1)
    c.report()
    assert "FAIL: 1 of 1 control(s) failed" in capsys.readouterr().err


def test_a_negative_floor_is_a_programming_error():
    # `match` is not decoration: PT011 refuses a bare ValueError because it matches any ValueError raised anywhere inside the block, including one raised by the test's own setup. Anchoring on the word the message must carry is what makes this assert the intended failure.
    with pytest.raises(ValueError, match="floor must not be negative"):
        Controls("bad", floor=-1)


def test_a_zero_floor_is_allowed_but_has_to_be_typed():
    """Writable, deliberately -- a suite built at runtime has no fixed count -- but only at the call site, where a reviewer sees the number."""
    assert Controls("runtime built", floor=0).floor == 0


# --------------------------------------------------------------------------- The output contract the harness parses ---------------------------------------------------------------------------


def test_a_green_report_prints_the_legacy_line_on_stdout(capsys):
    c = Controls("green", floor=2)
    c.check("a", 1, 1)
    c.check("b", 1, 1)
    assert c.report() is True
    out = capsys.readouterr()
    assert out.out.strip() == "2 control(s) passed"
    assert out.err == ""


def test_a_failure_line_names_got_and_wanted_on_stderr(capsys):
    c = Controls("red", floor=0)
    c.check("the label", "actual", "expected")
    err = capsys.readouterr().err
    assert err.strip() == "FAIL  the label: got 'actual', wanted 'expected'"


def test_a_red_report_prints_nothing_on_stdout(capsys):
    """A red suite whose verdict lands on stdout is a red the harness can miss, and stdout is where the SUCCESS line lives."""
    c = Controls("red", floor=0)
    c.check("a", 1, 2)
    c.report()
    assert capsys.readouterr().out == ""


def test_verbose_prints_a_line_per_passing_control(capsys):
    c = Controls("verbose", floor=0, verbose=True)
    c.check("a", 1, 1)
    assert "ok    a" in capsys.readouterr().out


def test_quiet_is_the_default(capsys):
    """CONTROL for the case above: verbosity is a choice, not the behaviour."""
    c = Controls("quiet", floor=0)
    c.check("a", 1, 1)
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------- exit(): the last line of a migrated file ---------------------------------------------------------------------------


def test_exit_is_zero_when_green():
    c = Controls("green", floor=1)
    c.check("a", 1, 1)
    with pytest.raises(SystemExit) as caught:
        c.exit()
    assert caught.value.code == 0


def test_exit_is_one_when_red():
    c = Controls("red", floor=1)
    c.check("a", 1, 2)
    with pytest.raises(SystemExit) as caught:
        c.exit()
    assert caught.value.code == 1


def test_exit_is_one_when_only_the_floor_failed():
    c = Controls("short", floor=99)
    c.check("a", 1, 1)
    with pytest.raises(SystemExit) as caught:
        c.exit()
    assert caught.value.code == 1


# --------------------------------------------------------------------------- No global state, which is what the `class Tally` copies all had ---------------------------------------------------------------------------


def test_two_runners_do_not_share_state():
    """`class Tally` with class attributes is shared by every instance and every importer. Two suites in one process silently added up."""
    a = Controls("a", floor=0)
    b = Controls("b", floor=0)
    a.check("only a", 1, 2)
    assert a.count == 1
    assert b.count == 0
    assert b.failures == []


def test_a_runner_keeps_its_name():
    assert Controls("wl_planfile", floor=1).name == "wl_planfile"


# ---- plant() / plant_re(): a mutant that does not mutate --------------------
#
# THE ASYMMETRY THIS MODULE'S HEADER NAMES APPLIES HARDEST HERE. `plant` exists so a control cannot silently feed its gate the CLEAN fixture and report a pass
# for an assertion it never made. A `plant` that raised on everything would
# satisfy every refusal case below, so each one is paired with the mutation it must still perform.


def test_plant_performs_the_mutation_it_is_asked_for():
    """The happy path FIRST, or every refusal below is met by a broken plant."""
    assert plant("a b", "b", "c") == "a c"
    assert plant("aa", "a", "b") == "bb", "every occurrence, not just the first"
    assert plant("aa", "a", "b", 1) == "ba", "and count= still bounds it"


def test_plant_refuses_a_needle_that_is_not_there():
    with pytest.raises(VacuousPlantError) as exc:
        plant("a b", "zzz", "c")
    assert "zzz" in str(exc.value), "the message names the needle that was missing"
    assert "CLEAN input" in str(exc.value), "and says what the control would have run against"


def test_plant_refuses_replacing_a_string_with_itself():
    """ITS OWN REFUSAL, distinct from the missing-needle one, because it is a different author mistake: a typo, not a drifted fixture. This is the case that catches the real one found in the tree on 2026-09-08 --
    `_FIXTURE_HEALTHY.replace("max_turns=140", "max_turns=140")` in
    `rediacc_ci/quality/review_turn_capacity.py`, a dead leg chained ahead of a live substitution inside the port of the very gate `control_vacuity` uses as its own control."""
    with pytest.raises(VacuousPlantError) as exc:
        plant("max_turns=140 here", "max_turns=140", "max_turns=140")
    # ASSERT ON WHAT ONLY THIS BRANCH SAYS. `old == new` is also caught further
    # down by the byte-identical check, so a looser assertion here (the word "identical", say) passes whether or not this refusal exists at all -- it re-asks a question the next branch already answers. Verified by planting:
    # deleting the `old == new` arm leaves the suite green under the loose form
    # and reds it under this one.
    assert "with itself" in str(exc.value), "the typo case keeps its own diagnosis"
    # MIRROR: the same call with a genuinely different replacement is fine.
    assert plant("max_turns=140 here", "max_turns=140", "max_turns=9") == "max_turns=9 here"


def test_plant_refuses_a_count_that_replaces_nothing():
    """`count=0` is the ONE way to reach the byte-identical arm: the needle is
    present and differs from its replacement, yet nothing is substituted. Found by planting -- deleting that arm left the suite green until this case existed, which meant the branch was asserted by nothing."""
    with pytest.raises(VacuousPlantError) as exc:
        plant("aa", "a", "b", 0)
    assert "byte-identical" in str(exc.value)


def test_plant_refuses_an_empty_needle():
    with pytest.raises(VacuousPlantError):
        plant("anything", "", "x")


def test_plant_re_matches_or_refuses():
    assert plant_re("a1b", r"\d", "X") == "aXb"
    with pytest.raises(VacuousPlantError) as exc:
        plant_re("ab", r"\d", "X")
    assert "zero times" in str(exc.value)


def test_plant_re_refuses_a_match_that_changes_nothing():
    """A pattern CAN match and still produce identical bytes -- the count check alone would pass this, so the byte comparison is not redundant."""
    with pytest.raises(VacuousPlantError) as exc:
        plant_re("abc", r"b", "b")
    assert "byte-identical" in str(exc.value)
