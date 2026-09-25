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
import subprocess
import time
import types
import typing

import pytest

from rediacc_hooks import dispatch, guards, hookio
from rediacc_hooks.tests import goldenio, guardcorpus

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


def _git_env():
    return dict(
        os.environ,
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
CWD_WORLDS = {"block_stale_pr_branch_date": "stale-branch-checkout"}
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


# The two host worlds, registered beside every other named fixture so `fixture_path` builds each once per session.
FIXTURE_BUILDERS["stale-branch-checkout"] = _stale_branch_checkout
FIXTURE_BUILDERS["toolchain-host"] = _toolchain_host


# THE ROOT A PAYLOAD SPELLS LITERALLY. `block_agent_browser_repo_output`'s "an absolute path inside the repo" case writes `/home/developer/console/x.png` into its EDGE_CASES, which means "inside the repo" only in a checkout at that path; from any other checkout the guard answers "outside" and the case silently tests the opposite arm. The payload is re-homed onto THIS checkout just before the guard reads it, while the case key (`golden_case_key`) is still hashed from the payload as written, so the key is the same everywhere and `goldenio.normalize` turns the answer back into `<REPO>`. On the recording checkout it is the identity.
LITERAL_ROOT = "/home/developer/console"


def rehome(payload):
    """`payload` with `LITERAL_ROOT` pointed at the checkout actually running."""
    return payload.replace(LITERAL_ROOT, str(ROOT))


def case_cwd(stem, work):
    """The directory a case runs in: the guard's synthetic checkout, or this one."""
    name = CWD_WORLDS.get(stem)
    return fixture_path(work, name) if name else str(ROOT)


def case_env(stem, extra, stubs, work):
    """`_base_env` for one case, with a `HOST_WORLDS` guard's PATH cut down to stubs + its fixture `bin/`."""
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


def fixture_path(work, name):
    if name not in _FIXTURES:
        target = pathlib.Path(work) / "fixtures" / name
        _FIXTURES[name] = str(all_builders()[name](target))
    return _FIXTURES[name]


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
    env = {
        "PATH": "%s:%s" % (stub_dir, os.environ.get("PATH", "/usr/bin:/bin")),
        "HOME": os.environ.get("HOME", "/"),
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
        foreign = pool if FULL else guardcorpus.cross_sample(pool, key)
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

# STILL SHARED WITH `test_hooks_procs.py`, and that is the whole reason this survives PLAN-retire-bash-oracles A3. Before A3 the comment here was about the bash driver's own cost (forking `env -i bash` once per case across roughly 6,000 cases); that reasoning left with the driver. What did NOT leave is that two of these guards (`block_self_matching_pgrep`,
# `block_bash_write_to_running_script`) read the REAL process table, and `test_hooks_procs.py` spawns real processes visible to that same table to prove its own guards' hazards. Measured 2026-09-09: run on two different xdist workers at once, this file's anti-vacuity controls went red for reasons that had nothing to do with either port -- a `sleep 8` fixture from one file was
# visible, at the wrong moment, to a case built by the other. Sharing this group serialises the two files onto one worker, which is what stops that. It is INERT without `--dist loadgroup`, so it changes nothing today; `test_hooks_procs.py` imports the name directly rather than each file hand-typing the same string.
XDIST_GROUP = "hooks-guards"


def python_fields(stem, payload, extra, stubs, work):
    """One case's answer from the live port, exactly as the harness observes it.

    `os.environ` is swapped for the case environment rather than passed down, because a ported guard that shells out to `git` or `gh` inherits the process environment. Passing an `env` only to `dispatch` would leave those children reading the test runner's own environment instead of the case's.

    `time.tzset()` IS NOT DECORATION, and it is the one piece of libc state that an in-process call does not get from swapping a dict. `TZ` is read by libc once and cached, so `datetime.now()` here would keep answering in the test runner's own zone however the case set the variable. Measured 2026-09-07: without this call, `block_stale_pr_branch_date` reported the port as
    diverging under a pinned `TZ=UTC` when the port was right and the HARNESS was
    the thing ignoring the variable. Restoring the runner's own zone afterwards matters for the same reason.
    """
    env = case_env(stem, extra, stubs, work)
    cwd = case_cwd(stem, work)
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
    [(c[0], c[1], c[2], c[4], c[5]) for c in GOLDEN_CASES],
    ids=["%s|%s" % (c[0], c[1]) for c in GOLDEN_CASES],
)
def test_guard_matches_golden(fixture_work, stem, label, payload, extra, stubs):
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


def test_every_guard_discriminates(fixture_work):
    """No guard may answer the same way on every case it was given.

    A guard that returns 0 on all of its inputs has been compared against a constant, which is the failure `test_shellscan_differential` found in its own field set: "the target_root field evaluated against an absent root was empty on all 385 cases -- a comparison that could not have failed".

    Exit code alone is not the test, because the four `warn-*` guards exit 0 by design and speak on stderr. The predicate is that SOMETHING varies. Runs every guard's own Python answer, golden-backed or `OWN_SUITE`: before PLAN-retire-bash-oracles A3 this read the bash driver's records for the golden-backed half and called `python_fields` directly for the rest, a split that
    existed only because the bash driver read `bash_results["records"][i]` back by POSITION (see `build_cases`'s docstring). There is no driver left to disagree with, so one pass over `CASES` covers every guard the same way.
    """
    seen = {}
    for stem, _, payload, _, extra, stubs in CASES:
        fields = python_fields(stem, payload, extra, stubs, fixture_work)
        seen.setdefault(stem, set()).add((fields["rc"], fields["out"], fields["err"]))
    flat = sorted(stem for stem, values in seen.items() if len(values) < 2)
    assert not flat, (
        "these guards answered identically on every case, so comparing them proves "
        "nothing: %s" % flat
    )


def test_the_differential_can_fail(tmp_path, fixture_work):
    """Every port declares one defect, and the comparison must catch it.

    A differential that has never failed is not evidence. This plants each port's own declared defect -- a single source substitution naming the line its twin's comments say cost the most -- and requires the ported guard to answer differently on at least one case it was given.
    """
    work = fixture_work
    unproven = []
    # THIS CONTROL COMPARES THE PORT AGAINST ITSELF-WITH-A-BUG and never needed
    # a golden or a bash process, which is what makes it work identically for an `OWN_SUITE` guard -- and an `OWN_SUITE` guard needs it MORE, being the one with no golden.
    all_cases = CASES
    for stem in guards.stems():
        module = guards.load(stem)
        defect = getattr(module, "DEFECT", None)
        assert defect, "%s declares no DEFECT, so nothing proves its differential can fail" % stem
        old, new = defect
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert old in source, "%s's declared DEFECT no longer applies to the port: %r" % (stem, old)
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
        if not changed:
            unproven.append(stem)
    assert not unproven, (
        "these ports answered identically with their declared defect planted, so this "
        "file's green does not depend on that branch being right: %s" % unproven
    )
