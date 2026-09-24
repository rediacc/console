"""Port of `.ci/scripts/test/gates/test-media-helpers.sh`, retired in W7 P5.

Two subjects, and the first one carries the second: `with_fake_bin` / `fake_bin_record` in `.ci/scripts/test/lib/test-helpers.sh`, and the `.ci/media` scan root in `.ci/scripts/quality/check_dead_case_arms.py`.

WHY THE HELPER IS TESTED AT ALL. Six other gate tests claim to prove things about code that drives a GPU, a libvirt cluster and an R2 bucket, and every one of those claims rests on `with_fake_bin` actually EMPTYING PATH. A helper that quietly left PATH intact would make all six pass against the host's real binaries while reporting hermetic isolation, which is the exact shape of a
green that means nothing. So the helper is tested first, and the assertion carrying the most weight is the negative one: the binaries nobody named are GONE.

THE PORT DRIVES THE BASH HELPER, NOT ITS PYTHON COUSIN, and this is the whole reason the module is written the way it is. `rediacc_ci.tests.gates.harness` has its own `fake_bin` with the same contract, and calling that here would be a test of the port's own library while the file claims to be testing `.ci/scripts/test/lib/test-helpers.sh`. Every case below therefore runs `bash -c
'source test-helpers.sh; with_fake_bin ... probe'` in a subprocess and reads its exit code, so the subject under test is the shipped shell function and nothing else. The probe bodies are the twin's, verbatim in shell, because translating them would change what is being asserted about a shell helper.

NO `xdist_group`. Each case is one `bash -c` subprocess with its own `mkdtemp` fixture; `with_fake_bin` scopes its PATH change to a subshell inside that process, so nothing leaks even between the cases in one file, let alone between workers. The two cases that run the real `check_dead_case_arms.py` only READ the tree.
"""

import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

HELPERS = paths.from_root(".ci", "scripts", "test", "lib", "test-helpers.sh")
# THE SUBJECT IS THE PYTHON GATE NOW. It was `.ci/scripts/quality/check-dead-case-arms.sh`
# (blob `19c18e3f491528ad54c0e1fb8832f626b0eade9d`), retired in W7P5-c on its K=5 `EQUIVALENT`
# ledger `.ci/shadow/w7p2-dead-case-arms.observations.jsonl`. See the identical note in
# `test_gate_dead_case_arms.py` for the differential that was driven before the deletion.
GATE = paths.from_root(".ci", "scripts", "quality", "check_dead_case_arms.py")
MEDIA = paths.from_root(".ci", "media")


def drive(gate, body: str) -> harness.RunResult:
    """Source the real helper library and run `body`, in one bash subprocess.

    `set -euo pipefail`, THE TWIN'S OWN PRELUDE, and the `-e` is load-bearing. A first draft of this port used `set -uo pipefail`, reasoning that `log_fail` exits 1 by itself. It does -- but `with_fake_bin` runs the body in a SUBSHELL, so that exit kills the subshell and returns non-zero to a parent that, without `-e`, simply carries on and exits 0. Measured: planting the exact
    defect the twin's header describes (`with_fake_bin` PREFIXING PATH instead of replacing it) turned the twin RED and left this port GREEN. That was a defect in the CONTROL, not in the gate; the gate's own assertion was firing correctly inside the subshell and nothing was reading its status.
    """
    if not HELPERS.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(HELPERS))
    script = "set -euo pipefail\nsource %s\n%s\n" % (str(HELPERS), body)
    return harness.run(["bash", "-c", script], cwd=paths.repo_root())


def expect_green(gate, body: str, label: str) -> harness.RunResult:
    result = drive(gate, body)
    if result.rc != 0:
        gate.log_fail(
            "%s: the probe exited %d\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (label, result.rc, result.out, result.err)
        )
    gate.assertions += 1
    return result


# --------------------------------------------------------------------------- with_fake_bin ---------------------------------------------------------------------------

PROBE_PATH_IS_ONLY_FAKES = """
_probe_path_is_only_fakes() {
    assert_eq "$PATH" "$FAKE_BIN_DIR" "PATH must be the fake dir and nothing else"
}
"""


def test_path_is_replaced_not_prefixed(gate):
    gate.log_test("PATH is replaced, not prefixed")
    expect_green(
        gate,
        PROBE_PATH_IS_ONLY_FAKES + 'with_fake_bin "docker" _probe_path_is_only_fakes',
        "PATH must be exactly the fake dir",
    )
    gate.log_pass("PATH is REPLACED by the fake dir, not prefixed onto the real one")


def test_everything_unnamed_is_absent(gate):
    gate.log_test("THE LOAD-BEARING ASSERTION: unnamed binaries are gone")
    # Every other media gate test's hermeticity claim is this one assertion wearing a different hat.
    expect_green(
        gate,
        """
_probe_unnamed_binaries_are_absent() {
    local absent=(docker node npm npx nvcc aws ssh rsync curl wget git python3 ffmpeg)
    local b present=()
    for b in "${absent[@]}"; do
        command -v "$b" >/dev/null 2>&1 && present+=("$b")
    done
    assert_eq "${present[*]:-}" "" "these should not be reachable inside with_fake_bin"
}
with_fake_bin "true" _probe_unnamed_binaries_are_absent
""",
        "no unnamed binary may be reachable",
    )
    gate.log_pass(
        "docker, node, npm, npx, nvcc, aws, ssh, rsync, curl, wget, git, python3 and "
        "ffmpeg are all absent"
    )


def test_a_named_fake_records_its_arguments(gate):
    gate.log_test("a named fake is on PATH and records argv")
    expect_green(
        gate,
        """
_probe_fake_records_argv() {
    docker run --rm alpine echo hi
    nvcc --version
    assert_eq "$(fake_bin_record docker)" "run --rm alpine echo hi" "docker's argv is recorded verbatim"
    assert_eq "$(fake_bin_record nvcc)" "--version" "nvcc's argv is recorded verbatim"
}
with_fake_bin "docker nvcc" _probe_fake_records_argv
""",
        "a named fake records the argv it was called with",
    )
    gate.log_pass("a named fake is on PATH and records the argv it was called with")


def test_a_never_called_fake_records_nothing(gate):
    gate.log_test("an empty record must be distinguishable from a broken recorder")
    # "nvcc was never invoked" is an assertion the CUDA module's test makes, so the empty-record case has to be distinguishable from a recorder that lost the file.
    expect_green(
        gate,
        """
_probe_never_called_records_nothing() {
    assert_eq "$(fake_bin_record aws)" "" "a fake that was never invoked records nothing"
}
with_fake_bin "aws" _probe_never_called_records_nothing
""",
        "a fake never called reports no invocations",
    )
    gate.log_pass("a fake that was never called reports no invocations")


def test_exit_code_suffix_is_honoured(gate):
    gate.log_test("the name!<n> form controls the fake's exit code")
    expect_green(
        gate,
        """
_probe_exit_code_is_honoured() {
    local rc=0
    flaky || rc=$?
    assert_exit_code 7 "$rc" "name!7 must exit 7"
}
with_fake_bin "flaky!7" _probe_exit_code_is_honoured
""",
        "name!7 must exit 7",
    )
    gate.log_pass("the name!<n> form controls the fake's exit code")


def test_passthrough_admits_the_real_binary(gate):
    gate.log_test("the +name form admits the real binary")
    # `cut`, DELIBERATELY: it is not a bash builtin, so this can only succeed if the symlink to the real binary is what answered. An earlier draft of the twin asserted on `printf` and proved nothing, because bash's builtin would have satisfied it with PATH empty.
    expect_green(
        gate,
        """
_probe_passthrough_is_the_real_binary() {
    assert_eq "$(echo 'a:b' | cut -d: -f2)" "b" "+cut must be the real cut"
    assert_eq "$(fake_bin_record cut)" "" "a passthrough is not a recorder, so it records nothing"
}
with_fake_bin "+cut" _probe_passthrough_is_the_real_binary
""",
        "+cut must be the real cut",
    )
    gate.log_pass("the +name form admits the real binary by name")


def test_the_callers_path_is_never_touched(gate):
    gate.log_test("the restriction is scoped to a subshell")
    # The distinction keeps a failing assertion from being followed by "rm: command not found" as the EXIT traps unwind.
    expect_green(
        gate,
        PROBE_PATH_IS_ONLY_FAKES
        + """
before="$PATH"
with_fake_bin "docker" _probe_path_is_only_fakes
assert_eq "$PATH" "$before" "the caller's PATH must be unchanged by with_fake_bin"
""",
        "the caller's PATH must be unchanged",
    )
    gate.log_pass("the caller's PATH is untouched: the restriction is scoped to a subshell")


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
    """PORT-ONLY. Every case is `bash -c`; a host without bash would fail them all
    with `FileNotFoundError` from a helper, which reads as flake and names no fix."""
    gate.log_test("the interpreter these cases need is present")
    harness.require_tool("bash", "install bash; every case in this module drives the shell helper")
    gate.assertions += 1
    gate.log_pass("bash is on PATH at %s" % shutil.which("bash"))
