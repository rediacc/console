"""`rediacc_ci.autopilot.autopilot_push`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/autopilot-push.sh` and the port over two identical sandboxes and compared exit code, stdout, stderr, the git call SEQUENCE and the (always empty) gh call log.

The ledger `.ci/shadow/w7p6-autopilot-push.observations.jsonl` holds 5 rows of that comparison, recorded in a disposable scratch git repository outside this checkout. Every case now compares against `goldens/autopilot-push/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p
<sha>` still yields the program that produced them.

THIS IS THE SECURITY BOUNDARY OF THE AUTONOMY LOOP: every write flows through `validate-handoff.cjs`, `exfil-tripwire.cjs` and then this script, and every rejection must be a LOUD escalation rather than a silent no-op. A recording that froze stdout alone would freeze the half that does not matter, so the recorded shape carries three sections beyond the two streams.

  `--- git calls ---`  the argv sequence, which is where the dangerous
                       differences live: staging one path at a time versus `-A`,
                       pushing an explicit SHA versus a branch name, and whether
                       a refusal happened BEFORE or AFTER a remote write.
  `--- gh calls ---`   always empty, and recorded anyway. This script must never
                       call `gh`; a port that grew a call is caught by the
                       section being non-empty rather than by nobody noticing.
  `--- git state ---`  what the run LEFT BEHIND: each repository's HEAD, branch
                       and porcelain status, and every ref on each bare remote.
                       This is what turns "nothing was pushed" from an inference
                       about an argv log into a recorded fact about a remote,
                       and it is where the commit a successful round minted is
                       pinned as durable state rather than as a line of output.

COMMIT SHAs ARE COMPARED, and that is deliberate. `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` are pinned, every fixture is built by the same code, and the committer identity comes from the same flags, so a SHA is a function of the tree, the message and the identity. A recorded SHA is therefore reproducible months later, and two runs printing the same one have committed the same
bytes under the same name.

-----------------------------------------------------------------------------
THE SANDBOX, AND WHY IT IS A SHIM RATHER THAN A PROMISE
-----------------------------------------------------------------------------
Every subject runs with a curated PATH whose FIRST entry holds two fakes: a recording `gh` that this script must never reach, and a recording, sandbox-GUARDED `git` shim. The shim logs the argv, then REFUSES with exit 97 unless the repository it would operate on resolves inside the per-case sandbox, and, for `push` and `fetch`, unless the remote URL does too. Only then does it
`execv` the real git.

So the safety property is not "the arguments were chosen carefully"; it is a control that fires. `test_the_shim_refuses_the_real_checkout` aims the shim at this repository and asserts exit 97, and `test_the_shim_refuses_a_remote_outside_the_sandbox` points a push at `https://github.com/...` and asserts the same. Both are PLANTS: if either stops firing, every case in this file has
been running unguarded. `test_the_fakes_win_the_path_lookup` asserts the resolution order itself.

-----------------------------------------------------------------------------
EVERY REFUSAL BRANCH, AND WHICH ONES CANNOT BE REACHED
-----------------------------------------------------------------------------
The twin was twenty-odd refusals and three success paths. Each reachable refusal has a case. FIVE ARE UNREACHABLE THROUGH THE CLI and are named as such rather than quietly skipped, because "no test" and "cannot happen" look the same in a test file and only one of them is acceptable:

  outcome-unknown              the validator's schema pins the enum
  stage-flag-disabled (subs)   the validator refuses submodules[] with the flag
                               off
  submodule-missing            an absent submodule makes the parent report the
                               path NOT dirty, so the validator refuses first
  submodule-not-initialized    same route (measured: removing a submodule's
                               `.git` makes `git status` report nothing at all
                               for that path)
  submodule-branch-forbidden   the top-level branch-forbidden check has already
                               refused the same three names
  submodule-pointer-rollback   a commit made on top of HEAD is a descendant of
                               HEAD by construction

Four cases drive the gate that stops each of the first five, and each asserts BOTH that the gate fired and that the unreachable message did not, which is the honest recording for a branch nothing can enter. The `submodule-not-initialized` predicate is additionally driven directly through the exported `submodule_toplevel_matches`, against a real directory that is not its own
checkout, which is the case whose failure mode is committing submodule content into console as ordinary files.

ONE CASE IS COMPARED BY SHAPE, and it has to be: an unwritable `--verdict-out`. Both sides exit 1 with nothing staged, and only the wording differs, because bash names its own line number and no port can honestly reproduce that. The exit code, the empty stdout, the git calls and the git state are compared exactly, and the recorded sentence stays in the golden as the evidence of
what the twin said.

-----------------------------------------------------------------------------
WHAT IS MASKED, AND WHY EACH ONE HAS TO BE
-----------------------------------------------------------------------------
Three tokens, each standing for something that genuinely cannot repeat, and nothing else:

  `<sandbox>`  the per-case temporary directory, which is the root of every
               path the subject is given and is rebuilt under a different name
               every run.
  `<work>`     the subject's own scratch directory. `mktemp -d` and
               `tempfile.mkdtemp` pick different random suffixes, and the twin
               printed that path inside the `commit -F` argv, so a recording
               that did not fold it would differ from every replay for a reason
               that says nothing about the subject. TMPDIR is pinned INSIDE the
               sandbox, so the fold cannot swallow anything else.
  `<mtime>`    `diff -u` stamps each header line with the file's modification
               time, which is wall clock. ONLY the timestamp is folded; the
               `+` and `-` lines that carry the actual evidence are compared in
               full.

-----------------------------------------------------------------------------
THE SANDBOX PATH IS DATA, AND A CASE NAME CAN THEREFORE CHANGE AN OUTCOME
-----------------------------------------------------------------------------
Each case builds its sandbox under a directory named after the case, and that name reaches git's own diagnostics, which the subject then greps. `a-submodule-push-that-is-not-a-non-fast-forward` was this case's first name, git's refusal quoted `<sandbox>/gone.git`, and the subject's `grep -qiE 'non-fast-forward|fetch first|\\[rejected\\]'` matched THE
DIRECTORY NAME. The run took the orphan-adoption branch and exited 128 instead of refusing at 1, and the scrub to `<sandbox>` hid the cause in the recording. Measured, and it cost the case one recording. The name is now `a-submodule-push-that-fails-another-way`; a new case name must not contain a token the subject matches on.

-----------------------------------------------------------------------------
THE CONTROL IS A WRAPPER PLANT, NOT A COPY OF THE FILE
-----------------------------------------------------------------------------
`script_dir()` resolves the two `.cjs` controls from `parents[3]` of this module's own file, so a throwaway COPY at any other path looks for the validator and the tripwire somewhere they are not and dies before a single git call. The control therefore writes a tiny entry point that imports the TRACKED module and replaces one attribute in its own process. The file on disk is never
written to at all.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import autopilot_push as ap
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "autopilot_push.py"
SLUG = "autopilot-push"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable
REAL_GIT = shutil.which("git") or "/usr/bin/git"

GIT_MARKER = "--- git calls ---\n"
GH_MARKER = "--- gh calls ---\n"
STATE_MARKER = "--- git state ---\n"

# `<sandbox>/tmp/tmp.AbCdEfGhIj` (bash mktemp) and `<sandbox>/tmp/tmpab12cd34` (Python). Applied AFTER the sandbox path itself has been folded.
WORKDIR_RE = re.compile(r"<sandbox>/tmp/tmp\.?[A-Za-z0-9_]+")

# `diff -u` stamps each header line with the file's mtime, which is wall clock.
MTIME_RE = re.compile(r"\t\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ [+-]\d{4}")

FIXED_DATE = "2026-01-01T00:00:00+00:00"
BOT_NAME = "Autopilot Operator"
BOT_EMAIL = "operator@example.invalid"

# The recording, sandbox-guarded `git`. See the module docstring: this is a CONTROL, not a convenience, and two tests plant against it.
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


def stub_bin(sandbox: pathlib.Path) -> str:
    """The curated PATH: the two fakes FIRST, then the real one.

    PREPENDED rather than reduced to a symlink farm, because the subject reaches node, jq, diff, sort and a long tail of coreutils. The safety property is therefore RESOLUTION ORDER plus the shim's own refusals, and all three are asserted rather than assumed.
    """
    stub = sandbox / "stubbin"
    stub.mkdir(parents=True, exist_ok=True)
    for name, text in (("git", FAKE_GIT), ("gh", FAKE_GH)):
        path = stub / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _git(cwd: pathlib.Path, *args: str, check: bool = True) -> str:
    """Real git, for FIXTURE BUILDING and for reading the state back. Never on the subject's PATH."""
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

    The submodule gitlink is written with `update-index --cacheinfo` rather than `git submodule add`, which keeps the fixture free of `protocol.file.allow` and leaves the submodule as a plain nested checkout, exactly the shape `rev-parse --show-toplevel` is asked about.
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
            # `--initial-branch=main` matters: a bare repo whose HEAD names a branch that does not exist clones as EMPTY, and an "orphan" built in that clone would be a ROOT commit, which would make the adoption cases pass through the unrelated-history arm instead of the one they are aimed at.
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


def handoff(console: pathlib.Path, **fields: typing.Any) -> None:
    body = {
        "schema": "rediacc-autopilot-handoff/1",
        "base_head": _git(console, "rev-parse", "HEAD"),
        "outcome": "push",
        "ledger_line": "r1 | run 1 | did the thing",
    }
    body.update(fields)
    (console / "handoff.json").write_text(json.dumps(body), encoding="utf-8")


# --------------------------------------------------------------------------- The scenarios, one per shape of tree ---------------------------------------------------------------------------


def plain(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "src.txt").write_text("changed\n", encoding="utf-8")
    _git(console, "add", "--", "src.txt")
    handoff(console, files=["src.txt"], commit_message="fix: the thing")
    return console


def no_handoff(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "src.txt").write_text("x\n", encoding="utf-8")
    return console


def stale_base(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "src.txt").write_text("x\n", encoding="utf-8")
    handoff(console, base_head="0" * 40, files=["src.txt"], commit_message="m")
    return console


def undeclared(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "src.txt").write_text("x\n", encoding="utf-8")
    (console / "sneaky.txt").write_text("y\n", encoding="utf-8")
    handoff(console, files=["src.txt"], commit_message="m")
    return console


def workflow_file(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / ".github").mkdir()
    (console / ".github" / "ci.yml").write_text("on: push\n", encoding="utf-8")
    handoff(console, files=[".github/ci.yml"], commit_message="m")
    return console


def escalating(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    handoff(console, outcome="escalate", escalation={"reason": "needs a human"})
    return console


def no_change(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    handoff(console, outcome="no-change")
    return console


def on_branch(name: str):
    def scenario(sandbox: pathlib.Path) -> pathlib.Path:
        console = build(sandbox, branch=name)
        (console / "src.txt").write_text("x\n", encoding="utf-8")
        handoff(console, files=["src.txt"], commit_message="m")
        return console

    return scenario


def detached(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    _git(console, "checkout", "-q", "--detach")
    (console / "src.txt").write_text("x\n", encoding="utf-8")
    handoff(console, files=["src.txt"], commit_message="m")
    return console


def expanding_pathspec(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "newdir").mkdir()
    (console / "newdir" / "a.txt").write_text("a\n", encoding="utf-8")
    (console / "newdir" / "b.txt").write_text("b\n", encoding="utf-8")
    handoff(console, files=["newdir/"], commit_message="m")
    return console


def big_blob(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "blob.txt").write_text("x" * 9000 + "\n", encoding="utf-8")
    handoff(console, files=["blob.txt"], commit_message="m")
    return console


def failed_jobs(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    (console / "src.txt").write_text("x\n", encoding="utf-8")
    (sandbox / "failed jobs.txt").write_text("Quality / code\n", encoding="utf-8")
    handoff(console, files=["src.txt"], commit_message="m")
    return console


def dead_remote(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox, remote=False)
    # A remote INSIDE the sandbox (so the shim allows the attempt) that is not a repository (so real git refuses it). Pointing it outside would test the shim instead of the subject.
    _git(console, "remote", "add", "origin", str(sandbox / "gone.git"))
    (console / "src.txt").write_text("x\n", encoding="utf-8")
    handoff(console, files=["src.txt"], commit_message="m")
    return console


def sub(sandbox: pathlib.Path) -> pathlib.Path:
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


def sub_ghost_file(sandbox: pathlib.Path) -> pathlib.Path:
    console = sub(sandbox)
    handoff(
        console,
        files=["private/renet"],
        commit_message="m",
        submodules=[
            {"path": "private/renet", "files": ["main.go", "ghost.go"], "message": "fix: x"}
        ],
    )
    return console


def sub_staged_extra(sandbox: pathlib.Path) -> pathlib.Path:
    console = sub(sandbox)
    nested = console / "private" / "renet"
    (nested / "extra.go").write_text("package main\n", encoding="utf-8")
    _git(nested, "add", "--", "extra.go")
    return console


def sub_big_blob(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox, submodule=True)
    nested = console / "private" / "renet"
    (nested / "blob.txt").write_text("y" * 9000 + "\n", encoding="utf-8")
    handoff(
        console,
        files=["private/renet"],
        commit_message="m",
        submodules=[{"path": "private/renet", "files": ["blob.txt"], "message": "fix: x"}],
    )
    return console


def sub_branch_exists(sandbox: pathlib.Path) -> pathlib.Path:
    console = sub(sandbox)
    _git(console / "private" / "renet", "branch", "work")
    return console


def sub_dead_remote(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox, submodule=True, sub_remote=False)
    _git(console / "private" / "renet", "remote", "add", "origin", str(sandbox / "gone.git"))
    (console / "private" / "renet" / "main.go").write_text("package main\n//e\n", encoding="utf-8")
    handoff(
        console,
        files=["private/renet"],
        commit_message="m",
        submodules=[{"path": "private/renet", "files": ["main.go"], "message": "fix: x"}],
    )
    return console


def sub_gone(sandbox: pathlib.Path) -> pathlib.Path:
    console = sub(sandbox)
    shutil.rmtree(console / "private" / "renet" / ".git")
    return console


def sub_on_main(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox, submodule=True, branch="main")
    (console / "private" / "renet" / "main.go").write_text("package main\n//e\n", encoding="utf-8")
    handoff(
        console,
        files=["private/renet"],
        commit_message="m",
        submodules=[{"path": "private/renet", "files": ["main.go"], "message": "x"}],
    )
    return console


def bad_outcome(sandbox: pathlib.Path) -> pathlib.Path:
    console = build(sandbox)
    handoff(console, outcome="sideways")
    return console


def _orphan(sandbox: pathlib.Path, *, email: str, with_main: bool, conflicting: bool):
    """Put a commit on the submodule remote's `work` branch, so this round's push is rejected as a non-fast-forward.

    Built in a SEPARATE clone so the round's own submodule checkout is untouched, which is the real shape: the orphan was left by a PREVIOUS round.
    """
    console = build(sandbox, submodule=True)
    bare = sandbox / "renet.git"
    if with_main:
        # A continuation of the submodule's own history: cloned from the remote, so it shares main's merge-base.
        work = sandbox / "orphan-work"
        _git(sandbox, "clone", "-q", str(bare), str(work))
        assert (work / "main.go").exists(), "the clone came up empty; the orphan would be a root"
        _git(work, "config", "user.email", email)
        _git(work, "config", "user.name", "Whoever")
        _git(work, "checkout", "-q", "-b", "work")
        body = "package main\n// theirs\n" if conflicting else "package main\n// orphan\n"
        (work / "main.go").write_text(body, encoding="utf-8")
        _git(work, "add", "--", "main.go")
        _git(work, "commit", "-q", "-m", "orphan round")
    else:
        # An UNRELATED history: a fresh repository, so its root commit shares no merge-base with the submodule's main at all.
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


def orphan_foreign(sandbox: pathlib.Path) -> pathlib.Path:
    return _orphan(sandbox, email="stranger@example.invalid", with_main=True, conflicting=False)


def orphan_unrelated(sandbox: pathlib.Path) -> pathlib.Path:
    return _orphan(sandbox, email=BOT_EMAIL, with_main=False, conflicting=False)


def orphan_no_main(sandbox: pathlib.Path) -> pathlib.Path:
    console = _orphan(sandbox, email=BOT_EMAIL, with_main=True, conflicting=False)
    # BOTH copies have to go: the remote-tracking ref the submodule already holds, and the branch on the remote that a fetch would restore it from.
    _git(sandbox / "renet.git", "update-ref", "-d", "refs/heads/main")
    _git(console / "private" / "renet", "update-ref", "-d", "refs/remotes/origin/main")
    return console


def orphan_conflicting(sandbox: pathlib.Path) -> pathlib.Path:
    return _orphan(sandbox, email=BOT_EMAIL, with_main=True, conflicting=True)


def orphan_adoptable(sandbox: pathlib.Path) -> pathlib.Path:
    """An orphan touching a DIFFERENT file, so the cherry-pick applies."""
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


# --------------------------------------------------------------------------- The argv builders ---------------------------------------------------------------------------


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


def dropping(flag: str):
    def argv(console: pathlib.Path) -> list[str]:
        out: list[str] = []
        skip = False
        for token in base_argv(console):
            if skip:
                skip = False
                continue
            if token == flag:
                skip = True
                continue
            out.append(token)
        return out

    return argv


def naming_branch(name: str):
    def argv(console: pathlib.Path) -> list[str]:
        return [
            "--root",
            str(console),
            "--handoff",
            str(console / "handoff.json"),
            "--branch",
            name,
        ]

    return argv


SUB_ENV = {"AUTOPILOT_ALLOW_SUBMODULES": "true"}

# name -> the tree to build, the argv to drive it with, and the environment
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "without-a-root": {"scenario": plain, "argv": dropping("--root")},
    "without-a-handoff": {"scenario": plain, "argv": dropping("--handoff")},
    "without-a-branch": {"scenario": plain, "argv": dropping("--branch")},
    "a-root-that-is-not-a-directory": {
        "scenario": plain,
        "argv": lambda console: [
            "--root",
            str(console / "nope"),
            "--handoff",
            "h",
            "--branch",
            "work",
        ],
    },
    "the-stage-flag-unset": {
        "scenario": plain,
        "argv": base_argv,
        "env": {"AUTOPILOT_ALLOW_PUSH": ""},
    },
    "the-stage-flag-false": {
        "scenario": plain,
        "argv": base_argv,
        "env": {"AUTOPILOT_ALLOW_PUSH": "false"},
    },
    "the-stage-flag-uppercase-true": {
        "scenario": plain,
        "argv": base_argv,
        "env": {"AUTOPILOT_ALLOW_PUSH": "TRUE"},
    },
    "the-stage-flag-one": {
        "scenario": plain,
        "argv": base_argv,
        "env": {"AUTOPILOT_ALLOW_PUSH": "1"},
    },
    "a-dry-run-with-no-stage-flag": {
        "scenario": plain,
        "argv": lambda console: base_argv(console, "--dry-run"),
        "env": {"AUTOPILOT_ALLOW_PUSH": ""},
    },
    "without-a-committer-name": {
        "scenario": plain,
        "argv": base_argv,
        "env": {"AUTOPILOT_GIT_NAME": ""},
    },
    "without-a-committer-email": {
        "scenario": plain,
        "argv": base_argv,
        "env": {"AUTOPILOT_GIT_EMAIL": ""},
    },
    "a-branch-mismatch": {"scenario": plain, "argv": naming_branch("some-other-branch")},
    "the-forbidden-branch-main": {"scenario": on_branch("main"), "argv": naming_branch("main")},
    "the-forbidden-branch-master": {
        "scenario": on_branch("master"),
        "argv": naming_branch("master"),
    },
    "a-detached-head": {"scenario": detached, "argv": naming_branch("HEAD")},
    "a-missing-handoff": {"scenario": no_handoff, "argv": base_argv},
    "a-stale-base-head": {"scenario": stale_base, "argv": base_argv},
    "an-undeclared-dirty-file": {"scenario": undeclared, "argv": base_argv},
    "a-denylisted-workflow-file": {"scenario": workflow_file, "argv": base_argv},
    "an-escalating-round": {
        "scenario": escalating,
        "argv": lambda console: base_argv(console, "--verdict-out", str(console.parent / "v.json")),
    },
    "a-no-change-round": {
        "scenario": no_change,
        "argv": lambda console: base_argv(console, "--verdict-out", str(console.parent / "v.json")),
    },
    "a-verdict-written-to-a-fifo": {
        "scenario": escalating,
        "argv": lambda console: base_argv(console, "--verdict-out", "/dev/stdout"),
    },
    "an-unwritable-verdict-out": {
        "scenario": plain,
        "argv": lambda console: base_argv(
            console, "--verdict-out", str(console.parent / "nodir" / "v.json")
        ),
    },
    "the-happy-path": {"scenario": plain, "argv": base_argv},
    "a-pathspec-that-expands": {"scenario": expanding_pathspec, "argv": base_argv},
    "a-tripped-tripwire": {"scenario": big_blob, "argv": base_argv},
    "a-failed-jobs-path-with-a-space": {
        "scenario": failed_jobs,
        "argv": lambda console: base_argv(
            console, "--failed-jobs", str(console.parent / "failed jobs.txt"), "--dry-run"
        ),
    },
    "a-console-push-that-fails": {"scenario": dead_remote, "argv": base_argv},
    "a-submodule-round": {"scenario": sub, "argv": base_argv, "env": SUB_ENV},
    "a-submodule-path-that-is-missing": {
        "scenario": sub_ghost_file,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "a-submodule-staged-set-mismatch": {
        "scenario": sub_staged_extra,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "a-tripped-tripwire-in-a-submodule": {
        "scenario": sub_big_blob,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "a-submodule-branch-that-already-exists": {
        "scenario": sub_branch_exists,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "a-submodule-push-that-fails-another-way": {
        "scenario": sub_dead_remote,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "a-foreign-orphan-branch": {"scenario": orphan_foreign, "argv": base_argv, "env": SUB_ENV},
    "an-unrelated-orphan-history": {
        "scenario": orphan_unrelated,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "an-orphan-with-no-resolvable-main": {
        "scenario": orphan_no_main,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "an-orphan-that-conflicts": {
        "scenario": orphan_conflicting,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "an-orphan-that-is-adopted": {"scenario": orphan_adoptable, "argv": base_argv, "env": SUB_ENV},
    "submodules-with-the-stage-flag-off": {
        "scenario": sub,
        "argv": base_argv,
        "env": {"AUTOPILOT_ALLOW_SUBMODULES": ""},
    },
    "a-submodule-whose-checkout-is-gone": {
        "scenario": sub_gone,
        "argv": base_argv,
        "env": SUB_ENV,
    },
    "a-submodule-round-on-a-forbidden-branch": {
        "scenario": sub_on_main,
        "argv": naming_branch("main"),
        "env": SUB_ENV,
    },
    "an-outcome-the-schema-forbids": {"scenario": bad_outcome, "argv": base_argv},
}

CASES = tuple(CASE_KW)

# The one case whose refusal text is bash's own. Compared by shape, in its own test.
DIVERGENT = ("an-unwritable-verdict-out",)


# --------------------------------------------------------------------------- Driving one subject ---------------------------------------------------------------------------


def git_state(sandbox: pathlib.Path) -> str:
    """What the run left behind: every checkout's HEAD, branch and status, and every ref on every bare remote.

    Read with the REAL git after the subject has exited, so the shim's log is not polluted by the reading. This is the section that makes "nothing was pushed" a fact about a remote rather than an inference from an argv log.
    """
    state: dict[str, typing.Any] = {}
    for label, repo in (
        ("console", sandbox / "console"),
        ("console/private/renet", sandbox / "console" / "private" / "renet"),
    ):
        if not (repo / ".git").exists():
            continue
        state[label] = {
            "head": _git(repo, "rev-parse", "HEAD", check=False),
            "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False),
            "status": _git(repo, "status", "--porcelain", check=False),
        }
    for label, bare in (
        ("console.git", sandbox / "console.git"),
        ("renet.git", sandbox / "renet.git"),
    ):
        if not bare.is_dir():
            continue
        state[label] = {
            "refs": _git(bare, "for-each-ref", "--format=%(refname) %(objectname)", check=False)
        }
    return json.dumps(state, indent=2, sort_keys=True)


def execute(
    subject: pathlib.Path,
    sandbox: pathlib.Path,
    argv: list[str],
    env_extra: dict[str, str],
) -> tuple[int, str, str, str, str, str]:
    """One subject, once, inside one prepared sandbox."""
    git_log = sandbox / "git-calls.log"
    gh_log = sandbox / "gh-calls.log"
    git_log.write_text("", encoding="utf-8")
    gh_log.write_text("", encoding="utf-8")
    tmpdir = sandbox / "tmp"
    tmpdir.mkdir(exist_ok=True)
    env = {
        "PATH": stub_bin(sandbox),
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
        # Both mktemp implementations honour TMPDIR, so the work directory lands inside the sandbox rather than in the shared /tmp, and the shim's own guard therefore covers it too.
        "TMPDIR": str(tmpdir),
    }
    env.update(env_extra)
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(sandbox),
        timeout=300,
    )

    def scrub(raw: str) -> str:
        folded = WORKDIR_RE.sub("<work>", raw.replace(str(sandbox), "<sandbox>"))
        return MTIME_RE.sub("\t<mtime>", folded)

    return (
        proc.returncode,
        scrub(proc.stdout),
        scrub(proc.stderr),
        scrub(git_log.read_text(encoding="utf-8")),
        scrub(gh_log.read_text(encoding="utf-8")),
        scrub(git_state(sandbox)),
    )


def run(
    subject: pathlib.Path, sandbox: pathlib.Path, name: str
) -> tuple[int, str, str, str, str, str]:
    """One subject, once, over this case's own freshly built sandbox."""
    kw = CASE_KW[name]
    sandbox.mkdir(parents=True, exist_ok=True)
    console = kw["scenario"](sandbox)
    argv = kw["argv"]
    resolved = argv(console) if callable(argv) else list(argv)
    env_extra = {"AUTOPILOT_ALLOW_PUSH": "true"}
    env_extra.update(kw.get("env") or {})
    return execute(subject, sandbox, resolved, env_extra)


def render(code: int, stdout: str, stderr: str, git_calls: str, gh_calls: str, state: str) -> str:
    return "%s%s%s%s%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        GIT_MARKER,
        git_calls,
        GH_MARKER,
        gh_calls,
        STATE_MARKER,
        state,
    )


def recorded(name: str) -> tuple[int, str, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(GIT_MARKER, 1)
    git_calls, rest = rest.split(GH_MARKER, 1)
    gh_calls, state = rest.split(STATE_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        git_calls,
        gh_calls,
        state.removesuffix("\n"),
    )


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str, str]:
    return run(PORT, tmp_path / name, name)


def calls(git_calls: str) -> list[str]:
    return [line for line in git_calls.splitlines() if line]


def verbs(git_calls: str) -> list[str]:
    return [line.split("\t")[0] for line in calls(git_calls)]


def wrote_anything(git_calls: str) -> bool:
    """Whether any staging, commit or push reached git, wherever it was aimed."""
    for line in calls(git_calls):
        parts = line.split("\t")
        if set(parts) & {"add", "commit", "push"}:
            return True
    return False


def pushes(git_calls: str) -> list[str]:
    return [line for line in calls(git_calls) if "push" in line.split("\t")]


def refs(state: str, repo: str) -> str:
    return json.loads(state).get(repo, {}).get("refs", "")


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = (
        "exit code",
        "stdout",
        "stderr",
        "the git CALL LOG",
        "the gh call log",
        "the git state left behind",
    )
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_recording_shows_a_gh_call() -> None:
    """The whole point of recording an always-empty section. This script must never call `gh`, and the claim is checked across the WHOLE corpus rather than case by case."""
    for name in CASES:
        assert recorded(name)[4] == "", name


# --------------------------------------------------------------------------- CONTROLS. These come first because everything above is worthless without them. ---------------------------------------------------------------------------


def test_the_fakes_win_the_path_lookup(tmp_path: pathlib.Path) -> None:
    """If the stubs ever stop winning, every case in this file has been talking to the real git and the real GitHub CLI."""
    path = stub_bin(tmp_path)
    for name in ("git", "gh"):
        resolved = shutil.which(name, path=path)
        assert resolved == str(tmp_path / "stubbin" / name), (
            "the fake %s does not win the PATH lookup: %r" % (name, resolved)
        )


def test_the_shim_refuses_the_real_checkout(tmp_path: pathlib.Path) -> None:
    """A PLANT. Aim the shim at this repository and it must refuse, so a case that ever escaped its sandbox cannot touch the tree the operator is using."""
    stub = stub_bin(tmp_path).split(":")[0]
    env = dict(os.environ)
    env.update(
        {
            "FAKE_GIT_REAL": REAL_GIT,
            "FAKE_GIT_SANDBOX": str(tmp_path),
            "FAKE_GIT_LOG": str(tmp_path / "log"),
            "PATH": "%s:%s" % (stub, os.environ["PATH"]),
        }
    )
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 97, "the shim let a command reach %s" % ROOT
    assert b"FAKE-GIT REFUSED" in proc.stderr
    assert not (tmp_path / "log").exists(), "a refused call was still recorded as made"


def test_the_shim_refuses_a_remote_outside_the_sandbox(tmp_path: pathlib.Path) -> None:
    """The other half of the plant: a push whose remote is not a path inside the sandbox must never reach the network."""
    stub = stub_bin(tmp_path).split(":")[0]
    repo = tmp_path / "repo"
    _init(repo, "work")
    (repo / "f").write_text("x", encoding="utf-8")
    _git(repo, "add", "--", "f")
    _git(repo, "commit", "-q", "-m", "c")
    _git(repo, "remote", "add", "origin", "https://github.com/rediacc/console.git")
    env = dict(os.environ)
    env.update(
        {
            "FAKE_GIT_REAL": REAL_GIT,
            "FAKE_GIT_SANDBOX": str(tmp_path),
            "FAKE_GIT_LOG": str(tmp_path / "log"),
            "PATH": "%s:%s" % (stub, os.environ["PATH"]),
        }
    )
    proc = subprocess.run(
        ["git", "-C", str(repo), "push", "origin", "HEAD:refs/heads/work"],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(tmp_path),
        timeout=60,
    )
    assert proc.returncode == 97, "a push to github.com was not refused"
    assert b"would leave the sandbox" in proc.stderr


# --------------------------------------------------------------------------- What the recordings say: the refusals before anything is read ---------------------------------------------------------------------------


def test_usage_refusals() -> None:
    for name in ("without-a-root", "without-a-handoff", "without-a-branch"):
        code, _, stderr, git_calls, _, _ = recorded(name)
        assert code == 2, name
        assert "usage: autopilot-push.sh" in stderr
        assert git_calls == "", "git ran before the arguments were checked"


def test_a_root_that_is_not_a_directory_is_refused_by_name() -> None:
    code, _, stderr, git_calls, _, _ = recorded("a-root-that-is-not-a-directory")
    assert code == 1
    assert "Required directory" in stderr
    assert git_calls == ""


def test_the_stage_flag_fails_closed_before_any_git_runs() -> None:
    """Absent is OFF; only the exact string `true` arms the push. And the refusal happens BEFORE the tree is read, so a misconfigured stage cannot even look."""
    for name in (
        "the-stage-flag-unset",
        "the-stage-flag-false",
        "the-stage-flag-uppercase-true",
        "the-stage-flag-one",
    ):
        code, _, stderr, git_calls, _, state = recorded(name)
        assert code == 1, name
        assert "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'" in stderr
        assert git_calls == "", "the tree was read with the stage flag off"
        assert refs(state, "console.git") == "", "the remote was written with the flag off"


def test_a_dry_run_needs_no_stage_flag() -> None:
    """The exemption is deliberate and narrow: a dry run never writes a remote. Recorded in both directions so a port cannot widen or close it."""
    code, stdout, _, git_calls, _, state = recorded("a-dry-run-with-no-stage-flag")
    assert code == 0
    assert git_calls != "", "the dry run did nothing at all"
    assert "push" not in verbs(git_calls), "a dry run pushed"
    assert len(stdout.strip().split("\n")[-1]) == 40, "no sha was printed"
    assert refs(state, "console.git") == "", "a dry run left a ref on the remote"


def test_the_committer_identity_is_required() -> None:
    """The commits are attributed to the operator's noreply identity (03-v2-autonomy.md section 0). An unset identity is a refusal, not a fallback to whatever the runner happens to have configured."""
    for name, variable in (
        ("without-a-committer-name", "AUTOPILOT_GIT_NAME"),
        ("without-a-committer-email", "AUTOPILOT_GIT_EMAIL"),
    ):
        code, _, stderr, git_calls, _, _ = recorded(name)
        assert code == 1, name
        assert "Required environment variable '%s' is not set" % variable in stderr
        assert git_calls == ""


def test_branch_mismatch_refuses_before_reading_the_handoff() -> None:
    code, _, stderr, git_calls, _, _ = recorded("a-branch-mismatch")
    assert code == 1
    assert "branch-mismatch: checkout is on 'work', caller named 'some-other-branch'" in stderr
    assert calls(git_calls) == ["rev-parse\t--abbrev-ref\tHEAD"], git_calls


def test_the_default_branches_are_refused_unconditionally() -> None:
    """renet/account/elite have no rulesets, so this is their only guard. The checkout is genuinely ON the branch, so the mismatch check passes and this is the thing doing the refusing."""
    for name, branch in (
        ("the-forbidden-branch-main", "main"),
        ("the-forbidden-branch-master", "master"),
    ):
        code, _, stderr, git_calls, _, _ = recorded(name)
        assert code == 1, branch
        assert "branch-forbidden: the autopilot never pushes '%s'" % branch in stderr
        assert len(calls(git_calls)) == 1, "the tree was read after the branch was refused"


def test_a_detached_head_is_refused_as_the_literal_head() -> None:
    """`git rev-parse --abbrev-ref HEAD` answers `HEAD` when detached, and the caller naming `HEAD` therefore passes the mismatch check, which is exactly why `HEAD` is in the forbidden list beside main and master."""
    code, _, stderr, _, _, _ = recorded("a-detached-head")
    assert code == 1
    assert "branch-forbidden: the autopilot never pushes 'HEAD'" in stderr


# --------------------------------------------------------------------------- The validator, and the three outcomes ---------------------------------------------------------------------------


def test_a_rejected_handoff_stages_nothing() -> None:
    """Four rejection classes, one recording each, and the same consequence: nothing staged, nothing pushed, exit 1."""
    for name, needle in (
        ("a-missing-handoff", "handoff-missing"),
        ("a-stale-base-head", "base-head-mismatch"),
        ("an-undeclared-dirty-file", "undeclared-dirty"),
        ("a-denylisted-workflow-file", "denylist-github"),
    ):
        code, stdout, stderr, git_calls, _, state = recorded(name)
        assert code == 1, name
        assert needle in stderr, name
        assert "handoff rejected; escalating (nothing staged, nothing pushed)" in stderr
        assert stdout == ""
        assert not wrote_anything(git_calls), (
            "%s: something was staged after a rejected handoff" % name
        )
        assert refs(state, "console.git") == "", name


def test_escalate_and_no_change_are_round_results_not_failures() -> None:
    """Exit 0, nothing staged. Exiting 1 here (as the twin did until 2026-08-09) made every escalating round paint the job red, which fired the generic failure latch and LOST the model's reason."""
    for name, outcome in (
        ("an-escalating-round", "escalate"),
        ("a-no-change-round", "no-change"),
    ):
        code, _, stderr, git_calls, _, _ = recorded(name)
        assert code == 0, outcome
        assert "outcome-%s: validated round, nothing staged and nothing pushed" % outcome in stderr
        assert not wrote_anything(git_calls)


def test_the_verdict_can_be_written_to_a_fifo() -> None:
    """`--verdict-out /dev/stdout` is what a workflow step passes when it wants the verdict in the run log, and `cat A >B` does not care that B is a pipe.

    THIS CAUGHT A REAL DIVERGENCE while porting: `shutil.copyfile` raises `SpecialFileError` on a fifo, so the port died where the twin wrote. Recorded so the plain open-and-write cannot be tidied back into a copyfile.

    ONE HARNESS NOTE, so a reader who sees this fail elsewhere does not go hunting the port. Under `subprocess.PIPE` (here) the reopen succeeds; under NODE's spawnSync it does not, because libuv backs a stdio pipe with a socketpair and reopening a socket through `/proc/self/fd` is ENXIO. The shadow-gate ledger scenario therefore wrote the verdict to a real file and `cat`ed it.
    """
    code, stdout, _, _, _, _ = recorded("a-verdict-written-to-a-fifo")
    assert code == 0
    assert json.loads(stdout)["outcome"] == "escalate"


def test_the_verdict_is_published_on_every_accepted_round(tmp_path: pathlib.Path) -> None:
    """BEFORE any outcome branching, so the post-boundary steps see the same validated object whether the round pushed, escalated or did nothing. Driven against the port directly, because the verdict file lands outside the recorded sections."""
    for name, outcome in (
        ("the-happy-path", "push"),
        ("an-escalating-round", "escalate"),
        ("a-no-change-round", "no-change"),
    ):
        sandbox = tmp_path / ("verdict-%s" % outcome)
        sandbox.mkdir(parents=True)
        console = CASE_KW[name]["scenario"](sandbox)
        out = sandbox / "verdict-out.json"
        code, _, stderr, _, _, _ = execute(
            PORT,
            sandbox,
            base_argv(console, "--verdict-out", str(out), "--dry-run"),
            {"AUTOPILOT_ALLOW_PUSH": "true"},
        )
        assert code == 0, stderr
        assert json.loads(out.read_text(encoding="utf-8"))["outcome"] == outcome


# --------------------------------------------------------------------------- The console staging path ---------------------------------------------------------------------------


def test_the_happy_path_commits_and_pushes_one_explicit_sha() -> None:
    """PUSH BY EXPLICIT SHA, never a bare branch name: the ref that leaves this machine is exactly the commit minted a line earlier."""
    code, stdout, stderr, git_calls, gh_calls, state = recorded("the-happy-path")
    assert code == 0
    # stdout carries the tripwire's own quiet line first; the SHA is the last.
    lines = stdout.strip().split("\n")
    assert lines[0].startswith("exfil-tripwire quiet: "), stdout
    sha = lines[-1]
    assert len(sha) == 40, stdout
    assert calls(git_calls)[-1] == "push\torigin\t%s:refs/heads/work" % sha
    assert "add\t--\tsrc.txt" in calls(git_calls), "the file was not staged one path at a time"
    assert not any(
        line.startswith(("add\t-A", "add\t--all")) or line == "add\t." for line in calls(git_calls)
    ), "wholesale staging"
    assert "pushed %s to origin refs/heads/work" % sha in stderr
    assert gh_calls == ""
    # The remote really carries that commit, which is the durable half of the claim.
    assert refs(state, "console.git") == "refs/heads/work %s" % sha, state


def test_a_pathspec_that_expands_is_refused_before_the_commit() -> None:
    """STAGED-SET EQUALITY, and the case it exists for. An UNTRACKED DIRECTORY is reported by `git status` as `dir/`, which the validator accepts as a declared path, and `git add -- dir/` then stages its two FILES. The staged set is therefore not the declared set, and the round stops with the unified diff on fd 2 as the evidence."""
    code, stdout, stderr, git_calls, _, state = recorded("a-pathspec-that-expands")
    assert code == 1
    assert "staged-set-mismatch: the staged set does not equal the validated files[]" in stderr
    assert "+newdir/a.txt" in stderr, "the unified diff evidence is missing from fd 2"
    assert "-newdir/" in stderr
    assert "commit" not in verbs(git_calls)
    assert "push" not in verbs(git_calls)
    assert stdout == ""
    assert refs(state, "console.git") == ""


def test_the_tripwire_stops_the_commit_before_it_is_made() -> None:
    """Rule 2: any single NEW file adding more than 8 KB trips, regardless of prefix. The diff is never uploaded and never printed, byte counts and paths only, because console artifacts are public."""
    code, _, stderr, git_calls, _, _ = recorded("a-tripped-tripwire")
    assert code == 1
    assert "TRIPWIRE:" in stderr
    assert "tripwire tripped; escalating (nothing committed, nothing pushed)" in stderr
    assert "xxxxxxxxxx" not in stderr, "the suspected diff content was printed"
    assert "commit" not in verbs(git_calls)
    assert "push" not in verbs(git_calls)


def test_the_failed_jobs_path_is_one_argument_even_with_a_space() -> None:
    """`${FAILED_JOBS:+--failed-jobs "$FAILED_JOBS"}` keeps the inner quotes, so a path with a space is ONE argument. A port that split it would hand node an unknown argument and the round would die for the wrong reason."""
    code, stdout, stderr, _, _, _ = recorded("a-failed-jobs-path-with-a-space")
    assert code == 0, stderr
    assert "exfil-tripwire quiet:" in stdout
    assert "unknown argument" not in stderr


def test_a_console_push_failure_is_the_scripts_last_word() -> None:
    """No usable remote for console: every validation has passed, and the failure surfaces as git's own status."""
    code, stdout, stderr, git_calls, _, _ = recorded("a-console-push-that-fails")
    assert code == 128, "git's own status, not the shim's 97 and not a smoothed 1"
    assert "does not appear to be a git repository" in stderr
    # The tripwire's quiet line is on stdout; the SHA is NOT, because `set -e` ends the run on git's status before the `echo`.
    assert "exfil-tripwire quiet:" in stdout
    assert not any(len(line) == 40 for line in stdout.strip().split("\n")), (
        "a sha was printed for a push that did not happen"
    )
    assert pushes(git_calls), "the push was never attempted"


# --------------------------------------------------------------------------- Submodules: phase 1, phase 2 and the ordering that makes the split worth it ---------------------------------------------------------------------------


def test_submodules_are_committed_then_pushed_before_console() -> None:
    """THE ORDER IS THE DESIGN. The submodule push must precede the console push, so the pointer console publishes always names a commit that already exists on the remote. The reverse order publishes a console commit pointing at a SHA nobody else can fetch."""
    code, stdout, stderr, git_calls, _, state = recorded("a-submodule-round")
    assert code == 0, stderr
    ordered = pushes(git_calls)
    assert len(ordered) == 2, ordered
    assert ordered[0].startswith("-C\t<sandbox>/console/private/renet\tpush\t"), ordered[0]
    assert ordered[1].startswith("push\torigin\t"), ordered[1]
    assert "gitlink verified: private/renet -> " in stderr
    assert "all repos validated; nothing has been pushed yet" in stderr
    # And that line arrives BEFORE the first push, which is the whole claim.
    assert stderr.index("all repos validated") < stderr.index("pushed ")
    sha = stdout.strip().split("\n")[-1]
    assert refs(state, "console.git") == "refs/heads/work %s" % sha, state
    # The submodule's own remote carries the work branch too, which is what makes the console pointer fetchable.
    assert "refs/heads/work " in refs(state, "renet.git"), state


def test_the_submodule_branch_is_created_at_current_head() -> None:
    """NOT at origin/main. Section 5's anti-rollback rule is ancestry, and branching at the recorded pointer makes it true by construction; branching at origin/main would silently rebase the round's work onto a different base."""
    git_calls = recorded("a-submodule-round")[3]
    assert "-C\t<sandbox>/console/private/renet\tcheckout\t-q\t-b\twork" in calls(git_calls)
    assert not any("origin/main" in line for line in calls(git_calls)), (
        "the branch was created somewhere other than current HEAD"
    )


def test_a_submodule_refusal_leaves_zero_remote_writes() -> None:
    """The reason the phases are split. A file declared in the submodule that is neither tracked nor on disk stops the round in phase 1, before anything has been pushed anywhere."""
    code, _, stderr, git_calls, _, state = recorded("a-submodule-path-that-is-missing")
    assert code == 1
    assert (
        "submodule-path-missing: 'private/renet/ghost.go' is declared but is neither "
        "tracked in the submodule nor present on disk" in stderr
    )
    assert pushes(git_calls) == [], "a remote was written"
    assert refs(state, "console.git") == ""
    assert "refs/heads/work" not in refs(state, "renet.git")


def test_a_submodule_staged_set_mismatch_refuses() -> None:
    """The identical check the console boundary applies, because a pathspec that expands is the same bug here. Driven with a file the model left ALREADY STAGED in the submodule index and did not declare."""
    code, _, stderr, git_calls, _, _ = recorded("a-submodule-staged-set-mismatch")
    assert code == 1
    assert "submodule-staged-set-mismatch: 'private/renet' staged set" in stderr
    assert "+extra.go" in stderr, "the unified diff evidence is missing"
    assert pushes(git_calls) == []


def test_the_submodule_tripwire_sees_parent_relative_paths() -> None:
    """The prefixes are rewritten to `a/private/renet/` so the same scope map that governs a console fix governs this one; without them every byte would look out of scope."""
    code, _, stderr, git_calls, _, _ = recorded("a-tripped-tripwire-in-a-submodule")
    assert code == 1
    assert "private/renet/blob.txt" in stderr, "the tripwire saw a submodule-relative path"
    assert (
        "tripwire tripped in submodule 'private/renet'; escalating "
        "(nothing committed there, nothing pushed)" in stderr
    )
    assert "commit" not in " ".join(calls(git_calls)).split("\t")


def test_an_existing_local_branch_in_the_submodule_refuses() -> None:
    """Checking it out would move HEAD across a tree the model has already edited. Refuse rather than guess which side wins."""
    code, _, stderr, git_calls, _, _ = recorded("a-submodule-branch-that-already-exists")
    assert code == 1
    assert (
        "submodule-branch-exists: 'private/renet' already has a local 'work' but HEAD is on "
        "'main'; refusing to move HEAD across the round's edits" in stderr
    )
    assert not any(line.split("\t")[-1].startswith("checkout") for line in calls(git_calls))


def test_a_submodule_push_that_is_not_a_non_fast_forward_refuses_to_guess() -> None:
    """The adoption path exists for ONE failure shape. Anything else stops the round rather than rewriting a branch on a hunch."""
    code, _, stderr, git_calls, _, state = recorded("a-submodule-push-that-fails-another-way")
    assert code == 1
    assert (
        "submodule-push-failed: 'private/renet' push failed for a reason that is not a "
        "non-fast-forward; refusing to guess" in stderr
    )
    assert not any(line.startswith("push\t") for line in calls(git_calls)), (
        "console was pushed anyway"
    )
    assert refs(state, "console.git") == ""


# --------------------------------------------------------------------------- The orphan adoption, which is the most dangerous code in the file ---------------------------------------------------------------------------


def test_a_foreign_branch_is_never_rewritten() -> None:
    """ "Ours" is TWO independent facts and this is the first: the tip's committer email must be the autopilot identity. Somebody else's branch stops the round even though it sits at exactly the name this round wants."""
    code, _, stderr, git_calls, _, state = recorded("a-foreign-orphan-branch")
    assert code == 1
    assert "submodule-foreign-branch: 'private/renet' branch 'work' already exists at" in stderr
    assert "rather than the autopilot identity" in stderr
    assert not any(line.startswith("push\t") for line in calls(git_calls)), (
        "console was pushed anyway"
    )
    assert refs(state, "console.git") == ""


def test_an_unrelated_history_is_never_built_on() -> None:
    """The second fact: the tip must share this round's merge-base with origin/main. A branch that merely happens to sit at the same name is not a continuation of this line of work."""
    code, _, stderr, _, _, _ = recorded("an-unrelated-orphan-history")
    assert code == 1
    assert "submodule-unrelated-branch: 'private/renet' remote tip" in stderr
    assert "refusing to build on an unrelated history" in stderr


def test_an_unresolvable_main_refuses_rather_than_adopting_on_identity_alone() -> None:
    """BOTH checks are required, so an unresolvable main is a REFUSAL, not a skip. A committer email is forgeable by anyone who can push, which makes the identity check the weaker half; failing closed is the only reading under which "both required" is true."""
    code, _, stderr, git_calls, _, _ = recorded("an-orphan-with-no-resolvable-main")
    assert code == 1
    assert (
        "submodule-main-unresolvable: 'private/renet' has no resolvable origin/main even "
        "after a fetch, so the ancestry half of the adoption check cannot run; refusing to "
        "adopt on the identity check alone" in stderr
    )
    assert not any(line.startswith("push\t") for line in calls(git_calls))


def test_an_orphan_that_does_not_apply_cleanly_stops_for_a_human() -> None:
    code, _, stderr, git_calls, _, _ = recorded("an-orphan-that-conflicts")
    assert code == 1
    assert "submodule-adopt-conflict: 'private/renet' this round's commit does not apply" in stderr
    assert "a human must reconcile the branch" in stderr
    assert not any(line.startswith("push\t") for line in calls(git_calls))


def test_a_provable_orphan_is_adopted_and_the_console_check_is_re_run() -> None:
    """PHASE 4. The adoption moved the submodule SHA, so the gitlink console staged in phase 2 now names a commit that is no longer the branch tip. Re-stage and re-run the SAME validation rather than patching the index and trusting it, which is why `gitlink verified` appears TWICE."""
    code, stdout, stderr, git_calls, _, state = recorded("an-orphan-that-is-adopted")
    assert code == 0, stderr
    assert "is an autopilot orphan; rebuilding this round's commit on top of it" in stderr
    assert "adopted the orphan in 'private/renet': pushed" in stderr
    assert (
        "an orphan was adopted; re-staging the pointers and re-running the console validation"
        in stderr
    )
    assert stderr.count("gitlink verified: private/renet -> ") == 2, (
        "the console validation was not re-run after the SHA moved"
    )
    # The two gitlink lines must name DIFFERENT shas: the second is the adopted commit, and a port that skipped the re-stage would print the first twice.
    verified = [line for line in stderr.split("\n") if "gitlink verified" in line]
    assert verified[0] != verified[1], "the pointer was not re-staged after the adoption"
    sha = stdout.strip().split("\n")[-1]
    assert len(sha) == 40
    # Three pushes: the submodule attempt that was rejected, the adopted commit, and console LAST, so the pointer console publishes names a commit that already exists on the remote.
    ordered = pushes(git_calls)
    assert len(ordered) == 3, ordered
    assert ordered[2].startswith("push\torigin\t"), ordered[2]
    assert refs(state, "console.git") == "refs/heads/work %s" % sha, state


# --------------------------------------------------------------------------- The unreachable arms, named rather than skipped ---------------------------------------------------------------------------


def test_the_unreachable_refusals_are_unreachable_for_the_same_reason() -> None:
    """Five refusals in the twin cannot be entered from the CLI. The honest recording is of the gate that stops each one, asserting both that it fired and that the unreachable message did not."""
    # 1. submodules[] with the stage flag OFF: the VALIDATOR refuses, so the write-site's belt-and-braces copy is never reached.
    code, _, stderr, _, _, _ = recorded("submodules-with-the-stage-flag-off")
    assert code == 1
    assert "submodules-disabled" in stderr, "the validator did not refuse first"
    assert "refusing 1 submodule change(s)" not in stderr, (
        "the write-site refusal became reachable; give it its own case"
    )

    # 2. an absent submodule: the parent reports the path NOT dirty, so the validator refuses before `submodule-missing` or the toplevel check.
    code, _, stderr, _, _, _ = recorded("a-submodule-whose-checkout-is-gone")
    assert code == 1
    assert "path-not-dirty: private/renet" in stderr
    assert "submodule-missing:" not in stderr
    assert "submodule-not-initialized:" not in stderr

    # 3. a forbidden branch inside the submodule loop: the top-level check has already refused the same three names.
    code, _, stderr, _, _, _ = recorded("a-submodule-round-on-a-forbidden-branch")
    assert code == 1
    assert "branch-forbidden: the autopilot never pushes 'main'" in stderr
    assert "submodule-branch-forbidden" not in stderr

    # 4. outcome-unknown: the schema pins the enum, so a fourth value never reaches the verdict at all.
    code, _, stderr, _, _, _ = recorded("an-outcome-the-schema-forbids")
    assert code == 1
    assert "handoff.outcome: must be one of push|escalate|no-change" in stderr
    assert "outcome-unknown" not in stderr


def test_the_toplevel_predicate_is_driven_directly(tmp_path: pathlib.Path) -> None:
    """`submodule-not-initialized`'s PREDICATE, whose failure mode is committing submodule content into console as ordinary files. Unreachable from the CLI (case 2 above), so it is driven here against three shapes: a real nested checkout, a plain directory inside a parent repo, and an absent path.

    `--git-dir` WOULD ANSWER YES FOR THE SECOND ONE, which is the whole reason the twin compared toplevels instead.
    """
    console = build(tmp_path, submodule=True)
    ok, top = ap.submodule_toplevel_matches(str(console), "private/renet")
    assert ok is True
    assert pathlib.Path(top) == console / "private" / "renet"

    (console / "private" / "plain").mkdir()
    ok, top = ap.submodule_toplevel_matches(str(console), "private/plain")
    assert ok is False, "a plain directory inside the parent passed as its own checkout"
    assert pathlib.Path(top) == console, "git answered with the PARENT, as documented"

    ok, top = ap.submodule_toplevel_matches(str(console), "private/absent")
    assert ok is False
    assert top == ""


def test_pure_helpers_are_exercised_directly(tmp_path: pathlib.Path) -> None:
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

    path = tmp_path / "lines"
    path.write_bytes(b"one\ntwo\npartial")
    assert ap.read_lines(str(path)) == ["one", "two"], "a final unterminated line is dropped"


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_an_unwritable_verdict_out_stops_the_round(tmp_path: pathlib.Path) -> None:
    """Exit 1 either way; the twin said it in bash's words and the port says it in its own, which is the one place the two diverge on fd 2. Compared on the code, on the empty stdout, on the call log and on the state left behind, not on the sentence."""
    name = "an-unwritable-verdict-out"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""
    assert want[3] == got[3], "the git calls diverged"
    assert want[4] == got[4] == ""
    assert want[5] == got[5], "the state left behind diverged"
    assert not wrote_anything(want[3]), (
        "something was staged before the verdict could not be written"
    )
    assert want[2].strip() != "", "the twin's refusal was recorded silent"
    assert got[2].strip() != "", "the port refused silently"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real module, drops the `--` separator from every `git add`, and runs `main`. See the control below.
PLANT = """import sys

from rediacc_ci.autopilot import autopilot_push as subject

_real = subject._run


def _add_without_the_separator(argv, **kwargs):
    if "add" in argv and "--" in argv:
        argv = [token for i, token in enumerate(argv) if token != "--" or i < argv.index("add")]
    return _real(argv, **kwargs)


subject._run = _add_without_the_separator
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_drop_of_the_pathspec_separator_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `git add -- <path>` stages a PATH; `git add <path>` stages whatever git decides that word is, and the words here are model-authored. A declared file whose name begins with a dash becomes an OPTION to git, which is the one shape of argument injection this boundary can still be handed, and the separator is what stops it. Dropping it changes nothing else in this fixture:
    git prints nothing either way, the staged set is identical, so the commit, its SHA, both streams and the ref that lands on the remote are all unchanged, and only the `--- git calls ---` section sees it.

    A REFSPEC MUTATION WOULD NOT HAVE PROVED THIS. Pushing `work:refs/heads/work` instead of `<sha>:refs/heads/work` was the first plant here and it FAILED as a control: git echoes the refspec in its own progress line on fd 2, so a stream comparison catches it too. Measured, and it is why the plant moved to the separator.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE. `script_dir()` resolves the two `.cjs` controls from `parents[3]` of the module's own path, so a copy under a temporary directory looks for the validator and the tripwire where they are not and dies before any git call. The wrapper imports the tracked module unmodified and replaces one attribute in its own process, so the file on
    disk is never written to at all.
    """
    original = PORT.read_text(encoding="utf-8")
    assert '"--",' in original, "the plant's target moved"

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(PLANT, encoding="utf-8")

    name = "the-happy-path"
    want = recorded(name)
    assert "add\t--\tsrc.txt" in calls(want[3]), "the corpus moved"

    sandbox = tmp_path / "planted"
    sandbox.mkdir(parents=True)
    console = CASE_KW[name]["scenario"](sandbox)
    planted = execute(mutant, sandbox, base_argv(console), {"AUTOPILOT_ALLOW_PUSH": "true"})
    assert "add\tsrc.txt" in calls(planted[3]), "the plant did not change the staging argv"
    assert "add\t--\tsrc.txt" not in calls(planted[3])
    for index in (0, 1, 2, 4, 5):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
