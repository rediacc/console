"""`rediacc_ci.version.bump`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/version/bump.sh` and the port over a throwaway console tree per side and compared exit code, stdout, stderr and the resulting FILES, contents and modes together. The ledger `.ci/shadow/w7p6-version-bump.observations.jsonl` holds 5 rows of that comparison.

Every case now compares against `goldens/version-bump/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

IT WAS SAFE TO RETIRE BECAUSE NOTHING CALLS IT ANY MORE, and that was established before anything was deleted rather than assumed. All three live call sites already run the port: `.github/workflows/ci-build-docker.yml:65` and `:162`, and `.github/workflows/ci-quality.yml:865`.

Each runs `PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --version <next>`, and a repository-wide grep finds no other invocation of the twin, in any workflow, script or gate.

REAL FILES, NOT STUBS, and that is the whole design. The deliverable of this subject IS a mutated `package.json`, so every case builds a throwaway console tree with real manifests in it and the recorded shape carries a `--- tree ---` section holding each file's bytes AND its mode. A stub could not show the root manifest being left alone when only the CLI one should be written, nor
jq's formatting drifting, nor the 0600 that `mktemp` plus `mv` leaves behind on a file that started 0644.

TWO MANIFESTS, AND THE ASYMMETRY IS THE SUBJECT. `package.json` at the root is READ for the current version and never written; `packages/cli/package.json` is the only entry in `VERSION_FILES_JSON` and the only file written. A port that wrote both would satisfy every version assertion here and fail on the recorded tree alone.

THE TWIN WAS BROKEN FOR `--auto` AND `--patch` ON THIS REPOSITORY, and the recordings drive it rather than describing it: every `package.json` here carries the placeholder `0.0.0-dev`, because the version source of truth is git tags, so `increment_patch` splits that into `0`, `0`, `0-dev` and asks bash for `$((0-dev + 1))`. `dev` is not a variable, `set -u` kills the run, and the
flags that a clean checkout would reach for are the two that fail.

THE OTHER HALF IS THE DANGEROUS ONE and has its own recordings: `--minor` and `--major` on the same placeholder do NOT die, because they only evaluate fields that are plain `0` and the `-dev` suffix rides along in a field neither touches. The same broken input yields a hard failure for two flags and a clean, plausible version for the other two, with nothing in the output hinting
that the current version was never a semver.

FOUR CASES ARE COMPARED BY SHAPE, and every one of them is bash naming itself. `$0` in the usage line, and the `line N:` coordinates in an arithmetic death, cannot be byte-identical across a `.sh` and a `.py`. Each is compared on exit code, on the stream the message landed on, on the tree left behind, and on the message's SHAPE, with the difference asserted to be confined to the
path.

WHAT IS MASKED, and it is two paths. The throwaway tree is rebuilt under a different temporary name every run, so it becomes `<tree>`; the checkout root becomes `<repo>`, because the fixture reaches into it for `PYTHONPATH` and a diagnostic could quote it. Nothing else is touched.

THE FIXTURE COPIES FOUR LIVE TRACKED FILES, and that is deliberate rather than a frozen copy of anything: `constants.sh`, `common.sh` and `.devcontainer/toolchain.env` are what the subject sources, and the port imports `rediacc_ci`. The OUTPUT is what is frozen, and it would change if those changed, which is a regression a golden should catch rather than hide.
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
from rediacc_ci.tests import frozen
from rediacc_ci.version import bump as vb

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "version" / "bump.py"
TWIN_REL = ".ci/scripts/version/bump.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
TOOLCHAIN_ENV = ROOT / ".devcontainer" / "toolchain.env"
BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

SLUG = "version-bump"
TREE_MARKER = "--- tree ---\n"

CLI_MANIFEST = "packages/cli/package.json"

# Everything the subject needs on PATH. `jq` is REAL: the port asks the same jq the twin asked, so its formatting cannot drift between them.
PATH_MINIMUM = ("dirname", "uname", "tr", "jq", "mktemp", "mv", "rm", "cat")

# The shape of an arithmetic death, with the coordinates left out. See the module docstring's note on the four shape-compared cases.
UNBOUND_RE = re.compile(r"^\S+: line \d+: dev: unbound variable$")


def manifest(name: str, version: str) -> str:
    """A realistic manifest: `.version` is NOT the first key, so a port that rebuilt the file instead of editing it would reorder the keys and be caught by the byte comparison."""
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


# name -> the argv, the two manifest versions, the environment, and the three fixture shapes that withhold something
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "no-arguments": {"args": []},
    "two-bump-flags": {"args": ["--patch", "--minor"]},
    "auto-and-patch-collide": {"args": ["--auto", "--patch"]},
    "a-bump-flag-with-an-explicit-version": {"args": ["--patch", "--version", "1.2.3"]},
    "an-unknown-option": {"args": ["--nope"]},
    "a-missing-toolchain-env": {"args": ["--help"], "with_pins": False},
    "no-jq-on-the-path": {"args": ["--version", "1.2.3"], "with_jq": False},
    "an-explicit-version": {"args": ["--version", "1.2.3"]},
    "a-higher-explicit-version": {"args": ["--version", "9.9.9"]},
    "a-non-semver-version": {"args": ["--version", "1.2"]},
    "a-prerelease-suffix": {"args": ["--version", "1.2.3-rc.1"]},
    "a-leading-v": {"args": ["--version", "v1.2.3"]},
    "a-dry-run": {"args": ["--version", "1.2.3", "--dry-run"]},
    "a-dry-run-from-the-environment": {"args": ["--version", "1.2.3"], "env": {"DRY_RUN": "true"}},
    "a-dry-run-from-a-one": {"args": ["--version", "1.2.3"], "env": {"DRY_RUN": "1"}},
    "an-output-file": {"args": ["--version", "1.2.3", "--output", "@ROOT@/out.txt"]},
    "a-patch-increment": {"args": ["--patch"]},
    "a-minor-increment": {"args": ["--minor"]},
    "a-major-increment": {"args": ["--major"]},
    "auto-is-patch": {"args": ["--auto"]},
    "the-placeholder-with-auto": {"args": ["--auto"], "root_version": "0.0.0-dev"},
    "the-placeholder-with-patch": {"args": ["--patch"], "root_version": "0.0.0-dev"},
    "the-placeholder-with-minor": {"args": ["--minor"], "root_version": "0.0.0-dev"},
    "the-placeholder-with-major": {"args": ["--major"], "root_version": "0.0.0-dev"},
    "a-four-part-version": {"args": ["--patch"], "root_version": "1.2.3.4"},
    "a-two-part-version": {"args": ["--patch"], "root_version": "1.2"},
    "a-missing-target-manifest": {"args": ["--version", "1.2.3"], "with_cli_manifest": False},
    "a-missing-root-manifest": {"args": ["--version", "1.2.3"], "with_root_manifest": False},
}

CASES = tuple(CASE_KW)

# The four cases in which bash names itself, by `$0` or by `line N:`. Compared by shape, in their own tests.
DIVERGENT = (
    "no-arguments",
    "the-placeholder-with-auto",
    "the-placeholder-with-patch",
    "a-four-part-version",
)


def stub_path(where: pathlib.Path, *, with_jq: bool = True) -> str:
    stub = where / "bin"
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


def build(where: pathlib.Path, name: str, subject: pathlib.Path) -> pathlib.Path:
    """A throwaway console tree holding the subject, the two manifests and what the subject sources."""
    kw = CASE_KW[name]
    root = where / "tree"
    for rel in (
        ".ci/scripts/version",
        ".ci/scripts/lib",
        ".ci/config",
        ".ci/rediacc_ci/version",
        ".devcontainer",
        "packages/cli",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    if subject.suffix == ".sh":
        shutil.copy2(ROOT / TWIN_REL, root / ".ci" / "scripts" / "version" / "bump.sh")
    else:
        shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "version" / "bump.py")
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / "constants.sh")
    if kw.get("with_pins", True):
        shutil.copy2(TOOLCHAIN_ENV, root / ".devcontainer" / "toolchain.env")
    if kw.get("with_root_manifest", True):
        (root / "package.json").write_text(
            manifest("console", kw.get("root_version", "0.4.29")), encoding="utf-8"
        )
    if kw.get("with_cli_manifest", True):
        (root / CLI_MANIFEST).write_text(
            manifest("@rediacc/cli", kw.get("cli_version", "0.4.29")), encoding="utf-8"
        )
        os.chmod(root / CLI_MANIFEST, 0o644)
    return root


def snapshot(root: pathlib.Path) -> dict[str, typing.Any]:
    """Every observable thing the tree can say afterwards: the bytes and the MODE of each file the subject could have touched."""
    out: dict[str, typing.Any] = {}
    for rel in ("package.json", CLI_MANIFEST, "out.txt"):
        path = root / rel
        out[rel] = (
            [path.read_text(encoding="utf-8"), "0o%o" % stat.S_IMODE(path.stat().st_mode)]
            if path.is_file()
            else None
        )
    return out


def run(subject: pathlib.Path, where: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, inside its own throwaway tree."""
    kw = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    root = build(where, name, subject)
    env = {
        "PATH": stub_path(where, with_jq=kw.get("with_jq", True)),
        "HOME": str(where / "home"),
        "TMPDIR": str(where / "tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    env.update(kw.get("env") or {})
    if subject.suffix == ".sh":
        runner, target = BASH, root / ".ci" / "scripts" / "version" / "bump.sh"
    else:
        runner, target = PYTHON, root / ".ci" / "rediacc_ci" / "version" / "bump.py"
    args = [a.replace("@ROOT@", str(root)) for a in kw["args"]]
    proc = subprocess.run(
        [runner, str(target), *args],
        cwd=str(where),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )

    def mask(text: str) -> str:
        return text.replace(str(root), "<tree>").replace(str(ROOT), "<repo>")

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(json.dumps(snapshot(root), indent=2, sort_keys=True)),
    )


def render(code: int, stdout: str, stderr: str, tree: str) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), TREE_MARKER, tree)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, tree = rest.split(TREE_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, tree.removesuffix("\n")


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(PORT, tmp_path / name, name)


def tree_of(state: str) -> dict[str, typing.Any]:
    return json.loads(state)


def cli_version(state: str) -> str:
    entry = tree_of(state)[CLI_MANIFEST]
    assert entry is not None, "the CLI manifest is absent from this recording"
    return json.loads(entry[0])["version"]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the tree left behind")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Refusals, before any file is touched ---------------------------------------------------------------------------


def test_two_bump_flags_are_refused() -> None:
    code, _, stderr, state = recorded("two-bump-flags")
    assert code == 1
    assert stderr == "✗ Only one bump flag may be used (--auto/--patch/--minor/--major)\n"
    assert cli_version(state) == "0.4.29"


def test_auto_and_patch_are_the_same_flag_and_still_collide() -> None:
    code, _, stderr, _ = recorded("auto-and-patch-collide")
    assert code == 1
    assert "Only one bump flag" in stderr


def test_a_bump_flag_with_an_explicit_version_is_refused() -> None:
    code, _, stderr, _ = recorded("a-bump-flag-with-an-explicit-version")
    assert code == 1
    assert stderr != ""


def test_an_unknown_option_is_refused() -> None:
    code, _, stderr, _ = recorded("an-unknown-option")
    assert code == 1
    assert stderr != ""


def test_a_missing_toolchain_env_refuses_before_any_argument_is_read() -> None:
    """`source constants.sh` (:26) precedes the argument loop (:44), so even `--help` does not print."""
    code, stdout, stderr, _ = recorded("a-missing-toolchain-env")
    assert code == 1
    assert "constants.sh: gate toolchain pins missing:" in stderr
    assert stdout == "", "the help text printed despite the refusal"


def test_missing_jq_is_refused_after_the_argument_validation() -> None:
    """`require_cmd jq` is the first line of `main` (:169), which runs AFTER the top-level validation, so a bad flag is reported even on a machine with no jq at all."""
    code, _, stderr, _ = recorded("no-jq-on-the-path")
    assert code == 1
    assert stderr == "✗ Required command 'jq' is not available\n"


# --------------------------------------------------------------------------- The explicit-version path, which is the only one that works today ---------------------------------------------------------------------------


def test_an_explicit_version_is_written_and_echoed() -> None:
    code, stdout, stderr, state = recorded("an-explicit-version")
    assert code == 0, stderr
    assert stdout == "1.2.3\n", "stdout is the capture interface"
    assert cli_version(state) == "1.2.3"
    assert "✓ Current version: 0.4.29" in stderr
    assert "→ Updating to version: 1.2.3" in stderr
    assert "✓ Updated 1 files" in stderr


def test_the_root_manifest_is_read_and_never_written() -> None:
    """THE ASYMMETRY A PORT WOULD SILENTLY GET WRONG. `VERSION_FILES_JSON` holds only the CLI manifest; the root one supplies the CURRENT version and must come out untouched, byte for byte and mode for mode."""
    state = recorded("a-higher-explicit-version")[3]
    assert tree_of(state)["package.json"][0] == manifest("console", "0.4.29"), (
        "the root manifest was rewritten"
    )
    assert cli_version(state) == "9.9.9"


def test_the_manifests_key_order_and_formatting_survive() -> None:
    """`jq '.version = $v'` EDITS, it does not rebuild: `name` still precedes `version`, the nested objects keep their shape, and the file keeps its trailing newline. A port that used Python's `json.dump` would pass every version assertion here and fail this one."""
    text = tree_of(recorded("an-explicit-version")[3])[CLI_MANIFEST][0]
    assert text.startswith('{\n  "name": "@rediacc/cli",\n  "version": "1.2.3",\n')
    assert text.endswith("}\n")
    assert '"node": ">=22.13.0"' in text


def test_the_manifest_comes_out_0600_because_mktemp_plus_mv() -> None:
    """A SIDE EFFECT NOBODY WOULD SEE IN A DIFF. `mktemp` creates 0600 and `mv` carries that mode onto the manifest, so a 0644 package.json becomes 0600. Recorded and pinned rather than quietly improved."""
    assert tree_of(recorded("an-explicit-version")[3])[CLI_MANIFEST][1] == "0o600"
    assert tree_of(recorded("an-explicit-version")[3])["package.json"][1] == "0o644", (
        "the untouched manifest changed mode too"
    )


def test_a_version_that_is_not_semver_is_refused_before_any_write() -> None:
    for name, shown in (
        ("a-non-semver-version", "1.2"),
        ("a-prerelease-suffix", "1.2.3-rc.1"),
        ("a-leading-v", "v1.2.3"),
    ):
        code, _, stderr, state = recorded(name)
        assert code == 1, name
        assert stderr.endswith("✗ Invalid version format: %s (expected X.Y.Z)\n" % shown), name
        assert cli_version(state) == "0.4.29", name


def test_dry_run_writes_nothing_and_still_echoes_the_version() -> None:
    code, stdout, _, state = recorded("a-dry-run")
    assert code == 0
    assert stdout == "1.2.3\n"
    assert cli_version(state) == "0.4.29", "a dry run wrote the manifest"


def test_dry_run_from_the_environment_is_the_exact_literal() -> None:
    """BOTH DIRECTIONS, and the second one is the surprise. `DRY_RUN=true` suppresses the write; `DRY_RUN=1` does NOT, because the test is against the exact literal, so a caller who exported the truthy spelling every other flag in this repository accepts gets a manifest written under them. Recorded rather than smoothed over: the two recordings differ only in that one file."""
    code, stdout, _, state = recorded("a-dry-run-from-the-environment")
    assert code == 0
    assert stdout == "1.2.3\n"
    assert cli_version(state) == "0.4.29", "DRY_RUN=true wrote the manifest"

    code, stdout, _, state = recorded("a-dry-run-from-a-one")
    assert code == 0
    assert stdout == "1.2.3\n"
    assert cli_version(state) == "1.2.3", "DRY_RUN=1 is not the literal `true` and must still write"


def test_output_writes_the_version_to_a_file() -> None:
    code, stdout, _, state = recorded("an-output-file")
    assert code == 0
    assert stdout == "1.2.3\n"
    assert tree_of(state)["out.txt"] is not None, "--output wrote nothing"
    assert tree_of(state)["out.txt"][0].strip() == "1.2.3"


# --------------------------------------------------------------------------- The increments ---------------------------------------------------------------------------


def test_patch_minor_and_major_increments() -> None:
    for name, expected in (
        ("a-patch-increment", "0.4.30"),
        ("a-minor-increment", "0.5.0"),
        ("a-major-increment", "1.0.0"),
    ):
        code, stdout, stderr, state = recorded(name)
        assert code == 0, stderr
        assert stdout == expected + "\n", name
        assert cli_version(state) == expected, name


def test_auto_is_patch() -> None:
    assert recorded("auto-is-patch")[1] == "0.4.30\n"


def test_minor_and_major_survive_the_placeholder_by_luck() -> None:
    """THE HALF OF THE DEFECT THAT MAKES IT DANGEROUS. `--minor` and `--major` on `0.0.0-dev` do NOT die: they only evaluate the major and minor fields, which are plain `0`, and the `-dev` suffix rides along in a field neither of them touches. The same broken input produces a hard failure for two flags and a clean, plausible-looking version for two others, with nothing in the
    output hinting that the current version was never a semver at all."""
    for name, expected in (
        ("the-placeholder-with-minor", "0.1.0"),
        ("the-placeholder-with-major", "1.0.0"),
    ):
        code, stdout, stderr, _ = recorded(name)
        assert code == 0, stderr
        assert stdout == expected + "\n", name
        assert "Current version: 0.0.0-dev" in stderr, name


def test_a_two_part_current_version_produces_a_valid_version() -> None:
    """`1.2` splits to `1`, `2`, `` and `$(( + 1))` is 1, so the increment SUCCEEDS and yields `1.2.1`. That is a valid semver, and it is written. Recorded because it looks like a bug and is not one."""
    code, stdout, stderr, state = recorded("a-two-part-version")
    assert code == 0, stderr
    assert stdout == "1.2.1\n"
    assert cli_version(state) == "1.2.1"


# --------------------------------------------------------------------------- Missing files ---------------------------------------------------------------------------


def test_a_missing_target_manifest_warns_then_fails_at_the_end() -> None:
    """A MISSING FILE IS NOT AN IMMEDIATE STOP. The subject warns, counts it in `failed`, finishes the list, prints "Updated 0 files", and only then exits 1. So the version is never echoed on stdout even though it was computed."""
    code, stdout, stderr, state = recorded("a-missing-target-manifest")
    assert code == 1
    assert "⚠ File not found: " in stderr
    assert "✓ Updated 0 files" in stderr
    assert "✗ Failed to update 1 files" in stderr
    assert stdout == "", "the version was echoed despite the failure"
    assert tree_of(state)[CLI_MANIFEST] is None


def test_a_missing_root_manifest_dies_with_jqs_own_status() -> None:
    """`current_version=$(jq -r '.version' ...)` is a bare assignment, so `set -e` exits with jq's status and jq's stderr, before anything is written."""
    code, _, stderr, state = recorded("a-missing-root-manifest")
    assert code == 2, stderr
    assert "Current version" not in stderr
    assert cli_version(state) == "0.4.29"


# --------------------------------------------------------------------------- The four divergences, each one bash naming itself ---------------------------------------------------------------------------


def test_no_arguments_refuses_with_the_error_on_stderr_and_usage_on_stdout(
    tmp_path: pathlib.Path,
) -> None:
    """TWO STREAMS, TWO PURPOSES (:97-99). `log_error` goes to stderr and the bare `echo "Usage: ..."` goes to STDOUT, which is the same stream a successful run puts the new version on. `$0` is the one thing that cannot agree."""
    name = "no-arguments"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[2] == got[2] == "✗ Must specify --auto/--patch/--minor/--major or --version\n"
    assert want[3] == got[3], "the tree diverged"
    for stream in (want[1], got[1]):
        assert stream.startswith("Usage: ")
        assert stream.endswith(
            " [--auto | --patch | --minor | --major | --version X.Y.Z] [--dry-run]\n"
        )
    assert want[1] != got[1], "the two usage lines claim the same program"
    assert "bump.sh" in want[1], "the recording no longer names the twin"
    assert "bump.py" in got[1]


def test_the_live_defect_every_bump_flag_dies_on_the_placeholder(
    tmp_path: pathlib.Path,
) -> None:
    """THE DEFECT THE PORT INHERITED, DRIVEN RATHER THAN DESCRIBED.

    Every `package.json` in this repository carries `0.0.0-dev`, because the version source of truth is git tags. `increment_patch` splits that into `0`, `0`, `0-dev` and asks bash for `$((0-dev + 1))`; `dev` is not a variable and `set -u` kills the run. So `--auto` and `--patch` were broken on a clean checkout of this repository, and still are.

    The exit code, the preceding "Current version" line, the tree and the message SHAPE all agree; the script path and line number are each side's own, which is the divergence and is asserted in both directions.
    """
    for name in ("the-placeholder-with-auto", "the-placeholder-with-patch"):
        want = recorded(name)
        got = port(tmp_path, name)
        assert want[0] == got[0] == 1, name
        assert want[1] == got[1] == "", name
        assert want[3] == got[3], name
        want_lines = want[2].splitlines()
        got_lines = got[2].splitlines()
        assert want_lines[0] == got_lines[0] == "✓ Current version: 0.0.0-dev", name
        assert UNBOUND_RE.match(want_lines[1]), want_lines
        assert UNBOUND_RE.match(got_lines[1]), got_lines
        assert want_lines[1] != got_lines[1], "the two claim the same coordinates"
        assert cli_version(want[3]) == "0.4.29", name


def test_a_four_part_current_version_keeps_the_remainder_in_the_patch_field(
    tmp_path: pathlib.Path,
) -> None:
    """`IFS='.' read -r major minor patch` gives `patch` the WHOLE remainder, so `1.2.3.4` asks for `$((3.4 + 1))` and dies. Named here because the obvious Python port (`split(".")[2]`) would quietly succeed with `1.2.4`. Both sides die; only the coordinates in the diagnostic differ."""
    name = "a-four-part-version"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""
    assert want[3] == got[3], "the tree diverged"
    for stream in (want[2], got[2]):
        assert "arithmetic" in stream or "syntax error" in stream, stream
    assert cli_version(want[3]) == "0.4.29"


# --------------------------------------------------------------------------- The pure helpers, driven against real bash ---------------------------------------------------------------------------


def bash_dot_fields(text: str) -> list[str]:
    """`IFS='.' read -r a b c`, run by the real bash.

    STILL DRIVEN AGAINST BASH ITSELF, even though the twin is gone: the claim the port makes is about bash's field splitting, and the only honest oracle for that is bash.
    """
    script = 'IFS="." read -r a b c\nprintf "%s\\0%s\\0%s" "$a" "$b" "$c"\n'
    proc = subprocess.run(
        [BASH, "-c", script], input=text + "\n", stdout=subprocess.PIPE, text=True, check=True
    )
    return proc.stdout.split("\0")


def test_read_dot_fields_matches_bash() -> None:
    """FOUR PROPERTIES, EACH MEASURED. `.` is not IFS whitespace, so nothing collapses, nothing is stripped, empty fields survive, and the last variable keeps the remainder with its delimiters."""
    for case in ("1.2.3", "1.2.3.4", ".1.2", "1.2.", "1.2", "", "0.0.0-dev", "...."):
        assert vb.read_dot_fields(case, 3) == bash_dot_fields(case), case


def bash_arith(value: str) -> tuple[int, str]:
    proc = subprocess.run(
        [BASH, "-c", 'set -u; v="$1"; echo $((v + 1))', "x", value],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def test_bash_arith_matches_bash_on_every_value_a_manifest_can_hold() -> None:
    """BOTH DIRECTIONS. The values that WORK must produce the same number, and the values that DIE must die: a helper with only the happy half would let `0.0.0-dev` through as `0.0.1` and nobody would notice until a tag was cut."""
    for value, expected in (("29", 30), ("0", 1), ("", 1), ("010", 9), ("0x10", 17), ("7", 8)):
        rc, text = bash_arith(value)
        assert rc == 0, "%r unexpectedly died in bash: %s" % (value, text)
        assert int(text) == expected, value
        assert vb.bash_arith("%s + 1" % value, value, 1) == expected, value

    for value, needle in (("0-dev", "dev: unbound variable"), ("08", "value too great")):
        rc, text = bash_arith(value)
        assert rc != 0, "%r no longer dies in bash: %s" % (value, text)
        assert needle in text, "%r died differently in bash: %s" % (value, text)
        with pytest.raises(vb.BashFatalError, match=re.escape(needle)):
            vb.bash_arith("%s + 1" % value, value, 1)


def test_pure_helpers() -> None:
    assert vb.is_semver("1.2.3")
    assert not vb.is_semver("v1.2.3")
    assert not vb.is_semver("1.2")
    assert not vb.is_semver("1.2.3-rc.1")
    assert vb.increment_patch("0.4.29") == "0.4.30"
    assert vb.increment_minor("0.4.29") == "0.5.0"
    assert vb.increment_major("0.4.29") == "1.0.0"
    assert vb.constants_root(ROOT, {}) == str(ROOT)
    assert vb.constants_root(ROOT, {"CONSOLE_ROOT_DIR": "rel/path"}) == "rel/path"
    opts = vb.parse_argv(["--minor", "--output", "f"], dry_run_default=False)
    assert (opts.bump_type, opts.output_file, opts.dry_run) == ("minor", "f", False)


def test_constants_have_not_drifted() -> None:
    """The two things the subject gets from constants.sh, re-read from the file.

    A LIVE PARSE WOULD FOLLOW A CHANGE SILENTLY, and the subject of this script is exactly WHICH files get written, so a red test is the answer that gets read.
    """
    text = CONSTANTS.read_text(encoding="utf-8")
    match = re.search(r"readonly VERSION_FILES_JSON=\(\n(.*?)\n\)", text, re.DOTALL)
    assert match is not None, "VERSION_FILES_JSON is no longer an array literal"
    declared = tuple(re.findall(r'"([^"]+)"', match.group(1)))
    assert declared == vb.VERSION_FILES_JSON, (declared, vb.VERSION_FILES_JSON)
    assert 'CONSOLE_ROOT_DIR="${CONSOLE_ROOT_DIR:-' in text


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


OVERRIDE = """

_real_update = update_package_json


def update_package_json(path, version, *, dry_run=False):  # noqa: F811 - the plant
    result = _real_update(path, version, dry_run=dry_run)
    if not dry_run:
        import json as _json

        with open(path, encoding="utf-8") as _fh:
            _doc = _json.load(_fh)
        with open(path, "w", encoding="utf-8") as _fh:
            _json.dump(_doc, _fh, indent=2, sort_keys=True)
            _fh.write("\\n")
    return result

"""


def test_a_planted_rebuild_of_the_manifest_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `jq '.version = $v'` EDITS the manifest in place, and a port that parsed the JSON and wrote it back would report the same version, print the same lines and exit the same way while reordering every key in a file the release path publishes. The plant leaves the real writer in place and rewrites the file afterwards with sorted keys, so the exit code and both streams are identical
    and only the `--- tree ---` section sees it.

    THE PLANT IS AN OVERRIDE APPENDED TO A COPY AT THE SUBJECT'S OWN PATH INSIDE THE FIXTURE, which is where the module already runs from in every case here, so nothing about its own location changes. It is inserted BEFORE the entry point, since an override placed after `if __name__` is defined too late to matter. The tracked file is never written.
    """
    original = PORT.read_text(encoding="utf-8")
    entry = 'if __name__ == "__main__":'
    assert original.count(entry) == 1, "the plant's anchor moved"

    name = "an-explicit-version"
    want = recorded(name)
    assert '"name": "@rediacc/cli"' in tree_of(want[3])[CLI_MANIFEST][0], "the corpus moved"

    where = tmp_path / "planted"
    where.mkdir(parents=True)
    root = build(where, name, PORT)
    target = root / ".ci" / "rediacc_ci" / "version" / "bump.py"
    target.write_text(original.replace(entry, OVERRIDE + "\n" + entry, 1), encoding="utf-8")

    env = {
        "PATH": stub_path(where),
        "HOME": str(where / "home"),
        "TMPDIR": str(where / "tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    os.makedirs(env["HOME"], exist_ok=True)
    os.makedirs(env["TMPDIR"], exist_ok=True)
    proc = subprocess.run(
        [PYTHON, str(target), *CASE_KW[name]["args"]],
        cwd=str(where),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == want[1], "the plant was supposed to be invisible on stdout"
    text = (root / CLI_MANIFEST).read_text(encoding="utf-8")
    assert json.loads(text)["version"] == "1.2.3", "the plant broke the subject outright"
    assert text != tree_of(want[3])[CLI_MANIFEST][0], "the plant did not change the bytes"
    assert text.startswith('{\n  "engines"'), "the plant did not reorder the keys: %r" % text[:40]

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
