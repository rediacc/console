#!/usr/bin/env python3
"""Housekeeping's gate-cost capture (.github/workflows/housekeeping.yml, job gate-costs-capture), one phase per call.

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.capture_gate_costs quick      serial ci:quick -> quick.json; fails on a hang or an unusable report
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.capture_gate_costs rotation   one third of the slow gates (run.ts --slow-rotation) -> rotation.json;
                                                                          never fails itself, writes rc=<n> to $GITHUB_OUTPUT instead
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.capture_gate_costs merge      quick.json plus rotation.json (when ROTATION_RC=0) -> gate-costs.json

PORTED FROM `.ci/scripts/ci/capture-gate-costs.sh` (784c0c80e), which is deleted: Ruling 7 (2026-09-06) admits no new bash under .ci, and the twin also leaned on `timeout(1)`, which the minimal CI image does not carry. Behaviour is the twin's, phase for phase; the one deliberate difference is that the bound is enforced here with a subprocess timeout and `os.killpg` instead of `timeout --kill-after=30s`.

THE BOUND, EXACTLY AS `timeout` DREW IT. The runner starts in its own process group; at the bound the whole group gets SIGTERM (run.ts's own handler then names the gates still running and kills their groups, scripts/ci-runner/run.ts installSignalHandlers), and SIGKILL `KILL_AFTER_S` (30 s) later if it is still alive. The phase sees 124 when SIGTERM ended it and 137 when SIGKILL had to, which are `timeout`'s own two answers, so "hung" still means rc 124 or 137.

ENV. RUNNER_TEMP, where the runner's stderr logs go (default: a fresh temporary directory). GITHUB_OUTPUT (rotation; skipped when unset). ROTATION_RC (merge). CAPTURE_NIGHT, 1-3, overrides the rotation index taken from the day of the year. QUICK_BOUND / ROTATION_BOUND override the outer bounds (12m / 32m; `timeout`'s spelling: a number with an optional s, m or h). CAPTURE_DIR is where the three .json files go (default: the current directory, which is what the workflow uploads from; a local sample points it outside the tree). CAPTURE_EXTRA_ARGS is appended to the quick run (a local `--only <ids>` sample), split on whitespace.

Local, from the repository root:

    RUNNER_TEMP=$(mktemp -d) CAPTURE_DIR=$(mktemp -d) CAPTURE_EXTRA_ARGS='--only check:ci-npmrc' \\
      PYTHONPATH=.ci python3 -m rediacc_ci.ci.capture_gate_costs quick

Every runner call streams its stderr (a start and a finish line per gate) live AND into $RUNNER_TEMP/gate-costs-<phase>.log, so a run cut short still shows the gate it was waiting on.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from rediacc_ci.ci import gate_costs

Env = dict[str, str]

RUNNER = ("npx", "tsx", "scripts/ci-runner/run.ts")
RUNNER_TAIL = ("--jobs", "1", "--sched", "slots", "--json")
KILL_AFTER_S = 30.0
DEFAULT_QUICK_BOUND = "12m"
DEFAULT_ROTATION_BOUND = "32m"
# THREE, because the repository keeps artifacts 3 days (.ci/config/actions-retention.json, 2026-10-07), so gate_costs never sees more than 3 captures: every slow gate must fall inside 3 nights.
ROTATION_PARTS = 3
# 600 s per gate: a 1-core grant can stretch a parallel suite past its CI step p90, and the kill names it rather than eating the night.
ROTATION_GATE_TIMEOUT_S = 600
TIMED_OUT_TERM = 124
TIMED_OUT_KILL = 137
USAGE = "usage: capture_gate_costs quick|rotation|merge"

_BOUND_RE = re.compile(r"^(\d+(?:\.\d+)?)([smh]?)$")
_UNIT_S = {"": 1, "s": 1, "m": 60, "h": 3600}


def parse_bound(text: str) -> float:
    """`timeout(1)`'s duration spelling, in seconds: `12m`, `30s`, `1h`, or a bare number of seconds. Raises ValueError on anything else, so a mistyped override is a refusal, not an unbounded run."""
    m = _BOUND_RE.match(text.strip())
    if m is None or float(m.group(1)) <= 0:
        raise ValueError("not a positive duration: %r (use e.g. 12m, 30s, 1h)" % text)
    return float(m.group(1)) * _UNIT_S[m.group(2)]


def hung(rc: int) -> bool:
    return rc in (TIMED_OUT_TERM, TIMED_OUT_KILL)


def rotation_night(env: Env, now: datetime | None = None) -> int:
    """CAPTURE_NIGHT when set, else the UTC day of the year modulo 3, plus one: `10#$(date -u +%j) % 3 + 1`."""
    override = env.get("CAPTURE_NIGHT")
    if override:
        return int(override)
    day = int((now or datetime.now(UTC)).strftime("%j"))
    return day % ROTATION_PARTS + 1


def _tee(src: IO[bytes], log_path: Path) -> None:
    with log_path.open("wb") as log:
        for chunk in iter(src.readline, b""):
            log.write(chunk)
            log.flush()
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()


def run_bounded(
    bound_s: float,
    out: Path,
    log_path: Path,
    args: Sequence[str],
    *,
    runner: Sequence[str] = RUNNER,
    kill_after_s: float = KILL_AFTER_S,
) -> int:
    """The runner's exit status, never raises for one: stdout to `out`, stderr live and into `log_path`. At `bound_s` the runner's process group gets SIGTERM, then SIGKILL `kill_after_s` later; 124 or 137 then, as `timeout --kill-after` answers."""
    argv = [*runner, *args, *RUNNER_TAIL]
    with out.open("wb") as stdout:
        try:
            child = subprocess.Popen(
                argv, stdout=stdout, stderr=subprocess.PIPE, start_new_session=True
            )
        except OSError as exc:
            print("cannot start %s: %s" % (argv[0], exc), file=sys.stderr)
            return 127
        stderr = child.stderr
        if stderr is None:  # pragma: no cover - stderr=PIPE always yields one
            raise RuntimeError("subprocess gave no stderr pipe")
        tee = threading.Thread(target=_tee, args=(stderr, log_path), daemon=True)
        tee.start()
        timed_out: int | None = None
        try:
            child.wait(timeout=bound_s)
        except subprocess.TimeoutExpired:
            timed_out = TIMED_OUT_TERM
            _signal_group(child, signal.SIGTERM)
            try:
                child.wait(timeout=kill_after_s)
            except subprocess.TimeoutExpired:
                timed_out = TIMED_OUT_KILL
                _signal_group(child, signal.SIGKILL)
                child.wait()
        # A daemon that left the group may still hold the pipe; the log keeps what arrived.
        tee.join(timeout=5)
        if not tee.is_alive():
            stderr.close()
    if timed_out is not None:
        return timed_out
    rc = child.returncode
    return 128 - rc if rc < 0 else rc


def _signal_group(child: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, sig)


def _out_dir(env: Env) -> Path:
    return Path(env.get("CAPTURE_DIR") or ".")


def _log_dir(env: Env) -> Path:
    return Path(env.get("RUNNER_TEMP") or tempfile.mkdtemp(prefix="gate-costs-"))


def phase_quick(env: Env, **run_kw: Any) -> int:
    bound = env.get("QUICK_BOUND") or DEFAULT_QUICK_BOUND
    out = _out_dir(env) / "quick.json"
    extra = (env.get("CAPTURE_EXTRA_ARGS") or "").split()
    rc = run_bounded(
        parse_bound(bound),
        out,
        _log_dir(env) / "gate-costs-quick.log",
        ["--quick", *extra],
        **run_kw,
    )
    if hung(rc):
        print(
            "::error title=Gate cost capture hung::the serial ci:quick outlived its %s bound "
            "(exit %d); the gates still running are named on the 'ci-runner: received SIGTERM' "
            "line above" % (bound, rc)
        )
        return 1
    print(
        "run.ts exit %d (gate reds are expected on this checkout and do not fail the capture)" % rc
    )
    return gate_costs.validate_capture(out)


def phase_rotation(env: Env, **run_kw: Any) -> int:
    bound = env.get("ROTATION_BOUND") or DEFAULT_ROTATION_BOUND
    out = _out_dir(env) / "rotation.json"
    try:
        bound_s = parse_bound(bound)
        night = rotation_night(env)
    except ValueError as exc:
        # Never fails itself: the verdict rides `rc`, so the quick capture still uploads.
        print("::error::capture_gate_costs rotation: %s" % exc)
        _write_rc(env, 1)
        return 0
    print("slow rotation %d/%d" % (night, ROTATION_PARTS))
    rc = run_bounded(
        bound_s,
        out,
        _log_dir(env) / "gate-costs-rotation.log",
        [
            "--slow-rotation",
            "%d/%d" % (night, ROTATION_PARTS),
            "--gate-timeout",
            str(ROTATION_GATE_TIMEOUT_S),
        ],
        **run_kw,
    )
    if hung(rc):
        print(
            "::error title=Slow-gate rotation hung::run.ts --slow-rotation %d/%d outlived its %s "
            "bound (exit %d); the gates still running are named on the 'ci-runner: received "
            "SIGTERM' line above" % (night, ROTATION_PARTS, bound, rc)
        )
    else:
        print("run.ts exit %d (gate reds are expected on this checkout)" % rc)
        rc = gate_costs.validate_capture(out)
    _write_rc(env, rc)
    return 0


def _write_rc(env: Env, rc: int) -> None:
    output = env.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write("rc=%d\n" % rc)


def merge_captures(quick: dict[str, Any], rotation: dict[str, Any]) -> dict[str, Any]:
    """The quick capture plus every rotation gate it does not already hold. A prerequisite both runs ran is kept once, from the quick run; `slowRotation` records what the rotation selected and ran."""
    have = {g.get("id") for g in quick.get("gates") or []}
    added = [g for g in rotation.get("gates") or [] if g.get("id") not in have]
    merged = dict(quick)
    merged["gates"] = list(quick.get("gates") or []) + added
    merged["slowRotation"] = {
        "selection": rotation.get("selection"),
        "gates": [g.get("id") for g in rotation.get("gates") or []],
    }
    return merged


def phase_merge(env: Env) -> int:
    out = _out_dir(env)
    target = out / "gate-costs.json"
    rotation_rc = env.get("ROTATION_RC") or ""
    if rotation_rc == "0":
        try:
            quick = json.loads((out / "quick.json").read_text(encoding="utf-8"))
            rotation = json.loads((out / "rotation.json").read_text(encoding="utf-8"))
            merged = merge_captures(quick, rotation)
        except (OSError, ValueError, AttributeError) as exc:
            print("::error::capture_gate_costs: cannot merge the two captures: %s" % exc)
            return 1
        target.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    else:
        print(
            "::warning::the slow rotation produced no usable capture (rc '%s'); uploading the "
            "quick capture alone" % rotation_rc
        )
        try:
            shutil.copyfile(out / "quick.json", target)
        except OSError as exc:
            print("::error::capture_gate_costs: no quick capture to upload: %s" % exc)
            return 1
    return gate_costs.validate_capture(target)


def read_env() -> Env:
    """Every variable a phase reads, each named in a literal `os.environ.get` so check:ci-env-manifest sees the read (the phases take this mapping, which keeps them testable without patching os.environ)."""
    found = {
        "RUNNER_TEMP": os.environ.get("RUNNER_TEMP"),
        "GITHUB_OUTPUT": os.environ.get("GITHUB_OUTPUT"),
        "CAPTURE_DIR": os.environ.get("CAPTURE_DIR"),
        "CAPTURE_NIGHT": os.environ.get("CAPTURE_NIGHT"),
        "CAPTURE_EXTRA_ARGS": os.environ.get("CAPTURE_EXTRA_ARGS"),
        "QUICK_BOUND": os.environ.get("QUICK_BOUND"),
        "ROTATION_BOUND": os.environ.get("ROTATION_BOUND"),
        "ROTATION_RC": os.environ.get("ROTATION_RC"),
    }
    return {k: v for k, v in found.items() if v is not None}


def main(argv: Sequence[str]) -> int:
    phase = argv[0] if len(argv) == 1 else ""
    env = read_env()
    try:
        if phase == "quick":
            return phase_quick(env)
        if phase == "rotation":
            return phase_rotation(env)
        if phase == "merge":
            return phase_merge(env)
    except ValueError as exc:
        print("::error::capture_gate_costs %s: %s" % (phase, exc))
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
