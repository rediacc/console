"""Port of `.ci/scripts/test/gates/test-media-venv.sh`.

`.ci/media/venv.sh`, the generative Python environment.

TWO KINDS OF ASSERTION, and they answer different questions.

  OWNERSHIP. Every function here was moved out of run.sh, and phase 2 deleted
  run.sh's copies. While both existed the claim to check was byte-identity, and it
  was; with one copy left, the claim that means something is that there IS one copy:
  exactly one file defines each name, it is this module, the origins define none of
  them, and sourcing media-entry.sh resolves each name to this file's body. A second
  definition reappearing anywhere -- a merge against the pre-cutover run.sh is the
  obvious way -- is then red rather than discovered later by whichever copy happens
  to run.

  BEHAVIOUR. What the module does when its dependencies are missing, which is the
  only part CI can actually drive. Every case below runs with PATH emptied and
  refilled BY NAME, so python3, ffmpeg, sox, apt-get, sudo, pip, docker, node and the
  network are absent unless the case says otherwise.

cuda.sh IS SOURCED ALONGSIDE venv.sh in every case, and that is not tidiness: `install_generative_python_deps` calls `install_flash_attn_if_supported`, which lives in cuda.sh. The cross-module edge is real, so it is exercised rather than stubbed away -- if it broke, the pip case would die with "command not found".

`+uname` IS REQUIRED IN EVERY SPEC. `.ci/scripts/lib/common.sh` runs
`CI_OS="$(detect_os)"` at SOURCE time and `detect_os` shells out to `uname`, so a
spec without it carries a stray "uname: command not found" on stderr in a case whose assertions have nothing to do with it.

NO `xdist_group`, for the reasons written out in `test_gate_media_cuda.py`: `fake_bin` mutates PATH on THIS process and restores it in a `finally`, so two of these in one worker are fine and two in two workers are independent processes. Nothing is bound, every case takes its own `mktemp -d`, and `MEDIA_MODULE_DIR` is a per-call ARGUMENT here rather than the environment variable it
is in bash, which removes the one module-global the twin does mutate.
"""

import shutil

from rediacc_ci.tests.gates import harness, media_verify

BASH_TWIN = ".ci/scripts/test/gates/test-media-venv.sh"

MODULE = media_verify.MEDIA_DIR / "venv.sh"

MOVED = (
    "ensure_generative_repo",
    "ensure_python_installed",
    "ensure_audio_system_deps",
    "install_generative_python_deps",
    "ensure_generative_venv",
)

MODULES = "cuda.sh venv.sh"


def run_venv(root, code: str, *, module_dir=None) -> harness.RunResult:
    return media_verify.media_run_module(root, MODULES, code, module_dir=module_dir)


def test_every_moved_function_is_solely_owned_by_this_module(gate):
    gate.log_test("venv.sh must hold the ONLY definition of all five moved functions")
    media_verify.media_assert_module_owns(gate, "venv.sh", *MOVED)


def test_the_ownership_assertion_can_fail(gate):
    """CONTROL. An assertion nobody has watched fail is one nobody has checked.

    "Nothing defines it, so nothing else defines it either" is the specific way this one could go quiet -- the same vacuity the byte-identity helper it replaced was
    built around. The shared control drives all four arms; see `media_verify.py` for
    what they are and why the fourth, a MISSING origin, was the one nothing covered.
    """
    gate.log_test("CONTROL: every way the ownership assertion could go quiet")
    with harness.temp_dir() as d:
        media_verify.media_assert_ownership_control(gate, d, "venv.sh", "ensure_generative_repo")


def test_a_planted_mutation_is_visible_to_the_behaviour_cases(gate):
    """CONTROL FOR THE BEHAVIOUR CASES BELOW, which assert diagnoses by their exact
    wording. Change one of those messages in a COPY of the module and the assertion
    naming it must stop holding; if it still held, the cases would be reading
    something other than the module under test.
    """
    gate.log_test("CONTROL: a one-line mutation must change what the behaviour cases see")
    with harness.temp_dir() as d:
        (d / "empty").mkdir()
        mutant = d / "mutant"
        mutant.mkdir()
        source = MODULE.read_text(encoding="utf-8")
        mutated = source.replace(
            'log_error "Missing private/generative directory"', 'log_error "MUTATED"'
        )
        if 'log_error "MUTATED"' not in mutated:
            gate.log_fail(
                "the mutation did not apply, so this control would pass for the wrong reason"
            )
        (mutant / "venv.sh").write_text(mutated, encoding="utf-8")
        # cuda.sh travels with it: media_run_module sources both from `module_dir`, and a directory holding only the mutant would fail on the cross-module edge rather than on the plant.
        shutil.copy2(media_verify.MEDIA_DIR / "cuda.sh", mutant / "cuda.sh")
        with harness.fake_bin("+uname"):
            result = run_venv(d / "empty", "ensure_generative_repo", module_dir=mutant)
            gate.assert_exit_code(
                1,
                result.rc,
                "the mutated copy still fails on a missing checkout; only its wording changed",
            )
            media_verify.media_assert_mutation_swapped(
                gate,
                result.combined,
                "Missing private/generative directory",
                "MUTATED",
                "diagnosis",
            )
    gate.log_pass("a one-line mutation in venv.sh changes what the behaviour cases observe")


def test_ensure_generative_repo_diagnoses_all_three_states(gate):
    gate.log_test("absent, not-a-checkout and present must be told apart by name")
    with harness.temp_dir() as d:
        (d / "empty").mkdir()
        (d / "nogit" / "private" / "generative").mkdir(parents=True)
        (d / "good" / "private" / "generative" / ".git").mkdir(parents=True)

        # NO FAKES AT ALL beyond uname: this function shells out to nothing, and proving that is worth an empty PATH. If it ever grows a dependency, these three cases report it as not-found.
        with harness.fake_bin("+uname"):
            result = run_venv(d / "empty", "ensure_generative_repo")
            gate.assert_exit_code(1, result.rc, "a missing private/generative must fail")
            gate.assert_contains(
                result.combined, "Missing private/generative directory", "names what is missing"
            )
            gate.assert_contains(
                result.combined,
                "not a submodule",
                "keeps the diagnosis that git submodule cannot fix this",
            )

        with harness.fake_bin("+uname"):
            result = run_venv(d / "nogit", "ensure_generative_repo")
            gate.assert_exit_code(
                1, result.rc, "a private/generative that is not a checkout must fail"
            )
            gate.assert_contains(
                result.combined,
                "is not a git checkout",
                "distinguishes 'absent' from 'not a checkout'",
            )

        with harness.fake_bin("+uname"):
            result = run_venv(d / "good", "ensure_generative_repo")
            gate.assert_exit_code(
                0, result.rc, "a real checkout must pass (output: %s)" % result.combined
            )
    gate.log_pass(
        "ensure_generative_repo tells absent, not-a-checkout and present apart, using no "
        "external command"
    )


def test_ensure_python_installed_keys_on_the_interpreter(gate):
    gate.log_test("the interpreter probe must key on python3 and say which one is missing")
    with harness.temp_dir() as d:
        with harness.fake_bin("+uname"):
            result = run_venv(d, "ensure_python_installed")
            gate.assert_exit_code(1, result.rc, "python3 absent must fail")
            gate.assert_contains(
                result.combined, "python3 is required", "says which interpreter is missing"
            )

        with harness.fake_bin("python3 +uname"):
            result = run_venv(d, "ensure_python_installed")
            gate.assert_exit_code(
                0, result.rc, "python3 present must pass (output: %s)" % result.combined
            )
    gate.log_pass("ensure_python_installed fails without python3 and passes with it")


def test_ensure_audio_system_deps_installs_only_what_is_missing(gate):
    gate.log_test("nothing missing means nothing installed; something missing must be NAMED")
    with harness.temp_dir() as d:
        # python3 is faked as a success-with-no-output, which is what makes `import ensurepip` succeed and keeps the versioned python<X.Y>-venv package out of the missing list.
        with harness.fake_bin("python3 ffmpeg ffprobe sox apt-get sudo +uname") as fake:
            result = run_venv(d, "ensure_audio_system_deps")
            gate.assert_exit_code(
                0, result.rc, "nothing missing must return 0 (output: %s)" % result.combined
            )
            gate.assert_eq(
                fake.record("apt-get"), "", "nothing may be installed when nothing is missing"
            )
            gate.assert_eq(
                fake.record("sudo"), "", "sudo must not be invoked when nothing is missing"
            )

        # ffmpeg/ffprobe present, sox absent, and no apt-get to fix it with.
        with harness.fake_bin("python3 ffmpeg ffprobe +uname"):
            result = run_venv(d, "ensure_audio_system_deps")
            gate.assert_exit_code(1, result.rc, "a missing dep on a host with no apt-get must fail")
            gate.assert_contains(result.combined, "Missing system deps", "says what is missing")
            gate.assert_contains(result.combined, "sox", "names the missing package")
    gate.log_pass(
        "ensure_audio_system_deps installs nothing when nothing is missing, and names what it "
        "cannot fix"
    )


def test_install_generative_python_deps_drives_pip_and_stamps(gate):
    gate.log_test("the four pip installs, the cuda.sh hand-off, and the content-hash stamp")
    with harness.temp_dir() as d:
        (d / "gen").mkdir()
        # `cat` is admitted so the module can read the stamp file back; python and pip
        # are fakes. No network, no PyPI, no wheel is built.
        with harness.fake_bin("python pip +cat +uname") as fake:
            result = run_venv(
                d, "install_generative_python_deps '%s/gen' '%s/stamp' 'HASH123'" % (d, d)
            )
            gate.assert_exit_code(
                0,
                result.rc,
                "the install must succeed with pip faked (output: %s)" % result.combined,
            )
            gate.assert_eq(
                (d / "stamp").read_text(encoding="utf-8").strip(),
                "HASH123",
                "the content hash is written to the stamp file",
            )
            pip_calls = fake.record("pip")
            gate.assert_contains(pip_calls, "install --upgrade pip", "pip is upgraded first")
            gate.assert_contains(
                pip_calls, "install -e %s/gen" % d, "the generative package is installed editable"
            )
            gate.assert_contains(pip_calls, "install qwen-tts", "qwen-tts is installed")
            gate.assert_contains(pip_calls, "install qwen-asr", "qwen-asr is installed")
            # THE CROSS-MODULE EDGE. install_flash_attn_if_supported lives in cuda.sh, and with `import flash_attn` succeeding it returns before touching pip again. If the edge were broken the run would have died with "command not found" above rather than reaching this line.
            gate.assert_not_contains(
                pip_calls, "flash-attn", "flash-attn is skipped when it already imports"
            )
    gate.log_pass(
        "install_generative_python_deps runs the four pip installs, defers to cuda.sh, and "
        "writes the stamp"
    )
