"""No test writes the project `CLAUDE_PROJECT_DIR` names, whatever the launching environment says (worklist #04a74a81).

THE DEFECT. Claude Code exports `CLAUDE_PROJECT_DIR`, and `wl_core.project_start` takes it as the project root ahead of every other rung. `wlfix.Fixture.python` pinned its fixture root with `setdefault` on an environment that still carried the inherited value, so a suite launched from a live session sent `--queue-set`, `--hint-propose` and the retro verbs to the REAL checkout. Measured
2026-10-09 in a scratch clone: `agent/plans/QUEUE.md`'s settings block came back as `turbo: on -- operator test` / `batch_size: 4`, two `agent/ledgers/*.jsonl` gained rows, and 201 hook tests failed. Unset, the same run was clean, which is why CI never saw it.

THE CONTROL IS A NESTED RUN, because the outer run cannot be its own witness: the root conftest drops the variable before this module is imported, so in-process it is absent whether or not the scrub works. The child pytest is launched WITH the variable aimed at a sentinel tree (a git repo holding copies of the files the leak rewrote) and runs (a) tests measured writing through the leak and (b) the probe
below, which only the child can make non-vacuous. The sentinel must come back byte-identical and the child must pass.

TWO NESTED RUNS, ONE PER LAYER, so each layer is shown right ON ITS OWN (review finding 6351de94.1). Run A loads the root conftest: its pop and the fixture scrub both apply, the probe passes and the sentinel stays byte-identical. Run B passes `--confcutdir` at this directory, so pytest never loads the root conftest and the variable REACHES the tests: the probe must FAIL there (that failure is the control proving the variable got through), and the leakers must still pass with the sentinel byte-identical, which only `wlfix.scrubbed_environ` can now explain. Removing the scrub's `CLAUDE_PROJECT_DIR` entry alone reds run B with the sentinel's QUEUE.md and both ledgers changed; removing the conftest pop alone reds run A's probe.

The case counts are matched as whole numbers (a negative lookbehind for a digit before `7 passed`), so `17 passed` never satisfies an expected `7 passed` (review finding 6351de94.3).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

REAL_ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
TIMEOUT = 600

#: The tests measured writing through the leak (QUEUE.md's settings block, hint-proposals.jsonl, stop-hook-retros.jsonl), one per writing verb family, every family the fix's commit named included (review finding 6351de94.2): measured 2026-10-11 by running each test of test_wl_queue_settings, test_wl_hints, test_wl_identity and test_wl_retro with `--confcutdir` and the scrub entry removed, and keeping one that wrote per file and verb.
LEAKERS = (
    "test_wl_queue_settings.py::test_queue_set_writes_atomically_prints_git_add_and_never_commits",
    "test_wl_hints.py::test_hint_propose_cli_round_trip_via_worklist",
    "test_wl_identity.py::test_184_every_verb_taking_a_me_refuses_an_identity_this_session_is_not",
    "test_wl_retro.py::test_r13_retro_brief_prints_the_id_and_the_previous_range_end",
    "test_wl_retro.py::test_r13_a_leased_item_writes_the_dispatched_row_once",
    "test_wl_retro.py::test_r13_a_tick_with_the_plan_path_writes_the_saved_row",
    "test_wl_retro.py::test_r17_the_brief_window_starts_at_the_last_saved_retro",
)
PROBE = "test_project_dir_containment.py::test_the_harness_root_never_reaches_a_test"

#: The files the leak rewrote, copied into the sentinel so a leaked write has the same target it had in the real tree.
SEEDED = (
    "agent/plans/QUEUE.md",
    "agent/ledgers/hint-proposals.jsonl",
    "agent/ledgers/stop-hook-retros.jsonl",
)


def test_the_harness_root_never_reaches_a_test():
    """The probe. Vacuous in a run launched without the variable (CI), and the reason the nested run below exists: there it is launched WITH it."""
    assert "CLAUDE_PROJECT_DIR" not in os.environ, (
        "CLAUDE_PROJECT_DIR=%r reached a test; every hook a test spawns with an inherited "
        "environment would take it as the project root and write there"
        % os.environ["CLAUDE_PROJECT_DIR"]
    )


def _digest(root: pathlib.Path) -> dict[str, str]:
    """rel path -> sha256 for every file under `root` outside `.git`."""
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _counted(output: str, word: str, n: int) -> bool:
    """Whether pytest's summary says exactly `n <word>`: a whole number, so `17 passed` is not `7 passed`."""
    return re.search(r"(?<!\d)%d %s\b" % (n, word), output) is not None


def _nested(tmp_path: pathlib.Path, name: str, extra: list[str]) -> tuple[list[str], int, str]:
    """(sentinel files that changed, rc, output) of one child pytest over the leakers and the probe, launched WITH CLAUDE_PROJECT_DIR aimed at a fresh sentinel."""
    work = tmp_path / name
    sentinel = work / "sentinel"
    for rel in SEEDED:
        source = REAL_ROOT / rel
        target = sentinel / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes() if source.is_file() else b"")
    subprocess.run(["git", "init", "-q", str(sentinel)], check=True, capture_output=True)
    before = _digest(sentinel)
    assert set(before) == set(SEEDED), "CONTROL: the sentinel was not seeded: %s" % sorted(before)

    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(sentinel)
    # The parent run's tree checks already cover this process tree; a nested one would judge the parent's writes as its own.
    env["TREE_SNAPSHOT"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-n",
        "0",
        "-o",
        "cache_dir=%s" % (work / "cache"),
        "--basetemp",
        str(work / "bt"),
        *extra,
        *(str(HERE / node) for node in (*LEAKERS, PROBE)),
    ]
    proc = subprocess.run(
        argv,
        cwd=str(REAL_ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    after = _digest(sentinel)
    changed = sorted(rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel))
    return changed, proc.returncode, proc.stdout + proc.stderr


def test_a_suite_launched_with_a_project_dir_leaves_that_project_untouched(tmp_path):
    """Run A: the root conftest loaded, both layers on. The sentinel is untouched and every case passes."""
    changed, rc, output = _nested(tmp_path, "both-layers", [])
    assert not changed, (
        "a suite launched with CLAUDE_PROJECT_DIR=<sentinel> wrote into it: %s\n%s"
        % (
            changed,
            output[-3000:],
        )
    )
    assert rc == 0, "the nested run failed (rc=%d):\n%s" % (rc, output[-4000:])
    assert _counted(output, "passed", len(LEAKERS) + 1), (
        "CONTROL: the nested run did not run every case:\n%s" % output[-2000:]
    )


def test_the_fixture_scrub_alone_keeps_the_project_untouched(tmp_path):
    """Run B: `--confcutdir` keeps the root conftest out, so the variable reaches the tests and only `wlfix.scrubbed_environ` stands between the leakers and the sentinel."""
    changed, rc, output = _nested(tmp_path, "fixture-only", ["--confcutdir", str(HERE)])
    summary = output.split("short test summary")[-1]
    assert PROBE.split("::")[1] in summary, output[-3000:]
    assert _counted(output, "failed", 1), (
        "CONTROL: with the root conftest out of the run the probe must fail, or the variable "
        "never reached the tests and this run proves nothing:\n%s" % output[-3000:]
    )
    assert rc == 1, "rc=%d:\n%s" % (rc, output[-3000:])
    assert _counted(output, "passed", len(LEAKERS)), (
        "every leaker must pass on the fixture scrub alone:\n%s" % output[-3000:]
    )
    assert not changed, (
        "with the conftest pop out of the run, the fixture alone let a write through: %s\n%s"
        % (
            changed,
            output[-3000:],
        )
    )


#: Modules allowed to read CLAUDE_PROJECT_DIR: hook code, which takes its project root from it by design, and the hook tests that set it explicitly for a hook they spawn. Anything else reading it would see it vanish under the root conftest's pop.
READERS_ROOT = ".claude/"


def harness_root_readers(registry: dict) -> list[str]:
    """Modules the python env registry records reading a `HARNESS_ROOT_ENV` variable."""
    names = set(_root_conftest_harness_env())
    return sorted(mod for mod, keys in registry.get("modules", {}).items() if names & set(keys))


def _root_conftest_harness_env() -> tuple[str, ...]:
    """`HARNESS_ROOT_ENV` as the root conftest declares it, read from its source so this test names whatever the pop removes."""
    for line in (REAL_ROOT / "conftest.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("HARNESS_ROOT_ENV = "):
            return tuple(re.findall(r'"([A-Z_]+)"', line))
    raise AssertionError("the root conftest no longer declares HARNESS_ROOT_ENV")


def test_the_conftest_pop_reaches_no_reader_outside_the_hook_tree():
    """Review finding 6351de94.4: the root conftest pops `HARNESS_ROOT_ENV` for EVERY test in the repository, `.ci` gate tests included, so no module outside `.claude/` may read it from the session environment. The python env registry (`.ci/config/python-env-registry.json`, kept complete by `check:ci-python-env-registry`) is the census of every read. Control first: a planted `.ci` reader is named."""
    planted = {
        "modules": {
            ".ci/rediacc_ci/x.py": ["CLAUDE_PROJECT_DIR"],
            ".claude/hooks/y.py": ["CLAUDE_PROJECT_DIR"],
        }
    }
    assert harness_root_readers(planted) == [".ci/rediacc_ci/x.py", ".claude/hooks/y.py"]
    registry = json.loads(
        (REAL_ROOT / ".ci" / "config" / "python-env-registry.json").read_text(encoding="utf-8")
    )
    readers = harness_root_readers(registry)
    assert readers, (
        "CONTROL: the registry records no reader at all, so it is not the census this test reads"
    )
    outside = [mod for mod in readers if not mod.startswith(READERS_ROOT)]
    assert outside == [], (
        "these modules read the harness root that the root conftest pops for every test: %s"
        % outside
    )
