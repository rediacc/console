"""The daily drift job (PLAN-health-checks-local D1, design D-drift) and its POST to the ops-health ingest.

DRIFT is a check that goes red because something outside the tree moved (an advisory, a newer release, an upstream mirror, the calendar), not because the commit is wrong. The set is COMPUTED from `nightly_tested_edge.DRIFT_GATE_IDS` (every external gate plus the audit), `CLOCK_GATE_IDS` (the clock-based plan and image lookups, where not already in the drift set), and the two steps split out of mixed ones (`SPLIT_DRIFT_STEPS`). Nothing is listed twice: the waiver that reads a drift-red run and this job share one set.

Exit codes: 0 every check green, 1 any check red (the verdict JSON names it), 2 the set could not be derived (a lock that cannot be read, or one missing a drift or clock id) or a bad argument. A set that cannot be derived runs nothing, since a smaller set that passes would read as a green.

`--post <verdict.json> --source <name>` sends the verdict to the ops-health Worker (`POST /v1/ingest`, bearer OPS_HEALTH_INGEST_TOKEN). A missing or unreadable verdict file is posted as `red`, because the workflow runs this under `if: always()` and a job that died before it wrote anything must not read as silence. `--post-state <state> --detail <text>` posts without a file (the weekly fleet run's `report-schedule` job).

    PYTHONPATH=.ci python3 -m rediacc_ci.release.drift_job [--only <name>...] [--out FILE]
    PYTHONPATH=.ci python3 -m rediacc_ci.release.drift_job --post FILE --source drift
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import pathlib
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from rediacc_ci.release import nightly_tested_edge
from rediacc_ci.release.nightly_tested_edge import (
    DRIFT_GATE_IDS,
    GATES_LOCK,
    GOVULNCHECK_STEP,
    OBS_UPSTREAM_STEP,
    DriftSetError,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# The calendar- and clock-based lookups: each answers differently tomorrow with no commit in between (a plan past its lifecycle window, an image whose upstream tag moved).
CLOCK_GATE_IDS: tuple[str, ...] = (
    "check:ci-plan-housekeeping",
    "check:ci-plan-folders",
    "check:ci-docker-image-freshness",
)

# The two split steps are not lock gates; their commands are the workflows' own.
SPLIT_COMMANDS: Mapping[str, tuple[str, ...]] = {
    OBS_UPSTREAM_STEP: (
        "python3",
        "-m",
        "rediacc_ci.infra.renet_pkg_matrix",
        "upstream",
        "--distro",
        "opensuse-16.0",
    ),
    GOVULNCHECK_STEP: ("python3", "-m", "rediacc_ci.private.run_renet", "govulncheck"),
}

CHECK_TIMEOUT_S = 25 * 60
# The whole run's budget, inside ci-drift.yml's job timeout with room for the setup steps before it and the ingest POST after it: a check is given at most what is left, and a check reached with nothing left is recorded red unrun, so the verdict file is always written before the runner kills the job.
RUN_BUDGET_S = 25 * 60
TAIL_CHARS = 2000
DETAIL_CHARS = 500
POST_ATTEMPTS = 3
POST_TIMEOUT_S = 20
DEFAULT_INGEST_URL = "https://ops-health.rediacc.com"
STATES = ("green", "red", "unknown")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Connector = Callable[..., Any]


@dataclass(frozen=True)
class Check:
    name: str
    argv: tuple[str, ...]


def drift_set(
    lock_path: pathlib.Path = GATES_LOCK, *, clock_ids: Sequence[str] = CLOCK_GATE_IDS
) -> list[Check]:
    """The checks this job runs, in order. Raises DriftSetError when the lock cannot be read or lacks a drift or clock id."""
    nightly_tested_edge.drift_steps(lock_path)  # raises when a drift id has no CI step
    entries = json.loads(lock_path.read_text(encoding="utf-8"))
    known = {str(e.get("id")) for e in entries if isinstance(e, dict)}
    missing = [gate for gate in clock_ids if gate not in known]
    if missing:
        raise DriftSetError(f"{lock_path} carries no gate for clock id(s) {', '.join(missing)}")
    ids: list[str] = []
    for gate in (*DRIFT_GATE_IDS, *clock_ids):
        if gate not in ids:
            ids.append(gate)
    checks = [Check(gate, ("npm", "run", "--silent", gate)) for gate in ids]
    checks += [Check(name, argv) for name, argv in SPLIT_COMMANDS.items()]
    return checks


def _tail(text: str) -> str:
    return text[-TAIL_CHARS:]


def run_check(check: Check, runner: Runner, timeout_s: float = CHECK_TIMEOUT_S) -> dict[str, Any]:
    started = time.monotonic()
    if timeout_s <= 0:
        return {
            "name": check.name,
            "rc": 124,
            "seconds": 0.0,
            "tail": f"not run: the run budget of {RUN_BUDGET_S} s was spent",
        }
    try:
        proc = runner(
            list(check.argv),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / ".ci")},
        )
        rc, tail = proc.returncode, _tail((proc.stdout or "") + (proc.stderr or ""))
    except subprocess.TimeoutExpired:
        rc, tail = 124, f"timed out after {round(timeout_s)} s"
    except OSError as exc:
        rc, tail = 127, f"could not start {check.argv[0]}: {exc}"
    return {
        "name": check.name,
        "rc": rc,
        "seconds": round(time.monotonic() - started, 1),
        "tail": tail,
    }


def build_verdict(results: Sequence[Mapping[str, Any]], now: datetime) -> dict[str, Any]:
    red = [str(r["name"]) for r in results if r["rc"] != 0]
    return {
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ok": not red,
        "state": "red" if red else "green",
        "detail": (", ".join(red))[:DETAIL_CHARS],
        "checks": list(results),
    }


def _post(
    *,
    source: str,
    state: str,
    detail: str,
    at: str,
    env: Mapping[str, str],
    connect: Connector,
    sleep: Callable[[float], None],
) -> int:
    token = env.get("OPS_HEALTH_INGEST_TOKEN", "")
    if not token:
        print("drift_job: OPS_HEALTH_INGEST_TOKEN is not set", file=sys.stderr)
        return 2
    url = env.get("OPS_HEALTH_URL", "") or DEFAULT_INGEST_URL
    parts = urlsplit(url.rstrip("/") + "/v1/ingest")
    if parts.scheme != "https" or not parts.hostname:
        print(f"drift_job: the ingest URL must be https, got {url!r}", file=sys.stderr)
        return 2
    body = json.dumps(
        {"source": source, "state": state, "detail": detail[:DETAIL_CHARS], "at": at}
    ).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    last = ""
    attempt = 0
    while attempt < POST_ATTEMPTS:
        attempt += 1
        conn = connect(parts.hostname, parts.port or 443, timeout=POST_TIMEOUT_S)
        try:
            conn.request("POST", parts.path, body=body, headers=headers)
            status = int(conn.getresponse().status)
        except (OSError, http.client.HTTPException) as exc:
            last = str(exc)
        else:
            if 200 <= status < 300:
                print(f"drift_job: posted {source}={state} to {url}")
                return 0
            last = f"HTTP {status}"
            if 400 <= status < 500:
                break
        finally:
            conn.close()
        if attempt < POST_ATTEMPTS:
            sleep(2.0 * attempt)
    print(f"drift_job: the ingest POST failed after {attempt} attempt(s): {last}", file=sys.stderr)
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drift_job", description="The daily drift job.")
    parser.add_argument("--lock", type=pathlib.Path, default=GATES_LOCK)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("drift-verdict.json"))
    parser.add_argument(
        "--only", action="append", default=[], help="run only this check (repeatable)"
    )
    parser.add_argument("--list", action="store_true", help="print the computed set and exit")
    parser.add_argument("--post", type=pathlib.Path, help="POST this verdict file to the ingest")
    parser.add_argument("--post-state", choices=STATES, help="POST this state without a file")
    parser.add_argument("--detail", default="")
    parser.add_argument("--source", default="drift")
    return parser


def _read_verdict(path: pathlib.Path, now: datetime) -> tuple[str, str, str]:
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        verdict = json.loads(path.read_text(encoding="utf-8"))
        state = str(verdict["state"])
        if state not in STATES:
            raise ValueError(state)
        return state, str(verdict.get("detail", "")), str(verdict["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return "red", f"no verdict was written ({path}): the job died before it finished", stamp


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner | None = None,
    env: Mapping[str, str] | None = None,
    connect: Connector | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    environment = os.environ if env is None else env
    now = datetime.now(UTC)

    if args.post or args.post_state:
        if args.post:
            state, detail, at = _read_verdict(args.post, now)
        else:
            state, detail, at = args.post_state, args.detail, now.strftime("%Y-%m-%dT%H:%M:%SZ")
        return _post(
            source=args.source,
            state=state,
            detail=detail,
            at=at,
            env=environment,
            connect=connect or http.client.HTTPSConnection,
            sleep=sleep or time.sleep,
        )

    try:
        checks = drift_set(args.lock)
    except (DriftSetError, OSError, ValueError) as exc:
        print(
            f"drift_job: the drift set cannot be derived, nothing was run: {exc}", file=sys.stderr
        )
        return 2
    if args.list:
        for check in checks:
            print(check.name)
        return 0
    if args.only:
        unknown = [name for name in args.only if name not in {c.name for c in checks}]
        if unknown:
            print(f"drift_job: not in the drift set: {', '.join(unknown)}", file=sys.stderr)
            return 2
        checks = [c for c in checks if c.name in args.only]

    run = runner or subprocess.run
    results = []
    deadline = (clock or time.monotonic)() + RUN_BUDGET_S
    for check in checks:
        left = deadline - (clock or time.monotonic)()
        result = run_check(check, run, min(CHECK_TIMEOUT_S, left))
        print(
            f"drift_job: {'ok ' if result['rc'] == 0 else 'RED'} {check.name} ({result['seconds']} s)"
        )
        if result["rc"] != 0:
            print(result["tail"], file=sys.stderr)
        results.append(result)
    verdict = build_verdict(results, now)
    args.out.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    print(f"drift_job: {verdict['state']} ({len(results)} checks), verdict in {args.out}")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
