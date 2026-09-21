"""`rediacc_ci.autopilot.linked_sub_prs`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/linked-sub-prs.sh` and the port over the same fixture body and compared exit code, stdout and stderr. The K=5 ledger `.ci/shadow/w7p6-linked-sub-prs.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that executed it compares against
`goldens/linked-sub-prs/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE INPUT IS BYTES, THE OUTPUT IS TEXT, and the recorder asserts that. The subject reads a PR body, which is whatever GitHub stored, and two cases feed it a NUL byte on purpose to exercise GNU grep's binary suppression. What comes BACK is repository names, numbers and diagnostics, so the two streams are recorded as UTF-8 and a case that ever printed a byte outside it would
have failed the recording rather than been silently mangled.

`--body` IS ALWAYS A RELATIVE PATH, and that is load-bearing for one case: grep's binary diagnostic named the path exactly as it was given, so an absolute path here would compare two absolute paths and never notice a port that rebuilt the string.

TWO CASES ARE COMPARED BY SHAPE RATHER THAN BYTE, and each has to be:

  * `an-invalid-owner-regex` -- an owner was interpolated into a regex by the
    twin, so an unbalanced bracket was a syntax error and the diagnostic was
    grep's. Exit code, stdout and the empty result match exactly; the port fails
    SILENTLY. Named in the port's docstring as its one known divergence.
  * `a-flag-that-is-not-an-identifier` -- `printf -v` refused a key that is not
    a shell identifier, which carried common.sh's own path and line number into
    the message.

THE NEGATIVE CONTROLS ARE THE POINT OF HALF THIS FILE. A parser that returned every number it saw would satisfy every positive case; `the-allowlist-boundary` and `near-miss-spellings` are what stop it.
"""

from __future__ import annotations

import io
import os
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import linked_sub_prs as lsp
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "linked_sub_prs.py"

SLUG = "linked-sub-prs"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

# One body carrying all three accepted spellings, a duplicate, a leading-zero twin of an existing number, an eight-digit run and a link to a repository that is NOT a submodule of this monorepo.
FULL_BODY = b"""## Linked submodule PRs

- https://github.com/rediacc/renet/pull/12
- rediacc/renet#12
- rediacc/account#7
- rediacc/account#007
- rediacc/elite/pull/12345678
- rediacc/homebrew-tap#3
- evil/renet#99
- rediacc/console#500
"""

ALLOWLIST_BODY = b"\n".join(
    [
        b"https://github.com/rediacc/console/pull/1",
        b"rediacc/website#2",
        b"attacker/renet#3",
        b"https://github.com/attacker/account/pull/4",
        b"rediacc/renet-extra#5",
        b"",
    ]
)

# Right repository, wrong shape. `http://github.com/rediacc/account/pull/9` is the exception: the optional group only matches https, but `rediacc/account/pull/9` is still a bare match inside it, so that line DOES link 9.
NEAR_MISS_BODY = b"\n".join(
    [
        b"rediacc/renet PR 12",
        b"rediacc/renet#",
        b"http://github.com/rediacc/account/pull/9",
        b"rediacc/elite/pulls/4",
        b"rediacc/homebrew-tap#x7",
        b"",
    ]
)

OWNER_BODY = b"rediacc/renet#1\nacme/renet#2\n"

# name -> (argv, how the fixture directory is built)
CASE_KW: dict[str, tuple[list[str], dict[str, typing.Any]]] = {
    "the-full-body": (["--body", "body.md"], {}),
    "the-allowlist-boundary": (["--body", "body.md"], {"body": ALLOWLIST_BODY}),
    "near-miss-spellings": (["--body", "body.md"], {"body": NEAR_MISS_BODY}),
    "a-url-spelling": (
        ["--body", "body.md"],
        {"body": b"https://github.com/rediacc/renet/pull/41\n"},
    ),
    "a-hash-spelling": (["--body", "body.md"], {"body": b"rediacc/renet#42\n"}),
    "a-path-spelling": (["--body", "body.md"], {"body": b"rediacc/renet/pull/43\n"}),
    "an-equal-run-with-7-first": (
        ["--body", "b.md"],
        {"body": b"rediacc/renet#7\nrediacc/renet#007\n", "body_name": "b.md"},
    ),
    "an-equal-run-with-007-first": (
        ["--body", "b.md"],
        {"body": b"rediacc/renet#007\nrediacc/renet#7\n", "body_name": "b.md"},
    ),
    "a-nul-byte-with-links": (
        ["--body", "body.md"],
        {"body": b"rediacc/renet#12\x00rediacc/account#13\n"},
    ),
    "a-nul-byte-without-links": (["--body", "body.md"], {"body": b"nothing\x00here\n"}),
    "an-empty-body": (["--body", "body.md"], {"body": b""}),
    "a-body-of-prose": (
        ["--body", "body.md"],
        {"body": b"just some prose\nwith no links\n"},
    ),
    "no-body-flag": ([], {}),
    "an-empty-body-flag": (["--body="], {}),
    "a-missing-body-file": (["--body", "nope.md"], {}),
    "a-directory-as-the-body": (["--body", "adir"], {"directory": "adir"}),
    "an-explicit-owner": (["--body", "body.md", "--owner", "acme"], {"body": OWNER_BODY}),
    "an-empty-owner": (["--body", "body.md", "--owner="], {"body": OWNER_BODY}),
    "an-invalid-owner-regex": (["--body", "body.md", "--owner", "redi(acc"], {}),
    "a-flag-that-is-not-an-identifier": (["--a.b", "x", "--body", "body.md"], {}),
    "a-positional-body-path": (["body.md"], {}),
}

CASES = tuple(CASE_KW)

# The two cases the port does not reproduce byte for byte. Each is compared by shape, in its own test.
DIVERGENT = ("an-invalid-owner-regex", "a-flag-that-is-not-an-identifier")


def fixture(
    base: pathlib.Path,
    *,
    body: bytes | None = FULL_BODY,
    body_name: str = "body.md",
    directory: str | None = None,
) -> pathlib.Path:
    """A fresh directory holding this case's body.

    A FRESH DIRECTORY PER RUN even though this subject writes nothing: the cheapest way to be sure it stays that way is never to give the next run the previous one's leftovers.
    """
    base.mkdir(parents=True, exist_ok=True)
    if directory is not None:
        (base / directory).mkdir(exist_ok=True)
    elif body is not None:
        (base / body_name).write_bytes(body)
    return base


def run(where: pathlib.Path, subject: pathlib.Path, name: str) -> tuple[int, bytes, bytes]:
    """One side, once, over its own copy of this case's fixture."""
    argv, kw = CASE_KW[name]
    base = fixture(where, **kw)
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(subject), *argv],
        capture_output=True,
        env=BASE_ENV,
        check=False,
        cwd=str(base),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def render(returncode: int, stdout: bytes, stderr: bytes) -> str:
    return frozen.render(returncode, stdout.decode("utf-8"), stderr.decode("utf-8"))


def recorded(name: str) -> tuple[int, bytes, bytes]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout.encode("utf-8"),
        stderr.encode("utf-8"),
    )


def drive(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path = PORT):
    return run(tmp_path / name, subject, name)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, bytes, bytes]:
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_full_body() -> None:
    """All three spellings, the allowlist, the dedup and the truncation at once."""
    returncode, stdout, stderr = recorded("the-full-body")
    assert returncode == 0
    assert stderr == b""
    assert stdout == (
        b"rediacc/renet 12\nrediacc/account 7\nrediacc/elite 1234567\nrediacc/homebrew-tap 3\n"
    ), stdout


def test_the_allowlist_is_the_boundary() -> None:
    """NEGATIVE CONTROL. A body that links only non-submodules prints nothing and exits 0, which is the twin's documented quiet-empty result."""
    assert recorded("the-allowlist-boundary") == (0, b"", b"")


def test_near_miss_spellings_are_not_links() -> None:
    """NEGATIVE CONTROL for the SPELLING half: right repository, wrong shape."""
    returncode, stdout, _ = recorded("near-miss-spellings")
    assert returncode == 0
    assert stdout == b"rediacc/account 9\n", stdout


def test_every_spelling_alone() -> None:
    """Each accepted spelling on its own, so a regression in one is not hidden by another matching the same number."""
    for name, want in (
        ("a-url-spelling", b"rediacc/renet 41\n"),
        ("a-hash-spelling", b"rediacc/renet 42\n"),
        ("a-path-spelling", b"rediacc/renet 43\n"),
    ):
        assert recorded(name)[1] == want, name


def test_numeric_dedup_keeps_the_first_of_an_equal_run() -> None:
    """`sort -un` read `007` and `7` as ONE PR. Which STRING survived depended on input order, and both orders are recorded because a port that sorted lexicographically would agree with one of them by accident."""
    assert recorded("an-equal-run-with-7-first")[1] == b"rediacc/renet 7\n"
    assert recorded("an-equal-run-with-007-first")[1] == b"rediacc/renet 007\n"


def test_a_nul_byte_makes_the_body_binary() -> None:
    """GNU grep suppressed every match, said so on stderr, and exited 0.

    Recorded rather than smoothed over: the result is an EMPTY link list, which is indistinguishable from a body with no links unless the diagnostic survives.
    """
    returncode, stdout, stderr = recorded("a-nul-byte-with-links")
    assert returncode == 0
    assert stdout == b""
    assert stderr == (
        b"grep: body.md: binary file matches\ngrep: body.md: binary file matches\n"
    ), stderr


def test_a_nul_byte_with_no_link_is_silent() -> None:
    """The other half of the case above: grep only announced a binary file it MATCHED, so a binary body with no links produced no diagnostic at all."""
    assert recorded("a-nul-byte-without-links") == (0, b"", b"")


def test_empty_and_linkless_bodies() -> None:
    for name in ("an-empty-body", "a-body-of-prose"):
        assert recorded(name) == (0, b"", b""), name


def test_usage_refusals() -> None:
    """`--body` absent, and `--body=` present but empty. Both exit 2."""
    returncode, _, stderr = recorded("no-body-flag")
    assert returncode == 2
    assert b"usage: linked-sub-prs.sh --body <file>" in stderr
    assert recorded("an-empty-body-flag")[0] == 2


def test_a_missing_or_unusable_body_refuses() -> None:
    """A DIRECTORY is not a regular file, so `-f` refused it too."""
    returncode, _, stderr = recorded("a-missing-body-file")
    assert returncode == 1
    assert b"Required file 'nope.md' does not exist" in stderr
    returncode, _, stderr = recorded("a-directory-as-the-body")
    assert returncode == 1
    assert b"Required file 'adir' does not exist" in stderr


def test_the_owner_is_a_parameter() -> None:
    """`--owner` changed which links counted, and an EMPTY one fell back to `rediacc` (`${ARG_OWNER:-rediacc}`, not `${ARG_OWNER-rediacc}`)."""
    assert recorded("an-explicit-owner")[1] == b"acme/renet 2\n"
    assert recorded("an-empty-owner")[1] == b"rediacc/renet 1\n"


def test_positional_arguments_are_invisible() -> None:
    """`parse_args` skipped anything not starting with `--`, so a positional body path was NOT a body path and the script refused for want of `--body`."""
    returncode, _, stderr = recorded("a-positional-body-path")
    assert returncode == 2
    assert b"usage: linked-sub-prs.sh" in stderr


# --------------------------------------------------------------------------- The two recorded divergences ---------------------------------------------------------------------------


def test_divergence_an_owner_that_is_not_valid_regex(tmp_path: pathlib.Path) -> None:
    """The port's one known divergence, pinned so a later "fix" turns it red.

    Both sides find nothing and exit 0; only the diagnostic differs (grep's versus none, and the twin emitted one per submodule).
    """
    name = "an-invalid-owner-regex"
    want_exit, want_out, want_err = recorded(name)
    returncode, stdout, stderr = drive(tmp_path, name)
    assert want_exit == returncode == 0
    assert want_out == stdout == b""
    assert b"Unmatched" in want_err, want_err
    assert stderr == b"", "the port must fail SILENTLY here, not refuse: %r" % stderr


def test_divergence_a_flag_that_is_not_a_shell_identifier(tmp_path: pathlib.Path) -> None:
    """`parse_args` QUIRK 3. Exit 2 on both; the twin's text carried common.sh's own path and line number, so only the shape is compared.

    THE FLAG HAS TO CARRY A CHARACTER THE PREFIX CANNOT RESCUE. `--1bad` looks like the obvious specimen and is not one: the key becomes `ARG_1BAD`, which starts with a letter and is a perfectly good shell identifier, so both sides parse it happily and exit 0. Driven, and it cost this case its first run. `--a.b` is the real thing: `ARG_A.B` cannot be a variable name.
    """
    name = "a-flag-that-is-not-an-identifier"
    want_exit, want_out, want_err = recorded(name)
    returncode, stdout, stderr = drive(tmp_path, name)
    assert want_exit == returncode == 2
    assert want_out == stdout == b""
    for text in (want_err, stderr):
        assert b"not a valid identifier" in text, text


# --------------------------------------------------------------------------- The helpers, without a subprocess ---------------------------------------------------------------------------


def test_pure_helpers_are_exercised_directly() -> None:
    """The helpers, without a subprocess, in BOTH directions."""
    assert lsp.SUB_REPOS == ("renet", "account", "elite", "homebrew-tap")
    assert lsp.is_binary(b"a\x00b") is True
    assert lsp.is_binary(b"ab\n") is False
    assert lsp.link_pattern("rediacc", "renet") == (
        rb"(https://github\.com/)?rediacc/renet(/pull/|#)[0-9]{1,7}"
    )
    assert lsp.numbers_for(b"rediacc/renet#12\n", "rediacc", "renet") == [b"12"]
    assert lsp.numbers_for(b"rediacc/renet#12\n", "rediacc", "account") == []
    assert lsp.numbers_for(b"rediacc/renet#12345678\n", "rediacc", "renet") == [b"1234567"]
    assert lsp._sort_un([b"9", b"10", b"9"]) == [b"9", b"10"]
    assert lsp._sort_un([b"007", b"7"]) == [b"007"]
    assert lsp._sort_un([]) == []
    # An owner that cannot compile matches nothing rather than raising.
    assert lsp.numbers_for(FULL_BODY, "redi(acc", "renet") == []
    # `scan` writes the binary diagnostic to the stream it is handed.
    buf = io.StringIO()
    assert lsp.scan(b"rediacc/renet#4\x00", "rediacc", "b.md", stderr=buf) == []
    assert buf.getvalue() == "grep: b.md: binary file matches\n"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_widening_of_the_allowlist_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Add `console` to the submodule list.

    The console repository is the monorepo itself, so a link to one of its own PRs is not a linked SUBMODULE PR, and accepting it would make the autopilot wait on a PR that is the very one it is working. `the-full-body` records four lines and no `rediacc/console 500`; a mutant that carries five prints it. The mutation runs from a throwaway copy of the package's module file;
    the tracked port is never touched.
    """
    with open(PORT, encoding="utf-8") as fh:
        original = fh.read()
    anchor = 'SUB_REPOS = ("renet", "account", "elite", "homebrew-tap")\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor, 'SUB_REPOS = ("renet", "account", "elite", "homebrew-tap", "console")\n'
    )

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "linked_sub_prs.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-full-body"
    _, stdout, _ = run(tmp_path / "planted", mutant, name)
    want = recorded(name)[1]
    assert b"rediacc/console 500\n" not in want, "the recorded corpus moved"
    assert b"rediacc/console 500\n" in stdout, "the plant did not change stdout"

    compare(tmp_path / "good", name)
    with open(PORT, encoding="utf-8") as fh:
        assert fh.read() == original
