"""Differential: `rediacc_ci.review.discover_epics` against its twin
`.ci/scripts/review/discover-epics.sh`.

A DISPOSABLE LOCAL GIT REPO, same strategy as `test_review_epic_context.py` and `test_pr_sync_epic_block.py`, and here it is not merely convenient: the subject resolves its snapshot root through `git rev-parse --show-toplevel`, so a fixture that is not a git repository would silently fall back to `.` and BOTH sides would then read the same wrong place and agree. Every case below
runs with cwd inside a real fixture repo carrying a real `agent/pr/<branch>.md`.

WHY `--dry-run` HAS NO EQUIVALENT HERE: this script writes nothing outside `$GITHUB_OUTPUT`, and with that variable unset it writes to stdout. Both are driven -- `test_github_output_file_receives_the_assignment` points it at a real file and compares the FILE, because a port that emitted the assignment to stdout in that case would still look identical on the human line.

THE ONE LINE THAT MATTERS MOST is the empty case: a matrix over `[]` does not
run the job at all, so `epics=[""]` (one flat pass) is what the twin emits and
what `test_planted_defect_is_caught` plants against.

K=5 LEDGER: `.ci/shadow/w7p6-discover-epics.observations.jsonl` -- five
distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct trees". Recorded against a disposable scratch git repo built OUTSIDE this checkout (this tree is dirty and `shadow-gate --record` refuses a dirty tree), holding copies of the twin, `common.sh` and the `rediacc_ci` package plus a per-tree `agent/pr/<branch>.md`. The five trees vary the snapshot: one epic, two
epics with a slashed branch, a snapshot with no trailer, PR_HEAD_REF unset, and the anchored-parse fixture. `--finding-re .` is passed because this script's output lines carry no severity marker.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "review" / "discover-epics.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "review" / "discover_epics.py"
BASH = shutil.which("bash") or "/bin/bash"

# Deliberately tiny and REPLACING, not extending, for the reason `rediacc_ci.tests.differential.BASE_ENV` gives: a differential that inherits the developer's environment passes or fails depending on whether PR_HEAD_REF or GITHUB_OUTPUT happen to be exported, and both are exported in CI.
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _repo(tmp_path: pathlib.Path, name: str = "repo") -> pathlib.Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "agent" / "pr").mkdir(parents=True)
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _snapshot(repo: pathlib.Path, branch: str, text: str) -> None:
    (repo / "agent" / "pr" / f"{branch.replace('/', '-')}.md").write_text(text, encoding="utf-8")


# What both subjects genuinely need on PATH before they reach `require_cmd jq`. Sourcing common.sh alone costs `dirname` (line 17 of the twin) and `uname` (common.sh's CI_OS/CI_ARCH assignments at source time), so an empty PATH breaks the twin with "dirname: command not found" -- a control that fires for the wrong reason, which is not a control. Confirmed by driving it: the first
# attempt at this case asserted the jq refusal and got the dirname error instead.
PATH_MINIMUM = ("dirname", "uname", "git", "grep", "sed", "cat", "wc", "tr", "mkdir", "rm")


def _path_without_jq(tmp_path: pathlib.Path) -> str:
    """A PATH carrying everything but jq, as symlinks into a fresh dir."""
    stub = tmp_path / "no-jq-bin"
    stub.mkdir(exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, f"{name} is missing from this machine; the case cannot run"
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    assert shutil.which("jq", path=str(stub)) is None, "jq leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path, cwd: pathlib.Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    # RESOLVED FROM THE TEST PROCESS'S OWN PATH, not the child's. The missing-jq case hands the child an EMPTY PATH on purpose, and a bare "bash" would then fail to spawn at all -- a FileNotFoundError that reads like a broken harness rather than the refusal under test.
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    return subprocess.run(
        [*runner, str(subject)],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


def run_both(
    repo: pathlib.Path, **overrides: str
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    env = dict(BASE_ENV, **overrides)
    return _run(TWIN, repo, env), _run(PORT, repo, env)


def _assert_agree(old, new, label: str) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )


def test_pr_head_ref_unset_is_a_refusal(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    old, new = run_both(repo)
    assert old.returncode == 1
    assert old.stdout == ""
    assert "PR_HEAD_REF is unset" in old.stderr
    _assert_agree(old, new, "pr-head-ref-unset")


def test_pr_head_ref_empty_is_the_same_refusal(tmp_path: pathlib.Path) -> None:
    """`${PR_HEAD_REF:-}` then `[[ -z ]]`: set-but-empty is unset here."""
    repo = _repo(tmp_path)
    old, new = run_both(repo, PR_HEAD_REF="")
    assert old.returncode == 1
    _assert_agree(old, new, "pr-head-ref-empty")


def test_no_snapshot_emits_one_flat_pass(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    old, new = run_both(repo, PR_HEAD_REF="0906-1")
    assert old.returncode == 0
    assert old.stdout == (
        'no epics declared for 0906-1; one flat review pass will run\nepics=[""]\n'
    )
    _assert_agree(old, new, "no-snapshot")


def test_snapshot_with_no_trailers_emits_one_flat_pass(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "# Work in 0906-1\n\n- [ ] item with no epic\n")
    old, new = run_both(repo, PR_HEAD_REF="0906-1")
    assert old.returncode == 0
    assert 'epics=[""]' in old.stdout
    _assert_agree(old, new, "snapshot-no-trailers")


def test_one_epic(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "prose\n`PR-TASK: ab12cd34`\nmore prose\n")
    old, new = run_both(repo, PR_HEAD_REF="0906-1")
    assert old.returncode == 0
    assert old.stdout == 'epics for 0906-1: ab12cd34\nepics=["ab12cd34"]\n'
    _assert_agree(old, new, "one-epic")


def test_two_epics_and_a_slash_in_the_branch_name(tmp_path: pathlib.Path) -> None:
    """`${branch//\\//-}` maps `feat/x` to `feat-x.md`; the human line still
    prints the branch with its slash."""
    repo = _repo(tmp_path)
    _snapshot(repo, "feat/x", "`PR-TASK: ab12cd34`\nmid\nPR-TASK: ef56ab78\n")
    old, new = run_both(repo, PR_HEAD_REF="feat/x")
    assert old.returncode == 0
    assert old.stdout == ('epics for feat/x: ab12cd34 ef56ab78\nepics=["ab12cd34","ef56ab78"]\n')
    _assert_agree(old, new, "two-epics-slash-branch")


def test_indented_and_uppercase_trailers_are_invisible(tmp_path: pathlib.Path) -> None:
    """BOTH DIRECTIONS in one fixture: the anchored, lowercase-only grep must
    ignore an indented line, an uppercase id and a trailing-comment line, and
    must still see the one well-formed trailer below them."""
    repo = _repo(tmp_path)
    _snapshot(
        repo,
        "0906-1",
        "  PR-TASK: aaaaaaaa\n"
        "`PR-TASK: ABCDEF12`\n"
        "PR-TASK: bbbbbbbb trailing words\n"
        "`PR-TASK: cc12dd34`\n",
    )
    old, new = run_both(repo, PR_HEAD_REF="0906-1")
    assert old.returncode == 0
    assert old.stdout == 'epics for 0906-1: cc12dd34\nepics=["cc12dd34"]\n'
    _assert_agree(old, new, "anchored-parse")


def test_github_output_file_receives_the_assignment(tmp_path: pathlib.Path) -> None:
    """The FILE is the artifact here. A port that wrote the assignment to
    stdout instead would produce an identical human line and an empty file."""
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "`PR-TASK: ab12cd34`\n")
    old_out = tmp_path / "old-output.txt"
    new_out = tmp_path / "new-output.txt"
    env = dict(BASE_ENV, PR_HEAD_REF="0906-1")
    old = _run(TWIN, repo, dict(env, GITHUB_OUTPUT=str(old_out)))
    new = _run(PORT, repo, dict(env, GITHUB_OUTPUT=str(new_out)))
    _assert_agree(old, new, "github-output-file")
    assert old.stdout == "epics for 0906-1: ab12cd34\n"
    assert old_out.read_text(encoding="utf-8") == 'epics=["ab12cd34"]\n'
    assert new_out.read_text(encoding="utf-8") == old_out.read_text(encoding="utf-8")


def test_github_output_appends_rather_than_truncates(tmp_path: pathlib.Path) -> None:
    """`>>`, not `>`. GITHUB_OUTPUT is shared with every other step."""
    repo = _repo(tmp_path)
    env = dict(BASE_ENV, PR_HEAD_REF="0906-1")
    old_out = tmp_path / "old-output.txt"
    new_out = tmp_path / "new-output.txt"
    old_out.write_text("prior=kept\n", encoding="utf-8")
    new_out.write_text("prior=kept\n", encoding="utf-8")
    old = _run(TWIN, repo, dict(env, GITHUB_OUTPUT=str(old_out)))
    new = _run(PORT, repo, dict(env, GITHUB_OUTPUT=str(new_out)))
    _assert_agree(old, new, "github-output-append")
    assert old_out.read_text(encoding="utf-8") == 'prior=kept\nepics=[""]\n'
    assert new_out.read_text(encoding="utf-8") == old_out.read_text(encoding="utf-8")


def test_empty_github_output_reads_as_unset(tmp_path: pathlib.Path) -> None:
    """`${GITHUB_OUTPUT:-/dev/stdout}` -- the `:-` form, so an exported but
    empty variable takes the default rather than trying to open `""`."""
    repo = _repo(tmp_path)
    old, new = run_both(repo, PR_HEAD_REF="0906-1", GITHUB_OUTPUT="")
    assert old.returncode == 0
    assert 'epics=[""]' in old.stdout
    _assert_agree(old, new, "empty-github-output")


def test_worklist_publish_root_override_is_honoured(tmp_path: pathlib.Path) -> None:
    """common.sh:610's override, which is how the two sides can be pointed at
    a snapshot outside whatever checkout they are standing in."""
    repo = _repo(tmp_path)
    elsewhere = _repo(tmp_path, name="elsewhere")
    _snapshot(elsewhere, "0906-1", "`PR-TASK: 99aabb00`\n")
    old, new = run_both(repo, PR_HEAD_REF="0906-1", WORKLIST_PUBLISH_ROOT=str(elsewhere))
    assert old.returncode == 0
    assert 'epics=["99aabb00"]' in old.stdout
    _assert_agree(old, new, "publish-root-override")


def test_missing_jq_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`require_cmd jq` is the twin's FIRST statement, so a machine without jq
    refuses before it ever looks at PR_HEAD_REF. The port keeps the check even though it never shells out to jq -- see its docstring. The seam is a PATH
    carrying every other binary the two need and nothing named jq; the port is
    invoked by absolute interpreter path so it can still start."""
    repo = _repo(tmp_path)
    old, new = run_both(repo, PATH=_path_without_jq(tmp_path), PR_HEAD_REF="0906-1")
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'jq' is not available\n"
    _assert_agree(old, new, "missing-jq")


def _run_with_socket_stdout(
    subject: pathlib.Path, cwd: pathlib.Path, env: dict[str, str]
) -> tuple[int, str, str]:
    """Run one side with a UNIX SOCKET as fd 1, and read what reached it.

    A socket, not a pipe, because that is the case that broke: Node's `child_process.spawnSync` gives its child a socketpair for stdout, so every Node harness in this repo -- `scripts/lib/shadow-gate.ts` included -- runs the subject this way.
    """
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    child_end, parent_end = socket.socketpair()
    try:
        proc = subprocess.run(
            [*runner, str(subject)],
            cwd=cwd,
            stdout=child_end.fileno(),
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
        child_end.close()
        parent_end.setblocking(False)
        try:
            out = parent_end.recv(65536).decode("utf-8")
        except BlockingIOError:
            out = ""
    finally:
        parent_end.close()
    return proc.returncode, out, proc.stderr


def test_defect_fixed_stdout_as_a_socket_no_longer_loses_the_assignment(
    tmp_path: pathlib.Path,
) -> None:
    """REGRESSION FOR A DEFECT FOUND BY THIS PORT AND FIXED IN THE TWIN.

    Until 2026-09-10 both call sites were
    `>>"${GITHUB_OUTPUT:-/dev/stdout}"`. Opening `/dev/stdout` fails with ENXIO
    ("No such device or address") when fd 1 is a UNIX socket, so with
    GITHUB_OUTPUT unset the twin printed its human line, LOST the `epics=`
    line -- the only thing the workflow reads -- and exited 1. Measured before the fix:

        twin rc=1 stdout='no epics declared for 0906-1; ...\n'
             stderr='discover-epics.sh: line 36: /dev/stdout: No such device
                     or address\n'
        port rc=0 stdout='no epics declared ...\nepics=[""]\n'

    GITHUB_OUTPUT is always set in Actions, so the live matrix never hit it;
    every local run and every Node-harness run did, including the shadow-gate recording this port's own ledger, which is how it was found. Both sides
    are asserted here, so a revert of either turns this red."""
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "`PR-TASK: ab12cd34`\n")
    env = dict(BASE_ENV, PR_HEAD_REF="0906-1")
    old = _run_with_socket_stdout(TWIN, repo, env)
    new = _run_with_socket_stdout(PORT, repo, env)
    assert old == (0, 'epics for 0906-1: ab12cd34\nepics=["ab12cd34"]\n', ""), (
        f"the twin regressed on socket stdout: {old!r}"
    )
    assert new == old, f"socket stdout diverged:\nold: {old!r}\nnew: {new!r}"


def test_defect_fixed_socket_stdout_on_the_empty_case_too(tmp_path: pathlib.Path) -> None:
    """The same defect on the OTHER call site -- the flat-pass `[""]` line,
    which is the one whose loss would leave a PR with no review at all."""
    repo = _repo(tmp_path)
    env = dict(BASE_ENV, PR_HEAD_REF="0906-1")
    old = _run_with_socket_stdout(TWIN, repo, env)
    new = _run_with_socket_stdout(PORT, repo, env)
    assert old[0] == 0
    assert 'epics=[""]' in old[1], f"the twin lost the flat-pass assignment: {old!r}"
    assert new == old


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the one line the twin's header calls the whole
    reason the script exists: `[""]` for the no-epics case. `[]` is the plausible-looking "correct" JSON, and it makes the review matrix expand to zero jobs -- a PR with no epics would get NO review at all. Driven red,
    then the source is restored byte-identical and re-verified green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace("_emit('epics=[\"\"]\\n', env)", "_emit('epics=[]\\n', env)")
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    repo = _repo(tmp_path)
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")
    env = dict(BASE_ENV, PR_HEAD_REF="0906-1")

    old = _run(TWIN, repo, env)
    bad = _run(mutant, repo, env)
    assert 'epics=[""]' in old.stdout, "the TWIN did not emit the flat-pass array; plant untested"
    assert bad.stdout != old.stdout, "the mutant agreed with the twin; the plant did not fire"
    assert "epics=[]" in bad.stdout

    good = _run(PORT, repo, env)
    assert good.stdout == old.stdout, "restored port no longer agrees with the twin"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
