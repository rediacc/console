#!/bin/bash
# ---- gate ----
# step: Rubric calibration
# needs: none
# lane: quality-code
# ---- end gate ----

# A calibrated rubric may not change without being re-calibrated.
#
# THE GAP. Three prompt constants drive the stop judge's rules, and each has a fixture set
# in `.claude/hooks/stop/calibrate-judge-rules.py` that scores it against a REAL model:
# SWEEP_PROMPT (SWEEP_CASES), BRAVE_PROMPT (BRAVE_CASES), REGGATE_PROMPT,
# SHAPE_PROMPT (SHAPE_CASES). Nothing forced
# the two to move together. Editing a rubric is cheap and silent; re-calibrating costs 14
# live model calls and several minutes, so the pressure is entirely toward skipping it --
# and a rubric whose calibration describes an older text is a rubric nobody has measured.
#
# `wl_classsweep`'s own docstring records that its examples ARE the calibration set the
# operator supplied. This session trimmed five of them to three, which is exactly the edit
# this gate exists to catch: it was re-calibrated by choice, not by machinery.
#
# WHAT THIS DOES NOT CLAIM. It cannot verify the calibration PASSED -- only that the
# recorded hash matches the text on disk, so a human or a session had the current text in
# front of the model. Recording a hash after a 12/14 run is possible and is a lie the gate
# cannot see; the run's own output is the evidence for that.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

MANIFEST="${1:-.ci/config/rubric-calibration.json}"

hashes() {
    python3 - "$1" <<'PY'
import hashlib, pathlib, re, sys, json
root = pathlib.Path(sys.argv[1])
SRC = {
    "SWEEP_PROMPT": root / ".claude/hooks/stop/wl_classsweep.py",
    "BRAVE_PROMPT": root / ".claude/hooks/stop/wl_bravedefault.py",
    "REGGATE_PROMPT": root / ".claude/hooks/stop/worklist_messages.py",
    # Added 2026-09-02. SHAPE_PROMPT had live fixtures (SHAPE_CASES) and was
    # calibrated by the same runner, yet was absent from this map -- so its text
    # could drift with nothing noticing, which is the one thing this gate exists
    # to prevent. It was the only rubric in that state with fixtures already
    # written; the remaining five (FOLLOWUP, DEFER_AUDIT, TRIAGE, ADMISSION,
    # PLANFID) have neither fixtures nor a hash, and adding a hash without
    # fixtures would freeze text nothing has ever proven correct.
    "SHAPE_PROMPT": root / ".claude/hooks/stop/wl_shapedup.py",
}
out = {}
for name, path in SRC.items():
    if not path.exists():
        continue
    m = re.search(r'^%s = """(.*?)"""' % name, path.read_text(), re.S | re.M)
    if m:
        out[name] = hashlib.sha256(m.group(1).encode()).hexdigest()[:16]
print(json.dumps(out, sort_keys=True))
PY
}

# -- CONTROL, before the real run. A gate that cannot fire is worse than no gate. --------
CTL="$(mktemp -d)"
trap 'rm -rf "$CTL"' EXIT
mkdir -p "$CTL/.claude/hooks/stop"
printf 'SWEEP_PROMPT = """original text"""\n' >"$CTL/.claude/hooks/stop/wl_classsweep.py"
a="$(hashes "$CTL")"
printf 'SWEEP_PROMPT = """MUTATED text"""\n' >"$CTL/.claude/hooks/stop/wl_classsweep.py"
b="$(hashes "$CTL")"
[ "$a" != "$b" ] || {
    echo "CONTROL DID NOT FIRE: a changed rubric produced an identical hash" >&2
    exit 1
}
grep -q SWEEP_PROMPT <<<"$a" || {
    echo "CONTROL COULD NOT PLANT: the extractor found no constant in the fixture" >&2
    exit 1
}
echo "✓ control: a changed rubric changes its hash, and the extractor finds one"

live="$(hashes "$REPO_ROOT")"
n="$(python3 -c 'import json,sys; print(len(json.loads(sys.stdin.read())))' <<<"$live")"
# FLOOR. Three constants exist. Finding fewer means a rename moved one out of reach and
# this green would assert nothing about it.
if [ "$n" -lt 3 ]; then
    echo "✗ found only $n calibrated rubric(s); expected 3. A constant was renamed or" >&2
    echo "  its heredoc shape changed, and this green would cover it no longer." >&2
    exit 1
fi

if [ ! -f "$MANIFEST" ]; then
    echo "✗ no calibration manifest at $MANIFEST" >&2
    exit 1
fi

python3 - "$MANIFEST" <<PY
import json, sys
live = json.loads('''$live''')
rec = json.load(open(sys.argv[1]))["rubrics"]
# THE OTHER DIRECTION, and it was missing. The loop below walks the rubrics found in
# SOURCE and looks each up in the manifest; a manifest entry naming a rubric that no
# longer exists is never visited. Probed 2026-09-04 by planting NO_SUCH_RUBRIC_XYZ:
# the gate printed "all 4 calibrated rubric(s) match" while the file held five, so a
# calibration could outlive the rubric it measured and read as coverage. Its sibling
# .ci/scripts/ci/shadow-compare.sh already refuses the same shape ("is in
# SHADOW_EXPECTED_MISMATCH but not in SHADOW_NAMES -- it excuses nothing here").
orphans = sorted(set(rec) - set(live))
if orphans:
    for k in orphans:
        print(f"✗ {k} is calibrated in the manifest but no such rubric exists in source", file=sys.stderr)
    print("", file=sys.stderr)
    print("  A calibration for a rubric that is gone measures nothing and reads as", file=sys.stderr)
    print(f"  coverage. Delete the entry from {sys.argv[1]}.", file=sys.stderr)
    sys.exit(1)

bad = [k for k, v in live.items() if rec.get(k, {}).get("sha") != v]
if bad:
    for k in bad:
        print(f"✗ {k} changed since it was last calibrated", file=sys.stderr)
        print(f"    recorded {rec.get(k, {}).get('sha', '(absent)')}  now {live[k]}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Re-calibrate, then record the new hash:", file=sys.stderr)
    print("    python3 .claude/hooks/stop/calibrate-judge-rules.py --live", file=sys.stderr)
    print(f"  Require the full pass, then update {sys.argv[1]}.", file=sys.stderr)
    sys.exit(1)
print(f"✓ all {len(live)} calibrated rubric(s) match the text they were measured on, "
      "and no manifest entry names a rubric that is gone")
PY
