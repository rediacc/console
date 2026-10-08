"""Port of `.ci/scripts/test/manual/probe-receipt-stability.sh` (42 lines): the control for the pre-push receipt's `stable` field.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.probe_receipt_stability

A tree that MOVES during a run must record `stable: false` and warn. Without this probe the field can only ever say true, which is the vacuity failure this repo gates against.

The mutation is an untracked file at the repo root, because the receipt's dirty digest hashes `git status --porcelain`, which lists untracked paths. It is created AFTER the run starts and removed only after the run ends: a persistent change, which is the case two samples can actually see. The name carries NO `.tmp` suffix, since `.gitignore` ignores `*.tmp`, so such a file never reaches `git status`, the digest never moves, and the control would report success while measuring nothing.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_probe_receipt_stability.py`).

  1. THE EXIT CODE IS THE VERDICT. The bash printed five numbers and exited with the status of its last `git status | grep -c`, so a vacuous control (plant invisible, no gate selected, no warning, `stable: true`) exited 0. Every one of those is a failure here.
  2. A RECEIPT THAT CANNOT BE READ IS REPORTED. The bash piped a missing or malformed receipt into an inline `python3 -c` and printed a traceback. The port reports the field as unreadable and fails.
  3. THE PLANT IS REMOVED ON EVERY EXIT. The bash removed it after `wait`, so an interrupted run left a `STABILITY-PROBE-*` file in the checkout and every later digest saw a dirty tree.
  4. THE CAPTURE FILE IS REMOVED. The bash left its `mktemp` file behind.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

from rediacc_ci import paths

GATE_COMMAND = (
    "npm",
    "run",
    "ci:quick",
    "--",
    "--only",
    "check:ci-docker-image-freshness",
)
SETTLE_SECONDS = 4.0
RECEIPT_REL = (".ci", "cache", "prepush-receipt.json")
PLANT_PREFIX = "STABILITY-PROBE"
SELECTED_MARK = "1 gate"
WARNING_MARK = "working tree CHANGED"
ABSENT = "FIELD ABSENT"


def plant_name(pid: int) -> str:
    return "%s-%d" % (PLANT_PREFIX, pid)


def count_marked(text: str, mark: str) -> int:
    """Lines containing `mark`, the count `grep -c` prints."""
    return sum(1 for line in text.splitlines() if mark in line)


def git_status(root: pathlib.Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
    )
    return proc.stdout


def read_stable(receipt: pathlib.Path) -> object:
    """The receipt's `stable` field, `ABSENT` when the receipt has none, or None when it cannot be read."""
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("stable", ABSENT)


def verdict(
    *, visible: int, selected: int, warned: int, stable: object, restored: int
) -> list[str]:
    """What is wrong with this probe run; empty means the control did its job."""
    problems = []
    if visible != 1:
        problems.append(
            "the plant was not visible to git status exactly once (%d), so the digest could not move"
            % visible
        )
    if selected < 1:
        problems.append("the run selected no gate, so the control was vacuous")
    if warned < 1:
        problems.append("the run printed no '%s' warning" % WARNING_MARK)
    if stable is None:
        problems.append("the receipt could not be read")
    elif stable is not False:
        problems.append("the receipt records stable=%r, expected False" % (stable,))
    if restored != 0:
        problems.append("the plant is still visible to git status after the run")
    return problems


def _run_with_plant(
    root: pathlib.Path, command: tuple[str, ...], settle: float, capture: str, out
) -> int:
    """Start the run, plant the file once it has settled, wait for the run, and return the plant's git-status count. The plant is gone on every exit."""
    plant = root / plant_name(os.getpid())
    run = None
    try:
        with open(capture, "w", encoding="utf-8") as sink:
            run = subprocess.Popen(
                command, cwd=root, stdout=sink, stderr=subprocess.STDOUT, text=True
            )
            time.sleep(settle)
            plant.write_text("", encoding="utf-8")
            stamp = time.strftime("%H:%M:%SZ", time.gmtime())
            print("planted %s at %s" % (plant.name, stamp), file=out)
            print("--- is the plant VISIBLE to git status? (must be 1) ---", file=out)
            visible = count_marked(git_status(root), PLANT_PREFIX)
            print(visible, file=out)
            run.wait()
    finally:
        if run is not None and run.poll() is None:
            run.kill()
            run.wait()
        with contextlib.suppress(FileNotFoundError):
            plant.unlink()
    return visible


def run_probe(
    root: pathlib.Path,
    command: tuple[str, ...] = GATE_COMMAND,
    settle: float = SETTLE_SECONDS,
    out=None,
) -> int:
    """Run the control against `root`; 0 when the field moved, 1 otherwise."""
    out = out or sys.stdout
    fd, capture = tempfile.mkstemp(prefix="receipt-probe-")
    os.close(fd)
    try:
        visible = _run_with_plant(root, command, settle, capture, out)
        text = pathlib.Path(capture).read_text(encoding="utf-8", errors="replace")
    finally:
        with contextlib.suppress(FileNotFoundError):
            pathlib.Path(capture).unlink()
    selected = count_marked(text, SELECTED_MARK)
    warned = count_marked(text, WARNING_MARK)
    stable = read_stable(root.joinpath(*RECEIPT_REL))
    restored = count_marked(git_status(root), PLANT_PREFIX)
    print(
        "--- did the run actually SELECT a gate? (0 here means the control was vacuous) ---",
        file=out,
    )
    print(selected, file=out)
    print("--- warning present in output? ---", file=out)
    print(warned, file=out)
    print("--- receipt ---", file=out)
    print("stable :", "FIELD UNREADABLE" if stable is None else stable, file=out)
    print("--- tree restored? (expect 0) ---", file=out)
    print(restored, file=out)
    problems = verdict(
        visible=visible, selected=selected, warned=warned, stable=stable, restored=restored
    )
    for problem in problems:
        print("FAIL: %s" % problem, file=out)
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    if argv:
        print("usage: python3 -m rediacc_ci.ops.probe_receipt_stability", file=sys.stderr)
        return 2
    return run_probe(paths.repo_root())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
