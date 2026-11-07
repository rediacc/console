"""The POST to the ops-health ingest (PLAN-health-checks-local D1, design D-drift), split out of `drift_job` so the step that only posts is not judged by the check timers of the job that runs checks.

`--post <verdict.json> --source <name>` sends the verdict to the ops-health Worker (`POST /v1/ingest`, bearer OPS_HEALTH_INGEST_TOKEN). A missing or unreadable verdict file is posted as `red`, because the workflow runs this under `if: always()` and a job that died before it wrote anything must not read as silence. `--post-state <state> --detail <text>` posts without a file (the weekly fleet run's `report-schedule` job).

Exit codes: 0 posted, 1 the ingest refused or was unreachable after the retries, 2 a bad argument, a missing token or a non-https URL.

    PYTHONPATH=.ci python3 -m rediacc_ci.release.ops_health_post --post FILE --source drift
    PYTHONPATH=.ci python3 -m rediacc_ci.release.ops_health_post --post-state red --detail TEXT --source ci-weekly
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import pathlib
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from rediacc_ci import well_known

DETAIL_CHARS = 500
POST_ATTEMPTS = 3
POST_TIMEOUT_S = 20
DEFAULT_INGEST_URL = well_known.OPS_HEALTH_ORIGIN
STATES = ("green", "red", "unknown")

Connector = Callable[..., Any]


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
        print("ops_health_post: OPS_HEALTH_INGEST_TOKEN is not set", file=sys.stderr)
        return 2
    url = env.get("OPS_HEALTH_URL", "") or DEFAULT_INGEST_URL
    parts = urlsplit(url.rstrip("/") + "/v1/ingest")
    if parts.scheme != "https" or not parts.hostname:
        print(f"ops_health_post: the ingest URL must be https, got {url!r}", file=sys.stderr)
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
                print(f"ops_health_post: posted {source}={state} to {url}")
                return 0
            last = f"HTTP {status}"
            if 400 <= status < 500:
                break
        finally:
            conn.close()
        if attempt < POST_ATTEMPTS:
            sleep(2.0 * attempt)
    print(
        f"ops_health_post: the ingest POST failed after {attempt} attempt(s): {last}",
        file=sys.stderr,
    )
    return 1


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ops_health_post", description="POST a verdict to the ops-health ingest."
    )
    parser.add_argument("--post", type=pathlib.Path, help="POST this verdict file to the ingest")
    parser.add_argument("--post-state", choices=STATES, help="POST this state without a file")
    parser.add_argument("--detail", default="")
    parser.add_argument("--source", default="drift")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    connect: Connector | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not (args.post or args.post_state):
        parser.error("one of --post or --post-state is required")
    environment = os.environ if env is None else env
    now = datetime.now(UTC)
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


if __name__ == "__main__":
    raise SystemExit(main())
