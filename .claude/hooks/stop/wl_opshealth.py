"""wl_opshealth: a red machine, probe or off-box alerter reaches an agent session, and exactly one session owns it (agent/plans/PLAN-health-checks-local.md L3, D-local).

WHAT IT READS. `.ci/cache/ops-health/state.json`, written by `python3 -m rediacc_ci.ops.ops_health refresh` (gitignored). Every check entry carries its own `at` and `ttl_s`, so the TTLs live in .ci/config/ops-health.json and the refresher, never here.

WHEN A CHECK IS DUE (its `at` older than its `ttl_s`, or no readable cache at all), ONE detached refresher is spawned, claimed through O_EXCL on `.ci/cache/ops-health/refresh.lock` (a lock older than LOCK_STALE_S is a dead refresher's and is taken over). The refresher is passed `--lock-held` and removes the lock when it ends. The hook never waits for it and never raises: the next stop reads what it wrote.

OWNERSHIP reuses wl_schedred's claim file. An open `[ ]`/`[>]`/`[?]` item whose text names `ops-health` belongs to its owner (the open-items blocker already holds that owner, and a peer gets one advisory). With no such item, `wl_schedred.claim` picks ONE session: the holder is blocked (`ops-health-red`, `ops-health-offbox-stale`) and every other session gets an advisory (`ops-health-peer`). The claim's run id is a signature of the red subjects, so a new red re-claims.

A cache that cannot be parsed, or a check that answered rc 2 (unreadable), is the advisory `ops-health-unreadable`, never a block.
"""

import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

import wl_core as C
import wl_schedred
import worklist_messages as M

CACHE_REL = pathlib.Path(".ci") / "cache" / "ops-health"
STATE_NAME = "state.json"
LOCK_NAME = "refresh.lock"
LOG_NAME = "refresh.log"
LOCK_STALE_S = 20 * 60
TRACK_WORD = "ops-health"
CLAIM_RED = "opshealth"
CLAIM_OFFBOX = "opshealth-offbox"
_OPEN_STATES = (" ", ">", "?")
_REFRESH_ARGV = ("-m", "rediacc_ci.ops.ops_health", "refresh", "--lock-held")
_ROW_LINES = 14
CLAIMED, TRACKED_HERE, PEER = "claimed", "tracked-here", "peer"


def cache_dir(root):
    return pathlib.Path(root) / CACHE_REL


def read_state(root):
    """(doc, error). (None, "") when there is no cache yet; (None, reason) when it cannot be parsed."""
    path = cache_dir(root) / STATE_NAME
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, "%s: %s" % (path, exc.strerror or exc)
    try:
        doc = json.loads(text)
    except ValueError as exc:
        return None, "%s does not parse: %s" % (path, exc)
    if not isinstance(doc, dict) or not isinstance(doc.get("checks"), dict):
        return None, "%s has no `checks` object" % path
    return doc, ""


def _when(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=datetime.UTC)


def due(doc, now):
    """True when no readable cache exists or any check is past its own TTL."""
    if not doc or not doc.get("checks"):
        return True
    for entry in doc["checks"].values():
        if not isinstance(entry, dict):
            return True
        at = _when(entry.get("at"))
        ttl = entry.get("ttl_s")
        if at is None or not isinstance(ttl, (int, float)):
            return True
        if (now - at).total_seconds() >= ttl:
            return True
    return False


def take_lock(root, now=None):
    now = time.time() if now is None else now
    d = cache_dir(root)
    with contextlib.suppress(OSError):
        d.mkdir(parents=True, exist_ok=True)
    path = d / LOCK_NAME
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age < LOCK_STALE_S:
                return False
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        except OSError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "at": now, "by": "wl_opshealth"}, fh)
        return True
    return False


def spawn_refresh(root, popen=None, now=None):
    """Take the lock and start ONE detached refresher. True when this call started it."""
    if not take_lock(root, now=now):
        return False
    popen = subprocess.Popen if popen is None else popen
    root = pathlib.Path(root)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / ".ci")
    try:
        log_fd = os.open(
            str(cache_dir(root) / LOG_NAME), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
        )
    except OSError:
        log_fd = subprocess.DEVNULL
    try:
        popen(
            [sys.executable or "python3", *_REFRESH_ARGV],
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError:
        with contextlib.suppress(OSError):
            (cache_dir(root) / LOCK_NAME).unlink()
        return False
    finally:
        if log_fd != subprocess.DEVNULL:
            with contextlib.suppress(OSError):
                os.close(log_fd)
    return True


def red_rows(doc):
    """[(subject, text)] for every red check; the off-box entry counts when it is red for a reason other than a stale cron, which has its own key."""
    out = []
    for name, entry in sorted((doc.get("checks") or {}).items()):
        if not isinstance(entry, dict) or entry.get("state") != "red":
            continue
        if name == "machines":
            for row in entry.get("rows") or []:
                if isinstance(row, dict) and row.get("state") == "red":
                    subject = "machine %s" % row.get("machine")
                    lines = ["  %s:" % subject]
                    lines += ["    - %s" % p for p in row.get("problems") or []]
                    out.append((subject, "\n".join(lines)))
            continue
        detail = str(entry.get("detail") or "")
        if name == "offbox":
            kept = [ln for ln in detail.splitlines() if "the alerter is not running" not in ln]
            if not kept:
                continue
            detail = "\n".join(kept)
        body = "\n".join("    %s" % ln for ln in detail.splitlines()[:_ROW_LINES])
        out.append((name, "  %s (rc %s):\n%s" % (name, entry.get("rc"), body)))
    return out


def unknown_rows(doc):
    out = []
    for name, entry in sorted((doc.get("checks") or {}).items()):
        if not isinstance(entry, dict):
            continue
        if entry.get("state") == "unknown":
            first = (str(entry.get("detail") or "").splitlines() or ["?"])[0]
            out.append("%s (%s)" % (name, first[:160]))
        if name == "machines":
            out.extend(
                "machine %s (%s)"
                % (row.get("machine"), "; ".join(row.get("unreadable") or [])[:160])
                for row in entry.get("rows") or []
                if isinstance(row, dict) and row.get("state") == "unknown"
            )
    return out


def signature(subjects):
    return hashlib.sha256("\n".join(sorted(subjects)).encode("utf-8")).hexdigest()[:16]


def tracking_items(items):
    return [
        it
        for it in items or ()
        if it.get("state") in _OPEN_STATES and TRACK_WORD in str(it.get("text") or "").lower()
    ]


def _owner(worklist, items, session_id, stem, run_id):
    """(CLAIMED | TRACKED_HERE | PEER, owner prefix)."""
    sid8 = (session_id or "")[:8]
    tracked = tracking_items(items)
    if tracked:
        if any(C.owned_by_me(it.get("owner"), session_id) for it in tracked):
            return TRACKED_HERE, sid8
        return PEER, str(tracked[0].get("owner") or "?")[:8]
    holder = wl_schedred.claim(worklist, stem, run_id, sid8)
    if holder and holder == sid8:
        return CLAIMED, sid8
    return PEER, holder or "?"


def assess(root, worklist, items, session_id, now=None, popen=None):
    """What this stop owes for ops health: {block, offbox_stale, peer, unreadable, spawned}. Never raises for a bad cache."""
    now = now or datetime.datetime.now(datetime.UTC)
    sid8 = (session_id or "")[:8] or "<me>"
    out = {"block": "", "offbox_stale": "", "peer": "", "unreadable": "", "spawned": False}
    doc, error = read_state(root)
    if due(doc, now):
        out["spawned"] = spawn_refresh(root, popen=popen, now=now.timestamp())
    if error:
        out["unreadable"] = M.N_OPS_HEALTH_UNREADABLE % {"what": error}
        return out
    if not doc:
        return out
    peers = []
    reds = red_rows(doc)
    if reds:
        subjects = [s for s, _t in reds]
        who, owner = _owner(worklist, items, session_id, CLAIM_RED, signature(subjects))
        if who == CLAIMED:
            out["block"] = M.V_OPS_HEALTH_RED % {
                "updated": doc.get("updated_at") or "?",
                "rows": "\n".join(t for _s, t in reds),
                "me": sid8,
                "add": "ops-health red: %s" % ", ".join(subjects),
            }
        elif who == PEER:
            peers.append(M.N_OPS_HEALTH_PEER % {"owner": owner, "subjects": ", ".join(subjects)})
    off = (doc.get("checks") or {}).get("offbox")
    if isinstance(off, dict) and off.get("stale"):
        last = off.get("last_cron_at") or "?"
        who, owner = _owner(worklist, items, session_id, CLAIM_OFFBOX, str(last))
        if who == CLAIMED:
            out["offbox_stale"] = M.V_OPS_HEALTH_OFFBOX_STALE % {
                "last": last,
                "age": off.get("cron_age_min") or "?",
                "read": off.get("read_at") or "?",
                "limit": off.get("stale_limit_min") or "?",
                "me": sid8,
                "add": "ops-health off-box alerter stopped (last cron %s)" % last,
            }
        elif who == PEER:
            peers.append(
                M.N_OPS_HEALTH_PEER % {"owner": owner, "subjects": "off-box alerter stopped"}
            )
    out["peer"] = "\n".join(peers)
    unknown = unknown_rows(doc)
    if unknown:
        out["unreadable"] = M.N_OPS_HEALTH_UNREADABLE % {"what": "; ".join(unknown)}
    return out
