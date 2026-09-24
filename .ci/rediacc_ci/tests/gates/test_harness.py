"""Controls for `harness.py` itself, in BOTH directions for every helper.

WHY THIS FILE EXISTS SEPARATELY FROM THE PORTS. The ported gate tests are evidence about their subjects; they are evidence about the harness only by accident, and only in the directions they happen to exercise. `assert_not_contains` is used by four ports and NONE of them ever supplies a haystack that does contain the needle, so a version of it that never fired would pass every one
of them. A helper with only positive controls will happily flag, or fail to flag, the whole tree.

So each helper is driven twice: once with an input that must be accepted, once with an input that must be REFUSED. The refusals are checked with `pytest.raises` rather than through the harness's own comparison, which keeps the failure direction from being decided by the very method under test.

THE SUBJECT IS AN INNER `Harness`; the outer `gate` fixture is the instrument. Two instances, so a control recorded on the subject cannot satisfy the instrument's own anti-vacuity floor and vice versa.
"""

import json
import os
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci.tests.gates import harness


def subject() -> harness.Harness:
    return harness.Harness("test_harness", "subject")


def test_log_pass_records_and_log_fail_raises(gate):
    inner = subject()
    inner.log_pass("something proved")
    gate.assert_eq(
        inner.passes, ["something proved"], "log_pass records the label, not just a count"
    )
    with pytest.raises(harness.GateAssertionError, match="the sky fell"):
        inner.log_fail("the sky fell")
    gate.log_pass("log_pass records and log_fail raises GateAssertionError carrying its message")


def test_assert_eq_both_directions_and_argument_order(gate):
    inner = subject()
    inner.assert_eq("a", "a", "equal values pass")
    gate.assert_eq(inner.assertions, 1, "a passing assertion is still counted")
    with pytest.raises(harness.GateAssertionError) as caught:
        inner.assert_eq("got-this", "wanted-that", "the message")
    # ACTUAL FIRST, EXPECTED SECOND, exactly as in test-helpers.sh. A port that swapped them would still raise here, so the message is what pins the order.
    gate.assert_contains(
        str(caught.value),
        "expected 'wanted-that', got 'got-this'",
        "assert_eq(actual, expected) keeps the bash argument order",
    )
    gate.log_pass(
        "assert_eq passes on equal, raises on unequal, and reports actual/expected in the bash order"
    )


def test_assert_contains_and_not_contains_both_directions(gate):
    inner = subject()
    inner.assert_contains("haystack with needle", "needle")
    inner.assert_not_contains("haystack", "needle")
    with pytest.raises(harness.GateAssertionError, match="substring missing"):
        inner.assert_contains("haystack", "needle")
    with pytest.raises(harness.GateAssertionError, match="unexpected substring present"):
        inner.assert_not_contains("haystack with needle", "needle")
    gate.assert_eq(inner.assertions, 4, "all four calls are counted, passing and failing alike")
    gate.log_pass("assert_contains and assert_not_contains each fire in both directions")


def test_assert_exit_code_keeps_the_opposite_argument_order(gate):
    inner = subject()
    inner.assert_exit_code(0, 0, "a matching code passes")
    with pytest.raises(harness.GateAssertionError) as caught:
        inner.assert_exit_code(1, 77, "the message")
    # EXPECTED FIRST for this one, the reverse of assert_eq. Normalising the pair would silently invert every existing call site, so the difference is pinned.
    gate.assert_contains(
        str(caught.value), "expected 1, got 77", "assert_exit_code(expected, actual)"
    )
    gate.log_pass("assert_exit_code passes on a match and reports expected-then-actual on a miss")


OUT_SENTINEL = "OUT-SENTINEL-7f3a"
ERR_SENTINEL = "ERR-SENTINEL-c41e"


def _noisy_run() -> harness.RunResult:
    return harness.run(
        ["bash", "-c", "echo %s; echo %s >&2; exit 5" % (OUT_SENTINEL, ERR_SENTINEL)]
    )


def _failure_text(action) -> str:
    try:
        action()
    except harness.GateAssertionError as caught:
        return str(caught)
    return "no failure raised"


def _output_problems(text: str) -> list[str]:
    """Everything wrong with a failure message that claims to carry a run's output.

    ONE CHECKER FOR THE REAL RUN AND THE PLANTED DEFECTS, so the planted runs prove this very function fires rather than a sibling written to be easy to satisfy.
    """
    problems = []
    if OUT_SENTINEL not in text:
        problems.append("stdout missing")
    if ERR_SENTINEL not in text:
        problems.append("stderr missing")
    out_label, err_label = text.find("--- stdout ---"), text.find("--- stderr ---")
    if not (0 <= out_label < text.find(OUT_SENTINEL) < err_label < text.find(ERR_SENTINEL)):
        problems.append("the streams are not labelled in order")
    return problems


def test_assert_exit_carries_the_subjects_output_on_failure(gate, monkeypatch):
    result = _noisy_run()
    inner = subject()
    inner.assert_exit(5, result, "a matching code passes")
    gate.assert_eq(inner.assertions, 1, "a passing assert_exit is still counted")
    gate.ok("assert_exit accepts a run whose exit code matches")

    text = _failure_text(lambda: inner.assert_exit(0, result, "the message"))
    gate.assert_contains(text, "the message: expected 0, got 5", "expected first, then actual")
    gate.assert_eq(_output_problems(text), [], "the failure carries both streams, labelled")
    gate.ok("control: a failing assert_exit carries the subject's stdout and stderr")

    completed = subprocess.run(
        ["bash", "-c", "echo %s; echo %s >&2; exit 3" % (OUT_SENTINEL, ERR_SENTINEL)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = _failure_text(lambda: inner.assert_exit(0, completed, "a CompletedProcess"))
    gate.assert_eq(_output_problems(text), [], "a CompletedProcess carries its streams too")
    gate.ok("control: a subprocess.CompletedProcess is accepted and its output attached")

    text = _failure_text(lambda: inner.log_fail("a hand-written failure", result))
    gate.assert_eq(_output_problems(text), [], "log_fail(message, result) attaches the output")
    gate.ok("control: log_fail attaches a run's output when handed the run")

    long = harness.run(["bash", "-c", "head -c 9000 /dev/zero | tr '\\0' x; echo; echo TAIL-END"])
    text = _failure_text(lambda: inner.assert_exit(1, long, "a long run"))
    gate.assert_contains(text, "TAIL-END", "the end of a long stream survives the cut")
    gate.assert_contains(text, "earlier chars dropped", "and the cut says so")
    gate.ok("control: a long stream keeps its tail and names what it dropped")

    # PLANTED DEFECTS. Each one is a harness that has regressed to the shape this helper replaced, and the checker above must refuse every one; a checker that passed any of them would have proved nothing about the real run.
    planted = {
        "the output is dropped": lambda _run: "",
        "only stderr is kept": lambda run: "--- stderr ---\n%s" % run.err,
        "the streams are swapped": lambda run: (
            "--- stdout ---\n%s\n--- stderr ---\n%s" % (run.err, run.out)
        ),
    }
    for defect, render in planted.items():
        with monkeypatch.context() as patch:
            patch.setattr(harness, "render_output", render)
            text = _failure_text(lambda: subject().assert_exit(0, result, "planted"))
        if _output_problems(text):
            gate.ok("planted defect caught: %s" % defect)
        else:
            gate.no("planted defect NOT caught: %s" % defect)
    gate.tally_finish("assert_exit output attachment")


def test_temp_dir_removes_its_directory_even_when_the_body_raises(gate):
    with harness.temp_dir() as path:
        (path / "file").write_text("x", encoding="utf-8")
        kept = path
    gate.assert_eq(kept.exists(), False, "the directory is gone after a clean exit")

    escaped = []

    def raising_body() -> None:
        with harness.temp_dir() as path:
            escaped.append(path)
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        raising_body()
    gate.assert_eq(escaped[0].exists(), False, "and gone after the body raises")
    gate.log_pass("temp_dir cleans up on both the clean and the raising path")


def test_fake_gh_shims_gh_and_restores_path(gate, tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text('{"tagName":"v9.9.9"}\n', encoding="utf-8")
    before = os.environ.get("PATH")
    with harness.fake_gh(payload):
        result = harness.run(["gh", "api", "whatever"])
        gate.assert_exit(0, result, "the shim runs")
        gate.assert_contains(result.out, "v9.9.9", "and serves the fixture bytes")
    gate.assert_eq(os.environ.get("PATH"), before, "PATH is restored on the way out")

    with pytest.raises(RuntimeError), harness.fake_gh(payload):
        raise RuntimeError("boom")
    gate.assert_eq(os.environ.get("PATH"), before, "PATH is restored after a raising body too")
    gate.log_pass("fake_gh serves the fixture and restores PATH on both paths")


def test_fake_bin_admits_only_what_the_spec_names(gate):
    with harness.fake_bin("+bash +env someprobe failing!3") as fakes:
        gate.assert_eq(
            os.environ["PATH"], str(fakes.dir), "PATH holds the fake directory and nothing else"
        )
        gate.assert_eq(
            shutil.which("someprobe"), str(fakes.dir / "someprobe"), "a named fake is reachable"
        )
        # THE DIRECTION THAT MATTERS. A denylist would leave this resolvable and the test would prove nothing about the binaries nobody thought to name.
        gate.assert_eq(shutil.which("curl"), None, "an UNNAMED binary is absent by construction")
        harness.run([str(fakes.dir / "someprobe"), "--flag", "value"])
        gate.assert_contains(fakes.record("someprobe"), "--flag value", "the fake records its argv")
        gate.assert_eq(fakes.record("nevercalled"), "", "a fake never called records nothing")
        gate.assert_exit(3, harness.run([str(fakes.dir / "failing")]), "name!<n> exits with <n>")
    gate.assert_eq(shutil.which("curl") is not None, True, "PATH is restored afterwards")
    gate.log_pass("fake_bin empties PATH, admits by name, records argv and honours name!<n>")


def test_fake_bin_refuses_a_plus_token_it_cannot_resolve(gate):
    with (
        pytest.raises(harness.GateAssertionError, match="no such binary on PATH"),
        harness.fake_bin("+definitely-not-a-real-binary-9f3a"),
    ):
        pass  # pragma: no cover -- the context manager raises before its body runs
    gate.log_pass("a `+name` for a binary that does not exist is a loud failure, not a silent skip")


def test_the_tally_verdict_fires_in_both_directions(gate):
    green = subject()
    green.ok("first control")
    green.ok("second control")
    green.tally_finish("a green subject")
    gate.assert_eq(green.tally_count, 2, "ok() counts")
    gate.assert_eq(green.tally_fails, 0, "and a green tally has no failures")

    red = subject()
    red.ok("this one held")
    red.no("this one did not")
    with pytest.raises(harness.GateAssertionError, match="1 of 2 control"):
        red.tally_finish("a red subject")
    gate.assert_eq(red.tally_fails, 1, "no() records a failure and KEEPS GOING")
    gate.log_pass(
        "tally_finish returns on a clean tally and raises with the bash verdict wording on a dirty one"
    )


def test_the_ledger_is_written_only_when_the_env_names_a_file(gate, tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    recorded = harness.Harness("m", "t", ledger=str(ledger))
    recorded.log_pass("one")
    recorded.ok("two")
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    gate.assert_eq(len(rows), 2, "both log_pass and ok reach the ledger")
    gate.assert_eq([r["event"] for r in rows], ["pass", "pass"], "and both are recorded as passes")
    gate.assert_eq(rows[0]["module"], "m", "the ledger keys on the module so parity can group")

    silent = harness.Harness("m", "t", ledger=None)
    silent.log_pass("three")
    gate.assert_eq(
        sorted(p.name for p in tmp_path.iterdir()),
        ["ledger.jsonl"],
        "with no ledger configured nothing is written anywhere",
    )
    gate.log_pass("the ledger records when configured and stays silent when it is not")


def test_run_keeps_the_two_streams_apart(gate):
    result = harness.run(["bash", "-c", "echo to-stdout; echo to-stderr >&2; exit 5"])
    gate.assert_exit(5, result, "the real exit code is returned")
    gate.assert_contains(result.out, "to-stdout", "stdout carries stdout")
    gate.assert_not_contains(
        result.out, "to-stderr", "and NOT stderr -- merging hides swallowed output"
    )
    gate.assert_contains(result.err, "to-stderr", "stderr carries stderr")
    gate.assert_contains(
        result.combined, "to-stdout", "combined offers both for twins that used 2>&1"
    )
    gate.assert_contains(result.combined, "to-stderr", "combined offers both")
    gate.log_pass("run() returns the real exit code and keeps stdout and stderr separate")


def test_run_overlays_the_environment_rather_than_replacing_it(gate):
    # The overlay is the half that matters: `env=` on subprocess REPLACES the whole
    # environment, so a fixture meaning to set one variable silently drops PATH and the failure arrives as "command not found" in a test about something else.
    result = harness.run(["bash", "-c", 'echo "$MY_PROBE|$PATH"'], env={"MY_PROBE": "set"})
    gate.assert_contains(result.out, "set|", "the overlay variable reaches the child")
    gate.assert_not_contains(result.out, "set|\n", "and PATH survived rather than being erased")
    gate.log_pass("run() overlays env onto os.environ instead of replacing it")


def test_assert_vacuous_tree_fails_accepts_a_refusing_gate_and_rejects_a_permissive_one(
    gate, tmp_path
):
    inner = subject()

    def refusing(path):
        return harness.RunResult(1, "nothing to assert in %s\n" % path, "")

    inner.assert_vacuous_tree_fails(refusing, tmp_path / "good", "nothing to assert", "must refuse")
    gate.assert_eq(len(inner.passes), 1, "a gate that refuses an empty tree passes the check")

    def permissive(path):  # noqa: ARG001
        return harness.RunResult(0, "all good\n", "")

    with pytest.raises(harness.GateAssertionError, match="must refuse"):
        inner.assert_vacuous_tree_fails(
            permissive, tmp_path / "bad", "nothing to assert", "must refuse"
        )
    gate.log_pass("assert_vacuous_tree_fails accepts a refusing gate and rejects a permissive one")


def test_the_harness_module_is_where_the_ported_tests_think_it_is(gate):
    # A cheap structural control: the vocabulary the ports call must all exist. A rename here is a red in every port, which is correct, but this names the missing method instead of leaving the reader with an AttributeError per file.
    expected = [
        "log_pass",
        "log_fail",
        "log_test",
        "log_info",
        "log_error",
        "assert_eq",
        "assert_contains",
        "assert_not_contains",
        "assert_exit_code",
        "assert_vacuous_tree_fails",
        "ok",
        "no",
        "tally_finish",
    ]
    missing = [name for name in expected if not hasattr(harness.Harness, name)]
    if missing:
        gate.log_fail(
            "harness.Harness is missing %d of test-helpers.sh's words: %s"
            % (len(missing), ", ".join(missing))
        )
    helpers = [
        "run",
        "temp_dir",
        "fake_gh",
        "fake_bin",
        "require_tool",
        "require_python_module",
        "RunResult",
        "GateAssertionError",
        "LEDGER_ENV",
    ]
    module_level = [name for name in helpers if not hasattr(harness, name)]
    if module_level:
        gate.log_fail("harness is missing %s" % ", ".join(module_level))
    gate.assert_eq(
        pathlib.Path(harness.__file__).name, "harness.py", "and it is the file the ports import"
    )
    gate.log_pass(
        "all %d Harness methods and %d module helpers of the ported vocabulary are present"
        % (len(expected), len(helpers))
    )


def test_run_replaces_the_environment_only_when_asked(gate):
    """`env_replace=True` is the `env -i` case, and it must be BOTH ways.

    A version that always replaced would drop PATH from every other caller; a version that never replaced would silently inherit the `RESULT_*` variables a real CI run exports, which is exactly what `test_gate_ci_complete_tiers` relies on NOT happening.
    """
    os.environ["GATE_HARNESS_PROBE"] = "inherited"
    try:
        overlaid = harness.run(
            ["bash", "-c", 'printf %s "${GATE_HARNESS_PROBE:-<unset>}"'], env={"OTHER": "x"}
        )
        gate.assert_eq(overlaid.out, "inherited", "the default OVERLAYS os.environ")
        replaced = harness.run(
            ["bash", "-c", 'printf %s "${GATE_HARNESS_PROBE:-<unset>}"'],
            env={"PATH": os.environ.get("PATH", "")},
            env_replace=True,
        )
        gate.assert_eq(replaced.out, "<unset>", "env_replace=True drops what was inherited")
    finally:
        os.environ.pop("GATE_HARNESS_PROBE", None)
    gate.log_pass("run() overlays by default and replaces only when env_replace is asked for")


def test_require_tool_both_directions(gate):
    """A tool that IS there returns its path; one that is not RAISES with the fix.

    The negative half is the point: a probe that returned None on a missing binary would hand `None` to subprocess and the failure would arrive as a TypeError in a case about something else entirely.
    """
    found = harness.require_tool("bash", "install bash")
    gate.assert_contains(found, "bash", "a present tool resolves to a path naming it")
    with pytest.raises(harness.GateAssertionError) as caught:
        harness.require_tool("gate-harness-no-such-binary", "run the install step")
    gate.assert_contains(str(caught.value), "run the install step", "the refusal carries the fix")
    gate.assert_contains(
        str(caught.value), "FAILURE and not a pass", "and says a missing tool is not a skip"
    )
    gate.log_pass("require_tool resolves a present tool and refuses an absent one with the fix")


def test_require_python_module_both_directions(gate):
    """An importable module is silent; an absent one RAISES naming module and fix."""
    harness.require_python_module("python3", "json", "impossible: json is stdlib")
    with pytest.raises(harness.GateAssertionError) as caught:
        harness.require_python_module(
            "python3", "gate_harness_no_such_module", "python3 -m pip install --user X"
        )
    gate.assert_contains(
        str(caught.value), "gate_harness_no_such_module", "the refusal names the module"
    )
    gate.assert_contains(
        str(caught.value), "pip install --user X", "and carries the remedy verbatim"
    )
    gate.log_pass("require_python_module accepts an importable module and refuses a missing one")


def test_a_signal_is_named_rather_than_left_as_a_number(gate):
    """`got 143` sends the reader hunting a branch that does not exist.

    THE ESTATE'S MOST-USED DIAGNOSTIC. `assert_exit_code` is called from gate tests on both sides, so an unnamed signal here is an unnamed signal everywhere. Three encodings must all resolve: `subprocess`'s negative returncode, a shell's 128+n, and an ordinary status that is neither.
    """
    gate.assert_eq(harness.describe_exit(0), "0", "a clean exit is left alone")
    gate.assert_eq(harness.describe_exit(1), "1", "and so is an ordinary failure")
    gate.ok("a plain status is not dressed up as a signal")

    gate.assert_eq(harness.describe_exit(143), "143 (KILLED by SIGTERM)", "128+15 is named")
    gate.assert_eq(harness.describe_exit(137), "137 (KILLED by SIGKILL)", "128+9 too")
    gate.assert_eq(harness.describe_exit(-9), "-9 (KILLED by SIGKILL)", "and subprocess's form")
    gate.ok("control: all three encodings of a kill resolve to a name")

    # THE BAND'S EDGES. 128 itself is not 128+0, and 160 is past the last real signal -- a rule without both edges renames ordinary statuses.
    gate.assert_eq(harness.describe_exit(128), "128", "128 is not a signal")
    gate.assert_eq(harness.describe_exit(160), "160", "nor is 160")
    gate.assert_eq(harness.describe_exit(255), "255", "nor an ordinary 255")
    gate.ok("control: the band excludes its own edges")

    # THE MESSAGE ITSELF, so the naming is proven where a reader meets it.
    probe = subject()
    try:
        probe.assert_exit_code(0, 143, "the subject was killed")
    except harness.GateAssertionError as caught:
        text = str(caught)
    else:
        text = "no failure raised"
    gate.assert_eq("KILLED by SIGTERM" in text, True, "assert_exit_code names it in the message")
    gate.assert_eq("expected 0" in text, True, "and still says what was expected")
    gate.ok("control: the naming reaches the failure text, not just the helper")

    gate.tally_finish("exit-code naming")
