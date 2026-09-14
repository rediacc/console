"""Differential: `rediacc_ci.setup.install_cli_global` against its twin
`.ci/scripts/setup/install-cli-global.sh`.

NOTHING HERE INSTALLS ANYTHING GLOBALLY. A recording fake `npm` on a scratch
PATH logs its argv, writes a tarball-shaped file where `npm pack` would, and
exits with whatever the fixture says. `ls`, `head` and `rm` are the real
binaries, because the twin's tarball selection is a `ls | head` pipeline whose
exact exit status under `pipefail` is the subject of the most important case in
this file.

THE CASE THAT MATTERS MOST IS `test_no_tarball_exits_2_with_zero_bytes`. The
twin's own error branch for "npm pack produced nothing" is DEAD CODE:
`TARBALL=$(ls -1 rediacc-cli-*.tgz 2>/dev/null | head -n 1)` under
`set -euo pipefail` ends the script with `ls`'s exit 2 before the `if [[ -z
"$TARBALL" ]]` is reached, and `2>/dev/null` means not one byte is printed.
Exit 2, both streams empty -- indistinguishable from a gate failing for a real
reason. The port reproduces it, and that test is what pins the reproduction.

THREE KINDS OF EVIDENCE:

  1. The two streams, which carry three `log_step` lines and one of three
     mutually exclusive closing lines.
  2. The call log: `pack` then `install -g <name>`, and WHICH name is the whole
     point of fact 1 in the port's docstring (the tarball installed is not
     necessarily the one just packed).
  3. The surviving directory, because `rm -f "$TARBALL"` removes ONE file and
     leaves any other tarball behind to win the next run.

THE LEDGER LINE. `→ ` and `✓ ` are CHATTER to `shadow-gate.ts` before any
`--finding-re` is consulted, so the fake echoes `call: npm ...` on stdout for
the shadow ledger to compare. See
`.ci/shadow/w7p6-install-cli-global.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.setup import install_cli_global as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/setup/install-cli-global.sh"
PORT_REL = ".ci/rediacc_ci/setup/install_cli_global.py"
BASH = shutil.which("bash") or "/bin/bash"

TREE_FILES = (
    TWIN_REL,
    ".ci/scripts/lib/common.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/setup/__init__.py",
    PORT_REL,
)

# `dirname`/`uname` for common.sh's source-time detection, `tr` for `to_upper`
# inside `parse_args`, and `ls`/`head`/`rm` because the twin runs all three and
# their real exit statuses are what the pipefail case turns on.
PATH_MINIMUM = ("dirname", "uname", "tr", "ls", "head", "rm")

FAKE_NPM = """#!{python}
import os
import pathlib
import shlex
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("npm\\t" + "\\t".join(argv) + "\\n")

# THE LEDGER LINE, under a prefix no CHATTER rule matches.
sys.stdout.write("call: npm " + " ".join(shlex.quote(a) for a in argv) + "\\n")

if argv[:1] == ["pack"]:
    rc = int(os.environ.get("FAKE_PACK_RC") or 0)
    name = os.environ.get("FAKE_PACK_NAME") or ""
    if rc == 0 and name:
        pathlib.Path(name).write_text("tarball\\n", encoding="utf-8")
        # Real `npm pack` prints the filename it created on stdout, and the twin
        # IGNORES it -- it re-derives the name with `ls | head`. Emitted so that
        # the ignoring is visible in the compared bytes.
        sys.stdout.write(name + "\\n")
    sys.exit(rc)

sys.exit(int(os.environ.get("FAKE_INSTALL_RC") or 0))
"""

# A stand-in for the installed CLI, so the `command -v` arms can be driven. It is
# never executed; only its presence on PATH is asked about.
FAKE_CLI = "#!/bin/sh\nexit 0\n"


def _bin(tree: pathlib.Path, *, present: tuple[str, ...] = ()) -> str:
    stub = tree / "stub-bin"
    shutil.rmtree(stub, ignore_errors=True)
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        (stub / real_name).symlink_to(real)
    npm = stub / "npm"
    npm.write_text(FAKE_NPM.format(python=sys.executable), encoding="utf-8")
    npm.chmod(0o755)
    for name in present:
        (stub / name).write_text(FAKE_CLI, encoding="utf-8")
        (stub / name).chmod(0o755)
    for absent in ("rdc", "rediacc"):
        if absent not in present:
            assert shutil.which(absent, path=str(stub)) is None
    return str(stub)


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    tree = tmp_path / "tree"
    if tree.exists():
        return tree
    for rel in TREE_FILES:
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    return tree


def _layout(tree: pathlib.Path, spec: dict[str, str]) -> None:
    """Rebuild `packages/` from scratch. `spec` maps a relative path to its
    contents; a value of `""` makes a directory."""
    shutil.rmtree(tree / "packages", ignore_errors=True)
    for rel, body in spec.items():
        target = tree / rel
        if body == "":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")


def _snapshot(tree: pathlib.Path) -> list[str]:
    root = tree / "packages"
    if not root.exists():
        return []
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        out.extend(os.path.relpath(os.path.join(dirpath, name), tree) for name in sorted(filenames))
    return sorted(out)


def _run(subject: str, tree: pathlib.Path, args, *, present=(), **extra: str):
    side = "old" if subject.endswith(".sh") else "new"
    call_log = tree / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tree, present=present),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(tree / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    runner = [BASH] if subject.endswith(".sh") else [sys.executable]
    proc = subprocess.run(
        [*runner, subject, *args],
        cwd=tree,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls, _snapshot(tree)


DEFAULT_SPEC = {"packages/cli": ""}
DEFAULT_TARBALL = "rediacc-cli-0.8.3.tgz"


def run_both(tmp_path: pathlib.Path, args=(), *, spec=None, present=(), **kw):
    tree = _tree(tmp_path)
    layout = DEFAULT_SPEC if spec is None else spec
    kw.setdefault("FAKE_PACK_NAME", DEFAULT_TARBALL)
    _layout(tree, layout)
    old = _run(TWIN_REL, tree, list(args), present=present, **kw)
    _layout(tree, layout)
    new = _run(PORT_REL, tree, list(args), present=present, **kw)
    return old, new


def _assert_agree(old3, new3, label: str) -> None:
    old, old_calls, old_fs = old3
    new, new_calls, new_fs = new3
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    assert new_calls == old_calls, (
        f"{label}: call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
    )
    assert new_fs == old_fs, f"{label}: surviving tree diverged:\nold: {old_fs}\nnew: {new_fs}"


# ---------------------------------------------------------------------------
# The happy path and its three closing arms
# ---------------------------------------------------------------------------


def test_the_default_run_packs_installs_and_cleans_up(tmp_path: pathlib.Path) -> None:
    """PINNED AGAINST LITERAL BYTES. Two npm calls, four stderr lines, and no
    tarball left behind. The closing arm here is the WARNING one, because nothing
    named `rdc` or `rediacc` is on the stub PATH -- which is also fact 3: a
    successful install of nothing exits 0."""
    old3, new3 = run_both(tmp_path)
    old, old_calls, old_fs = old3
    assert old.returncode == 0
    assert old_calls == ["npm\tpack", "npm\tinstall\t-g\t" + DEFAULT_TARBALL]
    assert old.stdout == (
        f"call: npm pack\n{DEFAULT_TARBALL}\ncall: npm install -g {DEFAULT_TARBALL}\n"
    )
    assert old.stderr == (
        "→ Installing CLI globally from packages/cli...\n"
        "→ Creating npm package tarball...\n"
        f"→ Installing {DEFAULT_TARBALL} globally...\n"
        "✓ CLI installed globally\n"
        "⚠ CLI command not found in PATH (may need to restart shell)\n"
    )
    assert old_fs == []
    _assert_agree(old3, new3, "default")


def test_rdc_on_path_takes_the_first_arm(tmp_path: pathlib.Path) -> None:
    old3, new3 = run_both(tmp_path, present=("rdc",))
    assert old3[0].stderr.endswith("✓ CLI available as 'rdc'\n")
    _assert_agree(old3, new3, "rdc-present")


def test_rediacc_without_rdc_takes_the_second_arm(tmp_path: pathlib.Path) -> None:
    """THE ORDER IS THE CONTRACT: `rdc` is probed first, so this arm is only
    reachable when `rdc` is absent. A port that probed the two in the other order
    would pass the previous test and fail this one."""
    old3, new3 = run_both(tmp_path, present=("rediacc",))
    assert old3[0].stderr.endswith("✓ CLI available as 'rediacc'\n")
    _assert_agree(old3, new3, "rediacc-present")


def test_both_present_still_reports_only_rdc(tmp_path: pathlib.Path) -> None:
    old3, new3 = run_both(tmp_path, present=("rdc", "rediacc"))
    assert old3[0].stderr.count("CLI available") == 1
    assert "rediacc'" not in old3[0].stderr
    _assert_agree(old3, new3, "both-present")


# ---------------------------------------------------------------------------
# --package-dir
# ---------------------------------------------------------------------------


def test_package_dir_as_a_separate_token(tmp_path: pathlib.Path) -> None:
    old3, new3 = run_both(
        tmp_path,
        ["--package-dir", "packages/other"],
        spec={"packages/cli": "", "packages/other": ""},
    )
    assert old3[0].stderr.startswith("→ Installing CLI globally from packages/other...\n")
    assert old3[2] == []
    _assert_agree(old3, new3, "--package-dir X")


def test_package_dir_with_an_equals_sign(tmp_path: pathlib.Path) -> None:
    old3, new3 = run_both(
        tmp_path,
        ["--package-dir=packages/other"],
        spec={"packages/cli": "", "packages/other": ""},
    )
    assert old3[0].stderr.startswith("→ Installing CLI globally from packages/other...\n")
    _assert_agree(old3, new3, "--package-dir=X")


def test_an_absent_package_dir_is_refused(tmp_path: pathlib.Path) -> None:
    old3, new3 = run_both(tmp_path, ["--package-dir", "packages/nope"])
    old = old3[0]
    assert old.returncode == 1
    assert old.stderr == "✗ Required directory 'packages/nope' does not exist\n"
    assert old3[1] == [], "nothing should have been packed"
    _assert_agree(old3, new3, "absent-dir")


def test_a_bare_package_dir_flag_becomes_the_string_true(tmp_path: pathlib.Path) -> None:
    """`parse_args` stores `true` for a `--flag` with no following value, so the
    refusal names a directory called `true`. It reads like a bug in the port the
    first time it is seen and it is the twin exactly."""
    old3, new3 = run_both(tmp_path, ["--package-dir"])
    assert old3[0].returncode == 1
    assert old3[0].stderr == "✗ Required directory 'true' does not exist\n"
    _assert_agree(old3, new3, "bare --package-dir")


def test_an_empty_package_dir_value_falls_back_to_the_default(
    tmp_path: pathlib.Path,
) -> None:
    """`${ARG_PACKAGE_DIR:-packages/cli}` uses `:-`, which treats an EMPTY value
    as unset. `--package-dir=` therefore behaves as if the flag were absent
    rather than refusing an empty path."""
    old3, new3 = run_both(tmp_path, ["--package-dir="])
    assert old3[0].returncode == 0
    assert old3[0].stderr.startswith("→ Installing CLI globally from packages/cli...\n")
    _assert_agree(old3, new3, "--package-dir=")


def test_a_positional_argument_is_ignored(tmp_path: pathlib.Path) -> None:
    """`parse_args` skips anything not starting with `--`, so a caller who types
    the directory without the flag gets the default and no complaint."""
    old3, new3 = run_both(
        tmp_path, ["packages/other"], spec={"packages/cli": "", "packages/other": ""}
    )
    assert old3[0].stderr.startswith("→ Installing CLI globally from packages/cli...\n")
    _assert_agree(old3, new3, "positional")


# ---------------------------------------------------------------------------
# Failure paths, including the dead branch
# ---------------------------------------------------------------------------


def test_no_tarball_exits_2_with_zero_bytes(tmp_path: pathlib.Path) -> None:
    """THE DEAD BRANCH. `npm pack` exits 0 and writes nothing; `ls` cannot stat
    the unexpanded pattern and exits 2; `pipefail` makes the pipeline 2; `set -e`
    ends the script at the ASSIGNMENT, before the `if [[ -z "$TARBALL" ]]` that
    would have printed `No tarball found after npm pack`.

    So the observable behaviour is exit 2 with NOTHING on stderr beyond the three
    step lines, and the message written for exactly this case never runs. The
    string is asserted ABSENT, which is what makes this a test of the deadness
    rather than of the exit code alone."""
    old3, new3 = run_both(tmp_path, FAKE_PACK_NAME="")
    old = old3[0]
    assert old.returncode == 2
    assert "No tarball found after npm pack" not in old.stderr
    assert "No tarball found after npm pack" not in old.stdout
    assert old.stderr == (
        "→ Installing CLI globally from packages/cli...\n→ Creating npm package tarball...\n"
    )
    assert old3[1] == ["npm\tpack"], "install -g must never be reached"
    _assert_agree(old3, new3, "no-tarball")
    assert port.UNREACHABLE_NO_TARBALL == "No tarball found after npm pack", (
        "the unreachable string is kept in the port so it stays greppable"
    )


def test_a_failing_npm_pack_exits_with_npms_own_code_and_no_message(
    tmp_path: pathlib.Path,
) -> None:
    """Fact 2: `npm pack` is unguarded, so `set -e` propagates its status
    verbatim -- 7 stays 7, it is not normalised to 1 the way the sibling
    `build-packages.sh` normalises its build failure. No `log_error` at all."""
    old3, new3 = run_both(tmp_path, FAKE_PACK_RC="7")
    old = old3[0]
    assert old.returncode == 7
    assert "✗" not in old.stderr
    assert old3[1] == ["npm\tpack"]
    _assert_agree(old3, new3, "pack-fails")


def test_a_failing_global_install_leaves_the_tarball_behind(
    tmp_path: pathlib.Path,
) -> None:
    """`set -e` ends the run at `npm install -g`, which is BEFORE `rm -f`. The
    tarball survives -- and, per fact 1, will be a candidate again on the next
    run. Again no message of the script's own."""
    old3, new3 = run_both(tmp_path, FAKE_INSTALL_RC="4")
    old = old3[0]
    assert old.returncode == 4
    assert "✗" not in old.stderr
    assert "CLI installed globally" not in old.stderr
    assert old3[2] == ["packages/cli/" + DEFAULT_TARBALL]
    _assert_agree(old3, new3, "install-fails")


# ---------------------------------------------------------------------------
# Fact 1: the tarball installed is not necessarily the one just packed
# ---------------------------------------------------------------------------


def test_a_stale_tarball_wins_over_the_one_just_packed(tmp_path: pathlib.Path) -> None:
    """FACT 1, DRIVEN. `npm pack` creates `rediacc-cli-0.8.3.tgz` and prints that
    name; the script ignores the printed name and takes the lexicographically
    first entry of the directory, which is the leftover
    `rediacc-cli-0.0.0-dev.tgz` -- the placeholder version every package.json in
    this repo carries. That stale file is what gets installed globally, and
    `rm -f` then removes it while leaving the freshly packed one behind to lose
    again next time."""
    old3, new3 = run_both(
        tmp_path,
        spec={"packages/cli": "", "packages/cli/rediacc-cli-0.0.0-dev.tgz": "stale\n"},
    )
    old, old_calls, old_fs = old3
    assert old.returncode == 0
    assert old_calls == ["npm\tpack", "npm\tinstall\t-g\trediacc-cli-0.0.0-dev.tgz"]
    assert "→ Installing rediacc-cli-0.0.0-dev.tgz globally...\n" in old.stderr
    assert old_fs == ["packages/cli/" + DEFAULT_TARBALL], (
        "the stale one was installed and deleted; the fresh one survives untouched"
    )
    _assert_agree(old3, new3, "stale-tarball")


def test_byte_ordering_not_version_ordering(tmp_path: pathlib.Path) -> None:
    """`ls | head -n 1` sorts bytes, so `0.10.0` precedes `0.9.0`. Neither
    implementation understands semantic versions and neither should start."""
    old3, new3 = run_both(
        tmp_path,
        spec={"packages/cli": "", "packages/cli/rediacc-cli-0.9.0.tgz": "older\n"},
        FAKE_PACK_NAME="rediacc-cli-0.10.0.tgz",
    )
    assert old3[1][1] == "npm\tinstall\t-g\trediacc-cli-0.10.0.tgz"
    _assert_agree(old3, new3, "byte-ordering")


# ---------------------------------------------------------------------------
# The pure helpers, exercised directly
# ---------------------------------------------------------------------------


def test_package_dir_defaults_and_overrides() -> None:
    assert port.package_dir([]) == "packages/cli"
    assert port.package_dir(["--package-dir", "x"]) == "x"
    assert port.package_dir(["--package-dir=x"]) == "x"
    assert port.package_dir(["--package-dir="]) == "packages/cli"
    assert port.package_dir(["--package-dir"]) == "true"


def test_choose_tarball_returns_none_when_nothing_matches(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert port.choose_tarball() is None
    (tmp_path / "rediacc-cli-1.0.0.tgz").write_text("", encoding="utf-8")
    (tmp_path / "rediacc-cli-0.2.0.tgz").write_text("", encoding="utf-8")
    (tmp_path / "other.tgz").write_text("", encoding="utf-8")
    assert port.choose_tarball() == "rediacc-cli-0.2.0.tgz"


def test_remove_tarball_tolerates_absence(tmp_path: pathlib.Path) -> None:
    """`-f`. Not reachable from `main`, and a port that raised here would turn a
    race with a concurrent cleanup into a traceback."""
    port.remove_tarball(str(tmp_path / "gone.tgz"))
