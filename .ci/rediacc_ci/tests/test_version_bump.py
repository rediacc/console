"""Differential: `rediacc_ci.version.bump` against its twin
`.ci/scripts/version/bump.sh`.

REAL FILES, NOT STUBS, and that is the whole design of this differential. The deliverable of this script IS a mutated `package.json`, so every case builds a throwaway console tree per side with real manifests in it, runs the subject, and compares the resulting BYTES and the resulting FILE MODE. A stub could not show the root manifest being written when only the CLI one should be,
nor jq's formatting drifting, nor the 0600 that `mktemp` + `mv` leaves behind.

TWO MANIFESTS, AND THE ASYMMETRY IS THE SUBJECT. `package.json` at the root is
READ for the current version and never written; `packages/cli/package.json` is
the only entry in `VERSION_FILES_JSON` and the only file written. `test_the_root_manifest_is_read_and_never_written` pins both halves, because a port that wrote both would pass every other case here.

THE TWIN IS BROKEN FOR `--auto` AND `--patch` ON THIS REPOSITORY, and `test_the_live_defect_*` drives it rather than describing it: the placeholder version `0.0.0-dev` makes `$((patch + 1))` evaluate `0 - dev` under `set -u`. `test_minor_and_major_survive_the_placeholder_by_luck` drives the other half, which is the worse one: the same input yields a clean, plausible version for the
two flags that never touch the patch field. Reproduced rather than repaired, on this box's contract.

ONE CLASS OF DELIBERATE DIVERGENCE, ASSERTED IN BOTH DIRECTIONS. bash's own runtime diagnostics and `$0` name the RUNNING program, so `--help`, the no-arguments usage line and the unbound-variable death cannot be byte-identical across a `.sh` and a `.py`. Each is checked for identical structure, identical exit code, and a difference confined to the script path.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.version import bump as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "version" / "bump.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "version" / "bump.py"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
TOOLCHAIN_ENV = ROOT / ".devcontainer" / "toolchain.env"
BASH = shutil.which("bash") or "/bin/bash"

CLI_MANIFEST = "packages/cli/package.json"

# Everything either subject needs on PATH. `jq` is REAL on both sides: the port asks the same jq the twin asks, so its formatting cannot drift between them.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "mktemp", "mv", "rm", "cat")


def _manifest(name: str, version: str) -> str:
    """A realistic manifest: `.version` is NOT the first key, so a port that
    rebuilt the file instead of editing it would reorder the keys and be
    caught by the byte comparison."""
    return (
        json.dumps(
            {
                "name": name,
                "version": version,
                "private": True,
                "scripts": {"build": "tsc"},
                "engines": {"node": ">=22.13.0"},
            },
            indent=2,
        )
        + "\n"
    )


def _stub_path(tmp_path: pathlib.Path, side: str, *, with_jq: bool = True) -> str:
    stub = tmp_path / ("%s-bin" % side)
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        if name == "jq" and not with_jq:
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    if not with_jq:
        assert shutil.which("jq", path=str(stub)) is None, "jq leaked into the stub PATH"
    return str(stub)


def _fixture(
    tmp_path: pathlib.Path,
    side: str,
    *,
    root_version: str = "0.4.29",
    cli_version: str = "0.4.29",
    with_pins: bool = True,
    with_cli_manifest: bool = True,
    with_root_manifest: bool = True,
) -> pathlib.Path:
    root = tmp_path / ("tree-%s" % side)
    for rel in (
        ".ci/scripts/version",
        ".ci/scripts/lib",
        ".ci/config",
        ".ci/rediacc_ci/version",
        ".devcontainer",
        "packages/cli",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "version" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "version" / PORT.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / "constants.sh")
    if with_pins:
        shutil.copy2(TOOLCHAIN_ENV, root / ".devcontainer" / "toolchain.env")
    if with_root_manifest:
        (root / "package.json").write_text(_manifest("console", root_version), encoding="utf-8")
    if with_cli_manifest:
        (root / CLI_MANIFEST).write_text(_manifest("@rediacc/cli", cli_version), encoding="utf-8")
        os.chmod(root / CLI_MANIFEST, 0o644)
    return root


def _snapshot(root: pathlib.Path) -> dict:
    """Every observable thing the tree can say afterwards."""
    out: dict = {}
    for rel in ("package.json", CLI_MANIFEST, "out.txt"):
        path = root / rel
        if path.is_file():
            out[rel] = (
                path.read_text(encoding="utf-8"),
                stat.S_IMODE(path.stat().st_mode),
            )
        else:
            out[rel] = None
    return out


def _run(
    tmp_path: pathlib.Path,
    side: str,
    args: list[str],
    *,
    port_source: str | None = None,
    with_jq: bool = True,
    **fixture_kw,
):
    extra = {k: v for k, v in fixture_kw.items() if k.startswith("ENV_")}
    fixture_kw = {k: v for k, v in fixture_kw.items() if not k.startswith("ENV_")}
    root = _fixture(tmp_path, side, **fixture_kw)
    if port_source is not None:
        (root / ".ci" / "rediacc_ci" / "version" / PORT.name).write_text(
            port_source, encoding="utf-8"
        )
    env = {
        "PATH": _stub_path(tmp_path, side, with_jq=with_jq),
        "HOME": str(tmp_path / ("%s-home" % side)),
        "TMPDIR": str(tmp_path / ("%s-tmp" % side)),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    for key, value in extra.items():
        env[key[len("ENV_") :]] = value

    if side.startswith("old"):
        subject = root / ".ci" / "scripts" / "version" / TWIN.name
        runner = [BASH]
    else:
        subject = root / ".ci" / "rediacc_ci" / "version" / PORT.name
        runner = [sys.executable]
    resolved = [a.replace("@ROOT@", str(root)) for a in args]
    proc = subprocess.run(
        [*runner, str(subject), *resolved],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    return proc, _snapshot(root), root


def run_both(tmp_path: pathlib.Path, args: list[str], **kw):
    return _run(tmp_path, "old", args, **kw), _run(tmp_path, "new", args, **kw)


def assert_agree(old, new, label: str) -> None:
    o_proc, o_tree, o_root = old
    n_proc, n_tree, n_root = new
    assert n_proc.returncode == o_proc.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, o_proc.returncode, n_proc.returncode, o_proc.stderr, n_proc.stderr)
    )
    assert n_proc.stdout.replace(str(n_root), "<tree>") == o_proc.stdout.replace(
        str(o_root), "<tree>"
    ), "%s: stdout diverged:\nold: %r\nnew: %r" % (label, o_proc.stdout, n_proc.stdout)
    assert n_proc.stderr.replace(str(n_root), "<tree>") == o_proc.stderr.replace(
        str(o_root), "<tree>"
    ), "%s: stderr diverged:\nold: %r\nnew: %r" % (label, o_proc.stderr, n_proc.stderr)
    assert n_tree == o_tree, "%s: the file tree diverged:\nold: %r\nnew: %r" % (
        label,
        o_tree,
        n_tree,
    )


# --------------------------------------------------------------------------- Refusals, before any file is touched ---------------------------------------------------------------------------


def test_no_arguments_refuses_with_the_error_on_stderr_and_usage_on_stdout(
    tmp_path: pathlib.Path,
) -> None:
    """TWO STREAMS, TWO PURPOSES (:97-99). `log_error` goes to stderr and the
    bare `echo "Usage: ..."` goes to STDOUT, which is the same stream the
    successful run puts the new version on."""
    old, new = run_both(tmp_path, [])
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Must specify --auto/--patch/--minor/--major or --version\n"
    assert old[0].stdout.startswith("Usage: ")
    assert old[0].stdout.endswith(
        " [--auto | --patch | --minor | --major | --version X.Y.Z] [--dry-run]\n"
    )
    assert old[1][CLI_MANIFEST] == new[1][CLI_MANIFEST]
    # `$0` is the one thing that cannot agree; everything else does.
    assert new[0].returncode == old[0].returncode
    assert new[0].stderr == old[0].stderr
    assert new[0].stdout != old[0].stdout
    assert "bump.sh" in old[0].stdout
    assert "bump.py" in new[0].stdout


def test_two_bump_flags_are_refused(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--patch", "--minor"])
    assert old[0].returncode == 1
    assert old[0].stderr == ("✗ Only one bump flag may be used (--auto/--patch/--minor/--major)\n")
    assert_agree(old, new, "two-bump-flags")


def test_auto_and_patch_are_the_same_flag_and_still_collide(
    tmp_path: pathlib.Path,
) -> None:
    """`--auto` and `--patch` both call `set_bump_type patch`, so passing both
    is refused even though they mean the same thing. Reproduced, not tidied."""
    old, new = run_both(tmp_path, ["--auto", "--patch"])
    assert old[0].returncode == 1
    assert "Only one bump flag" in old[0].stderr
    assert_agree(old, new, "auto-and-patch")


def test_a_bump_flag_with_an_explicit_version_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--patch", "--version", "1.2.3"])
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Cannot combine bump flags with --version\n"
    assert old[0].stdout == ""
    assert_agree(old, new, "flag-plus-version")


def test_an_unknown_option_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--nope"])
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Unknown option: --nope\n"
    assert_agree(old, new, "unknown-option")


def test_a_missing_toolchain_env_refuses_before_any_argument_is_read(
    tmp_path: pathlib.Path,
) -> None:
    """`source constants.sh` (:26) precedes the argument loop (:44)."""
    old, new = run_both(tmp_path, ["--help"], with_pins=False)
    assert old[0].returncode == 1
    assert "constants.sh: gate toolchain pins missing:" in old[0].stderr
    assert old[0].stdout == "", "the help text printed despite the refusal"
    assert_agree(old, new, "no-toolchain-env")


def test_missing_jq_is_refused_after_the_argument_validation(
    tmp_path: pathlib.Path,
) -> None:
    """`require_cmd jq` is the first line of `main` (:169), which runs AFTER the
    top-level validation, so a bad flag is reported even on a machine with no
    jq at all."""
    old, new = run_both(tmp_path, ["--version", "1.2.3"], with_jq=False)
    assert old[0].returncode == 1
    assert old[0].stderr == "✗ Required command 'jq' is not available\n"
    assert_agree(old, new, "missing-jq")


# --------------------------------------------------------------------------- The explicit-version path, which is the only one that works today ---------------------------------------------------------------------------


def test_an_explicit_version_is_written_and_echoed(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "1.2.3"])
    assert old[0].returncode == 0, old[0].stderr
    assert old[0].stdout == "1.2.3\n", "stdout is the capture interface"
    assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "1.2.3"
    assert "✓ Current version: 0.4.29" in old[0].stderr
    assert "→ Updating to version: 1.2.3" in old[0].stderr
    assert "✓ Updated 1 files" in old[0].stderr
    assert_agree(old, new, "explicit-version")


def test_the_root_manifest_is_read_and_never_written(tmp_path: pathlib.Path) -> None:
    """THE ASYMMETRY A PORT WOULD SILENTLY GET WRONG. `VERSION_FILES_JSON` holds
    only the CLI manifest; the root one supplies the CURRENT version and must
    come out untouched, byte for byte and mode for mode."""
    before = _manifest("console", "0.4.29")
    old, new = run_both(tmp_path, ["--version", "9.9.9"])
    assert old[1]["package.json"][0] == before, "the root manifest was rewritten"
    assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "9.9.9"
    assert_agree(old, new, "root-not-written")


def test_the_manifests_key_order_and_formatting_survive(tmp_path: pathlib.Path) -> None:
    """`jq '.version = $v'` EDITS, it does not rebuild: `name` still precedes
    `version`, the nested objects keep their shape, and the file keeps its trailing newline. A port that used Python's json.dump would pass every
    version assertion here and fail this one."""
    old, new = run_both(tmp_path, ["--version", "1.2.3"])
    text = old[1][CLI_MANIFEST][0]
    assert text.startswith('{\n  "name": "@rediacc/cli",\n  "version": "1.2.3",\n')
    assert text.endswith("}\n")
    assert '"node": ">=22.13.0"' in text
    assert_agree(old, new, "formatting")


def test_the_manifest_comes_out_0600_because_mktemp_plus_mv(
    tmp_path: pathlib.Path,
) -> None:
    """A SIDE EFFECT NOBODY WOULD SEE IN A DIFF. `mktemp` creates 0600 and `mv`
    carries that mode onto the manifest, so a 0644 package.json becomes 0600.
    Reproduced and pinned rather than quietly improved."""
    old, new = run_both(tmp_path, ["--version", "1.2.3"])
    assert old[1][CLI_MANIFEST][1] == 0o600, oct(old[1][CLI_MANIFEST][1])
    assert_agree(old, new, "mode-0600")


def test_a_non_semver_explicit_version_is_refused_before_any_write(
    tmp_path: pathlib.Path,
) -> None:
    old, new = run_both(tmp_path, ["--version", "1.2"])
    assert old[0].returncode == 1
    assert old[0].stderr.endswith("✗ Invalid version format: 1.2 (expected X.Y.Z)\n")
    assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "0.4.29"
    assert_agree(old, new, "bad-semver")


def test_a_prerelease_suffix_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "1.2.3-rc.1"])
    assert old[0].returncode == 1
    assert "Invalid version format: 1.2.3-rc.1" in old[0].stderr
    assert_agree(old, new, "prerelease")


def test_a_leading_v_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "v1.2.3"])
    assert old[0].returncode == 1
    assert "Invalid version format: v1.2.3" in old[0].stderr
    assert_agree(old, new, "leading-v")


def test_dry_run_writes_nothing_and_still_echoes_the_version(
    tmp_path: pathlib.Path,
) -> None:
    old, new = run_both(tmp_path, ["--version", "1.2.3", "--dry-run"])
    assert old[0].returncode == 0
    assert old[0].stdout == "1.2.3\n"
    assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "0.4.29"
    assert old[1][CLI_MANIFEST][1] == 0o644, "dry-run changed the file mode"
    assert "[DRY-RUN] Would update 1 files" in old[0].stderr
    assert_agree(old, new, "dry-run")


def test_dry_run_can_come_from_the_environment(tmp_path: pathlib.Path) -> None:
    """`DRY_RUN="${DRY_RUN:-false}"` (:28), and only the literal `true` counts."""
    old, new = run_both(tmp_path, ["--version", "1.2.3"], ENV_DRY_RUN="true")
    assert "[DRY-RUN] Would update 1 files" in old[0].stderr
    assert_agree(old, new, "dry-run-env")

    old2, new2 = run_both(tmp_path, ["--version", "1.2.3"], ENV_DRY_RUN="1")
    assert "✓ Updated 1 files" in old2[0].stderr, "DRY_RUN=1 was treated as true"
    assert_agree(old2, new2, "dry-run-env-1")


def test_output_writes_the_version_to_a_file(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--version", "1.2.3", "--output", "@ROOT@/out.txt"])
    assert old[0].returncode == 0
    assert old[1]["out.txt"][0] == "1.2.3\n"
    assert "Wrote version to " in old[0].stderr
    assert_agree(old, new, "output-file")


# --------------------------------------------------------------------------- The increment paths ---------------------------------------------------------------------------


def test_patch_minor_and_major_increments(tmp_path: pathlib.Path) -> None:
    for flag, expected in (("--patch", "0.4.30"), ("--minor", "0.5.0"), ("--major", "1.0.0")):
        sub = tmp_path / flag.strip("-")
        sub.mkdir()
        old, new = run_both(sub, [flag])
        assert old[0].returncode == 0, old[0].stderr
        assert old[0].stdout == expected + "\n", flag
        assert json.loads(old[1][CLI_MANIFEST][0])["version"] == expected
        assert_agree(old, new, "increment%s" % flag)


def test_auto_is_patch(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, ["--auto"])
    assert old[0].stdout == "0.4.30\n"
    assert_agree(old, new, "auto")


def test_the_live_defect_every_bump_flag_dies_on_the_0_0_0_dev_placeholder(
    tmp_path: pathlib.Path,
) -> None:
    """THE DEFECT THIS PORT INHERITED, DRIVEN RATHER THAN DESCRIBED.

    Every package.json in this repository carries `0.0.0-dev`, because the version source of truth is git tags. `increment_patch` splits that into
    `0`, `0`, `0-dev` and asks bash for `$((0-dev + 1))`; `dev` is not a
    variable and `set -u` kills the run. So `--auto` and `--patch` are broken on a clean checkout of this repo today.

    The exit code, the preceding "Current version" line and the message shape
    agree; the script path and line number are each side's own, which is the
    divergence and is asserted in both directions.
    """
    shape = re.compile(r"^\S+: line \d+: dev: unbound variable$")
    for flag in ("--auto", "--patch"):
        sub = tmp_path / ("dev" + flag.strip("-"))
        sub.mkdir()
        old, new = run_both(sub, [flag], root_version="0.0.0-dev")
        assert old[0].returncode == 1, flag
        assert new[0].returncode == 1, flag
        assert old[0].stdout == new[0].stdout == "", flag
        o_lines = old[0].stderr.splitlines()
        n_lines = new[0].stderr.splitlines()
        assert o_lines[0] == n_lines[0] == "✓ Current version: 0.0.0-dev", flag
        assert shape.match(o_lines[1]), o_lines
        assert shape.match(n_lines[1]), n_lines
        assert o_lines[1] != n_lines[1], "the two claim the same coordinates"
        assert old[1][CLI_MANIFEST] == new[1][CLI_MANIFEST], flag
        assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "0.4.29", flag


def test_minor_and_major_survive_the_placeholder_by_luck(tmp_path: pathlib.Path) -> None:
    """THE OTHER HALF OF THE DEFECT, AND THE PART THAT MAKES IT DANGEROUS.

    `--minor` and `--major` on `0.0.0-dev` do NOT die: they only evaluate the major and minor fields, which are plain `0`, and the `-dev` suffix rides along in a field neither of them touches. So the same broken input produces a hard failure for two flags and a clean, plausible-looking version for two others, with nothing in the output hinting that the current version was never a
    semver at all.
    """
    for flag, expected in (("--minor", "0.1.0"), ("--major", "1.0.0")):
        sub = tmp_path / ("ok" + flag.strip("-"))
        sub.mkdir()
        old, new = run_both(sub, [flag], root_version="0.0.0-dev")
        assert old[0].returncode == 0, old[0].stderr
        assert old[0].stdout == expected + "\n", flag
        assert "Current version: 0.0.0-dev" in old[0].stderr
        assert_agree(old, new, "placeholder%s" % flag)


def test_a_four_part_current_version_keeps_the_remainder_in_the_patch_field(
    tmp_path: pathlib.Path,
) -> None:
    """`IFS='.' read -r major minor patch` gives `patch` the WHOLE remainder, so
    `1.2.3.4` asks for `$((3.4 + 1))` and dies. Named here because the obvious
    Python port (`split(".")[2]`) would quietly succeed with `1.2.4`."""
    old, new = run_both(tmp_path, ["--patch"], root_version="1.2.3.4")
    assert old[0].returncode == 1
    assert new[0].returncode == 1
    assert "arithmetic" in old[0].stderr or "syntax error" in old[0].stderr, old[0].stderr
    assert old[1][CLI_MANIFEST] == new[1][CLI_MANIFEST]
    assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "0.4.29"


def test_a_two_part_current_version_produces_an_invalid_version(
    tmp_path: pathlib.Path,
) -> None:
    """`1.2` splits to `1`, `2`, `` and `$(( + 1))` is 1, so the increment
    SUCCEEDS and yields `1.2.1`. That is a valid semver, and it is written.
    Recorded because it looks like a bug and is not one."""
    old, new = run_both(tmp_path, ["--patch"], root_version="1.2")
    assert old[0].returncode == 0, old[0].stderr
    assert old[0].stdout == "1.2.1\n"
    assert_agree(old, new, "two-part-version")


# --------------------------------------------------------------------------- Missing files ---------------------------------------------------------------------------


def test_a_missing_target_manifest_warns_then_fails_at_the_end(
    tmp_path: pathlib.Path,
) -> None:
    """A MISSING FILE IS NOT AN IMMEDIATE STOP. The twin warns, counts it in
    `failed`, finishes the list, prints "Updated 0 files", and only then exits
    1. So the version is never echoed on stdout even though it was computed."""
    old, new = run_both(tmp_path, ["--version", "1.2.3"], with_cli_manifest=False)
    assert old[0].returncode == 1
    assert "⚠ File not found: " in old[0].stderr
    assert "✓ Updated 0 files" in old[0].stderr
    assert "✗ Failed to update 1 files" in old[0].stderr
    assert old[0].stdout == "", "the version was echoed despite the failure"
    assert_agree(old, new, "missing-target")


def test_a_missing_root_manifest_dies_with_jqs_own_status(
    tmp_path: pathlib.Path,
) -> None:
    """`current_version=$(jq -r '.version' ...)` is a bare assignment, so `set
    -e` exits with jq's status and jq's stderr, before anything is written."""
    old, new = run_both(tmp_path, ["--version", "1.2.3"], with_root_manifest=False)
    assert old[0].returncode == 2, old[0].stderr
    assert "Current version" not in old[0].stderr
    assert json.loads(old[1][CLI_MANIFEST][0])["version"] == "0.4.29"
    assert_agree(old, new, "missing-root-manifest")


# --------------------------------------------------------------------------- Pure helpers, driven against real bash ---------------------------------------------------------------------------


def _bash_dot_fields(text: str) -> list[str]:
    script = 'IFS="." read -r a b c\nprintf "%s\\0%s\\0%s" "$a" "$b" "$c"\n'
    proc = subprocess.run(
        [BASH, "-c", script], input=text + "\n", stdout=subprocess.PIPE, text=True, check=True
    )
    return proc.stdout.split("\0")


def test_read_dot_fields_matches_bash() -> None:
    """FOUR PROPERTIES, EACH MEASURED. `.` is not IFS whitespace, so nothing
    collapses, nothing is stripped, empty fields survive, and the last variable
    keeps the remainder with its delimiters."""
    for case in ("1.2.3", "1.2.3.4", ".1.2", "1.2.", "1.2", "", "0.0.0-dev", "...."):
        assert port.read_dot_fields(case, 3) == _bash_dot_fields(case), case


def _bash_arith(value: str) -> tuple[int, str]:
    proc = subprocess.run(
        [BASH, "-c", 'set -u; v="$1"; echo $((v + 1))', "x", value],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def test_bash_arith_matches_bash_on_every_value_a_manifest_can_hold() -> None:
    """BOTH DIRECTIONS. The values that WORK must produce the same number, and
    the values that DIE must die -- a helper with only the happy half would let `0.0.0-dev` through as `0.0.1` and nobody would notice until a tag was cut.
    """
    for value, expected in (("29", 30), ("0", 1), ("", 1), ("010", 9), ("0x10", 17), ("7", 8)):
        rc, text = _bash_arith(value)
        assert rc == 0, "%r unexpectedly died in bash: %s" % (value, text)
        assert int(text) == expected, value
        assert port.bash_arith("%s + 1" % value, value, 1) == expected, value

    for value, needle in (("0-dev", "dev: unbound variable"), ("08", "value too great")):
        rc, text = _bash_arith(value)
        assert rc != 0, "%r no longer dies in bash: %s" % (value, text)
        assert needle in text, "%r died differently in bash: %s" % (value, text)
        with pytest.raises(port.BashFatalError, match=re.escape(needle)):
            port.bash_arith("%s + 1" % value, value, 1)


def test_pure_helpers() -> None:
    assert port.is_semver("1.2.3")
    assert not port.is_semver("v1.2.3")
    assert not port.is_semver("1.2")
    assert not port.is_semver("1.2.3-rc.1")
    assert port.increment_patch("0.4.29") == "0.4.30"
    assert port.increment_minor("0.4.29") == "0.5.0"
    assert port.increment_major("0.4.29") == "1.0.0"
    assert port.constants_root(ROOT, {}) == str(ROOT)
    assert port.constants_root(ROOT, {"CONSOLE_ROOT_DIR": "rel/path"}) == "rel/path"
    opts = port.parse_argv(["--minor", "--output", "f"], dry_run_default=False)
    assert (opts.bump_type, opts.output_file, opts.dry_run) == ("minor", "f", False)


def test_constants_have_not_drifted() -> None:
    """The two things the twin gets from constants.sh, re-read from the file.

    A LIVE PARSE WOULD FOLLOW A CHANGE SILENTLY, and the subject of this script is exactly WHICH files get written, so a red test is the answer that gets read.
    """
    text = CONSTANTS.read_text(encoding="utf-8")
    match = re.search(r"readonly VERSION_FILES_JSON=\(\n(.*?)\n\)", text, re.DOTALL)
    assert match is not None, "VERSION_FILES_JSON is no longer an array literal"
    declared = tuple(re.findall(r'"([^"]+)"', match.group(1)))
    assert declared == port.VERSION_FILES_JSON, (declared, port.VERSION_FILES_JSON)
    assert 'CONSOLE_ROOT_DIR="${CONSOLE_ROOT_DIR:-' in text


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the ONE thing this script exists to do: the
    mutant writes the ROOT manifest instead of the CLI one. Every stream is byte-identical, the exit code is 0 on both sides, and the only evidence is the file tree. Driven red, then the source is confirmed byte-identical and
    green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        'VERSION_FILES_JSON = ("packages/cli/package.json",)',
        'VERSION_FILES_JSON = ("package.json",)',
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    old = _run(tmp_path, "old", ["--version", "1.2.3"])
    bad = _run(tmp_path, "bad", ["--version", "1.2.3"], port_source=mutated)
    assert bad[0].returncode == old[0].returncode == 0
    assert bad[0].stdout == old[0].stdout, (
        "the plant is invisible on stdout, which is why the tree is compared"
    )
    assert bad[1] != old[1], "the mutant produced the same tree"
    assert json.loads(bad[1]["package.json"][0])["version"] == "1.2.3"
    assert json.loads(bad[1][CLI_MANIFEST][0])["version"] == "0.4.29"

    good = _run(tmp_path, "new", ["--version", "1.2.3"])
    assert_agree(old, good, "plant-restored")
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
