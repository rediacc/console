"""wl_lkg: the last-known-good Stop hook, so a half-finished edit is not every session's Stop hook (agent/plans/PLAN-stop-hook-continuity.md P2.5).

WHY. The live hook runs straight from the working tree, so a writer's mid-edit NameError blocked EVERY stop of EVERY session with a traceback until the edit landed. Failing closed on a crash is right; the defect was that no working version existed to fail TO.

HOW.
  * snapshot()  at the end of every Stop that did not crash, hash the module set (worklist.py, worklist_messages.py, wl_*.py). A new digest is copied to
                <TMPDIR>/claude-worklist/.lkg/<digest>/ and `current` points at it. One hash per stop, one copy per change.
  * fallback()  when the live tree crashes, re-run the SAME stop (the raw stdin bytes) against the snapshot, with WORKLIST_LKG_CHILD=1 as the recursion guard,
                and hand back its verdict under one prefixed line naming the crash and the snapshot. It is the full battery, so it is not an escape hatch.
                With no snapshot yet, `git archive HEAD .claude/hooks/stop` is the snapshot.

WHEN IT STEPS ASIDE and the ordinary crash block fires: the snapshot is missing and git cannot supply one, the snapshot itself fails, or the live tree has been crashing for CRASH_GIVEUP_MIN while nothing in the stop directory changed for QUIET_EDIT_MIN -- nobody is mid-edit, so the crash is the state of the tree and must be seen.

Stdlib only, deliberately: it must import when every sibling is broken.
"""

import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

CHILD_ENV = "WORKLIST_LKG_CHILD"
# The live tree may crash this long before the fallback stops covering for it, but only while nothing in the stop directory is being edited.
CRASH_GIVEUP_MIN = 30
QUIET_EDIT_MIN = 10
# The snapshot child runs the whole battery; bounded so a wedged child cannot wedge the stop.
CHILD_TIMEOUT_S = 90
STOP_REL = ".claude/hooks/stop"


def stop_dir():
    return pathlib.Path(__file__).resolve().parent


def module_set(d):
    """The files that make up the hook, sorted by name."""
    d = pathlib.Path(d)
    names = ["worklist.py", "worklist_messages.py", *sorted(p.name for p in d.glob("wl_*.py"))]
    return [d / n for n in names if (d / n).is_file()]


def digest(d):
    h = hashlib.sha1()
    for p in module_set(d):
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def lkg_root():
    return pathlib.Path(tempfile.gettempdir()) / "claude-worklist" / ".lkg"


def snapshot(d=None):
    """Record the running module set as last-known-good. Returns its digest, or "" when it could not be written. Never raises."""
    try:
        d = pathlib.Path(d) if d is not None else stop_dir()
        dg = digest(d)
        root = lkg_root()
        target = root / dg
        if not (target / "worklist.py").is_file():
            root.mkdir(parents=True, exist_ok=True)
            tmp = pathlib.Path(tempfile.mkdtemp(prefix=".tmp-", dir=str(root)))
            for p in module_set(d):
                shutil.copy2(p, tmp / p.name)
            with contextlib.suppress(OSError):
                os.replace(tmp, target)
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        ptr = root / "current"
        tmp_ptr = root / (".current-%d" % os.getpid())
        tmp_ptr.write_text(dg, encoding="utf-8")
        os.replace(tmp_ptr, ptr)
        with contextlib.suppress(OSError):
            (root / "crash-since").unlink()
        return dg
    except Exception:  # noqa: BLE001 -- a snapshot must never be the thing that fails a stop
        return ""


def current():
    """(directory, digest, age_min) of the current snapshot, or None."""
    root = lkg_root()
    try:
        dg = (root / "current").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    d = root / dg
    if not dg or not (d / "worklist.py").is_file():
        return None
    return d, dg, max(0.0, (time.time() - (root / "current").stat().st_mtime) / 60.0)


def _git_snapshot(live):
    """The stop directory as committed at HEAD, extracted beside the snapshots, or None."""
    try:
        top = subprocess.run(
            ["git", "-C", str(live), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if top.returncode != 0:
            return None
        blob = subprocess.run(
            ["git", "-C", top.stdout.strip(), "archive", "HEAD", STOP_REL],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if blob.returncode != 0 or not blob.stdout:
            return None
        out = lkg_root() / "git-head"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(blob.stdout)) as tar:
            tar.extractall(out, filter="data")
        d = out / STOP_REL
        return d if (d / "worklist.py").is_file() else None
    except Exception:  # noqa: BLE001 -- no git snapshot is an answer, not a crash
        return None


def _newest_edit_age_min(live):
    try:
        newest = max(p.stat().st_mtime for p in pathlib.Path(live).glob("*.py"))
    except (OSError, ValueError):
        return None
    return (time.time() - newest) / 60.0


def _crash_age_min():
    root = lkg_root()
    p = root / "crash-since"
    try:
        return (time.time() - float(p.read_text(encoding="utf-8").strip())) / 60.0
    except (OSError, ValueError):
        with contextlib.suppress(OSError):
            root.mkdir(parents=True, exist_ok=True)
            p.write_text(str(time.time()), encoding="utf-8")
        return 0.0


def fallback(raw, why):
    """The snapshot's verdict for the stop the live tree just crashed on, as a dict to emit, or None when the ordinary crash block must fire.

    The recursion guard is the CALLER's: worklist.py never calls this from inside a snapshot child (CHILD_ENV set), so this module reads no environment at all."""
    live = stop_dir()
    crashed_for = _crash_age_min()
    edit_age = _newest_edit_age_min(live)
    if crashed_for >= CRASH_GIVEUP_MIN and (edit_age is None or edit_age >= QUIET_EDIT_MIN):
        return None
    cur = current()
    if cur is not None:
        d, dg, age = cur
        label = "the last-known-good snapshot %s (%d min old)" % (dg[:8], int(age))
    else:
        d = _git_snapshot(live)
        if d is None:
            return None
        label = "the committed hook at HEAD (no last-known-good snapshot yet)"
    env = dict(os.environ)
    env[CHILD_ENV] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, str(d / "worklist.py")],
            input=raw if isinstance(raw, bytes) else str(raw or "").encode("utf-8"),
            capture_output=True,
            timeout=CHILD_TIMEOUT_S,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", "replace").strip()
    try:
        verdict = json.loads(text) if text else {}
    except ValueError:
        return None
    if not isinstance(verdict, dict) or "Stop hook CRASHED" in str(verdict.get("systemMessage")):
        return None
    prefix = "live hook crashed (%s); this verdict is from %s." % (why, label)
    if verdict.get("decision") == "block":
        verdict["reason"] = prefix + "\n\n" + str(verdict.get("reason") or "")
    verdict["systemMessage"] = (prefix + " " + str(verdict.get("systemMessage") or "")).strip()
    return verdict
