"""Differential: `rediacc_ci.autopilot.autopilot_push` against its twin
`.ci/scripts/autopilot/autopilot-push.sh`.

THIS IS THE SECURITY BOUNDARY'S TEST, so the first thing it establishes is that
nothing here can reach a real remote or the real checkout.

-----------------------------------------------------------------------------
THE SANDBOX, AND WHY IT IS A SHIM RATHER THAN A PROMISE
-----------------------------------------------------------------------------
Every subject runs with a curated PATH whose FIRST entry holds two fakes:

  `gh`   a recording fake. This script never calls `gh`, and the fake is here to
         PROVE that: any call at all shows up in `gh-calls.log` and every case
         asserts the log is empty. A port that grew a `gh` call would be caught
         by absence rather than by nobody noticing.
  `git`  a recording, sandbox-GUARDED shim. It logs the argv, then REFUSES with
         exit 97 unless (a) the repository it would operate on resolves inside
         the per-case sandbox directory, and (b) for `push` and `fetch`, the
         remote URL also resolves inside it. Only then does it `execv` the real
         git.

So the safety property is not "we were careful with the arguments"; it is a
control that fires. `test_the_shim_refuses_the_real_checkout` aims the shim at
`/home/developer/console` and asserts exit 97, and
`test_the_shim_refuses_a_remote_outside_the_sandbox` points a push at
`https://github.com/...` and asserts the same. Both are PLANTS: if either stops
firing, every case in this file has been running unguarded.
`test_the_fakes_win_the_path_lookup` asserts the resolution order itself, so a
stub that stopped winning would be caught too.

THE GIT CALL LOG IS A PRIMARY ARTIFACT. Which repository, in which order, with
which arguments -- staging one path at a time versus `-A`, pushing an explicit
SHA versus a branch name, whether a refusal happened BEFORE or AFTER a remote
write -- is almost entirely invisible in stdout. Every case therefore compares
the recorded git argv sequence as well as exit code, stdout and stderr.

COMMIT SHAs ARE COMPARED, and that is deliberate. `GIT_AUTHOR_DATE` and
`GIT_COMMITTER_DATE` are pinned, the fixture is built identically on both sides,
and the committer identity comes from the same flags -- so the SHA the script
prints on stdout is a function of the tree, the message and the identity. Two
sides printing the same SHA have committed the same bytes under the same name.

-----------------------------------------------------------------------------
EVERY REFUSAL BRANCH, AND WHICH ONES CANNOT BE REACHED
-----------------------------------------------------------------------------
The twin is twenty-odd refusals and three success paths. Each reachable refusal
has a case below. FIVE ARE UNREACHABLE THROUGH THE CLI and are marked as such
rather than quietly skipped, because "no test" and "cannot happen" look the same
in a test file and only one of them is acceptable:

  outcome-unknown              the validator's schema pins the enum
  stage-flag-disabled (subs)   the validator refuses submodules[] with the flag off
  submodule-missing            an absent submodule makes the parent report the
                               path NOT dirty, so the validator refuses first
  submodule-not-initialized    same route (measured: removing a submodule's
                               `.git` makes `git status` report nothing at all
                               for that path)
  submodule-branch-forbidden   the top-level branch-forbidden check has already
                               refused the same three names
  submodule-pointer-rollback   a commit made on top of HEAD is a descendant of
                               HEAD by construction

`test_the_unreachable_refusals_are_unreachable_for_the_same_reason` drives the
gate that stops each one and asserts BOTH sides stop there, which is the honest
differential for a branch neither side can enter. The `submodule-not-initialized`
predicate is additionally driven directly through the exported
`submodule_toplevel_matches`, against a real directory that is not its own
checkout -- the case whose failure mode is committing submodule content into
console as ordinary files.

K=5 LEDGER: `.ci/shadow/w7p6-autopilot-push.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import autopilot_push as ap

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "autopilot-push.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "autopilot_push.py"
BASH = shutil.which("bash") or "/bin/bash"
REAL_GIT = shutil.which("git") or "/usr/bin/git"

# `<sandbox>/tmp/tmp.AbCdEfGhIj` (bash mktemp) and `<sandbox>/tmp/tmpab12cd34`
# (Python). Applied AFTER the sandbox path itself has been folded.
WORKDIR_RE = re.compile(rb"<sandbox>/tmp/tmp\.?[A-Za-z0-9_]+")

# `diff -u` stamps each header line with the file's mtime, which is wall clock
# and therefore always different between the two runs. Only the TIMESTAMP is
# folded; the +/- lines that carry the actual evidence are compared in full.
MTIME_RE = re.compile(rb"\t\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ [+-]\d{4}")

FIXED_DATE = "2026-01-01T00:00:00+00:00"
BOT_NAME = "Autopilot Operator"
BOT_EMAIL = "operator@example.invalid"

# The recording, sandbox-guarded `git`. See the module docstring: this is a
# CONTROL, not a convenience, and two tests plant against it.
FAKE_GIT = """#!/usr/bin/python3
import os
import subprocess
import sys

REAL = os.environ["FAKE_GIT_REAL"]
SANDBOX = os.path.realpath(os.environ["FAKE_GIT_SANDBOX"])
LOG = os.environ["FAKE_GIT_LOG"]
argv = sys.argv[1:]


def inside(path):
    real = os.path.realpath(path)
    return real == SANDBOX or real.startswith(SANDBOX + os.sep)


def refuse(why):
    sys.stderr.write("FAKE-GIT REFUSED: %s\\n" % why)
    sys.exit(97)


where = os.getcwd()
if len(argv) >= 2 and argv[0] == "-C":
    where = os.path.join(where, argv[1])
if not inside(where):
    refuse("%s is outside the sandbox %s" % (os.path.realpath(where), SANDBOX))

for verb in ("push", "fetch"):
    if verb in argv:
        # The remote is the first NON-FLAG token after the verb: `fetch -q
        # origin work` puts `-q` where a naive index+1 would look, and reading
        # `-q` as the remote made the shim refuse a call it should have allowed.
        rest = argv[argv.index(verb) + 1 :]
        remote = next((a for a in rest if not a.startswith("-")), "")
        got = subprocess.run(
            [REAL, "-C", where, "remote", "get-url", remote],
            capture_output=True,
            text=True,
        )
        url = got.stdout.strip()
        if not url or "://" in url or not inside(os.path.join(where, url)):
            refuse("%s to remote %r (url %r) would leave the sandbox" % (verb, remote, url))

with open(LOG, "a") as handle:
    handle.write("\\t".join(argv) + "\\n")
os.execv(REAL, [REAL] + argv)
"""

# A recording fake `gh`. This script must never call it; the log proves it.
FAKE_GH = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_GH_LOG"], "a") as handle:
    handle.write("\\t".join(sys.argv[1:]) + "\\n")
sys.stderr.write("gh: this script must not call gh\\n")
sys.exit(1)
"""


def _stub_bin(sandbox: pathlib.Path) -> str:
    """The curated PATH: the two fakes FIRST, then the real one.

    PREPENDED rather than reduced to a symlink farm, because both subjects reach
    node, jq, diff, sort and a long tail of coreutils through `common.sh`. The
    safety property is therefore RESOLUTION ORDER plus the shim's own refusals,
    and all three are asserted rather than assumed.
    """
    stub = sandbox / "stubbin"
    stub.mkdir(exist_ok=True)
    for name, body in (("git", FAKE_GIT), ("gh", FAKE_GH)):
        path = stub / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _git(cwd: pathlib.Path, *args: str, check: bool = True) -> str:
    """Real git, for FIXTURE BUILDING only. Never on the subjects' PATH."""
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_DATE": FIXED_DATE,
            "GIT_COMMITTER_DATE": FIXED_DATE,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
    )
    proc = subprocess.run(
        [REAL_GIT, "-C", str(cwd), *args], capture_output=True, text=True, env=env, check=False
    )
    if check and proc.returncode != 0:
        raise AssertionError("fixture git %s failed: %s" % (args, proc.stderr))
    return proc.stdout.strip()


def _init(path: pathlib.Path, branch: str, email: str = BOT_EMAIL, name: str = BOT_NAME) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", branch)
    _git(path, "config", "user.email", email)
    _git(path, "config", "user.name", name)


def build(
    sandbox: pathlib.Path,
    *,
    submodule: bool = False,
    branch: str = "work",
    remote: bool = True,
    sub_remote: bool = True,
) -> pathlib.Path:
    """One console checkout, optionally with a `private/renet` submodule.

    The submodule gitlink is written with `update-index --cacheinfo` rather than
    `git submodule add`, which keeps the fixture free of `protocol.file.allow`
    and leaves the submodule as a plain nested checkout -- exactly the shape
    `rev-parse --show-toplevel` is asked about in the twin.
    """
    console = sandbox / "console"
    if submodule:
        sub = console / "private" / "renet"
        _init(sub, "main")
        (sub / "main.go").write_text("package main\n", encoding="utf-8")
        _git(sub, "add", "--", "main.go")
        _git(sub, "commit", "-q", "-m", "base")
        if sub_remote:
            bare = sandbox / "renet.git"
            # `--initial-branch=main` matters: a bare repo whose HEAD names a
            # branch that does not exist clones as EMPTY, and an "orphan" built
            # in that clone would be a ROOT commit -- which would make the
            # adoption cases pass through the unrelated-history arm instead of
            # the one they are aimed at.
            _git(sandbox, "init", "-q", "--bare", "--initial-branch=main", str(bare))
            _git(sub, "remote", "add", "origin", str(bare))
            _git(sub, "push", "-q", "origin", "main")
    _init(console, branch)
    (console / "README.md").write_text("hello\n", encoding="utf-8")
    _git(console, "add", "--", "README.md")
    if submodule:
        (console / ".gitmodules").write_text(
            '[submodule "private/renet"]\n\tpath = private/renet\n\turl = ../renet.git\n',
            encoding="utf-8",
        )
        _git(console, "add", "--", ".gitmodules")
        sub_sha = _git(console / "private" / "renet", "rev-parse", "HEAD")
        _git(console, "update-index", "--add", "--cacheinfo", "160000,%s,private/renet" % sub_sha)
    _git(console, "commit", "-q", "-m", "base")
    if remote:
        bare = sandbox / "console.git"
        _git(sandbox, "init", "-q", "--bare", str(bare))
        _git(console, "remote", "add", "origin", str(bare))
    return console


def handoff(console: pathlib.Path, **fields) -> None:
    body = {
        "schema": "rediacc-autopilot-handoff/1",
        "base_head": _git(console, "rev-parse", "HEAD"),
        "outcome": "push",
        "ledger_line": "r1 | run 1 | did the thing",
    }
    body.update(fields)
    (console / "handoff.json").write_text(json.dumps(body), encoding="utf-8")


def _run(subject: pathlib.Path, sandbox: pathlib.Path, argv: list[str], env_extra: dict[str, str]):
    git_log = sandbox / "git-calls.log"
    gh_log = sandbox / "gh-calls.log"
    git_log.write_text("", encoding="utf-8")
    gh_log.write_text("", encoding="utf-8")
    tmpdir = sandbox / "tmp"
    tmpdir.mkdir(exist_ok=True)
    env = {
        "PATH": _stub_bin(sandbox),
        "HOME": str(sandbox),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GIT_REAL": REAL_GIT,
        "FAKE_GIT_SANDBOX": str(sandbox),
        "FAKE_GIT_LOG": str(git_log),
        "FAKE_GH_LOG": str(gh_log),
        "GIT_AUTHOR_DATE": FIXED_DATE,
        "GIT_COMMITTER_DATE": FIXED_DATE,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "AUTOPILOT_GIT_NAME": BOT_NAME,
        "AUTOPILOT_GIT_EMAIL": BOT_EMAIL,
        # A leaked real `gh` would fail auth rather than write anything.
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(sandbox / "gh-config"),
        # Both mktemp implementations honour TMPDIR, so the work
        # directory lands inside the sandbox rather than in the shared
        # /tmp -- and the shim's own guard therefore covers it too.
        "TMPDIR": str(tmpdir),
    }
    env.update(env_extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(sandbox),
        timeout=300,
    )
    marker = str(sandbox).encode()

    def scrub(raw: bytes) -> bytes:
        # The sandbox path first, then the per-run work directory. `mktemp -d`
        # and `tempfile.mkdtemp` pick different random suffixes, and the twin
        # prints that path in the `commit -F` argv -- so a comparison that did
        # not fold it would diverge on every case for a reason that says nothing
        # about the port. TMPDIR is pinned INSIDE the sandbox so the fold cannot
        # accidentally swallow anything else.
        folded = WORKDIR_RE.sub(b"<work>", raw.replace(marker, b"<sandbox>"))
        return MTIME_RE.sub(b"\t<mtime>", folded)

    git_calls = [scrub(line.encode()).decode() for line in git_log.read_text().splitlines() if line]
    gh_calls = [line for line in gh_log.read_text().splitlines() if line]
    return proc.returncode, scrub(proc.stdout), scrub(proc.stderr), git_calls, gh_calls


def _sides(
    name: str,
    scenario,
    argv,
    *,
    env: dict[str, str] | None = None,
):
    """Both subjects, two identical private sandboxes.

    `scenario(sandbox) -> console` builds the tree; `argv` is either a list or a
    callable taking the console path, because most cases need to name it.
    """
    env_extra = {"AUTOPILOT_ALLOW_PUSH": "true"}
    env_extra.update(env or {})
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            sandbox = pathlib.Path(td) / subject.stem
            sandbox.mkdir(parents=True)
            console = scenario(sandbox)
            resolved = argv(console) if callable(argv) else list(argv)
            results.append(_run(subject, sandbox, resolved, env_extra))
    old, new = results
    labels = ("exit", "stdout", "stderr", "git calls", "gh calls")
    for i, label in enumerate(labels):
        assert new[i] == old[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old[i],
            new[i],
        )
    return old


def base_argv(console: pathlib.Path, *extra: str) -> list[str]:
    return [
        "--root",
        str(console),
        "--handoff",
        str(console / "handoff.json"),
        "--branch",
        "work",
        *extra,
    ]


# ---------------------------------------------------------------------------
# CONTROLS. These come first because everything below is worthless without them.
# ---------------------------------------------------------------------------


def test_the_fakes_win_the_path_lookup() -> None:
    """If the stubs ever stop winning, every case in this file has been talking
    to the real git and the real GitHub CLI."""
    with tempfile.TemporaryDirectory() as td:
        sandbox = pathlib.Path(td)
        path = _stub_bin(sandbox)
        for name in ("git", "gh"):
            resolved = shutil.which(name, path=path)
            assert resolved == str(sandbox / "stubbin" / name), (
                "the fake %s does not win the PATH lookup: %r" % (name, resolved)
            )


def test_the_shim_refuses_the_real_checkout() -> None:
    """A PLANT. Aim the shim at this repository and it must refuse, so a case
    that ever escaped its sandbox cannot touch the tree the operator is using."""
    with tempfile.TemporaryDirectory() as td:
        sandbox = pathlib.Path(td)
        stub = _stub_bin(sandbox).split(":")[0]
        env = dict(os.environ)
        env.update(
            {
                "FAKE_GIT_REAL": REAL_GIT,
                "FAKE_GIT_SANDBOX": str(sandbox),
                "FAKE_GIT_LOG": str(sandbox / "log"),
                "PATH": "%s:%s" % (stub, os.environ["PATH"]),
            }
        )
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True,
            env=env,
            check=False,
            cwd=str(sandbox),
        )
        assert proc.returncode == 97, "the shim let a command reach %s" % ROOT
        assert b"FAKE-GIT REFUSED" in proc.stderr
        assert not (sandbox / "log").exists(), "a refused call was still recorded as made"


def test_the_shim_refuses_a_remote_outside_the_sandbox() -> None:
    """The other half of the plant: a push whose remote is not a path inside the
    sandbox must never reach the network."""
    with tempfile.TemporaryDirectory() as td:
        sandbox = pathlib.Path(td)
        stub = _stub_bin(sandbox).split(":")[0]
        repo = sandbox / "repo"
        _init(repo, "work")
        (repo / "f").write_text("x", encoding="utf-8")
        _git(repo, "add", "--", "f")
        _git(repo, "commit", "-q", "-m", "c")
        _git(repo, "remote", "add", "origin", "https://github.com/rediacc/console.git")
        env = dict(os.environ)
        env.update(
            {
                "FAKE_GIT_REAL": REAL_GIT,
                "FAKE_GIT_SANDBOX": str(sandbox),
                "FAKE_GIT_LOG": str(sandbox / "log"),
                "PATH": "%s:%s" % (stub, os.environ["PATH"]),
            }
        )
        proc = subprocess.run(
            ["git", "-C", str(repo), "push", "origin", "HEAD:refs/heads/work"],
            capture_output=True,
            env=env,
            check=False,
            cwd=str(sandbox),
            timeout=60,
        )
        assert proc.returncode == 97, "a push to github.com was not refused"
        assert b"would leave the sandbox" in proc.stderr


# ---------------------------------------------------------------------------
# The refusals before anything is read
# ---------------------------------------------------------------------------


def _plain(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "src.txt").write_text("changed\n", encoding="utf-8")
    _git(console, "add", "--", "src.txt")
    handoff(console, files=["src.txt"], commit_message="fix: the thing")
    return console


def test_usage_refusals() -> None:
    for drop in ("--root", "--handoff", "--branch"):

        def argv(console, drop=drop):
            full = base_argv(console)
            out, skip = [], False
            for token in full:
                if skip:
                    skip = False
                    continue
                if token == drop:
                    skip = True
                    continue
                out.append(token)
            return out

        code, _, stderr, git_calls, gh_calls = _sides("usage%s" % drop, _plain, argv)
        assert code == 2, drop
        assert b"usage: autopilot-push.sh" in stderr
        assert git_calls == [], "git ran before the arguments were checked"
        assert gh_calls == []


def test_a_root_that_is_not_a_directory_is_refused_by_name() -> None:
    code, _, stderr, git_calls, _ = _sides(
        "root-missing",
        _plain,
        lambda console: ["--root", str(console / "nope"), "--handoff", "h", "--branch", "work"],
    )
    assert code == 1
    assert b"Required directory" in stderr
    assert git_calls == []


def test_the_stage_flag_fails_closed_before_any_git_runs() -> None:
    """Absent is OFF; only the exact string `true` arms the push. And the refusal
    happens BEFORE the tree is read, so a misconfigured stage cannot even look."""
    for name, value in (("unset", ""), ("false", "false"), ("uppercase", "TRUE"), ("one", "1")):
        code, _, stderr, git_calls, _ = _sides(
            "flag-%s" % name, _plain, base_argv, env={"AUTOPILOT_ALLOW_PUSH": value}
        )
        assert code == 1, name
        assert b"stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'" in stderr
        assert git_calls == [], "the tree was read with the stage flag off"


def test_a_dry_run_needs_no_stage_flag() -> None:
    """The exemption is deliberate and narrow: a dry run never writes a remote.
    Pinned in both directions so a port cannot widen or close it."""
    code, stdout, _, git_calls, _ = _sides(
        "dry-run-no-flag",
        _plain,
        lambda console: base_argv(console, "--dry-run"),
        env={"AUTOPILOT_ALLOW_PUSH": ""},
    )
    assert code == 0
    assert git_calls, "the dry run did nothing at all"
    assert not any("push" in call.split("\t") for call in git_calls), "a dry run pushed"
    assert len(stdout.strip().split(b"\n")[-1]) == 40, "no sha was printed"


def test_the_committer_identity_is_required() -> None:
    """The commits are attributed to the operator's noreply identity
    (03-v2-autonomy.md section 0). An unset identity is a refusal, not a
    fallback to whatever the runner happens to have configured."""
    for missing in ("AUTOPILOT_GIT_NAME", "AUTOPILOT_GIT_EMAIL"):
        code, _, stderr, git_calls, _ = _sides(
            "identity-%s" % missing, _plain, base_argv, env={missing: ""}
        )
        assert code == 1, missing
        assert ("Required environment variable '%s' is not set" % missing).encode() in stderr
        assert git_calls == []


def test_branch_mismatch_refuses_before_reading_the_handoff() -> None:
    code, _, stderr, git_calls, _ = _sides(
        "branch-mismatch",
        _plain,
        lambda console: [
            "--root",
            str(console),
            "--handoff",
            str(console / "handoff.json"),
            "--branch",
            "some-other-branch",
        ],
    )
    assert code == 1
    assert b"branch-mismatch: checkout is on 'work', caller named 'some-other-branch'" in stderr
    assert git_calls == ["rev-parse\t--abbrev-ref\tHEAD"], git_calls


def test_the_default_branches_are_refused_unconditionally() -> None:
    """renet/account/elite have no rulesets, so this is their only guard. The
    checkout is genuinely ON the branch, so the mismatch check passes and this is
    the thing doing the refusing."""
    for branch in ("main", "master"):

        def scenario(sandbox, branch=branch):
            console = build(sandbox, branch=branch)
            (console / "src.txt").write_text("x\n", encoding="utf-8")
            handoff(console, files=["src.txt"], commit_message="m")
            return console

        code, _, stderr, git_calls, _ = _sides(
            "forbidden-%s" % branch,
            scenario,
            lambda console, branch=branch: [
                "--root",
                str(console),
                "--handoff",
                str(console / "handoff.json"),
                "--branch",
                branch,
            ],
        )
        assert code == 1, branch
        assert ("branch-forbidden: the autopilot never pushes '%s'" % branch).encode() in stderr
        assert len(git_calls) == 1, "the tree was read after the branch was refused"


def test_a_detached_head_is_refused_as_the_literal_head() -> None:
    """`git rev-parse --abbrev-ref HEAD` answers `HEAD` when detached, and the
    caller naming `HEAD` therefore passes the mismatch check -- which is exactly
    why `HEAD` is in the forbidden list beside main and master."""

    def scenario(sandbox):
        console = build(sandbox)
        _git(console, "checkout", "-q", "--detach")
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        handoff(console, files=["src.txt"], commit_message="m")
        return console

    code, _, stderr, _, _ = _sides(
        "forbidden-head",
        scenario,
        lambda console: [
            "--root",
            str(console),
            "--handoff",
            str(console / "handoff.json"),
            "--branch",
            "HEAD",
        ],
    )
    assert code == 1
    assert b"branch-forbidden: the autopilot never pushes 'HEAD'" in stderr


# ---------------------------------------------------------------------------
# The validator, and the three outcomes
# ---------------------------------------------------------------------------


def test_a_rejected_handoff_stages_nothing() -> None:
    """Four rejection classes, one assertion each, and the same consequence:
    nothing staged, nothing pushed, exit 1."""

    def missing(sandbox):
        console = build(sandbox)
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        return console

    def stale(sandbox):
        console = build(sandbox)
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        handoff(console, base_head="0" * 40, files=["src.txt"], commit_message="m")
        return console

    def undeclared(sandbox):
        console = build(sandbox)
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        (console / "sneaky.txt").write_text("y\n", encoding="utf-8")
        handoff(console, files=["src.txt"], commit_message="m")
        return console

    def workflow(sandbox):
        console = build(sandbox)
        (console / ".github").mkdir()
        (console / ".github" / "ci.yml").write_text("on: push\n", encoding="utf-8")
        handoff(console, files=[".github/ci.yml"], commit_message="m")
        return console

    for name, scenario, needle in (
        ("no-handoff", missing, b"handoff-missing"),
        ("stale-base", stale, b"base-head-mismatch"),
        ("undeclared", undeclared, b"undeclared-dirty"),
        ("workflow", workflow, b"denylist-github"),
    ):
        code, stdout, stderr, git_calls, _ = _sides("reject-%s" % name, scenario, base_argv)
        assert code == 1, name
        assert needle in stderr, name
        assert b"handoff rejected; escalating (nothing staged, nothing pushed)" in stderr
        assert stdout == b""
        assert not any(call.split("\t")[0] in ("add", "commit", "push") for call in git_calls), (
            "%s: something was staged after a rejected handoff" % name
        )


def test_escalate_and_no_change_are_round_results_not_failures() -> None:
    """Exit 0, nothing staged. Exiting 1 here (as the twin did until 2026-08-09)
    made every escalating round paint the job red, which fired the generic
    failure latch and LOST the model's reason."""
    for outcome in ("escalate", "no-change"):

        def scenario(sandbox, outcome=outcome):
            console = build(sandbox)
            extra = {"escalation": {"reason": "needs a human"}} if outcome == "escalate" else {}
            handoff(console, outcome=outcome, **extra)
            return console

        code, _, stderr, git_calls, _ = _sides(
            "outcome-%s" % outcome,
            scenario,
            lambda console: base_argv(console, "--verdict-out", str(console.parent / "v.json")),
        )
        assert code == 0, outcome
        assert (
            "outcome-%s: validated round, nothing staged and nothing pushed" % outcome
        ).encode() in stderr
        assert not any(call.split("\t")[0] in ("add", "commit", "push") for call in git_calls)


def test_the_verdict_is_published_on_every_accepted_round() -> None:
    """BEFORE any outcome branching, so the post-boundary steps see the same
    validated object whether the round pushed, escalated or did nothing."""
    for outcome in ("escalate", "no-change", "push"):
        with tempfile.TemporaryDirectory() as td:
            sandbox = pathlib.Path(td)
            console = build(sandbox)
            if outcome == "push":
                (console / "src.txt").write_text("x\n", encoding="utf-8")
                handoff(console, files=["src.txt"], commit_message="m")
            elif outcome == "escalate":
                handoff(console, outcome=outcome, escalation={"reason": "r"})
            else:
                handoff(console, outcome=outcome)
            out = sandbox / "verdict-out.json"
            code, _, _, _, _ = _run(
                PORT,
                sandbox,
                base_argv(console, "--verdict-out", str(out), "--dry-run"),
                {"AUTOPILOT_ALLOW_PUSH": "true"},
            )
            assert code == 0, outcome
            assert json.loads(out.read_text())["outcome"] == outcome


def test_the_verdict_can_be_written_to_a_fifo() -> None:
    """`--verdict-out /dev/stdout` is what a workflow step passes when it wants
    the verdict in the run log, and `cat A >B` does not care that B is a pipe.

    THIS CAUGHT A REAL DIVERGENCE while porting: `shutil.copyfile` raises
    `SpecialFileError` on a fifo, so the port died where the twin wrote. Pinned
    so the plain open-and-write cannot be "tidied" back into a copyfile.

    ONE HARNESS NOTE, so a reader who sees this fail elsewhere does not go
    hunting the port. Under `subprocess.PIPE` (here) the reopen succeeds on both
    sides; under NODE's spawnSync it does not, because libuv backs a stdio pipe
    with a socketpair and reopening a socket through `/proc/self/fd` is ENXIO.
    The shadow-gate ledger scenario therefore writes the verdict to a real file
    and `cat`s it, and the two sides differ there only in the WORDING of the
    refusal -- bash names its own line number, which no port can honestly
    reproduce. `test_an_unwritable_verdict_out_stops_the_round` pins the part
    that matters (exit 1, nothing staged); the live workflow passes
    `$RUNNER_TEMP/verdict.json`, so the diverging wording is off the real
    path."""

    def scenario(sandbox):
        console = build(sandbox)
        handoff(console, outcome="escalate", escalation={"reason": "needs a human"})
        return console

    code, stdout, stderr, _, _ = _sides(
        "verdict-out-fifo",
        scenario,
        lambda console: base_argv(console, "--verdict-out", "/dev/stdout"),
    )
    assert code == 0, stderr
    assert json.loads(stdout.decode())["outcome"] == "escalate"


def test_an_unwritable_verdict_out_stops_the_round() -> None:
    """Exit 1 either way; the twin says it in bash's words and the port in its
    own, which is the one place the two diverge on fd 2. Compared on the code
    and on the fact that nothing was staged, not on the sentence."""
    with tempfile.TemporaryDirectory() as td:
        sandbox = pathlib.Path(td)
        console = build(sandbox)
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        handoff(console, files=["src.txt"], commit_message="m")
        results = [
            _run(
                subject,
                sandbox,
                base_argv(console, "--verdict-out", str(sandbox / "nodir" / "v.json")),
                {"AUTOPILOT_ALLOW_PUSH": "true"},
            )
            for subject in (TWIN, PORT)
        ]
    for code, stdout, _, git_calls, _ in results:
        assert code == 1
        assert stdout == b""
        assert not any(call.split("\t")[0] in ("add", "commit", "push") for call in git_calls)


# ---------------------------------------------------------------------------
# The console staging path
# ---------------------------------------------------------------------------


def test_the_happy_path_commits_and_pushes_one_explicit_sha() -> None:
    """PUSH BY EXPLICIT SHA, never a bare branch name: the ref that leaves this
    machine is exactly the commit minted a line earlier."""
    code, stdout, stderr, git_calls, gh_calls = _sides("push", _plain, base_argv)
    assert code == 0
    # stdout carries the tripwire's own quiet line first; the SHA is the last.
    lines = stdout.decode().strip().split("\n")
    assert lines[0].startswith("exfil-tripwire quiet: "), stdout
    sha = lines[-1]
    assert len(sha) == 40, stdout
    assert git_calls[-1] == "push\torigin\t%s:refs/heads/work" % sha, git_calls[-1]
    assert "add\t--\tsrc.txt" in git_calls, "the file was not staged one path at a time"
    assert not any(
        call.startswith(("add\t-A", "add\t--all")) or call == "add\t." for call in git_calls
    ), "wholesale staging"
    assert ("pushed %s to origin refs/heads/work" % sha).encode() in stderr
    assert gh_calls == []


def test_a_pathspec_that_expands_is_refused_before_the_commit() -> None:
    """STAGED-SET EQUALITY, and the case it exists for. An UNTRACKED DIRECTORY is
    reported by `git status` as `dir/`, which the validator accepts as a declared
    path -- and `git add -- dir/` then stages its two FILES. The staged set is
    therefore not the declared set, and the round stops with the unified diff on
    fd 2 as the evidence."""

    def scenario(sandbox):
        console = build(sandbox)
        (console / "newdir").mkdir()
        (console / "newdir" / "a.txt").write_text("a\n", encoding="utf-8")
        (console / "newdir" / "b.txt").write_text("b\n", encoding="utf-8")
        handoff(console, files=["newdir/"], commit_message="m")
        return console

    code, stdout, stderr, git_calls, _ = _sides("expanding-pathspec", scenario, base_argv)
    assert code == 1
    assert b"staged-set-mismatch: the staged set does not equal the validated files[]" in stderr
    assert b"+newdir/a.txt" in stderr, "the unified diff evidence is missing from fd 2"
    assert b"-newdir/" in stderr
    assert not any(call.split("\t")[0] in ("commit", "push") for call in git_calls)
    assert stdout == b""


def test_the_tripwire_stops_the_commit_before_it_is_made() -> None:
    """Rule 2: any single NEW file adding more than 8 KB trips, regardless of
    prefix. The diff is never uploaded and never printed -- byte counts and paths
    only -- because console artifacts are public."""

    def scenario(sandbox):
        console = build(sandbox)
        (console / "blob.txt").write_text("x" * 9000 + "\n", encoding="utf-8")
        handoff(console, files=["blob.txt"], commit_message="m")
        return console

    code, _, stderr, git_calls, _ = _sides("tripwire", scenario, base_argv)
    assert code == 1
    assert b"TRIPWIRE:" in stderr
    assert b"tripwire tripped; escalating (nothing committed, nothing pushed)" in stderr
    assert b"xxxxxxxxxx" not in stderr, "the suspected diff content was printed"
    assert not any(call.split("\t")[0] in ("commit", "push") for call in git_calls)


def test_the_failed_jobs_path_is_one_argument_even_with_a_space() -> None:
    """`${FAILED_JOBS:+--failed-jobs "$FAILED_JOBS"}` keeps the inner quotes, so a
    path with a space is ONE argument. A port that split it would hand node an
    unknown argument and the round would die for the wrong reason."""

    def scenario(sandbox):
        console = build(sandbox)
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        (sandbox / "failed jobs.txt").write_text("Quality / code\n", encoding="utf-8")
        handoff(console, files=["src.txt"], commit_message="m")
        return console

    code, stdout, stderr, _, _ = _sides(
        "failed-jobs-space",
        scenario,
        lambda console: base_argv(
            console, "--failed-jobs", str(console.parent / "failed jobs.txt"), "--dry-run"
        ),
    )
    assert code == 0, stderr
    assert b"exfil-tripwire quiet:" in stdout
    assert b"unknown argument" not in stderr


def test_a_console_push_failure_is_the_scripts_last_word() -> None:
    """No remote for console: the submodule half (there is none here) and every
    validation have passed, and the failure surfaces as git's own status."""

    def scenario(sandbox):
        console = build(sandbox, remote=False)
        # A remote INSIDE the sandbox (so the shim allows the attempt) that is
        # not a repository (so real git refuses it). Pointing it outside would
        # test the shim instead of the script.
        _git(console, "remote", "add", "origin", str(sandbox / "gone.git"))
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        handoff(console, files=["src.txt"], commit_message="m")
        return console

    code, stdout, stderr, git_calls, _ = _sides("console-push-fails", scenario, base_argv)
    assert code == 128, "git's own status, not the shim's 97 and not a smoothed 1"
    assert b"does not appear to be a git repository" in stderr
    # The tripwire's quiet line is on stdout; the SHA is NOT, because `set -e`
    # ends the run on git's status before the `echo`.
    assert b"exfil-tripwire quiet:" in stdout
    assert not any(len(line) == 40 for line in stdout.decode().strip().split("\n")), (
        "a sha was printed for a push that did not happen"
    )
    assert any(call.startswith("push\t") for call in git_calls)


# ---------------------------------------------------------------------------
# Submodules: phase 1, phase 2 and the ordering that makes the split worth it
# ---------------------------------------------------------------------------


def _sub_scenario(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox, submodule=True)
    (console / "private" / "renet" / "main.go").write_text(
        "package main\n// edited\n", encoding="utf-8"
    )
    handoff(
        console,
        files=["private/renet"],
        commit_message="chore: bump renet",
        submodules=[
            {"path": "private/renet", "files": ["main.go"], "message": "fix: edit the go file"}
        ],
    )
    return console


SUB_ENV = {"AUTOPILOT_ALLOW_SUBMODULES": "true"}


def test_submodules_are_committed_then_pushed_before_console() -> None:
    """THE ORDER IS THE DESIGN. The submodule push must precede the console push,
    so the pointer console publishes always names a commit that already exists on
    the remote. The reverse order publishes a console commit pointing at a SHA
    nobody else can fetch."""
    code, stdout, stderr, git_calls, _ = _sides("sub-push", _sub_scenario, base_argv, env=SUB_ENV)
    assert code == 0, stderr
    pushes = [call for call in git_calls if "push" in call.split("\t")]
    assert len(pushes) == 2, pushes
    assert pushes[0].startswith("-C\t<sandbox>/console/private/renet\tpush\t"), pushes[0]
    assert pushes[1].startswith("push\torigin\t"), pushes[1]
    assert b"gitlink verified: private/renet -> " in stderr
    assert b"all repos validated; nothing has been pushed yet" in stderr
    # And that line arrives BEFORE the first push, which is the whole claim.
    assert stderr.index(b"all repos validated") < stderr.index(b"pushed ")
    assert stdout.decode().strip().split("\n")[-1] == _last_sha(git_calls)


def _last_sha(git_calls: list[str]) -> str:
    for call in reversed(git_calls):
        parts = call.split("\t")
        if parts[0] == "push":
            return parts[2].split(":")[0]
    raise AssertionError("no console push in %r" % git_calls)


def test_a_submodule_refusal_leaves_zero_remote_writes() -> None:
    """The reason the phases are split. A file declared in the submodule that is
    neither tracked nor on disk stops the round in phase 1, before anything has
    been pushed anywhere."""

    def scenario(sandbox):
        console = _sub_scenario(sandbox)
        handoff(
            console,
            files=["private/renet"],
            commit_message="m",
            submodules=[
                {"path": "private/renet", "files": ["main.go", "ghost.go"], "message": "fix: x"}
            ],
        )
        return console

    code, _, stderr, git_calls, _ = _sides("sub-path-missing", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert (
        b"submodule-path-missing: 'private/renet/ghost.go' is declared but is neither "
        b"tracked in the submodule nor present on disk" in stderr
    )
    assert not any("push" in call.split("\t") for call in git_calls), "a remote was written"


def test_a_submodule_staged_set_mismatch_refuses() -> None:
    """The identical check the console boundary applies, because a pathspec that
    expands is the same bug here. Driven with a file the model left ALREADY
    STAGED in the submodule index and did not declare."""

    def scenario(sandbox):
        console = _sub_scenario(sandbox)
        sub = console / "private" / "renet"
        (sub / "extra.go").write_text("package main\n", encoding="utf-8")
        _git(sub, "add", "--", "extra.go")
        return console

    code, _, stderr, git_calls, _ = _sides("sub-staged-mismatch", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert b"submodule-staged-set-mismatch: 'private/renet' staged set" in stderr
    assert b"+extra.go" in stderr, "the unified diff evidence is missing"
    assert not any("push" in call.split("\t") for call in git_calls)


def test_the_submodule_tripwire_sees_parent_relative_paths() -> None:
    """The prefixes are rewritten to `a/private/renet/` so the same scope map
    that governs a console fix governs this one; without them every byte would
    look out of scope."""

    def scenario(sandbox):
        console = build(sandbox, submodule=True)
        sub = console / "private" / "renet"
        (sub / "blob.txt").write_text("y" * 9000 + "\n", encoding="utf-8")
        handoff(
            console,
            files=["private/renet"],
            commit_message="m",
            submodules=[{"path": "private/renet", "files": ["blob.txt"], "message": "fix: x"}],
        )
        return console

    code, _, stderr, git_calls, _ = _sides("sub-tripwire", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert b"private/renet/blob.txt" in stderr, "the tripwire saw a submodule-relative path"
    assert (
        b"tripwire tripped in submodule 'private/renet'; escalating "
        b"(nothing committed there, nothing pushed)" in stderr
    )
    assert not any("commit" in call.split("\t") for call in git_calls)


def test_the_submodule_branch_is_created_at_current_head() -> None:
    """NOT at origin/main. Section 5's anti-rollback rule is ancestry, and
    branching at the recorded pointer makes it true by construction; branching at
    origin/main would silently rebase the round's work onto a different base."""
    code, _, stderr, git_calls, _ = _sides("sub-branch", _sub_scenario, base_argv, env=SUB_ENV)
    assert code == 0, stderr
    assert "-C\t<sandbox>/console/private/renet\tcheckout\t-q\t-b\twork" in git_calls, git_calls
    assert not any("origin/main" in call for call in git_calls), (
        "the branch was created somewhere other than current HEAD"
    )


def test_an_existing_local_branch_in_the_submodule_refuses() -> None:
    """Checking it out would move HEAD across a tree the model has already
    edited. Refuse rather than guess which side wins."""

    def scenario(sandbox):
        console = _sub_scenario(sandbox)
        sub = console / "private" / "renet"
        _git(sub, "branch", "work")
        return console

    code, _, stderr, git_calls, _ = _sides("sub-branch-exists", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert (
        b"submodule-branch-exists: 'private/renet' already has a local 'work' but HEAD is on "
        b"'main'; refusing to move HEAD across the round's edits" in stderr
    )
    assert not any(call.split("\t")[-1].startswith("checkout") for call in git_calls)


def test_a_submodule_push_that_is_not_a_non_fast_forward_refuses_to_guess() -> None:
    """The adoption path exists for ONE failure shape. Anything else stops the
    round rather than rewriting a branch on a hunch."""

    def scenario(sandbox):
        console = build(sandbox, submodule=True, sub_remote=False)
        _git(console / "private" / "renet", "remote", "add", "origin", str(sandbox / "gone.git"))
        (console / "private" / "renet" / "main.go").write_text("package main\n//e\n", "utf-8")
        handoff(
            console,
            files=["private/renet"],
            commit_message="m",
            submodules=[{"path": "private/renet", "files": ["main.go"], "message": "fix: x"}],
        )
        return console

    code, _, stderr, git_calls, _ = _sides("sub-push-failed", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert (
        b"submodule-push-failed: 'private/renet' push failed for a reason that is not a "
        b"non-fast-forward; refusing to guess" in stderr
    )
    assert not any(call.startswith("push\t") for call in git_calls), "console was pushed anyway"


# ---------------------------------------------------------------------------
# The orphan adoption, which is the most dangerous code in the file
# ---------------------------------------------------------------------------


def _orphan(sandbox: pathlib.Path, *, email: str, with_main: bool, conflicting: bool):
    """Put a commit on the submodule remote's `work` branch, so this round's push
    is rejected as a non-fast-forward.

    Built in a SEPARATE clone so the round's own submodule checkout is untouched,
    which is the real shape: the orphan was left by a PREVIOUS round.
    """
    console = build(sandbox, submodule=True)
    bare = sandbox / "renet.git"
    if with_main:
        # A continuation of the submodule's own history: cloned from the remote,
        # so it shares main's merge-base.
        work = sandbox / "orphan-work"
        _git(sandbox, "clone", "-q", str(bare), str(work))
        assert (work / "main.go").exists(), "the clone came up empty; the orphan would be a root"
        _git(work, "config", "user.email", email)
        _git(work, "config", "user.name", "Whoever")
        _git(work, "checkout", "-q", "-b", "work")
        body = "package main\n// orphan\n" if not conflicting else "package main\n// theirs\n"
        (work / "main.go").write_text(body, encoding="utf-8")
        _git(work, "add", "--", "main.go")
        _git(work, "commit", "-q", "-m", "orphan round")
    else:
        # An UNRELATED history: a fresh repository, so its root commit shares no
        # merge-base with the submodule's main at all.
        work = sandbox / "unrelated"
        _init(work, "work", email=email, name="Whoever")
        (work / "other.go").write_text("package other\n", encoding="utf-8")
        _git(work, "add", "--", "other.go")
        _git(work, "commit", "-q", "-m", "unrelated branch")
        _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", "work")
    (console / "private" / "renet" / "main.go").write_text(
        "package main\n// ours\n", encoding="utf-8"
    )
    handoff(
        console,
        files=["private/renet"],
        commit_message="chore: bump renet",
        submodules=[{"path": "private/renet", "files": ["main.go"], "message": "fix: ours"}],
    )
    return console


def test_a_foreign_branch_is_never_rewritten() -> None:
    """ "Ours" is TWO independent facts and this is the first: the tip's committer
    email must be the autopilot identity. Somebody else's branch stops the round
    even though it sits at exactly the name this round wants."""

    def scenario(sandbox):
        return _orphan(sandbox, email="stranger@example.invalid", with_main=True, conflicting=False)

    code, _, stderr, git_calls, _ = _sides("adopt-foreign", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert b"submodule-foreign-branch: 'private/renet' branch 'work' already exists at" in stderr
    assert b"rather than the autopilot identity" in stderr
    assert not any(call.startswith("push\t") for call in git_calls), "console was pushed anyway"


def test_an_unrelated_history_is_never_built_on() -> None:
    """The second fact: the tip must share this round's merge-base with
    origin/main. A branch that merely happens to sit at the same name is not a
    continuation of this line of work."""

    def scenario(sandbox):
        return _orphan(sandbox, email=BOT_EMAIL, with_main=False, conflicting=False)

    code, _, stderr, _, _ = _sides("adopt-unrelated", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert b"submodule-unrelated-branch: 'private/renet' remote tip" in stderr
    assert b"refusing to build on an unrelated history" in stderr


def test_an_unresolvable_main_refuses_rather_than_adopting_on_identity_alone() -> None:
    """BOTH checks are required, so an unresolvable main is a REFUSAL, not a
    skip. A committer email is forgeable by anyone who can push, which makes the
    identity check the weaker half; failing closed is the only reading under
    which "both required" is true."""

    def scenario(sandbox):
        console = _orphan(sandbox, email=BOT_EMAIL, with_main=True, conflicting=False)
        # BOTH copies have to go: the remote-tracking ref the submodule already
        # holds, and the branch on the remote that a fetch would restore it from.
        _git(sandbox / "renet.git", "update-ref", "-d", "refs/heads/main")
        _git(console / "private" / "renet", "update-ref", "-d", "refs/remotes/origin/main")
        return console

    code, _, stderr, git_calls, _ = _sides("adopt-no-main", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert (
        b"submodule-main-unresolvable: 'private/renet' has no resolvable origin/main even "
        b"after a fetch, so the ancestry half of the adoption check cannot run; refusing to "
        b"adopt on the identity check alone" in stderr
    )
    assert not any(call.startswith("push\t") for call in git_calls)


def test_an_orphan_that_does_not_apply_cleanly_stops_for_a_human() -> None:
    def scenario(sandbox):
        return _orphan(sandbox, email=BOT_EMAIL, with_main=True, conflicting=True)

    code, _, stderr, git_calls, _ = _sides("adopt-conflict", scenario, base_argv, env=SUB_ENV)
    assert code == 1
    assert b"submodule-adopt-conflict: 'private/renet' this round's commit does not apply" in stderr
    assert b"a human must reconcile the branch" in stderr
    assert not any(call.startswith("push\t") for call in git_calls)


def test_a_provable_orphan_is_adopted_and_the_console_check_is_re_run() -> None:
    """PHASE 4. The adoption moved the submodule SHA, so the gitlink console
    staged in phase 2 now names a commit that is no longer the branch tip.
    Re-stage and re-run the SAME validation rather than patching the index and
    trusting it -- which is why `gitlink verified` appears TWICE."""

    def scenario(sandbox):
        # An orphan touching a DIFFERENT file, so the cherry-pick applies.
        console = build(sandbox, submodule=True)
        bare = sandbox / "renet.git"
        work = sandbox / "orphan-work"
        _git(sandbox, "clone", "-q", str(bare), str(work))
        assert (work / "main.go").exists(), "the clone came up empty; the orphan would be a root"
        _git(work, "config", "user.email", BOT_EMAIL)
        _git(work, "config", "user.name", BOT_NAME)
        _git(work, "checkout", "-q", "-b", "work")
        (work / "orphan.go").write_text("package main\n", encoding="utf-8")
        _git(work, "add", "--", "orphan.go")
        _git(work, "commit", "-q", "-m", "orphan round")
        _git(work, "push", "-q", "origin", "work")
        (console / "private" / "renet" / "main.go").write_text(
            "package main\n// ours\n", encoding="utf-8"
        )
        handoff(
            console,
            files=["private/renet"],
            commit_message="chore: bump renet",
            submodules=[{"path": "private/renet", "files": ["main.go"], "message": "fix: ours"}],
        )
        return console

    code, stdout, stderr, git_calls, _ = _sides("adopt-ok", scenario, base_argv, env=SUB_ENV)
    assert code == 0, stderr
    assert b"is an autopilot orphan; rebuilding this round's commit on top of it" in stderr
    assert b"adopted the orphan in 'private/renet': pushed" in stderr
    assert (
        b"an orphan was adopted; re-staging the pointers and re-running the console validation"
        in stderr
    )
    assert stderr.count(b"gitlink verified: private/renet -> ") == 2, (
        "the console validation was not re-run after the SHA moved"
    )
    # The two gitlink lines must name DIFFERENT shas: the second is the adopted
    # commit, and a port that skipped the re-stage would print the first twice.
    lines = [line for line in stderr.split(b"\n") if b"gitlink verified" in line]
    assert lines[0] != lines[1], "the pointer was not re-staged after the adoption"
    assert len(stdout.decode().strip().split("\n")[-1]) == 40
    # Three pushes: the submodule attempt that was rejected, the adopted commit,
    # and console LAST -- so the pointer console publishes names a commit that
    # already exists on the remote.
    pushes = [call for call in git_calls if "push" in call.split("\t")]
    assert len(pushes) == 3, pushes
    assert pushes[2].startswith("push\torigin\t"), pushes[2]


# ---------------------------------------------------------------------------
# The unreachable arms, named rather than skipped
# ---------------------------------------------------------------------------


def test_the_unreachable_refusals_are_unreachable_for_the_same_reason() -> None:
    """Five refusals in the twin cannot be entered from the CLI. The honest
    differential is to drive the gate that stops each one and assert BOTH sides
    stop there, which is what this does."""
    # 1. submodules[] with the stage flag OFF: the VALIDATOR refuses, so the
    #    write-site's belt-and-braces copy is never reached.
    code, _, stderr, _, _ = _sides(
        "unreachable-subs-flag", _sub_scenario, base_argv, env={"AUTOPILOT_ALLOW_SUBMODULES": ""}
    )
    assert code == 1
    assert b"submodules-disabled" in stderr, "the validator did not refuse first"
    assert b"refusing 1 submodule change(s)" not in stderr, (
        "the write-site refusal became reachable; give it its own case"
    )

    # 2. an absent submodule: the parent reports the path NOT dirty, so the
    #    validator refuses before `submodule-missing` or the toplevel check.
    def gone(sandbox):
        console = _sub_scenario(sandbox)
        shutil.rmtree(console / "private" / "renet" / ".git")
        return console

    code, _, stderr, _, _ = _sides("unreachable-sub-missing", gone, base_argv, env=SUB_ENV)
    assert code == 1
    assert b"path-not-dirty: private/renet" in stderr
    assert b"submodule-missing:" not in stderr
    assert b"submodule-not-initialized:" not in stderr

    # 3. a forbidden branch inside the submodule loop: the top-level check has
    #    already refused the same three names.
    def on_main(sandbox):
        console = build(sandbox, submodule=True, branch="main")
        (console / "private" / "renet" / "main.go").write_text("package main\n//e\n", "utf-8")
        handoff(
            console,
            files=["private/renet"],
            commit_message="m",
            submodules=[{"path": "private/renet", "files": ["main.go"], "message": "x"}],
        )
        return console

    code, _, stderr, _, _ = _sides(
        "unreachable-sub-branch",
        on_main,
        lambda console: [
            "--root",
            str(console),
            "--handoff",
            str(console / "handoff.json"),
            "--branch",
            "main",
        ],
        env=SUB_ENV,
    )
    assert code == 1
    assert b"branch-forbidden: the autopilot never pushes 'main'" in stderr
    assert b"submodule-branch-forbidden" not in stderr

    # 4. outcome-unknown: the schema pins the enum, so a fourth value never
    #    reaches the verdict at all.
    def bad_outcome(sandbox):
        console = build(sandbox)
        handoff(console, outcome="sideways")
        return console

    code, _, stderr, _, _ = _sides("unreachable-outcome", bad_outcome, base_argv)
    assert code == 1
    assert b"handoff.outcome: must be one of push|escalate|no-change" in stderr
    assert b"outcome-unknown" not in stderr


def test_the_toplevel_predicate_is_driven_directly() -> None:
    """`submodule-not-initialized`'s PREDICATE, whose failure mode is committing
    submodule content into console as ordinary files. Unreachable from the CLI
    (case 2 above), so it is driven here against three shapes: a real nested
    checkout, a plain directory inside a parent repo, and an absent path.

    `--git-dir` WOULD ANSWER YES FOR THE SECOND ONE, which is the whole reason
    the twin compares toplevels instead."""
    with tempfile.TemporaryDirectory() as td:
        sandbox = pathlib.Path(td)
        console = build(sandbox, submodule=True)
        ok, top = ap.submodule_toplevel_matches(str(console), "private/renet")
        assert ok is True
        assert pathlib.Path(top) == console / "private" / "renet"

        plain = console / "private" / "plain"
        plain.mkdir()
        ok, top = ap.submodule_toplevel_matches(str(console), "private/plain")
        assert ok is False, "a plain directory inside the parent passed as its own checkout"
        assert pathlib.Path(top) == console, "git answered with the PARENT, as documented"

        ok, top = ap.submodule_toplevel_matches(str(console), "private/absent")
        assert ok is False
        assert top == ""


def test_pure_helpers_are_exercised_directly() -> None:
    """BOTH DIRECTIONS: something that must appear and something that must not."""
    argv = ap.tripwire_argv(pathlib.Path("/s"), "/w/d.diff", "")
    assert argv == ["node", "/s/exfil-tripwire.cjs", "--diff", "/w/d.diff"]
    assert "--failed-jobs" not in argv, "an empty value must contribute NO argument"
    argv = ap.tripwire_argv(pathlib.Path("/s"), "/w/d.diff", "/w/failed jobs.txt")
    assert argv[-2:] == ["--failed-jobs", "/w/failed jobs.txt"], "the space split the argument"

    assert ap.FORBIDDEN_BRANCHES == ("main", "master", "HEAD")
    assert ap.NON_FAST_FORWARD_RE.search("! [rejected] work -> work (non-fast-forward)")
    assert ap.NON_FAST_FORWARD_RE.search("hint: Updates were rejected... fetch first")
    assert ap.NON_FAST_FORWARD_RE.search("NON-FAST-FORWARD"), "the match is case-insensitive"
    assert not ap.NON_FAST_FORWARD_RE.search(
        "fatal: 'origin' does not appear to be a git repository"
    ), "a dead remote must NOT be read as a non-fast-forward"

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "lines")
        with open(path, "wb") as handle:
            handle.write(b"one\ntwo\npartial")
        assert ap.read_lines(path) == ["one", "two"], "a final unterminated line is dropped"
