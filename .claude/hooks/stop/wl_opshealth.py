"""wl_opshealth: a red machine, probe or off-box alerter reaches an agent session, and exactly one session owns it (agent/plans/PLAN-health-checks-local.md L3, D-local).

WHAT IT READS. `.ci/cache/ops-health/state.json`, written by `python3 -m rediacc_ci.ops.ops_health refresh` (gitignored). Every check entry carries its own `at` and `ttl_s`, so the TTLs live in .ci/config/ops-health.json and the refresher, never here.

WHEN A CHECK IS DUE (its `at` older than its `ttl_s`, or no readable cache at all), ONE detached refresher is spawned, claimed through O_EXCL on `.ci/cache/ops-health/refresh.lock` (a lock whose recorded pid is dead, or older than LOCK_STALE_S, is a dead refresher's and is taken over). The refresher is passed `--lock-held` and removes the lock when it ends. The hook never waits for it and never raises: the next stop reads what it wrote.

OWNERSHIP reuses wl_schedred's claim file. An open `[ ]`/`[>]`/`[?]` item whose text opens with `ops-health` (optionally behind a `(<hex prefix>)` tag) belongs to its owner (the open-items blocker already holds that owner, and a peer gets one advisory). With no such item, `wl_schedred.claim` picks ONE session: the holder is blocked (`ops-health-red`, `ops-health-offbox-stale`) and every other session gets an advisory (`ops-health-peer`). The claim's run id is a signature of the red subjects, so a new red re-claims.

A cache that cannot be parsed, or a check that answered rc 2 (unreadable), is the advisory `ops-health-unreadable`, never a block.
"""

import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import uuid

import wl_core as C
import wl_schedred
import worklist_messages as M

CACHE_REL = pathlib.Path(".ci") / "cache" / "ops-health"
STATE_NAME = "state.json"
LOCK_NAME = "refresh.lock"
LOG_NAME = "refresh.log"
LOCK_STALE_S = 20 * 60
# A refresher that fails leaves the cache due, so the next stop would start another one at once. One attempt per RETRY_S, whatever became of the last (review 3fe50062.3); the stamp lives in LAST_NAME.
RETRY_S = 5 * 60
LAST_NAME = "refresh.last"
GUARD_NAME = "refresh.guard"
# The handoff token rides to the refresher in this variable; it stamps only the lock that carries it (rediacc_ci.ops.ops_health.stamp_lock).
LOCK_HANDOFF_ENV = "OPS_HEALTH_LOCK_HANDOFF"
# An item TRACKS the red only when its text opens with the tag the block's `--add` line prints, optionally behind the `(<session prefix>)` tag; a task that merely mentions ops-health tracks nothing (review 3fe50062.1).
TRACK_RE = re.compile(r"^\s*(?:\([0-9a-f]{4,12}\)\s*)?ops-health(?![\w-]|\.\w)", re.IGNORECASE)
CLAIM_RED = "opshealth"
CLAIM_OFFBOX = "opshealth-offbox"
_OPEN_STATES = (" ", ">", "?")
_REFRESH_ARGV = ("-m", "rediacc_ci.ops.ops_health", "refresh", "--lock-held")
# The module _REFRESH_ARGV runs, relative to the root it is spawned for.
REFRESHER_REL = ".ci/rediacc_ci/ops/ops_health.py"
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


def _guarded(root, fn, default):
    """fn() under the flock on the guard file, or `default` when the guard cannot be opened."""
    d = cache_dir(root)
    with contextlib.suppress(OSError):
        d.mkdir(parents=True, exist_ok=True)
    try:
        guard = os.open(str(d / GUARD_NAME), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return default
    try:
        fcntl.flock(guard, fcntl.LOCK_EX)
        return fn()
    finally:
        os.close(guard)


def take_lock(root, now=None, token=None):
    """Claim the refresh lock. The stale takeover (stat, unlink, then the O_EXCL open) runs under an flock on a guard file, so two stops that both see one stale lock take it in turn: the second finds the first's fresh lock and stands down instead of deleting it (review 3fe50062.2)."""
    now = time.time() if now is None else now
    return _guarded(root, lambda: _take_lock_held(cache_dir(root) / LOCK_NAME, now, token), False)


def _proc_stat(pid):
    """(state, start ticks) from /proc/<pid>/stat, or None where there is no such file (no procfs, or no such pid)."""
    try:
        text = pathlib.Path("/proc/%d/stat" % pid).read_text(encoding="ascii", errors="replace")
    except (OSError, ValueError):
        return None
    # The command name sits in parentheses and may hold spaces; the fields after the last ")" start at field 3 (state), and field 22 is the start time.
    fields = text[text.rfind(")") + 2 :].split()
    if len(fields) < 20:
        return None
    try:
        return fields[0], int(fields[19])
    except ValueError:
        return None


def process_start(pid):
    """The process start time (clock ticks since boot), or None where procfs cannot tell."""
    stat = _proc_stat(pid)
    return stat[1] if stat else None


def pid_alive(pid, start=None):
    """True when `pid` names a running process: not a zombie, and when `start` is given, the same process that recorded it rather than a reused pid. A pid owned by another user counts as running."""
    try:
        os.kill(pid, 0)
    except PermissionError:
        pass
    except (OSError, OverflowError, ValueError):
        return False
    stat = _proc_stat(pid)
    if stat is None:
        return True
    if stat[0] == "Z":
        return False
    return start is None or stat[1] == start


def lock_record(path):
    """The lock's JSON record, or None when it cannot be read (a lock mid-write, or a foreign one)."""
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def lock_is_stale(path, now):
    """A lock whose recorded process is gone (dead, a zombie, or its pid reused by another process) is stale at once; any lock older than LOCK_STALE_S is stale. Raises OSError when the lock vanished."""
    age = now - path.stat().st_mtime
    rec = lock_record(path)
    pid = _int(rec.get("pid")) if rec else None
    if pid is not None and not pid_alive(pid, _int(rec.get("start"))):
        return True
    return age >= LOCK_STALE_S


def lock_body(pid, now, token=None, **extra):
    """The record a lock holds: the holder's pid and start time, so a reused pid is not taken for it, and the handoff token."""
    body = {"pid": pid, "start": process_start(pid), "at": now, **extra}
    if token:
        body["token"] = token
    return body


def _take_lock_held(path, now, token=None):
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            try:
                stale = lock_is_stale(path, now)
            except OSError:
                continue
            if not stale:
                return False
            with contextlib.suppress(OSError):
                path.unlink()
            continue
        except OSError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(lock_body(os.getpid(), now, token, by="wl_opshealth"), fh)
        return True
    return False


def hand_over(root, token, child, now):
    """Rewrite the lock with the refresher's pid, under the guard flock, and only while it still carries this hook's token: a refresher that already released it, or another hook that took it since, is left alone. True when handed over."""
    path = cache_dir(root) / LOCK_NAME

    def swap():
        rec = lock_record(path)
        if not rec or rec.get("token") != token:
            return False
        try:
            path.write_text(
                json.dumps(lock_body(child, now, token, by="wl_opshealth")), encoding="utf-8"
            )
        except OSError:
            return False
        return True

    return _guarded(root, swap, False)


def recent_attempt(root, now):
    """True when a refresher was started less than RETRY_S before `now`."""
    try:
        at = float(json.loads((cache_dir(root) / LAST_NAME).read_text(encoding="utf-8"))["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    # A clock stepped back puts `at` ahead of `now`: the distance either way counts, so the backoff holds across a small step (review 368858a0.1).
    return abs(now - at) < RETRY_S


def spawn_refresh(root, popen=None, now=None):
    """Take the lock and start ONE detached refresher. True when this call started it. At most one attempt per RETRY_S."""
    stamp = time.time() if now is None else now
    # The refresher runs as `-m rediacc_ci.ops.ops_health` with <root>/.ci first on its path, and writes the ledger of whichever tree that module lives in. A root without its own copy (a hook-test sandbox) would run another tree's module and write that tree's agent/ledgers/ops-health.jsonl, which is how ci:quick run 18's pytest tripwire failed 20 tests.
    if not (pathlib.Path(root) / REFRESHER_REL).is_file():
        return False
    if recent_attempt(root, stamp):
        return False
    token = uuid.uuid4().hex
    if not take_lock(root, now=now, token=token):
        return False
    with contextlib.suppress(OSError):
        (cache_dir(root) / LAST_NAME).write_text(json.dumps({"at": stamp}), encoding="utf-8")
    popen = subprocess.Popen if popen is None else popen
    root = pathlib.Path(root)
    env = dict(os.environ)
    # The operator's own PYTHONPATH stays behind the repo's (review 3fe50062.4).
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / ".ci"), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    env[LOCK_HANDOFF_ENV] = token
    try:
        log_fd = os.open(
            str(cache_dir(root) / LOG_NAME), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
        )
    except OSError:
        log_fd = subprocess.DEVNULL
    try:
        proc = popen(
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
    # The lock names this hook's pid, which exits at once; hand it to the refresher so the next stop's liveness check sees a live holder.
    child = getattr(proc, "pid", None)
    if isinstance(child, int) and child > 0:
        hand_over(root, token, child, stamp)
    return True


def repair_command(row, finding):
    """The exact `machine repair` line for one fix still due."""
    fix = finding.get("fix") or {}
    parts = ["./rdc.sh"]
    if row.get("config"):
        parts += ["--config", str(row["config"])]
    parts += ["machine", "repair", str(row.get("machine")), "--code", str(finding.get("code"))]
    if fix.get("class") == "auto-with-backup":
        parts.append("--with-backup")
    return " ".join(parts)


def machine_lines(row):
    """What the refresher repaired, what it held back, and what is left: a fix due as its command, an operator-only item as an ask."""
    lines = []
    for act in (row.get("repair") or {}).get("actions") or []:
        what = "%s %s: %s" % (act.get("code"), act.get("action"), act.get("result"))
        lines.append(M.OPS_REPAIRED_LINE % {"what": what})
    lines += [M.OPS_ADVISORY_LINE % {"what": a} for a in row.get("advisories") or []]
    for finding in row.get("findings") or []:
        fix = finding.get("fix")
        if not isinstance(fix, dict):
            continue
        klass = str(fix.get("class") or "")
        if klass == "operator-only":
            lines.append(
                M.OPS_ASK_LINE % {"code": finding.get("code"), "action": fix.get("action") or "?"}
            )
        else:
            lines.append(
                M.OPS_FIX_DUE_LINE
                % {
                    "code": finding.get("code"),
                    "klass": klass,
                    "window": M.OPS_WINDOW_NOTE if fix.get("window_only") else "",
                    "command": repair_command(row, finding),
                }
            )
    return lines


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
                    lines += machine_lines(row)
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
        if it.get("state") in _OPEN_STATES and TRACK_RE.match(str(it.get("text") or ""))
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
