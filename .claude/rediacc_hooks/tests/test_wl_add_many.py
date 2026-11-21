"""`worklist.py --add-many <me>`: one item per stdin line, one fold, one append (agent/plans/PLAN-plan-preflight.md).

The verb exists because `/writers-now` tracked 34 items through 34 slow `--add` processes. Every case drives the real CLI through `wlfix`; the counts come from the real functions, wrapped in a subprocess pointed at the fixture store, and the store itself is read back through `--list`, so a refused run is proven by the fold rather than by its exit code.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from rediacc_hooks.tests import wlfix

# Runs the real main() with its store calls counted, and prints the counts as the last stdout line.
PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import worklist as W

counts = {"load": 0, "append": 0, "events": 0}
real_load, real_append = W.S.load, W.S.append_events

def load(*a, **k):
    counts["load"] += 1
    return real_load(*a, **k)

def append(worklist, payloads, *a, **k):
    counts["append"] += 1
    counts["events"] += len(payloads)
    return real_append(worklist, payloads, *a, **k)

W.S.load, W.S.append_events = load, append
sys.argv = ["worklist.py", "--add-many", sys.argv[2]]
rc = 0
try:
    W.main()
except SystemExit as exc:
    rc = exc.code or 0
print(json.dumps({"rc": rc, **counts}))
"""


def counted(fix, stdin: str) -> tuple[dict, str, str]:
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, str(wlfix.STOP_DIR), wlfix.ME],
        input=stdin,
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.stdout.strip(), "the probe printed nothing: %s" % proc.stderr[-1200:]
    lines = proc.stdout.strip().splitlines()
    return json.loads(lines[-1]), "\n".join(lines[:-1]), proc.stderr


def fold_count(fix) -> int:
    """The items the store folds to, read by the verb a session reads them with."""
    got = fix.cli("--list")
    assert got.rc == 0, got.err[:300]
    return len(re.findall(r"\[#[0-9a-f]+ ", got.out))


def test_three_lines_give_three_items_from_one_fold_and_one_append(wl):
    counts, out, _err = counted(wl, "first thing to track\nsecond thing\nthird thing\n")
    assert counts == {"rc": 0, "load": 1, "append": 1, "events": 3}, counts
    assert fold_count(wl) == 3
    for text in ("first thing to track", "second thing", "third thing"):
        assert re.search(r"^added #[0-9a-f]+: %s$" % text, out, re.MULTILINE), out[:400]
    assert len(set(re.findall(r"added #([0-9a-f]+)", out))) == 3, out[:400]


def test_items_are_owned_and_listed_exactly_as_add_writes_them(wl):
    """The inverse of one planted fact: the same text through `--add` and through `--add-many` folds to the same line."""
    wl.cli("--add", wlfix.ME, "tracked by the single verb")
    got = wl.cli("--add-many", wlfix.ME, stdin="tracked by the many verb\n")
    assert got.rc == 0, got.err[:300]
    listed = wl.cli("--list").out
    single = re.search(r"^(.*)tracked by the single verb(.*?)\s+\[#", listed, re.MULTILINE)
    many = re.search(r"^(.*)tracked by the many verb(.*?)\s+\[#", listed, re.MULTILINE)
    assert single, listed[:400]
    assert many, listed[:400]
    assert single.groups() == many.groups(), listed[:400]


def test_an_invalid_line_is_refused_before_anything_is_written(wl):
    """FIRE: an unknown blocker and an interior blank line. The fold count stays 0, and the CONTROL below changes only those two lines and writes all of the rest."""
    bad = "good line one\nwaits on nothing BLOCKED_BY:#00000000\n\ngood line two\n"
    counts, out, err = counted(wl, bad)
    assert counts["rc"] == 2, counts
    assert counts["append"] == 0, counts
    assert fold_count(wl) == 0
    assert "added #" not in out, out[:300]
    assert "line 2: BLOCKED_BY names #00000000" in err, err[:400]
    assert "line 3: an empty item tracks nothing" in err, err[:400]
    assert "Nothing was written" in err, err[:400]

    counts, _out, _err = counted(wl, "good line one\ngood line two\n")
    assert counts == {"rc": 0, "load": 1, "append": 1, "events": 2}, counts
    assert fold_count(wl) == 2


def test_a_live_blocker_passes_and_a_closed_one_is_refused(wl):
    """`--add`'s BLOCKED_BY rule per line, against the one fold."""
    first = wl.cli("--add-many", wlfix.ME, stdin="the blocker\n")
    added = re.search(r"added #([0-9a-f]+)", first.out)
    assert added is not None, first.out
    rid = added.group(1)
    assert wl.cli("--add-many", wlfix.ME, stdin="waits BLOCKED_BY:#%s\n" % rid).rc == 0
    assert fold_count(wl) == 2
    assert wl.cli("--tick", wlfix.ME, rid, "https://ci.invalid/run/1 nocommit:research").rc == 0
    late = wl.cli("--add-many", wlfix.ME, stdin="too late BLOCKED_BY:#%s\n" % rid)
    assert late.rc == 2, late.err[:300]
    assert "already closed" in late.err, late.err[:300]
    assert fold_count(wl) == 2


def test_empty_stdin_and_argv_text_are_refused(wl):
    empty = wl.cli("--add-many", wlfix.ME, stdin="")
    assert empty.rc == 2, empty.err[:300]
    assert "no lines arrived on stdin" in empty.err, empty.err[:300]
    argv = wl.cli("--add-many", wlfix.ME, "text in argv", stdin="a real line\n")
    assert argv.rc == 2, argv.err[:300]
    assert "read from STDIN" in argv.err, argv.err[:300]
    bare = wl.cli("--add-many")
    assert bare.rc != 0, bare.err[:300]
    assert "--add-many <my-prefix>" in bare.err, bare.err[:300]
    assert fold_count(wl) == 0


def test_a_foreign_identity_is_refused_before_stdin_is_judged(wl):
    got = wl.cli("--add-many", "feedface", stdin="a line\n")
    assert got.rc != 0, got.err[:300]
    assert "identity mismatch" in got.out + got.err, (got.out + got.err)[:300]
    assert fold_count(wl) == 0


def test_a_near_duplicate_warns_and_still_adds(wl):
    text = "rework the alpha gateway retry budget and its gate"
    wl.cli("--add", wlfix.ME, text)
    got = wl.cli("--add-many", wlfix.ME, stdin="%s\nsomething else entirely here\n" % text)
    assert got.rc == 0, got.err[:300]
    assert got.err.count("WARNING: similar open item") == 1, got.err[:300]
    assert fold_count(wl) == 3
