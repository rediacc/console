"""Differential: `rediacc_ci.security.actionlint` against its twin
`.ci/scripts/security/actionlint.sh`.

TWO KINDS OF CASE, AND THE SPLIT IS THE POINT.

  REAL RUNS, against this repository's own 29 workflow files with the REAL
  pinned actionlint. actionlint is a pure reader and the twin already runs it on
  every invocation, so there is nothing to stub for the happy path -- and
  nothing that would reproduce it if there were: no fixture carries 29 real
  workflows with a real `${{ }}` expression graph. Both real-run cases hash all
  29 inputs before and after and refuse a byte of drift, so "read-only" is
  asserted rather than assumed.

  FIXTURE RUNS, against a scratch tree with a RECORDING FAKE `actionlint` and a
  RECORDING FAKE `curl` on a scratch PATH. Every acquisition and failure path
  lives here, because there is no way to make the real tool fail on demand
  without editing a real workflow file. The fakes append their exact argv to
  `$FAKE_LOG`, and every fixture case compares the two call logs as well as the
  two output streams: a port that produced identical bytes by asking a DIFFERENT
  question would pass a stdout comparison and fail this one.

WHY THE FIXTURE COPIES BOTH IMPLEMENTATIONS. Each side resolves the repository
root from its OWN location -- the twin from `${BASH_SOURCE[0]}/../../..`,
`paths.repo_root()` from `.ci/rediacc_ci/paths.py` -- and both then hard-code `.github/workflows` and `.ci/*/workflow` relative to it. There is no `$ROOT` seam on the bash side, so the only way to point both at a fixture is to put both INSIDE the fixture at their real relative paths.

NOTHING IS NORMALISED. Every case below compares stdout, stderr, the exit code and the call log byte for byte, with one deliberate exception that is asserted
as a DIVERGENCE rather than hidden: under `CI=true` with stderr on a tty,
`common.sh` emits colour and `rediacc_ci.log` does not (`test_log.py::test_ci_true_is_the_one_deliberate_divergence` pins the same decision). `test_ci_true_on_a_tty_is_the_one_inherited_divergence` asserts both sides of it here too, so a reader meeting it in the wild is meeting a decision.

ONE PATH THAT CANNOT BE DIFFERENTIALLY TESTED, named rather than skipped silently: the unsupported-architecture refusal reads `uname -m` in bash and `platform.machine()` in Python, and neither can be faked for the other (the Python call is a syscall, not a PATH lookup). The port's branch is exercised directly instead, and the two message strings are compared against the twin's
bytes so a reworded twin reds this file.

K=5 LEDGER: `.ci/shadow/w7p6-actionlint.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import tarfile

import pytest

from rediacc_ci import paths
from rediacc_ci.security import actionlint as port
from rediacc_ci.tests import differential

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/security/actionlint.sh"
PORT_REL = ".ci/rediacc_ci/security/actionlint.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

# The minimum of the package a path-invoked port needs. Deliberately short: the fixture must not become a second copy of the repository.
COPIED = (
    TWIN_REL,
    ".ci/scripts/lib/common.sh",
    ".ci/config/constants.sh",
    ".devcontainer/toolchain.env",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

CLEAN_WORKFLOW = """name: %s
on: workflow_dispatch
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
"""

# THE FAKE RECORDS BEFORE IT ANSWERS. `--version` is answered without a log line because the twin probes it through a command substitution whose result decides whether the PATH binary is used at all, and a probe is not a call the gate makes on purpose.
FAKE_ACTIONLINT = """#!/bin/bash
if [[ "$1" == "--version" ]]; then
    cat "$FAKE_DATA/version"
    exit 0
fi
printf 'FAKECALL actionlint %s\\n' "$*" >>"$FAKE_LOG"
[[ -f "$FAKE_DATA/findings" ]] && cat "$FAKE_DATA/findings"
exit "$(cat "$FAKE_DATA/rc" 2>/dev/null || echo 0)"
"""

# A curl that records its argv and then does whatever `$FAKE_DATA/curl.mode` says. `fail` exits 22 SILENTLY: a real curl under `-fsSL` prints `curl: (22) ...` of its own, and the two sides route curl's stderr differently, so a talking fake would fail the differential for a reason that is not the port's. That routing difference is itself a finding this wave
# reports; see the module note in actionlint.py.
FAKE_CURL = """#!/bin/bash
printf 'FAKECALL curl %s\\n' "$*" >>"$FAKE_LOG"
out=""
prev=""
for a in "$@"; do
    [[ "$prev" == "-o" ]] && out="$a"
    prev="$a"
done
mode="$(cat "$FAKE_DATA/curl.mode" 2>/dev/null || echo fail)"
case "$mode" in
    fail) exit 22 ;;
    garbage) printf 'not a tarball' >"$out"; exit 0 ;;
    good) cp "$FAKE_DATA/actionlint.tar.gz" "$out"; exit 0 ;;
esac
exit 22
"""


def _write(path: pathlib.Path, body: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch repository holding both implementations and the two fakes."""
    fx = tmp_path / "fx"
    for rel in COPIED:
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)

    for name in ("alpha", "beta"):
        _write(fx / ".github" / "workflows" / ("%s.yml" % name), CLEAN_WORKFLOW % name)
    # A TEMPLATE IS MANDATORY IN EVERY FIXTURE, and not as scenery: without one
    # the twin dies silently at `targets="$(collect_targets)"` before doing
    # anything at all. See `test_an_empty_template_glob_kills_the_twin_silently`, which is the case that documents it.
    _write(fx / ".ci" / "breakpoint" / "workflow" / "breakpoint.yml", CLEAN_WORKFLOW % "bp")

    data = fx / "fake" / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "version").write_text("%s\n" % port.actionlint_version(ROOT), encoding="utf-8")
    (data / "rc").write_text("0\n", encoding="utf-8")

    bindir = fx / "fake" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    _write(bindir / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    _write(bindir / "curl", FAKE_CURL, mode=0o755)
    return fx


def data_dir(fx: pathlib.Path) -> pathlib.Path:
    return fx / "fake" / "data"


def _env(fx: pathlib.Path, side: str, log: pathlib.Path, **extra: str) -> dict[str, str]:
    """REPLACES the caller's environment; see `differential.BASE_ENV`."""
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PATH"] = "%s%s%s" % (fx / "fake" / "bin", os.pathsep, env["PATH"])
    env["FAKE_DATA"] = str(data_dir(fx))
    env["FAKE_LOG"] = str(log)
    # RUNNER_TEMP, so the acquisition cache is per-side scratch and a download in one case cannot satisfy the next one. NOT `CI_TEMP`, which the twin's line
    # names and `common.sh:511` overwrites two lines earlier; setting CI_TEMP
    # here would silently leave both sides pointed at the real /tmp cache and the download cases would never run. That is the defect, used as the test's own control.
    env["RUNNER_TEMP"] = str(fx / "cache" / side)
    if side == "new":
        env["PYTHONPATH"] = str(fx / ".ci")
    env.update(extra)
    return env


def run_both(fx: pathlib.Path, *, path_has_tool: bool = True, **extra: str) -> tuple:
    """Both implementations, same fixture, same fakes. Returns results AND logs."""
    results = []
    logs = []
    for side, argv in (
        ("old", ["bash", str(fx / TWIN_REL)]),
        ("new", ["python3", str(fx / PORT_REL)]),
    ):
        log = fx / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        env = _env(fx, side, log, **extra)
        if not path_has_tool:
            # Same scratch PATH, minus the fake actionlint. `curl` must stay, because the acquisition path is what this shape exists to reach.
            hidden = fx / "fake" / "nobin"
            hidden.mkdir(parents=True, exist_ok=True)
            _write(hidden / "curl", FAKE_CURL, mode=0o755)
            env["PATH"] = "%s%s%s" % (hidden, os.pathsep, differential.BASE_ENV["PATH"])
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(fx),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )

        # THE ONE MASK, and it is the harness's own doing rather than the port's: each side gets its OWN scratch tool cache (`<fx>/cache/old` against `<fx>/cache/new`) so that a download in one side cannot silently satisfy the other. Folding the two spellings together compares the cache path in every other respect -- the version directory, the file name, the URL -- and only stops
        # the differential tripping on the isolation the test itself introduced.
        def _mask(text: str, side: str = side) -> str:
            masked = text.replace(str(fx / "cache" / side), "<cache>").replace(str(fx), "<fx>")
            return differential.mask_toolchain_tmp(masked)

        results.append((proc.returncode, _mask(proc.stdout), _mask(proc.stderr)))
        logs.append(_mask(log.read_text(encoding="utf-8")).splitlines())
    return results[0], results[1], logs[0], logs[1]


def assert_same(old: tuple, new: tuple) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def assert_agree(fx: pathlib.Path, **kwargs: object) -> tuple:
    """Run both and assert on all four channels. Returns the twin's result."""
    old, new, old_log, new_log = run_both(fx, **kwargs)  # type: ignore[arg-type]
    assert new_log == old_log, "call log:\n--- twin\n%s\n--- port\n%s" % (
        "\n".join(old_log),
        "\n".join(new_log),
    )
    assert_same(old, new)
    return old


# --------------------------------------------------------------------------- Real runs against this repository ---------------------------------------------------------------------------


def _workflow_hashes() -> dict[str, str]:
    """sha256 of every file the real run reads. A MISSING corpus is a failure.

    `if targets: ...` was the shape to avoid: an empty dict compared against an empty dict reports "nothing was mutated" having hashed nothing, which is the vacuity this whole file exists to refuse.
    """
    targets = port.collect_targets(ROOT)
    assert len(targets) >= 20, (
        "only %d workflow file(s) under the real root; the read-only guard would "
        "be hashing almost nothing" % len(targets)
    )
    return {p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in targets}


def _warm_actionlint(env_extra: dict[str, str] | None = None) -> None:
    """Put actionlint in the shared cache BEFORE either side runs.

    WITHOUT THIS THE TEST MEASURES RUN ORDER, NOT THE TWO IMPLEMENTATIONS. Both sides fetch actionlint on a miss and both announce it (`actionlint.sh:98`, `actionlint.py:322`), and `_run_real` runs the twin first into a cache they SHARE. So on a host where actionlint is already present neither fetches and the streams match, while on a host where it is absent the twin pays for the
    download, prints `✓ fetching actionlint 1.7.12 (amd64)`, and the port -- now finding it cached -- prints nothing. One line of difference, produced entirely by which subject went first.

    That is what happened in CI run 34970782616, where `test_the_real_repository_agrees_with_the_real_actionlint` failed on exactly that line while both sides reported `actionlint clean across 29 workflow file(s)`. A developer machine hides it because the cache is always warm.

    Warming explicitly makes the precondition the same on both hosts instead of leaving it to luck. It is NOT a loss of coverage: the fetch path has its own
    case (`assert "fetching actionlint" in old[2]`), which drives it against a
    scratch cache on purpose.

    IT WARMS BY RUNNING A SUBJECT, NOT BY CALLING ensure_actionlint() IN-PROCESS, and the difference is the whole fix. The cache is
    `${CI_TEMP:-${RUNNER_TEMP:-/tmp}}/actionlint-<version>` (actionlint.sh:55,
    and common.sh exports CI_TEMP from RUNNER_TEMP at source time). An in-process warm-up resolves that against PYTEST's environment, while the subjects get `differential.env_for`, which carries only PATH/HOME/LC_ALL/LANG. On a developer machine RUNNER_TEMP is unset in both, so the two agree by accident
    and the warm-up worked; on a GitHub runner RUNNER_TEMP is set for pytest and
    absent from env_for, so the warm-up filled one cache and the subjects read another. That is exactly how this case still failed in run 35009582358 after a first attempt at fixing it -- the fix had the right idea and the wrong environment, which is the same mistake this file is full of.

    Running the port as a subprocess under the SAME env cannot get that wrong: the cache is resolved by the code under test, from the environment the measured runs will use, rather than recomputed here from a path this file would have to guess.

    A warm-up that cannot reach the network is left to the subjects, which then BOTH fail to fetch and agree about that too.
    """
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = str(ROOT / ".ci")
    if env_extra:
        env.update(env_extra)
    subprocess.run(
        ["python3", str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def _run_real(env_extra: dict[str, str] | None = None) -> tuple[tuple, tuple]:
    _warm_actionlint(env_extra)
    results = []
    for side, argv in (("old", ["bash", str(TWIN)]), ("new", ["python3", str(PORT)])):
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        if side == "new":
            env["PYTHONPATH"] = str(ROOT / ".ci")
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    return results[0], results[1]


def test_the_real_repository_agrees_with_the_real_actionlint() -> None:
    """29 real workflows through the real pinned binary, byte for byte."""
    before = _workflow_hashes()
    old, new = _run_real()
    assert old[0] == 0, "the twin failed on the real tree:\n%s" % old[2]
    assert_same(old, new)
    # SEEN the verdict, not matched two empty strings.
    assert "actionlint clean across" in old[2]
    count = len(before)
    assert ("over %d workflow file(s)" % count) in old[2], (
        "the twin did not report the %d files collect_targets sees" % count
    )
    assert _workflow_hashes() == before, "a real run mutated a workflow file"


def test_the_real_tree_argv_is_identical_including_order(tmp_path: pathlib.Path) -> None:
    """The 29 real paths, in the same sequence, with the same single flag.

    THE ORDER IS THE ASSERTION. Both sides expand three separate globs and
    concatenate them without re-sorting; a port that merged them into one
    `sorted()` would hand actionlint a `.yaml` file before a later `.yml` one and still print an identical clean banner. Only the argv shows it.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _write(bindir / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    data = tmp_path / "data"
    data.mkdir()
    (data / "version").write_text("%s\n" % port.actionlint_version(ROOT), encoding="utf-8")
    (data / "rc").write_text("0\n", encoding="utf-8")

    logs = []
    for side, argv in (("old", ["bash", str(TWIN)]), ("new", ["python3", str(PORT)])):
        log = tmp_path / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        env["PATH"] = "%s%s%s" % (bindir, os.pathsep, env["PATH"])
        env["FAKE_DATA"] = str(data)
        env["FAKE_LOG"] = str(log)
        if side == "new":
            env["PYTHONPATH"] = str(ROOT / ".ci")
        subprocess.run(
            argv, env=env, cwd=str(ROOT), capture_output=True, text=True, check=False, timeout=180
        )
        logs.append(log.read_text(encoding="utf-8").splitlines())
    assert logs[0], "the fake actionlint was never called; the control did not fire"
    assert len(logs[0][0].split()) > 20, "argv line names too few files: %s" % logs[0][0]
    assert logs[1] == logs[0]


# --------------------------------------------------------------------------- Fixture runs ---------------------------------------------------------------------------


def test_clean_fixture_agrees(fixture: pathlib.Path) -> None:
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "clean across 3 workflow file(s)" in old[2]


def test_yaml_extension_is_collected_after_every_yml(fixture: pathlib.Path) -> None:
    """`*.yml` is a SEPARATE pass from `*.yaml`, and the passes concatenate."""
    _write(fixture / ".github" / "workflows" / "aaa.yaml", CLEAN_WORKFLOW % "aaa")
    old, _new, old_log, new_log = run_both(fixture)
    assert old[0] == 0
    assert new_log == old_log
    argv = old_log[0].split()
    # The template pass is always last, so the `.yaml` file sits just before it and AFTER both `.yml` files -- which is exactly what "separate pass, concatenated" means and what one merged `sorted()` would destroy.
    assert argv[-1].endswith("/.ci/breakpoint/workflow/breakpoint.yml"), old_log[0]
    assert argv[-2].endswith("/.github/workflows/aaa.yaml"), old_log[0]
    assert [a.rsplit("/", 1)[-1] for a in argv[3:]] == [
        "alpha.yml",
        "beta.yml",
        "aaa.yaml",
        "breakpoint.yml",
    ], old_log[0]


def test_the_out_of_tree_workflow_template_is_collected(fixture: pathlib.Path) -> None:
    """`.ci/*/workflow/*.yml`, the coverage every other workflow gate misses.

    The fixture already carries one; a SECOND one under a different `.ci/*`
    directory proves the middle `*` is expanded and sorted rather than hardcoded to `breakpoint`.
    """
    _write(fixture / ".ci" / "aaa" / "workflow" / "vendored.yml", CLEAN_WORKFLOW % "vendored")
    old, _new, old_log, new_log = run_both(fixture)
    assert old[0] == 0
    assert new_log == old_log
    assert "over 4 workflow file(s)" in old[2]
    argv = old_log[0].split()
    assert argv[-2].endswith("/.ci/aaa/workflow/vendored.yml"), old_log[0]
    assert argv[-1].endswith("/.ci/breakpoint/workflow/breakpoint.yml"), old_log[0]


def test_findings_exit_1_with_the_four_error_lines(fixture: pathlib.Path) -> None:
    (data_dir(fixture) / "rc").write_text("1\n", encoding="utf-8")
    (data_dir(fixture) / "findings").write_text(
        'a.yml:3:5: unexpected key "jobss" [syntax-check]\n', encoding="utf-8"
    )
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "ZERO jobs and no error message anywhere." in old[2]
    assert "unexpected key" in old[1], "actionlint's own finding must stay on STDOUT"


def test_only_the_template_survives_and_it_is_still_linted(fixture: pathlib.Path) -> None:
    """Deleting `.github/workflows` leaves the template, which IS the corpus."""
    shutil.rmtree(fixture / ".github")
    old, _new, old_log, new_log = run_both(fixture)
    assert old[0] == 0
    assert new_log == old_log
    assert "over 1 workflow file(s)" in old[2]


def test_an_empty_template_glob_kills_the_twin_silently(fixture: pathlib.Path) -> None:
    """THE DEFECT THIS WAVE FOUND, reproduced on both sides. Port note 3.

    `collect_targets` ends with `for f in "$ROOT"/.ci/*/workflow/*.yml; do
    [[ -f "$f" ]] && echo "$f"; done`, so when that glob matches nothing the
    function returns 1 and `set -e` kills the script at the assignment: exit 1,
    ZERO bytes on both streams, with two real workflow files sitting unlinted. Exit 1 is also the code for "actionlint reported findings", so the CI reader is sent looking for an expression error that does not exist.
    """
    shutil.rmtree(fixture / ".ci" / "breakpoint")
    old, new, old_log, new_log = run_both(fixture)
    assert old == (1, "", ""), "the twin no longer dies silently: %r" % (old,)
    assert new_log == old_log == [], "actionlint must not be called at all"
    assert_same(old, new)
    # The two real workflows are still there and still unread.
    assert len(list((fixture / ".github" / "workflows").iterdir())) == 2


def test_the_exit_3_refusal_is_unreachable(fixture: pathlib.Path) -> None:
    """The corollary, stated as its own assertion so it cannot be forgotten.

    Every tree splits two ways: the template glob matches (so the corpus is non-empty and the count test passes) or it does not (so the script is already dead). There is no third case, and therefore no input that reaches the exit-3 message. Both directions are driven here.
    """
    shutil.rmtree(fixture / ".github")
    with_template = run_both(fixture)[0]
    assert with_template[0] == 0
    shutil.rmtree(fixture / ".ci" / "breakpoint")
    without_template = run_both(fixture)[0]
    assert without_template == (1, "", "")
    twin = TWIN.read_text(encoding="utf-8")
    assert "exit 3" in twin, "the twin dropped the branch; rewrite this case"
    for result in (with_template, without_template):
        assert "a lint run over zero files" not in result[2]


def test_a_wrong_version_on_path_is_announced_then_the_cache_is_used(
    fixture: pathlib.Path,
) -> None:
    """The PATH binary loses, and the twin says so before falling through."""
    (data_dir(fixture) / "version").write_text("9.9.9\n", encoding="utf-8")
    # A cached binary at the pin, so neither side reaches curl.
    for side in ("old", "new"):
        cache = fixture / "cache" / side / ("actionlint-%s" % port.actionlint_version(ROOT))
        _write(cache / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "9.9.9 is on PATH but this gate pins" in old[2]


def test_a_silent_version_prints_the_twins_double_space(fixture: pathlib.Path) -> None:
    """`have` is empty and the message keeps the gap. Port note 2.

    `--version` SUCCEEDS here and simply says nothing, which is the only way to reach the empty-`have` message: a probe that FAILS kills the gate first, and the case below is that one.
    """
    _write(
        fixture / "fake" / "bin" / "actionlint",
        '#!/bin/bash\n[[ "$1" == "--version" ]] && exit 0\n'
        'printf \'FAKECALL actionlint %s\\n\' "$*" >>"$FAKE_LOG"\nexit 0\n',
        mode=0o755,
    )
    for side in ("old", "new"):
        cache = fixture / "cache" / side / ("actionlint-%s" % port.actionlint_version(ROOT))
        _write(cache / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "actionlint  is on PATH but this gate pins" in old[2]


def test_a_failing_version_probe_kills_the_gate_silently(fixture: pathlib.Path) -> None:
    """THE THIRD DEFECT, reproduced on both sides. Port note 10.

    `have="$(actionlint --version 2>/dev/null | head -1 | tr -d 'v')"` under
    `set -euo pipefail`: the probe's non-zero status travels through the command substitution and `set -e` ends the run. The status here is 3, which is this gate's DOCUMENTED code for "nothing to check (vacuous)", so a broken shim on PATH is reported to CI as an empty corpus, with no message at all and three perfectly readable workflow files left unlinted.
    """
    _write(
        fixture / "fake" / "bin" / "actionlint",
        '#!/bin/bash\n[[ "$1" == "--version" ]] && exit 3\n'
        'printf \'FAKECALL actionlint %s\\n\' "$*" >>"$FAKE_LOG"\nexit 0\n',
        mode=0o755,
    )
    for side in ("old", "new"):
        cache = fixture / "cache" / side / ("actionlint-%s" % port.actionlint_version(ROOT))
        _write(cache / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    old, new, old_log, new_log = run_both(fixture)
    assert old == (3, "", ""), "the twin no longer dies silently: %r" % (old,)
    assert new_log == old_log == []
    assert_same(old, new)


def test_a_failing_version_probe_carries_its_own_code(fixture: pathlib.Path) -> None:
    """Not always 3: whatever the probe returned. Both sides, three codes."""
    for code in (1, 2, 9):
        _write(
            fixture / "fake" / "bin" / "actionlint",
            '#!/bin/bash\n[[ "$1" == "--version" ]] && exit %d\n'
            'printf \'FAKECALL actionlint %%s\\n\' "$*" >>"$FAKE_LOG"\nexit 0\n' % code,
            mode=0o755,
        )
        old, new, _ol, _nl = run_both(fixture)
        assert old == (code, "", ""), "code %d: twin gave %r" % (code, old)
        assert_same(old, new)


def test_a_failed_download_is_exit_2(fixture: pathlib.Path) -> None:
    (data_dir(fixture) / "curl.mode").write_text("fail\n", encoding="utf-8")
    old = assert_agree(fixture, path_has_tool=False)
    assert old[0] == 2
    assert "could not download actionlint from" in old[2]


def test_a_checksum_mismatch_refuses_to_extract(fixture: pathlib.Path) -> None:
    """The strongest fixture case: verification happens BEFORE extraction."""
    (data_dir(fixture) / "curl.mode").write_text("garbage\n", encoding="utf-8")
    old = assert_agree(fixture, path_has_tool=False)
    assert old[0] == 2
    assert "checksum MISMATCH -- refusing to extract" in old[2]
    expected = port.actionlint_checksums(ROOT)["ACTIONLINT_SHA256_LINUX_AMD64"]
    other = port.actionlint_checksums(ROOT)["ACTIONLINT_SHA256_LINUX_ARM64"]
    assert (expected in old[2]) or (other in old[2]), "the expected hash was not printed"
    assert hashlib.sha256(b"not a tarball").hexdigest() in old[2]


def test_a_verified_download_is_extracted_and_run(fixture: pathlib.Path, tmp_path) -> None:
    """The whole acquisition path end to end, with a REAL tar and a REAL hash.

    The tarball is built here and its sha256 is written into the fixture's own `constants.sh`, so the case proves the verify-then-extract sequence rather than skipping past it.
    """
    payload = tmp_path / "actionlint"
    _write(payload, FAKE_ACTIONLINT, mode=0o755)
    tarball = data_dir(fixture) / "actionlint.tar.gz"
    with tarfile.open(str(tarball), "w:gz") as archive:
        archive.add(str(payload), arcname="actionlint")
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()

    constants = fixture / ".ci" / "config" / "constants.sh"
    text = constants.read_text(encoding="utf-8")
    for key in ("ACTIONLINT_SHA256_LINUX_AMD64", "ACTIONLINT_SHA256_LINUX_ARM64"):
        text = "\n".join(
            'readonly %s="%s"' % (key, digest) if line.startswith("readonly %s=" % key) else line
            for line in text.split("\n")
        )
    constants.write_text(text, encoding="utf-8")
    (data_dir(fixture) / "curl.mode").write_text("good\n", encoding="utf-8")

    old = assert_agree(fixture, path_has_tool=False)
    assert old[0] == 0, "acquisition failed:\n%s" % old[2]
    assert "fetching actionlint" in old[2]
    for side in ("old", "new"):
        landed = (
            fixture
            / "cache"
            / side
            / ("actionlint-%s" % port.actionlint_version(ROOT))
            / "actionlint"
        )
        assert os.access(str(landed), os.X_OK), "%s side did not extract an executable" % side


# --------------------------------------------------------------------------- Colour, and the one inherited divergence ---------------------------------------------------------------------------


def test_no_colour_off_a_tty(fixture: pathlib.Path) -> None:
    old, new, _ol, _nl = run_both(fixture)
    assert differential.escape_bytes(old[2]) == 0
    assert differential.escape_bytes(new[2]) == 0


def _tty_stderr(fx: pathlib.Path, side: str, **extra: str) -> str:
    """Run one side with a pty on STDERR and return what it wrote there."""
    log = fx / ("calls.%s" % side)
    log.write_text("", encoding="utf-8")
    env = _env(fx, side, log, **extra)
    script = (
        "bash %s" % (fx / TWIN_REL)
        if side == "old"
        else "PYTHONPATH=%s python3 %s" % (env["PYTHONPATH"], fx / PORT_REL)
    )
    _rc, _out, err = differential.bash_streams(
        script, env=env, cwd=str(fx), tty="stderr", timeout=120
    )
    return err


def test_colour_on_a_tty_matches(fixture: pathlib.Path) -> None:
    old = _tty_stderr(fixture, "old")
    new = _tty_stderr(fixture, "new")
    assert differential.escape_bytes(old) > 0, "the tty control did not fire"
    assert new == old


def test_ci_true_on_a_tty_is_the_one_inherited_divergence(fixture: pathlib.Path) -> None:
    """A PINNED DECISION, not a surprise. See the module docstring.

    `common.sh` gates colour on the stream alone and ignores CI; `rediacc_ci.log`
    also honours `CI=true`, because GitHub's log viewer renders escapes as
    literal text. Asserted in BOTH directions so nobody "fixes" either side.
    """
    old = _tty_stderr(fixture, "old", CI="true")
    new = _tty_stderr(fixture, "new", CI="true")
    assert differential.escape_bytes(old) > 0, "common.sh stopped colouring under CI=true"
    assert differential.escape_bytes(new) == 0, "the house logger started colouring under CI"
    assert new != old
    # The MESSAGES still agree; only the escapes differ.
    plain = re.compile(r"\033\[[0-9;]*m")
    assert plain.sub("", old) == plain.sub("", new)


# --------------------------------------------------------------------------- The pure helpers, exercised directly ---------------------------------------------------------------------------


def test_path_version_deletes_every_v_not_just_a_leading_one(tmp_path: pathlib.Path) -> None:
    """`tr -d 'v'`. Port note 1: `lstrip`/`removeprefix` would disagree."""
    fake = tmp_path / "actionlint"
    _write(fake, '#!/bin/bash\necho "v1.7.12-dev"\necho ignored\n', mode=0o755)
    assert port.path_version(str(fake)) == ("1.7.12-de", 0)


def test_path_version_of_a_binary_that_cannot_run_is_126(tmp_path: pathlib.Path) -> None:
    """bash's own status for "cannot execute". See `path_version`'s docstring."""
    assert port.path_version(str(tmp_path / "nope")) == ("", 126)


def test_cache_dir_ignores_ci_temp_because_common_sh_overwrites_it(monkeypatch) -> None:
    """THE SECOND DEFECT, as a unit. The twin's own `${CI_TEMP:-...}` is dead.

    Driven against the BASH too, below, so this is not just an assertion about what the port chose to do.
    """
    monkeypatch.delenv("CI_TEMP", raising=False)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    assert str(port.cache_dir("1.0")) == "/tmp/actionlint-1.0"
    monkeypatch.setenv("CI_TEMP", "/c")
    assert str(port.cache_dir("1.0")) == "/tmp/actionlint-1.0", "CI_TEMP must be ignored"
    monkeypatch.setenv("TMPDIR", "/t")
    assert str(port.cache_dir("1.0")) == "/t/actionlint-1.0"
    monkeypatch.setenv("RUNNER_TEMP", "/r")
    assert str(port.cache_dir("1.0")) == "/r/actionlint-1.0"


def test_common_sh_really_does_overwrite_ci_temp() -> None:
    """The bash half of the case above. Sourcing common.sh is the whole test."""
    for extra, expected in (({}, "/tmp"), ({"TMPDIR": "/TMPD"}, "/TMPD")):
        env = differential.env_for(CI_TEMP="/CALLER_SET", **extra)
        rc, out, _err = differential.bash_streams(
            'source .ci/scripts/lib/common.sh; printf "%s" "$CI_TEMP"',
            env=env,
            cwd=str(ROOT),
        )
        assert rc == 0
        assert out == expected, "CI_TEMP survived as %r; the defect is gone" % out


def test_the_arch_table_covers_exactly_the_twins_four_spellings() -> None:
    """A fifth spelling here would be a silent widening of the refusal."""
    assert set(port.ARCH_TABLE) == {"x86_64", "amd64", "aarch64", "arm64"}
    assert {v[0] for v in port.ARCH_TABLE.values()} == {"amd64", "arm64"}


def test_the_pins_and_checksums_come_from_the_files_the_twin_reads() -> None:
    version = port.actionlint_version(ROOT)
    assert version, "no ACTIONLINT_VERSION in toolchain.env"
    assert version[0].isdigit(), "ACTIONLINT_VERSION is not a version: %r" % version
    pins = (ROOT / ".devcontainer" / "toolchain.env").read_text(encoding="utf-8")
    assert ("ACTIONLINT_VERSION=%s" % version) in pins
    sums = port.actionlint_checksums(ROOT)
    assert set(sums) == {"ACTIONLINT_SHA256_LINUX_AMD64", "ACTIONLINT_SHA256_LINUX_ARM64"}
    constants = (ROOT / ".ci" / "config" / "constants.sh").read_text(encoding="utf-8")
    for key, value in sums.items():
        assert ('readonly %s="%s"' % (key, value)) in constants


def test_the_unsupported_arch_refusal_says_what_the_twin_says() -> None:
    """The one path no differential can drive; see the module docstring."""
    twin = TWIN.read_text(encoding="utf-8")
    assert "no pinned actionlint checksum for architecture '$arch'" in twin
    assert "add one to .ci/config/constants.sh rather than downloading unverified" in twin
    assert port.ARCH_TABLE.get("riscv64") is None


def test_collect_targets_on_the_real_tree_is_sorted_within_each_pass() -> None:
    """Three passes, each byte-sorted, concatenated. Port notes 4 and 5."""
    targets = port.collect_targets(ROOT)
    workflows = [t for t in targets if "/.github/workflows/" in t]
    yml = [t for t in workflows if t.endswith(".yml")]
    yaml = [t for t in workflows if t.endswith(".yaml")]
    assert yml == sorted(yml)
    assert yaml == sorted(yaml)
    assert workflows == yml + yaml
    assert len(targets) > len(workflows) or all("/workflow/" not in t for t in targets)
