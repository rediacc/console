"""`rediacc_ci.quality.profiler_coverage` against the awk and grep it replaces.

WHAT THE SHADOW LEDGER ALREADY PROVES:
`.ci/shadow/w7p2-profiler-coverage.observations.jsonl` drives both
implementations end to end over five distinct committed trees: unprofiled Linux
jobs, a stale allowlist entry, a malformed reference with a bad interval and a
label mismatch, the fail-closed classification of an unknown label and an
unresolvable expression, and a low-effort BLOCKER.

WHAT THE LEDGER CANNOT ISOLATE is the EIGHT EXTRACTORS, and they are the whole
gate. Each is a small awk state machine whose failure mode is silence: an
extractor that stops matching under-reports coverage, and under-reported
coverage reads exactly like a clean tree. The twin knows this, which is why it
self-tests every extractor against a planted sample before it looks at the real
tree; this file does the other half, comparing the PORT against the TWIN over
the repository's own workflows.

THE TWIN'S TEXT IS READ AT TEST TIME, not copied here. Each awk program is
pulled out of `.ci/scripts/quality/check-profiler-coverage.sh` by name and run
under bash, so this comparison cannot drift away from the file it is about. A
copy would be a third implementation, and a third implementation is what this
whole workstream exists to remove.
"""

import pathlib
import re
import subprocess

import pytest

from rediacc_ci import log, paths
from rediacc_ci.quality import profiler_coverage as pc

TWIN = paths.CI_DIR.parent / ".ci" / "scripts" / "quality" / "check-profiler-coverage.sh"
WORKFLOWS = paths.CI_DIR.parent / ".github" / "workflows"
ACTION_REF = "./.github/actions/profiler"


@pytest.fixture(autouse=True)
def _fresh_logger():
    """`rediacc_ci.log` caches one Logger bound to `sys.stderr` at first use.

    pytest's capture fixtures swap and close that stream per test, so a logger
    cached by an earlier test writes into a closed file and every later test
    dies naming the logger rather than the test that poisoned it.
    """
    log.reset()
    yield
    log.reset()


def _twin_function(name: str) -> str:
    """The named shell function, verbatim, out of the twin.

    A range extraction rather than a hand copy: the whole point is that the
    comparison is against the file as it stands today.
    """
    text = TWIN.read_text(encoding="utf-8")
    start = re.search(r"^%s\(\) \{$" % re.escape(name), text, re.MULTILINE)
    assert start is not None, "the twin no longer defines %s()" % name
    end = re.search(r"^\}$", text[start.start() :], re.MULTILINE)
    assert end is not None, "unterminated %s() in the twin" % name
    return text[start.start() : start.start() + end.end()]


def _run_twin(names: list[str], call: str, *args: str) -> str:
    script = "\n".join(_twin_function(n) for n in names) + "\n" + call + "\n"
    proc = subprocess.run(
        ["bash", "-c", script, "_", *args],
        capture_output=True,
        text=True,
        check=False,
        env={"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, "%s / %s" % (proc.returncode, proc.stderr)
    assert proc.stderr == "", proc.stderr
    return proc.stdout


def _lines(out: str) -> list[str]:
    return out.split("\n")[:-1] if out else []


def _write(tmp: pathlib.Path, name: str, body: str) -> str:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def _corpus() -> list[pathlib.Path]:
    """Every real workflow file, which is the corpus both sides must agree on.

    A ZERO-LENGTH CORPUS IS A FAILING TEST, not a skipped one: every case below
    would pass vacuously over an empty list, which is the exact shape this
    gate's own floors exist to refuse.
    """
    found = sorted(p for p in WORKFLOWS.iterdir() if p.is_file() and p.suffix in (".yml", ".yaml"))
    assert len(found) >= 10, "the workflow corpus collapsed to %d file(s)" % len(found)
    return found


# --------------------------------------------------------------------------- The extractors, over the repository's own workflows ---------------------------------------------------------------------------


def test_job_keys_agrees_with_the_twin_on_every_real_workflow() -> None:
    total = 0
    for wf in _corpus():
        want = _lines(_run_twin(["job_keys"], 'job_keys "$1"', str(wf)))
        got = pc.job_keys(pc.records(wf.read_text(encoding="utf-8")))
        assert got == want, wf.name
        total += len(got)
    # THE SHAPE, NOT JUST THE VERDICT: a parse that collapsed to nothing would make every comparison above trivially true.
    assert total >= 60, "the two agreed on only %d job(s)" % total


def test_job_block_agrees_with_the_twin_on_every_real_job() -> None:
    checked = 0
    for wf in _corpus():
        lines = pc.records(wf.read_text(encoding="utf-8"))
        for job in pc.job_keys(lines):
            want = _run_twin(["job_block"], 'job_block "$1" "$2"', str(wf), job)
            got = "".join("%s\n" % line for line in pc.job_block(lines, job))
            assert got == want, "%s:%s" % (wf.name, job)
            checked += 1
    assert checked >= 60, "only %d block(s) compared" % checked


def test_runs_on_and_is_caller_agree_with_the_twin(tmp_path: pathlib.Path) -> None:
    seen_runner = 0
    seen_caller = 0
    for wf in _corpus():
        lines = pc.records(wf.read_text(encoding="utf-8"))
        for job in pc.job_keys(lines):
            block = pc.job_block(lines, job)
            path = _write(tmp_path, "block.txt", "".join("%s\n" % line for line in block))
            want = _run_twin(["runs_on"], 'runs_on "$1"', path).rstrip("\n")
            assert pc.runs_on(block) == want, "%s:%s" % (wf.name, job)
            caller = _run_twin(["is_caller"], 'is_caller "$1"', path).strip()
            assert pc.is_caller(block) == (caller == "yes"), "%s:%s" % (wf.name, job)
            seen_runner += 1 if want else 0
            seen_caller += 1 if caller else 0
    # BOTH DIRECTIONS MUST BE REPRESENTED in the corpus, or the agreement above is an agreement about one answer.
    assert seen_runner > 0, "no job in the corpus declares runs-on"
    assert seen_caller > 0, "no reusable-workflow caller in the corpus"


def test_covering_uses_and_step_inputs_agree_with_the_twin(tmp_path: pathlib.Path) -> None:
    covered = 0
    inputs_seen = 0
    for wf in _corpus():
        lines = pc.records(wf.read_text(encoding="utf-8"))
        for job in pc.job_keys(lines):
            block = pc.job_block(lines, job)
            path = _write(tmp_path, "block.txt", "".join("%s\n" % line for line in block))
            want = _run_twin(["covering_uses"], 'covering_uses "$1" "$2"', path, ACTION_REF).strip()
            assert pc.covering_uses(block, ACTION_REF) == int(want), "%s:%s" % (wf.name, job)
            covered += int(want)
            want_inputs = _lines(
                _run_twin(["step_inputs"], 'step_inputs "$1" "$2"', path, ACTION_REF)
            )
            assert pc.step_inputs(block, ACTION_REF) == want_inputs, "%s:%s" % (wf.name, job)
            inputs_seen += len(want_inputs)
    assert covered > 0, "no job in the corpus uses the profiler, so nothing was compared"
    assert inputs_seen > 0, "no profiler step passes an input, so step_inputs was never exercised"


def test_matrix_values_agrees_with_the_twin_where_a_matrix_exists(
    tmp_path: pathlib.Path,
) -> None:
    compared = 0
    for wf in _corpus():
        lines = pc.records(wf.read_text(encoding="utf-8"))
        for job in pc.job_keys(lines):
            block = pc.job_block(lines, job)
            declared = pc.runs_on(block)
            if not declared.startswith("${{ matrix."):
                continue
            key = re.match(r"^[A-Za-z0-9_-]*", declared.split("matrix.", 1)[1]).group(0)
            path = _write(tmp_path, "block.txt", "".join("%s\n" % line for line in block))
            want = _lines(_run_twin(["matrix_values"], 'matrix_values "$1" "$2"', path, key))
            assert pc.matrix_values(block, key) == want, "%s:%s" % (wf.name, job)
            compared += 1
    assert compared > 0, "no matrixed job in the corpus, so matrix_values was never exercised"


def test_declared_inputs_agrees_with_the_twin_on_the_real_action() -> None:
    action = paths.CI_DIR.parent / ".github" / "actions" / "profiler" / "action.yml"
    want = _lines(_run_twin(["declared_inputs"], 'declared_inputs "$1"', str(action)))
    assert pc.declared_inputs(pc.records(action.read_text(encoding="utf-8"))) == want
    assert len(want) >= 1, "the action declares no inputs, so the parser proves nothing"


# --------------------------------------------------------------------------- The shapes the real corpus does not contain ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: .github/actions/profiler",
        "        uses: github.com/x/actions/profiler@v1",
        "      - uses: ../.github/actions/profiler",
    ],
)
def test_malformed_refs_fires_on_each_illegal_form(tmp_path: pathlib.Path, line: str) -> None:
    path = _write(tmp_path, "block.txt", "%s\n" % line)
    want = _lines(_run_twin(["malformed_refs"], 'malformed_refs "$1" "$2"', path, ACTION_REF))
    got = pc.malformed_refs([line], ACTION_REF)
    assert got == want
    assert got, line


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: ./.github/actions/profiler",
        "      - uses: ./.github/actions/profiler  # with a comment",
        "      - uses: ./.github/actions/profiler/nest-probe",
    ],
)
def test_malformed_refs_stays_quiet_on_each_legal_form(tmp_path: pathlib.Path, line: str) -> None:
    """THE MIRROR. Without it a `malformed_refs` matching everything passes."""
    path = _write(tmp_path, "block.txt", "%s\n" % line)
    want = _lines(_run_twin(["malformed_refs"], 'malformed_refs "$1" "$2"', path, ACTION_REF))
    assert pc.malformed_refs([line], ACTION_REF) == want
    assert want == []


def test_covering_uses_rejects_a_longer_path(tmp_path: pathlib.Path) -> None:
    block = ["      - uses: ./.github/actions/profiler/nest-probe"]
    path = _write(tmp_path, "block.txt", "%s\n" % block[0])
    want = int(_run_twin(["covering_uses"], 'covering_uses "$1" "$2"', path, ACTION_REF).strip())
    assert pc.covering_uses(block, ACTION_REF) == want == 0


def test_is_linux_label_classifies_unknown_as_unknown_not_as_not_linux() -> None:
    """The direction that decides whether a hole is silent.

    An unknown label must cost an allowlist line, never be waved through as
    "not Linux". `NOT_LINUX` and `UNKNOWN` are different answers for that
    reason, and collapsing them is a one-character change nobody would notice.
    """
    assert pc.is_linux_label("ubuntu-slim") == pc.LINUX
    assert pc.is_linux_label("macos-14") == pc.NOT_LINUX
    assert pc.is_linux_label("windows-latest") == pc.NOT_LINUX
    assert pc.is_linux_label("self-hosted") == pc.UNKNOWN
    assert pc.is_linux_label("") == pc.UNKNOWN


def test_inline_selftest_runs_before_any_real_scan() -> None:
    """The twin's ten pre-sweep controls, ported as they were: not behind a flag."""
    assert pc.inline_selftest() == 0


def test_selftest_passes() -> None:
    assert pc.selftest() == 0
