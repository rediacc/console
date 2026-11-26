"""Gate test for `rediacc_ci.quality.detect_wasm` (`check:ci-detect-wasm`).

The gate rebuilds `detect.wasm` from the private/renet gitlink with `./build.sh detect_wasm` and compares it, `wasm_exec.js` and `detect-wasm.json` with private/account's committed copy (agent/plans/PLAN-forensics-detection.md D6, box FD11).

BOTH DIRECTIONS, ON THE REAL ARTIFACT. The selftest proves the comparison helpers on a synthetic byte string. That proves the helpers, not that the real rebuild matches, so the cases here run the whole gate, build included: green on the committed artifact, green on an untouched COPY of it under `--artifact-dir` (the control for every plant), and red on a copy with ONE flipped byte. The flip is planted twice: once with the json untouched, which R1 catches before any build, and once with the json's sha256 rewritten to match the flipped binary, which only the rebuild (R3) can catch. The second plant is the one that proves the rebuild is load bearing.

PROVENANCE IS THE INPUTS DIGEST. `renet_inputs_sha256` must move when a file the WASM build reads changes and must NOT move for a test-only or unrelated renet change, or every renet commit would again force an account commit. The digest cases run `./build.sh detect_wasm_inputs` over a scratch copy of the files the build needs (so the real tree is never planted): identical copy equal to the real tree (the control), a `_test.go` edit and an unrelated-package edit leave it unchanged, a detector source edit, a new detector file, and a go.mod edit each move it. A manifest recording a stale digest is rc 1 through R2 on the real rebuild path.

CANNOT RUN IS 77. With no `go` on PATH the gate must refuse a verdict and name the fix, never pass and never report a finding about the artifact.

The build is cached by Go after the first case, so the module runs in seconds. NO `xdist_group`: every case reads the real tree or writes only under its own tmp_path.
"""

import hashlib
import json
import os
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

MODULE = "rediacc_ci.quality.detect_wasm"
SUT = paths.from_root(".ci", "rediacc_ci", "quality", "detect_wasm.py")
ARTIFACT_SUBDIR = "private/account/src/services/forensics-detect/wasm"
REAL_ARTIFACT = paths.from_root(*ARTIFACT_SUBDIR.split("/"))
REAL_BUILD = paths.from_root("private", "renet", "build.sh")


def _run(*args: str, env_extra: dict[str, str] | None = None) -> harness.RunResult:
    env = {"PYTHONPATH": str(paths.from_root(".ci"))}
    env.update(env_extra or {})
    return harness.run([sys.executable, "-m", MODULE, *args], cwd=paths.repo_root(), env=env)


def _require_subject(gate) -> None:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    if not (REAL_ARTIFACT / "detect-wasm.json").is_file():
        gate.log_fail(
            "the committed artifact is missing at %s. Fix: git submodule update --init private/account"
            % ARTIFACT_SUBDIR
        )
    if not REAL_BUILD.is_file():
        gate.log_fail(
            "private/renet is not checked out. Fix: git submodule update --init private/renet"
        )
    harness.require_tool(
        "go", "install the pinned Go from .devcontainer/toolchain.env (./run.sh setup)"
    )


def _copy(tmp_path: pathlib.Path) -> pathlib.Path:
    copy = tmp_path / "wasm"
    shutil.copytree(REAL_ARTIFACT, copy)
    return copy


def _flip_one_byte(copy: pathlib.Path) -> str:
    path = copy / "detect.wasm"
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    return hashlib.sha256(bytes(data)).hexdigest()


def test_gate_green_on_the_committed_artifact(gate):
    gate.log_test("the gate rebuilds from the gitlink and matches the committed artifact")
    _require_subject(gate)
    result = _run()
    gate.assert_exit(0, result, "the committed artifact must be what the gitlink builds")
    gate.assert_contains(result.combined, "controls first", "controls ran before the verdict")
    gate.assert_contains(
        result.combined, "every plant fired", "the selftest reported in the real run"
    )
    manifest = json.loads((REAL_ARTIFACT / "detect-wasm.json").read_text(encoding="utf-8"))
    gate.assert_contains(
        result.combined,
        "inputs %s" % manifest["renet_inputs_sha256"][:16],
        "the verdict names the detector inputs digest",
    )
    gate.assert_contains(
        result.combined, "sha256 %s" % manifest["sha256"][:16], "the verdict names the hash"
    )
    gate.log_pass("committed artifact reproduces")


def test_selftest_passes(gate):
    gate.log_test("the gate's own controls pass behind --selftest")
    _require_subject(gate)
    result = _run("--selftest")
    gate.assert_exit(0, result, "selftest must pass")
    gate.assert_contains(result.combined, "every plant fired", "selftest verdict present")
    gate.log_pass("selftest green")


def test_unplanted_copy_is_green(gate, tmp_path):
    gate.log_test("CONTROL: an untouched copy under --artifact-dir is green")
    _require_subject(gate)
    result = _run("--artifact-dir", str(_copy(tmp_path)))
    gate.assert_exit(0, result, "the copy must be green, or every plant below proves nothing")
    gate.log_pass("unplanted copy green")


def test_one_flipped_byte_is_caught(gate, tmp_path):
    gate.log_test("PLANT: one flipped byte in a copy of detect.wasm is rc 1")
    _require_subject(gate)
    copy = _copy(tmp_path)
    _flip_one_byte(copy)
    result = _run("--artifact-dir", str(copy))
    gate.assert_exit(1, result, "a flipped byte must be a finding")
    gate.assert_contains(
        result.combined, "changed without a rebuild (R1)", "the manifest check names it"
    )
    gate.assert_contains(
        result.combined, "is not what the gitlink builds (sha256", "the rebuild names it too"
    )
    gate.log_pass("flipped byte caught")


def test_flipped_byte_with_a_matching_json_is_caught_by_the_rebuild(gate, tmp_path):
    gate.log_test(
        "PLANT: a flipped byte whose json sha256 was rewritten to match is still rc 1, through the rebuild"
    )
    _require_subject(gate)
    copy = _copy(tmp_path)
    forged = _flip_one_byte(copy)
    manifest_path = copy / "detect-wasm.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = forged
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = _run("--artifact-dir", str(copy))
    gate.assert_exit(1, result, "only the rebuild can catch this, and it must")
    gate.assert_not_contains(
        result.combined, "(R1)", "the manifest is self-consistent, so R1 stays silent"
    )
    gate.assert_contains(
        result.combined, "is not what the gitlink builds (sha256", "the rebuild caught it"
    )
    gate.log_pass("forged manifest caught by the rebuild")


def test_missing_go_cannot_run(gate, tmp_path):
    gate.log_test(
        "CANNOT RUN: with no go on PATH the gate refuses a verdict (77) and names the fix"
    )
    _require_subject(gate)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("git", "bash"):
        found = shutil.which(tool)
        if found is None:
            gate.log_fail("%s is not on PATH; this case cannot build its PATH" % tool)
            continue
        os.symlink(found, bindir / tool)
    result = _run(env_extra={"PATH": str(bindir)})
    gate.assert_exit(77, result, "a missing go must refuse, never pass")
    gate.assert_contains(
        result.combined, "`go` is not on PATH", "the refusal names the missing tool"
    )
    gate.log_pass("missing go refused")


def _inputs_digest(renet: pathlib.Path) -> str:
    result = harness.run(
        ["bash", str(renet / "build.sh"), "detect_wasm_inputs"],
        cwd=renet,
        env={"GOTOOLCHAIN": "local"},
    )
    assert result.rc == 0, result.combined
    digest = result.out.strip()
    assert len(digest) == 64, "expected a bare sha256 on stdout, got %r" % digest
    return digest


def _scratch_renet(tmp_path: pathlib.Path) -> pathlib.Path:
    """The files the detector build needs, copied; nothing under the real tree is written."""
    scratch = tmp_path / "renet"
    scratch.mkdir()
    for rel in ("build.sh", "go.mod", "go.sum"):
        shutil.copy2(REAL_BUILD.parent / rel, scratch / rel)
    for rel in ("scripts/pull-with-retry.sh",):
        (scratch / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REAL_BUILD.parent / rel, scratch / rel)
    for rel in ("pkg/detect", "pkg/models", "cmd/detectwasm", "pkg/i18n"):
        shutil.copytree(REAL_BUILD.parent / rel, scratch / rel)
    return scratch


def test_inputs_digest_ignores_tests_and_unrelated_packages(gate, tmp_path):
    gate.log_test(
        "CONTROL: the digest is stable under a copy and under test-only and unrelated edits"
    )
    _require_subject(gate)
    scratch = _scratch_renet(tmp_path)
    base = _inputs_digest(scratch)
    manifest = json.loads((REAL_ARTIFACT / "detect-wasm.json").read_text(encoding="utf-8"))
    gate.assert_eq(
        base,
        manifest["renet_inputs_sha256"],
        "a copy of the build's files digests like the real tree, which the committed manifest records",
    )
    tests = sorted((scratch / "cmd" / "detectwasm").glob("*_test.go"))
    gate.assert_eq(
        bool(len(tests) > 0), True, "the scratch copy holds a detector test file to edit"
    )
    with tests[0].open("a", encoding="utf-8") as fh:
        fh.write("// test-only edit\n")
    gate.assert_eq(_inputs_digest(scratch), base, "a _test.go edit does not move the digest")
    (scratch / "pkg" / "unrelated_pkg").mkdir()
    (scratch / "pkg" / "unrelated_pkg" / "x.go").write_text(
        "package unrelated_pkg\n", encoding="utf-8"
    )
    (scratch / "README.md").write_text("docs\n", encoding="utf-8")
    gate.assert_eq(_inputs_digest(scratch), base, "an unrelated package and a doc do not move it")
    gate.log_pass("digest ignores tests and unrelated files")


def test_inputs_digest_moves_on_detector_changes(gate, tmp_path):
    gate.log_test(
        "PLANT: a detector source edit, a new detector file and a go.mod edit each move the digest"
    )
    _require_subject(gate)
    scratch = _scratch_renet(tmp_path)
    base = _inputs_digest(scratch)
    seen = {base}
    with (scratch / "cmd" / "detectwasm" / "api.go").open("a", encoding="utf-8") as fh:
        fh.write("// detector edit\n")
    edited = _inputs_digest(scratch)
    gate.assert_eq(
        bool(edited not in seen), True, "an edit to cmd/detectwasm/api.go moves the digest"
    )
    seen.add(edited)
    (scratch / "pkg" / "detect" / "zz_planted.go").write_text("package detect\n", encoding="utf-8")
    added = _inputs_digest(scratch)
    gate.assert_eq(bool(added not in seen), True, "a new file in pkg/detect moves the digest")
    seen.add(added)
    with (scratch / "go.mod").open("a", encoding="utf-8") as fh:
        fh.write("// go.mod edit\n")
    gate.assert_eq(
        bool(_inputs_digest(scratch) not in seen), True, "a go.mod edit moves the digest"
    )
    gate.log_pass("detector-side changes move the digest")


def test_stale_inputs_digest_is_caught(gate, tmp_path):
    gate.log_test("PLANT: a manifest recording another inputs digest is rc 1 through R2")
    _require_subject(gate)
    copy = _copy(tmp_path)
    manifest_path = copy / "detect-wasm.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["renet_inputs_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = _run("--artifact-dir", str(copy))
    gate.assert_exit(1, result, "a stale digest must be a finding")
    gate.assert_contains(
        result.combined, "changed without a rebuild (R2)", "R2 names the stale inputs"
    )
    gate.log_pass("stale digest caught")
