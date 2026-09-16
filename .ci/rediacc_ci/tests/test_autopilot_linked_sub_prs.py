"""Differential: `rediacc_ci.autopilot.linked_sub_prs` against its twin
`.ci/scripts/autopilot/linked-sub-prs.sh`.

BYTES, NOT TEXT, on both streams. The subject reads a PR body, which is
whatever GitHub stored, and one of the cases below feeds it a NUL byte on
purpose to exercise GNU grep's binary suppression. A comparison that decoded
would fail on the input rather than on the difference it is looking for.

EVERY CASE RUNS BOTH SIDES OVER A FRESH COPY OF THE FIXTURE, in the same
directory, with `--body` given as a RELATIVE path. The relative spelling is
load-bearing for one case: grep's binary diagnostic names the path exactly as
it was given, so an absolute path in the test would compare two absolute paths
and never notice a port that rebuilt the string.

WHAT IS COMPARED BY SHAPE RATHER THAN BYTE, and why each one has to be:

  * `--owner 'redi(acc'` -- an owner is interpolated into a regex by the twin,
    so an unbalanced bracket is a syntax error, and grep's diagnostic is
    grep's. Exit code, stdout and the empty result are compared exactly; only
    the diagnostic text is not. Named in the port's docstring as its one known
    divergence.
  * `--1bad x` -- `printf -v` refuses a key that is not a shell identifier,
    which carries the twin's own path and line number into the message.

THE NEGATIVE CONTROLS ARE THE POINT OF HALF THIS FILE. A parser that returned
every number it saw would pass every positive case here; `test_the_allowlist_
is_the_boundary` and `test_near_miss_spellings_are_not_links` are what stop it.

K=5 LEDGER: `.ci/shadow/w7p6-linked-sub-prs.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout, since
`shadow-gate.ts --record` refuses a dirty tree and this checkout is never
clean.
"""

from __future__ import annotations

import io
import os
import pathlib
import subprocess
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import linked_sub_prs as lsp

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "linked-sub-prs.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "linked_sub_prs.py"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

# One body carrying all three accepted spellings, a duplicate, a leading-zero
# twin of an existing number, an eight-digit run and a link to a repository
# that is NOT a submodule of this monorepo.
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


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str]) -> tuple[int, bytes, bytes]:
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=BASE_ENV,
        check=False,
        cwd=str(base),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _sides(
    name: str,
    argv: list[str],
    *,
    body: bytes | None = FULL_BODY,
    body_name: str = "body.md",
    exact_stderr: bool = True,
) -> tuple[int, bytes, bytes]:
    """Run both sides over their own copy of the fixture and compare.

    A FRESH DIRECTORY PER SIDE even though this subject writes nothing: the
    cheapest way to be sure it stays that way is never to give the second side
    the first side's leftovers.
    """
    with tempfile.TemporaryDirectory() as td:
        results = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            if body is not None:
                (base / body_name).write_bytes(body)
            results.append(_run(subject, base, argv))
        old, new = results

    assert new[0] == old[0], "%s: exit diverged: %r vs %r\n twin stderr: %r\n port stderr: %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\nold: %r\nnew: %r" % (name, old[1], new[1])
    if exact_stderr:
        assert new[2] == old[2], "%s: stderr diverged:\nold: %r\nnew: %r" % (name, old[2], new[2])
    return old


def test_the_full_body() -> None:
    """All three spellings, the allowlist, the dedup and the truncation at once."""
    exit_code, stdout, stderr = _sides("full", ["--body", "body.md"])
    assert exit_code == 0
    assert stderr == b""
    assert stdout == (
        b"rediacc/renet 12\nrediacc/account 7\nrediacc/elite 1234567\nrediacc/homebrew-tap 3\n"
    ), stdout


def test_the_allowlist_is_the_boundary() -> None:
    """NEGATIVE CONTROL. A body that links only non-submodules prints nothing
    and exits 0, which is the twin's documented quiet-empty result."""
    body = b"\n".join(
        [
            b"https://github.com/rediacc/console/pull/1",
            b"rediacc/website#2",
            b"attacker/renet#3",
            b"https://github.com/attacker/account/pull/4",
            b"rediacc/renet-extra#5",
            b"",
        ]
    )
    exit_code, stdout, stderr = _sides("allowlist", ["--body", "body.md"], body=body)
    assert exit_code == 0
    assert stdout == b"", stdout
    assert stderr == b""


def test_near_miss_spellings_are_not_links() -> None:
    """NEGATIVE CONTROL for the SPELLING half: right repository, wrong shape."""
    body = b"\n".join(
        [
            b"rediacc/renet PR 12",  # no separator
            b"rediacc/renet#",  # no number
            b"http://github.com/rediacc/account/pull/9",  # http, and the
            # optional group only matches https -- but `rediacc/account/pull/9`
            # is still a bare match inside it, so this line DOES link 9.
            b"rediacc/elite/pulls/4",  # /pulls/ is not /pull/
            b"rediacc/homebrew-tap#x7",  # digit not adjacent to the separator
            b"",
        ]
    )
    exit_code, stdout, _ = _sides("near-miss", ["--body", "body.md"], body=body)
    assert exit_code == 0
    assert stdout == b"rediacc/account 9\n", stdout


def test_every_spelling_alone() -> None:
    """Each accepted spelling on its own, so a regression in one is not hidden
    by another matching the same number."""
    for label, line, want in (
        ("url", b"https://github.com/rediacc/renet/pull/41\n", b"rediacc/renet 41\n"),
        ("hash", b"rediacc/renet#42\n", b"rediacc/renet 42\n"),
        ("path", b"rediacc/renet/pull/43\n", b"rediacc/renet 43\n"),
    ):
        _, stdout, _ = _sides(label, ["--body", "body.md"], body=line)
        assert stdout == want, (label, stdout)


def test_numeric_dedup_keeps_the_first_of_an_equal_run() -> None:
    """`sort -un` reads `007` and `7` as ONE PR. Which STRING survives depends
    on input order, and both orders are driven because a port that sorted
    lexicographically would agree with one of them by accident."""
    _, first, _ = _sides(
        "zeros-7-first",
        ["--body", "b.md"],
        body=b"rediacc/renet#7\nrediacc/renet#007\n",
        body_name="b.md",
    )
    assert first == b"rediacc/renet 7\n", first
    _, second, _ = _sides(
        "zeros-007-first",
        ["--body", "b.md"],
        body=b"rediacc/renet#007\nrediacc/renet#7\n",
        body_name="b.md",
    )
    assert second == b"rediacc/renet 007\n", second


def test_a_nul_byte_makes_the_body_binary() -> None:
    """GNU grep suppresses every match, says so on stderr, and exits 0.

    Reproduced rather than smoothed over: the result is an EMPTY link list,
    which is indistinguishable from a body with no links unless the diagnostic
    survives.
    """
    body = b"rediacc/renet#12\x00rediacc/account#13\n"
    exit_code, stdout, stderr = _sides("binary", ["--body", "body.md"], body=body)
    assert exit_code == 0
    assert stdout == b""
    assert stderr == (
        b"grep: body.md: binary file matches\ngrep: body.md: binary file matches\n"
    ), stderr


def test_a_nul_byte_with_no_link_is_silent() -> None:
    """The other half of the case above: grep only announces a binary file it
    MATCHED, so a binary body with no links produces no diagnostic at all."""
    _, stdout, stderr = _sides("binary-quiet", ["--body", "body.md"], body=b"nothing\x00here\n")
    assert stdout == b""
    assert stderr == b""


def test_empty_and_linkless_bodies() -> None:
    for label, body in (("empty", b""), ("prose", b"just some prose\nwith no links\n")):
        exit_code, stdout, stderr = _sides(label, ["--body", "body.md"], body=body)
        assert (exit_code, stdout, stderr) == (0, b"", b""), (label, exit_code, stdout, stderr)


def test_usage_refusals() -> None:
    """`--body` absent, and `--body=` present but empty. Both exit 2."""
    exit_code, _, stderr = _sides("no-body", [])
    assert exit_code == 2
    assert b"usage: linked-sub-prs.sh --body <file>" in stderr
    assert _sides("empty-body", ["--body="])[0] == 2


def test_a_missing_or_unusable_body_refuses() -> None:
    exit_code, _, stderr = _sides("missing", ["--body", "nope.md"])
    assert exit_code == 1
    assert b"Required file 'nope.md' does not exist" in stderr
    # A DIRECTORY is not a regular file, so `-f` refuses it too.
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            (base / "adir").mkdir(parents=True)
            code, _, err = _run(subject, base, ["--body", "adir"])
            assert code == 1, subject
            assert b"Required file 'adir' does not exist" in err, subject


def test_the_owner_is_a_parameter() -> None:
    """`--owner` changes which links count, and an EMPTY one falls back to
    `rediacc` (`${ARG_OWNER:-rediacc}`, not `${ARG_OWNER-rediacc}`)."""
    body = b"rediacc/renet#1\nacme/renet#2\n"
    _, acme, _ = _sides("owner-acme", ["--body", "body.md", "--owner", "acme"], body=body)
    assert acme == b"acme/renet 2\n", acme
    _, empty, _ = _sides("owner-empty", ["--body", "body.md", "--owner="], body=body)
    assert empty == b"rediacc/renet 1\n", empty


def test_divergence_an_owner_that_is_not_valid_regex() -> None:
    """The port's one known divergence, pinned so a later "fix" turns it red.

    Both sides find nothing and exit 0; only the diagnostic differs (grep's
    versus Python's, and the twin emits one per submodule).
    """
    with tempfile.TemporaryDirectory() as td:
        seen = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            (base / "body.md").write_bytes(FULL_BODY)
            seen.append(_run(subject, base, ["--body", "body.md", "--owner", "redi(acc"]))
        old, new = seen
    assert old[0] == new[0] == 0, (old, new)
    assert old[1] == new[1] == b"", (old[1], new[1])
    assert b"Unmatched" in old[2], old[2]
    assert new[2] == b"", "the port must fail SILENTLY here, not refuse: %r" % new[2]


def test_divergence_a_flag_that_is_not_a_shell_identifier() -> None:
    """`parse_args` QUIRK 3. Exit 2 on both; the twin's text carries common.sh's
    own path and line number, so only the shape is compared.

    THE FLAG HAS TO CARRY A CHARACTER THE PREFIX CANNOT RESCUE. `--1bad` looks
    like the obvious specimen and is not one: the key becomes `ARG_1BAD`, which
    starts with a letter and is a perfectly good shell identifier, so both
    sides parse it happily and exit 0. Driven, and it cost this case its first
    run. `--a.b` is the real thing: `ARG_A.B` cannot be a variable name.
    """
    with tempfile.TemporaryDirectory() as td:
        seen = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            (base / "body.md").write_bytes(FULL_BODY)
            seen.append(_run(subject, base, ["--a.b", "x", "--body", "body.md"]))
        old, new = seen
    assert old[0] == new[0] == 2, (old, new)
    assert old[1] == new[1] == b"", (old[1], new[1])
    for side in (old, new):
        assert b"not a valid identifier" in side[2], side[2]


def test_positional_arguments_are_invisible() -> None:
    """`parse_args` skips anything not starting with `--`, so a positional body
    path is NOT a body path and the script refuses for want of `--body`."""
    exit_code, _, stderr = _sides("positional", ["body.md"])
    assert exit_code == 2
    assert b"usage: linked-sub-prs.sh" in stderr


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
