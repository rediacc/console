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

import pytest
from rediacc_ci import paths, xdist_groups

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


# --------------------------------------------------------------------------- The untracked-file snapshot, and the reason it is session-scoped and autouse.
#
# A TEST THAT WRITES THE REAL TREE LEAVES NO TRACE IN ITS OWN RESULT. The retired bash worklist suites wrote `aa.jsonl`, `zz.jsonl`, `.events.jsonl`, `.lastevent-*.json`, `.requests`, `.local/` and `claude/` into the repository root and every one of them passed; the debris was found weeks later by a human looking at `git status`. `check:ci-tree-shape` now refuses those files in
# CI, which catches them a commit too late. This catches them in the run that made them.
#
# WHY SESSION-SCOPED RATHER THAN PER TEST. A per-test snapshot is two `git status` calls times nine thousand tests, which is minutes of subprocess time to answer a question whose answer changes a handful of times a year. The session pair costs two calls and still names the culprit, because the LAST TEST TO RUN is reported alongside the paths -- not proof, but the first place
# to look, and under `-p no:randomly` it is the file that wrote them.
#
# WHY IT FAILS RATHER THAN WARNS. A warning at the end of a green run is read by nobody. The failure is raised from the fixture's teardown, so the tests' own verdicts are printed first and this one lands underneath them where it cannot be mistaken for a test failure.
#
# UNDER xdist THE CHECK RUNS IN EVERY WORKER, and that is harmless rather than wrong: each worker snapshots the same tree, so a file written by any of them is reported by all of them. `TREE_SNAPSHOT=0` switches it off for the one case it cannot serve, a suite deliberately driven against a dirty checkout.

#: NOT a `WORKLIST_*` name, deliberately. `check:ci-worklist-env-registry` owns that prefix and its corpus does not reach this file, so a name claiming it would be governed by a registry that cannot see it. `check:ci-python-env-registry` keys on the whole tree with no prefix and does reach here, which is the one that must carry it.
SNAPSHOT_ENV = "TREE_SNAPSHOT"

#: The three trees a stray is both likely and invisible in. `:(glob)*` matches depth-1 files at the root only, because a bare `*` in a git pathspec crosses `/` and would pull in the whole repository.
SCOPE = (":(glob)*", "agent", ".claude/hooks/stop")
REVIEWS = "agent/reviews/"


def _untracked() -> set[str]:
    """Untracked-not-ignored paths, or an empty set when git cannot answer.

    An EMPTY SET on failure rather than a raise: this fixture must never be the reason a suite fails, and a git that cannot run leaves the before and after equal, which is silence rather than a false accusation.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(paths.repo_root()),
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
    before = _untracked()
    yield
    added = sorted(_untracked() - before)
    if not added:
        return
    last = getattr(getattr(request.session, "items", [None])[-1], "nodeid", "(unknown)")
    raise AssertionError(
        "%d untracked file(s) appeared in the real tree during this session:\n%s\n"
        "  The last test to run was %s, which is where to look first.\n"
        "  A test that writes the repository leaves no trace in its own result, which is "
        "how the retired bash worklist suites put aa.jsonl, zz.jsonl and .events.jsonl at "
        "the repository root and stayed green. Write to tmp_path instead.\n"
        "  Set %s=0 only for a suite deliberately driven against a dirty checkout."
        % (len(added), "\n".join("    %s" % path for path in added), last, SNAPSHOT_ENV)
    )


# --------------------------------------------------------------------------- The session TRIPWIRE on tracked paths (agent/plans/PLAN-prepush-full-cpu.md PF15, 2026-10-05).
#
# WHY IT EXISTS. Three gate tests used to plant into the real tree, and the suite bought that off with the `real-tree` xdist group (one worker) and an exclusive `tree:repo` claim on check:ci-pytest, which held six other gates out of the pool for the whole pytest wall. The plants moved into copies and both serialisations were dropped. This is what keeps them dropped: a test that changes a tracked path, or leaves a new file, under the testpaths roots or the directories the gate tests scan fails the run that did it, naming the path. The `_tree_snapshot` fixture above watches a different place (strays at the root, in `agent/` and `.claude/hooks/stop`) and stays as it is.
#
# IN THE CONTROLLER ONLY, before collection and after the last report. Under xdist the workers start at different moments, so a per-worker pair would blame a file one worker wrote on every other worker; the controller's pair spans the whole run once. A serial run has no workers and the same two hooks run in-process.
#
# ON CONTENT, NOT ON THE STATUS LETTER. A file already modified before the run reads ` M` before and after however much a test rewrites it, so each listed path is keyed on its status AND a hash of its bytes.
#
# UNKNOWN IS A FAILURE. If git cannot answer at the start, nothing is being checked, and a green run would claim a tree it never looked at.
#
# IN A SHARED CHECKOUT a concurrent session's edit under these roots during the run reads as a difference too. The pre-push runs in its push clone, where the tree is still; set TREE_SNAPSHOT=0 (the switch the fixture above already honours) only for a suite deliberately driven against a tree others are editing.

#: The directories the gate tests scan, beside the testpaths roots read from the ini.
TRIPWIRE_SCAN_DIRS = ("scripts", ".ci/scripts", "packages/www/scripts")
_TRIPWIRE_KEY = pytest.StashKey[dict[str, tuple[str, str]] | None]()
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
    config.stash[_TRIPWIRE_KEY] = tree_state(config.rootpath, tripwire_scope(config))


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    if _tripwire_off(config) or _TRIPWIRE_KEY not in config.stash:
        return
    before = config.stash[_TRIPWIRE_KEY]
    scope = tripwire_scope(config)
    lines: list[str] = []
    config.stash[_TRIPWIRE_LINES] = lines
    say = lines.append

    after = tree_state(config.rootpath, scope)
    if before is None or after is None:
        say(
            "TREE TRIPWIRE UNCHECKED: `git status` could not be read in %s, so no test was shown not to "
            "have changed a tracked path under %s. Unknown is not clean."
            % (config.rootpath, ", ".join(scope))
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        return
    changed = tripwire_diff(before, after)
    if not changed:
        # The shape, so a reader can see it ran and over what. Not under -q, which keeps the nested parity runs' output unchanged (see pytest_report_header).
        if config.get_verbosity() >= 0:
            say(
                "tree tripwire: 0 of %d listed path(s) changed under %s"
                % (len(after), ", ".join(scope))
            )
        return
    say(
        "TREE TRIPWIRE: %d path(s) under %s changed during this session:"
        % (len(changed), ", ".join(scope))
    )
    for rel in changed:
        say(
            "    %s  %s -> %s"
            % (rel, (before.get(rel) or ("--", ""))[0], (after.get(rel) or ("--", ""))[0])
        )
    say(
        "  A test wrote the tracked tree. Plant into a copy instead (test_gate_gate_anti_vacuity.py's "
        "empty_tree_fixture, test_gate_paths_exist.py's planted_fixture). In a checkout other sessions are "
        "editing, a concurrent edit under these roots reads the same way; the pre-push runs in its push "
        "clone, where the tree is still."
    )
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    """The tripwire's verdict, printed in the summary: `pytest_sessionfinish` above runs inside the terminal reporter's own finish, before this section, and writing from there lands on the progress line."""
    for line in config.stash.get(_TRIPWIRE_LINES, []):
        terminalreporter.write_line(line)
