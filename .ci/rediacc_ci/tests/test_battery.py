"""`rediacc_ci.battery` against `.ci/scripts/test/run-all.sh`, the runner it replaces.

WHAT IS WORTH TESTING HERE, and it is not "does it run 148 shell scripts". The
scheduling is the cheap part; the VERDICT is where a runner goes silently wrong, and
run-all.sh's header is a list of the ways it did:

  * a test the scheduler lost, reported as a shorter green run rather than a red one,
  * a test that exits 0 having asserted nothing, indistinguishable from a good one,
  * a `PASS:` pattern spelled `\\x1b` instead of the real escape byte, which matched
    NOTHING while the counter stayed right -- "20 passed" with no assertions listed
    reads exactly like 20 tests that assert nothing,
  * a glob that stops matching, reporting success having run nothing,
  * and two schedulers deciding isolation separately and disagreeing.

Each of those is a case below, driven against a fixture battery rather than the real
one, so a control that is supposed to go RED can be planted without touching a tree
other sessions are working in.

THE PROGRAM IS ALSO DRIVEN AS A PROGRAM. Exit codes and stream separation are
invisible to a function-level test: `--selftest` must exit 0, a vacuous fixture must
exit 1, and an absent bash must exit 77 and NOT 1, because 77 is this repo's
"no verdict was reached" and 1 would say the battery judged the code and found it bad.
"""

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import battery, paths

BATTERY = paths.from_root(".ci", "rediacc_ci", "battery.py")
TWIN = paths.from_root(".ci", "scripts", "test", "run-all.sh")


def _fixture_battery(base: pathlib.Path, **scripts: str) -> tuple[pathlib.Path, pathlib.Path]:
    gates = base / "gates"
    gates.mkdir(exist_ok=True)
    for name, body in scripts.items():
        path = gates / (name.replace("_", "-") + ".sh")
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    lock = base / "lock.json"
    if not lock.exists():
        lock.write_text("[]", encoding="utf-8")
    return gates, lock


def _run_program(args, env=None, cwd=None):
    merged = dict(os.environ)
    merged.update(env or {})
    return subprocess.run(
        [sys.executable, str(BATTERY), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd or paths.repo_root()),
        env=merged,
        timeout=600,
    )


# -- the verdict, which is the part that goes silently wrong -----------------


def test_a_test_that_exits_zero_asserting_nothing_is_a_failure(tmp_path):
    gates, lock = _fixture_battery(
        tmp_path,
        test_green="#!/bin/bash\necho 'PASS: held'\n",
        test_vacuous="#!/bin/bash\necho 'ran, asserted nothing'\n",
    )
    report = battery.run_battery(gates_dir=gates, root=tmp_path, lock_path=lock, check_tree=False)
    assert not report.ok
    assert any("made no assertions" in f for f in report.failed)
    # And the green one still counted, so this is a per-test verdict and not a
    # whole-battery panic.
    assert report.passed == 1


def test_a_lost_result_is_a_failure_and_never_a_skip():
    outcome = battery.Outcome("test-x.sh")
    assert outcome.verdict == "lost"
    report = battery.Report()
    battery.score(outcome, report)
    assert report.passed == 0
    assert report.failed == ["test-x.sh (no result recorded)"]


def test_a_glob_that_matches_nothing_is_a_failure(tmp_path):
    gates, lock = _fixture_battery(tmp_path, test_green="#!/bin/bash\necho 'PASS: held'\n")
    report = battery.run_battery(
        gates_dir=gates, root=tmp_path, lock_path=lock, pattern="test-absent-*.sh", check_tree=False
    )
    assert not report.ok
    assert any("matched NO test" in f for f in report.failed)


def test_the_pass_predicate_sees_the_real_escape_byte(tmp_path):
    # THE DEFECT THIS EXISTS FOR. run-all.sh once spelled the escape as the literal
    # text "x1b", so every colour-emitting gate test contributed zero assertions
    # while the pass counter stayed right.
    gates, lock = _fixture_battery(
        tmp_path,
        test_coloured="#!/bin/bash\nprintf '\\033[0;32mPASS:\\033[0m coloured\\n'\n",
    )
    report = battery.run_battery(gates_dir=gates, root=tmp_path, lock_path=lock, check_tree=False)
    assert report.ok
    assert report.assertions == 1


def test_a_line_merely_containing_the_word_pass_is_not_an_assertion():
    assert battery.PASS_RE.findall("we should PASS: eventually\n") == []
    assert battery.PASS_RE.findall("FAIL: no\n") == []
    assert battery.PASS_RE.findall("PASS: yes\n") == ["PASS:"]


# -- isolation, read from the lock -------------------------------------------


def test_isolation_is_read_from_the_lock_in_both_directions(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            [
                {"id": "w", "run": ".ci/scripts/test/gates/test-w.sh", "mutex": ["tree:scripts"]},
                {"id": "s", "run": ".ci/scripts/test/gates/test-s.sh", "reads": ["tree:scripts"]},
                {"id": "t", "run": ".ci/scripts/test/gates/test-t.sh"},
                {"id": "n", "run": ".ci/scripts/test/gates/test-n.sh", "mutex": ["renet-bin"]},
                {"id": "o", "run": "npm run check:other", "mutex": ["tree:scripts"]},
            ]
        ),
        encoding="utf-8",
    )
    schedule = battery.build_schedule(lock)
    assert schedule.source == "lock"
    assert schedule.bucket("test-w.sh") == "W"
    assert schedule.bucket("test-s.sh") == "S"
    assert schedule.bucket("test-t.sh") == "T"
    # A mutex that is not a `tree:` resource is about something else entirely
    # (renet-bin, the account vitest state); it must not make a real-tree writer.
    assert schedule.bucket("test-n.sh") == "T"
    # And a non-gate-test entry contributes nothing here even when it claims a tree.
    assert "check:other" not in schedule.writers


def test_an_unreadable_lock_classifies_nothing_rather_than_guessing(tmp_path):
    assert battery.classify_from_lock(tmp_path / "absent.json", "mutex") == set()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert battery.classify_from_lock(broken, "mutex") == set()


def test_an_undeclared_lock_degrades_to_serial_and_says_so(tmp_path):
    gates, lock = _fixture_battery(tmp_path, test_green="#!/bin/bash\necho 'PASS: held'\n")
    report = battery.run_battery(
        gates_dir=gates, root=tmp_path, lock_path=lock, jobs=8, check_tree=False
    )
    assert report.schedule_source == "undeclared"
    # THE POINT: a requested 8 is IGNORED while the contract is unknown. Serial is
    # the only safe choice; classifying every test as fixture-isolated is a guess.
    assert report.jobs == 1
    assert any("manifest.ts" in line for line in report.notices)
    assert report.ok


def test_a_declared_lock_restores_the_requested_worker_count(tmp_path):
    gates, lock = _fixture_battery(tmp_path, test_green="#!/bin/bash\necho 'PASS: held'\n")
    lock.write_text(
        json.dumps([{"id": "g", "run": ".ci/scripts/test/gates/test-x.sh", "reads": ["tree:y"]}]),
        encoding="utf-8",
    )
    report = battery.run_battery(
        gates_dir=gates, root=tmp_path, lock_path=lock, jobs=4, check_tree=False
    )
    assert report.jobs == 4
    assert report.schedule_source == "lock"
    assert report.notices == []


def test_the_env_seam_overrides_membership(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_ALL_WRITERS", "test-a.sh test-b.sh")
    monkeypatch.setenv("RUN_ALL_SCANNERS", "test-c.sh")
    schedule = battery.build_schedule(tmp_path / "absent.json")
    assert schedule.source == "env"
    assert schedule.bucket("test-a.sh") == "W"
    assert schedule.bucket("test-c.sh") == "S"
    assert schedule.bucket("test-d.sh") == "T"


def test_the_live_lock_is_read_by_the_same_code_the_twin_uses(tmp_path):
    """THE CLAIM THIS FILE IS HERE TO KEEP HONEST: the two runners must not decide
    isolation separately. run-all.sh classifies with an inline python3 heredoc over
    the same lock; drive it and require the same answer on the REAL file."""
    lock = paths.from_root("scripts", "ci-runner", "gates.lock.json")
    twin_source = TWIN.read_text(encoding="utf-8")
    start = twin_source.index('python3 - "$GATES_LOCK" "$1" <<\'CLASSIFY\'')
    program = twin_source[
        twin_source.index("\n", start) + 1 : twin_source.index("\nCLASSIFY", start)
    ]
    script = tmp_path / "classify.py"
    script.write_text(program, encoding="utf-8")

    def twin_answer(lock_path, claim):
        proc = subprocess.run(
            [sys.executable, str(script), str(lock_path), claim],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        return {ln for ln in proc.stdout.split() if ln}

    for claim in ("mutex", "reads"):
        assert battery.classify_from_lock(lock, claim) == twin_answer(lock, claim)

    # THE AGREEMENT ABOVE WAS VACUOUS UNTIL 2026-09-07, and the assertion that used
    # to sit here is what said so. Then: ZERO of the 148 gate-test entries in the
    # live lock declared `mutex`, `reads`, `heavy` or `weight`, so both readers
    # correctly answered with the empty set and "they agree" was a claim about
    # nothing -- two readers returning nothing agree the way two broken clocks do.
    # That state was pinned with `== set()` and a message telling whoever landed the
    # declarations to delete it.
    #
    # They landed. W2.4's missing half was a MISSING TYPE: `gate-spec.ts` declared
    # `mutex?: string[]` and had no `reads` field at all, so the 21 scanner gate
    # tests were undeclarable while the battery asked `classify_from_lock` for
    # exactly that claim. The lock now carries `mutex: ['tree:repo']` on the 4
    # real-tree writers and `reads: ['tree:repo']` on the 21 scanners.
    #
    # So the live comparison now has an answer, and it is ASSERTED NON-EMPTY rather
    # than assumed to be. A lock that silently lost its declarations again would
    # otherwise slide back into the vacuous state while this test stayed green,
    # which is the exact failure the old assertion existed to make visible.
    live_writers = battery.classify_from_lock(lock, "mutex")
    live_scanners = battery.classify_from_lock(lock, "reads")
    assert live_writers, (
        "the live lock declares no `mutex: [tree:*]` gate test at all, so comparing "
        "the two readers on it compares nothing. Restore the declarations before "
        "trusting this test's green."
    )
    assert live_scanners, (
        "the live lock declares no `reads: [tree:*]` gate test at all, so comparing "
        "the two readers on it compares nothing. Restore the declarations before "
        "trusting this test's green."
    )

    # The comparison is ALSO repeated on a SYNTHETIC lock carrying every shape the
    # readers have to tell apart, because the live lock exercises only the shapes it
    # happens to use today.
    synthetic = tmp_path / "synthetic.json"
    synthetic.write_text(
        json.dumps(
            [
                {"id": "w", "run": ".ci/scripts/test/gates/test-w.sh", "mutex": ["tree:scripts"]},
                {
                    "id": "w2",
                    "run": "bash .ci/scripts/test/gates/test-w2.sh --flag",
                    "mutex": ["tree:.ci/scripts", "renet-bin"],
                },
                {"id": "s", "run": ".ci/scripts/test/gates/test-s.sh", "reads": ["tree:scripts"]},
                {"id": "t", "run": ".ci/scripts/test/gates/test-t.sh"},
                {"id": "n", "run": ".ci/scripts/test/gates/test-n.sh", "mutex": ["renet-bin"]},
                {"id": "o", "run": "npm run check:other", "mutex": ["tree:scripts"]},
                "not-a-dict",
            ]
        ),
        encoding="utf-8",
    )
    assert battery.classify_from_lock(synthetic, "mutex") == {"test-w.sh", "test-w2.sh"}
    for claim in ("mutex", "reads"):
        assert battery.classify_from_lock(synthetic, claim) == twin_answer(synthetic, claim)


# -- the program, driven as a program ----------------------------------------


def test_the_selftest_exits_zero_and_prints_a_floored_control_count():
    proc = _run_program(["--selftest"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "control(s) passed" in proc.stdout
    # A floored tally, so a file whose controls stopped executing cannot report
    # green with a small number.
    count = int(proc.stdout.rsplit("\n", 2)[-2].split()[0])
    assert count >= 22


def test_the_selftest_writes_nothing_to_stderr(tmp_path):
    """A green run must not print a FAIL line anywhere.

    The selftest plants a deliberately vacuous fixture test and requires the runner
    to refuse it. That refusal used to print `FAIL: test-vacuous.sh exited 0 without
    a single PASS: line` onto the real stderr of a PASSING selftest -- a scary line
    on a green run, which is exactly how a reader is trained to stop reading stderr.
    The fixture runs are `quiet=True`; this keeps them that way.
    """
    proc = _run_program(["--selftest"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stderr == "", proc.stderr
    # CONTROL: the block printer is not simply dead. A non-quiet fixture run still
    # says the same thing, so `quiet` suppresses output rather than removing the
    # refusal.
    gates, lock = _fixture_battery(tmp_path, test_vacuous="#!/bin/bash\necho 'asserted nothing'\n")
    loud = battery.run_battery(
        gates_dir=gates, root=tmp_path, lock_path=lock, check_tree=False, env={}
    )
    assert not loud.ok
    quiet = battery.run_battery(
        gates_dir=gates, root=tmp_path, lock_path=lock, check_tree=False, env={}, quiet=True
    )
    assert not quiet.ok
    assert loud.failed == quiet.failed


def test_the_selftest_is_hermetic_against_an_ambient_env_seam():
    """THE DEFECT THIS PINS, found 2026-09-07 by the runner refusing to report.

    `battery.py` was driven on a shell that had exported RUN_ALL_WRITERS for the
    bash twin. `build_schedule` read os.environ directly, so four controls asserting
    on the SOURCE of a schedule got "env" where they wanted "lock" or "undeclared",
    and the runner declared its own controls broken rather than judging the battery.
    That refusal was correct; a control whose verdict depends on an ambient variable
    is a control that passes or fails for reasons the reader cannot see.
    """
    poisoned = {"RUN_ALL_WRITERS": "test-poison.sh", "RUN_ALL_SCANNERS": "test-poison2.sh"}
    proc = _run_program(["--selftest"], env=poisoned)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    clean = _run_program(["--selftest"], env={"RUN_ALL_WRITERS": "", "RUN_ALL_SCANNERS": ""})
    assert clean.returncode == 0, clean.stdout + clean.stderr
    # CONTROL FOR THE SEAM: it is still live, so `env={}` inside the selftest is a
    # deliberate isolation rather than a variable nothing reads.
    schedule = battery.build_schedule(
        paths.from_root("scripts", "ci-runner", "gates.lock.json"), env=poisoned
    )
    assert schedule.source == "env"
    assert schedule.bucket("test-poison.sh") == "W"
    assert schedule.bucket("test-poison2.sh") == "S"


def test_list_prints_the_shape_and_the_undeclared_notice():
    proc = _run_program(["--list"])
    assert proc.returncode == 0, proc.stderr
    last = proc.stdout.strip().splitlines()[-1]
    assert "test(s):" in last
    assert " W, " in last
    assert " S, " in last
    assert " T " in last
    # 148 gate tests exist on disk; the count is read from the tree, never typed.
    on_disk = len(list(paths.from_root(*battery.GATES_SUBDIR).glob("test-*.sh")))
    assert last.startswith("%d test(s):" % on_disk)
    assert on_disk > 0


def test_a_vacuous_fixture_battery_exits_one_as_a_program(tmp_path):
    gates, _lock = _fixture_battery(tmp_path, test_vacuous="#!/bin/bash\necho 'asserted nothing'\n")
    proc = _run_program(["--jobs", "1"], env={"RUN_ALL_GATES_DIR": str(gates)})
    assert proc.returncode == 1
    assert "without a single PASS: line" in proc.stderr


def test_an_absent_bash_is_77_and_never_1():
    """77 is BLOCKED, not FAILED. Returning 1 here would say the battery judged the
    code and found it bad, which is false, and it is what made a pre-push lane refuse
    every push on a machine that simply lacked a tool."""
    proc = _run_program([], env={"PATH": "/nonexistent-for-this-control"})
    assert proc.returncode == 77, proc.stdout + proc.stderr
    assert "bash is not on PATH" in proc.stderr
    assert "NOT skipping" in proc.stderr


def test_an_absent_gates_directory_is_a_failure_not_a_pass(tmp_path):
    proc = _run_program([], env={"RUN_ALL_GATES_DIR": str(tmp_path / "nope")})
    assert proc.returncode == 1
    assert "does not exist" in proc.stderr


# -- the tracked-tree guard --------------------------------------------------


def test_the_tracked_tree_guard_notices_a_modified_tracked_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *argv], cwd=str(repo), check=True, capture_output=True, timeout=120)
    tracked = repo / "tracked.txt"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True, timeout=120
    )
    subprocess.run(
        ["git", "commit", "-qm", "seed"],
        cwd=str(repo),
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert battery.tree_state(repo) == ""

    gates, lock = _fixture_battery(
        repo,
        test_writer="#!/bin/bash\necho 'PASS: wrote'\necho changed >'%s'\n" % tracked,
    )
    report = battery.run_battery(gates_dir=gates, root=repo, lock_path=lock, check_tree=True)
    assert not report.ok
    assert any("left a tracked file modified" in f for f in report.failed)

    # CONTROL FOR THE PLANT. Restore the file and the same battery is green, so the
    # refusal above is caused by the modification and not by the fixture repo.
    tracked.write_text("original\n", encoding="utf-8")
    (gates / "test-writer.sh").write_text(
        "#!/bin/bash\necho 'PASS: wrote nothing'\n", encoding="utf-8"
    )
    (gates / "test-writer.sh").chmod(0o755)
    report = battery.run_battery(gates_dir=gates, root=repo, lock_path=lock, check_tree=True)
    assert report.ok


@pytest.mark.parametrize(
    ("recorded", "rc", "assertions", "expected"),
    [
        (True, 0, 3, "pass"),
        (True, 1, 3, "fail"),
        (True, 1, 0, "fail"),
        (True, 0, 0, "vacuous"),
        (False, None, 0, "lost"),
    ],
)
def test_the_verdict_matrix(recorded, rc, assertions, expected):
    outcome = battery.Outcome("test-x.sh")
    outcome.recorded, outcome.rc, outcome.assertions = recorded, rc, assertions
    assert outcome.verdict == expected
