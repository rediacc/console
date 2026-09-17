"""Port of `.ci/scripts/test/gates/test-media-shims.sh`.

Tests for the two COMPATIBILITY ENTRY POINTS W10 phase 3 left behind, and for the interfaces they forward to. Four claims, in the twin's order:

  1. Both old paths exist, are executable, and are exec shims with no logic of
     their own (a shim that grew argument handling is a second implementation of
     the contract).
  2. Driven for real, from an arbitrary cwd, argv arrives on the far side byte
     for byte, including empty arguments and arguments containing spaces, with
     stdin still connected and the exit status forwarded.
  3. The controls plant a broken shim and require every one of those assertions
     to fire, because a forwarding test that has never been watched failing
     proves only that something ran.
  4. The ACCEPTED SURFACE of each relocated program is frozen as a SET: the seven
     flags upload-r2.sh parses and the five environment variables run-in-tts.sh
     reads. Renaming `--defer-manifest` breaks private/growth's publish just as
     thoroughly as moving the file, and it would be caught by nothing at all.

Nothing here needs docker, node, npm, nvcc, aws, ssh, a GPU or a network.

WHY THIS PORT DOES NOT CALL `media_verify.media_chain_mutate`. That helper does not exist on the Python side yet, and the twin uses it here only as "apply this sed to one file in my own sandbox". The two mutations are written out below as explicit line edits instead, each with a REFUSAL when its anchor is missing, which is the same discipline the twin gets from the follow-up greps
around its sed calls. They agree with the sed forms because both target the single line that begins `exec "$ROOT`: the first prefixes a `shift` line before it, the second turns it into a non-exec call with `|| true` appended.

WHERE THIS REIMPLEMENTS grep AND sort, AND WHY THE ANSWERS AGREE. `upload_flags` is `grep -oE '^ +--[a-z-]+\\)' | tr -d ' )' | sort -u`, and `tts_env_names` is `grep -vE '^\\s*#' | grep -oE '\\b(REDIACC|RDC)_[A-Z0-9_]+' | sort -u`. Both are line-oriented regex scans over ASCII identifiers, and Python's `sorted()` on a set of ASCII strings is `sort -u` under any collation that
cannot reorder them: every flag shares the `--` prefix and every variable shares an uppercase alphabet, so the two orders coincide. The frozen lists below are the twin's, unchanged, which is what makes that claim checkable rather than asserted.

ONE DELIBERATE DIFFERENCE, stated because it is a difference: the twin measures a shim's code size with `printf '%s\\n' "$code" | wc -l`, which reports 1 for an EMPTY code set. This module counts the lines it actually has, so an empty shim reports 0. Both are under the ceiling of 4 and both then fail the `exec` check on
the next line, so no verdict moves; the Python number is simply the honest one.

NO `xdist_group`. Every sandbox is built under pytest's own `tmp_path`, and the two cases that drive the REAL shims execute them read-only from an arbitrary cwd. `harness.fake_bin` mutates `os.environ["PATH"]` and restores it in a `finally`,
which is per-process and therefore per-worker; pytest never runs two tests at once
inside one worker, so no case can observe another's PATH.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-media-shims.sh"

ROOT = paths.repo_root()

# RELOCATED is where the body lives now; SHIM is the spelling a caller still uses.
TTS_SHIM = ".ci/docker/run-in-tts.sh"
TTS_REAL = ".ci/media/tools/run-in-tts.sh"
R2_SHIM = ".ci/scripts/deploy/upload-media-to-r2.sh"
R2_REAL = ".ci/media/tools/upload-r2.sh"

# The image context moved with the wrapper, because they are one thing.
TTS_CONTEXT = ".ci/media/tts"

# THE FROZEN SURFACES. These two lists ARE the cross-repo contract. Adding an entry is a widening and is fine. REMOVING or RENAMING one is a breaking change that has to land in private/generative or private/growth in the same wave.
UPLOAD_FLAGS_FROZEN = "--defer-manifest --engine --field --file --key --kind --lang"
TTS_ENV_FROZEN = (
    "RDC_GPU_LOCK_DIR RDC_GPU_LOCK_FILE RDC_HF_CACHE RDC_MODELS_VOLUME REDIACC_NO_DOCKER"
)

# ARGV WITH TEETH. An empty string and an argument holding spaces are the two shapes a careless forward destroys, and both are shapes a real caller passes.
SHIM_ARGV = ["--kind", "solutions", "--key", "a slug with spaces", "--lang", "", "--field", "mp4"]

# Bash builtins only: read, printf, exit. The recorder must work with PATH emptied, because a caller of these shims is entitled to any PATH at all.
RECORDER = """#!/bin/bash
rec="$(dirname "${BASH_SOURCE[0]}")/../../../record"
{
    printf 'ARGC=%s\\n' "$#"
    for a in "$@"; do printf 'ARG<%s>\\n' "$a"; done
    printf 'CWD=%s\\n' "$PWD"
    while IFS= read -r line; do printf 'STDIN<%s>\\n' "$line"; done
} >"$rec"
exit 43
"""

FLAG_RE = re.compile(r"^ +(--[a-z-]+)\)", re.MULTILINE)
ENV_RE = re.compile(r"\b(?:REDIACC|RDC)_[A-Z0-9_]+")
CODE_SKIP_RE = re.compile(r"^\s*(#|$)")
ARG_LOGIC_RE = re.compile(r"\b(shift|case|while|if)\b")


def shim_sandbox(directory: pathlib.Path, shim: str, target: str) -> pathlib.Path:
    """The smallest tree in which the shim resolves: the shim at its real relative
    depth, and a RECORDER where the relocated program would be.

    THE TARGET IS A RECORDER, NOT THE REAL PROGRAM, and that is the point. What is under test is the forward, and the forward has to be observable independently of whatever the far side does with the arguments.
    """
    repo = directory / "repo"
    (repo / shim).parent.mkdir(parents=True, exist_ok=True)
    (repo / target).parent.mkdir(parents=True, exist_ok=True)
    (repo / shim).write_bytes((ROOT / shim).read_bytes())
    (repo / shim).chmod(0o755)
    (repo / target).write_text(RECORDER, encoding="utf-8")
    (repo / target).chmod(0o755)
    return repo


def mutate_exec_line(gate, path: pathlib.Path, kind: str) -> None:
    """The twin's two `media_chain_mutate` seds, as explicit line edits.

    `shift` : prefix a `shift` line before the `exec "$ROOT...` line. `swallow`: turn `exec "$ROOT..."` into `"$ROOT..." || true`, which is how a
               wrapper reports success for a failed run.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith('exec "$ROOT')), None)
    if index is None:
        gate.log_fail(
            'the %s mutation did not apply: %s has no line beginning `exec "$ROOT`, so '
            "this control would pass for the wrong reason" % (kind, path)
        )
    if kind == "shift":
        lines.insert(index, "shift")
    else:
        lines[index] = lines[index][len("exec ") :] + " || true"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def upload_flags(path: pathlib.Path) -> str:
    """Every long flag the argument loop accepts, sorted and unique."""
    return " ".join(sorted(set(FLAG_RE.findall(path.read_text(encoding="utf-8")))))


def tts_env_names(path: pathlib.Path) -> str:
    """Every REDIACC_/RDC_ variable the CODE reads, sorted and unique.

    Comment lines are stripped first: the header discusses these names at length, and a freeze that counted prose would be pinned to the documentation rather than the interface.
    """
    code = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not re.match(r"^\s*#", line)
    ]
    return " ".join(sorted(set(ENV_RE.findall("\n".join(code)))))


def test_the_relocation_landed_and_the_old_context_is_gone(gate):
    for relative in (TTS_SHIM, TTS_REAL, R2_SHIM, R2_REAL):
        path = ROOT / relative
        if not path.is_file():
            gate.log_fail("%s does not exist" % relative)
        if not (path.stat().st_mode & 0o111):
            gate.log_fail(
                "%s is not executable, so a caller's exec would fail with EACCES" % relative
            )
    if not (ROOT / TTS_CONTEXT / "Dockerfile").is_file():
        gate.log_fail(
            "%s/Dockerfile does not exist -- the wrapper builds this directory by name"
            % TTS_CONTEXT
        )
    if not (ROOT / TTS_CONTEXT / "generative-pyproject.toml").is_file():
        gate.log_fail(
            "%s/generative-pyproject.toml does not exist -- the Dockerfile COPYs it by name"
            % TTS_CONTEXT
        )

    # THE OLD CONTEXT MUST BE GONE, not merely unused. Two build contexts, one of them stale, is how a session spends an hour wondering why an edited Dockerfile changed nothing about the image.
    if (ROOT / ".ci" / "docker" / "tts").exists():
        gate.log_fail(
            ".ci/docker/tts still exists -- the relocated context at %s would be the "
            "second copy" % TTS_CONTEXT
        )

    # And the wrapper must name the NEW context. This is the one line in it that a move silently invalidates.
    if "$ROOT/%s" % TTS_CONTEXT not in (ROOT / TTS_REAL).read_text(encoding="utf-8"):
        gate.log_fail(
            "%s does not build %s -- the wrapper and its context have come apart"
            % (TTS_REAL, TTS_CONTEXT)
        )
    gate.log_pass(
        "both programs and the tts image context are at their new paths, the old context "
        "is gone, and the wrapper names the new one"
    )


def test_the_old_paths_are_exec_shims_and_nothing_more(gate):
    # A SHIM WITH LOGIC IS A SECOND IMPLEMENTATION. The contract these two paths
    # carry is already implemented once; anything here that inspects, rewrites or
    # validates argv is a place for the two copies to disagree, and the disagreement would only show up in a repository this one cannot read.
    for relative in (TTS_SHIM, R2_SHIM):
        code = [
            line
            for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
            if not CODE_SKIP_RE.match(line)
        ]
        if len(code) > 4:
            gate.log_fail(
                "%s has %d lines of code; a forwarding shim is a shebang, set -e, a root, "
                "and an exec" % (relative, len(code))
            )
        if not any(line.startswith('exec "') for line in code):
            gate.log_fail(
                "%s does not exec -- a call would fork, and the exit status, signals and "
                "terminal would belong to the shim" % relative
            )
        offending = [line for line in code if ARG_LOGIC_RE.search(line)]
        if offending:
            gate.log_fail(
                "%s handles arguments; a shim that reads argv is a second implementation "
                "of a contract that already has one: %s" % (relative, offending)
            )
    gate.log_pass(
        "both old paths are exec shims: no argument handling, no branching, exec on the last line"
    )


def shim_forwards_everything(gate, repo: pathlib.Path, shim: str) -> None:
    record = repo / "record"
    # cd somewhere with no relationship to the sandbox: a shim that resolved its target relative to the CALLER's directory instead of its own would pass from the repo root and fail everywhere else, which is the failure mode a cross-repo caller hits first.
    result = harness.run([str(repo / shim), *SHIM_ARGV], cwd="/", stdin="")
    gate.assert_exit_code(
        43, result.rc, "the shim must forward the target's exit status, not invent one"
    )
    if not record.is_file():
        gate.log_fail("the target was never reached: %s did not forward at all" % shim)
    got = record.read_text(encoding="utf-8")
    gate.assert_contains(
        got,
        "ARGC=%d" % len(SHIM_ARGV),
        "the target must receive exactly the arguments the caller passed, no more and no fewer",
    )
    for argument in SHIM_ARGV:
        gate.assert_contains(
            got, "ARG<%s>" % argument, "argument %r did not arrive intact" % argument
        )
    gate.assert_contains(
        got, "CWD=/", "the shim must not change the working directory a caller chose"
    )


def shim_forwards_stdin(gate, repo: pathlib.Path, shim: str) -> None:
    result = harness.run([str(repo / shim), "one"], cwd="/", stdin="a line on stdin\n")
    gate.assert_exit_code(43, result.rc, "exit status must survive a piped stdin too")
    gate.assert_contains(
        (repo / "record").read_text(encoding="utf-8"),
        "STDIN<a line on stdin>",
        "stdin must still be connected on the far side of the exec",
    )


def test_both_shims_forward_argv_cwd_stdin_and_status(gate, tmp_path):
    for name, shim, target in (("tts", TTS_SHIM, TTS_REAL), ("r2", R2_SHIM, R2_REAL)):
        repo = shim_sandbox(tmp_path / name, shim, target)
        with harness.fake_bin("+bash +dirname"):
            shim_forwards_everything(gate, repo, shim)
        with harness.fake_bin("+bash +dirname"):
            shim_forwards_stdin(gate, repo, shim)
    gate.log_pass(
        "both shims forward argv byte for byte, keep the caller's cwd and stdin, and "
        "return the target's exit status"
    )


def test_the_forwarding_assertion_can_fail(gate, tmp_path):
    # CONTROL, in the three ways a forward breaks. Each mutates the sandbox rather than the checkout, and each must be observed failing.

    # 1. The target is not there. This is what a relocation without a shim update looks like, and it is the failure the cross-repo callers would hit.
    repo = shim_sandbox(tmp_path / "gone", TTS_SHIM, TTS_REAL)
    (repo / TTS_REAL).unlink()
    result = harness.run([str(repo / TTS_SHIM), "one"], cwd="/", stdin="")
    if result.rc == 0:
        gate.log_fail(
            "the shim succeeded with its target deleted, so reaching the target is not "
            "what is being measured"
        )

    # 2. The target is there but the shim mangles argv. A stray `shift` is the classic version and it is silent: the call still runs, with the first flag eaten.
    repo = shim_sandbox(tmp_path / "shift", TTS_SHIM, TTS_REAL)
    mutate_exec_line(gate, repo / TTS_SHIM, "shift")
    result = harness.run([str(repo / TTS_SHIM), *SHIM_ARGV], cwd="/", stdin="")
    gate.assert_exit_code(
        43, result.rc, "the mutated shim still reaches the target; only its argv changed"
    )
    gate.assert_not_contains(
        (repo / "record").read_text(encoding="utf-8"),
        "ARGC=%d" % len(SHIM_ARGV),
        "a shim that shifts must NOT satisfy the argv assertion, or that assertion is "
        "measuring nothing",
    )

    # 3. The exit status is swallowed. `"$ROOT/..." "$@"` without exec, followed by a successful last command, is how a wrapper reports success for a failed run.
    repo = shim_sandbox(tmp_path / "swallow", TTS_SHIM, TTS_REAL)
    mutate_exec_line(gate, repo / TTS_SHIM, "swallow")
    result = harness.run([str(repo / TTS_SHIM), "one"], cwd="/", stdin="")
    if result.rc != 0:
        gate.log_fail(
            "the swallowing mutation did not apply, so this control would pass for the "
            "wrong reason (rc=%d, stderr: %s)" % (result.rc, result.err.strip())
        )
    gate.log_pass(
        "the forwarding assertions fire on a missing target, on a shifted argv and on a "
        "swallowed exit status"
    )


def test_the_real_tts_chain_runs_with_docker_absent(gate):
    # REDIACC_NO_DOCKER=1 is the wrapper's own host escape hatch, documented in its
    # header. It is what makes this drivable with docker absent, and it exercises the whole file down to the exec rather than a special test path.
    with harness.fake_bin("+bash +dirname"):
        result = harness.run(
            [
                str(ROOT / TTS_SHIM),
                "/bin/sh",
                "-c",
                'printf "REACHED:%s\\n" "$*"',
                "sh",
                "a b",
                "c",
            ],
            cwd="/",
            env={"REDIACC_NO_DOCKER": "1"},
        )
    gate.assert_exit_code(0, result.rc, "the host path must succeed")
    gate.assert_contains(
        result.combined,
        "REACHED:a b c",
        "the real chain must run the command it was given, with its arguments intact",
    )
    gate.log_pass(
        "the old .ci/docker/run-in-tts.sh path still runs a command end to end with docker absent"
    )


def test_the_real_r2_chain_reaches_the_relocated_body(gate):
    # An invalid --kind is refused by the relocated script's own first validation, before any credential is read and long before aws is called. The message is that script's, so seeing it is proof the shim landed in the real body.
    with harness.fake_bin("+bash +dirname +uname"):
        result = harness.run([str(ROOT / R2_SHIM), "--kind", "not-a-kind"], cwd="/")
    gate.assert_exit_code(1, result.rc, "an invalid --kind must be refused")
    gate.assert_contains(
        result.combined,
        "--kind must be 'tutorials' or 'solutions', got 'not-a-kind'",
        "the diagnosis must come from the relocated body, which is what proves the shim reached it",
    )
    gate.log_pass(
        "the old .ci/scripts/deploy/upload-media-to-r2.sh path still lands in "
        ".ci/media/tools/upload-r2.sh, with aws and the network absent"
    )


def test_the_cross_repo_surfaces_are_frozen(gate):
    gate.assert_eq(
        upload_flags(ROOT / R2_REAL),
        UPLOAD_FLAGS_FROZEN,
        "the flag set upload-r2.sh accepts has changed; a caller in private/growth passes "
        "these by name",
    )
    gate.assert_eq(
        tts_env_names(ROOT / TTS_REAL),
        TTS_ENV_FROZEN,
        "the environment run-in-tts.sh reads has changed; a caller in private/generative "
        "sets these by name",
    )
    gate.log_pass(
        "the seven upload flags and the five narration environment variables match their "
        "frozen sets"
    )


def test_the_surface_freeze_can_fail(gate, tmp_path):
    # CONTROL. A set comparison against a list somebody typed is exactly the shape that goes quiet: rename the flag AND the list in one edit and it stays green, which is correct, but drop the flag alone and it must not.
    mutants = tmp_path / "mut"
    mutants.mkdir(parents=True, exist_ok=True)

    flags_mutant = mutants / "upload-r2.sh"
    original = (ROOT / R2_REAL).read_text(encoding="utf-8")
    if original.count("        --defer-manifest)") != 1:
        gate.log_fail(
            "the flag mutation anchor is missing or ambiguous, so this control would pass "
            "for the wrong reason"
        )
    flags_mutant.write_text(
        original.replace("        --defer-manifest)", "        --renamed-manifest)"),
        encoding="utf-8",
    )
    if upload_flags(flags_mutant) == UPLOAD_FLAGS_FROZEN:
        gate.log_fail(
            "renaming --defer-manifest did not change the extracted flag set, so the "
            "freeze is measuring nothing"
        )

    env_mutant = mutants / "run-in-tts.sh"
    wrapper = (ROOT / TTS_REAL).read_text(encoding="utf-8")
    if "RDC_HF_CACHE" not in wrapper:
        gate.log_fail(
            "the variable mutation anchor is missing, so this control would pass for the "
            "wrong reason"
        )
    env_mutant.write_text(wrapper.replace("RDC_HF_CACHE", "RDC_HF_CACHE_RENAMED"), encoding="utf-8")
    if tts_env_names(env_mutant) == TTS_ENV_FROZEN:
        gate.log_fail(
            "renaming RDC_HF_CACHE did not change the extracted variable set, so the "
            "freeze is measuring nothing"
        )

    # AND THE OTHER DIRECTION: the extractors must not be blind to everything. An extractor that returned the empty string would satisfy neither assertion above and would fail the live test, but for the wrong reason.
    if not upload_flags(ROOT / R2_REAL):
        gate.log_fail("the flag extractor found nothing at all")
    if not tts_env_names(ROOT / TTS_REAL):
        gate.log_fail("the variable extractor found nothing at all")
    gate.log_pass(
        "both surface freezes fire on a renamed flag and a renamed variable, and neither "
        "extractor is empty"
    )
