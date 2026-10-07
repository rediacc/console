"""The proof for every ported guard: a differential against its frozen golden.

WHY A DIFFERENTIAL, restated for this phase because the argument is not the same one `test_shellscan_differential` makes. That file compares 28 INTERNAL fields, because `command-scan.sh` is a library whose functions are the surface. A guard has no such surface. Its entire contract is what the harness observes:

    the exit code            0 allows the tool call, 2 refuses it
    stdout                   what the session sees
    stderr                   the message, which for at least 21 `check_out`
                             assertions in the suite IS the product ("an exit
                             code alone cannot tell 'blocked, here is the
                             correct command' from 'blocked, good luck'")

So three fields are compared, byte for byte, and the richness that the other differential gets from field count this one gets from INPUT count: every guard is run against the events its own suite cases pair with it, against a deterministic sample of every OTHER guard's events, against 25 degenerate event shapes the suite never produces, and against every edge case the port module declares from its twin's comments. Cross-feeding is not padding: over-blocking only ever shows up on somebody else's input.

WHERE THE OTHER SIDE OF THE COMPARISON COMES FROM, since PLAN-retire-bash-oracles A3. Until then this file forked a real `bash` process per case against the tracked original at `.claude/oracles/`; A1 froze that same driver's answers into `tests/goldens/<stem>.jsonl` over the FULL corpus, A2 pointed the comparison at that file, and A3 deleted the oracle tree and the driver once every twinned guard's golden was proven to match. `test_guard_matches_golden` below is now the only comparison; a guard's stderr is the product's own, not a transcription of somebody else's.

WHAT STILL MAKES THE COMPARISON FAIR, carried over from the driver era because the reasons did not stop applying just because one side stopped being a second process:

  * THE ENVIRONMENT IS BUILT HERE, RATHER THAN INHERITED. An inherited
    `CLAUDE_PROJECT_DIR`, `PATH` or `GIT_INDEX_FILE` would make the result depend on who ran it, or on what a previous test left behind.
  * `gh` IS STUBBED. Half these guards call it, and an unstubbed one makes a
    recording a network test: two runs seconds apart can disagree because a PR changed, and that disagreement would be reported as a port defect.
  * BYTES, NOT TEXT. `subprocess` in text mode translates universal newlines,
    so a lone `\\r` in a message would come back as `\\n`. `test_shellscan_differential` records finding this the hard way; it is not re-learned here.
  * THE WALL CLOCK IS FROZEN. A guard that names today in its message would
    otherwise need a new golden every midnight; see "The frozen clock" below.

ANTI-VACUITY. Three separate controls, because each covers a different way this file could pass while proving nothing:

  1. `test_every_guard_discriminates` -- a guard whose whole case set returns
     one exit code is a guard the corpus never exercised. Comparing two
     constants is not a comparison.
  2. `test_the_differential_can_fail` -- every port declares a DEFECT, one
     source substitution, and the differential must catch it. A green that has
     never been shown to be able to go red is not evidence.
  3. `test_corpus_is_real_and_large_enough` -- a recovery RATIO against the
     call sites counted in the same pass, so a parser that quietly stops
     understanding the suite reds instead of shrinking the corpus to three
     strings.

RUNNING THE DEEP SWEEP. `REDIACC_GUARD_DIFF_FULL=1` feeds EVERY payload to
EVERY guard instead of the cross sample. `regolden.py` always runs this way, since a golden built from the default sample would have no record for a payload a later default-mode run might legitimately ask about.
"""

import builtins
import contextlib
import datetime
import json
import os
import pathlib
import re
import subprocess
import time
import types
import typing

import pytest

from rediacc_hooks import dispatch, guards, hookio
from rediacc_hooks.tests import goldenio, guardcorpus
from rediacc_hooks.wellknown import GH_ORIGIN, GH_REPO

ROOT = guardcorpus.repo_root()

FULL = os.environ.get("REDIACC_GUARD_DIFF_FULL", "") not in ("", "0")


# --------------------------------------------------------------------------- The stub environment ---------------------------------------------------------------------------

# `gh`, stubbed to the shape every guard here already treats as its fail-open path: nothing on stdout, a non-zero exit. Guards that need it to SUCCEED declare their own stub through `ENVS` on the port module, exactly as the suite's own `stub_gh` and `_gc_shim` helpers do for the same guards.
#
# WHY STUB AT ALL, since both sides would call the same real `gh`. Because they would not call it at the same MOMENT. The bash side runs the whole corpus first and the Python side follows; a PR that changes state in between turns into a field that differs, reported as a port defect. Measured cost of the real thing on one case: a network round trip per invocation, times several hundred cases, times two sides.
DEFAULT_STUBS = {
    "gh": "#!/bin/sh\nexit 1\n",
}


def _stub_dir(tmp_path, stubs):
    directory = tmp_path / ("stubs-%s" % abs(hash(tuple(sorted(stubs.items())))))
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in stubs.items():
        path = directory / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return directory


# --------------------------------------------------------------------------- Named git fixtures ---------------------------------------------------------------------------
#
# WHY THEY EXIST, and the control that demanded them. Roughly half these guards read local git state -- a branch name, whether the branch is ahead of its remote, whether a worktree is dirty. Run against THIS checkout they all take one branch of their logic, whichever branch this worktree happens to be in, and `test_every_guard_discriminates` then reports the guard as answering identically on every case. That is not a nuisance: it is the control saying the comparison could not have failed. `block_merge_with_unpushed` was the first port to trip it, on the first run, because no `origin/<branch>` ref exists in a feature worktree and the guard fails open on every input.
#
# So a module names the git worlds its twin distinguishes, the harness builds each one ONCE per session, and both sides are pointed at it through CLAUDE_PROJECT_DIR. The repositories are built with `git init`, never cloned and never fetched: no network, and nothing outside the temporary directory is read or written.
FIXTURE_TOKEN = "{FIXTURE:%s}"  # noqa: S105


# A HOME no host owns. FOUND 2026-09-30 (#0c7d2263's sweep of the world builders): `GIT_CONFIG_GLOBAL=/dev/null` stops git reading `~/.gitconfig`, but NOT `$XDG_CONFIG_HOME/git/ignore` and `.../attributes`, which git reads by default whatever the global config says, so a `git add -A` in a fixture honoured this machine's personal ignore list. And an inherited `GIT_DIR`, `GIT_INDEX_FILE` or `GIT_WORK_TREE` (a pytest run from inside a git hook sets them) would point
# `git init` at the host's repository instead of the fixture's.
NO_HOME = "/nonexistent"


def _scrubbed(environ):
    """`environ` without a single inherited `GIT_*` variable."""
    return {k: v for k, v in environ.items() if not k.startswith("GIT_")}


def _git_env():
    return dict(
        _scrubbed(os.environ),
        HOME=NO_HOME,
        XDG_CONFIG_HOME=NO_HOME,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        # PINNED, found live by PLAN-retire-bash-oracles A1's golden freeze. An unpinned date left the SHAPE of `_build_repo`'s commits deterministic (same branch, same file, same commit COUNT) but not their SHA1s, since a commit hash folds in the timestamp: `block_merge_with_unpushed`'s message quotes the short hash of each unpushed commit, so two builds of the identical "ahead"
        # fixture minutes apart produced two different messages, and a golden frozen from one build never matched a differential run against another. Every commit this harness makes now lands at the same instant, so the SAME fixture spec always hashes to the SAME commit, in this process or in `regolden.py`'s.
        GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )


def _git(cwd, *args):
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=_git_env(),
    )


def _build_repo(path, branch, ahead):
    """A repo on `branch` with `ahead` commits its origin has never seen."""
    bare = path.parent / (path.name + ".origin.git")
    bare.mkdir(parents=True)
    _git(bare, "init", "--bare", "--initial-branch=main", "-q")
    path.mkdir(parents=True)
    _git(path, "init", "--initial-branch=main", "-q")
    _git(path, "remote", "add", "origin", str(bare))
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(path, "add", "seed.txt")
    _git(path, "commit", "-q", "-m", "seed")
    if branch != "main":
        _git(path, "checkout", "-q", "-b", branch)
    _git(path, "push", "-q", "origin", branch)
    for i in range(ahead):
        (path / ("local-%d.txt" % i)).write_text("x\n", encoding="utf-8")
        _git(path, "add", ".")
        _git(path, "commit", "-q", "-m", "local only %d" % i)
    return path


def _synthetic_this_worktree(path):
    """A FIXED, SYNTHETIC repository in the shape of this checkout, built from nothing and identical on every build.

    DECIDED 2026-09-24 (PLAN-retire-bash-oracles A4, W-A's open question). Until then this was a `--shared` clone of the LIVE checkout, taken once per session. That was already a step up from pointing `CLAUDE_PROJECT_DIR` at the checkout itself, which is what four guards' `this-worktree` variant did until 2026-09-22: a concurrent session's commit landed between the bash pass and the Python side, and `block_merge_with_unpushed` reported "66 commit(s) ... are not pushed" from bash and "67" from the port, while `block_unverified_push` named two different `HEAD^{tree}` hashes in its refusal. A per-session clone closed that race, because both sides of ONE run read one snapshot.

    GOLDENS REOPENED IT ACROSS RUNS. A golden is a record frozen in one session and compared in every later one, so a snapshot of a SHARED, MOVING tree is a different world every time the tree moves: the unpushed-commit list, the `HEAD^{tree}` hash in the unverified-push refusal and the epic list `block_untagged_commit` prints from `agent/pr/<branch>.md` all drift with every commit anyone lands, and each drift would have to be re-recorded as "intentional" when it is nothing of the kind. So the world is now synthetic, like every other fixture here: `_build_repo`'s pinned-date commits, so the same build always hashes to the same commits.

    WHAT IT KEEPS OF THE REAL SHAPE, which is why it is not just `git-ahead` again: this worktree's own branch naming (`MMDD-N`), an `agent/pr/<branch>.md` epic snapshot in the format `worklist.py --publish` writes (so `block_untagged_commit`'s epic list and its "names no epic on this branch" arm read real-looking data), a remote-tracking ref BEHIND the branch by three commits (the ahead-of-remote arm), and no pre-push receipt (the "no local gate run has judged this tree" arm `block_unverified_push` answered from the live tree). What it gives up is the live tree's 7,000-file size, which no guard's answer depends on.
    """
    _build_repo(path, "0923-1", 2)
    snap = path / "agent" / "pr"
    snap.mkdir(parents=True)
    (snap / "0923-1.md").write_text(
        "<!-- generated by worklist.py --publish; edit the worklist, not this file -->\n"
        "# Work in 0923-1\n\n"
        "### Retire the bash hook oracles\n\n`PR-TASK: 5d0c1a2b`\n\n_no tracked items yet_\n\n"
        "### Tooling transformation\n\n`PR-TASK: e87fa3ce`\n\n_no tracked items yet_\n",
        encoding="utf-8",
    )
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "chore(pr): epic snapshot")
    return path


# Exposed for a port module's own `FIXTURES` table: `build_repo(path, branch, ahead)` is the whole vocabulary most git guards need, and re-deriving it per module would be four copies of `git init` semantics.
build_repo = _build_repo
git_in = _git

FIXTURE_BUILDERS = {
    # A feature branch with two commits the remote has never seen. This is the 2026-09-01 near-miss shape: pushed head, later commit still local.
    "git-ahead": lambda p: _build_repo(p, "0831-1", 2),
    # The same branch, fully pushed. The ALLOW side of the same guard.
    "git-synced": lambda p: _build_repo(p, "0831-1", 0),
    # On main, where /pr-merge deliberately ends.
    "git-main": lambda p: _build_repo(p, "main", 2),
    # This checkout's SHAPE, synthetic and pinned. The key keeps its historical name because three guards' `ENVS` name it; `_synthetic_this_worktree` above carries why a clone of the live tree was retired for goldens.
    "this-worktree-snapshot": _synthetic_this_worktree,
}


# --------------------------------------------------------------------------- The host a guard would otherwise read ---------------------------------------------------------------------------
#
# FOUND 2026-09-25 (#09f4643f) by running this file from a second checkout and under a different HOME and PATH. Two guards read the HOST rather than the payload, and their goldens froze whatever this machine happened to be:
#
#   * `block_stale_pr_branch_date` falls back to `ev.cwd`, which the harness set to the live checkout, so about 57 records carried its current branch (`0923-1`) and a next-branch suggestion computed from its real refs. Every new branch anyone cut moved the golden.
#   * `block_host_toolchain_run` asks the real PATH whether `ruff`/`go`/`shfmt` are executable and walks the real tree for `.venv` / `node_modules`, both through `hookio.repo_root()`, which is the module's own location and ignores every variable the harness sets. Nine records flipped on a host where `packages/cli/node_modules` or `~/.local/bin/ruff` was absent.
#
# So each gets a synthetic world, built once per session like every other fixture here, and the harness hands it over rather than the guard being changed: `cwd` for the branch guard, and a `repo_root` plus a PATH tail made only of the fixture's own `bin/` for the toolchain guard. The guard's code path is untouched; only the world it looks at stops being this machine.
#
#   * `block_premature_ready` resolved a selector-less `gh pr ready` against `git -C . branch --show-current`, the PYTEST PROCESS's directory, whatever `cwd` the harness handed the event. Its goldens were frozen on a checkout with a branch; CI's `actions/checkout` of a pull_request is a DETACHED merge commit, where the same read prints nothing and the guard takes its "no current branch" refusal instead. Six records went red in CI only (run 37649744806, #6f901a98). The guard now falls back to `ev.cwd`, and the harness hands it `console-pr-checkout`.
CWD_WORLDS = {
    "block_stale_pr_branch_date": "stale-branch-checkout",
    "block_premature_ready": "console-pr-checkout",
}
HOST_WORLDS = {"block_host_toolchain_run": "toolchain-host"}


def _stale_branch_checkout(path):
    """An `MMDD-N` checkout whose next-free-slot search has to step over BOTH ref families.

    The frozen clock reads 0229 (0301 in `tz-far-east`), so `0229-1` taken locally and `0229-2` taken on the remote make the suggestion `0229-3`: a guard that consulted only one of the two would suggest a slot that collides, and the golden would say so.
    """
    _build_repo(path, "0825-7", 1)
    _git(path, "branch", "0229-1")
    _git(path, "update-ref", "refs/remotes/origin/0229-2", "HEAD")
    return path


def _toolchain_host(path):
    """A repo root and a `bin/` that decide every host question `block_host_toolchain_run` asks.

    `ruff` and `actionlint` are installed; `shfmt` is HALF-installed (a mode-0644 file, which `command -v` prints and `test -x` refuses, the case the guard's comments measured); `go`, `shellcheck`, `aws`, `bw` and `bws` are absent. The tree carries the account submodule's `package.json` (the NEEDS_ENV arm) and the three host-built toolchains the hostbound walk looks for.
    """
    for rel in ("private/account/node_modules", "packages/cli/node_modules"):
        (path / rel).mkdir(parents=True)
    (path / "private/growth/video_pipeline/.venv").mkdir(parents=True)
    (path / "private/account/package.json").write_text("{}\n", encoding="utf-8")
    (path / "private/account/scripts/rotation").mkdir(parents=True)
    (path / "private/account/scripts/rotation/rotate.sh").write_text("", encoding="utf-8")
    (path / "private/growth/video_pipeline/run.sh").write_text("", encoding="utf-8")
    tools = path / "bin"
    tools.mkdir()
    for name, mode in (("ruff", 0o755), ("actionlint", 0o755), ("shfmt", 0o644)):
        (tools / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (tools / name).chmod(mode)
    return path


def _console_checkout(path, detached, branch="0923-1"):
    """A checkout whose `origin` names the console repository, on `branch` (the `MMDD-N` name `0923-1` by default) or detached at the same commit.

    The origin URL is the one `gh` and `shellscan._origin_repo` read the repo from, so a selector-less `gh pr ready` here is a console flip; the bare remote `_build_repo` pushed to is only how the commits got a remote-tracking ref. `git remote get-url` reads config and never touches the network. DETACHED is what `actions/checkout` produces for a pull_request, and what `gh pr ready` with no selector cannot resolve (gh 2.98.0 there: "could not determine current branch: failed to run git: not on any branch", rc=1).
    """
    _build_repo(path, branch, 0)
    _git(path, "remote", "set-url", "origin", "%s/%s.git" % (GH_ORIGIN, GH_REPO))
    if detached:
        _git(path, "checkout", "-q", "--detach")
    return path


# The host worlds, registered beside every other named fixture so `fixture_path` builds each once per session.
FIXTURE_BUILDERS["stale-branch-checkout"] = _stale_branch_checkout
FIXTURE_BUILDERS["toolchain-host"] = _toolchain_host
FIXTURE_BUILDERS["console-pr-checkout"] = lambda p: _console_checkout(p, detached=False)
FIXTURE_BUILDERS["console-pr-detached"] = lambda p: _console_checkout(p, detached=True)


# THE ROOT A PAYLOAD SPELLS LITERALLY. `block_agent_browser_repo_output`'s "an absolute path inside the repo" case writes `/home/developer/console/x.png` into its EDGE_CASES, which means "inside the repo" only in a checkout at that path; from any other checkout the guard answers "outside" and the case silently tests the opposite arm. The payload is re-homed onto THIS checkout just before the guard reads it, while the case key (`golden_case_key`) is still hashed from the payload as written, so the key is the same everywhere and `goldenio.normalize` turns the answer back into `<REPO>`. On the recording checkout it is the identity.
LITERAL_ROOT = "/home/developer/console"


def rehome(payload):
    """`payload` with `LITERAL_ROOT` pointed at the checkout actually running."""
    return payload.replace(LITERAL_ROOT, str(ROOT))


def case_cwd(stem, work):
    """The directory a case runs in: the guard's synthetic checkout, or this one."""
    name = CWD_WORLDS.get(stem)
    return fixture_path(work, name) if name else str(ROOT)


def _revive_process_world(stem):
    """Rebuild `stem`'s spawned-process world if any of its shells has exited. True when it did.

    FOUND 2026-09-30 (#af1d1d05): `test_the_differential_can_fail` reported `block_bash_write_to_running_script`'s DEFECT as changing no answer in a FULL run and passed filtered. The DEFECT only changes an answer when a named script is RUNNING (the guard allows everything else), so its every witness needs the world's live `bash <script>` shells, and those shells die two ways a filtered run never
    reaches: each runs a 600-second `sleep`, and a FULL pass reaches this guard's defect well past ten minutes after the world was built; and under `-n`, a second xdist worker building the same fixed-path world waits out the 300-second lock and then kills the first worker's shells. The world's builder respawns only when its `_CHILDREN` list is empty, so a dead world stayed dead for the rest of the session.

    The rebuild goes through the module's own reaper and lock list, released so the respawn can take the lock again from this same process (an flock held on one descriptor refuses a second descriptor of the same process).
    """
    module = guards.load(stem)
    children = getattr(module, "_CHILDREN", None)
    if not children or all(child.poll() is None for child in children):
        return False
    module._reap()
    # Reaped by the pid `Popen` holds as well: a dropped `Popen` whose shell was never waited on raises a ResourceWarning at collection, which pytest turns into a failure of whichever test happens to be running.
    for child in children:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            child.kill()
            child.wait(timeout=10)
    for fd in module._LOCK_FDS:
        os.close(fd)
    module._LOCK_FDS.clear()
    children.clear()
    names = set(getattr(module, "FIXTURES", {}))
    for key in [k for k in _FIXTURES if k[1] in names]:
        del _FIXTURES[key]
    return True


def case_env(stem, extra, stubs, work):
    """`_base_env` for one case, with a `HOST_WORLDS` guard's PATH cut down to stubs + its fixture `bin/`."""
    _revive_process_world(stem)
    stub_dir = _stub_dir(work, dict(DEFAULT_STUBS, **stubs))
    env = _base_env(stub_dir, extra, work)
    name = HOST_WORLDS.get(stem)
    if name and "PATH" not in extra:
        env["PATH"] = "%s:%s" % (stub_dir, pathlib.Path(fixture_path(work, name)) / "bin")
    return env


def host_hookio(stem, work):
    """A copy of `hookio` whose `repo_root()` answers the guard's fixture world, or None.

    A COPY, bound into the guard module's namespace, the same move `frozen_clock` makes with `datetime`: patching the shared `hookio` would change `repo_root()` for every other caller in the process too.
    """
    name = HOST_WORLDS.get(stem)
    if name is None:
        return None
    root = pathlib.Path(fixture_path(work, name))
    shim = types.ModuleType("hookio")
    shim.__dict__.update(vars(hookio))
    setattr(shim, "repo_root", lambda: root)  # noqa: B010 -- a ModuleType attribute mypy cannot see
    return shim


@contextlib.contextmanager
def host_world(stem, work):
    """Point `stem`'s module at `host_hookio` for one call, if it has a host world at all."""
    shim = host_hookio(stem, work)
    if shim is None:
        yield
        return
    module = guards.load(stem)
    saved = module.hookio
    setattr(module, "hookio", shim)  # noqa: B010 -- a guard module attribute mypy types as a module
    try:
        yield
    finally:
        setattr(module, "hookio", saved)  # noqa: B010


_FIXTURES = {}


def all_builders():
    """The shared table plus every one a port module declares for itself.

    A guard whose twin distinguishes a world nothing else needs declares it in
    its own file, as `FIXTURES = {"name": builder}`, and the name is then usable
    in its `ENVS`. That keeps a port and the world it is judged in in ONE file, which matters when several agents are porting different guards into this
    package at once: a shared table is a shared edit, and a shared edit is a
    collision.
    """
    table = dict(FIXTURE_BUILDERS)
    for stem in guards.stems():
        for name, builder in getattr(guards.load(stem), "FIXTURES", {}).items():
            if name in table and table[name] is not builder:
                msg = (
                    "fixture %r is declared by %s and by another module with a different "
                    "builder; two worlds sharing a name would silently give one guard the "
                    "other's tree" % (name, stem)
                )
                raise AssertionError(msg)
            table[name] = builder
    return table


@contextlib.contextmanager
def _hermetic_process_env():
    """`os.environ` as `_git_env` builds it, for the duration of one world build.

    A PORT MODULE'S OWN BUILDER does not call `_git_env`: `block_untagged_commit`'s `epic-snapshot`, for one, starts from `dict(os.environ, ...)`, so it inherited every `GIT_*` variable, the host's XDG ignore list, and an unpinned commit date. Swapping the process environment here gives every builder, shared or declared, the same scrubbed world without touching a guard.
    """
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(_git_env())
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def fixture_path(work, name):
    """`name`'s world under `work`, built once per `work`.

    KEYED BY `work` AS WELL AS NAME, found 2026-09-30 while regoldening #0c7d2263: `regolden.py guards` records each guard under its own `TemporaryDirectory`, deleted when that guard is done, and a cache keyed by name alone handed every later guard the FIRST guard's deleted path. `git -C <gone> branch --show-current` then printed nothing, and 64 `block_untagged_commit` and 20 `block_unverified_push` records were frozen against a checkout that no longer existed.
    """
    key = (str(work), name)
    if key not in _FIXTURES:
        target = pathlib.Path(work) / "fixtures" / name
        with _hermetic_process_env():
            _FIXTURES[key] = str(all_builders()[name](target))
    return _FIXTURES[key]


def _resolve_fixtures(value, work):
    out = value
    for name in all_builders():
        token = FIXTURE_TOKEN % name
        if token in out:
            out = out.replace(token, fixture_path(work, name))
    return out


def _fixture_gitconfig(stub_dir):
    """A global git config naming a fixed, synthetic identity, written once beside the stub directories.

    FOUND 2026-09-25 (#328aca77): `_base_env` passed the runner's real HOME, so git read `~/.gitconfig` and `block_unlinked_commit_author`'s golden froze `file:/home/developer/.gitconfig` and the operator's own address. 18 of its cases failed under another HOME, and a golden is no place for a personal email.
    """
    path = pathlib.Path(stub_dir).parent / "fixture-gitconfig"
    if not path.exists():
        path.write_text(
            "[user]\n\tname = Fixture\n\temail = 1+fixture@users.noreply.github.com\n",
            encoding="utf-8",
        )
    return str(path)


def _fixture_identity(stub_dir):
    """The `COMMIT_IDENTITY_FILE` `block_unlinked_commit_author` checks against, in the fixture's name.

    Without it the guard reads the tracked `.ci/config/commit-identity.json`, whose `Allowed (from ...)` list is the operator's real address and moves with every `--refresh`. The fixture's own noreply form (`<id>+<login>@users.noreply.github.com`) is what the gitconfig above uses, so a plain commit is still ALLOWED and the refusal arms are reached exactly as before.
    """
    path = pathlib.Path(stub_dir).parent / "fixture-commit-identity.json"
    if not path.exists():
        doc = {
            "format": 1,
            "identities": [{"login": "fixture", "id": 1, "emails": ["fixture@example.com"]}],
        }
        path.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    return str(path)


def _base_env(stub_dir, extra, work=None):
    """The environment BOTH sides run under, built rather than inherited.

    `PATH` keeps the real one behind the stub directory: these guards call `git`, `sed`, `awk` and `python3`, and an empty PATH would make every one of them fail identically on both sides -- agreement that proves nothing.
    """
    scratch = pathlib.Path(stub_dir).parent
    for sub in ("fixture-home", "fixture-tmp"):
        (scratch / sub).mkdir(exist_ok=True)
    env = {
        "PATH": "%s:%s" % (stub_dir, os.environ.get("PATH", "/usr/bin:/bin")),
        # An EMPTY home and temp dir the harness owns, not the runner's (#0c7d2263's sweep). `block_commit_meta`'s default variant expands `$HOME/...` body files off the real HOME, and `block_settled_questions` appends each refusal to `worklist.py --path`'s ledger under TMPDIR: run inherited, every differential pass wrote hundreds of `session: unknown` rows into this machine's live ask-refusal ledger.
        "HOME": str(scratch / "fixture-home"),
        "TMPDIR": str(scratch / "fixture-tmp"),
        "CLAUDE_PROJECT_DIR": str(ROOT),
        "LC_ALL": "C",
        "TZ": "UTC",
        # The host's git identity, like its clock, is not an input any case chose: no system config, and a global one that is the fixture's.
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": _fixture_gitconfig(stub_dir),
        "COMMIT_IDENTITY_FILE": _fixture_identity(stub_dir),
        # Deliberately NOT inherited. `test_shellscan_differential` records the same reasoning: a differential that depends on the caller's environment is one that passes for the wrong reason, and an inherited GIT_INDEX_FILE would reach every `git ls-files` in this chain.
    }
    env.update(extra)
    if work is not None:
        env = {k: _resolve_fixtures(v, work) for k, v in env.items()}
    return env


def environments(module):
    """`[(label, env_extra, stubs)]` for one port module.

    One variant by default. A module declares `ENVS` when its twin's behaviour genuinely forks on something outside the payload -- a `gh` that answers, an environment variable its own comments name -- and then both sides run every variant.
    """
    return getattr(module, "ENVS", None) or [("default", {}, {})]


# --------------------------------------------------------------------------- The frozen clock ---------------------------------------------------------------------------
#
# WHY THE HARNESS FREEZES THE WALL CLOCK, found 2026-09-25 (#34654813): `block_stale_pr_branch_date`'s golden, recorded on 0924, failed 31 cases the next day. The guard's message names today ("today is 0924") and the next free `MMDD-N`, and two of its EDGE_CASES build their `--head` from the clock at import, so the payload (and with it the case key) moved at midnight too.
#
# TOKENIZING THE DATE COULD NOT FIX IT, which is why this is a freeze and not a `<TODAY>` token. (1) The EXIT CODE moves with the hour, not just the day: under `tz-far-west` (UTC-12) the "UTC's today" head is allowed after 12:00 UTC and refused before it, under `tz-far-east` (UTC+14) the flip is at 10:00 UTC, and no text substitution turns a 2 into a 0. (2) The suggested rename is `<today>-<first N no live ref holds>`, read from the live checkout, so a real "today" is perturbed by every branch a session files that day. (3) A window
# substitution also rewrites literals that merely LOOK like today (`0825-2`, the checkout's own `0923-1`) on their own days.
#
# NOT A SEAM IN THE GUARD. The guard's source is untouched and reads no variable that could move its idea of today; the freeze is this process swapping the `datetime` module object a clock-reading guard module holds, for the duration of one in-process call, exactly as `python_fields` already swaps `os.environ`. Production runs the guard in its own process, which this cannot reach.
#
# THE INSTANT IS CHOSEN TO STRADDLE. 2024-02-29T13:00Z is 0229 in UTC and in `tz-far-west` (01:00) but 0301 in `tz-far-east` (03:00), so a port that went back to reading UTC instead of local time now answers "today is 0229" under `tz-far-east` on EVERY run, where before the differential could only see that on the hours the two clocks happened to disagree. A leap day, so the MMDD shared by two of the three zones can only collide with a live
# `0229-N` branch once in four years.
FROZEN_CLOCK = datetime.datetime(2024, 2, 29, 13, 0, tzinfo=datetime.UTC)

# The zone a clock-reading module's EDGE_CASES are EVALUATED in. `block_stale_pr_branch_date` builds one head from UTC's today and one from "the machine's LOCAL today"; the machine is whoever runs pytest, so on a UTC host (CI) the two collapse into one case and on a CEST host they part for two hours a night. Pinning the evaluation zone to UTC+14 makes the pair always distinct (0229-9 vs 0301-9), on every host, at every hour.
EDGE_CLOCK_TZ = "Etc/GMT-14"


class _FrozenDateTime(datetime.datetime):
    """`datetime.datetime` whose `now()` is `FROZEN_CLOCK`, rendered in the zone asked for.

    `now()` with no zone stays LOCAL and honours `TZ` through `fromtimestamp`, which is the property the guard's clock note turns on: a frozen clock that always answered in UTC would make the two-clock control blind again, the very defect that docstring records.
    """

    @classmethod
    def now(cls, tz=None):
        return datetime.datetime.fromtimestamp(FROZEN_CLOCK.timestamp(), tz)

    @classmethod
    def today(cls):
        return cls.now()


FROZEN_DATETIME = types.ModuleType("datetime")
FROZEN_DATETIME.__dict__.update(vars(datetime))
setattr(FROZEN_DATETIME, "datetime", _FrozenDateTime)  # noqa: B010 -- a ModuleType attribute mypy cannot see


def _reads_clock(module):
    return getattr(module, "datetime", None) is datetime


# Every guard module that holds the `datetime` module, decided once, BEFORE anything swaps it. A new clock-reading guard joins this set by importing `datetime` the way the existing two do; one that reads the clock another way (`time.time`, `date.today` via a `from` import) would escape the freeze and show up as a golden that breaks at midnight, the symptom that found this.
CLOCK_READERS = {stem for stem in guards.stems() if _reads_clock(guards.load(stem))}


@contextlib.contextmanager
def _pinned_tz(zone):
    saved = os.environ.get("TZ")
    os.environ["TZ"] = zone
    time.tzset()
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        time.tzset()


@contextlib.contextmanager
def frozen_clock(stem):
    """Point `stem`'s module at `FROZEN_DATETIME` for one call, if it reads the clock at all."""
    if stem not in CLOCK_READERS:
        yield
        return
    module = guards.load(stem)
    setattr(module, "datetime", FROZEN_DATETIME)  # noqa: B010 -- a guard module attribute mypy types as str
    try:
        yield
    finally:
        setattr(module, "datetime", datetime)  # noqa: B010 -- see the swap above


def _frozen_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
    if name == "datetime" and level == 0:
        return FROZEN_DATETIME
    return builtins.__import__(name, globals, locals, fromlist, level)


def edge_cases(module):
    """A module's EDGE_CASES, re-evaluated under the frozen clock when it reads one.

    `block_stale_pr_branch_date` computes two heads from `datetime.now()` AT IMPORT, so the imported list carries the real day and the real host's zone. Re-running the module body with `import datetime` resolved to the frozen module (and the zone pinned to `EDGE_CLOCK_TZ`) yields the same declarations evaluated at `FROZEN_CLOCK`, so a payload, and the case key hashed from it, is the same on every day and every host. Every other module's list is returned as imported.
    """
    stem = module.__name__.rsplit(".", 1)[-1]
    if stem not in CLOCK_READERS:
        return getattr(module, "EDGE_CASES", [])
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    namespace = {
        "__name__": "%s__frozen_clock" % module.__name__,
        "__file__": module.__file__,
        "__package__": module.__package__,
        "__builtins__": dict(vars(builtins), __import__=_frozen_import),
    }
    with _pinned_tz(EDGE_CLOCK_TZ):
        exec(compile(source, module.__file__, "exec"), namespace)  # noqa: S102
    return namespace.get("EDGE_CASES", [])


# --------------------------------------------------------------------------- Building the case list ---------------------------------------------------------------------------


# The event a chain's guards are handed, when a port's EDGE_CASES entry is a bare string. A module whose twin reads `file_path` or `tool_name` declares its
# case as a dict instead and gets exactly that document.
#
# THE FIRST CUT PUT THE BARE COMMAND ON STDIN, and the anti-vacuity control is what found it: every edge case became an unparseable payload, `jq` returned "" for all of them, and each one exercised only the guard's empty-command branch. It passed the differential (both sides agree on nonsense) while testing none of the shapes it named, which is the exact failure this file's controls exist for.
CHAIN_BUILDER = {
    "pre-bash": "bash_json",
    "post-bash": "bash_json",
    "pre-edit": "edit_json",
    "pre-ask": "ask_json",
}


def edge_payload(module, spec):
    if isinstance(spec, dict):
        return json.dumps(spec)
    builder = getattr(module, "EVENT_BUILDER", None) or CHAIN_BUILDER[module.CHAIN]
    return json.dumps(guardcorpus.BUILDERS[builder]([spec]))


def build_cases():
    """Every (guard, label, payload, env-variant) the differential will run.

    Only guards that have BEEN PORTED are included. That is not a way of excusing the rest: a port that does not exist has no golden to compare against, and `test_every_ported_guard_is_registered` is what stops a module being written and then quietly left out of this list.

    ONE LIST FOR EVERY GUARD, golden-backed or not (PLAN-retire-bash-oracles A3). Before A3 this split into `CASES`/`NATIVE_CASES`, because the bash driver wrote one case file per list element and read `bash_results["records"][i]` back by POSITION, so a guard with no oracle anywhere in the list would have shifted every later index. Golden lookups are keyed by CONTENT hash
    (`golden_case_key`), never by position, so that constraint is gone with the driver that needed it. An `OWN_SUITE` guard is still built and cross-fed exactly like every other one -- that is what lets `test_every_guard_discriminates` and `test_the_differential_can_fail` say something about it too -- it simply never appears in `GOLDEN_CASES`, because it has no golden to be compared
    against.
    """
    harvested, stats = guardcorpus.harvest_cases()
    pool = sorted({payload for _, payload, _, _ in harvested})
    own = {}
    for guard, payload, label, suite_rc in harvested:
        own.setdefault(guard, []).append((label, payload, suite_rc))

    cases = []
    for stem in guards.stems():
        module = guards.load(stem)
        # THE SUITE'S KEY, which since the P7 cutover is the MODULE: a case reads `check 2 guards/block_x.py`, because that is the key `check-hook-integrity.sh` inventories the live guard under and one spelling has to drive the suite, the coverage gate and this corpus.
        key = "guards/%s.py" % stem
        named = own.get(key, [])
        seen = set()
        picked = []
        for label, payload, _ in named:
            if payload not in seen:
                seen.add(payload)
                picked.append(("suite-%s" % label, payload))
        for label, spec in edge_cases(module):
            payload = edge_payload(module, spec)
            if payload not in seen:
                seen.add(payload)
                picked.append(("edge-%s" % label, payload))
        for label, payload in guardcorpus.DEGENERATE_PAYLOADS:
            if payload not in seen:
                seen.add(payload)
                picked.append(("degen-%s" % label, payload))
        # `foreign_pool` in BOTH modes: a host path fed to a guard it was not written for makes that guard's golden answer this machine's `/tmp` (#0c7d2263).
        foreign = guardcorpus.foreign_pool(pool) if FULL else guardcorpus.cross_sample(pool, key)
        for payload in foreign:
            if payload not in seen:
                seen.add(payload)
                # CONTENT-HASHED, NOT POSITIONAL. `foreign` is the full 378-payload pool under REDIACC_GUARD_DIFF_FULL=1 and a 40-payload per-guard sample otherwise, so the SAME payload lands at a different index in the two modes. A golden recorded from the full sweep (A1's freeze always runs full) and read back by an ordinary default-mode run has to find this case by what it IS, not by which position it happened to occupy the day it was recorded -- see goldenio's module docstring.
                picked.append(("cross-%s" % goldenio.content_hash(payload), payload))
        for env_label, extra, stubs in environments(module):
            for label, payload in picked:
                cases.append((stem, "%s|%s" % (env_label, label), payload, env_label, extra, stubs))
    return cases, stats, pool


CASES, HARVEST_STATS, POOL = build_cases()


# --------------------------------------------------------------------------- The two sides ---------------------------------------------------------------------------

# THE PROCESS-TABLE READERS, AND WHY ONLY THEIR CASES ARE GROUPED. Three guards read the REAL process table, and `test_hooks_procs.py` spawns real processes visible to that same table to prove its own guards' hazards. Measured 2026-09-09: run on two different xdist workers at once, this file's anti-vacuity controls went red for reasons that had nothing to do with either port -- a `sleep 8` fixture from one file was visible, at the wrong
# moment, to a case built by the other -- and on 2026-09-30 two workers each built the fixed-path running-script world and the second killed the first's shells (#af1d1d05).
#
# THIS FILE NO LONGER DECLARES A GROUP (agent/plans/PLAN-prepush-full-cpu.md PF11, 2026-10-05). The repo-root conftest groups whole MODULES, so the old module-level `XDIST_GROUP = "hooks-guards"` pinned every one of this file's roughly 6,900 items (461 s of test time) to one worker, which was check:ci-pytest's floor at any core count. The cases that actually need the group -- these three guards' golden cases, their two anti-vacuity controls, and the dead-world control -- moved to `test_guards_process_table.py`, which declares `XDIST_GROUP = "hooks-guards"` beside `test_hooks_procs.py`'s marked cases. Everything left here distributes per item. `SPREAD_STEMS` below and that file's `READER_STEMS` partition `guards.stems()`, and its `test_the_partition_covers_every_guard` proves it.
PROCESS_TABLE_READERS = {
    "block_self_matching_pgrep",
    "block_bash_write_to_running_script",
    "block_edit_of_running_script",
}

# Every other guard: their cases read no process table, so they distribute freely.
SPREAD_STEMS = [stem for stem in guards.stems() if stem not in PROCESS_TABLE_READERS]


def python_fields(stem, payload, extra, stubs, work, cwd=None):
    """One case's answer from the live port, exactly as the harness observes it.

    `os.environ` is swapped for the case environment rather than passed down, because a ported guard that shells out to `git` or `gh` inherits the process environment. Passing an `env` only to `dispatch` would leave those children reading the test runner's own environment instead of the case's.

    `time.tzset()` IS NOT DECORATION, and it is the one piece of libc state that an in-process call does not get from swapping a dict. `TZ` is read by libc once and cached, so `datetime.now()` here would keep answering in the test runner's own zone however the case set the variable. Measured 2026-09-07: without this call, `block_stale_pr_branch_date` reported the port as
    diverging under a pinned `TZ=UTC` when the port was right and the HARNESS was
    the thing ignoring the variable. Restoring the runner's own zone afterwards matters for the same reason.

    `cwd` overrides the guard's world for a test that pins one arm in a world no golden case runs in (the detached checkout below).
    """
    env = case_env(stem, extra, stubs, work)
    cwd = cwd or case_cwd(stem, work)
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    time.tzset()
    try:
        with frozen_clock(stem), host_world(stem, work):
            rc, out, err = dispatch.run_one(stem, rehome(payload), cwd=cwd, env=env)
    finally:
        os.environ.clear()
        os.environ.update(saved)
        time.tzset()
    return {"rc": str(rc), "out": out, "err": err}


def diff_fields(want, got):
    diffs = []
    for key in ("rc", "out", "err"):
        want_val = want.get(key, "<missing from golden>")
        got_val = got.get(key, "<missing from port>")
        if got_val != want_val:
            diffs.append((key, want_val, got_val))
    return diffs


def render(diffs, stem, label, payload):
    lines = ["%s diverged on %s for payload %r" % (stem, label, payload)]
    for key, want, got in diffs:
        lines.append("  field %s" % key)
        lines.append("    golden %r" % want)
        lines.append("    python %r" % got)
    return "\n".join(lines)


# --------------------------------------------------------------------------- The corpus, before anything is compared against it ---------------------------------------------------------------------------


def test_corpus_is_real_and_large_enough():
    assert HARVEST_STATS["recovered"] >= guardcorpus.MIN_CASES, (
        "only %d suite cases recovered from %s; below %d the differential is proving "
        "the ports against a handful of strings"
        % (HARVEST_STATS["recovered"], HARVEST_STATS["source"], guardcorpus.MIN_CASES)
    )
    ratio = HARVEST_STATS["recovered"] / HARVEST_STATS["call_sites"]
    assert ratio >= guardcorpus.RECOVERY_FLOOR, (
        "recovered %d of %d check call sites (%.3f); the payload parser has stopped "
        "understanding the suite" % (HARVEST_STATS["recovered"], HARVEST_STATS["call_sites"], ratio)
    )


def test_builders_match_the_suite():
    """The transcribed event shapes are still the suite's own.

    If a builder changes and the table does not, every payload for that builder is silently the wrong shape, BOTH sides get it, and this file goes on passing while testing something else.
    """
    drift = guardcorpus.builder_shape_drift()
    assert not drift, "suite payload builders no longer match the corpus table: %r" % (drift,)


def test_every_ported_guard_is_registered():
    """A module in `guards/` that this file does not exercise is invisible.

    Same failure the driver contract names for a gate the binder cannot see: "it is invisible, which is worse than unregistered, because nothing reports the absence".
    """
    exercised = {stem for stem, _, _, _, _, _ in CASES}
    missing = sorted(set(guards.stems()) - exercised)
    assert not missing, "these guard modules exist but no case runs them: %s" % missing


def test_this_worktree_cases_run_against_a_snapshot():
    """No case may be judged against the LIVE checkout, however real that looks.

    The `this-worktree` label means a real repository shape, and for four guards it meant the running session's own tree until a concurrent commit was shown to split one comparison into two experiments.
    Restoring `("this-worktree", {}, {})` would restore that silently: the case would keep passing whenever nothing else committed, which is most runs and none of the ones that matter. This names the one property that has to hold instead of trusting the comment that says so.
    """
    live = []
    for stem, label, _, env_label, extra, _ in CASES:
        if env_label != "this-worktree":
            continue
        if extra.get("CLAUDE_PROJECT_DIR", str(ROOT)) == str(ROOT):
            live.append("%s|%s" % (stem, label))
    assert not live, (
        "these cases point CLAUDE_PROJECT_DIR at the live checkout, so a commit landing "
        "mid-run is reported as a port defect: %s" % sorted({c.split("|")[0] for c in live})
    )


def test_every_port_has_goldens():
    """A golden-backed guard's golden file must exist. An `OWN_SUITE` one must have a suite.

    THE SECOND HALF IS THE POINT, and it is what stops `OWN_SUITE = True` becoming the cheap way out of this whole file. A guard with no golden is not judged against less evidence, it is judged against DIFFERENT evidence: a dedicated `test-<stem>.py` beside it, which `check-hook-integrity.sh` already treats as covering both directions. Without this arm, adding the sentinel to
    an ordinary guard would silently remove it from the differential AND from every other control, and the suite would go green faster than before.
    """
    for stem in guards.stems():
        module = guards.load(stem)
        if guards.has_own_suite(module):
            suite = pathlib.Path(module.__file__).with_name("test-%s.py" % stem)
            assert suite.is_file(), (
                "%s declares OWN_SUITE = True, so it has no golden. That is admitted -- see "
                "guards.has_own_suite -- but only in exchange for a dedicated suite at %s, "
                "which does not exist. A guard with neither a golden nor its own suite has no "
                "evidence at all." % (stem, suite.relative_to(ROOT))
            )
            continue
        golden = goldenio.golden_path(stem)
        assert golden.is_file(), (
            "%s has no golden at %s. Run "
            "`.claude/rediacc_hooks/tests/regolden.py %s --reason '<why>'` to freeze one "
            "before this guard's differential can run at all."
            % (stem, golden.relative_to(ROOT), stem)
        )


# --------------------------------------------------------------------------- The differential ---------------------------------------------------------------------------

_GOLDEN_CACHE: dict[str, tuple] = {}


def golden_for(stem):
    if stem not in _GOLDEN_CACHE:
        _GOLDEN_CACHE[stem] = goldenio.read_golden(goldenio.golden_path(stem))
    return _GOLDEN_CACHE[stem]


def golden_case_key(label, payload, extra, stubs):
    """The exact key `regolden.py` writes under, given one case's own inputs.

    Built from the case's own `label`/`payload`/`extra`/`stubs` -- the fourth and fifth elements of a `CASES` row, captured before `_resolve_fixtures` ever substitutes a real path in, never from the ephemeral tmp root a given pytest session happens to build fixtures under. That is what makes the key reproducible across sessions and across the full/default cross-feed split; see `goldenio`'s module docstring and the `cross-<hash>` relabelling in `build_cases` above.
    """
    return goldenio.case_key(
        label, payload, json.dumps(extra, sort_keys=True), json.dumps(stubs, sort_keys=True)
    )


@pytest.fixture(scope="session")
def fixture_work(tmp_path_factory):
    """A tmp root for `FIXTURE_BUILDERS` (git-ahead, this-worktree-snapshot, ...).

    Every control in this file that needs a real git world (a `git-ahead` case, the synthetic `this-worktree` checkout) shares this one session-scoped directory, so each world is built once per pytest session rather than once per case.

    ONCE PER WORKER, NOT ONCE PER RUN, ON A MEASUREMENT (agent/plans/PLAN-prepush-full-cpu.md PF12, 2026-10-05). The plan proposed building the worlds once per run behind a lock and sharing them read-only across xdist workers, on the hypothesis that no case writes into them. Its read-only control refuted that: with every world built and then `chmod -R a-w`, 45 of 6,862 golden cases failed, every one of them `warn_remote_drift` in its `behind` world, because that guard runs a real `git fetch` into its fixture (FETCH_HEAD, new objects, a moved `refs/remotes/origin/*`). Shared worlds would race those fetches between workers. And the saving is small: all 45 worlds build in 1.4 s and hold about 2,600 inodes per worker, so per-worker worlds stay.
    """
    return tmp_path_factory.mktemp("guard-golden-fixtures")


# A GOLDEN CANNOT FREEZE A FIXTURE THAT SPAWNS A REAL PROCESS. `block_bash_write_to_running_script`'s and `block_edit_of_running_script`'s "running" `ENVS` variant launches two real `bash <script>` processes and quotes ONE'S LIVE PID in the refusal message (each guard's own docstring: "the pids in the message are identical because it is literally the same process"). That PID is
# minted fresh by every session that runs this file, so a golden frozen from one session's PIDs can never match a later session's. FOUND LIVE by A1's freeze: recording PLANTED a real PID into the golden and every later `test_guard_matches_golden` run then diverged on it, which is not a port defect -- `test_hooks_procs.py`'s dedicated `test_block_bash_write_to_running_script`
# and `test_block_edit_of_running_script` still prove these two guards correct, live, every run, against real spawned processes. Excluded from golden-mode coverage rather than worked around with a fabricated PID or a `pytest.skip` (which `check:ci-pytest` refuses): this is a golden-mode-only gap, not a coverage gap.
GOLDEN_UNSTABLE_ENVS = {
    ("block_bash_write_to_running_script", "running"),
    ("block_edit_of_running_script", "running"),
}

# AN OWN_SUITE GUARD HAS NO GOLDEN TO COMPARE AGAINST, ever -- it was never bash, so there is nothing to have frozen. Filtered here rather than left out of `build_cases` in the first place, so the SAME cases still feed `test_every_guard_discriminates` and `test_the_differential_can_fail` (see `build_cases`'s docstring).
_OWN_SUITE_STEMS = {stem for stem in guards.stems() if guards.has_own_suite(guards.load(stem))}

GOLDEN_CASES = [
    c for c in CASES if c[0] not in _OWN_SUITE_STEMS and (c[0], c[3]) not in GOLDEN_UNSTABLE_ENVS
]


def test_golden_unstable_envs_are_still_real():
    """A stale exclusion here would silently stop freezing cases that could be frozen fine."""
    present = {(stem, env_label) for stem, _, _, env_label, _, _ in CASES}
    stale = GOLDEN_UNSTABLE_ENVS - present
    assert not stale, (
        "these golden-mode exclusions no longer match any case in CASES, so they are stale "
        "and should be removed: %s" % sorted(stale)
    )


def test_goldens_name_no_host():
    """No golden may carry this checkout's path or the runner's own git identity.

    Either one makes the golden true only on the machine that recorded it (#328aca77): the checkout root is what `goldenio.normalize` turns into `<REPO>`, and the identity is what the fixture gitconfig in `_base_env` replaces. A regolden run without either would plant it straight back, and this is what says so on the recording machine itself, before a second checkout ever has to.
    """
    real_email = subprocess.run(
        ["git", "config", "--global", "user.email"], capture_output=True, text=True, check=False
    ).stdout.strip()
    tracked = json.loads((ROOT / ".ci/config/commit-identity.json").read_text(encoding="utf-8"))
    needles = [str(ROOT), real_email]
    needles += [e for entry in tracked.get("identities", []) for e in entry.get("emails", [])]
    leaks = {}
    for path in sorted(goldenio.GOLDEN_DIR.glob("*.jsonl")):
        text = path.read_text(encoding="utf-8")
        found = [needle for needle in needles if needle and needle in text]
        if found:
            leaks[path.name] = found
    assert not leaks, "these goldens froze a fact about this host: %s" % leaks


def test_host_worlds_reach_the_guard(fixture_work):
    """The branch guard reads the fixture checkout and the toolchain guard reads the fixture root, never this one."""
    stale = guards.load("block_stale_pr_branch_date")
    err = python_fields(
        "block_stale_pr_branch_date",
        edge_payload(stale, "gh pr create --draft --fill"),
        {},
        {},
        fixture_work,
    )["err"]
    assert "branch '0825-7'" in err, err
    assert '"0825-7" "0229-3"' in err, err
    tool = guards.load("block_host_toolchain_run")
    err = python_fields(
        "block_host_toolchain_run",
        edge_payload(tool, "shfmt -w private/growth/video_pipeline/run.sh"),
        {},
        {"docker": "#!/bin/sh\nexit 0\n"},
        fixture_work,
    )["err"]
    assert "'private/growth/video_pipeline'" in err, err
    assert tool.hookio is hookio


def test_host_path_payloads_never_cross_feed():
    """A payload naming `/tmp`, `/home` or `$HOME` reaches only the guard its suite case was written for (#0c7d2263).

    The CONTROL is a planted pair: the exact payload that made `block_untagged_commit`'s golden answer this machine's `/tmp/commit-msg.txt` must be dropped, and an ordinary commit beside it kept, or the filter is either absent or dropping everything.
    """
    bash = guardcorpus.BUILDERS["bash_json"]
    planted = json.dumps(bash(["git commit -F /tmp/commit-msg.txt"]))
    ordinary = json.dumps(bash(["git commit -F msg.txt -- a"]))
    assert guardcorpus.cross_sample([planted, ordinary], "guards/x.py", limit=10) == [ordinary]
    assert guardcorpus.foreign_pool([planted, ordinary]) == [ordinary]
    for spelling in ("cat ~/x", "cp $HOME/a b", "cp ${HOME}/a b", "cd /tmp && ls", "ls /home/u"):
        assert guardcorpus.names_host_path(spelling), spelling
    for spelling in ("scp f host:/tmp", "ls packages/www/tmp/x", "cat /dev/null", "ls private/tmp"):
        assert not guardcorpus.names_host_path(spelling), spelling
    # The real pool carries the planted payload, so the filter is not vacuous over the corpus either, and no guard's foreign cases hold one.
    assert planted in POOL
    leaked = sorted(
        {
            stem
            for stem, label, payload, *_ in CASES
            if "|cross-" in label and guardcorpus.names_host_path(payload)
        }
    )
    assert not leaked, "these guards were cross-fed a host path: %s" % leaked


def test_the_case_environment_names_no_host(fixture_work):
    """HOME and TMPDIR are the harness's own, and no inherited `GIT_*` variable reaches a world builder."""
    env = case_env("block_commit_meta", {}, {}, fixture_work)
    for key in ("HOME", "TMPDIR"):
        assert env[key].startswith(str(fixture_work)), (key, env[key])
    saved = dict(os.environ)
    os.environ["GIT_DIR"] = "/nonexistent-host-repo/.git"
    try:
        with _hermetic_process_env():
            assert "GIT_DIR" not in os.environ
            assert os.environ["HOME"] == NO_HOME
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_the_frozen_clock_reaches_the_guard_and_straddles(fixture_work):
    """The freeze is real, honours TZ, and makes the two clocks disagree on every run.

    Three things that could each be quietly false: `CLOCK_READERS` could miss the guard (the golden would go back to breaking at midnight), the frozen `now()` could answer in UTC regardless of TZ (the two-clock control would be blind again, see the guard's clock note), and the re-evaluated EDGE_CASES could still carry the real day (the case keys would move at midnight).
    """
    stem = "block_stale_pr_branch_date"
    assert stem in CLOCK_READERS
    module = guards.load(stem)
    heads = [spec for _, spec in edge_cases(module) if "-9 --fill" in spec]
    assert heads == [
        "gh pr create --draft --head 0229-9 --fill",
        "gh pr create --draft --head 0301-9 --fill",
    ], heads
    payload = edge_payload(module, "gh pr create --draft --head 0825-2 --fill")
    zones = {label: extra for label, extra, _ in environments(module)}
    west = python_fields(stem, payload, zones["tz-far-west"], {}, fixture_work)["err"]
    east = python_fields(stem, payload, zones["tz-far-east"], {}, fixture_work)["err"]
    utc = python_fields(stem, payload, zones["default"], {}, fixture_work)["err"]
    assert "today is 0229." in utc
    assert "today is 0229." in west
    assert "today is 0301." in east
    # And the swap is undone: the imported module is back on the real clock.
    assert module.datetime is datetime


@pytest.mark.parametrize(
    ("stem", "label", "payload", "extra", "stubs"),
    [
        pytest.param(
            c[0],
            c[1],
            c[2],
            c[4],
            c[5],
            id="%s|%s" % (c[0], c[1]),
        )
        for c in GOLDEN_CASES
        if c[0] not in PROCESS_TABLE_READERS
    ],
)
def test_guard_matches_golden(fixture_work, stem, label, payload, extra, stubs):
    """One case against its frozen golden. The process-table readers' cases run the same assertion in `test_guards_process_table.py`."""
    assert_matches_golden(fixture_work, stem, label, payload, extra, stubs)


def assert_matches_golden(fixture_work, stem, label, payload, extra, stubs):
    """The golden comparison, shared with `test_guards_process_table.py` so both halves assert the identical thing."""
    header, silent, records = golden_for(stem)
    assert header is not None, (
        "%s has no golden recorded -- run regolden.py %s --reason '<why>'" % (stem, stem)
    )
    key = golden_case_key(label, payload, extra, stubs)
    want = goldenio.lookup(silent, records, key)
    assert want is not None, (
        "%s's golden has no record for %r (key %s) -- the corpus moved since the last "
        "regolden; run regolden.py %s --reason '<why>'" % (stem, label, key, stem)
    )
    fields = python_fields(stem, payload, extra, stubs, fixture_work)
    got = {
        "rc": fields["rc"],
        "out": goldenio.normalize(fields["out"], fixture_work),
        "err": goldenio.normalize(fields["err"], fixture_work),
    }
    decoded = {
        "rc": want["rc"],
        "out": goldenio.decode_field(want.get("out", "")),
        "err": goldenio.decode_field(want.get("err", "")),
    }
    diffs = diff_fields(decoded, got)
    assert not diffs, render(diffs, stem, label, payload)


# --------------------------------------------------------------------------- The ambient checkout ---------------------------------------------------------------------------
#
# A GOLDEN THAT DEPENDS ON THE RUNNER'S OWN CHECKOUT PASSES WHERE IT WAS RECORDED AND NOWHERE ELSE (#6f901a98). `block_premature_ready` read `git -C . branch --show-current`, and `.` is whatever directory pytest runs in: a branch on every developer machine, a DETACHED merge commit under `actions/checkout` of a pull_request. Six records were green locally and red in CI only (run 37649744806), which is the one place a red cannot be reproduced from.
#
# So every guard whose source reads a branch (the regex below, over-inclusive on purpose: a payload mentioning `--show-current` also qualifies, which only costs time) has its whole golden replayed from inside two synthetic checkouts: detached (CI's shape) and on `main` (the branch name guards treat specially). A green here means the answer does not depend on where pytest stands. Red at fad446748, the commit that made the guard refuse an empty selector: the detached replay diverges on exactly the six CI cases.
AMBIENT_CHECKOUTS = ("console-pr-detached", "ambient-on-main")
FIXTURE_BUILDERS["ambient-on-main"] = lambda p: _console_checkout(p, detached=False, branch="main")
BRANCH_READ = re.compile(r"show-current|symbolic-ref|abbrev-ref|current_branch\(")
BRANCH_READERS = sorted(
    stem
    for stem in SPREAD_STEMS
    if stem not in _OWN_SUITE_STEMS
    and BRANCH_READ.search(pathlib.Path(guards.load(stem).__file__).read_text(encoding="utf-8"))
)


def test_the_branch_readers_are_seen():
    """The regex finds the guard that went red in CI, and more than it: an empty or one-guard list would make the replay below a control that cannot fail."""
    assert "block_premature_ready" in BRANCH_READERS, BRANCH_READERS
    assert len(BRANCH_READERS) >= 5, BRANCH_READERS


@pytest.mark.parametrize("ambient", AMBIENT_CHECKOUTS)
@pytest.mark.parametrize("stem", BRANCH_READERS)
def test_goldens_ignore_the_ambient_checkout(monkeypatch, fixture_work, stem, ambient):
    """Every golden case of a branch-reading guard, replayed from inside a detached and an on-`main` checkout."""
    where = fixture_path(fixture_work, ambient)
    head = subprocess.run(
        ["git", "-C", where, "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
        env=_git_env(),
    ).stdout.strip()
    # The control's own control: a "detached" world that is on a branch would make this replay a second copy of the ordinary one.
    assert head == ("" if ambient == "console-pr-detached" else "main"), (ambient, head)
    cases = [c for c in GOLDEN_CASES if c[0] == stem]
    assert cases, "%s has no golden case to replay" % stem
    monkeypatch.chdir(where)
    diverged = []
    for _, label, payload, _, extra, stubs in cases:
        try:
            assert_matches_golden(fixture_work, stem, label, payload, extra, stubs)
        except AssertionError as exc:
            diverged.append(str(exc).splitlines()[0])
    assert not diverged, (
        "%d of %d %s golden cases change answer when pytest runs inside a %s checkout, so the "
        "golden is true only where it was recorded. Hand the guard a fixture world "
        "(CWD_WORLDS, or a CLAUDE_PROJECT_DIR token in its ENVS) instead of the process's "
        "directory:\n  %s" % (len(diverged), len(cases), stem, ambient, "\n  ".join(diverged))
    )


def test_a_selectorless_flip_on_a_detached_head_is_refused(fixture_work):
    """`gh pr ready` with no selector on a detached HEAD is refused before any `gh` call; a named PR or a branch is verified as usual.

    The refusal is right: gh itself cannot resolve a PR there ("could not determine current branch: failed to run git: not on any branch", rc=1, gh 2.98.0), so the flip can never happen and refusing costs nothing. The `gh` stub answers SUCCESS throughout, so a refusal can only come from the detached arm.
    """
    stem = "block_premature_ready"
    module = guards.load(stem)
    green = {"gh": "#!/bin/sh\necho SUCCESS\n"}
    detached = fixture_path(fixture_work, "console-pr-detached")
    bare = edge_payload(module, "gh pr ready")
    got = python_fields(stem, bare, {}, green, fixture_work, cwd=detached)
    assert got["rc"] == "2", got
    assert "(no PR named and no current branch)" in got["err"], got
    # The production shape: the Bash tool's payload carries its own `cwd`, which wins over the dispatcher's.
    carried = json.dumps(dict(json.loads(bare), cwd=detached))
    got = python_fields(stem, carried, {}, green, fixture_work)
    assert got["rc"] == "2", got
    assert "(no PR named and no current branch)" in got["err"], got
    # Controls: the same flip on a branch, and a named PR on the detached head, both reach gh and pass.
    assert python_fields(stem, bare, {}, green, fixture_work)["rc"] == "0"
    named = edge_payload(module, "gh pr ready 42")
    assert python_fields(stem, named, {}, green, fixture_work, cwd=detached)["rc"] == "0"


@pytest.mark.parametrize("stem", SPREAD_STEMS)
def test_every_guard_discriminates(fixture_work, stem):
    """No guard may answer the same way on every case it was given (one item per guard; the process-table readers' items are in `test_guards_process_table.py`).

    A guard that returns 0 on all of its inputs has been compared against a constant, which is the failure `test_shellscan_differential` found in its own field set: "the target_root field evaluated against an absent root was empty on all 385 cases -- a comparison that could not have failed".

    Exit code alone is not the test, because the four `warn-*` guards exit 0 by design and speak on stderr. The predicate is that SOMETHING varies. Runs every guard's own Python answer, golden-backed or `OWN_SUITE`: before PLAN-retire-bash-oracles A3 this read the bash driver's records for the golden-backed half and called `python_fields` directly for the rest, a split that
    existed only because the bash driver read `bash_results["records"][i]` back by POSITION (see `build_cases`'s docstring). There is no driver left to disagree with, so one pass over `CASES` covers every guard the same way.
    """
    assert_discriminates(fixture_work, stem)


def assert_discriminates(fixture_work, stem):
    """`stem` answers differently on at least two of its cases.

    PER GUARD SINCE 2026-10-05 (PF11): this was one loop over every guard's cases, 188 s as a single item. A guard's verdict depends only on its own cases, so one item per guard asks the same question and lets the items spread across workers.
    """
    seen = set()
    for cstem, _, payload, _, extra, stubs in CASES:
        if cstem != stem:
            continue
        fields = python_fields(stem, payload, extra, stubs, fixture_work)
        seen.add((fields["rc"], fields["out"], fields["err"]))
    assert len(seen) >= 2, (
        "%s answered identically on every case, so comparing it proves nothing" % stem
    )


@pytest.mark.parametrize("stem", SPREAD_STEMS)
def test_the_differential_can_fail(tmp_path, fixture_work, stem):
    """Every port declares one defect, and the comparison must catch it (one item per guard; the process-table readers' items are in `test_guards_process_table.py`).

    A differential that has never failed is not evidence. This plants each port's own declared defect -- a single source substitution naming the line its twin's comments say cost the most -- and requires the ported guard to answer differently on at least one case it was given.
    """
    assert_defect_is_caught(tmp_path, fixture_work, stem)


def _outside_defect(src: str, *names: str) -> str:
    """`src` with every top-level `DEFECT` (or named) assignment removed, so a needle search cannot be satisfied by the declaration that names it.

    `old in src` alone stays true after the guarded line is deleted, because the declaration itself contains the text it plants (measured 2026-10-05).
    """
    import ast  # noqa: PLC0415 -- only the planted-defect controls need it

    wanted = names or ("DEFECT",)
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


def assert_defect_is_caught(tmp_path, fixture_work, stem):
    """`stem`'s declared DEFECT changes its answer on at least one of its cases. Per guard since 2026-10-05 (PF11), for the reason `assert_discriminates` gives."""
    work = fixture_work
    # THIS CONTROL COMPARES THE PORT AGAINST ITSELF-WITH-A-BUG and never needed
    # a golden or a bash process, which is what makes it work identically for an `OWN_SUITE` guard -- and an `OWN_SUITE` guard needs it MORE, being the one with no golden.
    all_cases = CASES
    module = guards.load(stem)
    defect = getattr(module, "DEFECT", None)
    assert defect, "%s declares no DEFECT, so nothing proves its differential can fail" % stem
    old, new = defect
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    assert old in _outside_defect(source), (
        "%s's declared DEFECT no longer applies to the port outside its own declaration: %r"
        % (stem, old)
    )
    broken_src = source.replace(old, new)
    assert broken_src != source
    broken_path = tmp_path / ("broken_%s.py" % stem)
    broken_path.write_text(broken_src, encoding="utf-8")
    namespace: dict[str, typing.Any] = {
        "__name__": "broken_%s" % stem,
        "__file__": str(broken_path),
    }
    exec(compile(broken_src, str(broken_path), "exec"), namespace)  # noqa: S102
    # The broken copy reads the SAME frozen clock as the good one, or a clock-reading port would "change its answer" on today's date rather than on its planted defect, and this control would pass for the wrong reason.
    if stem in CLOCK_READERS:
        namespace["datetime"] = FROZEN_DATETIME
    # And the SAME host world, for the same reason: a defect judged against this machine's PATH and tree would be judged against a different world from the good side's.
    shim = host_hookio(stem, work)
    if shim is not None:
        namespace["hookio"] = shim
    broken_run = namespace["run"]
    changed = False
    for cstem, _, payload, _, extra, stubs in all_cases:
        if cstem != stem:
            continue
        good = python_fields(stem, payload, extra, stubs, work)
        env = case_env(stem, extra, stubs, work)
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        # `python_fields` re-reads TZ for the good side; without the same call here the broken side answered in the RUNNER's zone, so under a `tz-far-*` variant the two differed on the clock alone and the planted defect was never what this control saw.
        time.tzset()
        try:
            event = hookio.Event(rehome(payload), cwd=case_cwd(stem, work), env=env)
            rc = broken_run(event)
            bad = dict(zip(("rc", "out", "err"), event.result(rc), strict=True))
            bad["rc"] = str(bad["rc"])
        finally:
            os.environ.clear()
            os.environ.update(saved)
            time.tzset()
        if bad != good:
            changed = True
            break
    assert changed, (
        "%s answered identically with its declared defect planted, so this "
        "file's green does not depend on that branch being right" % stem
    )
