"""`rediacc_ci.security.actionlint`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/security/actionlint.sh` and the port over one scratch repository apiece and compared the exit code, both streams and the recorded argv of every tool call.

The ledger `.ci/shadow/w7p6-actionlint.observations.jsonl` recorded that comparison over five distinct trees, every one of them EQUIVALENT; the row count is stated here from the file rather than carried forward from the sentence that used to claim it.

Every FIXTURE case now compares against `goldens/actionlint/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree; each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

HOW THE CORPUS IS HELD STABLE, which is the whole difficulty of freezing a gate that shells out to a real linter. Three things could put a version or a host into a recorded byte, and each is removed at the source rather than masked afterwards.

  * THE TOOL ITSELF IS A RECORDING FAKE in every frozen case. The real actionlint
    is never run by a golden, so no recorded byte carries its output, its
    wording or its version banner.
  * THE PIN IS THE FIXTURE'S OWN. The scratch repository carries its own
    `.devcontainer/toolchain.env` and `.ci/config/constants.sh`, and the builder
    rewrites `ACTIONLINT_VERSION` to `0.0.0-fixture` and both pinned checksums to
    a fixed literal. Both implementations read the pin from the tree they are
    standing in, so a real pin bump cannot red one recorded byte.
  * THE ARCHITECTURE IS MASKED, because `uname -m` is the one input the fixture
    cannot own: the fetch message and the download URL name `amd64` on this
    host and `arm64` on another, and a recording is compared on whichever runner
    picks it up.

WHAT ELSE IS MASKED, and it is the harness's own doing rather than the port's: the scratch repository's path becomes `<fx>` and its per-case tool cache becomes `<cache>`, both of which the differential already folded for the same reason. Nothing else is touched.

THE REAL-TREE CASES ARE DELIBERATELY NOT FROZEN, and that is a decision rather than an omission. A recording of "actionlint clean across 29 workflow file(s)" is a recording of this repository's workflow directory on the day it was taken, and the next workflow file added would red it for a reason that has nothing to do with the port. Those two cases survive as live runs against the
real tree with the real pinned binary, asserting the SHAPE (the count matches `collect_targets`, the banner is present, no input file was mutated) rather than a frozen byte.

ONE FROZEN CASE IS COMPARED BY SHAPE, and it is an inherited decision rather than a surprise: under `CI=true` with stderr on a tty, `common.sh` emits colour and `rediacc_ci.log` does not, because GitHub's log viewer renders escapes as literal text. Both halves are asserted, so nobody "fixes" either side.

ONE PATH CANNOT BE DRIVEN AT ALL, named rather than skipped silently: the unsupported-architecture refusal reads `uname -m` in bash and `platform.machine()` in Python, and neither can be faked for the other. The port's strings are asserted directly instead, and the twin's wording is recoverable from the blob sha every golden header carries.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.security import actionlint as port
from rediacc_ci.tests import differential, frozen

ROOT = paths.repo_root()
SLUG = "actionlint"

TWIN_REL = ".ci/scripts/security/actionlint.sh"
PORT_REL = ".ci/rediacc_ci/security/actionlint.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

CALLS_MARKER = "--- calls ---\n"

# The fixture's own pin, so no recorded byte depends on the real one. See the module docstring.
FIXTURE_VERSION = "0.0.0-fixture"
FIXTURE_SHA = "f" * 64
ARCH_RE = re.compile(r"(?<![A-Za-z0-9])(?:amd64|arm64)(?![A-Za-z0-9])")

# The minimum of the package a path-invoked port needs. Deliberately short: the fixture must not become a second copy of the repository.
COPIED = (
    ".ci/scripts/lib/common.sh",
    ".ci/config/constants.sh",
    ".devcontainer/toolchain.env",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

# What a BASH subject needed in the tree on top of that: the twin itself. Reached only by the one-shot recorder, which ran while the twin was still tracked; the suite's subject is the port or a throwaway mutant of it.
TWIN_ONLY = (TWIN_REL,)

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

# A version probe that answers with a chosen exit code and no output at all.
FAKE_VERSION_EXIT = """#!/bin/bash
[[ "$1" == "--version" ]] && exit %d
printf 'FAKECALL actionlint %%s\\n' "$*" >>"$FAKE_LOG"
exit 0
"""

# A curl that records its argv and then does whatever `$FAKE_DATA/curl.mode` says. `fail` exits 22 SILENTLY: a real curl under `-fsSL` prints `curl: (22) ...` of its own, and the two sides routed curl's stderr differently, so a talking fake would have failed the differential for a reason that is not the port's.
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

# name -> how the case is wired. `tweak` names the edit made to the built fixture, `path_has_tool` hides the fake actionlint so the acquisition path is reached, `tty` puts stderr on a pty, and `env` adds to the base environment.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-clean-fixture": {},
    "a-yaml-extension-after-every-yml": {"tweak": "add-yaml"},
    "a-second-out-of-tree-template": {"tweak": "add-template"},
    "findings-exit-1": {"tweak": "findings"},
    "only-the-template-survives": {"tweak": "drop-github"},
    "an-empty-template-glob": {"tweak": "drop-template"},
    "a-wrong-version-on-path": {"tweak": "wrong-version"},
    "a-silent-version-probe": {"tweak": "silent-version"},
    "a-failing-version-probe": {"tweak": "version-exit-3"},
    "a-failing-version-probe-exiting-1": {"tweak": "version-exit-1"},
    "a-failing-version-probe-exiting-2": {"tweak": "version-exit-2"},
    "a-failing-version-probe-exiting-9": {"tweak": "version-exit-9"},
    "a-failed-download": {"tweak": "curl-fail", "path_has_tool": False},
    "a-checksum-mismatch": {"tweak": "curl-garbage", "path_has_tool": False},
    "a-verified-download": {"tweak": "curl-good", "path_has_tool": False},
    "colour-on-a-tty": {"tty": "stderr"},
    "ci-true-on-a-tty": {"tty": "stderr", "env": {"CI": "true"}},
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte. Compared by shape, in its own test.
DIVERGENT = ("ci-true-on-a-tty",)


def write(path: pathlib.Path, body: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def repin(fx: pathlib.Path, *, version: str = FIXTURE_VERSION, sha: str = FIXTURE_SHA) -> None:
    """Give the scratch repository its OWN pin and checksums.

    Both implementations resolve the pin from the tree they are standing in, so this is what keeps every recorded byte independent of the real `ACTIONLINT_VERSION` and of a checksum that changes with it.
    """
    env_file = fx / ".devcontainer" / "toolchain.env"
    lines = [
        "ACTIONLINT_VERSION=%s" % version if line.startswith("ACTIONLINT_VERSION=") else line
        for line in env_file.read_text(encoding="utf-8").split("\n")
    ]
    env_file.write_text("\n".join(lines), encoding="utf-8")

    constants = fx / ".ci" / "config" / "constants.sh"
    text = constants.read_text(encoding="utf-8")
    for key in ("ACTIONLINT_SHA256_LINUX_AMD64", "ACTIONLINT_SHA256_LINUX_ARM64"):
        text = "\n".join(
            'readonly %s="%s"' % (key, sha) if line.startswith("readonly %s=" % key) else line
            for line in text.split("\n")
        )
    constants.write_text(text, encoding="utf-8")


def seed_cache(fx: pathlib.Path) -> None:
    """A cached binary at the fixture's pin, so a case reaches neither curl nor the PATH copy."""
    cache = fx / "cache" / ("actionlint-%s" % FIXTURE_VERSION)
    write(cache / "actionlint", FAKE_ACTIONLINT, mode=0o755)


def tweak(fx: pathlib.Path, kind: str | None) -> None:
    """The edit one case makes to the built fixture."""
    if kind is None:
        return
    data = fx / "fake" / "data"
    if kind == "add-yaml":
        write(fx / ".github" / "workflows" / "aaa.yaml", CLEAN_WORKFLOW % "aaa")
    elif kind == "add-template":
        write(fx / ".ci" / "aaa" / "workflow" / "vendored.yml", CLEAN_WORKFLOW % "vendored")
    elif kind == "findings":
        write(data / "rc", "1\n")
        write(data / "findings", 'a.yml:3:5: unexpected key "jobss" [syntax-check]\n')
    elif kind == "drop-github":
        shutil.rmtree(fx / ".github")
    elif kind == "drop-template":
        shutil.rmtree(fx / ".ci" / "breakpoint")
    elif kind == "wrong-version":
        write(data / "version", "9.9.9\n")
        seed_cache(fx)
    elif kind == "silent-version":
        write(fx / "fake" / "bin" / "actionlint", FAKE_VERSION_EXIT % 0, mode=0o755)
        seed_cache(fx)
    elif kind.startswith("version-exit-"):
        code = int(kind.rsplit("-", 1)[1])
        write(fx / "fake" / "bin" / "actionlint", FAKE_VERSION_EXIT % code, mode=0o755)
        seed_cache(fx)
    elif kind == "curl-fail":
        write(data / "curl.mode", "fail\n")
    elif kind == "curl-garbage":
        write(data / "curl.mode", "garbage\n")
    elif kind == "curl-good":
        build_tarball(fx)
        write(data / "curl.mode", "good\n")
    else:
        raise AssertionError("no such tweak: %r" % kind)


def build_tarball(fx: pathlib.Path) -> None:
    """A REAL tar.gz whose REAL sha256 is written into the fixture's own constants.

    The acquisition case proves the verify-then-extract sequence rather than skipping past it, so the checksum has to be the tarball's own. It never reaches either stream on the success path, so the recording stays stable even though gzip stamps the archive with the hour it was built.
    """
    payload = fx / "fake" / "payload" / "actionlint"
    write(payload, FAKE_ACTIONLINT, mode=0o755)
    tarball = fx / "fake" / "data" / "actionlint.tar.gz"
    tarball.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(str(tarball), "w:gz") as archive:
        archive.add(str(payload), arcname="actionlint")
    repin(fx, sha=hashlib.sha256(tarball.read_bytes()).hexdigest())


def build(tmp_path: pathlib.Path, name: str, *, subject_rel: str = PORT_REL) -> pathlib.Path:
    """A scratch repository holding the subject, the fakes and this case's edit."""
    fx = tmp_path / "fx"
    for rel in COPIED + (TWIN_ONLY if subject_rel.endswith(".sh") else ()):
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    repin(fx)

    for workflow in ("alpha", "beta"):
        write(fx / ".github" / "workflows" / ("%s.yml" % workflow), CLEAN_WORKFLOW % workflow)
    # A TEMPLATE IS MANDATORY IN EVERY FIXTURE, and not as scenery: without one the twin died silently at `targets="$(collect_targets)"` before doing anything at all. `an-empty-template-glob` is the case that records it.
    write(fx / ".ci" / "breakpoint" / "workflow" / "breakpoint.yml", CLEAN_WORKFLOW % "bp")

    data = fx / "fake" / "data"
    data.mkdir(parents=True, exist_ok=True)
    write(data / "version", "%s\n" % FIXTURE_VERSION)
    write(data / "rc", "0\n")

    bindir = fx / "fake" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    write(bindir / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    write(bindir / "curl", FAKE_CURL, mode=0o755)

    tweak(fx, CASE_KW[name].get("tweak"))
    return fx


def mask(text: str, fx: pathlib.Path) -> str:
    masked = text.replace(str(fx / "cache"), "<cache>").replace(str(fx), "<fx>")
    return ARCH_RE.sub("<arch>", differential.mask_toolchain_tmp(masked))


def drive(
    fx: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    """One subject, once, over an already-built fixture."""
    kw = CASE_KW[name]
    log = fx / "calls.log"
    log.write_text("", encoding="utf-8")
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["FAKE_DATA"] = str(fx / "fake" / "data")
    env["FAKE_LOG"] = str(log)
    # RUNNER_TEMP, so the acquisition cache is this case's own scratch. NOT `CI_TEMP`, which the twin's line names and `common.sh` overwrites two lines earlier; setting CI_TEMP here would silently leave the run pointed at the real /tmp cache and the download cases would never run. That is the defect, used as the suite's own control.
    env["RUNNER_TEMP"] = str(fx / "cache")
    if kw.get("path_has_tool", True):
        env["PATH"] = "%s%s%s" % (fx / "fake" / "bin", os.pathsep, env["PATH"])
    else:
        # The same scratch PATH, minus the fake actionlint. `curl` must stay, because the acquisition path is what this shape exists to reach.
        hidden = fx / "fake" / "nobin"
        hidden.mkdir(parents=True, exist_ok=True)
        write(hidden / "curl", FAKE_CURL, mode=0o755)
        env["PATH"] = "%s%s%s" % (hidden, os.pathsep, differential.BASE_ENV["PATH"])
    if subject_rel.endswith(".sh"):
        command = "bash %s" % (fx / subject_rel)
    else:
        env["PYTHONPATH"] = str(fx / ".ci")
        command = "PYTHONPATH=%s python3 %s" % (env["PYTHONPATH"], fx / subject_rel)
    env.update(kw.get("env") or {})

    if kw.get("tty"):
        code, out, err = differential.bash_streams(
            command, env=env, cwd=str(fx), tty=kw["tty"], timeout=180
        )
    else:
        argv = (
            ["bash", str(fx / subject_rel)]
            if subject_rel.endswith(".sh")
            else [
                "python3",
                str(fx / subject_rel),
            ]
        )
        proc = subprocess.run(
            argv, env=env, cwd=str(fx), capture_output=True, text=True, check=False, timeout=180
        )
        code, out, err = proc.returncode, proc.stdout, proc.stderr
    calls = mask(log.read_text(encoding="utf-8"), fx).splitlines()
    return code, mask(out, fx), mask(err, fx), calls


def run(
    tmp_path: pathlib.Path, name: str, *, subject_rel: str = PORT_REL
) -> tuple[int, str, str, list[str]]:
    return drive(build(tmp_path, name, subject_rel=subject_rel), name, subject_rel=subject_rel)


def render(code: int, stdout: str, stderr: str, calls: list[str]) -> str:
    return "%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        "\n".join(calls),
    )


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls.rstrip("\n").splitlines(),
    )


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the tool calls diverged: %r vs %r" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_carries_a_real_pin_or_a_host_path() -> None:
    """THE STABILITY CLAIM, checked over the corpus rather than argued in prose.

    A golden that named the live `ACTIONLINT_VERSION`, one of the real pinned checksums, or an absolute path from the recording host would be a golden that reds on the next pin bump or on another runner.
    """
    live_version = port.actionlint_version(ROOT)
    live_sums = set(port.actionlint_checksums(ROOT).values())
    for name in CASES:
        code, stdout, stderr, calls = recorded(name)
        del code
        blob = "\n".join([stdout, stderr, *calls])
        assert live_version not in blob, name
        for checksum in live_sums:
            assert checksum not in blob, name
        assert str(ROOT) not in blob, name
        assert "/tmp/" not in blob.replace("<fx>", "").replace("<cache>", ""), name


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_clean_fixture_lints_all_three_files() -> None:
    code, _, stderr, calls = recorded("a-clean-fixture")
    assert code == 0
    assert "clean across 3 workflow file(s)" in stderr
    assert len(calls) == 1, calls


def test_the_yaml_extension_is_collected_after_every_yml() -> None:
    """`*.yml` is a SEPARATE pass from `*.yaml`, and the passes concatenate."""
    code, _, _, calls = recorded("a-yaml-extension-after-every-yml")
    assert code == 0
    argv = calls[0].split()
    # The template pass is always last, so the `.yaml` file sits just before it and AFTER both `.yml` files, which is exactly what "separate pass, concatenated" means and what one merged `sorted()` would destroy.
    assert [a.rsplit("/", 1)[-1] for a in argv[3:]] == [
        "alpha.yml",
        "beta.yml",
        "aaa.yaml",
        "breakpoint.yml",
    ], calls[0]


def test_the_out_of_tree_workflow_template_is_collected() -> None:
    """`.ci/*/workflow/*.yml`, the coverage every other workflow gate misses.

    Every fixture carries one; the SECOND one here sits under a different `.ci/*` directory, which proves the middle `*` is expanded and sorted rather than hardcoded to `breakpoint`.
    """
    code, _, stderr, calls = recorded("a-second-out-of-tree-template")
    assert code == 0
    assert "over 4 workflow file(s)" in stderr
    argv = calls[0].split()
    assert argv[-2].endswith("/.ci/aaa/workflow/vendored.yml"), calls[0]
    assert argv[-1].endswith("/.ci/breakpoint/workflow/breakpoint.yml"), calls[0]


def test_findings_exit_1_with_the_four_error_lines() -> None:
    code, stdout, stderr, _ = recorded("findings-exit-1")
    assert code == 1
    assert "ZERO jobs and no error message anywhere." in stderr
    assert "unexpected key" in stdout, "actionlint's own finding must stay on STDOUT"


def test_only_the_template_survives_and_it_is_still_linted() -> None:
    """Deleting `.github/workflows` leaves the template, which IS the corpus."""
    code, _, stderr, _ = recorded("only-the-template-survives")
    assert code == 0
    assert "over 1 workflow file(s)" in stderr


def test_an_empty_template_glob_kills_the_twin_silently() -> None:
    """THE DEFECT THIS WAVE FOUND, reproduced on both sides. Port note 3.

    `collect_targets` ended with `for f in "$ROOT"/.ci/*/workflow/*.yml; do [[ -f "$f" ]] && echo "$f"; done`, so when that glob matched nothing the function returned 1 and `set -e` killed the script at the assignment: exit 1, ZERO bytes on both streams, with two real workflow files sitting unlinted. Exit 1 is also the code for "actionlint reported findings", so the CI reader is
    sent looking for an expression error that does not exist.
    """
    assert recorded("an-empty-template-glob")[:3] == (1, "", "")
    assert recorded("an-empty-template-glob")[3] == [], "actionlint must not be called at all"


def test_the_exit_3_refusal_is_unreachable() -> None:
    """The corollary, stated as its own assertion so it cannot be forgotten.

    Every tree splits two ways: the template glob matches, so the corpus is non-empty and the count test passes, or it does not, so the script is already dead. There is no third case and therefore no input that reaches the exit-3 message. Both directions are recorded, and the message is asserted absent from each.
    """
    with_template = recorded("only-the-template-survives")
    without_template = recorded("an-empty-template-glob")
    assert with_template[0] == 0
    assert without_template[:3] == (1, "", "")
    for result in (with_template, without_template):
        assert "a lint run over zero files" not in result[2]
    assert "a lint run over zero files reports success while checking nothing" in PORT.read_text(
        encoding="utf-8"
    ), "the port dropped the unreachable branch; rewrite this case"


def test_a_wrong_version_on_path_is_announced_then_the_cache_is_used() -> None:
    """The PATH binary loses, and the gate says so before falling through."""
    code, _, stderr, _ = recorded("a-wrong-version-on-path")
    assert code == 0
    assert "9.9.9 is on PATH but this gate pins" in stderr


def test_a_silent_version_prints_the_twins_double_space() -> None:
    """`have` is empty and the message keeps the gap. Port note 2.

    `--version` SUCCEEDS here and simply says nothing, which is the only way to reach the empty-`have` message: a probe that FAILS kills the gate first, and the next case is that one.
    """
    code, _, stderr, _ = recorded("a-silent-version-probe")
    assert code == 0
    assert "actionlint  is on PATH but this gate pins" in stderr


def test_a_failing_version_probe_kills_the_gate_silently() -> None:
    """THE THIRD DEFECT, reproduced on both sides. Port note 10.

    `have="$(actionlint --version 2>/dev/null | head -1 | tr -d 'v')"` under `set -euo pipefail`: the probe's non-zero status travelled through the command substitution and `set -e` ended the run.

    The status here is 3, which is this gate's DOCUMENTED code for "nothing to check (vacuous)", so a broken shim on PATH is reported to CI as an empty corpus, with no message at all and three perfectly readable workflow files left unlinted.
    """
    assert recorded("a-failing-version-probe")[:3] == (3, "", "")
    assert recorded("a-failing-version-probe")[3] == []


def test_a_failing_version_probe_carries_its_own_code() -> None:
    """Not always 3: whatever the probe returned. Three more codes, recorded."""
    for code in (1, 2, 9):
        assert recorded("a-failing-version-probe-exiting-%d" % code)[:3] == (code, "", "")


def test_a_failed_download_is_exit_2() -> None:
    code, _, stderr, calls = recorded("a-failed-download")
    assert code == 2
    assert "could not download actionlint from" in stderr
    assert any(line.startswith("FAKECALL curl ") for line in calls), calls


def test_a_checksum_mismatch_refuses_to_extract() -> None:
    """The strongest fixture case: verification happens BEFORE extraction."""
    code, _, stderr, _ = recorded("a-checksum-mismatch")
    assert code == 2
    assert "checksum MISMATCH -- refusing to extract" in stderr
    assert FIXTURE_SHA in stderr, "the expected hash was not printed"
    assert hashlib.sha256(b"not a tarball").hexdigest() in stderr


def test_a_verified_download_is_extracted_and_run(tmp_path: pathlib.Path) -> None:
    """The whole acquisition path end to end, with a REAL tar and a REAL hash.

    The extracted binary is a filesystem fact rather than a byte on a stream, so the recording is compared as usual and the port is then driven once more to assert that something executable actually landed in the cache.
    """
    code, _, stderr, _ = recorded("a-verified-download")
    assert code == 0, stderr
    assert "fetching actionlint" in stderr
    fx = build(tmp_path, "a-verified-download")
    assert drive(fx, "a-verified-download")[0] == 0
    landed = fx / "cache" / ("actionlint-%s" % FIXTURE_VERSION) / "actionlint"
    assert os.access(str(landed), os.X_OK), "the port did not extract an executable"


# --------------------------------------------------------------------------- Colour, and the one inherited divergence ---------------------------------------------------------------------------


def test_no_colour_off_a_tty() -> None:
    assert differential.escape_bytes(recorded("a-clean-fixture")[2]) == 0


def test_colour_on_a_tty_matches() -> None:
    assert differential.escape_bytes(recorded("colour-on-a-tty")[2]) > 0, (
        "the tty control did not fire"
    )


def test_ci_true_on_a_tty_is_the_one_inherited_divergence(tmp_path: pathlib.Path) -> None:
    """A PINNED DECISION, not a surprise. See the module docstring.

    `common.sh` gated colour on the stream alone and ignored CI; `rediacc_ci.log` also honours `CI=true`, because GitHub's log viewer renders escapes as literal text. Asserted in BOTH directions so nobody "fixes" either side.
    """
    name = "ci-true-on-a-tty"
    want = recorded(name)
    got = run(tmp_path, name)
    assert differential.escape_bytes(want[2]) > 0, "common.sh stopped colouring under CI=true"
    assert differential.escape_bytes(got[2]) == 0, "the house logger started colouring under CI"
    assert got[2] != want[2]
    assert got[0] == want[0]
    assert got[3] == want[3]
    # The MESSAGES still agree; only the escapes differ.
    plain = re.compile(r"\033\[[0-9;]*m")
    assert plain.sub("", want[2]) == plain.sub("", got[2])


# --------------------------------------------------------------------------- The real tree, live rather than frozen ---------------------------------------------------------------------------


def workflow_hashes() -> dict[str, str]:
    """sha256 of every file a real run reads. A MISSING corpus is a failure.

    `if targets: ...` was the shape to avoid: an empty dict compared against an empty dict reports "nothing was mutated" having hashed nothing, which is the vacuity this whole file exists to refuse.
    """
    targets = port.collect_targets(ROOT)
    assert len(targets) >= 20, (
        "only %d workflow file(s) under the real root; the read-only guard would "
        "be hashing almost nothing" % len(targets)
    )
    return {p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in targets}


def test_the_real_repository_passes_with_the_real_actionlint() -> None:
    """The real workflows through the real pinned binary. NOT FROZEN, and the module docstring says why: the count in this banner is a fact about the repository today rather than about the port."""
    before = workflow_hashes()
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PYTHONPATH"] = str(ROOT / ".ci")
    proc = subprocess.run(
        ["python3", str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    assert "actionlint clean across" in proc.stderr
    assert ("over %d workflow file(s)" % len(before)) in proc.stderr, (
        "the gate did not report the %d files collect_targets sees" % len(before)
    )
    assert workflow_hashes() == before, "a real run mutated a workflow file"


def test_the_real_tree_argv_names_every_collected_file_in_order(tmp_path: pathlib.Path) -> None:
    """The real paths, in `collect_targets`'s sequence, with the same single flag.

    THE ORDER IS THE ASSERTION. Three separate globs are concatenated without re-sorting; a port that merged them into one `sorted()` would hand actionlint a `.yaml` file before a later `.yml` one and still print an identical clean banner. Only the argv shows it.
    """
    bindir = tmp_path / "bin"
    write(bindir / "actionlint", FAKE_ACTIONLINT, mode=0o755)
    data = tmp_path / "data"
    write(data / "version", "%s\n" % port.actionlint_version(ROOT))
    write(data / "rc", "0\n")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")

    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["PATH"] = "%s%s%s" % (bindir, os.pathsep, env["PATH"])
    env["FAKE_DATA"] = str(data)
    env["FAKE_LOG"] = str(log)
    env["PYTHONPATH"] = str(ROOT / ".ci")
    subprocess.run(
        ["python3", str(PORT)],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines, "the fake actionlint was never called; the control did not fire"
    argv = lines[0].split()
    assert argv[:3] == ["FAKECALL", "actionlint", "-no-color"], lines[0]
    assert argv[3:] == port.collect_targets(ROOT), "the argv is not collect_targets in order"
    assert len(argv[3:]) > 20, "argv names too few files: %s" % lines[0]


# --------------------------------------------------------------------------- The pure helpers, exercised directly ---------------------------------------------------------------------------


def test_path_version_deletes_every_v_not_just_a_leading_one(tmp_path: pathlib.Path) -> None:
    """`tr -d 'v'`. Port note 1: `lstrip`/`removeprefix` would disagree."""
    fake = tmp_path / "actionlint"
    write(fake, '#!/bin/bash\necho "v1.7.12-dev"\necho ignored\n', mode=0o755)
    assert port.path_version(str(fake)) == ("1.7.12-de", 0)


def test_path_version_of_a_binary_that_cannot_run_is_126(tmp_path: pathlib.Path) -> None:
    """bash's own status for "cannot execute". See `path_version`'s docstring."""
    assert port.path_version(str(tmp_path / "nope")) == ("", 126)


def test_cache_dir_ignores_ci_temp_because_common_sh_overwrites_it(monkeypatch) -> None:
    """THE SECOND DEFECT, as a unit. The twin's own `${CI_TEMP:-...}` was dead.

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
        code, out, _err = differential.bash_streams(
            'source .ci/scripts/lib/common.sh; printf "%s" "$CI_TEMP"',
            env=env,
            cwd=str(ROOT),
        )
        assert code == 0
        assert out == expected, "CI_TEMP survived as %r; the defect is gone" % out


def test_the_arch_table_covers_exactly_the_twins_four_spellings() -> None:
    """A fifth spelling here would be a silent widening of the refusal."""
    assert set(port.ARCH_TABLE) == {"x86_64", "amd64", "aarch64", "arm64"}
    assert {v[0] for v in port.ARCH_TABLE.values()} == {"amd64", "arm64"}


def test_the_pins_and_checksums_come_from_the_files_the_twin_read() -> None:
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


def test_the_unsupported_arch_refusal_keeps_the_twins_wording() -> None:
    """The one path no run can drive; see the module docstring.

    The twin's two lines are recoverable from the blob sha in any golden header, so what is asserted here is that the port still carries them verbatim and that the table still refuses an architecture nobody pinned.
    """
    text = PORT.read_text(encoding="utf-8")
    assert "no pinned actionlint checksum for architecture '%s'" in text
    assert "add one to .ci/config/constants.sh rather than downloading unverified" in text
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


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_loss_of_the_template_pass_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Stop concatenating the out-of-tree templates.

    `.ci/*/workflow/*.yml` is the coverage this gate exists for: `check-workflows.sh`, `check-workflow-gates.sh` and `check-actions.ts` all scan `.github/` only, so a template could carry an unpinned action SHA or a broken expression and no other gate would say a word. It is the file that broke twice. A mutant that drops the pass still exits 0 and still prints a clean banner, one
    file short, and both the count on stderr and the recorded argv say so.

    THE MUTANT LIVES AT THE PORT'S OWN PATH INSIDE THE SCRATCH REPOSITORY, which is what makes the plant honest: both implementations resolve the repository root from their own location, so a copy anywhere else would resolve a different tree. The fixture is a throwaway copy already; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "    out.extend(templates)\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "    del templates\n")

    name = "a-clean-fixture"
    want = recorded(name)
    fx = build(tmp_path / "planted", name)
    (fx / PORT_REL).write_text(mutated, encoding="utf-8")
    got = drive(fx, name)

    assert "over 3 workflow file(s)" in want[2], "the recorded corpus moved"
    assert got[0] == 0, "the plant was meant to stay quiet, not to crash: %r" % (got,)
    assert "over 2 workflow file(s)" in got[2], "the plant did not narrow the corpus"
    assert "breakpoint.yml" in want[3][0]
    assert "breakpoint.yml" not in got[3][0], "the template was still linted"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
