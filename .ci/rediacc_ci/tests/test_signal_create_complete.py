"""`rediacc_ci.ci_signal.create_complete` against its bash twin.

BYTE-IDENTICAL IS THE ASSERTION HERE, not a finding-set comparison: the twin's
two messages are literal strings with no timestamp, pid or tmp path in them
except the output path itself, and the output path is supplied by the test. So
every case below compares the whole `(exit, stdout, stderr)` tuple, plus the
BYTES OF BOTH FILES the script writes -- a port that logged the right line and
wrote the wrong file would pass a stdout-only comparison.

THE TWO SIDES GET DIFFERENT OUTPUT DIRECTORIES ON PURPOSE. Sharing one would
let the second run overwrite the first's `complete.txt` and the comparison
would then be reading the new side's file twice. `_swap` substitutes the two
directory paths out of the captured stderr so the tuples can still be compared
byte for byte.

ONE CASE USES A REAL PTY (`tty="stderr"`), because colour is decided by
`isatty` and a differential that only ever runs off a tty proves the boring
half: `common.sh:18-32` and `rediacc_ci.log.colour_allowed` are two separate
opinions about the same escape sequences, and the pty is the only way to make
either of them speak.

K=5 LEDGER: `.ci/shadow/w7p6-create-complete.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this repo's
working tree is not clean and `shadow-gate.ts --record` refuses a dirty tree).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/signal/create-complete.sh"
MODULE = "rediacc_ci.ci_signal.create_complete"

PLACEHOLDER = "<outdir>"


def _swap(text: str, outdir: str) -> str:
    return text.replace(outdir, PLACEHOLDER)


def run_both(
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    env_extra: dict[str, str] | None = None,
    tty: str | None = None,
    use_flag: bool = True,
) -> tuple[tuple[int, str, str], tuple[int, str, str], pathlib.Path, pathlib.Path]:
    """Run both sides into their own output directory. Returns both tuples and
    both directories, with the directory path masked out of the streams."""
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    extra = dict(env_extra or {})

    def side_env(target: pathlib.Path, **more: str) -> dict[str, str]:
        pinned = {k: v.replace(PLACEHOLDER, str(target)) for k, v in extra.items()}
        return diff.env_for(**pinned, **more)

    def side_args(target: pathlib.Path) -> str:
        parts = list(args)
        if use_flag:
            parts = ["--output", str(target), *parts]
        return " ".join("'%s'" % p for p in parts)

    old = diff.bash_streams(
        "bash %s %s" % (TWIN, side_args(old_dir)),
        env=side_env(old_dir),
        tty=tty,
        timeout=30,
    )
    new = diff.bash_streams(
        "python3 -m %s %s" % (MODULE, side_args(new_dir)),
        env=side_env(new_dir, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        tty=tty,
        timeout=30,
    )
    old = (old[0], _swap(old[1], str(old_dir)), _swap(old[2], str(old_dir)))
    new = (new[0], _swap(new[1], str(new_dir)), _swap(new[2], str(new_dir)))
    return old, new, old_dir, new_dir


def _tree(directory: pathlib.Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.iterdir())}


def test_missing_name_refuses_identically(tmp_path: pathlib.Path) -> None:
    old, new, old_dir, new_dir = run_both(tmp_path, [], use_flag=False)
    assert old[0] == 1
    assert old[1] == ""
    assert old[2] == (
        "✗ Usage: create-complete.sh --name <signal_name> [--output <dir>] [--status <status>]\n"
    )
    assert new == old
    # Neither side may write anything on the refusal path.
    assert _tree(old_dir) == {}
    assert _tree(new_dir) == {}


def test_empty_name_value_is_treated_as_absent(tmp_path: pathlib.Path) -> None:
    """`--name=` sets ARG_NAME to the empty string, and `${ARG_NAME:-}` then
    reads as unset. A port using `.get(key, default)` instead of `or` would
    happily write `complete-.txt`, so this case is the one that catches it."""
    old, new, old_dir, new_dir = run_both(tmp_path, ["--name="], use_flag=False)
    assert old[0] == 1
    assert "Usage: create-complete.sh" in old[2]
    assert new == old
    assert _tree(old_dir) == _tree(new_dir) == {}


def test_happy_path_is_byte_identical_and_writes_both_files(tmp_path: pathlib.Path) -> None:
    old, new, old_dir, new_dir = run_both(tmp_path, ["--name", "cli-Linux"])
    assert old == (
        0,
        "",
        "✓ Created completion signal: %s/complete-cli-Linux.txt (status: success)\n" % PLACEHOLDER,
    )
    assert new == old
    assert _tree(old_dir) == {"complete-cli-Linux.txt": "success\n", "complete.txt": "success\n"}
    assert _tree(new_dir) == _tree(old_dir)


def test_status_flag_reaches_both_files(tmp_path: pathlib.Path) -> None:
    old, new, old_dir, new_dir = run_both(tmp_path, ["--name", "e2e-ceph", "--status", "failure"])
    assert old[0] == 0
    assert "(status: failure)" in old[2]
    assert new == old
    assert _tree(old_dir) == {"complete-e2e-ceph.txt": "failure\n", "complete.txt": "failure\n"}
    assert _tree(new_dir) == _tree(old_dir)


def test_output_directory_is_created_recursively(tmp_path: pathlib.Path) -> None:
    """`mkdir -p` makes intermediate components; `Path.mkdir(parents=True)` is
    the only spelling that agrees, and `exist_ok` is the other half of `-p`."""
    deep_old = tmp_path / "a" / "b" / "old"
    deep_new = tmp_path / "a" / "b" / "new"
    o = diff.bash_streams(
        "bash %s --name nested --output '%s'" % (TWIN, deep_old), env=diff.env_for(), timeout=30
    )
    n = diff.bash_streams(
        "python3 -m %s --name nested --output '%s'" % (MODULE, deep_new),
        env=diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        timeout=30,
    )
    assert o[0] == n[0] == 0
    assert _swap(o[2], str(deep_old)) == _swap(n[2], str(deep_new))
    assert (
        _tree(deep_old)
        == _tree(deep_new)
        == {
            "complete-nested.txt": "success\n",
            "complete.txt": "success\n",
        }
    )


def test_runner_temp_is_preferred_over_tmpdir(tmp_path: pathlib.Path) -> None:
    """`CI_TEMP` is `get_temp_dir()`: RUNNER_TEMP, else TMPDIR, else /tmp. The
    fallback ORDER is the part a port gets wrong, so both variables are set and
    only one of them may be written into."""
    decoy_old = tmp_path / "decoy"
    decoy_old.mkdir()
    old, new, old_dir, new_dir = run_both(
        tmp_path,
        ["--name", "from-runner-temp"],
        env_extra={"RUNNER_TEMP": PLACEHOLDER, "TMPDIR": str(decoy_old)},
        use_flag=False,
    )
    assert old[0] == 0
    assert old[2] == (
        "✓ Created completion signal: %s/complete-from-runner-temp.txt (status: success)\n"
        % PLACEHOLDER
    )
    assert new == old
    assert (
        _tree(old_dir)
        == _tree(new_dir)
        == {
            "complete-from-runner-temp.txt": "success\n",
            "complete.txt": "success\n",
        }
    )
    assert _tree(decoy_old) == {}


def test_tmpdir_is_used_when_runner_temp_is_empty(tmp_path: pathlib.Path) -> None:
    """`[[ -n "${RUNNER_TEMP:-}" ]]` is a NON-EMPTY test, so `RUNNER_TEMP=`
    falls through to TMPDIR rather than resolving to the empty string."""
    old, new, old_dir, new_dir = run_both(
        tmp_path,
        ["--name", "from-tmpdir"],
        env_extra={"RUNNER_TEMP": "", "TMPDIR": PLACEHOLDER},
        use_flag=False,
    )
    assert old[0] == 0
    assert "%s/complete-from-tmpdir.txt" % PLACEHOLDER in old[2]
    assert new == old
    assert (
        _tree(old_dir)
        == _tree(new_dir)
        == {
            "complete-from-tmpdir.txt": "success\n",
            "complete.txt": "success\n",
        }
    )


def test_flag_valued_name_reproduces_the_parse_args_quirk(tmp_path: pathlib.Path) -> None:
    """`--name --status failure` does NOT mean "name is --status". parse_args
    refuses to consume a token beginning with `--` as a value, so ARG_NAME
    becomes the literal string `true` and the signal file is `complete-true.txt`.
    Surprising, live in the twin, and therefore required of the port."""
    old, new, old_dir, new_dir = run_both(tmp_path, ["--name", "--status", "failure"])
    assert old[0] == 0
    assert "complete-true.txt (status: failure)" in old[2]
    assert new == old
    assert _tree(old_dir) == {"complete-true.txt": "failure\n", "complete.txt": "failure\n"}
    assert _tree(new_dir) == _tree(old_dir)


def test_positional_arguments_are_invisible_to_the_parser(tmp_path: pathlib.Path) -> None:
    """parse_args skips anything not starting with `--`, so a caller who wrote
    `create-complete.sh cli-Linux` gets the usage refusal, not a signal file."""
    old, new, old_dir, new_dir = run_both(tmp_path, ["cli-Linux"], use_flag=False)
    assert old[0] == 1
    assert "Usage: create-complete.sh" in old[2]
    assert new == old
    assert _tree(old_dir) == _tree(new_dir) == {}


def test_colour_matches_when_stderr_is_a_terminal(tmp_path: pathlib.Path) -> None:
    """The branch a developer actually sees. Off a tty both sides print a bare
    `✓`; on one, both must print the SAME escape sequence around it."""
    old, new, _old_dir, _new_dir = run_both(tmp_path, ["--name", "tty-case"], tty="stderr")
    assert old[0] == 0
    assert "\033[0;32m✓\033[0m Created completion signal:" in old[2]
    assert new == old
    assert diff.escape_bytes(old[2]) == diff.escape_bytes(new[2]) == 2


def test_no_color_suppresses_the_escape_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new, _old_dir, _new_dir = run_both(
        tmp_path, ["--name", "tty-case"], env_extra={"NO_COLOR": "1"}, tty="stderr"
    )
    assert old[0] == 0
    assert diff.escape_bytes(old[2]) == 0
    assert new == old


def test_unwritable_output_directory_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """DOCUMENTED DIVERGENCE, pinned rather than papered over: `mkdir -p` over
    an existing regular file dies under `set -e`, and this port raises OSError.
    Same exit code, same stream, different wording -- so the assertion is on the
    code and on the path being named, not on the bytes."""
    blocker_old = tmp_path / "blocked-old"
    blocker_new = tmp_path / "blocked-new"
    blocker_old.write_text("not a directory\n", encoding="utf-8")
    blocker_new.write_text("not a directory\n", encoding="utf-8")
    o = diff.bash_streams(
        "bash %s --name x --output '%s'" % (TWIN, blocker_old), env=diff.env_for(), timeout=30
    )
    n = diff.bash_streams(
        "python3 -m %s --name x --output '%s'" % (MODULE, blocker_new),
        env=diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        timeout=30,
    )
    assert o[0] == 1
    assert n[0] == 1
    assert o[1] == n[1] == ""
    # Both refuse loudly. Only the wording is allowed to differ, and the twin's
    # is the WEAKER of the two on this host: uutils' `mkdir` (which `/usr/bin/mkdir`
    # symlinks to here) prints a bare `mkdir: Already exists` naming no path at all,
    # while GNU coreutils would name it. The port names it unconditionally, so that
    # half is asserted directly rather than left to whichever mkdir is installed.
    assert o[2].strip() != ""
    assert str(blocker_new) in n[2]
