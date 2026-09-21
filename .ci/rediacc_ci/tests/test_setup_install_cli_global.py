"""`rediacc_ci.setup.install_cli_global`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/setup/install-cli-global.sh` and the port over one fixture tree apiece and compared three kinds of evidence at once. The K=5 ledgers `.ci/shadow/w7p6-install-cli-global.observations.jsonl` and `.ci/shadow/w7p4b-install-cli-global.observations.jsonl` recorded that over five distinct trees each.

Every case now compares against `goldens/install-cli-global/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree; each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

NOTHING HERE INSTALLS ANYTHING GLOBALLY. A recording fake `npm` on a scratch PATH logs its argv, writes a tarball-shaped file where `npm pack` would, and exits with whatever the case says. `ls`, `head` and `rm` are the real binaries, because the twin's tarball selection is a `ls | head` pipeline whose exact exit status under `pipefail` is the subject of the most important case in
this file.

THREE KINDS OF EVIDENCE, SO THE RECORDED SHAPE CARRIES TWO SECTIONS BEYOND THE STREAMS:

  1. The two streams, which carry three `log_step` lines and one of three
     mutually exclusive closing lines.
  2. `--- calls ---`, the fake's argv log: `pack` then `install -g <name>`, and
     WHICH name is the whole point of fact 1 in the port's docstring (the tarball
     installed is not necessarily the one just packed). A port that packed and
     installed nothing at all would print the same steps.
  3. `--- tree ---`, the surviving `packages/` listing, because `rm -f "$TARBALL"`
     removes ONE file and leaves any other tarball behind to win the next run. A
     cleanup that stopped happening is invisible on both streams.

THE CASE THAT MATTERS MOST IS `no-tarball-at-all`. The twin's own error branch for "npm pack produced nothing" is DEAD CODE: `TARBALL=$(ls -1 rediacc-cli-*.tgz 2>/dev/null | head -n 1)` under `set -euo pipefail` ended the script with `ls`'s exit 2 before the `if [[ -z "$TARBALL" ]]` was reached, and `2>/dev/null` meant not one byte was printed.

Exit 2, both streams empty, indistinguishable from a gate failing for a real reason. The recording is what pins the reproduction now that the script is gone.

NOTHING IS MASKED, and that is a claim rather than an omission. The differential compared raw bytes with no normalizer at all, and a freezing normally has to add one for the fixture's absolute path; here no absolute path reaches any recorded section. Both streams carry only the package directory as the case spelled it, the tarball names the case's own environment chose, and literal
prose. The call log is argv, which is relative. The tree listing is built with `os.path.relpath` against the fixture root. A golden that masked any of those would be weaker than the comparison it replaced.

THE LEDGER LINE. `→ ` and `✓ ` are CHATTER to `shadow-gate.ts` before any `--finding-re` is consulted, so the fake echoes `call: npm ...` on stdout for the shadow ledger to compare, and that line is part of the recorded stdout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.setup import install_cli_global as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
SLUG = "install-cli-global"

TWIN_REL = ".ci/scripts/setup/install-cli-global.sh"
PORT_REL = ".ci/rediacc_ci/setup/install_cli_global.py"
BASH = shutil.which("bash") or "/bin/bash"

CALLS_MARKER = "--- calls ---\n"
TREE_MARKER = "--- tree ---\n"

# Both subjects resolve the repo root from their own file location, so the fixture holds a COPY of the port at that relative depth rather than running the tracked file in place.
TREE_FILES = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/setup/__init__.py",
    PORT_REL,
)

# What a BASH subject needed in the tree on top of that: the twin itself and the library it sourced. Reached only by the one-shot recorder, which ran while the twin was still tracked; the suite's subject is the port or a throwaway mutant of it.
BASH_FILES = (TWIN_REL, ".ci/scripts/lib/common.sh")

# `dirname`/`uname` for common.sh's source-time detection, `tr` for `to_upper` inside `parse_args`, and `ls`/`head`/`rm` because the twin ran all three and their real exit statuses are what the pipefail case turns on.
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
        # IGNORED it -- it re-derived the name with `ls | head`. Emitted so that
        # the ignoring is visible in the compared bytes.
        sys.stdout.write(name + "\\n")
    sys.exit(rc)

sys.exit(int(os.environ.get("FAKE_INSTALL_RC") or 0))
"""

# A stand-in for the installed CLI, so the `command -v` arms can be driven. It is never executed; only its presence on PATH is asked about.
FAKE_CLI = "#!/bin/sh\nexit 0\n"

DEFAULT_SPEC = {"packages/cli": ""}
TWO_DIRS = {"packages/cli": "", "packages/other": ""}
DEFAULT_TARBALL = "rediacc-cli-0.8.3.tgz"

# name -> how the run is wired. `args` is the argv, `spec` rebuilds `packages/` (a value of `""` makes a directory), `present` puts a CLI stand-in on the stub PATH, and `env` overrides what the fake `npm` does.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-default-run": {},
    "rdc-on-path": {"present": ("rdc",)},
    "rediacc-on-path-without-rdc": {"present": ("rediacc",)},
    "both-names-on-path": {"present": ("rdc", "rediacc")},
    "package-dir-as-a-separate-token": {
        "args": ["--package-dir", "packages/other"],
        "spec": TWO_DIRS,
    },
    "package-dir-with-an-equals-sign": {
        "args": ["--package-dir=packages/other"],
        "spec": TWO_DIRS,
    },
    "an-absent-package-dir": {"args": ["--package-dir", "packages/nope"]},
    "a-bare-package-dir-flag": {"args": ["--package-dir"]},
    "an-empty-package-dir-value": {"args": ["--package-dir="]},
    "a-positional-argument": {"args": ["packages/other"], "spec": TWO_DIRS},
    "no-tarball-at-all": {"env": {"FAKE_PACK_NAME": ""}},
    "a-failing-npm-pack": {"env": {"FAKE_PACK_RC": "7"}},
    "a-failing-global-install": {"env": {"FAKE_INSTALL_RC": "4"}},
    "a-stale-tarball-wins": {
        "spec": {"packages/cli": "", "packages/cli/rediacc-cli-0.0.0-dev.tgz": "stale\n"},
    },
    "byte-ordering-not-version-ordering": {
        "spec": {"packages/cli": "", "packages/cli/rediacc-cli-0.9.0.tgz": "older\n"},
        "env": {"FAKE_PACK_NAME": "rediacc-cli-0.10.0.tgz"},
    },
}

CASES = tuple(CASE_KW)


def stub_bin(tree: pathlib.Path, present: tuple[str, ...]) -> str:
    """The whole PATH for one run: the six real binaries, the fake `npm`, and whichever CLI names this case wants found."""
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


def fixture(tmp_path: pathlib.Path, name: str, subject: str) -> pathlib.Path:
    """This case's own tree, built from scratch. A fresh one per run, so no run inherits the tarballs the previous one left behind."""
    tree = tmp_path / "tree"
    needed = TREE_FILES + (BASH_FILES if subject.endswith(".sh") else ())
    for rel in needed:
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    shutil.rmtree(tree / "packages", ignore_errors=True)
    for rel, body in (CASE_KW[name].get("spec") or DEFAULT_SPEC).items():
        target = tree / rel
        if body == "":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
    return tree


def snapshot(tree: pathlib.Path) -> list[str]:
    """Every file left under `packages/`, named relative to the fixture root."""
    root = tree / "packages"
    if not root.exists():
        return []
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        out.extend(os.path.relpath(os.path.join(dirpath, name), tree) for name in sorted(filenames))
    return sorted(out)


def run(
    tmp_path: pathlib.Path, name: str, *, subject: str = PORT_REL
) -> tuple[int, str, str, list[str], list[str]]:
    """One subject, once, over this case's own fixture. Returns the recorded shape's five parts.

    `subject` is interpreted from inside the tree, so the tracked port runs from its copy and a mutant runs from an absolute path outside it, resolving `rediacc_ci` through the same `PYTHONPATH` either way.
    """
    kw = CASE_KW[name]
    tree = fixture(tmp_path, name, subject)
    call_log = tree / "calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_bin(tree, kw.get("present") or ()),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(tree / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_PACK_NAME": DEFAULT_TARBALL,
    }
    env.update(kw.get("env") or {})
    runner = BASH if subject.endswith(".sh") else sys.executable
    proc = subprocess.run(
        [runner, subject, *(kw.get("args") or [])],
        cwd=tree,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls, snapshot(tree)


def render(code: int, stdout: str, stderr: str, calls: list[str], tree: list[str]) -> str:
    return "%s%s%s\n%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        json.dumps(calls, indent=2),
        TREE_MARKER,
        json.dumps(tree, indent=2),
    )


def recorded(name: str) -> tuple[int, str, str, list[str], list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, tree = rest.split(TREE_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        json.loads(calls),
        json.loads(tree),
    )


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str], list[str]]:
    want = recorded(name)
    got = run(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the npm calls diverged: %r vs %r" % (name, want[3], got[3])
    assert got[4] == want[4], "%s: the surviving tree diverged: %r vs %r" % (name, want[4], got[4])
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The happy path and its three closing arms ---------------------------------------------------------------------------


def test_the_default_run_packs_installs_and_cleans_up() -> None:
    """PINNED AGAINST LITERAL BYTES. Two npm calls, five stderr lines, and no tarball left behind. The closing arm is the WARNING one, because nothing named `rdc` or `rediacc` was on the stub PATH, which is also fact 3: a successful install of nothing exits 0."""
    code, stdout, stderr, calls, tree = recorded("the-default-run")
    assert code == 0
    assert calls == ["npm\tpack", "npm\tinstall\t-g\t" + DEFAULT_TARBALL]
    assert stdout == f"call: npm pack\n{DEFAULT_TARBALL}\ncall: npm install -g {DEFAULT_TARBALL}\n"
    assert stderr == (
        "→ Installing CLI globally from packages/cli...\n"
        "→ Creating npm package tarball...\n"
        f"→ Installing {DEFAULT_TARBALL} globally...\n"
        "✓ CLI installed globally\n"
        "⚠ CLI command not found in PATH (may need to restart shell)\n"
    )
    assert tree == []


def test_rdc_on_path_takes_the_first_arm() -> None:
    assert recorded("rdc-on-path")[2].endswith("✓ CLI available as 'rdc'\n")


def test_rediacc_without_rdc_takes_the_second_arm() -> None:
    """THE ORDER IS THE CONTRACT: `rdc` was probed first, so this arm is only reachable when `rdc` is absent. A port that probed the two in the other order would match the previous recording and fail this one."""
    assert recorded("rediacc-on-path-without-rdc")[2].endswith("✓ CLI available as 'rediacc'\n")


def test_both_present_still_reports_only_rdc() -> None:
    stderr = recorded("both-names-on-path")[2]
    assert stderr.count("CLI available") == 1
    assert "rediacc'" not in stderr


# --------------------------------------------------------------------------- --package-dir ---------------------------------------------------------------------------


def test_package_dir_is_honoured_in_both_spellings() -> None:
    """`--package-dir X` and `--package-dir=X` reach the same place, and the run still cleans up after itself in the directory it was pointed at."""
    for name in ("package-dir-as-a-separate-token", "package-dir-with-an-equals-sign"):
        _, _, stderr, _, tree = recorded(name)
        assert stderr.startswith("→ Installing CLI globally from packages/other...\n"), name
        assert tree == [], name


def test_an_absent_package_dir_is_refused() -> None:
    code, _, stderr, calls, _ = recorded("an-absent-package-dir")
    assert code == 1
    assert stderr == "✗ Required directory 'packages/nope' does not exist\n"
    assert calls == [], "nothing should have been packed"


def test_a_bare_package_dir_flag_becomes_the_string_true() -> None:
    """`parse_args` stored `true` for a `--flag` with no following value, so the refusal named a directory called `true`. It reads like a bug in the port the first time it is seen and it is the twin exactly."""
    code, _, stderr, _, _ = recorded("a-bare-package-dir-flag")
    assert code == 1
    assert stderr == "✗ Required directory 'true' does not exist\n"


def test_an_empty_package_dir_value_falls_back_to_the_default() -> None:
    """`${ARG_PACKAGE_DIR:-packages/cli}` used `:-`, which treats an EMPTY value as unset. `--package-dir=` therefore behaved as if the flag were absent rather than refusing an empty path."""
    code, _, stderr, _, _ = recorded("an-empty-package-dir-value")
    assert code == 0
    assert stderr.startswith("→ Installing CLI globally from packages/cli...\n")


def test_a_positional_argument_is_ignored() -> None:
    """`parse_args` skipped anything not starting with `--`, so a caller who typed the directory without the flag got the default and no complaint, even with the named directory sitting right there."""
    assert recorded("a-positional-argument")[2].startswith(
        "→ Installing CLI globally from packages/cli...\n"
    )


# --------------------------------------------------------------------------- Failure paths, including the dead branch ---------------------------------------------------------------------------


def test_no_tarball_exits_2_with_zero_bytes() -> None:
    """THE DEAD BRANCH. `npm pack` exited 0 and wrote nothing; `ls` could not stat the unexpanded pattern and exited 2; `pipefail` made the pipeline 2; `set -e` ended the script at the ASSIGNMENT, before the `if [[ -z "$TARBALL" ]]` that would have printed `No tarball found after npm pack`.

    So the recorded behaviour is exit 2 with NOTHING on stderr beyond the two step lines, and the message written for exactly this case never ran. The string is asserted ABSENT from the recording, which is what makes this a test of the deadness rather than of the exit code alone.
    """
    code, stdout, stderr, calls, _ = recorded("no-tarball-at-all")
    assert code == 2
    assert port.UNREACHABLE_NO_TARBALL not in stderr
    assert port.UNREACHABLE_NO_TARBALL not in stdout
    assert stderr == (
        "→ Installing CLI globally from packages/cli...\n→ Creating npm package tarball...\n"
    )
    assert calls == ["npm\tpack"], "install -g must never be reached"
    assert port.UNREACHABLE_NO_TARBALL == "No tarball found after npm pack", (
        "the unreachable string is kept in the port so it stays greppable"
    )


def test_a_failing_npm_pack_exits_with_npms_own_code_and_no_message() -> None:
    """Fact 2: `npm pack` was unguarded, so `set -e` propagated its status verbatim. 7 stays 7, it is not normalised to 1 the way the sibling `build-packages.sh` normalises its build failure, and no `log_error` is recorded at all."""
    code, _, stderr, calls, _ = recorded("a-failing-npm-pack")
    assert code == 7
    assert "✗" not in stderr
    assert calls == ["npm\tpack"]


def test_a_failing_global_install_leaves_the_tarball_behind() -> None:
    """`set -e` ended the run at `npm install -g`, which is BEFORE `rm -f`. The tarball survives in the recorded tree and, per fact 1, would be a candidate again on the next run. Again no message of the script's own."""
    code, _, stderr, _, tree = recorded("a-failing-global-install")
    assert code == 4
    assert "✗" not in stderr
    assert "CLI installed globally" not in stderr
    assert tree == ["packages/cli/" + DEFAULT_TARBALL]


# --------------------------------------------------------------------------- Fact 1: the tarball installed is not necessarily the one just packed ---------------------------------------------------------------------------


def test_a_stale_tarball_wins_over_the_one_just_packed() -> None:
    """FACT 1, RECORDED. `npm pack` created `rediacc-cli-0.8.3.tgz` and printed that name; the script ignored the printed name and took the lexicographically first entry of the directory, which is the leftover `rediacc-cli-0.0.0-dev.tgz`, the placeholder version every package.json in this repo carries.

    That stale file is what got installed globally, and `rm -f` then removed it while leaving the freshly packed one behind to lose again next time."""
    code, _, stderr, calls, tree = recorded("a-stale-tarball-wins")
    assert code == 0
    assert calls == ["npm\tpack", "npm\tinstall\t-g\trediacc-cli-0.0.0-dev.tgz"]
    assert "→ Installing rediacc-cli-0.0.0-dev.tgz globally...\n" in stderr
    assert tree == ["packages/cli/" + DEFAULT_TARBALL], (
        "the stale one was installed and deleted; the fresh one survives untouched"
    )


def test_byte_ordering_not_version_ordering() -> None:
    """`ls | head -n 1` sorted bytes, so `0.10.0` precedes `0.9.0`. Neither implementation understands semantic versions and neither should start."""
    assert recorded("byte-ordering-not-version-ordering")[3][1] == (
        "npm\tinstall\t-g\trediacc-cli-0.10.0.tgz"
    )


# --------------------------------------------------------------------------- The pure helpers, exercised directly ---------------------------------------------------------------------------


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
    """`-f`. Not reachable from `main`, and a port that raised here would turn a race with a concurrent cleanup into a traceback."""
    port.remove_tarball(str(tmp_path / "gone.tgz"))


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_skip_of_the_cleanup_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Stop deleting the tarball that was just installed.

    `rm -f "$TARBALL"` is the last thing the twin did before its closing lines, and skipping it changes not one byte of either stream and not one entry of the call log: the mutant packs, installs and reports exactly as the recording says. Only `--- tree ---` sees it, which is the section a stream-only recording would have dropped. It is also the live defect underneath fact 1, since
    a tarball that survives is the one that wins the next run.

    The mutation runs from a throwaway copy placed outside the fixture and resolving `rediacc_ci` through the same `PYTHONPATH`; the tracked port is never touched, and the real port is compared again afterwards so a mutant that failed for some unrelated reason cannot pass for a caught one.
    """
    source = ROOT / PORT_REL
    original = source.read_text(encoding="utf-8")
    anchor = "    try:\n        remove_tarball(tarball)\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "    try:\n        pass\n")

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-default-run"
    want = recorded(name)
    got = run(tmp_path / "planted", name, subject=str(mutant))
    assert want[4] == [], "the recorded corpus moved"
    assert got[4] == ["packages/cli/" + DEFAULT_TARBALL], "the plant did not change the tree"
    assert got[:4] == want[:4], "only the surviving tree may differ, and it is what catches this"

    compare(tmp_path / "good", name)
    assert source.read_text(encoding="utf-8") == original
