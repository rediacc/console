"""`.ci/scripts/test/lib/test-helpers.sh`, ported to Python, vocabulary intact.

WHY THE VOCABULARY IS PRESERVED RATHER THAN TRANSLATED. 131 of the 148 gate tests source that file and speak its words -- `log_pass`, `assert_eq`, `with_fake_bin`, `ok`/`no`/`tally_finish` -- at something over a thousand call sites. The helper file itself already argues this case once, in the header of its tally block: three tests carried a byte-identical `ok`/`no` tally, and the
consolidation deliberately moved the VOCABULARY into the library instead of rewriting a hundred call sites onto the older `log_pass` spelling, because "rewriting them all is not a consolidation, it is a rewrite with its own defect budget". The same argument applies with more force here, where the rewrite also changes language. A port that renames every assertion is a port whose
diff cannot be read against its original, and a diff nobody can read is how a verdict changes without anyone noticing.

So `assert_eq(actual, expected, msg)` keeps its argument ORDER, and `assert_exit_code(expected, actual, msg)` keeps its OPPOSITE order, because that is what the bash pair does and swapping one of them silently inverts every use.

WHY NOT BARE `assert`. Two reasons, and the first is the honest one: ruff's per-file S101 exemption in this repo is scoped to `**/tests/test_*.py`, which does NOT match a file one directory deeper (`tests/gates/test_*.py`). Rather than widen a repo-wide suppression to accommodate a subdirectory, the port uses the assertion vocabulary it was going to use anyway. The second reason is
the one that would still hold if the glob matched: a bare `assert` is invisible to the tally, and the tally is what makes "this test exited 0 having asserted nothing" a FAILURE here, the same way `battery.py` makes it one for the bash side.

THE ANTI-VACUITY CONTRACT, restated in code rather than in memory. `battery.py` scores a bash gate test that exits 0 without emitting one `PASS:` line as a FAILURE ("exited 0 but made no assertions"). `conftest.py` in this directory enforces the identical rule for every ported test, from the tally this module keeps. A ported test that stops asserting therefore reds instead of
getting quieter.

THE LEDGER. When `$GATE_HARNESS_LEDGER` names a file, every recorded control is appended to it as one JSON object per line. `test_twin_parity.py` uses that to compare the port's control count against the twin's `PASS:` line count on the same tree, which is the only floor here that is not hand-typed: it is derived from the bash original, and it moves when the original moves.
"""

import contextlib
import json
import os
import pathlib
import shutil
import signal
import stat
import subprocess
import tempfile
from typing import Any

LEDGER_ENV = "GATE_HARNESS_LEDGER"

# The colour codes test-helpers.sh uses. Kept so a ported test's stdout is byte-comparable with its twin's when a reader puts the two side by side, and so the `PASS:` counting in test_twin_parity.py has to strip exactly one thing on both sides rather than one thing on one side.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


def _colours_on() -> bool:
    """Colour only when a human is reading. CI logs keep the escapes out."""
    return os.environ.get("CI") != "true" and os.environ.get("NO_COLOR") is None


def describe_exit(code: int) -> str:
    """`"143 (KILLED by SIGTERM)"` rather than `"143"`.

    THREE ENCODINGS OF THE SAME EVENT, and a reader should not have to know which one they are holding. `subprocess` reports a signal as a NEGATIVE returncode; a shell reports the same death as 128+n; and an ordinary exit is neither. 160 is outside the band deliberately -- 128+32 is past the last real signal, so a plain exit status of 159 or above is left alone rather than renamed
    into a signal that does not exist.
    """
    if code < 0:
        number = -code
    elif 128 < code < 160:
        number = code - 128
    else:
        return str(code)
    try:
        name = signal.Signals(number).name
    except ValueError:
        name = "signal %d" % number
    return "%d (KILLED by %s)" % (code, name)


class GateAssertionError(AssertionError):
    """What `log_fail` raises. An AssertionError so pytest reports it as a failure.

    `log_fail` in bash prints and calls `exit 1`, halting the test file at the first failure for a clean diagnostic. Raising has the same effect inside one pytest test function, and a better one across the file: the remaining tests still run, so one broken subject does not hide the state of the others.
    """


class RunResult:
    """`(returncode, stdout, stderr)` with the streams kept APART.

    SEPARATE ON PURPOSE, and `combined` is offered rather than assumed. Several of the bash twins redirect `2>&1` into one log and assert on the merged text; those ports use `.combined`. Everything else reads `.out` or `.err`, which is what catches the two defects a merge hides: progress text written to stdout, and a wrapper that swallows one stream entirely.
    """

    def __init__(self, rc: int, out: str, err: str) -> None:
        self.rc = rc
        self.out = out
        self.err = err

    @property
    def combined(self) -> str:
        return self.out + self.err

    def __repr__(self) -> str:
        return "RunResult(rc=%d, out=%r, err=%r)" % (self.rc, self.out, self.err)


OUTPUT_TAIL = 4000


def _rc_of(result: Any) -> int:
    rc = getattr(result, "rc", None)
    if rc is None:
        rc = result.returncode
    return rc


def _stream_of(result: object, short: str, long: str) -> str:
    text = getattr(result, short, None)
    if text is None:
        text = getattr(result, long, None)
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return text or ""


def _tail(text: str) -> str:
    if not text:
        return "(empty)"
    if len(text) <= OUTPUT_TAIL:
        return text.rstrip("\n")
    return "(%d earlier chars dropped)\n%s" % (
        len(text) - OUTPUT_TAIL,
        text[-OUTPUT_TAIL:].rstrip("\n"),
    )


def render_output(result: object) -> str:
    """The two streams of a run, labelled and kept apart, for a failure message.

    Accepts a `RunResult` (`.out`/`.err`) or a `subprocess.CompletedProcess` (`.stdout`/`.stderr`). Each stream keeps its last OUTPUT_TAIL characters, because the end of a failing run is where the reason usually is.
    """
    return "--- stdout ---\n%s\n--- stderr ---\n%s" % (
        _tail(_stream_of(result, "out", "stdout")),
        _tail(_stream_of(result, "err", "stderr")),
    )


def run(
    argv: list[str],
    *,
    cwd: os.PathLike[str] | str | None = None,
    env: dict[str, str] | None = None,
    env_replace: bool = False,
    stdin: str | None = None,
    timeout: int = 300,
) -> RunResult:
    """Drive a real command. `env` OVERLAYS os.environ rather than replacing it.

    The overlay is the important half. `env=` on subprocess REPLACES the whole
    environment, so a fixture that meant to set one variable silently drops PATH, HOME and everything else, and the failure arrives as "command not found" in a test that has nothing to do with PATH.

    `env_replace=True` IS THE `env -i` CASE, and it is opt-in by name because it
    is exactly the mistake the overlay defaults exist to prevent. Two twins need it for a real reason rather than for tidiness: `test_gate_ci_complete_tiers.py` drives assert-ci-complete.sh under `env -i` so that a `RESULT_*` variable the fixture did NOT set reads as `<unset>` -- which is the case that catches a renamed job -- and it cannot do that while this process's own
    environment
    is inherited, because a real CI run exports those very names. Callers pass the WHOLE environment they want, PATH included; nothing is added back for them.
    """
    merged = dict(env or {}) if env_replace else dict(os.environ)
    if env and not env_replace:
        merged.update(env)
    proc = subprocess.run(
        argv,
        cwd=None if cwd is None else str(cwd),
        env=merged,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


def require_tool(name: str, fix: str) -> str:
    """The absolute path of `name`, or a LOUD refusal carrying the fix line.

    WHY THIS IS NOT LEFT TO subprocess. `subprocess.run(["git", ...])` on a host
    with no git raises `FileNotFoundError: [Errno 2] No such file or directory:
    'git'`, which pytest renders as an ERROR inside whatever helper happened to call it. That reads as flake, names no remedy, and points at the test rather than at the machine. Probing first turns it into an assertion failure that says which binary is missing and what to run.

    A missing tool is a FAILURE and never a skip: a case that cannot run has not been checked, and "not checked" folded into "fine" is the shape this whole directory exists to refuse.
    """
    found = shutil.which(name)
    if not found:
        raise GateAssertionError(
            "%s is not on PATH, so this case could not run at all -- which is a "
            "FAILURE and not a pass. Fix: %s" % (name, fix)
        )
    return found


def require_python_module(interpreter: str, module: str, fix: str) -> None:
    """`interpreter` must be able to import `module`, or a LOUD refusal.

    THE CASE THIS EXISTS FOR IS NOT HYPOTHETICAL. `check-workflow-gates.sh` opens
    with its own pyyaml bootstrap because "pyyaml is absent from ubuntu-slim by
    default"; a test that LIFTS one of its python bodies out and runs it directly bypasses that bootstrap and gets `ModuleNotFoundError: No module named 'yaml'` -- from a nested interpreter, rendered as an exit code, in a case whose message is about workflow ordering. Probing first names the missing module and the remedy instead.

    NOT A SKIP. A case that could not import its dependency has not been checked, and unchecked folded into fine is the shape this directory refuses.
    """
    probe = subprocess.run(
        [interpreter, "-c", "import %s" % module],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise GateAssertionError(
            "%s cannot import %r, so this case could not run at all -- which is a "
            "FAILURE and not a pass. Fix: %s" % (interpreter, module, fix)
        )


@contextlib.contextmanager
def temp_dir():
    """`with_temp_dir`. Nests safely; removed on the way out, exception or not.

    The bash version binds the path into an EXIT trap because a shell function cannot otherwise clean up after an `exit` from inside itself. A context manager has that property natively, which is why this is the one helper whose shape changes: the trap was scaffolding for a language feature Python has.
    """
    path = pathlib.Path(tempfile.mkdtemp())
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _write_exec(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@contextlib.contextmanager
def fake_gh(output_file: os.PathLike[str] | str):
    """`with_fake_gh`. Shims `gh` on PATH with a script that cats `output_file`.

    Yields the bin directory. PATH is restored on the way out, including when the body raises -- the bash original restores it only on the success path, which is survivable there because `log_fail` exits the process, and is not survivable here because the next test would inherit the shim.
    """
    with temp_dir() as bindir:
        _write_exec(bindir / "gh", '#!/bin/bash\ncat "%s"\n' % os.fspath(output_file))
        old = os.environ.get("PATH", "")
        os.environ["PATH"] = "%s%s%s" % (bindir, os.pathsep, old)
        try:
            yield bindir
        finally:
            os.environ["PATH"] = old


class FakeBin:
    """The directory `fake_bin` put on PATH, plus what each fake was called with."""

    def __init__(self, bindir: pathlib.Path, records: pathlib.Path) -> None:
        self.dir = bindir
        self.records = records

    def record(self, name: str) -> str:
        """`fake_bin_record`. Every invocation of `name`, one line per call.

        Empty output means it was never called, which is a claim worth asserting on its own -- "nvcc was never invoked" is the whole point of the CUDA module's skip path, and it is only visible because the recorder distinguishes "no file" from "an empty file".
        """
        path = self.records / name
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def called(self, name: str) -> int:
        return len([ln for ln in self.record(name).splitlines() if ln.strip() or ln == ""])


@contextlib.contextmanager
def fake_bin(spec: str):
    """`with_fake_bin`. PATH holds ONLY what `spec` names, for the body's duration.

    The denylist argument from the bash original applies verbatim and is the whole design: shadowing the handful of binaries a test means to avoid proves nothing about the ones nobody thought to name, and the interesting failure is exactly a module quietly reaching for `curl` on a machine that happens to have it. Emptying PATH and re-admitting by name inverts the burden, so a new
    dependency announces itself as "command not found" inside the test.

    `spec` tokens, unchanged:
        name        a fake that RECORDS its argv and exits 0
        name!<n>    a fake that records its argv and exits <n>
        +name       the REAL binary, resolved from the caller's PATH and symlinked

    The bash version runs the body in a SUBSHELL so the outer PATH is never touched. Python has no subshell, so PATH is saved and restored in a `finally`, which covers the case the subshell was protecting against: a raising body.
    """
    with temp_dir() as root:
        bindir = root / "bin"
        records = root / "records"
        bindir.mkdir()
        records.mkdir()
        for token in spec.split():
            if token.startswith("+"):
                name = token[1:]
                real = shutil.which(name)
                if not real:
                    raise GateAssertionError(
                        "fake_bin: +%s requested but no such binary on PATH" % name,
                    )
                (bindir / name).symlink_to(real)
                continue
            name, _, code = token.partition("!")
            _write_exec(
                bindir / name,
                "#!/bin/bash\nprintf '%%s\\n' \"$*\" >>%s\nexit %s\n"
                % (json.dumps(str(records / name)), code or "0"),
            )
        old_path = os.environ.get("PATH", "")
        old_dir = os.environ.get("FAKE_BIN_DIR")
        old_records = os.environ.get("FAKE_BIN_RECORDS")
        os.environ["PATH"] = str(bindir)
        os.environ["FAKE_BIN_DIR"] = str(bindir)
        os.environ["FAKE_BIN_RECORDS"] = str(records)
        try:
            yield FakeBin(bindir, records)
        finally:
            os.environ["PATH"] = old_path
            for key, value in (
                ("FAKE_BIN_DIR", old_dir),
                ("FAKE_BIN_RECORDS", old_records),
            ):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class Harness:
    """One gate test's running tally, speaking test-helpers.sh's vocabulary.

    An OBJECT and not module globals, for the reason `Controls` is one: two tests in one pytest process must not share a counter, and a counter that survives between tests turns "this test asserted nothing" into "some earlier test asserted something", which is the vacuity this whole file exists to refuse.
    """

    def __init__(self, module: str, test: str, *, ledger: str | None = None) -> None:
        self.module = module
        self.test = test
        self.ledger = ledger
        self.passes: list[str] = []
        self.assertions = 0
        # The `ok`/`no` tally, kept as its own pair of counters because tally_finish's verdict line is a documented output shape three gate tests already print by hand.
        self.tally_count = 0
        self.tally_fails = 0

    # -- the log_* vocabulary ------------------------------------------------

    def _paint(self, colour: str, word: str, text: str) -> str:
        if _colours_on():
            return "%s%s%s %s" % (colour, word, NC, text)
        return "%s %s" % (word, text)

    def log_pass(self, message: str) -> None:
        """A control PASSED. This is the line `battery.py` counts, so it is the line the anti-vacuity refusal counts too."""
        self.passes.append(message)
        self._record("pass", message)
        print(self._paint(GREEN, "PASS:", message))

    def log_fail(self, message: str, result: object = None) -> None:
        """A control FAILED. Raises; `log_fail` in bash prints and exits 1.

        `result`, when given, is the run the failure is about, and its stdout and stderr are appended to the raised message. The ledger records the bare `message`, so a label stays a label.
        """
        self._record("fail", message)
        if result is not None:
            raise GateAssertionError(message + "\n" + render_output(result))
        raise GateAssertionError(message)

    def log_test(self, message: str) -> None:
        print(self._paint(YELLOW, "TEST:", message))

    def log_info(self, message: str) -> None:
        print(self._paint(YELLOW, "INFO:", message))

    def log_error(self, message: str) -> None:
        print(self._paint(RED, "ERROR:", message))

    # -- the assert_* vocabulary ---------------------------------------------

    def assert_eq(self, actual: object, expected: object, msg: str = "") -> None:
        """`assert_eq <actual> <expected> [<message>]`. ACTUAL FIRST, as in bash."""
        self.assertions += 1
        if actual != expected:
            self.log_fail(
                "%s: expected '%s', got '%s'" % (msg or "values differ", expected, actual)
            )

    def assert_contains(self, haystack: str, needle: str, msg: str = "") -> None:
        self.assertions += 1
        if needle not in haystack:
            self.log_fail("%s: '%s' not in \"%s\"" % (msg or "substring missing", needle, haystack))

    def assert_not_contains(self, haystack: str, needle: str, msg: str = "") -> None:
        self.assertions += 1
        if needle in haystack:
            self.log_fail(
                "%s: '%s' in \"%s\"" % (msg or "unexpected substring present", needle, haystack)
            )

    def assert_exit_code(self, expected: int, actual: int, msg: str = "") -> None:
        """`assert_exit_code <expected> <actual>`. EXPECTED FIRST -- the opposite of `assert_eq`, and it is that way in bash. Normalising the two would flip the meaning of every existing call site silently, which is worse than the inconsistency.

        A SIGNAL IS NAMED, NOT LEFT AS A NUMBER. `got 143` reads as a verdict the subject chose and sends the reader looking for the branch that returned it; there is no such branch, because 143 is 128+15 and something killed it. This helper is used across the whole gate-test estate, so the naming belongs here rather than at each call site.
        """
        self.assertions += 1
        if actual != expected:
            self.log_fail(
                "%s: expected %d, got %s"
                % (msg or "wrong exit code", expected, describe_exit(actual))
            )

    def assert_exit(self, expected: int, result: object, msg: str = "") -> None:
        """`assert_exit_code` for a RUN rather than a bare number: EXPECTED FIRST, then the RunResult (or `subprocess.CompletedProcess`) itself.

        THE OUTPUT TRAVELS WITH THE FAILURE. A wrong exit code with no output says only that something went wrong; the subject's own stdout and stderr say what. Taking the whole result lets the helper attach both streams, so no call site has to remember to append them and none can forget. `assert_exit_code` stays for the cases that genuinely hold only an integer.
        """
        self.assertions += 1
        actual = _rc_of(result)
        if actual != expected:
            self.log_fail(
                "%s: expected %d, got %s"
                % (msg or "wrong exit code", expected, describe_exit(actual)),
                result,
            )

    def assert_vacuous_tree_fails(self, runner, directory: pathlib.Path, needle: str, label: str):
        """The anti-vacuity case every gate test taking a ROOT override owes.

        `runner(path)` must return the gate's EXIT CODE and leave its output in the RunResult it returns; the bash original leaves it in `$LAST_OUT`, which is the only difference and only because a Python function can return two things.
        """
        empty = directory / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        result = runner(empty)
        self.assert_exit(1, result, label)
        self.assert_contains(result.combined, needle, "says the check has nothing to assert")
        self.log_pass("empty tree fails (anti-vacuity), it does not pass silently")

    # -- the ok/no tally -----------------------------------------------------

    def ok(self, message: str) -> None:
        """`ok`. Prints an UNCOLOURED `PASS:` line, exactly as the bash tally does."""
        self.tally_count += 1
        self.assertions += 1
        self.passes.append(message)
        self._record("pass", message)
        print("PASS: %s" % message)

    def no(self, message: str) -> None:
        """`no`. Records a failure and KEEPS GOING -- the tally's whole point."""
        self.tally_count += 1
        self.tally_fails += 1
        self.assertions += 1
        self._record("fail", message)
        print("FAIL: %s" % message)

    def tally_finish(self, subject: str) -> None:
        """`tally_finish`, byte-identical verdict lines, raising instead of returning 1.

        The bash callers `exit` on its status so a caller that forgets cannot report green by falling off the end. A pytest test cannot fall off the end into a pass either, because the fixture's teardown refuses a zero-control test.
        """
        print()
        if self.tally_fails == 0:
            print("✓ %s: %d control(s) passed" % (subject, self.tally_count))
            return
        raise GateAssertionError(
            "✗ %s: %d of %d control(s) failed" % (subject, self.tally_fails, self.tally_count)
        )

    # -- the ledger ----------------------------------------------------------

    def _record(self, event: str, label: str) -> None:
        if not self.ledger:
            return
        row = {"module": self.module, "test": self.test, "event": event, "label": label}
        with open(self.ledger, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def block_from(text: str, opener: str) -> list[str]:
    """The lines from the first one STARTING WITH `opener` through the closing `}`.

    SHARED BECAUSE FIVE GATE TESTS CARRIED THE SAME NINE LINES, and unlike an assertion message there is nothing per-case in them. The five are `test_gate_installmethods_container_version.py`, `..._linuxpkg_idiom.py`, `..._manifest.py`, `test_gate_preview_worker_reaping.py` and `test_gate_watchdog_supersession.py`; they pull a bash function body, a bash
    function body, a bash function body, `cleanup_preview_workers()` and an
    `async function hasNewerRun` respectively, which is the whole of the variation and it is an ARGUMENT. `check:ci-shape-duplication` reported the loop as four overlapping findings the moment the gate-test family entered its corpus.

    `awk "/^name\\(\\) \\{/,/^\\}/"` in the bash twins. It matches a line-anchored
    `}` and nothing cleverer, because the subjects are shell and JavaScript files
    formatted with the closing brace in column 1; a brace counter would be a second thing to be wrong about.

    IT RETURNS EMPTY RATHER THAN REFUSING, and that is deliberate. Every caller has its own refusal sentence naming what it was looking for and why its absence makes that file check nothing -- the per-case content this repo keeps duplicated on purpose. Folding those five sentences into one generic "block not found" would make each red harder to read, which is the opposite of the
    trade this extraction is for.
    """
    body: list[str] = []
    collecting = False
    for line in text.splitlines():
        if not collecting and line.startswith(opener):
            collecting = True
        if collecting:
            body.append(line)
            if line == "}":
                break
    return body


def watchdog_subject(gate, watchdog):
    """The watchdog module path, refusing loudly if it or node is missing.

    SHARED BECAUSE IT WAS BYTE-IDENTICAL IN THREE FILES, not because three files happened to look alike. `test_gate_watchdog_classifier_chain.py`, `..._log_capture.py` and `..._supersession.py` each carried the same four lines with the same message and the same tool hint -- the shape `check:ci-shape-duplication` reports as `148f0bece7dd` once the gate-test family enters its corpus.
    Unlike an assertion message, which is the per-case content this repo deliberately keeps duplicated, this says nothing specific to any of the three, so there is nothing lost by having one copy.

    It takes `watchdog` rather than reading a module constant, so a caller pointing at a fixture copy still gets the refusal rather than silently checking the real file.
    """
    if not watchdog.is_file():
        gate.log_fail("subject under test is missing: %s" % watchdog)
    require_tool("node", "install Node.js; the watchdog is a CommonJS module")
    return watchdog
