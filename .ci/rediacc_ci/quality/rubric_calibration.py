"""A calibrated rubric may not change without being re-calibrated.

Ported from `.ci/scripts/quality/check-rubric-calibration.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__` for the phase-5 decision that retired the twin.

THE GAP. Three prompt constants drive the stop judge's rules, and each has a fixture set in `.claude/hooks/stop/calibrate-judge-rules.py` that scores it against a REAL model: SWEEP_PROMPT (SWEEP_CASES), BRAVE_PROMPT (BRAVE_CASES), REGGATE_PROMPT, SHAPE_PROMPT (SHAPE_CASES). Nothing forced the two to move together. Editing a rubric is cheap and silent; re-calibrating costs 14 live
model calls and several minutes, so the pressure is entirely toward skipping it -- and a rubric whose calibration describes an older text is a rubric nobody has measured.

`wl_classsweep`'s own docstring records that its examples ARE the calibration set the operator supplied. That session trimmed five of them to three, which is exactly the edit this gate exists to catch: it was re-calibrated by choice, not by machinery.

WHAT THIS DOES NOT CLAIM. It cannot verify the calibration PASSED -- only that the recorded hash matches the text on disk, so a human or a session had the current text in front of the model. Recording a hash after a 12/14 run is possible and is a lie the gate cannot see; the run's own output is the evidence for that.

THE SOURCE MAP, carried with its history intact:

  SWEEP_PROMPT    .claude/hooks/stop/wl_classsweep.py
  BRAVE_PROMPT    .claude/hooks/stop/wl_bravedefault.py
  REGGATE_PROMPT  .claude/hooks/stop/worklist_messages.py
  SHAPE_PROMPT    .claude/hooks/stop/wl_shapedup.py

SHAPE_PROMPT was added 2026-09-02. It had live fixtures (SHAPE_CASES) and was calibrated by the same runner, yet was absent from this map -- so its text could drift with nothing noticing, which is the one thing this gate exists to prevent. It was the only rubric in that state with fixtures already written; the remaining five (FOLLOWUP, DEFER_AUDIT, TRIAGE, ADMISSION, PLANFID) have
neither fixtures nor a hash, and adding a hash without fixtures would freeze text nothing has ever proven correct.

THE OTHER DIRECTION, and it was missing until it was probed. The comparison walks the rubrics found in SOURCE and looks each up in the manifest; a manifest entry naming a rubric that no longer exists is never visited. Probed 2026-09-04 by planting NO_SUCH_RUBRIC_XYZ: the gate printed "all 4 calibrated rubric(s) match"
while the file held five, so a calibration could outlive the rubric it measured
and read as coverage. Its sibling `.ci/scripts/ci/shadow-compare.sh` already refuses the same shape ("is in SHADOW_EXPECTED_MISMATCH but not in SHADOW_NAMES -- it excuses nothing here").

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWIN IS ALREADY MOSTLY PYTHON, RUN THROUGH TWO HEREDOCS. `hashes()` is a `python3 - "$1" <<'PY'` block and the manifest comparison is a `python3 - "$MANIFEST" <<PY` block -- note the UNQUOTED marker on the second, which is what lets `'''$live'''` interpolate the first block's JSON output through the shell. That interpolation is the port's one genuine safety improvement and it
is worth naming rather than silently removing: a rubric hash is 16 hex characters so it can never contain a quote today, but the value crossing a shell expansion into a Python string literal is a shape that only stays safe by accident of what happens to be in it. In the port the two halves are one process and the value never becomes source text.

THE SORT ORDER OF `bad` IS PRESERVED, AND IT IS NOT OBVIOUS. The twin's first
heredoc prints `json.dumps(out, sort_keys=True)` and the second parses that back,
so `live.items()` iterates in SORTED KEY order even though `SRC` is written in a different order. A port that iterated `SRC` would report the same findings in a different sequence -- which the shadow comparator would forgive, since it compares a multiset -- but a human diffing two logs would not. `live` is therefore built sorted.

THE FLOOR SAYS THREE WHILE FOUR RUBRICS EXIST, and that is deliberate in the original: SHAPE_PROMPT was added later and the floor was not raised with it. It is carried at 3 unchanged. Raising it would be a behaviour change, and this file's job is to keep the verdict; it is reported as a finding instead.
"""

import hashlib
import json
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The manifest, and the default the twin uses when given no argument.
DEFAULT_MANIFEST = ".ci/config/rubric-calibration.json"

# The rubric constants and the file each lives in, relative to the repo root. See the module docstring for why SHAPE_PROMPT arrived late and why five other prompts are deliberately absent.
SOURCES = {
    "SWEEP_PROMPT": ".claude/hooks/stop/wl_classsweep.py",
    "BRAVE_PROMPT": ".claude/hooks/stop/wl_bravedefault.py",
    "REGGATE_PROMPT": ".claude/hooks/stop/worklist_messages.py",
    "SHAPE_PROMPT": ".claude/hooks/stop/wl_shapedup.py",
}

# FLOOR. Three constants existed when the floor was written. Finding fewer means a rename moved one out of reach and this green would assert nothing about it. See the module docstring: the value is stale by one and is carried unchanged anyway.
MIN_RUBRICS = 3

# 16 hex characters of sha256. Not the full digest, matching the twin, so a recorded hash stays readable in a JSON file a human edits.
HASH_CHARS = 16


def hashes(root: pathlib.Path) -> dict[str, str]:
    """{constant: sha256[:16]} for every rubric whose file and heredoc are present.

    A missing FILE and a missing CONSTANT both yield an absent key rather than an error, exactly as the twin's `continue` and unmatched-regex do. That is what makes the floor below load-bearing: absence is silent here, so something has to count what came back.
    """
    out: dict[str, str] = {}
    for name, relative in SOURCES.items():
        path = root / relative
        if not path.exists():
            continue
        # `^NAME = \"\"\"(.*?)\"\"\"` with DOTALL and MULTILINE, non-greedy so the
        # first closing triple-quote ends the constant. Anchored at the start of a line so a mention of the name inside another string cannot match.
        match = re.search(
            r'^%s = """(.*?)"""' % name, path.read_text(encoding="utf-8"), re.DOTALL | re.MULTILINE
        )
        if match:
            out[name] = hashlib.sha256(match.group(1).encode()).hexdigest()[:HASH_CHARS]
    # Sorted, because the twin round-trips this through `json.dumps(sort_keys=True)`
    # and every later iteration inherits that order. See the port notes.
    return dict(sorted(out.items()))


def run_control() -> int:
    """CONTROL, before the real run. A gate that cannot fire is worse than no gate.

    Two assertions, and they cover different failures. That a CHANGED rubric produces a DIFFERENT hash proves the extractor is reading the constant rather than, say, the file's mtime. That the extractor found a constant AT ALL proves the regex still matches the shape these files are written in -- without it,
    an extractor that returns `{}` for everything would satisfy the first
    assertion trivially, since `{} != {}` is false but so is any comparison it
    could make.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ctl = pathlib.Path(tmp)
        target = ctl / ".claude/hooks/stop"
        target.mkdir(parents=True)
        sweep = target / "wl_classsweep.py"
        sweep.write_text('SWEEP_PROMPT = """original text"""\n', encoding="utf-8")
        before = hashes(ctl)
        sweep.write_text('SWEEP_PROMPT = """MUTATED text"""\n', encoding="utf-8")
        after = hashes(ctl)
        if before == after:
            print(
                "CONTROL DID NOT FIRE: a changed rubric produced an identical hash", file=sys.stderr
            )
            return 1
        if "SWEEP_PROMPT" not in before:
            print(
                "CONTROL COULD NOT PLANT: the extractor found no constant in the fixture",
                file=sys.stderr,
            )
            return 1
    print("✓ control: a changed rubric changes its hash, and the extractor finds one")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    manifest_name = args[0] if args else DEFAULT_MANIFEST
    manifest = root / manifest_name

    if run_control() != 0:
        return 1

    live = hashes(root)
    if len(live) < MIN_RUBRICS:
        print(
            "✗ found only %d calibrated rubric(s); expected %d. A constant was renamed or"
            % (len(live), MIN_RUBRICS),
            file=sys.stderr,
        )
        print(
            "  its heredoc shape changed, and this green would cover it no longer.", file=sys.stderr
        )
        return 1

    if not manifest.is_file():
        print("✗ no calibration manifest at %s" % manifest_name, file=sys.stderr)
        return 1

    recorded = json.loads(manifest.read_text(encoding="utf-8"))["rubrics"]

    # THE OTHER DIRECTION FIRST, because it is the one that was missing. A manifest entry naming a rubric that is gone is never visited by the sha comparison below, and reads as coverage.
    orphans = sorted(set(recorded) - set(live))
    if orphans:
        for key in orphans:
            print(
                "✗ %s is calibrated in the manifest but no such rubric exists in source" % key,
                file=sys.stderr,
            )
        print(file=sys.stderr)
        print(
            "  A calibration for a rubric that is gone measures nothing and reads as",
            file=sys.stderr,
        )
        print("  coverage. Delete the entry from %s." % manifest_name, file=sys.stderr)
        return 1

    bad = [key for key, value in live.items() if recorded.get(key, {}).get("sha") != value]
    if bad:
        for key in bad:
            print("✗ %s changed since it was last calibrated" % key, file=sys.stderr)
            print(
                "    recorded %s  now %s"
                % (recorded.get(key, {}).get("sha", "(absent)"), live[key]),
                file=sys.stderr,
            )
        print(file=sys.stderr)
        print("  Re-calibrate, then record the new hash:", file=sys.stderr)
        print("    python3 .claude/hooks/stop/calibrate-judge-rules.py --live", file=sys.stderr)
        print("  Require the full pass, then update %s." % manifest_name, file=sys.stderr)
        return 1

    print(
        "✓ all %d calibrated rubric(s) match the text they were measured on, "
        "and no manifest entry names a rubric that is gone" % len(live)
    )
    return 0


def selftest() -> int:
    """Plant each finding class and its mirror, against a manifest under our control.

    The rubric TEXT is the real tree's -- there is no seam for it, and inventing one would be a behaviour change -- so every plant is on the manifest side. That is enough: the manifest is the half a human edits, and both failure classes the gate names (a stale sha, an orphaned entry) live there.
    """
    ctl = Controls("rubric-calibration", floor=8, verbose=True)
    live = hashes(paths.repo_root())

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        def manifest(payload: object) -> str:
            path = base / "m.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return str(path)

        truthful = {"rubrics": {k: {"sha": v} for k, v in live.items()}}
        ctl.check("CONTROL: a truthful manifest passes", main([manifest(truthful)]), 0)

        # THE PLANT. One recorded sha no longer describes the text on disk, which is precisely "a rubric whose calibration describes an older text".
        first = min(live)
        stale = {"rubrics": {k: {"sha": v} for k, v in live.items()}}
        stale["rubrics"][first] = {"sha": "0" * HASH_CHARS}
        ctl.check("PLANT: one stale sha is caught", main([manifest(stale)]), 1)

        # Every sha stale, so a gate that only ever looks at the first key fails the same way and this control alone would not distinguish them -- which is why the single-key plant above exists as well.
        allstale = {"rubrics": {k: {"sha": "1" * HASH_CHARS} for k in live}}
        ctl.check("PLANT: every stale sha is caught", main([manifest(allstale)]), 1)

        # A rubric present in source but ABSENT from the manifest: `.get(key, {})`
        # yields `(absent)` and the entry is bad. Not the orphan direction.
        missing = {"rubrics": {k: {"sha": v} for k, v in live.items() if k != first}}
        ctl.check("PLANT: an uncalibrated rubric is caught", main([manifest(missing)]), 1)

        # THE DIRECTION THAT WAS MISSING, replanted with the same name the 2026-09-04 probe used, so the record and the control agree.
        orphan = {"rubrics": {k: {"sha": v} for k, v in live.items()}}
        orphan["rubrics"]["NO_SUCH_RUBRIC_XYZ"] = {"sha": "2" * HASH_CHARS}
        ctl.check("PLANT: an orphaned manifest entry is caught", main([manifest(orphan)]), 1)

        # ORDER MATTERS: an orphan AND a stale sha must report the orphan, because a stale-sha report would send the reader to re-calibrate a rubric that no longer exists.
        both = {"rubrics": {k: {"sha": v} for k, v in live.items()}}
        both["rubrics"][first] = {"sha": "3" * HASH_CHARS}
        both["rubrics"]["NO_SUCH_RUBRIC_XYZ"] = {"sha": "4" * HASH_CHARS}
        ctl.check("ORDER: orphan is reported before stale sha", main([manifest(both)]), 1)

        ctl.check("PLANT: a missing manifest is refused", main([str(base / "absent.json")]), 1)
        # THE MIRROR of every plant above: the truthful manifest, again, AFTER seven refusals. A gate that got stuck in a failed state would fail here and nowhere else.
        ctl.check("MIRROR: the truthful manifest still passes", main([manifest(truthful)]), 0)

    return 0 if ctl.report() else 1
