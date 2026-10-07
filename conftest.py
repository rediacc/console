"""Repo-root conftest: attach the xdist groups derived in `rediacc_ci.xdist_groups`.

WHY AT THE ROOT AND NOWHERE ELSE. `pyproject.toml` lists three `testpaths` (`.ci/rediacc_ci/tests`, `.ci/rediacc_ci/tests/gates`, `.claude/rediacc_hooks/tests`), and pytest loads a conftest for every directory from the rootdir DOWN to each collected file. Only a conftest at the rootdir is therefore seen by all three; one placed in any of them would silently leave the other two
ungrouped, which is the half-wired shape that reads as working.

WHY THE IMPORT BELOW WORKS WITHOUT A sys.path HOP. `pythonpath = [".ci"]` in
pyproject.toml is applied by `Config._configure_python_path`, which `_pytest/config/__init__.py:1575` calls BEFORE the `pytest_load_initial_conftests` dispatch at :1603 that imports this file (verified against pytest 9.1.1). A hand-written hop here would be a second copy of that decision. If the ordering ever changes, the failure is a loud ConftestImportFailure naming this file,
not a silent loss of grouping.

WHAT IT DOES NOT DO. It does not turn parallelism on, and it does not decide the worker count. `-n` lives on the GATE's argv (`.ci/rediacc_ci/check_pytest.py`) and deliberately not in `addopts`: `test_twin_parity.py` spawns a nested `python -m pytest` per ported module, which reads the same ini, so `-n auto` in `addopts` would have 24 outer workers each spawn
24 inner ones. `--dist loadgroup` IS in `addopts` (pyproject.toml says why): without it these markers do nothing, and a bare `pytest -n auto` spread test_guards_differential.py's session fixture over 24 workers.
"""

import os
import subprocess
import sys

import pytest
from rediacc_ci import xdist_groups

# The sweep of basetemps a KILLED run left, for every test in both pytest roots; see that module for why it is a plugin rather than code here.
pytest_plugins = ["rediacc_ci.pytest_tmp"]


# The lock's real-tree declarations, read ONCE per process. A dict rather than a module-level rebind so no `global` statement is needed; the key names the reason the entry exists rather than being a bare index.
_CACHE: dict[str, set[str]] = {}


def _real_tree_twins() -> set[str]:
    if "real_tree_twins" not in _CACHE:
        _CACHE["real_tree_twins"] = xdist_groups.real_tree_twins(xdist_groups.lock_path())
    return _CACHE["real_tree_twins"]


def pytest_report_header() -> str:
    """PRINT THE SHAPE, so a collapse in the join is visible rather than silent.

    The number that matters is how many real-tree gate tests the lock declares. It is the only source since the shell battery runner was retired, so if it ever reads 0, the derivation below admits every twin to every worker and `test_twin_parity`'s own refusal is the thing that will go red -- but a reader seeing this line will already know why.

    Suppressed automatically under `-q` (pytest prints no header at negative verbosity), which is what keeps the nested parity runs' output unchanged.
    """
    return "xdist groups: %d real-tree gate test(s) declared by the lock" % len(_real_tree_twins())


# `tryfirst` IS LOAD-BEARING, NOT TIDINESS. Without it this hook does NOTHING and does it silently.
#
# xdist reads the group in the WORKER (xdist/remote.py:236) from a `pytest_collection_modifyitems` that carries NO hookimpl decorator, so it runs at DEFAULT priority -- and pluggy calls it before a default-priority conftest impl. By the time this ran, xdist had already frozen `item._nodeid`, so every marker added here was ignored and every test distributed freely.
#
# MEASURED on a minimal 8-test repro, one group for everything, `-n 8 --dist loadgroup`, against a 3.57s ungrouped reference:
#
# static @pytest.mark.xdist_group in the file 18.23s honoured added by this hook, default priority 3.90s IGNORED added by this hook with tryfirst 17.88s honoured
#
# The 3.90s row is the failure mode: a green run, the right number of tests, and no grouping at all. On the real corpus this was the difference between 1015.50s and 381.41s -- and, worse than the time, it left test_core_ports.py's deterministic 20000-port scan UNGUARDED while appearing to be guarded.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every item whose module declares a shared resource.

    NO-OP WITHOUT THE PLUGIN, and that is a guard rather than a convenience. `--strict-markers` is on, so `pytest.mark.xdist_group` on a pytest that has no xdist registered is a hard error at attribute-access time -- it would break every serial run on a host where the bootstrap has not installed the plugin yet. Skipping is safe here and hides nothing: with no xdist there are no
    workers, so there is nothing a group could have serialised.

    Modules are grouped, not items: the resources being declared (the real tree, the host's port space) are shared by every test in the file.
    """
    if not config.pluginmanager.hasplugin("xdist"):
        return
    _order_longest_first(config, items)
    unsafe = _real_tree_twins()
    # Memoised per module, because `group_for` is cheap but `item.module` is asked about nine thousand times and the answer cannot differ between two items of the same module.
    seen: dict[str, str | None] = {}
    for item in items:
        module = getattr(item, "module", None)
        if module is None:
            continue
        name = getattr(module, "__name__", "")
        if name not in seen:
            seen[name] = xdist_groups.group_for(module, unsafe)
        group = seen[name]
        if group:
            item.add_marker(pytest.mark.xdist_group(group))


_GROUP_LOCK = pytest.StashKey[xdist_groups.MachineGroupLock]()


def _group_of(item: pytest.Item | None) -> str | None:
    marker = item.get_closest_marker("xdist_group") if item is not None else None
    if marker is None:
        return None
    name = marker.args[0] if marker.args else marker.kwargs.get("name")
    return str(name) if name else None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    """Hold the item's group machine-wide (xdist_groups.MachineGroupLock) from the group's first item to its last, so a concurrent run's same group waits instead of colliding on its fixed ports or paths. Released when the next item leaves the group, which also covers a module fixture torn down in the last item's teardown."""
    group = _group_of(item)
    lock = item.config.stash.setdefault(_GROUP_LOCK, xdist_groups.MachineGroupLock())
    if group is not None:
        lock.enter(group)
    elif lock.held is not None:
        lock.release()
    # The write record ("Write attribution" below) names the test running when a tree write happened; setup, call and teardown all belong to it.
    _AUDIT["test"] = item.nodeid
    yield
    _AUDIT["test"] = "(between tests)"
    if group is not None and _group_of(nextitem) != group:
        lock.release()


def _order_longest_first(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Reorder `items` so the longest-measured files start first (agent/plans/PLAN-prepush-full-cpu.md PF18).

    UNDER xdist ONLY, because a serial run's wall is the sum whatever the order. The measurement is `.ci/config/lane-durations.json`'s per-file `units` (see `xdist_groups.unit_durations` for why the tracked file and not the local junit), and the sort is stable, so items keep their order within a file.
    """
    durations, default = xdist_groups.unit_durations()
    if not durations:
        return
    root = config.rootpath
    files = []
    for item in items:
        try:
            files.append(str(item.path.relative_to(root)))
        except ValueError:
            files.append(str(item.path))
    order = xdist_groups.order_longest_first(files, durations, default)
    items[:] = [items[i] for i in order]


# --------------------------------------------------------------------------- Write attribution, shared by the two tree checks below (2026-10-07).
#
# WHY. Both checks compare the tree before and after a session, and a difference says only that SOMETHING wrote the tree. In a checkout other sessions are editing, that something is usually a peer: on 2026-10-07 four writers got rc=1 from runs in which every test passed, because another session committed or edited files under the watched roots mid-run, and the
# message blamed whichever test happened to run last. A tripwire that cries wolf in the shared checkout gets switched off there (TREE_SNAPSHOT=0), and then it guards nothing.
#
# HOW. A `sys.addaudithook` in every process that runs tests (the serial process, or each xdist worker) records each path under the rootdir that is opened for writing, renamed, removed, created, truncated or chmodded, keyed to the test running at that moment (`_AUDIT["test"]`, set by `pytest_runtest_protocol`). Under xdist each worker hands its record
# to the controller through `workeroutput`. A changed path this record holds is the run's own write, named by test, and fails the run in every tree.
#
# WHAT THE RECORD CANNOT SEE, and why a strict mode remains. An audit hook sees its own process only, so a write made by a CHILD a test spawned (git, node, a python subprocess) is as anonymous as a peer's. So an unattributed change is judged by the tree: when no tracked path was modified at session start (the push clone, CI's fresh checkout), nothing but
# this run could have written it and it FAILS, exactly as before. When the tree was already dirty (a shared checkout), it is reported as a WARNING naming every path and the run's verdict stands. The mode is printed on every run, so a collapse to the shared mode where strict was expected is visible.

#: The audit events that change the tree, and the argument positions holding a written path (with its dir_fd, or None). NOT `os.mkdir` or `os.rmdir`: git cannot see an empty directory, a file made inside one has its own `open`, and `mkdir(exist_ok=True)` raises the event for a directory that already exists, which
#: under the subtree rule below made one test the author of everything under `.ci` (measured on the first full hooks run of this change, 2026-10-07).
_WRITE_EVENTS: dict[str, tuple[tuple[int, int | None], ...]] = {
    "open": ((0, None),),
    "os.rename": ((0, 2), (1, 3)),
    "os.remove": ((0, 1),),
    "os.truncate": ((0, None),),
    "os.chmod": ((0, 2),),
    "os.symlink": ((1, 2),),
    "os.link": ((1, 3),),
    "shutil.rmtree": ((0, 1),),
}
_OPEN_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

#: rootdir-relative path -> the nodeid of the first test that wrote it, for THIS process.
_WRITES: dict[str, str] = {}
#: Unattributed findings of the `_tree_snapshot` fixture in a shared tree, for THIS process; the controller prints them.
_NOTES: list[str] = []
_AUDIT: dict[str, object] = {"root": None, "test": "(collection)", "busy": False}
_FORWARDED = pytest.StashKey[tuple[dict[str, str], list[str]]]()


def _audit_path(arg, dir_fd) -> str | None:
    """The absolute path an audit argument names, or None when it is a bare descriptor that cannot be read back."""
    if isinstance(arg, int):
        try:
            return os.readlink("/proc/self/fd/%d" % arg)
        except OSError:
            return None
    path = os.fsdecode(os.fspath(arg))
    if not os.path.isabs(path) and isinstance(dir_fd, int) and dir_fd >= 0:
        try:
            path = os.path.join(os.readlink("/proc/self/fd/%d" % dir_fd), path)
        except OSError:
            return None
    return os.path.abspath(path)


#: The events whose path may be a DIRECTORY carrying a whole subtree (a directory renamed into place or away, a tree removed). Only these are recorded as `<rel>/`, which `attributed` matches as a prefix.
_SUBTREE_EVENTS = frozenset({"os.rename", "shutil.rmtree"})


def record_write(
    root: str, path: str, test: str, writes: dict[str, str], subtree: bool = False
) -> None:
    """File `path` under `root` (both absolute) into `writes` as written by `test`, and as the subtree `<rel>/` too when `subtree`. Bytecode caches are skipped: git ignores them and they are most of the volume."""
    for base in (path, os.path.realpath(path)):
        if base.startswith(root + os.sep):
            rel = base[len(root) + 1 :]
            if "__pycache__" not in rel:
                writes.setdefault(rel, test)
                if subtree:
                    writes.setdefault(rel + "/", test)
            return


def _audit_hook(event: str, args: tuple) -> None:
    spec = _WRITE_EVENTS.get(event)
    if spec is None or _AUDIT["busy"]:
        return
    if event == "open" and not (isinstance(args[2], int) and args[2] & _OPEN_WRITE_FLAGS):
        return
    _AUDIT["busy"] = True
    try:
        root = str(_AUDIT["root"])
        for path_at, fd_at in spec:
            path = _audit_path(args[path_at], args[fd_at] if fd_at is not None else None)
            if path is not None:
                record_write(root, path, str(_AUDIT["test"]), _WRITES, event in _SUBTREE_EVENTS)
    except Exception:  # noqa: BLE001 -- an audit hook that raises aborts the operation it audits; a lost record is only a weaker attribution
        pass
    finally:
        _AUDIT["busy"] = False


def attributed(rel: str, writes: dict[str, str]) -> str | None:
    """The test that wrote `rel` itself, or moved or removed an ancestor directory of it as a subtree (a `<dir>/` entry), or None. A plain write to an ancestor's NAME attributes nothing below it."""
    if rel in writes:
        return writes[rel]
    probe = os.path.dirname(rel)
    while probe:
        if probe + "/" in writes:
            return writes[probe + "/"]
        probe = os.path.dirname(probe)
    return None


def judge(
    changed: list[str], writes: dict[str, str], strict: bool
) -> tuple[list[tuple[str, str | None]], list[str]]:
    """Split `changed` into (failing, foreign). In a strict tree every change fails, attributed or not; in a shared tree only the run's own writes fail and the rest are a peer's or a child process's, reported as foreign."""
    failing: list[tuple[str, str | None]] = []
    foreign: list[str] = []
    for rel in changed:
        who = attributed(rel, writes)
        if who is not None or strict:
            failing.append((rel, who))
        else:
            foreign.append(rel)
    return failing, foreign


def tree_is_strict(root) -> bool:
    """True when no TRACKED path is modified or staged, so no other writer can be assumed. Untracked files do not count, because a CI build leaves them. Unknown (git cannot answer) is strict: the weaker mode is earned, never defaulted into."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode != 0 or result.stdout == ""


def _mode(strict: bool) -> str:
    return (
        "strict: no tracked path was modified at start, so every change fails"
        if strict
        else "shared: the tree was already dirty, so only this run's own writes fail"
    )


def pytest_configure(config: pytest.Config) -> None:
    """Install the write record once per process, rooted at the rootdir."""
    if os.environ.get(SNAPSHOT_ENV) == "0" or _AUDIT["root"] is not None:
        return
    _AUDIT["root"] = os.path.realpath(str(config.rootpath))
    sys.addaudithook(_audit_hook)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node) -> None:
    """xdist controller: gather each worker's write record and its shared-tree notes."""
    writes, notes = node.config.stash.setdefault(_FORWARDED, ({}, []))
    output = getattr(node, "workeroutput", None) or {}
    for rel, test in (output.get("tree_writes") or {}).items():
        writes.setdefault(rel, test)
    notes.extend(n for n in output.get("tree_notes") or [] if n not in notes)


# --------------------------------------------------------------------------- The untracked-file snapshot, and the reason it is session-scoped and autouse.
#
# A TEST THAT WRITES THE REAL TREE LEAVES NO TRACE IN ITS OWN RESULT. The retired bash worklist suites wrote `aa.jsonl`, `zz.jsonl`, `.events.jsonl`, `.lastevent-*.json`, `.requests`, `.local/` and `claude/` into the repository root and every one of them passed; the debris was found weeks later by a human looking at `git status`. `check:ci-tree-shape` now refuses those files in
# CI, which catches them a commit too late. This catches them in the run that made them.
#
# WHY SESSION-SCOPED RATHER THAN PER TEST. A per-test snapshot is two `git status` calls times nine thousand tests, which is minutes of subprocess time to answer a question whose answer changes a handful of times a year. The session pair costs two calls, and the write record above names the test that wrote a stray when the write was in-process.
#
# WHY IT FAILS RATHER THAN WARNS. A warning at the end of a green run is read by nobody. The failure is raised from the fixture's teardown, so the tests' own verdicts are printed first and this one lands underneath them where it cannot be mistaken for a test failure. The one exception is the shared tree's UNATTRIBUTED stray (see "Write attribution"): a peer's file
# is not this run's failure, so it is printed by the controller as a warning, path by path.
#
# UNDER xdist THE CHECK RUNS IN EVERY WORKER: each worker snapshots the same tree and judges it against its OWN write record, so the worker that wrote a stray fails naming the test, and in a strict tree every other worker fails too. `TREE_SNAPSHOT=0` switches it off for the one case it cannot serve, a suite deliberately driven against a dirty checkout.
#
# ROOTED AT THE RUN'S ROOTDIR, not at `paths.repo_root()`: they are the same directory for the real suite, and in a nested pytest against a scratch repository (test_tree_tripwire.py) the rootdir is the scratch tree, where the old root watched the real checkout and read a peer's file there as the nested run's stray.

#: NOT a `WORKLIST_*` name, deliberately. `check:ci-worklist-env-registry` owns that prefix and its corpus does not reach this file, so a name claiming it would be governed by a registry that cannot see it. `check:ci-python-env-registry` keys on the whole tree with no prefix and does reach here, which is the one that must carry it.
SNAPSHOT_ENV = "TREE_SNAPSHOT"

#: The three trees a stray is both likely and invisible in. `:(glob)*` matches depth-1 files at the root only, because a bare `*` in a git pathspec crosses `/` and would pull in the whole repository.
SCOPE = (":(glob)*", "agent", ".claude/hooks/stop")
REVIEWS = "agent/reviews/"


def _untracked(root) -> set[str]:
    """Untracked-not-ignored paths, or an empty set when git cannot answer.

    An EMPTY SET on failure rather than a raise: this fixture must never be the reason a suite fails, and a git that cannot run leaves the before and after equal, which is silence rather than a false accusation.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--others",
                "--exclude-standard",
                "--",
                *SCOPE,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    # `agent/reviews/` is written ASYNCHRONOUSLY by the per-commit reviewer (agent/plans/PLAN-per-commit-review.md), a detached process any commit in this checkout starts; a review that lands while a suite runs is that process's file, not a test's, and was measured failing an unrelated suite on 2026-10-02.
    return {path for path in result.stdout.split("\0") if path and not path.startswith(REVIEWS)}


@pytest.fixture(scope="session", autouse=True)
def _tree_snapshot(request):
    """Fail the session when a test left an untracked file in the real tree."""
    if os.environ.get(SNAPSHOT_ENV) == "0":
        yield
        return
    root = request.config.rootpath
    strict = tree_is_strict(root)
    before = _untracked(root)
    yield
    added = sorted(_untracked(root) - before)
    failing, foreign = judge(added, _WRITES, strict)
    if foreign:
        _NOTES.append(
            "tree snapshot: %d untracked file(s) appeared that no test of this run wrote in-process (%s); "
            "a concurrent session's file, or a child process's:\n%s"
            % (len(foreign), _mode(strict), "\n".join("    %s" % path for path in foreign))
        )
    if not failing:
        return
    last = getattr(getattr(request.session, "items", [None])[-1], "nodeid", "(unknown)")
    raise AssertionError(
        "%d untracked file(s) appeared in the real tree during this session (%s):\n%s\n"
        "  A path naming no test was written by a child process a test spawned, or by another writer; "
        "the last test to run was %s, which is where to look first.\n"
        "  A test that writes the repository leaves no trace in its own result, which is "
        "how the retired bash worklist suites put aa.jsonl, zz.jsonl and .events.jsonl at "
        "the repository root and stayed green. Write to tmp_path instead.\n"
        "  Set %s=0 only for a suite deliberately driven against a dirty checkout."
        % (
            len(failing),
            _mode(strict),
            "\n".join(
                "    %s%s" % (path, "  written by %s" % who if who else "") for path, who in failing
            ),
            last,
            SNAPSHOT_ENV,
        )
    )


# --------------------------------------------------------------------------- The session TRIPWIRE on tracked paths (agent/plans/PLAN-prepush-full-cpu.md PF15, 2026-10-05).
#
# WHY IT EXISTS. Three gate tests used to plant into the real tree, and the suite bought that off with the `real-tree` xdist group (one worker) and an exclusive `tree:repo` claim on check:ci-pytest, which held six other gates out of the pool for the whole pytest wall. The plants moved into copies and both serialisations were dropped. This is what keeps them dropped: a test that changes a tracked path, or leaves a new file, under the testpaths roots or the directories the gate tests scan fails the run that did it, naming the path. The `_tree_snapshot` fixture above watches a different place (strays at the root, in `agent/` and `.claude/hooks/stop`) and stays as it is.
#
# IN THE CONTROLLER ONLY, before collection and after the last report. Under xdist the workers start at different moments, so a per-worker pair would blame a file one worker wrote on every other worker; the controller's pair spans the whole run once, and judges it against the write records the workers forward. A serial run has no workers and the same two hooks run in-process.
#
# ON CONTENT, NOT ON THE STATUS LETTER. A file already modified before the run reads ` M` before and after however much a test rewrites it, so each listed path is keyed on its status AND a hash of its bytes.
#
# UNKNOWN IS A FAILURE. If git cannot answer at the start, nothing is being checked, and a green run would claim a tree it never looked at.
#
# IN A SHARED CHECKOUT a concurrent session's edit or commit under these roots reads as a difference too, and is judged by "Write attribution" above: a change no test of this run wrote in-process is a warning naming the path when the tree was dirty at start, and a failure when it was not (the push clone, CI).

#: The directories the gate tests scan, beside the testpaths roots read from the ini.
TRIPWIRE_SCAN_DIRS = ("scripts", ".ci/scripts", "packages/www/scripts")
_TRIPWIRE_KEY = pytest.StashKey[tuple[dict[str, tuple[str, str]] | None, bool]]()
_TRIPWIRE_LINES = pytest.StashKey[list[str]]()


def tripwire_scope(config: pytest.Config) -> list[str]:
    """The testpaths roots plus the gate tests' scan directories, as git pathspecs relative to the rootdir."""
    return [*config.getini("testpaths"), *TRIPWIRE_SCAN_DIRS]


def parse_porcelain(raw: str) -> list[tuple[str, str]]:
    """`(status, path)` pairs from `git status --porcelain=v1 -z`. A rename or copy carries its source as a second NUL field, which names the old path and is skipped."""
    out: list[tuple[str, str]] = []
    fields = raw.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        out.append((status, path))
        if status[0] in "RC":
            i += 1
    return out


def tree_state(root, scope: list[str]) -> dict[str, tuple[str, str]] | None:
    """`{path: (status, sha256 of its bytes or "<absent>")}` for every changed or untracked path under `scope`, or None when git cannot answer."""
    import hashlib  # noqa: PLC0415 -- only the tripwire needs it, and conftest is imported by every run

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                *scope,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    state: dict[str, tuple[str, str]] = {}
    for status, rel in parse_porcelain(result.stdout):
        path = root / rel
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<absent>"
        except OSError:
            digest = "<unreadable>"
        state[rel] = (status, digest)
    return state


def tripwire_diff(
    before: dict[str, tuple[str, str]], after: dict[str, tuple[str, str]]
) -> list[str]:
    """Every path whose status or bytes differ between the two states, sorted."""
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def _tripwire_off(config: pytest.Config) -> bool:
    return os.environ.get(SNAPSHOT_ENV) == "0" or hasattr(config, "workerinput")


def pytest_sessionstart(session: pytest.Session) -> None:
    config = session.config
    if _tripwire_off(config):
        return
    config.stash[_TRIPWIRE_KEY] = (
        tree_state(config.rootpath, tripwire_scope(config)),
        tree_is_strict(config.rootpath),
    )


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    if hasattr(config, "workerinput"):
        # A worker hands its write record and notes to the controller, which judges the run once.
        if os.environ.get(SNAPSHOT_ENV) != "0":
            config.workeroutput["tree_writes"] = dict(_WRITES)  # type: ignore[attr-defined]
            config.workeroutput["tree_notes"] = list(_NOTES)  # type: ignore[attr-defined]
        return
    if _tripwire_off(config) or _TRIPWIRE_KEY not in config.stash:
        return
    before, strict = config.stash[_TRIPWIRE_KEY]
    scope = tripwire_scope(config)
    lines: list[str] = []
    config.stash[_TRIPWIRE_LINES] = lines
    say = lines.append
    # Serial: this process ran the tests. xdist: the workers' records, forwarded by pytest_testnodedown.
    writes, notes = config.stash.get(_FORWARDED, (dict(_WRITES), list(_NOTES)))
    lines.extend(notes)

    after = tree_state(config.rootpath, scope)
    if before is None or after is None:
        say(
            "TREE TRIPWIRE UNCHECKED: `git status` could not be read in %s, so no test was shown not to "
            "have changed a tracked path under %s. Unknown is not clean."
            % (config.rootpath, ", ".join(scope))
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        return
    failing, foreign = judge(tripwire_diff(before, after), writes, strict)
    if foreign:
        say(
            "tree tripwire WARNING: %d path(s) under %s changed during this session with no in-process write "
            "by any test of this run (%s). A concurrent session's edit or commit, or a child process a test "
            "spawned; in the push clone and CI these fail:"
            % (len(foreign), ", ".join(scope), _mode(strict))
        )
        for rel in foreign:
            say(
                "    %s  %s -> %s"
                % (rel, (before.get(rel) or ("--", ""))[0], (after.get(rel) or ("--", ""))[0])
            )
    if not failing:
        # The shape, so a reader can see it ran and over what. Not under -q, which keeps the nested parity runs' output unchanged (see pytest_report_header).
        if config.get_verbosity() >= 0:
            say(
                "tree tripwire: 0 of %d listed path(s) changed by this run under %s (%s; %d in-tree write(s) recorded)"
                % (len(after), ", ".join(scope), _mode(strict), len(writes))
            )
        return
    say(
        "TREE TRIPWIRE: %d path(s) under %s changed during this session (%s):"
        % (len(failing), ", ".join(scope), _mode(strict))
    )
    for rel, who in failing:
        say(
            "    %s  %s -> %s  %s"
            % (
                rel,
                (before.get(rel) or ("--", ""))[0],
                (after.get(rel) or ("--", ""))[0],
                "written by %s" % who
                if who
                else "(no in-process write: a child process a test spawned, or another writer)",
            )
        )
    say(
        "  A test wrote the tracked tree. Plant into a copy instead (test_gate_gate_anti_vacuity.py's "
        "empty_tree_fixture, test_gate_paths_exist.py's planted_fixture)."
    )
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    """The tripwire's verdict, printed in the summary: `pytest_sessionfinish` above runs inside the terminal reporter's own finish, before this section, and writing from there lands on the progress line."""
    for line in config.stash.get(_TRIPWIRE_LINES, []):
        terminalreporter.write_line(line)
