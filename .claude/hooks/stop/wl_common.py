"""wl_common: helpers the stop-hook modules each used to carry a private copy of.

check:ci-shape-duplication's advisory profile reported the copies as shapes (agent/plans/PLAN-stop-hook-refactor-enforcement.md, Extraction queue), and each helper here replaces one family:

  Checker        the `--selftest` PASS/FAIL closure, seven copies in two print styles (24180b37961d, 47f5d13372ca, bf17a63ee8b9, 4881a1ff7ea2, 0d45b0617807).
                 Both styles stay byte-identical, so no selftest's output changes.
  run_quiet      a bounded, non-forking subprocess call whose spawn failure is a None rather than a raise (e2c04fa7b0d1). A command that FORKS goes through wl_proc instead.
  clean          a stripped, capped string field of a judge verdict object (05dbeeede217).
  tail_records   the parsed JSON records in the tail of a transcript (24fb35a0f6c7, ecdbc43a8849).
  records        the parse-and-skip loop over raw JSONL lines those rest on.

Stdlib only, so it imports when every other sibling is broken, and no module gains a dependency heavier than the copy it replaces.
"""

import json
import os
import subprocess


class Checker:
    """`check(label, cond, detail="")` prints one control line and counts the failures.

    style "arrow"   FAIL lines end `  <- <detail>` (wl_admit, wl_ci, wl_planfid, wl_roundlog).
    style "indent"  a failing control's detail goes on its own line, indented, and only when non-empty (wl_profile, wl_resprofile, wl_ressample).
    """

    def __init__(self, style="arrow"):
        self.style = style
        self.failures = 0

    def __call__(self, label, cond, detail=""):
        passed = bool(cond)
        if self.style == "indent":
            tail = ("\n        " + detail) if (detail and not passed) else ""
        else:
            tail = "" if passed else "  <- %s" % (detail,)
        print("  %s  %s%s" % ("PASS" if passed else "FAIL", label, tail))
        if not passed:
            self.failures += 1

    @property
    def ok(self):
        return self.failures == 0

    def verdict(self, name):
        """Print the closing line every arrow-style selftest printed, and return its exit code."""
        print("  %s" % ("all %s controls passed" % name if self.ok else "*** FAILURES ***"))
        return 0 if self.ok else 1


def run_quiet(argv, cwd=None, timeout=10):
    """`subprocess.run(argv, capture_output=True, text=True)` bounded by `timeout`, or None when it could not be spawned or timed out. For commands that do not fork; wl_proc is the door for ones that do."""
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def clean(obj, key, limit):
    """`obj[key]` stripped and capped at `limit` characters when it is a string, else ""."""
    v = obj.get(key)
    return v.strip()[:limit] if isinstance(v, str) else ""


def records(lines, need=None):
    """The JSON objects among raw JSONL `lines`, in order: blank lines, lines not containing `need` (bytes, when given) and unparseable lines are skipped."""
    for raw in lines:
        if not raw.strip() or (need is not None and need not in raw):
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if isinstance(rec, dict):
            yield rec


def tail_records(path, max_bytes):
    """The JSON objects in the last `max_bytes` of the file at `path`, oldest first, or None when there is no such file or it cannot be read. When the read starts mid-file its first line is dropped, because it is probably partial."""
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            chunk = f.read()
    except OSError:
        return None
    lines = chunk.split(b"\n")
    if size > max_bytes:
        lines = lines[1:]
    return list(records(lines))
