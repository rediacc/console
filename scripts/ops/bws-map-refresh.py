#!/usr/bin/env python3
"""Regenerate .ci/config/bws-secret-map.json from the live `ci-shared` project.

WHY THIS EXISTS
  bitwarden/sm-action fetches secrets by UUID, never by name, so the workflows
  carry names and this committed map translates them. A rename in Secrets
  Manager preserves the UUID, so after a rename the map's NAME column is the
  only thing that moves -- but it has to move, or `check:ci-bws-map` fails and
  every job that requests the old name fails at run time.

WHY NO VALUE EVER ENTERS THIS FILE
  `bws secret list` returns each secret's decrypted VALUE alongside its id and
  key. This repo is public and the map is committed. So the very first thing
  done with the listing is a projection down to {id, key, projectId} -- the
  value is dropped before anything is printed, compared, or written, and it is
  never passed to a subprocess, a log line, or an exception message. The map
  holds ids only; the id is a pointer, not a credential. Nothing here prints
  the access token either: it is read from the environment by `bws` itself.

REFUSALS (a map that is wrong is worse than a map that is missing)
  - fewer than MIN_ENTRIES secrets returned: a scoped-down token or a wrong
    project id returns a short list rather than an error, and silently
    shrinking the map is how a name stops resolving.
  - any id that is not a UUID.
  - any secret outside the target project.
  - duplicate names in the listing.

USAGE
  BWS_ACCESS_TOKEN=... scripts/ops/bws-map-refresh.py [--bws /path/to/bws]
                                                      [--dry-run]
  `bws` is not installed on the host; the devcontainer has it at
  /usr/local/bin/bws (.devcontainer/Dockerfile, hash-pinned 2.1.0). Pass
  --bws to point at a copy downloaded the same way.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / ".ci" / "config" / "bws-secret-map.json"

MIN_ENTRIES = 40

# THE EXPIRY FILE IS GONE, AND SO IS EVERYTHING THAT READ IT. `warn_if_token_expiring()` lived here until 2026-09-23 and read a hand-maintained date out of `.ci/config/bws-token-expiry.json`.
# Both are deleted by `agent/plans/PLAN-bws-rotation-on-failure.md`, whose ruling is that detection is the FAILURE and never a date: nothing in this repository can observe a machine account's expiry, so a written-down date is a second source of truth that only a human ever refreshes.
#
# WHAT IS LOST, HONESTLY: up to five days' notice before the credential died, delivered by exactly one reader that a human ran by hand occasionally. It never warned CI, never warned `bws_env_load`, never warned a deploy, and no gate read it.
#
# WHAT SURVIVED THE DELETION is the client-id fingerprint, because it was the one part of that reader binding a claim to the LIVE token rather than to a written date. It now lives at `rediacc_ci.core.bws_env.client_fingerprint`, and `scripts/dev/bws-rotate.py` uses it to refuse a paste of the credential that is already installed.


def _rotation_notice(returncode: int, stderr: str) -> list[str]:
    """The rotation notice for a failed `bws`, from the ONE classifier, out of process.

    WHY A SUBPROCESS AND NOT AN IMPORT, since an import would read better. This file lives under `scripts/ops/` and there is no `_cipath` shim there; the canonical way onto `sys.path` is `import _cipath` from a sibling, or `paths.on_sys_path`, which already requires `rediacc_ci` to be importable.
    A hand-written `sys.path.insert` here would be a NEW finding against the whole-tree hop baseline in `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py`, and that baseline is shrink-only. So the classifier is REACHED rather than copied, and `check:ci-bws-rotation-notice` asserts that no second copy of the decision exists anywhere in the tree.

    THE STDERR GOES ON STDIN, never on argv: argv is visible in `ps` and in process accounting, and `bws`'s stderr is the stream most likely to echo something back.

    A FAILURE TO REACH THE CLASSIFIER IS REPORTED, not swallowed. Returning an empty list on an OSError would turn "the notice could not be produced" into "there was nothing to say", which is the shape this whole plan exists to refuse.
    """
    try:
        done = subprocess.run(
            [sys.executable, "-m", "rediacc_ci.core.bws_env", "rotation-notice", str(returncode)],
            input=stderr,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT / ".ci")},
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [
            f"!! the rotation classifier could not be run ({exc}), so this failure is",
            "   UNCLASSIFIED rather than fine. Read .ci/config/bws-rotation-notice.txt.",
        ]
    # 3 is a wiring fault and 4 is a run that did not fail at all. Neither is a rotation.
    if done.returncode != 0:
        return []
    return done.stdout.rstrip("\n").split("\n")


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bws", default=None, help="path to the bws binary (default: from PATH)")
    ap.add_argument("--dry-run", action="store_true", help="report the diff, write nothing")
    args = ap.parse_args()

    if not MAP.exists():
        die(f"{MAP} is missing; this script refreshes it, it does not invent it")
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    project = doc.get("project")
    if not project or not UUID_RE.match(str(project)):
        die("the map has no usable 'project' uuid to refresh from")

    bws = args.bws or shutil.which("bws")
    if not bws or not Path(bws).exists():
        die("bws not found; install it as .devcontainer/Dockerfile does, or pass --bws")

    # `--color no` is load-bearing: bws 2.1.0's default `--color auto` does not detect a non-tty and wraps `--output json` in truecolor ANSI escapes even when stdout is a pipe (verified 2026-09-02 against the hash-pinned 2.1.0 binary). Without it every run of this script died on the json.JSONDecodeError below -- i.e. it had never worked from a pipe, which is the only way it runs.
    proc = subprocess.run(
        [bws, "--color", "no", "secret", "list", str(project), "--output", "json"],
        capture_output=True,
        text=True,
        check=False,  # the return code is judged below, with stderr only
    )
    if proc.returncode != 0:
        # THE NOTICE COMES BEFORE THE DEATH AND ON THE SAME STREAM, which is why it is stderr and not stdout. The first version printed it to stdout and it arrived AFTER `die`'s line under a pipe: stderr is unbuffered and a piped stdout is block-buffered, so the two came out in the opposite order to the one they were written in. A procedure that appears below the exception
        # reads as trailing noise.
        for line in _rotation_notice(proc.returncode, proc.stderr or ""):
            print(line, file=sys.stderr)
        # stderr only: stdout on a partial failure could carry secret material.
        die(f"bws secret list exited {proc.returncode}: {proc.stderr.strip()}")
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        die("bws secret list did not return JSON (stdout withheld: it may carry values)")

    # PROJECTION FIRST. Everything below this line has no access to any value.
    entries = [
        {
            "id": str(s.get("id", "")),
            "key": str(s.get("key", "")),
            "projectId": str(s.get("projectId", "")),
        }
        for s in raw
    ]
    del raw, proc

    if len(entries) < MIN_ENTRIES:
        die(
            f"listing returned {len(entries)} secret(s), floor is {MIN_ENTRIES}; refusing to shrink the map"
        )
    bad = [e["key"] for e in entries if not UUID_RE.match(e["id"])]
    if bad:
        die(f"malformed id on: {', '.join(sorted(bad))}")
    foreign = [e["key"] for e in entries if e["projectId"] != project]
    if foreign:
        die(f"listing carried secrets outside project {project}: {', '.join(sorted(foreign))}")
    keys = [e["key"] for e in entries]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        die(f"duplicate secret name(s) in the listing: {', '.join(dupes)}")

    new = dict(doc)  # preserve every top-level field, in its existing order
    new["refreshed_at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    new["secrets"] = {e["key"]: {"id": e["id"]} for e in sorted(entries, key=lambda e: e["key"])}

    old_names = set(doc.get("secrets") or {})
    added = sorted(set(new["secrets"]) - old_names)
    removed = sorted(old_names - set(new["secrets"]))
    print(f"{len(new['secrets'])} secret(s) in {MAP.relative_to(ROOT)}")
    for n in removed:
        print(f"  - {n}")
    for n in added:
        print(f"  + {n}")

    text = json.dumps(new, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    MAP.write_text(text, encoding="utf-8")
    print(f"✓ wrote {MAP.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
