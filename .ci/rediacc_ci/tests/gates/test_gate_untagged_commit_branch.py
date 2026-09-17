"""Port of `.ci/scripts/test/gates/test-untagged-commit-branch.sh`.

`block_untagged_commit` must know WHICH BRANCH it is judging, including when HEAD is detached.

WHY THE TWIN EXISTS. The guard validates a `PR-TASK:` id against `agent/pr/<branch>.md`, and it resolved `<branch>` with `git rev-parse --abbrev-ref HEAD`. That prints the literal string `HEAD` when detached, so the snapshot path became `agent/pr/HEAD.md`, nothing was found, and a TYPO'D id -- the case the guard was extended for -- sailed straight through. Detached is not exotic:
it is EVERY `pull_request` checkout and every halted rebase. Measured 2026-08-27, the suite case asserting a typo is refused returned 0 in CI while passing on every developer machine, for exactly this reason.

WHAT THE PORT DOES DIFFERENTLY, and why the two still agree.

  * THE JSON PAYLOAD. The twin shells out to `jq -Rn --arg c ... '$c'` purely to
    get one shell string quoted into a JSON document. `json.dumps` produces the
    same document, and the guard parses the document rather than the bytes that
    made it, so nothing about the claim changes. It also removes `jq` from this
    port's dependency set, which matters because a missing `jq` is the shape of
    tool-absence that turns a gate green without running it.

  * ONE FIXTURE PER CASE, not one shared fixture walked through HEAD states. The
    twin is a straight-line script, so it can afford to build the repository once
    and mutate HEAD as it goes. Independent pytest functions cannot share that
    without ordering, and ordering is what makes a suite fail in a different place
    than it broke. Each case therefore builds its own repository to exactly the
    state it needs. The precondition controls (`abbrev-ref` really prints `HEAD`,
    the rebase really halted) are what keep that rebuild honest: a case expecting
    exit 0 would also pass if the detach or the rebase silently did not happen.

NO `xdist_group`. Every case runs in its own `tempfile.mkdtemp()` git repository, drives the guard as a subprocess with an explicit environment, and mutates no module global and no path inside the real tree. Two of these running at once share nothing.

THE ENVIRONMENT IS SCRUBBED PER CALL. `PR_HEAD_REF` and `GITHUB_HEAD_REF` are removed unless a case sets one, because a real CI run exports those very names and would otherwise decide these cases for us.
"""

import json
import os
import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-untagged-commit-branch.sh"

DISPATCH = paths.from_root(".claude", "rediacc_hooks", "dispatch.py")
GUARD = "block_untagged_commit"

REAL = "f2757830"
TYPO = "f2757831"

BRANCH = "0827-1"


def _git(gate, repo: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        gate.log_fail(
            "git %s failed in the fixture (rc=%d): %s"
            % (" ".join(args), proc.returncode, (proc.stderr or proc.stdout).strip())
        )
    return proc.stdout.strip()


def make_repo(gate, root: pathlib.Path) -> pathlib.Path:
    """A repository on `BRANCH` carrying agent/pr/<BRANCH>.md with the REAL id."""
    harness.require_tool("git", "install git; this gate drives real git deliberately")
    repo = root / "repo"
    repo.mkdir(parents=True)
    _git(gate, repo, "init", "-q", "-b", BRANCH)
    _git(gate, repo, "config", "user.email", "fixture@example.invalid")
    _git(gate, repo, "config", "user.name", "branch-fixture")
    _git(gate, repo, "config", "commit.gpgsign", "false")
    (repo / "agent" / "pr").mkdir(parents=True)
    (repo / "agent" / "pr" / ("%s.md" % BRANCH)).write_text(
        "### Enforcement layer\n\n`PR-TASK: %s`\n" % REAL, encoding="utf-8"
    )
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _git(gate, repo, "add", "-A")
    _git(gate, repo, "commit", "-qm", "base")
    return repo


def run_guard(repo: pathlib.Path, task_id: str, env_key: str = "", env_value: str = "") -> int:
    """The guard's EXIT CODE for a `git commit` carrying `task_id`.

    Driven the way the Bash tool drives it: the hook payload on stdin, cwd inside the fixture, `CLAUDE_PROJECT_DIR` naming it.
    """
    command = 'git commit -m "feat: x\n\nPR-TASK: %s"' % task_id
    payload = json.dumps({"tool_input": {"command": command}})
    env = dict(os.environ)
    env.pop("PR_HEAD_REF", None)
    env.pop("GITHUB_HEAD_REF", None)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    if env_key:
        env[env_key] = env_value
    proc = subprocess.run(
        ["python3", str(DISPATCH), GUARD],
        cwd=str(repo),
        env=env,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return proc.returncode


def test_on_a_branch_the_guard_judges_the_snapshot(gate):
    """The baseline the whole guard rests on: a real branch, a real snapshot."""
    gate.log_test("on a branch: the id is judged against agent/pr/<branch>.md")
    with harness.temp_dir() as root:
        repo = make_repo(gate, root)
        gate.assert_exit_code(2, run_guard(repo, TYPO), "on a branch: a typo'd id is refused")
        gate.log_pass("on a branch: a typo'd id is refused")
        gate.assert_exit_code(0, run_guard(repo, REAL), "on a branch CONTROL: the real id passes")
        gate.log_pass("on a branch CONTROL: the real id passes")


def test_a_plain_detached_head_allows_rather_than_refusing_blind(gate):
    """No branch means no published epic set, so the guard ALLOWS."""
    gate.log_test("plain detach: nothing to judge against, so nothing is refused")
    with harness.temp_dir() as root:
        repo = make_repo(gate, root)
        base_sha = _git(gate, repo, "rev-parse", "HEAD")
        _git(gate, repo, "checkout", "-q", "--detach", base_sha)
        gate.assert_exit_code(
            0,
            run_guard(repo, TYPO),
            "plain detach: no branch exists, so it allows rather than refusing blind",
        )
        gate.log_pass("plain detach: no branch exists, so it allows rather than refusing blind")
        gate.assert_exit_code(
            0, run_guard(repo, REAL), "plain detach CONTROL: the real id still passes"
        )
        gate.log_pass("plain detach CONTROL: the real id still passes")
        # THE PRECONDITION, without which both cases above would also pass on a detach that silently did not happen.
        abbrev = _git(gate, repo, "rev-parse", "--abbrev-ref", "HEAD")
        gate.assert_eq(
            abbrev,
            "HEAD",
            "fixture precondition: abbrev-ref must print the string HEAD when detached",
        )
        gate.log_pass(
            "fixture precondition: abbrev-ref really does print the string HEAD when detached"
        )


def test_detached_under_ci_the_environment_names_the_branch(gate):
    """The CI case that was red: detached, with the branch only in the environment."""
    gate.log_test("detached + a branch-naming variable: the typo is refused again")
    with harness.temp_dir() as root:
        repo = make_repo(gate, root)
        base_sha = _git(gate, repo, "rev-parse", "HEAD")
        _git(gate, repo, "checkout", "-q", "--detach", base_sha)
        gate.assert_exit_code(
            2,
            run_guard(repo, TYPO, "GITHUB_HEAD_REF", BRANCH),
            "detached + GITHUB_HEAD_REF: the typo is refused -- the CI case that was red",
        )
        gate.log_pass("detached + GITHUB_HEAD_REF: the typo is refused -- the CI case that was red")
        gate.assert_exit_code(
            2,
            run_guard(repo, TYPO, "PR_HEAD_REF", BRANCH),
            "detached + PR_HEAD_REF: same, via the variable the gate step sets",
        )
        gate.log_pass("detached + PR_HEAD_REF: same, via the variable the gate step sets")
        gate.assert_exit_code(
            0,
            run_guard(repo, TYPO, "GITHUB_HEAD_REF", "no-such-branch"),
            "CONTROL: a branch with NO snapshot has no set to judge, so it allows",
        )
        gate.log_pass("CONTROL: a branch with NO snapshot has no set to judge, so it allows")


def test_mid_rebase_the_branch_is_recovered_from_head_name(gate):
    """The detached case that actually happens here: a halted rebase."""
    gate.log_test("mid-rebase: git remembers the branch in rebase-merge/head-name")
    with harness.temp_dir() as root:
        repo = make_repo(gate, root)
        base_sha = _git(gate, repo, "rev-parse", "HEAD")
        (repo / "f.txt").write_text("mine\n", encoding="utf-8")
        _git(gate, repo, "commit", "-qam", "mine")
        _git(gate, repo, "checkout", "-q", "-b", "other", base_sha)
        (repo / "f.txt").write_text("theirs\n", encoding="utf-8")
        _git(gate, repo, "commit", "-qam", "theirs")
        _git(gate, repo, "checkout", "-q", BRANCH)
        # The rebase is EXPECTED to fail: a halt is the state under test, so this one git call is deliberately not routed through the failing _git helper.
        subprocess.run(
            ["git", "-C", str(repo), "rebase", "other"],
            env={**os.environ, "GIT_EDITOR": "true"},
            capture_output=True,
            text=True,
            check=False,
        )
        # ANTI-VACUITY: a rebase that did not halt leaves HEAD on the branch, where ordinary resolution works and the cases below would pass having proven nothing. `--git-path` prints a path RELATIVE to the repository, so it is joined explicitly rather than resolved against this process's cwd.
        halted = False
        for name in ("rebase-merge", "rebase-apply"):
            candidate = repo / _git(gate, repo, "rev-parse", "--git-path", name)
            if candidate.is_dir():
                halted = True
                break
        if not halted:
            gate.log_fail(
                "fixture precondition: the rebase did not halt, so the cases below prove nothing"
            )
        gate.assertions += 1
        gate.log_pass("fixture precondition: the rebase really is halted mid-list")
        gate.assert_exit_code(
            2,
            run_guard(repo, TYPO),
            "mid-rebase: the branch is recovered from head-name, so the typo is refused",
        )
        gate.log_pass("mid-rebase: the branch is recovered from head-name, so the typo is refused")
        gate.assert_exit_code(0, run_guard(repo, REAL), "mid-rebase CONTROL: the real id passes")
        gate.log_pass("mid-rebase CONTROL: the real id passes")


def test_the_guard_is_reachable_through_the_dispatcher(gate):
    """PORT-ONLY. Every case above drives `dispatch.py <name>`; if that name were gone the dispatcher would exit non-zero for a reason unrelated to branches, and the two cases expecting a non-zero exit would pass for the wrong reason."""
    gate.log_test("the dispatcher really knows this guard by name")
    if not DISPATCH.is_file():
        gate.log_fail("the hook dispatcher is missing: %s" % paths.relative_to_root(DISPATCH))
    gate.assertions += 1
    with harness.temp_dir() as root:
        # A payload the guard has nothing to say about: no PR-TASK id, so the only way this exits non-zero is the dispatcher failing to find the guard.
        payload = json.dumps({"tool_input": {"command": "echo hello"}})
        env = dict(os.environ)
        env.pop("PR_HEAD_REF", None)
        env.pop("GITHUB_HEAD_REF", None)
        env["CLAUDE_PROJECT_DIR"] = str(root)
        proc = subprocess.run(
            ["python3", str(DISPATCH), GUARD],
            cwd=str(root),
            env=env,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        gate.assert_exit_code(
            0,
            proc.returncode,
            "dispatch.py %s on an unrelated command must exit 0 (stderr: %s)"
            % (GUARD, proc.stderr.strip()),
        )
    gate.log_pass("dispatch.py resolves %r, so the refusals above are the guard's" % GUARD)
