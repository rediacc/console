"""Port of `.ci/scripts/test/gates/test-media-cuda.sh`.

`.ci/media/cuda.sh`, the flash-attn accelerator probe.

This is the ONE function in the media pipeline whose behaviour depends on
hardware, and it is therefore the one most likely to be edited on a machine that
HAS a GPU and never exercised on one that does not. All four of its exits are
driven here with no GPU, no CUDA toolkit, no torch and no PyPI: a scripted
`python` fake answers the two questions the function asks it, `nvcc` is present or
absent BY NAME, and `pip` records what it was asked to install without installing
anything.

THE OWNERSHIP ASSERTION IS THE OTHER HALF. It used to be byte-identity against
run.sh's copy; run.sh has no copy any more, so what it asserts now is that this
module is the ONLY definition of the function, that run.sh and media.sh no longer
carry one, and that sourcing media-entry.sh resolves the name to this file's body.
There is no verb that reaches this function -- it is called from venv.sh, three
levels below `www tutorials generate` -- so the chain probe other media tests use
does not apply here, and the mutation control instead re-runs a real behaviour
case against a deliberately altered COPY of this module.

WHY A SCRIPTED `python` AND NOT THE RECORDING FAKE. The function asks python two
questions and both are `python -c`; the four exits differ ONLY in how those two
answer, which a uniform fake cannot express. The scripted fake matches on the
argument text, which is what makes "flash_attn imports but torch has no CUDA" a
distinguishable state from "neither".

NO `xdist_group`, and this one is worth stating rather than assuming, because the
media harness is the part of this suite most likely to need one. `fake_bin`
mutates PATH ON THIS PROCESS and restores it in a `finally`, so two of these
running in ONE worker would be fine and two in two workers are independent
processes. Nothing is bound, no fixed path is written (every case takes its own
`mktemp -d`), and `MEDIA_MODULE_DIR` is a per-call ARGUMENT in the port rather
than the environment variable it is in bash, which removes the one module-global
the twin does mutate.
"""

import stat

from rediacc_ci.tests.gates import harness, media_verify

BASH_TWIN = ".ci/scripts/test/gates/test-media-cuda.sh"

MODULE = media_verify.MEDIA_DIR / "cuda.sh"
FUNCTION = "install_flash_attn_if_supported"

# The spec every behaviour case runs under. `+uname` is REQUIRED rather than
# tidy: common.sh runs `CI_OS="$(detect_os)"` at source time and detect_os shells
# out to uname, so without it every run carries a stray "uname: command not
# found" on stderr. `nvcc` is deliberately ABSENT from this spec; the cases that
# want a compiler name it themselves.
BASE_SPEC = "python pip +cat +chmod +uname"


def script_python(bindir, flash_attn_imports: str, torch_cuda_answer: str) -> None:
    """Replace the recording `python` fake with one that answers the two probes.

    A uniform fake cannot do this: `import flash_attn` and the
    `torch.cuda.is_available()` query are both `python -c`, and the four exits
    differ only in how those two answer.
    """
    target = bindir / "python"
    target.write_text(
        "#!/bin/bash\n"
        'case "$*" in\n'
        "    *flash_attn*) exit %d ;;\n"
        '    *torch.cuda*) echo "%s"; exit 0 ;;\n'
        "esac\n"
        "exit 0\n" % (0 if flash_attn_imports == "yes" else 1, torch_cuda_answer),
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_cuda(root, *, module_dir=None):
    return media_verify.media_run_module(root, "cuda.sh", FUNCTION, module_dir=module_dir)


def test_this_module_solely_owns_the_moved_function(gate):
    gate.log_test("cuda.sh must be the ONLY definition, and media-entry.sh must resolve to it")
    media_verify.media_assert_module_owns(gate, "cuda.sh", FUNCTION)


def test_the_ownership_assertion_can_fail(gate):
    gate.log_test("CONTROL: every way the ownership assertion could go quiet")
    # A second definition put back into an origin (which is what a badly resolved merge against the pre-cutover file would produce), a name nothing defines anywhere (the vacuity the old byte-identity helper was built around), and an origin file that is not there to be read.
    with harness.temp_dir() as d:
        media_verify.media_assert_ownership_control(gate, d, "cuda.sh", FUNCTION)


def test_a_planted_mutation_is_visible_to_the_behaviour_cases(gate):
    gate.log_test("CONTROL FOR EVERY BEHAVIOUR CASE BELOW, and why the module seam exists")
    # The four exits are asserted by their MESSAGES; this re-runs the no-CUDA exit
    # against a copy of cuda.sh whose message has been changed, and requires the change to show up. If it did not, those four assertions would be reading something other than the module under test, and their green would mean nothing.
    with harness.temp_dir() as d:
        mutant = d / "mutant"
        mutant.mkdir()
        source = MODULE.read_text(encoding="utf-8")
        mutated = source.replace("CUDA not available in torch", "CUDA MUTATED")
        (mutant / "cuda.sh").write_text(mutated, encoding="utf-8")
        if "CUDA MUTATED" not in mutated:
            gate.log_fail(
                "the mutation did not apply, so this control would pass for the wrong reason"
            )
        with harness.fake_bin(BASE_SPEC) as fake:
            script_python(fake.dir, "no", "false")
            result = run_cuda(d, module_dir=mutant)
            gate.assert_exit_code(
                0, result.rc, "the mutated copy still runs; only its wording changed"
            )
            media_verify.media_assert_mutation_swapped(
                gate, result.combined, "CUDA not available in torch", "CUDA MUTATED", "message"
            )
    gate.log_pass("a one-line mutation in cuda.sh changes what the behaviour cases observe")


def test_all_four_exits(gate):
    gate.log_test("all four exits, with no GPU, no CUDA toolkit, no torch and no PyPI")
    with harness.temp_dir() as d:
        # ALREADY INSTALLED.
        with harness.fake_bin(BASE_SPEC) as fake:
            script_python(fake.dir, "yes", "true")
            result = run_cuda(d)
            gate.assert_exit_code(0, result.rc, "an already-importable flash_attn must return 0")
            gate.assert_eq(
                fake.record("pip"), "", "nothing may be installed when it already imports"
            )

        # NO CUDA IN TORCH.
        with harness.fake_bin(BASE_SPEC) as fake:
            script_python(fake.dir, "no", "false")
            result = run_cuda(d)
            gate.assert_exit_code(0, result.rc, "no CUDA in torch must SKIP, not fail")
            gate.assert_contains(
                result.combined, "CUDA not available in torch", "says why it skipped"
            )
            gate.assert_eq(fake.record("pip"), "", "nothing may be installed without CUDA")

        # NO NVCC. Deliberately NOT in the spec: absent is the condition under test.
        with harness.fake_bin(BASE_SPEC) as fake:
            script_python(fake.dir, "no", "true")
            result = run_cuda(d)
            gate.assert_exit_code(0, result.rc, "a missing nvcc must SKIP, not fail")
            gate.assert_contains(
                result.combined, "nvcc not found", "says which tool the source build needs"
            )
            gate.assert_eq(fake.record("pip"), "", "nothing may be installed without a compiler")

        # SUPPORTED.
        with harness.fake_bin(BASE_SPEC + " nvcc") as fake:
            script_python(fake.dir, "no", "true")
            result = run_cuda(d)
            gate.assert_exit_code(0, result.rc, "the supported path must return 0")
            pip_calls = fake.record("pip")
            gate.assert_contains(
                pip_calls, "install --upgrade packaging ninja", "build deps come first"
            )
            gate.assert_contains(
                pip_calls,
                "install flash-attn --no-build-isolation",
                "flash-attn is built without isolation",
            )
            gate.assert_eq(
                fake.record("nvcc"), "", "nvcc is PROBED with command -v, never executed"
            )
    gate.log_pass("already-installed, no-CUDA, no-nvcc and supported all reach their own exit")


def test_a_failing_install_only_warns(gate):
    gate.log_test("a failed accelerator install must not take the pipeline down with it")
    # `pip!1` is the fake_bin spelling for a recorder that exits 1.
    with harness.temp_dir() as d, harness.fake_bin("python pip!1 nvcc +cat +chmod +uname") as fake:
        script_python(fake.dir, "no", "true")
        result = run_cuda(d)
        gate.assert_exit_code(
            0, result.rc, "a failed accelerator install must not fail the pipeline"
        )
        gate.assert_contains(
            result.combined, "flash-attn install failed", "says the install failed"
        )
        gate.assert_contains(
            result.combined, "continuing without it", "and says the pipeline continues"
        )
    gate.log_pass("a failed flash-attn install warns and returns 0, so the pipeline survives it")
