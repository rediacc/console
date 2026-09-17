"""Differential: `rediacc_ci.setup.build_packages` against its twin
`.ci/scripts/setup/build-packages.sh`.

NOTHING HERE RUNS A REAL BUILD. A recording fake `npm` on a scratch PATH logs
its argv and, when the fixture asks it to, creates `packages/shared/dist` the
way a real build would. `rm` is NOT faked: the deletion is half of what this
script does and the only way to check it is to let it happen in a fixture tree
and look at what survived.

THREE KINDS OF EVIDENCE, AND ALL THREE ARE NEEDED:

  1. THE TWO STREAMS. Four `log_*` lines, one of them invisible unless
     `DEBUG=true`.
  2. THE CALL LOG, which is one line. Small, and still worth comparing: a port
     that ran `npm run build` instead of `npm run build:packages` would print
     identical output and exit 0.
  3. THE FILESYSTEM AFTER THE RUN. This is the half a stream comparison cannot
     see at all. `rm -rf packages/shared/dist packages/shared/*.tsbuildinfo`
     prints nothing on any path -- the `log_debug` above it is silent unless
     DEBUG is exactly `true` -- so a port that deleted the wrong set, or nothing,
     or too much, would be byte-identical on both streams. Every case below
     snapshots `packages/` after each side and compares the two snapshots.

THE GLOB IS THE PART A TRANSCRIPTION GETS WRONG. Bash expands
`packages/shared/*.tsbuildinfo` before `rm` runs and, with no match and no
`nullglob`, hands the PATTERN to `rm` as a literal operand that `-f` then
swallows. `test_no_tsbuildinfo_files_is_a_silent_no_op` drives exactly that, and
`test_a_dotfile_tsbuildinfo_survives_both` drives the case where the two glob
implementations could plausibly disagree and do not.

THE LEDGER LINE. `shadow-gate.ts` classifies `→ ` and `✓ ` lines as CHATTER
before `--finding-re` is consulted, and three of this script's four messages are
exactly those, so the fake's `call: npm ...` on stdout is what the shadow ledger
compares. See `.ci/shadow/w7p6-build-packages.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.setup import build_packages as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/setup/build-packages.sh"
PORT_REL = ".ci/rediacc_ci/setup/build_packages.py"
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

# `dirname`/`uname`/`tr` are what `common.sh` needs at source time; `rm` is the
# real one, on purpose. If a port ever stopped shelling out AND stopped deleting, only the filesystem snapshot would notice, which is why it exists.
PATH_MINIMUM = ("dirname", "uname", "tr", "rm")

FAKE_NPM = """#!{python}
import os
import pathlib
import shlex
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("npm\\t" + "\\t".join(argv) + "\\n")

# THE LEDGER LINE. A `→ `/`✓ ` line can never become a shadow-gate finding, so
# the fake echoes its own argv under a prefix nothing classifies as chatter.
sys.stdout.write("call: npm " + " ".join(shlex.quote(a) for a in argv) + "\\n")

# A real `npm run build:packages` emits packages/shared/dist. The fixture decides
# whether this run does, because "the build succeeded and emitted nothing" is the
# case the twin calls `(may be expected)`.
if os.environ.get("FAKE_NPM_EMIT"):
    out = pathlib.Path(os.environ["FAKE_NPM_EMIT"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.js").write_text("// built\\n", encoding="utf-8")

sys.exit(int(os.environ.get("FAKE_NPM_RC") or 0))
"""


def _bin(tree: pathlib.Path) -> str:
    stub = tree / "stub-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    npm = stub / "npm"
    npm.write_text(FAKE_NPM.format(python=sys.executable), encoding="utf-8")
    npm.chmod(0o755)
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
    """Rebuild `packages/` from scratch, so both sides start identically.

    `spec` maps a path relative to the tree root to what it should be:
    `dir`, `file`, or `link:<target>`. Written as data rather than as a pile of
    boolean flags because the interesting cases are about the TYPE of
    `packages/shared/dist`, not about its presence.
    """
    shutil.rmtree(tree / "packages", ignore_errors=True)
    shutil.rmtree(tree / "keepsake", ignore_errors=True)
    for rel, kind in spec.items():
        target = tree / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "dir":
            target.mkdir(parents=True, exist_ok=True)
        elif kind == "file":
            target.write_text("x\n", encoding="utf-8")
        elif kind.startswith("link:"):
            target.symlink_to(kind.split(":", 1)[1])
        else:  # pragma: no cover - a typo in a fixture must not pass silently
            raise ValueError("unknown fixture kind %r" % kind)


def _snapshot(tree: pathlib.Path) -> list[str]:
    """Every surviving path under `packages/` and `keepsake/`, with its type.

    Sorted, relative, and typed. `keepsake/` is in the snapshot because the
    symlink case needs to prove the TARGET survived: `rm -rf` on a symlink
    removes the link, and a port that followed it would delete a directory
    outside `packages/` with no output difference at all.
    """
    out: list[str] = []
    for base in ("packages", "keepsake"):
        root = tree / base
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            here = os.path.relpath(dirpath, tree)
            out.append("dir  %s" % here)
            for name in sorted(filenames + [d for d in dirnames if (tree / here / d).is_symlink()]):
                path = tree / here / name
                kind = "link" if path.is_symlink() else "file"
                out.append("%s %s" % (kind, os.path.relpath(path, tree)))
    return sorted(set(out))


def _run(subject: str, tree: pathlib.Path, args: list[str], **extra: str):
    side = "old" if subject.endswith(".sh") else "new"
    call_log = tree / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tree),
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


DEFAULT_SPEC = {
    "packages/shared/dist": "dir",
    "packages/shared/dist/stale.js": "file",
    "packages/shared/tsconfig.tsbuildinfo": "file",
}


def run_both(tmp_path: pathlib.Path, args: list[str] = (), *, spec=None, **kw):
    tree = _tree(tmp_path)
    layout = DEFAULT_SPEC if spec is None else spec
    emit = kw.pop("emit", True)
    if emit:
        kw["FAKE_NPM_EMIT"] = str(tree / "packages/shared/dist")
    _layout(tree, layout)
    old, old_calls, old_fs = _run(TWIN_REL, tree, list(args), **kw)
    _layout(tree, layout)
    new, new_calls, new_fs = _run(PORT_REL, tree, list(args), **kw)
    return (old, old_calls, old_fs), (new, new_calls, new_fs)


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


# --------------------------------------------------------------------------- The happy path ---------------------------------------------------------------------------


def test_the_default_run_wipes_builds_and_verifies(tmp_path: pathlib.Path) -> None:
    """PINNED AGAINST LITERAL BYTES. One npm call, three stderr lines, and the
    stale `dist/stale.js` gone -- proof the wipe happened before the build rather
    than being skipped because the directory already existed."""
    old3, new3 = run_both(tmp_path)
    old, old_calls, old_fs = old3
    assert old.returncode == 0
    assert old_calls == ["npm\trun\tbuild:packages"]
    assert old.stdout == "call: npm run build:packages\n"
    assert old.stderr == (
        "→ Building shared packages...\n"
        "✓ Shared packages built successfully\n"
        "✓ Verified: packages/shared/dist exists\n"
    )
    assert "file packages/shared/dist/stale.js" not in old_fs
    assert "file packages/shared/dist/index.js" in old_fs
    assert "file packages/shared/tsconfig.tsbuildinfo" not in old_fs
    _assert_agree(old3, new3, "default")


def test_debug_true_reveals_the_otherwise_silent_deletion(tmp_path: pathlib.Path) -> None:
    """`log_debug` (common.sh:51-55) is the only announcement the `rm -rf` gets,
    and it needs `DEBUG` to be exactly `true`."""
    old3, new3 = run_both(tmp_path, DEBUG="true")
    assert old3[0].stderr.splitlines()[1] == "[DEBUG] Cleaning TypeScript build cache..."
    _assert_agree(old3, new3, "DEBUG=true")


def test_debug_1_is_not_debug_true(tmp_path: pathlib.Path) -> None:
    """THE NEGATIVE CONTROL for the debug branch. `DEBUG=1` is truthy to a human
    and to most tools, and to `[[ "${DEBUG:-false}" == "true" ]]` it is not. A
    port that accepted any truthy string would be quietly noisier than the twin
    on every machine where someone exports DEBUG=1 for another tool."""
    old3, new3 = run_both(tmp_path, DEBUG="1")
    assert "[DEBUG]" not in old3[0].stderr
    _assert_agree(old3, new3, "DEBUG=1")


# --------------------------------------------------------------------------- The vacuity, and the failure ---------------------------------------------------------------------------


def test_a_build_that_emits_nothing_warns_and_exits_zero(tmp_path: pathlib.Path) -> None:
    """THE VACUITY CLASS, IN THE SCRIPT WHOSE JOB IS TO BUILD. The script deletes
    `packages/shared/dist`, runs a build that produces nothing, finds the
    directory gone, calls that `(may be expected)` and exits 0. That is exactly
    the tsbuildinfo no-op the wipe eleven lines above exists to prevent, and it
    is reported as a warning nobody greps for."""
    old3, new3 = run_both(tmp_path, emit=False)
    old = old3[0]
    assert old.returncode == 0
    assert old.stderr == (
        "→ Building shared packages...\n"
        "✓ Shared packages built successfully\n"
        "⚠ Package directory packages/shared/dist not found (may be expected)\n"
    )
    assert old3[2] == ["dir  packages", "dir  packages/shared"]
    _assert_agree(old3, new3, "emitted-nothing")


def test_a_failing_build_stops_before_the_verification(tmp_path: pathlib.Path) -> None:
    """Exit 1, and the `Verified:`/`not found` line never prints -- so a reader
    cannot tell from the output whether `dist` survived. It did not."""
    old3, new3 = run_both(tmp_path, emit=False, FAKE_NPM_RC="3")
    old = old3[0]
    assert old.returncode == 1, "the twin normalises npm's 3 to its own 1"
    assert old.stderr == ("→ Building shared packages...\n✗ Failed to build shared packages\n")
    assert "Verified" not in old.stderr
    assert "may be expected" not in old.stderr
    _assert_agree(old3, new3, "build-fails")


# --------------------------------------------------------------------------- The glob and the `rm -rf` ---------------------------------------------------------------------------


def test_no_tsbuildinfo_files_is_a_silent_no_op(tmp_path: pathlib.Path) -> None:
    """With no match, bash hands `rm` the PATTERN as a literal operand and `-f`
    swallows the resulting error: nothing is printed and the exit code is
    untouched. The port globs to an empty list, which is the same outcome by a
    different route -- and the route matters, because a port that passed the
    unexpanded pattern to `Path.unlink` would raise."""
    old3, new3 = run_both(
        tmp_path,
        spec={"packages/shared/dist": "dir", "packages/shared/src.ts": "file"},
    )
    old = old3[0]
    assert old.returncode == 0
    assert "No such file" not in old.stderr
    assert "file packages/shared/src.ts" in old3[2]
    _assert_agree(old3, new3, "no-tsbuildinfo")


def test_every_tsbuildinfo_goes_not_just_the_first(tmp_path: pathlib.Path) -> None:
    old3, new3 = run_both(
        tmp_path,
        spec={
            "packages/shared/dist": "dir",
            "packages/shared/tsconfig.tsbuildinfo": "file",
            "packages/shared/tsconfig.build.tsbuildinfo": "file",
            "packages/shared/nested/deep.tsbuildinfo": "file",
        },
    )
    survivors = old3[2]
    assert not [s for s in survivors if s.endswith("shared/tsconfig.tsbuildinfo")]
    assert not [s for s in survivors if s.endswith("tsconfig.build.tsbuildinfo")]
    # The glob has no `**`, so a nested one is NOT swept. Reproduced, not fixed.
    assert "file packages/shared/nested/deep.tsbuildinfo" in survivors
    _assert_agree(old3, new3, "many-tsbuildinfo")


def test_a_dotfile_tsbuildinfo_survives_both(tmp_path: pathlib.Path) -> None:
    """`*` matches no leading dot in bash and none in `glob`, so `.tsbuildinfo`
    is invisible to both. The case exists because that is the single most likely
    place two glob implementations disagree."""
    old3, new3 = run_both(
        tmp_path,
        spec={"packages/shared/dist": "dir", "packages/shared/.tsbuildinfo": "file"},
    )
    assert "file packages/shared/.tsbuildinfo" in old3[2]
    _assert_agree(old3, new3, "dotfile")


def test_dist_as_a_regular_file_is_removed_too(tmp_path: pathlib.Path) -> None:
    """`rm -rf` does not care what `dist` is; `shutil.rmtree` would raise
    `NotADirectoryError`. The build then recreates it as a directory."""
    old3, new3 = run_both(
        tmp_path, spec={"packages/shared/dist": "file", "packages/shared/x.tsbuildinfo": "file"}
    )
    assert old3[0].returncode == 0
    assert "dir  packages/shared/dist" in old3[2]
    _assert_agree(old3, new3, "dist-is-a-file")


def test_dist_as_a_symlink_loses_the_link_and_keeps_the_target(
    tmp_path: pathlib.Path,
) -> None:
    """A stale `dist` symlink into another worktree is a real state in a repo
    that uses git worktrees. `rm -rf` unlinks it and never touches what it points
    at; a port that resolved the link first would silently delete somebody else's
    build output, with byte-identical stdout and stderr. The snapshot includes
    `keepsake/` precisely so that deletion would be visible here."""
    old3, new3 = run_both(
        tmp_path,
        emit=False,
        spec={
            "keepsake/real-dist": "dir",
            "keepsake/real-dist/precious.js": "file",
            "packages/shared/dist": "link:../../keepsake/real-dist",
        },
    )
    survivors = old3[2]
    assert "file keepsake/real-dist/precious.js" in survivors
    assert not [s for s in survivors if s.endswith("packages/shared/dist")]
    _assert_agree(old3, new3, "dist-is-a-symlink")


# --------------------------------------------------------------------------- Arguments, which the twin has none of ---------------------------------------------------------------------------


def test_arguments_are_ignored_including_help(tmp_path: pathlib.Path) -> None:
    """The twin has no `parse_args` and no `case`, so `--help` builds the
    packages. An argparse in the port would exit 2 with a usage block instead."""
    old3, new3 = run_both(tmp_path, ["--help", "nonsense"])
    assert old3[0].returncode == 0
    assert old3[1] == ["npm\trun\tbuild:packages"]
    _assert_agree(old3, new3, "--help")


# --------------------------------------------------------------------------- The pure helper, exercised directly ---------------------------------------------------------------------------


def test_clean_targets_lists_dist_first_and_always(tmp_path: pathlib.Path) -> None:
    """`dist` is handed to `rm -rf` unconditionally, present or not, so it is in
    the list either way -- a caller counting targets should see what bash built,
    not the subset that happened to exist."""
    shared = tmp_path / "packages" / "shared"
    shared.mkdir(parents=True)
    (shared / "b.tsbuildinfo").write_text("", encoding="utf-8")
    (shared / "a.tsbuildinfo").write_text("", encoding="utf-8")
    assert port.clean_targets(tmp_path) == [
        "packages/shared/dist",
        "packages/shared/a.tsbuildinfo",
        "packages/shared/b.tsbuildinfo",
    ]


def test_clean_targets_on_an_empty_tree_is_just_dist(tmp_path: pathlib.Path) -> None:
    assert port.clean_targets(tmp_path) == ["packages/shared/dist"]


def test_remove_path_is_a_no_op_on_something_absent(tmp_path: pathlib.Path) -> None:
    """`-f`. A port that raised here would fail every run on a fresh checkout."""
    port.remove_path(str(tmp_path / "nothing-here"))
