"""`rediacc_ci.quality.pipefail_grep_q` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-pipefail-grep-q.sh` over a
git fixture with stdout and stderr captured SEPARATELY, and its bytes are compared
against the port's. The twin has no environment seam -- it resolves its root from
its OWN location and enumerates through `git -C "$ROOT" ls-files` -- so the
fixture is a real git repository holding BOTH implementations. Same recipe as the
committed ledger, `.ci/shadow/w7p2-pipefail-grepq.observations.jsonl`.

THE MECHANISM CONTROL RUNS FOR REAL IN EVERY CASE BELOW, on both sides: a 300 KB
producer piped into `grep -q` under pipefail, asserted to report MISSED. It is the
one control that cannot be a pure assertion, because the claim is about what the
kernel does to a writer whose reader has exited. If the host ever stops
reproducing the race, both implementations go red together and these cases say so
rather than quietly agreeing about a myth.

THE RACING SHAPE IS ASSEMBLED AT RUNTIME in this file too, exactly as the twin
assembles its own fixture, so that this file's TEXT never carries it contiguously.
The twin flagged itself the first time it became a tracked file for precisely that
reason.
"""

import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import pipefail_grep_q as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-pipefail-grep-q.sh"
MODULE = "pipefail_grep_q"

# Assembled, never written out. See the module docstring.
GQ = "grep -q"


def offender_file(count: int) -> str:
    """A scanned script with `count` racing pipelines and three DECOYS.

    The decoys are the negative half and they are not decoration: a comment
    naming the shape, a string literal quoting it, and the sanctioned
    command-substitution fix must all stay unflagged, or the gate is over-broad
    and gets switched off.
    """
    lines = [
        "#!/bin/bash",
        "set -uo pipefail",
        'body() { cat "$1"; }',
        '# never write: body "$1" | %s x' % GQ,
        'echo "no racing body | %s here"' % GQ,
        'if [ -n "$(body "$1" | grep x)" ]; then :; fi',
    ]
    lines += ['if body "$1" | %s marker%d; then :; fi' % (GQ, i) for i in range(1, count + 1)]
    return "\n".join(lines) + "\n"


def build(tmp_path: pathlib.Path, offenders: int) -> pathlib.Path:
    """A sealed git specimen holding BOTH implementations and a planted file."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "scripts" / "probe").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    (root / ".ci" / "scripts" / "probe" / "a.sh").write_text(
        offender_file(offenders), encoding="utf-8"
    )
    # A REAL GIT REPOSITORY, because the corpus is `git ls-files` and an
    # unversioned tree makes the gate scan ZERO files -- which is its own
    # anti-vacuity refusal, not the case under test.
    env = diff.env_for()
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "gate@example.invalid"],
        ["config", "user.name", "test"],
        ["add", "-A"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "specimen"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, env=env)
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=env, cwd=str(root), timeout=180)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.quality.%s" % MODULE, env=env, cwd=str(root), timeout=180
    )
    return old, new


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_port_and_twin_agree_byte_for_byte(tmp_path: pathlib.Path, count: int) -> None:
    root = build(tmp_path, count)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == 1
    assert new_exit == old_exit
    assert new_out == old_out
    assert new_err == old_err
    assert "%d racing pipeline(s)" % count in old_err
    # THE MECHANISM CONTROL MUST HAVE FIRED on both sides, or the rest of this
    # comparison is two gates agreeing about a myth.
    assert "SIGPIPE under pipefail really does flip" in old_out
    assert "SIGPIPE under pipefail really does flip" in new_out


def test_a_clean_corpus_is_green_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The mirror the parametrized cases need: a gate that flagged everything
    would satisfy all five of them and be useless."""
    root = build(tmp_path, 0)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == 0
    assert new_exit == 0
    assert new_out == old_out
    assert new_err == old_err
    assert "no racing" in old_out
    # The decoys are still in the file, so this green is a statement about them.
    assert "Blind spot" in old_out


def test_the_scanned_count_is_printed_and_non_trivial(tmp_path: pathlib.Path) -> None:
    """ "N file(s) clean" is the anti-vacuity evidence a reader can check."""
    root = build(tmp_path, 0)
    (_, old_out, _), (_, new_out, _) = run_both(root)
    assert "file(s) clean." in old_out
    assert new_out == old_out
    scanned = int(old_out.split("pipefail/grep -q: ")[1].split(" ")[0])
    assert scanned > 1


# ---------------------------------------------------------------------------
# The decision functions, driven directly. Both directions for every rule.
# ---------------------------------------------------------------------------

_SEED = 'set -o pipefail\nbody() { cat "$1"; }\n'


@pytest.mark.parametrize(
    ("text", "hits"),
    [
        pytest.param(_SEED + 'if body "$1" | %s x; then :; fi\n' % GQ, 1, id="the-racing-shape"),
        pytest.param(
            _SEED + 'if [ -n "$(body "$1" | grep x)" ]; then :; fi\n',
            0,
            id="the-sanctioned-fix",
        ),
        pytest.param(
            'set -o pipefail\nif printf "%%s" "$x" | %s y; then :; fi\n' % GQ,
            0,
            id="a-bounded-builtin-producer",
        ),
        pytest.param(
            'body() { cat "$1"; }\nif body "$1" | %s x; then :; fi\n' % GQ,
            0,
            id="no-pipefail-no-race",
        ),
        pytest.param(
            _SEED + '# never write: body "$1" | %s x\n' % GQ, 0, id="a-comment-is-not-code"
        ),
        pytest.param(
            'set -o pipefail\npass() { echo "$*"; }\necho "no racing pass | %s here"\n' % GQ,
            0,
            id="a-string-literal-is-not-code",
        ),
        pytest.param(
            "set -o pipefail\nif x | %s y; then :; fi\n" % GQ, 0, id="not-a-local-function"
        ),
        pytest.param("", 0, id="empty"),
    ],
)
def test_offenders_in(text: str, hits: int) -> None:
    assert len(gate.offenders_in(text)) == hits


def test_a_line_naming_two_local_functions_is_reported_twice() -> None:
    """One `grep -n` per function name, so a line matching two is two hits.

    Pinned because it looks like a missing de-duplication and is the twin's
    shape; a port that collapsed it would disagree on the count.
    """
    text = "set -o pipefail\nabe() { :; }\nzed() { :; }\nif abe zed | %s x; then :; fi\n" % GQ
    assert len(gate.offenders_in(text)) == 2


@pytest.mark.parametrize(
    ("line", "stripped"),
    [
        pytest.param("code # tail", "code ", id="comment"),
        pytest.param("a 'b c' d", "a '' d", id="single-quoted"),
        pytest.param('a "b c" d', 'a "" d', id="double-quoted"),
        pytest.param("body | grep x", "body | grep x", id="plain-code-survives"),
    ],
)
def test_strip_code(line: str, stripped: str) -> None:
    assert gate.strip_code(line) == stripped


@pytest.mark.parametrize(
    ("text", "names"),
    [
        pytest.param("body() {\n", ["body"], id="column-one"),
        pytest.param("  body() {\n", [], id="indented-is-not-a-definition"),
        pytest.param("body () {\n", [], id="a-space-before-the-parens"),
        pytest.param("zed() {\nabe() {\nzed() {\n", ["abe", "zed"], id="sorted-and-unique"),
    ],
)
def test_local_functions(text: str, names: list[str]) -> None:
    assert gate.local_functions(text) == names


def test_the_mechanism_control_reproduces_on_this_host(tmp_path: pathlib.Path) -> None:
    """The OS half of the gate, asserted here as well as inside the gate.

    If this ever stops saying MISSED, the gate is guarding a myth on this host
    and every green it prints is worthless. That is worth a failing test, not a
    skip.
    """
    assert gate.mechanism_output(tmp_path) == "MISSED"


def test_the_live_corpus_is_not_empty() -> None:
    """`git ls-files` over the real tree must return files, or the gate is blind."""
    files = [f for f in gate.scan_files(paths.repo_root()) if f]
    assert len(files) > 100


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 18
