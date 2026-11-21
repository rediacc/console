#!/usr/bin/env python3
"""Controls for wl_opshealth, the Stop hook's ops-health check (agent/plans/PLAN-health-checks-local.md L3, D-local).

    python3 .claude/hooks/stop/test-opshealth.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/).

Every fixture is a temporary root holding `.ci/cache/ops-health/state.json` and a temporary worklist path for the claim files. The refresher is never started: `popen` is a recorder, so a control counts spawns instead of processes. Each refusal has a passing twin built from the same fixture with one fact changed.
"""

import atexit
import datetime
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time

import wl_opshealth as O

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"


def _by_file(name):
    """A `.ci/rediacc_ci` module loaded BY FILE, not through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those)."""
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
T = controls.Controls("opshealth", floor=33)
check = T.check

NOW = datetime.datetime(2026, 11, 6, 12, 0, tzinfo=datetime.UTC)
A = "aaaa1111-0000-0000-0000-000000000000"
B = "bbbb2222-0000-0000-0000-000000000000"


def iso(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def entry(state="green", rc=0, age_min=1, ttl_s=1800, **extra):
    return {
        "state": state,
        "rc": rc,
        "at": iso(NOW - datetime.timedelta(minutes=age_min)),
        "ttl_s": ttl_s,
        "detail": extra.pop("detail", state),
        **extra,
    }


def green_doc():
    return {
        "updated_at": iso(NOW),
        "checks": {
            "machines": entry(rows=[{"machine": "m1", "state": "green", "problems": []}]),
            "telemetry": entry(ttl_s=21600),
            "portal-captcha": entry(ttl_s=21600),
            "cf-usage": entry(ttl_s=604800),
            "offbox": entry(ttl_s=900, stale=False, last_cron_at=iso(NOW)),
        },
    }


def red_doc():
    doc = green_doc()
    doc["checks"]["machines"] = entry(
        "red",
        1,
        rows=[
            {
                "machine": "m1",
                "state": "red",
                "problems": ["machine health rc 1: datastore 86%"],
            }
        ],
    )
    return doc


class Spawns:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, argv, **kw):
        with self.lock:
            self.calls.append((argv, kw))


def fixture(doc=None, raw=None):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="opshealth-"))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    d = tmp / ".ci" / "cache" / "ops-health"
    d.mkdir(parents=True)
    # The refresher module spawn_refresh requires in the root it spawns for (an empty stand-in: popen is a recorder).
    (tmp / O.REFRESHER_REL).parent.mkdir(parents=True)
    (tmp / O.REFRESHER_REL).write_text("")
    if raw is not None:
        (d / "state.json").write_text(raw)
    elif doc is not None:
        (d / "state.json").write_text(json.dumps(doc))
    return tmp, tmp / "worklist.md"


def assess(root, wl, sid, items=(), popen=None, now=NOW):
    return O.assess(root, wl, list(items), sid, now=now, popen=popen or Spawns())


# --- a red cache: the claimant is blocked, a peer is advised
root, wl = fixture(red_doc())
a = assess(root, wl, A)
check("red: the first session claims and is blocked", bool(a["block"]), True)
check("red: the block names the machine and its problem", "datastore 86%" in a["block"], True)
check(
    "red: the block carries the --add line for this session",
    "--add aaaa1111 'ops-health red: machine m1'" in a["block"],
    True,
)
check("red: the claimant gets no peer advisory", a["peer"], "")
b = assess(root, wl, B)
check("red: a peer is not blocked", b["block"], "")
check(
    "red: a peer gets the advisory naming the owner", "owned by session aaaa1111" in b["peer"], True
)
check("red: a fresh cache spawns no refresher", a["spawned"] or b["spawned"], False)

# --- a green twin: nothing
root, wl = fixture(green_doc())
g = assess(root, wl, A)
check("green: no block", g["block"], "")
check("green: no advisory", (g["peer"], g["unreadable"], g["offbox_stale"]), ("", "", ""))

# --- tracking items own the red
root, wl = fixture(red_doc())
mine = [{"state": " ", "owner": "aaaa1111", "text": "ops-health red: machine m1"}]
t = assess(root, wl, A, items=mine)
check("tracked by this session: the open-items blocker holds it, no second block", t["block"], "")
check("tracked by this session: no peer advisory", t["peer"], "")
t2 = assess(root, wl, B, items=mine)
check("tracked by a peer: this session gets the advisory", "aaaa1111" in t2["peer"], True)
closed = [{"state": "x", "owner": "aaaa1111", "text": "ops-health red: machine m1"}]
check(
    "a ticked item tracks nothing: the claim blocks again",
    bool(assess(root, wl, A, items=closed)["block"]),
    True,
)

# --- a stale cache spawns ONE refresher, and a second stop spawns none
root, wl = fixture(
    dict(green_doc(), checks=dict(green_doc()["checks"], machines=entry(age_min=31)))
)
sp = Spawns()
s1 = assess(root, wl, A, popen=sp)
s2 = assess(root, wl, B, popen=sp)
check("stale: the first stop spawns the refresher", s1["spawned"], True)
check("stale: the second stop finds the lock and spawns none", s2["spawned"], False)
check("stale: exactly one spawn recorded", len(sp.calls), 1)

# A root without its own refresher module (a hook-test sandbox) spawns nothing, since the refresher would write another tree's ledger.
bare_root, bare_wl = fixture(
    dict(green_doc(), checks=dict(green_doc()["checks"], machines=entry(age_min=31)))
)
(bare_root / O.REFRESHER_REL).unlink()
bare_sp = Spawns()
check(
    "no refresher module: a stale cache spawns nothing",
    assess(bare_root, bare_wl, A, popen=bare_sp)["spawned"],
    False,
)
check("no refresher module: nothing recorded", len(bare_sp.calls), 0)
argv, kw = sp.calls[0]
check(
    "stale: the refresher is `ops_health refresh --lock-held`",
    argv[1:],
    ["-m", "rediacc_ci.ops.ops_health", "refresh", "--lock-held"],
)
check("stale: the refresher is detached", kw.get("start_new_session"), True)
check(
    "stale: the refresher gets PYTHONPATH=.ci first",
    kw["env"]["PYTHONPATH"].split(os.pathsep)[0],
    str(root / ".ci"),
)
# Review 3fe50062.4: an operator PYTHONPATH is kept behind the repo's.
_saved = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = "/operator/libs"
try:
    root_p, wl_p = fixture(None)
    sp_p = Spawns()
    assess(root_p, wl_p, A, popen=sp_p)
    check(
        "stale: an operator PYTHONPATH is kept",
        sp_p.calls[0][1]["env"]["PYTHONPATH"],
        "%s%s/operator/libs" % (root_p / ".ci", os.pathsep),
    )
finally:
    if _saved is None:
        del os.environ["PYTHONPATH"]
    else:
        os.environ["PYTHONPATH"] = _saved

# --- two concurrent stops spawn one
root, wl = fixture(None)
sp = Spawns()
barrier = threading.Barrier(4)
results: list[bool] = []


def stop(sid):
    barrier.wait()
    results.append(assess(root, wl, sid, popen=sp)["spawned"])


threads = [threading.Thread(target=stop, args=(s,)) for s in (A, B, A, B)]
for th in threads:
    th.start()
for th in threads:
    th.join()
check(
    "concurrent: four stops with no cache spawn exactly one refresher",
    (len(sp.calls), results.count(True)),
    (1, 1),
)

# --- a dead refresher's lock is taken over after 20 minutes
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
check("stale lock: the lock file exists", lock.exists(), True)
old = NOW.timestamp() - O.LOCK_STALE_S - 5
os.utime(lock, (old, old))
sp2 = Spawns()
# One attempt per RETRY_S: this stop is past the backoff of the spawn above (review 3fe50062.3).
check(
    "stale lock: a lock older than 20 min is taken over",
    assess(root, wl, A, popen=sp2, now=NOW + datetime.timedelta(seconds=O.RETRY_S + 1))["spawned"],
    True,
)
young = NOW.timestamp() - O.LOCK_STALE_S + 60
os.utime(lock, (young, young))
check(
    "stale lock twin: a 19 min lock is respected",
    assess(root, wl, A, popen=Spawns())["spawned"],
    False,
)

# --- a refresher that fails leaves the cache due: one attempt per RETRY_S (review 3fe50062.3)
root, wl = fixture(None)
check("backoff: the first stop spawns", assess(root, wl, A)["spawned"], True)
(root / ".ci" / "cache" / "ops-health" / "refresh.lock").unlink()  # the failed refresher's cleanup
check(
    "backoff: a stop a minute later spawns nothing",
    assess(root, wl, A, now=NOW + datetime.timedelta(seconds=60))["spawned"],
    False,
)
check(
    "backoff twin: a stop past RETRY_S spawns again",
    assess(root, wl, A, now=NOW + datetime.timedelta(seconds=O.RETRY_S + 1))["spawned"],
    True,
)

# --- a clock stepped back inside RETRY_S keeps the backoff (review 368858a0.1)
root, wl = fixture(None)
check("clock step: the first stop spawns", assess(root, wl, A)["spawned"], True)
(root / ".ci" / "cache" / "ops-health" / "refresh.lock").unlink()
check(
    "clock step: a stop 60 s BEFORE the stamp spawns nothing",
    assess(root, wl, A, now=NOW - datetime.timedelta(seconds=60))["spawned"],
    False,
)

# --- many stops that all see one stale lock spawn one refresher (review 3fe50062.2)
root, wl = fixture(None)
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
lock.write_text("{}")
old = NOW.timestamp() - O.LOCK_STALE_S - 5
os.utime(lock, (old, old))
sp = Spawns()
barrier = threading.Barrier(8)
results = []


def stale_stop():
    barrier.wait()
    results.append(O.take_lock(root, now=NOW.timestamp()))


threads = [threading.Thread(target=stale_stop) for _ in range(8)]
for th in threads:
    th.start()
for th in threads:
    th.join()
check("stale race: eight stops over one stale lock take it once", results.count(True), 1)

# --- an unrelated open task that mentions ops-health tracks nothing (review 3fe50062.1)
root, wl = fixture(red_doc())
chatter = [{"state": " ", "owner": "bbbb2222", "text": "tidy the ops-health docs"}]
check(
    "tracking: an unrelated mention does not own the red",
    bool(assess(root, wl, A, items=chatter)["block"]),
    True,
)
for word in ("ops-health-docs cleanup", "ops-health.md tidy"):
    check(
        "tracking: %r is another word, not the tag" % word,
        O.TRACK_RE.match(word) is None,
        True,
    )
check("tracking twin: the tag then a colon", O.TRACK_RE.match("ops-health: red") is not None, True)
check("tracking twin: the tag then a period", O.TRACK_RE.match("ops-health. red") is not None, True)
tagged = [{"state": " ", "owner": "aaaa1111", "text": "(aaaa1111) ops-health red: machine m1"}]
root, wl = fixture(red_doc())
check(
    "tracking twin: a tagged tracking item still owns it",
    assess(root, wl, A, items=tagged)["block"],
    "",
)

# --- the off-box alerter stopped
doc = green_doc()
doc["checks"]["offbox"] = entry(
    "red",
    1,
    ttl_s=900,
    stale=True,
    last_cron_at=iso(NOW - datetime.timedelta(minutes=31)),
    cron_age_min=31.0,
    stale_limit_min=30.0,
    read_at=iso(NOW),
    detail="last_cron_at x is 31 min old (limit 30): the alerter is not running",
)
root, wl = fixture(doc)
o = assess(root, wl, A)
check(
    "offbox stale: the claimant gets ops-health-offbox-stale",
    "ALERTER STOPPED" in o["offbox_stale"],
    True,
)
check("offbox stale: the age is named", "31.0 min" in o["offbox_stale"], True)
check("offbox stale: it is not also a red row", o["block"], "")
check(
    "offbox stale: a peer gets the advisory",
    "off-box alerter stopped" in assess(root, wl, B)["peer"],
    True,
)
doc["checks"]["offbox"]["stale"] = False
doc["checks"]["offbox"]["state"] = "green"
root, wl = fixture(doc)
check("offbox twin: a 29 min cron is not stale", assess(root, wl, A)["offbox_stale"], "")

# --- a cache that cannot be parsed: advisory, no raise, a refresh is spawned
root, wl = fixture(raw="{not json")
sp = Spawns()
u = assess(root, wl, A, popen=sp)
check("unparseable: advisory names the cache", "does not parse" in u["unreadable"], True)
check("unparseable: no block", (u["block"], u["offbox_stale"]), ("", ""))
check("unparseable: a refresh is spawned to rewrite it", len(sp.calls), 1)

# --- an unreadable check (rc 2) is an advisory, not a block
doc = green_doc()
doc["checks"]["telemetry"] = entry(
    "unknown", 2, ttl_s=21600, detail="bws profile telemetry-probe: no token"
)
root, wl = fixture(doc)
k = assess(root, wl, A)
check(
    "unknown: advisory names the check and its reason",
    "telemetry (bws profile telemetry-probe: no token)" in k["unreadable"],
    True,
)
check("unknown: no block", k["block"], "")


# --- L7: what is left after the refresher's auto-repair
def repair_doc(row_extra):
    doc = green_doc()
    doc["checks"]["machines"] = entry(
        "red",
        1,
        rows=[
            {
                "config": "eu-remote",
                "machine": "m1",
                "state": "red",
                "problems": ["machine health rc 1: backup.coverage.absent"],
                **row_extra,
            }
        ],
    )
    return doc


def fnd(code, klass, action, window=False):
    return {
        "code": code,
        "fix": {"action": action, "class": klass, "window_only": window},
    }


root, wl = fixture(
    repair_doc(
        {
            "findings": [
                fnd("backup.coverage.absent", "operator-only", "bind a backup strategy"),
                fnd("renet.binary.replaced", "auto-safe", "restart-services", window=True),
                fnd("container.restart-loop", "auto-safe", "restart"),
            ],
            "repair": {
                "actions": [{"code": "datastore.usage.high", "action": "trim", "result": "fixed"}]
            },
            "advisories": ["repair of container.restart-loop skipped: 3 attempts today (limit 3)"],
        }
    )
)
blk = assess(root, wl, A)["block"]
check(
    "repair: an operator-only item is an ask with its action",
    "ASK the operator (backup.coverage.absent, operator-only): bind a backup strategy" in blk,
    True,
)
check(
    "repair: an operator-only item has no repair command",
    "machine repair m1 --code backup.coverage.absent" in blk,
    False,
)
check(
    "repair: a fix still due lists the exact repair command with its config",
    "./rdc.sh --config eu-remote machine repair m1 --code container.restart-loop" in blk,
    True,
)
check(
    "repair: a window-only fix says so",
    "renet.binary.replaced, auto-safe, inside the maintenance window only" in blk,
    True,
)
check(
    "repair: what was repaired is listed", "repaired: datastore.usage.high trim: fixed" in blk, True
)
check("repair: the attempt-limit advisory is listed", "advisory: repair of container" in blk, True)
root, wl = fixture(repair_doc({"findings": [fnd("a.b", "auto-safe", "x")]}))
check(
    "repair: no ASK line when the row holds no operator-only finding",
    "ASK the operator" in assess(root, wl, A)["block"],
    False,
)

# --- a lock whose recorded pid is dead is taken over at once; a live holder's is not (hostinger runner D-c)
_gone = subprocess.Popen(["true"])
_gone.wait()
root, wl = fixture(None)
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
lock.write_text(json.dumps({"pid": _gone.pid, "at": NOW.timestamp()}))
os.utime(lock, (NOW.timestamp(), NOW.timestamp()))
check(
    "dead holder: a fresh lock of a dead pid is taken over",
    O.take_lock(root, now=NOW.timestamp() + 1),
    True,
)
root, wl = fixture(None)
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
lock.write_text(json.dumps({"pid": os.getpid(), "at": NOW.timestamp()}))
os.utime(lock, (NOW.timestamp(), NOW.timestamp()))
check(
    "dead holder twin: a fresh lock of a live pid holds",
    O.take_lock(root, now=NOW.timestamp() + 1),
    False,
)


# --- the handoff names the refresher, a process distinct from this one (review 7acdec1f.1)
_sleeper = subprocess.Popen(["sleep", "30"])
atexit.register(_sleeper.kill)
_seen_env: dict[str, str] = {}


def _child_popen(_argv, **kw):
    _seen_env.update(kw.get("env") or {})
    return _sleeper


root, wl = fixture(None)
O.spawn_refresh(root, popen=_child_popen, now=NOW.timestamp())
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
held = json.loads(lock.read_text())
check("spawn: the lock names the refresher's pid, not the hook's", held["pid"], _sleeper.pid)
check("spawn twin: the refresher is not this process", held["pid"] != os.getpid(), True)
check(
    "spawn: the lock records the refresher's start time",
    held["start"],
    O.process_start(_sleeper.pid),
)
check(
    "spawn: the refresher is passed the lock's handoff token",
    _seen_env.get(O.LOCK_HANDOFF_ENV) == held["token"] and bool(held["token"]),
    True,
)

# --- the handoff never rewrites a lock it no longer holds (review 7acdec1f.2)
root, wl = fixture(None)
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
foreign = {"pid": os.getpid(), "at": NOW.timestamp(), "token": "other-hook"}


def _taken_meanwhile(_argv, **_kw):
    lock.write_text(json.dumps(foreign))
    return _sleeper


O.spawn_refresh(root, popen=_taken_meanwhile, now=NOW.timestamp())
check("handoff: another hook's lock is left as it is", json.loads(lock.read_text()), foreign)


def _released_meanwhile(_argv, **_kw):
    lock.unlink()
    return _sleeper


root, wl = fixture(None)
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
O.spawn_refresh(root, popen=_released_meanwhile, now=NOW.timestamp())
check("handoff: a lock the refresher already released is not planted again", lock.exists(), False)

# --- a zombie or a reused pid is not a live holder (review 7acdec1f.4)
_zombie = subprocess.Popen(["true"])
for _ in range(200):
    if (O._proc_stat(_zombie.pid) or ("?",))[0] == "Z":
        break
    time.sleep(0.01)
check("zombie: an exited, unreaped child is not alive", O.pid_alive(_zombie.pid), False)
_zombie.wait()
check("zombie twin: a running process is alive", O.pid_alive(_sleeper.pid), True)
_start = O.process_start(_sleeper.pid)
check(
    "reused pid: a different start time is not the recorded holder",
    O.pid_alive(_sleeper.pid, _start + 1),
    False,
)
check("reused pid twin: the recorded start time is", O.pid_alive(_sleeper.pid, _start), True)
root, wl = fixture(None)
lock = root / ".ci" / "cache" / "ops-health" / "refresh.lock"
lock.write_text(json.dumps({"pid": _sleeper.pid, "start": _start + 1, "at": NOW.timestamp()}))
os.utime(lock, (NOW.timestamp(), NOW.timestamp()))
check(
    "reused pid: a fresh lock of a reused pid is taken over",
    O.take_lock(root, now=NOW.timestamp() + 1),
    True,
)

T.exit()
