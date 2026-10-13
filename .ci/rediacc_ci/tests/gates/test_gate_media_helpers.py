"""Port of `.ci/scripts/test/gates/test-media-helpers.sh`, retired in W7 P5.

Two subjects, and the first one carries the second: `harness.fake_bin` (the `with_fake_bin` / `fake_bin_record` pair), and the `.ci/media` scan root in `.ci/scripts/quality/check_dead_case_arms.py`.

WHY THE HELPER IS TESTED AT ALL. The media gate tests (`test_gate_media_{args,bridge,cuda,entry,pool,portable,r2,shims,venv}.py`) claim to prove things about code that drives a GPU, a libvirt cluster and an R2 bucket, and every one of those claims rests on `harness.fake_bin` actually EMPTYING PATH. A helper that quietly left PATH intact would make all of them pass against the host's real
binaries while reporting hermetic isolation, which is the exact shape of a green that means nothing. So the helper is tested first, and the assertion carrying the most weight is the negative one: the binaries nobody named are GONE.

THE SUBJECT MOVED, THE CASES DID NOT. Until PLAN-retire-bash-oracles section 12 U3 step 2 these cases drove the bash helper (`.ci/scripts/test/lib/test-helpers.sh`) through `bash -c`, because that was the helper the bash gate tests used. Its last sourcer went with U2 and the file was deleted, so per DB16 each case was salvaged onto the helper the media ports really use, with the same probe and the same expected value. `test_harness.py` covers `fake_bin`'s general contract; the cases here keep the
media-specific claims it does not make: the full list of binaries a media module could reach for, and the `+cut` passthrough that only a REAL binary can satisfy.

NO `xdist_group`. `fake_bin` saves and restores PATH in a `finally`, so a case changes this worker's environment only for the duration of its `with` block. The cases that run the real `check_dead_case_arms.py` only READ the tree.
"""

import os
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# THE SUBJECT IS THE PYTHON GATE NOW. It was `.ci/scripts/quality/check-dead-case-arms.sh`
# (blob `19c18e3f491528ad54c0e1fb8832f626b0eade9d`), retired in W7P5-c on its K=5 `EQUIVALENT`
# ledger `.ci/shadow/w7p2-dead-case-arms.observations.jsonl`. See the identical note in
# `test_gate_dead_case_arms.py` for the differential that was driven before the deletion.
GATE = paths.from_root(".ci", "scripts", "quality", "check_dead_case_arms.py")
MEDIA = paths.from_root(".ci", "media")


# --------------------------------------------------------------------------- fake_bin ---------------------------------------------------------------------------


def test_path_is_replaced_not_prefixed(gate):
    gate.log_test("PATH is replaced, not prefixed")
    with harness.fake_bin("docker") as fakes:
        gate.assert_eq(
            os.environ.get("PATH"), str(fakes.dir), "PATH must be the fake dir and nothing else"
        )
    gate.log_pass("PATH is REPLACED by the fake dir, not prefixed onto the real one")


def test_everything_unnamed_is_absent(gate):
    gate.log_test("THE LOAD-BEARING ASSERTION: unnamed binaries are gone")
    # Every other media gate test's hermeticity claim is this one assertion wearing a different hat.
    absent = [
        "docker",
        "node",
        "npm",
        "npx",
        "nvcc",
        "aws",
        "ssh",
        "rsync",
        "curl",
        "wget",
        "git",
        "python3",
        "ffmpeg",
    ]
    with harness.fake_bin("true"):
        present = [b for b in absent if shutil.which(b) is not None]
    gate.assert_eq(" ".join(present), "", "these should not be reachable inside fake_bin")
    gate.log_pass(
        "docker, node, npm, npx, nvcc, aws, ssh, rsync, curl, wget, git, python3 and "
        "ffmpeg are all absent"
    )


def test_a_named_fake_records_its_arguments(gate):
    gate.log_test("a named fake is on PATH and records argv")
    with harness.fake_bin("docker nvcc") as fakes:
        gate.assert_exit(
            0, harness.run(["docker", "run", "--rm", "alpine", "echo", "hi"]), "docker"
        )
        gate.assert_exit(0, harness.run(["nvcc", "--version"]), "nvcc")
        gate.assert_eq(
            fakes.record("docker"),
            "run --rm alpine echo hi\n",
            "docker's argv is recorded verbatim",
        )
        gate.assert_eq(fakes.record("nvcc"), "--version\n", "nvcc's argv is recorded verbatim")
    gate.log_pass("a named fake is on PATH and records the argv it was called with")


def test_a_never_called_fake_records_nothing(gate):
    gate.log_test("an empty record must be distinguishable from a broken recorder")
    # "nvcc was never invoked" is an assertion the CUDA module's test makes, so the empty-record case has to be distinguishable from a recorder that lost the file.
    with harness.fake_bin("aws") as fakes:
        gate.assert_eq(fakes.record("aws"), "", "a fake that was never invoked records nothing")
        gate.assert_eq(fakes.called("aws"), 0, "and counts zero calls")
    gate.log_pass("a fake that was never called reports no invocations")


def test_exit_code_suffix_is_honoured(gate):
    gate.log_test("the name!<n> form controls the fake's exit code")
    with harness.fake_bin("flaky!7"):
        gate.assert_exit(7, harness.run(["flaky"]), "name!7 must exit 7")
    gate.log_pass("the name!<n> form controls the fake's exit code")


def test_passthrough_admits_the_real_binary(gate):
    gate.log_test("the +name form admits the real binary")
    # `cut`, DELIBERATELY: it is not a Python or shell builtin, so this can only succeed if the symlink to the real binary is what answered. An earlier draft of the bash twin asserted on `printf` and proved nothing, because bash's builtin would have satisfied it with PATH empty.
    with harness.fake_bin("+cut") as fakes:
        result = harness.run(["cut", "-d:", "-f2"], stdin="a:b\n")
        gate.assert_exit(0, result, "+cut must run")
        gate.assert_eq(result.out, "b\n", "+cut must be the real cut")
        gate.assert_eq(
            fakes.record("cut"), "", "a passthrough is not a recorder, so it records nothing"
        )
    gate.log_pass("the +name form admits the real binary by name")


def test_the_callers_path_is_never_touched(gate):
    gate.log_test("the restriction is scoped to the with block")
    # The distinction keeps a failing assertion from being followed by "rm: command not found" as the cleanup unwinds.
    before = os.environ.get("PATH")
    with harness.fake_bin("docker") as fakes:
        gate.assert_eq(os.environ.get("PATH"), str(fakes.dir), "inside: only the fakes")
    gate.assert_eq(
        os.environ.get("PATH"), before, "the caller's PATH must be unchanged by fake_bin"
    )
    gate.log_pass("the caller's PATH is untouched: the restriction is scoped to the with block")


# --------------------------------------------------------------------------- The .ci/media scan root in check_dead_case_arms.py ---------------------------------------------------------------------------


def run_gate_media(media_dirs: str | None = None) -> harness.RunResult:
    env = {} if media_dirs is None else {"DEAD_CASE_MEDIA_DIRS": media_dirs}
    return harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)


def test_media_root_is_wired_into_the_real_scan(gate, tmp_path: pathlib.Path):
    gate.log_test("the MEDIA_DIRS variable reaches the real scan")
    # The failure this catches is not "the scanner is broken" -- the gate's own control covers that -- but "the new variable was declared and never passed to scan". Only driving the REAL gate with the root overridden tells those apart.
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    media = tmp_path / "media"
    media.mkdir()
    (media / "mod.sh").write_text(
        'case "$1" in\n    *"zzznosuchmediafield=1"*) exit 1 ;;\nesac\n', encoding="utf-8"
    )
    result = run_gate_media(str(media))
    gate.assert_exit(1, result, "a dead arm in the media root must fail the gate")
    gate.assert_contains(
        result.combined,
        "zzznosuchmediafield",
        "names the dead field it found in the media root",
    )
    gate.log_pass("MEDIA_DIRS reaches the real scan: a dead arm planted there reds the gate")


def test_the_real_media_folder_is_clean_and_counted(gate):
    gate.log_test("the real .ci/media folder is scanned, counted and clean")
    result = run_gate_media()
    gate.assert_exit(0, result, "the real tree must have no dead case arms")
    gate.assert_contains(
        result.combined, ".ci/media", "the verdict must name the media root it scanned"
    )
    gate.assert_not_contains(
        result.combined,
        "(0 media shell file(s)",
        "a zero-file media root is vacuous, not clean",
    )
    gate.log_pass("the real .ci/media folder is scanned, counted and clean")


def test_an_empty_media_root_is_vacuous_not_clean(gate, tmp_path: pathlib.Path):
    gate.log_test("anti-vacuity for the new root, driven through the real gate")
    # A root that has stopped matching files must be a FAILURE, because otherwise it is indistinguishable from a clean one.
    empty = tmp_path / "nothing"
    empty.mkdir()
    result = run_gate_media(str(empty))
    gate.assert_exit(1, result, "an empty media root must fail rather than report clean")
    gate.assert_contains(result.combined, "VACUOUS", "says the scan root proves nothing")
    gate.log_pass("an empty media root is refused as vacuous")


def test_the_real_media_folder_is_not_itself_empty(gate):
    """PORT-ONLY, and it closes the gap between the two cases above.

    `test_the_real_media_folder_is_clean_and_counted` asserts the verdict does not carry the literal `(0 media shell file(s)` phrase, which is a claim about the gate's WORDING. If that phrase were ever reworded, the assertion would keep passing over a scan of nothing. Counting the files on disk is the same claim made about the tree instead of about a string."""
    gate.log_test("the media root this gate scans really holds shell files")
    if not MEDIA.is_dir():
        gate.log_fail(
            "%s does not exist, so the scan above read nothing" % paths.relative_to_root(MEDIA)
        )
    found = sorted(MEDIA.glob("*.sh"))
    if not found:
        gate.log_fail(
            "%s holds no .sh file at all, so a green from the real scan would be "
            "vacuous however it is worded" % paths.relative_to_root(MEDIA)
        )
    gate.assertions += 1
    gate.log_pass("%d shell file(s) in .ci/media are what the real scan read" % len(found))


def test_bash_is_the_interpreter_every_case_above_used(gate):
    """PORT-ONLY. Every fake `fake_bin` writes is a `#!/bin/bash` script; a host without bash would fail
    the fake_bin cases with an exec error from a helper, which reads as flake and names no fix."""
    gate.log_test("the interpreter these cases need is present")
    harness.require_tool("bash", "install bash; every fake fake_bin writes is a bash script")
    gate.assertions += 1
    gate.log_pass("bash is on PATH at %s" % shutil.which("bash"))
