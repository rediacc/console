"""Differential: `rediacc_ci.security.shellcheck` against its twin `.ci/scripts/security/shellcheck.sh`.

TWO KINDS OF CASE.

  ONE REAL RUN against this repository's own 620 tracked-and-untracked shell
  scripts with the REAL pinned shellcheck. It is the only input that exercises
  the real `git ls-files` union, the 16-batch chunking and the real `--version`
  banner at once, it takes about 100 seconds per side, and it is BYTE FOR BYTE
  on both streams with no normalisation of any kind. It hashes all 620 inputs
  before and after and refuses a byte of drift.

  FIXTURE RUNS in a scratch GIT repository -- git, because the enumerator IS
  `git ls-files` and a fixture without an index would exercise a different half
  of it. A RECORDING FAKE `shellcheck` on a scratch PATH makes the BATCH
  BOUNDARIES observable, which matters: the real tool prints its "For more
  information" footer once per invocation, so a port that chunked by 50 instead
  of 40 would produce different bytes on a real tree while passing every
  stdout comparison a single-batch fixture could make.

EVERY GIT OPERATION IS `git -C <scratch>` AND NEVER A `cd`, and `_git` asserts that `rev-parse --show-toplevel` resolves inside the scratch directory before it runs anything. The repository this test file lives in normally holds several sessions' uncommitted work; a stray `git add -A` in the wrong tree is not recoverable.

WHAT IS NORMALISED: the scratch tool-cache path, which is per-side by construction so that a download in one side cannot satisfy the other. Nothing
else. In particular the bash-4 block's `grep -r` order is NOT normalised, and
is instead confined to single-file fixtures for the reason given in the port's module docstring.

K=5 LEDGER: `.ci/shadow/w7p6-shellcheck.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.security import shellcheck as port
from rediacc_ci.tests import differential

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/security/shellcheck.sh"
PORT_REL = ".ci/rediacc_ci/security/shellcheck.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

COPIED = (
    TWIN_REL,
    ".ci/scripts/lib/toolchain.sh",
    ".ci/config/constants.sh",
    ".devcontainer/toolchain.env",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/proc.py",
    ".ci/rediacc_ci/gitx.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/toolchain.py",
    ".ci/rediacc_ci/security/__init__.py",
    PORT_REL,
)

TRIVIAL_SH = '#!/bin/bash\necho "$1"\n'

FAKE_SHELLCHECK = """#!/bin/bash
if [[ "$1" == "--version" ]]; then
    printf 'ShellCheck - fake\\nversion: %s\\n' "$FAKE_VERSION"
    exit 0
fi
printf 'FAKECALL shellcheck %s\\n' "$*" >>"$FAKE_LOG"
n=0
for a in "$@"; do
    [[ "$a" == -* || "$a" == SC* || "$a" == warning ]] && continue
    n=$((n + 1))
    if [[ -n "${FAKE_FLAG_ON:-}" && "$a" == *"$FAKE_FLAG_ON"* ]]; then
        printf 'In %s line 2:\\necho $1\\n     ^-- SC2086: Double quote.\\n' "$a"
        touch "$FAKE_DATA/flagged"
    fi
done
printf 'FAKEBATCH %d\\n' "$n" >>"$FAKE_LOG"
[[ -f "$FAKE_DATA/flagged" && -n "${FAKE_FLAG_ON:-}" ]] && exit 1
exit 0
"""

FAKE_CURL = """#!/bin/bash
printf 'FAKECALL curl %s\\n' "$*" >>"$FAKE_LOG"
exit 22
"""


def _write(path: pathlib.Path, body: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def pin() -> str:
    return toolchain.pin_for("shellcheck")


def _git(scratch: pathlib.Path, *args: str) -> str:
    """`git -C <scratch> ...`, with the toplevel guard fired FIRST.

    The guard is not decoration. `git add -A` and `git commit` in this repository would sweep several other sessions' uncommitted work into an index nobody asked for, and the check that the toplevel resolves inside `scratch` is the one thing standing between this fixture and that.
    """
    resolved = subprocess.run(
        ["git", "-C", str(scratch), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert pathlib.Path(resolved).resolve() == scratch.resolve(), (
        "REFUSING: git -C %s resolves to %s, not the scratch tree" % (scratch, resolved)
    )
    assert pathlib.Path(resolved).resolve() != ROOT.resolve(), "REFUSING: that is the real repo"
    return subprocess.run(
        ["git", "-C", str(scratch), *args],
        capture_output=True,
        text=True,
        check=True,
        env={
            **differential.env_for(),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    ).stdout


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A scratch GIT repository holding both implementations and the fakes."""
    fx = tmp_path / "fx"
    fx.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(fx)],
        check=True,
        capture_output=True,
        text=True,
    )
    for rel in COPIED:
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    _write(fx / "run.sh", TRIVIAL_SH)
    _write(fx / "scripts" / "one.sh", TRIVIAL_SH)
    _git(fx, "add", "-A")
    _git(fx, "commit", "-qm", "fixture")

    data = fx / "fake" / "data"
    data.mkdir(parents=True, exist_ok=True)
    bindir = fx / "fake" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    _write(bindir / "curl", FAKE_CURL, mode=0o755)
    return fx


def _env(fx: pathlib.Path, side: str, log: pathlib.Path, **extra: str) -> dict[str, str]:
    env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
    env["FAKE_LOG"] = str(log)
    env["FAKE_DATA"] = str(fx / "fake" / "data")
    env["FAKE_VERSION"] = pin()
    if side == "new":
        env["PYTHONPATH"] = str(fx / ".ci")
    env.update(extra)
    return env


def run_both(
    fx: pathlib.Path, *, fake_tool: bool = True, scratch_cache: bool = False, **extra: str
) -> tuple:
    """Both implementations, same fixture. Returns results AND call logs."""
    results = []
    logs = []
    for side, argv in (
        ("old", ["bash", str(fx / TWIN_REL)]),
        ("new", ["python3", str(fx / PORT_REL)]),
    ):
        log = fx / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        flagged = fx / "fake" / "data" / "flagged"
        flagged.unlink(missing_ok=True)
        env = _env(fx, side, log, **extra)
        if fake_tool:
            bindir = fx / "fake" / ("bin-%s" % side)
            bindir.mkdir(parents=True, exist_ok=True)
            _write(bindir / "shellcheck", FAKE_SHELLCHECK, mode=0o755)
            env["PATH"] = "%s%s%s" % (bindir, os.pathsep, env["PATH"])
        if scratch_cache:
            env["CI_TEMP"] = str(fx / "cache" / side)
            env["PATH"] = "%s%s%s" % (fx / "fake" / "bin", os.pathsep, "/usr/bin:/bin")
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(fx),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

        def _mask(text: str, side: str = side) -> str:
            masked = text.replace(str(fx / "cache" / side), "<cache>").replace(str(fx), "<fx>")
            return differential.mask_toolchain_tmp(masked)

        results.append((proc.returncode, _mask(proc.stdout), _mask(proc.stderr)))
        logs.append(_mask(log.read_text(encoding="utf-8")).splitlines())
    return results[0], results[1], logs[0], logs[1]


def assert_same(old: tuple, new: tuple) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


def assert_agree(fx: pathlib.Path, **kwargs: object) -> tuple:
    """All four channels, and the call log is compared with NO sorting at all."""
    old, new, old_log, new_log = run_both(fx, **kwargs)  # type: ignore[arg-type]
    assert new_log == old_log, "call log:\n--- twin\n%s\n--- port\n%s" % (
        "\n".join(old_log),
        "\n".join(new_log),
    )
    assert_same(old, new)
    return old


# --------------------------------------------------------------------------- The real run ---------------------------------------------------------------------------


def real_hashes() -> dict[str, str]:
    """sha256 of every file the real enumerator reaches. A collapse FAILS."""
    files = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.sh"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(ROOT),
    ).stdout.split("\0")
    out = {}
    for rel in files:
        if not rel:
            continue
        path = ROOT / rel
        if path.is_file():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(out) > 400, "only %d shell files; the enumerator collapsed" % len(out)
    return out


def _run_real() -> tuple[tuple, tuple]:
    results = []
    for side, argv in (("old", ["bash", str(TWIN)]), ("new", ["python3", str(PORT)])):
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        if side == "new":
            env["PYTHONPATH"] = str(ROOT / ".ci")
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        results.append((proc.returncode, proc.stdout, proc.stderr))
    return results[0], results[1]


def test_the_real_repository_agrees_byte_for_byte() -> None:
    """620 real scripts, the real pinned shellcheck, no normalisation at all."""
    before = real_hashes()
    old, new = _run_real()
    assert_same(old, new)
    assert "info: Checking every tracked and untracked *.sh file" in old[1]
    count = len(before)
    assert ("info: %d file(s)" % count) in old[1], (
        "the twin counted something other than the %d files git lists" % count
    )
    assert real_hashes() == before, "a real run mutated a shell script"


def test_the_real_enumeration_matches_the_ports_exactly() -> None:
    """Cheap half of the case above, so a broken enumerator reds in a second."""
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)
        found = port.shell_files()
    finally:
        os.chdir(cwd)
    assert sorted(real_hashes()) == [f for f in found if (ROOT / f).is_file()]
    assert len(found) > 400


# --------------------------------------------------------------------------- Fixture runs ---------------------------------------------------------------------------


def test_a_clean_fixture_passes_and_batches_once(fixture: pathlib.Path) -> None:
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "info: Checking shell script compatibility" in old[1]
    assert "success: Shell scripts passed" in old[1]


def test_the_batch_size_is_forty(fixture: pathlib.Path) -> None:
    """`xargs -n 40`. The boundaries are OBSERVABLE in the real tool's output.

    45 scripts on top of the fixture's own, so the last batch is a short one and a port that chunked by 50 would show one invocation where there are two.
    """
    for i in range(45):
        _write(fixture / "scripts" / ("gen%02d.sh" % i), TRIVIAL_SH)
    _git(fixture, "add", "-A")
    _git(fixture, "commit", "-qm", "more")
    _old, _new, old_log, new_log = run_both(fixture)
    assert new_log == old_log
    sizes = [int(line.split()[1]) for line in old_log if line.startswith("FAKEBATCH ")]
    assert sizes, "the fake shellcheck was never called"
    assert all(size <= 40 for size in sizes), sizes
    assert sizes[:-1] == [40] * (len(sizes) - 1), "a non-final batch was not full: %s" % sizes
    assert len(sizes) >= 2, "only one batch; the chunking is untested"


def test_findings_exit_1_after_every_batch_has_run(fixture: pathlib.Path) -> None:
    """xargs runs ALL batches and only then reports 123; so does the port."""
    for i in range(45):
        _write(fixture / "scripts" / ("gen%02d.sh" % i), TRIVIAL_SH)
    _git(fixture, "add", "-A")
    _git(fixture, "commit", "-qm", "more")
    old = assert_agree(fixture, FAKE_FLAG_ON="gen00.sh")
    assert old[0] == 1
    assert "error: shellcheck reported findings" in old[2]
    assert "SC2086" in old[1]


def test_a_tracked_file_deleted_in_the_working_tree_is_skipped(
    fixture: pathlib.Path,
) -> None:
    """`rm` without `git rm` leaves it in the index; shellcheck would die on it.

    The deleted file is deliberately NOT the last one in sorted order -- that
    case is the defect below, and mixing the two would let a green here mean
    either thing.
    """
    _write(fixture / "zz-last.sh", TRIVIAL_SH)
    _git(fixture, "add", "-A")
    _git(fixture, "commit", "-qm", "tail")
    (fixture / "run.sh").unlink()
    old = assert_agree(fixture)
    assert old[0] == 0
    assert "info: skipping 1 tracked file(s) deleted in the working tree: run.sh" in old[1]
    argv = [line for line in old[1].split("\n") if line.startswith("FAKECALL")]
    assert not any(" run.sh" in line for line in argv), argv


def test_two_deleted_files_are_listed_space_separated(fixture: pathlib.Path) -> None:
    """`tr '\\n' ' '` with no trailing space, and the count from `wc -l`."""
    _write(fixture / "zz-last.sh", TRIVIAL_SH)
    _write(fixture / "scripts" / "two.sh", TRIVIAL_SH)
    _git(fixture, "add", "-A")
    _git(fixture, "commit", "-qm", "two")
    (fixture / "scripts" / "one.sh").unlink()
    (fixture / "scripts" / "two.sh").unlink()
    old = assert_agree(fixture)
    assert old[0] == 0
    assert (
        "info: skipping 2 tracked file(s) deleted in the working tree: "
        "scripts/one.sh scripts/two.sh" in old[1]
    )


def test_deleting_the_last_sorted_file_kills_the_gate(fixture: pathlib.Path) -> None:
    """THE SECOND DEFECT, reproduced on both sides. See the port's docstring.

    `scripts/one.sh` sorts last in this fixture. Deleting it makes the twin print its "skipping" line and then die at the FILTERING assignment, with exit 1 and not one file linted. Exit 1 is also "shellcheck reported findings", so the CI reader is told the tree is dirty when it was never read.
    """
    files = sorted(_git(fixture, "ls-files", "*.sh").split())
    assert files[-1] == "scripts/one.sh", files
    (fixture / "scripts" / "one.sh").unlink()
    old, _new, old_log, new_log = run_both(fixture)
    assert old[0] == 1, "the twin no longer dies here: %r" % (old,)
    assert new_log == old_log == [], "shellcheck must never have run"
    assert "info: skipping 1 tracked file(s)" in old[1]
    assert "error:" not in old[2], "and it dies with NO explanation: %r" % old[2]
    assert_same(old, run_both(fixture)[1])


def test_a_path_with_a_space_is_the_one_named_divergence(fixture: pathlib.Path) -> None:
    """NOT a reproduction. xargs re-splits the path; this port does not.

    Written down as a disagreement rather than hidden, because the twin's behaviour is plainly wrong and re-deriving xargs' quoting rules to be wrong in the same way would be a worse port. No such path exists in this tree today; the day one does, the difference is already documented and tested.
    """
    _write(fixture / "scripts" / "has space.sh", TRIVIAL_SH)
    _write(fixture / "zz-last.sh", TRIVIAL_SH)
    _git(fixture, "add", "-A")
    _git(fixture, "commit", "-qm", "space")
    _old, _new, old_log, new_log = run_both(fixture)
    # THE LOG LINE ITSELF CANNOT SHOW THIS, and that is worth stating: the fake records `"$*"`, which re-joins its argv with spaces, so a path split into two arguments prints identically to one that was not. The COUNT is what sees it, which is exactly why the fake records a count as well as a line.
    twin_count = [int(x.split()[1]) for x in old_log if x.startswith("FAKEBATCH ")]
    port_count = [int(x.split()[1]) for x in new_log if x.startswith("FAKEBATCH ")]
    assert twin_count, old_log
    assert port_count, new_log
    assert sum(twin_count) == sum(port_count) + 1, (
        "xargs stopped re-splitting (%s vs %s); this divergence is gone and the "
        "note in shellcheck.py should be deleted" % (twin_count, port_count)
    )


def test_an_untracked_script_is_still_checked(fixture: pathlib.Path) -> None:
    """`--others --exclude-standard`: a new gate test is covered before commit."""
    _write(fixture / "scripts" / "brand-new.sh", TRIVIAL_SH)
    _old, _new, old_log, new_log = run_both(fixture)
    assert new_log == old_log
    assert any("scripts/brand-new.sh" in line for line in old_log), old_log


def test_a_gitignored_script_is_not_checked(fixture: pathlib.Path) -> None:
    """The other half of `--exclude-standard`: node_modules must stay out."""
    _write(fixture / ".gitignore", "ignored/\n")
    _write(fixture / "ignored" / "vendor.sh", TRIVIAL_SH)
    _old, _new, old_log, new_log = run_both(fixture)
    assert new_log == old_log
    assert not any("vendor.sh" in line for line in old_log), old_log


def test_the_empty_corpus_refusal_is_reachable(tmp_path: pathlib.Path) -> None:
    """A work tree with the two implementations and NOTHING else tracked.

    Built by hand rather than from the shared fixture because the only way to reach an empty `git ls-files '*.sh'` is for the twins themselves to be invisible to it, and the twin resolves its root from its own location. So the twins live inside the tree and `.gitignore` hides them: `git ls-files` lists no tracked `.sh`, and `--others --exclude-standard` honours the ignore.
    """
    fx = tmp_path / "empty"
    fx.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(fx)], check=True, capture_output=True, text=True
    )
    for rel in COPIED:
        dest = fx / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    _write(fx / ".gitignore", ".ci/\n")
    _git(fx, "add", ".gitignore")
    _git(fx, "commit", "-qm", "only the ignore file")

    data = fx / "fake" / "data"
    data.mkdir(parents=True, exist_ok=True)
    bindir = fx / "fake" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    _write(bindir / "shellcheck", FAKE_SHELLCHECK, mode=0o755)

    results = []
    logs = []
    for side, argv in (
        ("old", ["bash", str(fx / TWIN_REL)]),
        ("new", ["python3", str(fx / PORT_REL)]),
    ):
        log = fx / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        env["PATH"] = "%s%s%s" % (bindir, os.pathsep, env["PATH"])
        env["FAKE_LOG"] = str(log)
        env["FAKE_DATA"] = str(data)
        env["FAKE_VERSION"] = pin()
        if side == "new":
            env["PYTHONPATH"] = str(fx / ".ci")
        proc = subprocess.run(
            argv, env=env, cwd=str(fx), capture_output=True, text=True, check=False, timeout=120
        )
        results.append(
            (
                proc.returncode,
                proc.stdout.replace(str(fx), "<fx>"),
                proc.stderr.replace(str(fx), "<fx>"),
            )
        )
        logs.append(log.read_text(encoding="utf-8").splitlines())
    assert logs[1] == logs[0] == [], "shellcheck must not run over an empty list"
    assert_same(results[0], results[1])
    assert results[0][0] == 1
    assert (
        "error: no tracked *.sh files found: the enumerator is broken, not the tree clean"
        in results[0][2]
    )


def test_an_unacquirable_shellcheck_is_exit_1_with_both_hints(fixture: pathlib.Path) -> None:
    old = assert_agree(fixture, fake_tool=False, scratch_cache=True)
    assert old[0] == 1
    assert "error: shellcheck is unusable for this gate" in old[2]
    assert "toolchain: could not download shellcheck from" in old[2]
    assert "Every lane's toolchain:" in old[1]


# --------------------------------------------------------------------------- The bash-4 block ---------------------------------------------------------------------------


def _build(fx: pathlib.Path, body: str) -> None:
    _write(fx / ".ci" / "scripts" / "build" / "b.sh", body)
    _git(fx, "add", "-A")
    _git(fx, "commit", "-qm", "build script")


def test_all_four_bash4_constructs_are_reported_in_order(fixture: pathlib.Path) -> None:
    """One file, all four probes, so the report's own section order is pinned."""
    _build(
        fixture,
        "#!/bin/bash\ndeclare -A m\nfoo |& bar\ncoproc p { echo hi; }\nmapfile -t a < f\n",
    )
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "Found bash 4+ features in build scripts" in old[2]
    sections = [
        "declare -A (associative arrays require bash 4.0+):",
        "|& (pipe stderr requires bash 4.0+):",
        "coproc (requires bash 4.0+):",
        "mapfile/readarray (requires bash 4.0+):",
    ]
    positions = [old[1].index(s) for s in sections]
    assert positions == sorted(positions), "the four sections came out in another order"
    assert "macOS ships with bash 3.2 due to GPLv3 licensing." in old[1]


def test_a_commented_mapfile_is_not_reported_but_a_commented_declare_is(
    fixture: pathlib.Path,
) -> None:
    """`^[^#]*` guards one pattern and not the other. Both directions."""
    _build(fixture, "#!/bin/bash\n# mapfile -t a < f\n# declare -A m\n")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "# declare -A m" in old[1]
    assert "mapfile -t a" not in old[1]


def test_a_word_boundary_keeps_coprocess_out(fixture: pathlib.Path) -> None:
    """`grep -w`. A port using a bare substring test would flag this line."""
    _build(fixture, "#!/bin/bash\ncoprocess=1\nreadarrayx=2\n")
    old = assert_agree(fixture)
    assert old[0] == 0, "a word-boundary miss became a finding:\n%s" % old[1]
    assert "success: Shell scripts passed" in old[1]


def test_echo_e_mangles_a_backslash_in_a_matched_line(fixture: pathlib.Path) -> None:
    """THE DEFECT, both sides. `echo -e` re-expands the SOURCE line's escapes.

    The matched line contains a literal backslash-n; the report shows a real newline in the middle of the finding, so the `path:line:` prefix and the rest of the source line end up on different lines of the output.
    """
    _build(fixture, "#!/bin/bash\ndeclare -A m # printf 'a\\nb'\n")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "declare -A m # printf 'a" in old[1]
    assert "\\n" not in old[1], "the backslash survived; the defect is gone"
    assert "\nb'" in old[1], "the escape was not expanded into a real newline"


def test_echo_e_backslash_c_truncates_the_whole_report(fixture: pathlib.Path) -> None:
    """The worst of the four: every finding after a `\\c` silently disappears.

    The `declare -A` section comes first and carries the `\\c`; the `coproc` section that follows it is found, assembled, and then thrown away by `echo -e`. So the operator is told about one construct and not the other,
    with nothing indicating that anything was dropped.
    """
    _build(fixture, "#!/bin/bash\ndeclare -A m # \\c\ncoproc p { echo hi; }\n")
    old = assert_agree(fixture)
    assert old[0] == 1
    assert "declare -A (associative arrays require bash 4.0+):" in old[1]
    assert "coproc (requires bash 4.0+):" not in old[1], (
        "the truncation defect is gone; rewrite this case"
    )


# --------------------------------------------------------------------------- Colour ---------------------------------------------------------------------------


def test_colour_is_on_off_a_tty_because_this_twin_never_tests_one(
    fixture: pathlib.Path,
) -> None:
    old, new, _ol, _nl = run_both(fixture)
    assert differential.escape_bytes(old[1]) > 0, "the twin stopped colouring off a tty"
    assert_same(old, new)


def test_ci_true_disables_colour_on_both_sides(fixture: pathlib.Path) -> None:
    old, new, _ol, _nl = run_both(fixture, CI="true")
    assert differential.escape_bytes(old[1]) == 0
    assert differential.escape_bytes(new[1]) == 0
    assert_same(old, new)


# --------------------------------------------------------------------------- The pure helpers ---------------------------------------------------------------------------


def test_batches_are_forty_wide_and_lose_nothing() -> None:
    items = ["f%03d" % i for i in range(85)]
    chunks = port.batches(items)
    assert [len(c) for c in chunks] == [40, 40, 5]
    assert [x for c in chunks for x in c] == items
    assert port.batches([]) == []


def test_echo_e_expands_the_separators_and_stops_at_backslash_c() -> None:
    assert port.echo_e("a\\nb") == "a\nb\n"
    assert port.echo_e("a\\tb") == "a\tb\n"
    assert port.echo_e("a\\\\b") == "a\\b\n"
    assert port.echo_e("a\\cb") == "a", "no trailing newline after \\c either"
    assert port.echo_e("a\\qb") == "a\\qb\n", "an unknown escape is left alone"
    assert port.echo_e("\\x41") == "A\n"
    assert port.echo_e("\\0101") == "A\n"


def test_echo_e_agrees_with_bash_on_every_case_above() -> None:
    """The assertion above is only worth as much as BASH agreeing with it.

    Drives the real `echo -e` for each case, so the unescaper is pinned to the behaviour it is reproducing rather than to one reading of the manual.
    """
    for text in ("a\\nb", "a\\tb", "a\\\\b", "a\\cb", "a\\qb", "\\x41", "\\0101"):
        rc, out, _err = differential.bash_streams(
            "echo -e %s" % _sq(text), env=differential.env_for(), cwd=str(ROOT)
        )
        assert rc == 0
        assert out == port.echo_e(text), "bash %r -> %r, port -> %r" % (
            text,
            out,
            port.echo_e(text),
        )


def _sq(text: str) -> str:
    return "'%s'" % text.replace("'", "'\\''")


def test_missing_files_follows_symlinks_like_dash_e(tmp_path: pathlib.Path) -> None:
    """`[ -e ]` follows, so a dangling symlink counts as MISSING."""
    (tmp_path / "real.sh").write_text("", encoding="utf-8")
    (tmp_path / "dangling.sh").symlink_to(tmp_path / "gone.sh")
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert port.missing_files(["real.sh", "dangling.sh", "absent.sh"]) == [
            "dangling.sh",
            "absent.sh",
        ]
    finally:
        os.chdir(cwd)


def test_the_flags_and_the_batch_size_are_the_twins() -> None:
    twin = TWIN.read_text(encoding="utf-8")
    assert 'SHELLCHECK_OPTS="-e SC1090 -e SC1091 -e SC2034 -S warning"' in twin
    assert port.SHELLCHECK_OPTS == ("-e", "SC1090", "-e", "SC1091", "-e", "SC2034", "-S", "warning")
    assert "xargs -r -n 40 -P1" in twin
    assert port.BATCH == 40
    assert ".ci/scripts/build" in twin
    assert port.BUILD_DIR == ".ci/scripts/build"


def test_colours_reads_ci_at_the_call_site(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert port.colours() == (port.RED, port.GREEN, port.NC)
    monkeypatch.setenv("CI", "true")
    assert port.colours() == ("", "", "")
    monkeypatch.setenv("CI", "1")
    assert port.colours() == (port.RED, port.GREEN, port.NC), "only the exact string 'true'"
