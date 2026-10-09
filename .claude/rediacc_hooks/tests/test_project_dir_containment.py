"""No test writes the project `CLAUDE_PROJECT_DIR` names, whatever the launching environment says (worklist #04a74a81).

THE DEFECT. Claude Code exports `CLAUDE_PROJECT_DIR`, and `wl_core.project_start` takes it as the project root ahead of every other rung. `wlfix.Fixture.python` pinned its fixture root with `setdefault` on an environment that still carried the inherited value, so a suite launched from a live session sent `--queue-set`, `--hint-propose` and the retro verbs to the REAL checkout. Measured
2026-10-09 in a scratch clone: `agent/plans/QUEUE.md`'s settings block came back as `turbo: on -- operator test` / `batch_size: 4`, two `agent/ledgers/*.jsonl` gained rows, and 201 hook tests failed. Unset, the same run was clean, which is why CI never saw it.

THE CONTROL IS A NESTED RUN, because the outer run cannot be its own witness: the root conftest drops the variable before this module is imported, so in-process it is absent whether or not the scrub works. The child pytest is launched WITH the variable aimed at a sentinel tree (a git repo holding copies of the files the leak rewrote) and runs (a) tests measured writing through the leak and (b) the probe
below, which only the child can make non-vacuous. The sentinel must come back byte-identical and the child must pass.

THE PLANT, run when this landed: with `HARNESS_ROOT_ENV`'s pop removed from the root conftest the probe fails in the child; with the `wlfix.scrubbed_environ` entry removed as well, the sentinel's QUEUE.md and both ledgers change too.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys

REAL_ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
TIMEOUT = 600

#: One test per write the leak was measured making: QUEUE.md's settings block, hint-proposals.jsonl, stop-hook-retros.jsonl.
LEAKERS = (
    "test_wl_queue_settings.py::test_queue_set_writes_atomically_prints_git_add_and_never_commits",
    "test_wl_hints.py::test_hint_propose_cli_round_trip_via_worklist",
    "test_wl_retro.py::test_r13_retro_brief_prints_the_id_and_the_previous_range_end",
    "test_wl_retro.py::test_r13_a_leased_item_writes_the_dispatched_row_once",
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


def test_a_suite_launched_with_a_project_dir_leaves_that_project_untouched(tmp_path):
    sentinel = tmp_path / "sentinel"
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
        "cache_dir=%s" % (tmp_path / "cache"),
        "--basetemp",
        str(tmp_path / "bt"),
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
    output = proc.stdout + proc.stderr
    after = _digest(sentinel)
    changed = sorted(rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel))
    assert not changed, (
        "a suite launched with CLAUDE_PROJECT_DIR=<sentinel> wrote into it: %s\n%s"
        % (changed, output[-3000:])
    )
    assert proc.returncode == 0, "the nested run failed (rc=%d):\n%s" % (
        proc.returncode,
        output[-4000:],
    )
    assert "%d passed" % (len(LEAKERS) + 1) in output, (
        "CONTROL: the nested run did not run every case:\n%s" % output[-2000:]
    )
