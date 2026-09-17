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
  BWS_ACCESS_TOKEN=... scripts/dev/bws-map-refresh.py [--bws /path/to/bws]
                                                      [--dry-run]
  `bws` is not installed on the host; the devcontainer has it at
  /usr/local/bin/bws (.devcontainer/Dockerfile, hash-pinned 2.1.0). Pass
  --bws to point at a copy downloaded the same way.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
EXPIRY = ROOT / ".ci" / "config" / "bws-token-expiry.json"


# `expires` HAS THREE STATES and this reader used to accept only one of them.
#
# It did `dt.date.fromisoformat(str(e["expires"]))` inside a try that swallows ValueError and returns, so a single non-date row silently disabled the WHOLE warning -- including
# for the other rows, which is the worst direction. That was invisible while the file held
# exactly one dated token; the 2026-09-09 split into a never-expiring local account and an
# unverified CI one is what made it reachable.
#
# Bitwarden's own default is no expiry ("When the token Expires. By default, Never." -- bitwarden.com/help/access-tokens), so `null` is the COMMON case, not an edge one, and "unknown" has to stay distinct from it: null is a claim that the token never expires, "unknown" is a record that nobody checked. Collapsing them would let an unverified CI credential read as safe forever.
NEVER = "never"
UNKNOWN = "unknown"


def _expiry_of(entry):
    """A `datetime.date`, or the NEVER / UNKNOWN sentinel. Raises on a malformed date."""
    raw = entry.get("expires")
    if raw is None:
        return NEVER
    if isinstance(raw, str) and raw.strip().lower() == UNKNOWN:
        return UNKNOWN
    return dt.date.fromisoformat(str(raw))


def _live_client_fingerprint() -> str:
    """sha256 of the CLIENT ID half of BWS_ACCESS_TOKEN, or "" when absent.

    The token's shape is `0.<client-id>.<secret>:<key>`. Only the identifier is
    hashed, and only a prefix of the digest is kept, so nothing derived from the
    secret can leave this function.
    """
    token = os.environ.get("BWS_ACCESS_TOKEN", "")
    client_id = token.split(".")[1] if token.count(".") >= 2 else ""
    if not client_id:
        return ""
    return hashlib.sha256(client_id.encode()).hexdigest()[:16]


def warn_if_token_expiring() -> None:
    """A machine-account token carries no expiry inside it, so nothing can derive
    this -- it is written down at mint time or it is discovered as an outage.

    Advisory on purpose: a hard refusal here would block the refresh on a clock
    even when the token still works, and this script has real refusals for the
    things it can actually verify. What it prevents is the failure MODE: `bws`
    answers an expired token with an opaque auth error, so without this the
    first symptom is every local command breaking at once for no stated reason.

    THE SCHEMA IS AN ARRAY because the replacement posture is a SPLIT -- a
    read-only account for .env and CI, a read-write one supplied per rotation --
    and a one-token file cannot describe the state during the swap, which is
    exactly when it is being read. One entry today; the loop is not speculative
    scaffolding, it is the shape the next mint produces.
    """
    try:
        doc = json.loads(EXPIRY.read_text(encoding="utf-8"))
        entries = doc["tokens"]
        if not isinstance(entries, list) or not entries:
            return
        tokens = [(e, _expiry_of(e)) for e in entries]
    except (OSError, ValueError, KeyError, TypeError):
        return  # absent or malformed is not this script's job to enforce

    where = EXPIRY.relative_to(ROOT)
    warn_days = int(doc.get("warn_days", 5))

    # BIND THE CLAIM TO THE TOKEN IT DESCRIBES. Every other state-changing script in scripts/dev/ derives applied-vs-pending from the live system -- apply-cf-redirect-rules.sh reads the Cloudflare ruleset, the R2 scrubs read R2, this script's own map carries refreshed_at behind a staleness gate. A hand-written date is the one shape that cannot self-check, so it gets the nearest
    # thing: a fingerprint of the token's client id. Mint a new token without updating the file and this says so, instead of the date quietly describing a token that no longer exists.
    #
    # WITH AN ARRAY THE FINGERPRINT ALSO SELECTS. When the live token matches one
    # declared entry, only that entry's date is the one in force; the others
    # describe accounts this process is not using. When it matches NONE, the file describes something else entirely and every date below is about the wrong account -- that is louder than any expiry warning, so it returns.
    fp = _live_client_fingerprint()
    declared = {str(e.get("client_id_sha256", "")) for e, _ in tokens}
    if fp:
        if fp in declared:
            tokens = [(e, d) for e, d in tokens if str(e.get("client_id_sha256", "")) == fp]
        elif any(declared - {""}):
            names = ", ".join(
                f"{e.get('name', '?')} ({e.get('client_id_sha256', '-')})" for e, _ in tokens
            )
            print(
                f"!! {where} describes {names}, but BWS_ACCESS_TOKEN is a DIFFERENT "
                f"machine account ({fp}). Every expiry date in that file is about the "
                f"wrong token."
            )
            return
        else:
            print(
                f"   (note: no entry in {where} carries a client_id_sha256; add {fp} "
                f"so a swapped token cannot go unnoticed)"
            )

    today = dt.datetime.now(dt.UTC).date()
    shouted = False
    # A row with no countdown is REPORTED, not warned about, and never sorted against a date. Silence here would be indistinguishable from "checked, and fine".
    for entry, expires in [(e, d) for e, d in tokens if not isinstance(d, dt.date)]:
        if expires is UNKNOWN:
            print(
                f"   (note: {entry.get('name', '?')} has no verified expiry in {where}; "
                f"fill it in from the web vault so a lapse cannot arrive unannounced)"
            )
    dated = sorted([(e, d) for e, d in tokens if isinstance(d, dt.date)], key=lambda t: t[1])
    for entry, expires in dated:
        left = (expires - today).days
        if left > warn_days:
            continue
        shouted = True
        name = entry.get("name", "?")
        if left < 0:
            print(
                f"!! BWS_ACCESS_TOKEN ({name}) EXPIRED {-left} day(s) ago "
                f"({expires}). An auth error below means that, not a network fault."
            )
        else:
            print(f"!! BWS_ACCESS_TOKEN ({name}) expires in {left} day(s) ({expires}).")
        print("   Only the operator can mint a replacement -- no bws verb creates or rotates")
        print(
            f"   a machine-account token. Plan: {entry.get('replacement_plan', '(none recorded)')}"
        )
    if shouted:
        print(f"   Update {where} after minting.")


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

    warn_if_token_expiring()

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
