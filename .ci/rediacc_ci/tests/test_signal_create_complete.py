"""`rediacc_ci.ci_signal.create_complete`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/signal/create-complete.sh` and the port over the same arguments and compared the whole `(exit, stdout, stderr)` tuple plus the BYTES OF BOTH FILES the script writes; a port that logged the right line and wrote the wrong file would pass a stdout-only comparison. The K=5 ledger
`.ci/shadow/w7p6-create-complete.observations.jsonl` recorded that comparison over five distinct trees, against a disposable scratch git repo outside this checkout. The twin has now been deleted, and every case compares against `goldens/create-complete/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree; the provenance header carries its blob
sha, so `git cat-file -p <sha>` still yields the program that produced them.

BYTE-IDENTICAL IS STILL THE ASSERTION. The twin's two messages are literal strings with no timestamp, pid or tmp path in them except the output path itself, which the case supplies. The recorded shape therefore carries a third section, `--- files ---`, holding the JSON of what landed in the output directory and in the decoy directory beside it. Two of the seven writing cases
exist only to prove the decoy stayed empty, and a recording that dropped it would have frozen half of what the differential compared.

WHAT IS NORMALISED, and it is two paths. The output directory and the decoy are named verbatim in stderr and in the recorded file map, and a recording is compared against directories built under a different tempdir name months later, so they become `<outdir>` and `<decoy>`. Nothing else is touched: the glyph, the escape sequences of the two terminal cases and the exact
wording are all compared as recorded.

ONE CASE IS COMPARED BY SHAPE, and it has to be. `mkdir -p` over an existing regular file dies under `set -e` and the port raises OSError: same exit code, same stream, different wording, and the twin's was the WEAKER of the two on the recording host, where `/usr/bin/mkdir` is uutils and prints a bare `mkdir: Already exists` naming no path at all. The port names the path
unconditionally, so that half is asserted directly rather than left to whichever mkdir is installed.
"""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

SLUG = "create-complete"
MODULE = "rediacc_ci.ci_signal.create_complete"

PLACEHOLDER = "<outdir>"
DECOY = "<decoy>"
FILES_MARKER = "--- files ---\n"

# name -> how the run is wired. `use_flag` passes `--output`; `deep` puts the output directory under two components that do not exist yet; `blocked` makes the output path an existing regular file.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-missing-name": {"args": [], "use_flag": False},
    "an-empty-name-value": {"args": ["--name="], "use_flag": False},
    "the-happy-path": {"args": ["--name", "cli-Linux"]},
    "a-failure-status": {"args": ["--name", "e2e-ceph", "--status", "failure"]},
    "a-nested-output-directory": {"args": ["--name", "nested"], "deep": True},
    "runner-temp-is-preferred-over-tmpdir": {
        "args": ["--name", "from-runner-temp"],
        "use_flag": False,
        "env_extra": {"RUNNER_TEMP": PLACEHOLDER, "TMPDIR": DECOY},
    },
    "tmpdir-when-runner-temp-is-empty": {
        "args": ["--name", "from-tmpdir"],
        "use_flag": False,
        "env_extra": {"RUNNER_TEMP": "", "TMPDIR": PLACEHOLDER},
    },
    "a-flag-valued-name": {"args": ["--name", "--status", "failure"]},
    "a-positional-argument": {"args": ["cli-Linux"], "use_flag": False},
    "colour-on-a-terminal": {"args": ["--name", "tty-case"], "tty": "stderr"},
    "no-colour-on-a-terminal": {
        "args": ["--name", "tty-case"],
        "env_extra": {"NO_COLOR": "1"},
        "tty": "stderr",
    },
    "an-unwritable-output-directory": {"args": ["--name", "x"], "blocked": True},
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte. Compared by shape, in its own test.
DIVERGENT = ("an-unwritable-output-directory",)


def places(tmp_path: pathlib.Path, name: str) -> tuple[pathlib.Path, pathlib.Path]:
    """This case's output directory and its decoy, neither of them created here."""
    kw = CASE_KW[name]
    out = tmp_path / "a" / "b" / "out" if kw.get("deep") else tmp_path / "out"
    return out, tmp_path / "decoy"


def tree(directory: pathlib.Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.iterdir())}


def command(subject: str, name: str, out: pathlib.Path) -> str:
    kw = CASE_KW[name]
    parts = list(kw["args"])
    if kw.get("use_flag", True):
        parts = ["--output", str(out), *parts]
    return "%s %s" % (subject, " ".join("'%s'" % p for p in parts))


def environment(name: str, out: pathlib.Path, decoy: pathlib.Path) -> dict[str, str]:
    """This case's environment, with the two placeholders resolved to real paths.

    `RUNNER_TEMP` is REMOVED rather than emptied by default: `CI_TEMP` reads it with `[[ -n ... ]]`, which distinguishes unset from empty, and one case exists to drive exactly that distinction.
    """
    extra = dict(CASE_KW[name].get("env_extra") or {})
    extra.setdefault("RUNNER_TEMP", None)
    extra.setdefault("TMPDIR", DECOY)
    extra.setdefault("PYTHONPATH", ".ci")
    extra.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    resolved = {
        key: None
        if value is None
        else value.replace(PLACEHOLDER, str(out)).replace(DECOY, str(decoy))
        for key, value in extra.items()
    }
    return diff.env_for(**resolved)


def mask(text: str, out: pathlib.Path, decoy: pathlib.Path) -> str:
    return text.replace(str(out), PLACEHOLDER).replace(str(decoy), DECOY)


def run(tmp_path: pathlib.Path, name: str, *, subject: str) -> tuple[int, str, str, str]:
    """One side, once, over this case's own directories. Returns the recorded shape's four parts."""
    kw = CASE_KW[name]
    out, decoy = places(tmp_path, name)
    decoy.mkdir(parents=True, exist_ok=True)
    if kw.get("blocked"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("not a directory\n", encoding="utf-8")
    code, stdout, stderr = diff.bash_streams(
        command(subject, name, out),
        env=environment(name, out, decoy),
        tty=kw.get("tty"),
        timeout=30,
    )
    files = json.dumps({"out": tree(out), "decoy": tree(decoy)}, indent=2, sort_keys=True)
    return (
        code,
        mask(stdout, out, decoy),
        mask(stderr, out, decoy),
        mask(files, out, decoy),
    )


def render(code: int, stdout: str, stderr: str, files: str) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), FILES_MARKER, files)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, files = rest.split(FILES_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, files.rstrip("\n")


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(tmp_path, name, subject="python3 -m %s" % MODULE)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the files diverged: %s vs %s" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_missing_name_refuses_and_writes_nothing() -> None:
    code, stdout, stderr, files = recorded("a-missing-name")
    assert code == 1
    assert stdout == ""
    assert stderr == (
        "✗ Usage: create-complete.sh --name <signal_name> [--output <dir>] [--status <status>]\n"
    )
    assert json.loads(files) == {"out": {}, "decoy": {}}


def test_an_empty_name_value_is_treated_as_absent() -> None:
    """`--name=` sets ARG_NAME to the empty string, and `${ARG_NAME:-}` then reads as unset. A port using `.get(key, default)` instead of `or` would happily write `complete-.txt`, so this case is the one that catches it."""
    code, _, stderr, files = recorded("an-empty-name-value")
    assert code == 1
    assert "Usage: create-complete.sh" in stderr
    assert json.loads(files) == {"out": {}, "decoy": {}}


def test_the_happy_path_writes_both_files() -> None:
    code, stdout, stderr, files = recorded("the-happy-path")
    assert (code, stdout) == (0, "")
    assert stderr == (
        "✓ Created completion signal: %s/complete-cli-Linux.txt (status: success)\n" % PLACEHOLDER
    )
    assert json.loads(files)["out"] == {
        "complete-cli-Linux.txt": "success\n",
        "complete.txt": "success\n",
    }


def test_the_status_flag_reaches_both_files() -> None:
    code, _, stderr, files = recorded("a-failure-status")
    assert code == 0
    assert "(status: failure)" in stderr
    assert json.loads(files)["out"] == {
        "complete-e2e-ceph.txt": "failure\n",
        "complete.txt": "failure\n",
    }


def test_the_output_directory_is_created_recursively() -> None:
    """`mkdir -p` makes intermediate components; `Path.mkdir(parents=True)` is the only spelling that agrees, and `exist_ok` is the other half of `-p`."""
    code, _, _, files = recorded("a-nested-output-directory")
    assert code == 0
    assert json.loads(files)["out"] == {
        "complete-nested.txt": "success\n",
        "complete.txt": "success\n",
    }


def test_runner_temp_is_preferred_over_tmpdir() -> None:
    """`CI_TEMP` is `get_temp_dir()`: RUNNER_TEMP, else TMPDIR, else /tmp. The fallback ORDER is the part a port gets wrong, so both variables are set and only one of them may be written into."""
    code, _, stderr, files = recorded("runner-temp-is-preferred-over-tmpdir")
    assert code == 0
    assert stderr == (
        "✓ Created completion signal: %s/complete-from-runner-temp.txt (status: success)\n"
        % PLACEHOLDER
    )
    assert json.loads(files) == {
        "out": {"complete-from-runner-temp.txt": "success\n", "complete.txt": "success\n"},
        "decoy": {},
    }


def test_tmpdir_is_used_when_runner_temp_is_empty() -> None:
    """`[[ -n "${RUNNER_TEMP:-}" ]]` is a NON-EMPTY test, so `RUNNER_TEMP=` falls through to TMPDIR rather than resolving to the empty string."""
    code, _, stderr, files = recorded("tmpdir-when-runner-temp-is-empty")
    assert code == 0
    assert "%s/complete-from-tmpdir.txt" % PLACEHOLDER in stderr
    assert json.loads(files)["out"] == {
        "complete-from-tmpdir.txt": "success\n",
        "complete.txt": "success\n",
    }


def test_a_flag_valued_name_reproduces_the_parse_args_quirk() -> None:
    """`--name --status failure` does NOT mean "name is --status". parse_args refuses to consume a token beginning with `--` as a value, so ARG_NAME becomes the literal string `true` and the signal file is `complete-true.txt`. Surprising, live in the twin, and therefore required of the port."""
    code, _, stderr, files = recorded("a-flag-valued-name")
    assert code == 0
    assert "complete-true.txt (status: failure)" in stderr
    assert json.loads(files)["out"] == {
        "complete-true.txt": "failure\n",
        "complete.txt": "failure\n",
    }


def test_positional_arguments_are_invisible_to_the_parser() -> None:
    """parse_args skips anything not starting with `--`, so a caller who wrote `create-complete.sh cli-Linux` gets the usage refusal, not a signal file."""
    code, _, stderr, files = recorded("a-positional-argument")
    assert code == 1
    assert "Usage: create-complete.sh" in stderr
    assert json.loads(files) == {"out": {}, "decoy": {}}


def test_colour_is_recorded_on_a_terminal_and_suppressed_by_no_color() -> None:
    """The branch a developer actually sees. Off a tty the glyph is bare; on one it carries the escape sequence, and `NO_COLOR` takes it away again."""
    coloured = recorded("colour-on-a-terminal")[2]
    assert "\033[0;32m✓\033[0m Created completion signal:" in coloured
    assert diff.escape_bytes(coloured) == 2
    assert diff.escape_bytes(recorded("no-colour-on-a-terminal")[2]) == 0


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_an_unwritable_output_directory(tmp_path: pathlib.Path) -> None:
    """Both sides refuse loudly over an output path that is a regular file. Only the wording is allowed to differ, so the assertion is on the code, the stream and the path being named."""
    name = "an-unwritable-output-directory"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""
    assert want[2].strip() != "", "the twin's refusal was recorded silent"
    assert PLACEHOLDER in got[2], "the port did not name the path it could not write"
    assert json.loads(got[3]) == json.loads(want[3]) == {"out": {}, "decoy": {}}


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_drop_of_the_generic_file_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Stop writing the generic `complete.txt`.

    That second file is the whole reason a waiter can poll one name it knows in advance, and the port's last statement is the only thing that writes it. Dropping it changes nothing on either stream, so a comparison of the streams alone would stay green; the `--- files ---` section is what sees it. The mutant is a throwaway copy run as a plain script, resolving
    `rediacc_ci` through `PYTHONPATH` exactly as the module spelling does, and the tracked port is never touched.
    """
    source = paths.from_root(".ci", "rediacc_ci", "ci_signal", "create_complete.py")
    original = source.read_text(encoding="utf-8")
    anchor = '    (out / "complete.txt").write_text(status + "\\n", encoding="utf-8")\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "")

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-happy-path"
    out, decoy = places(tmp_path, name)
    decoy.mkdir(parents=True, exist_ok=True)
    code, _, _ = diff.bash_streams(
        command("python3 '%s'" % mutant, name, out),
        env=environment(name, out, decoy),
        timeout=30,
    )
    assert code == 0
    assert "complete.txt" in json.loads(recorded(name)[3])["out"], "the recorded corpus moved"
    assert "complete.txt" not in tree(out), "the plant did not change what was written"
    assert "complete-cli-Linux.txt" in tree(out)

    compare(tmp_path / "good", name)
    assert source.read_text(encoding="utf-8") == original
