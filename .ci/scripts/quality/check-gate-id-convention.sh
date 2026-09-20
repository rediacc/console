#!/usr/bin/env bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-gate-id-convention is now registered to the Python port's entry point,
# .ci/scripts/quality/check_gate_id_convention.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs ".ci/scripts/quality/check_gate_id_convention.py" but its header derives ".ci/scripts/quality/check-gate-id-convention.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

# Assert that a manifest entry which RUNS a gates/ script is registered as
# `gate-test:<name>` and carries no redundant npm alias.
#
# WHY THIS EXISTS. On 2026-08-08 a new gate under `.ci/scripts/test/gates/` was
# registered as `check:ci-edge-verify-retries` with a `package.json` script, while
# all 57 of its siblings used `id: 'gate-test:<name>'` and invoked the script
# directly. A reviewer caught it and said the thing that made it worth fixing:
#
#   "It passes check-ci-parity's assertions either way (nothing enforces the
#    gate-test: prefix), so it's not a defect, just an inconsistency for future
#    maintainers to notice."
#
# A convention held by 57 entries and enforced by NONE is one that gets broken
# again by whoever copies the odd one out. This is the enforcement.
#
# THE INVARIANT IS NARROW, AND THE NARROWNESS IS THE POINT. It is NOT "any entry
# mentioning gates/". Several legitimate `check:ci-*` quality gates name a gates/
# script in their `ci: { kind: 'test', test: ... }` field -- that field says which
# CI job covers them, not what they run. Flagging those would be a false positive
# that trains people to ignore this gate. The rule applies ONLY to what `run`
# actually executes.
#
# ACCEPTED LIMITATION (ruled on in the #557 review): the alias unwind is ONE hop.
# A two-hop chain (`run: npm run A` -> `A: npm run B` -> `B: gates/ script`) would
# escape resolves_to_gate_script(). No such chain exists, and the design principle
# here is control-first against shapes that have actually shipped -- if a two-hop
# alias ever appears, plant it as a second control and widen the unwind THEN,
# rather than speculatively complicating the resolver now.
#
# ---------------------------------------------------------------------------
# THE SUBJECT IS gates.lock.json, NOT manifest.ts, SINCE 2026-09-06 (W2.4a).
#
# This gate used to run a regex over the 5,700-line TypeScript literal in
# `scripts/ci-runner/manifest.ts`:
#
#     re.findall(r"\{\s*id:\s*'([^']+)'\s*,\s*run:\s*'([^']+)'", manifest)
#
# and it was WRONG, in the silent direction, for as long as it shipped. `\{\s*id:`
# allows only whitespace between the opening brace and `id:`, so every entry whose
# leading comment sits INSIDE the brace was invisible. Measured on 2026-09-06 at
# commit ac817a647:
#
#     OLD regex pairs: 373   NEW lock pairs: 420   only in OLD: []
#     entries resolving to a gates/ script: OLD 135, NEW 147
#
# Strict subset, never a superset: the regex saw 373 of 420 entries and 135 of the
# 147 gate scripts it exists to police. Twelve gate-test registrations -- gate-header,
# gate-lanes, media-docs, media-portable, media-shims, rebase-resolve, resprofile,
# shadow-gate, shrink-only-composition, untagged-commit-branch, vacuity-floors,
# watchdog-monitor-ordering -- were outside the gate's field of view entirely, and the
# old FLOOR of 40 sailed past 373 without a murmur. This is the same scar
# `.claude/hooks/stop/wl_reggate.py` carries in its `_manifest_entries` docstring,
# found there on 2026-08-20 at 259 of 261 seen: a TS-shape nobody anticipated makes
# the set SHORTER while the green line still reads healthy.
#
# `scripts/ci-runner/gates.lock.json` is that same literal projected to JSON by
# `scripts/gen/gen-gates-lock.ts` and kept faithful by `check:ci-gates-lock`, which fails
# when the two disagree. One parse, no regex archaeology, and a shape error is a JSON
# error rather than a quietly shorter list. Re-running the gate's own logic over all
# 420 entries produced ZERO findings, so widening the field of view did not re-scope
# what the tree is allowed to contain; it only stopped the gate lying about how much
# of it had been read.
# ---------------------------------------------------------------------------
#
# CONTROL-FIRST, and there are TWO controls because there are two ways to be wrong.
# The first plants the exact 2026-08-08 shape (a gates/ script invoked via an
# `npm run check:ci-*` alias) and requires detection. The second truncates the lock
# and requires the FLOOR to fire, which is the direction the old regex failed in and
# nothing noticed. If either plant passes, the gate declares ITSELF broken and exits
# non-zero.

set -euo pipefail

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOCK="$REPO_ROOT/scripts/ci-runner/gates.lock.json"
PKG="$REPO_ROOT/package.json"
GATES_DIR="$REPO_ROOT/.ci/scripts/test/gates"

fail() {
    echo "${RED}✗${NC} $*" >&2
    exit 1
}

[[ -f "$LOCK" ]] || fail "check-gate-id-convention: $LOCK not found; refusing to pass while measuring nothing. It is generated by scripts/gen/gen-gates-lock.ts and guarded by check:ci-gates-lock."
[[ -f "$PKG" ]] || fail "check-gate-id-convention: $PKG not found"
[[ -d "$GATES_DIR" ]] || fail "check-gate-id-convention: $GATES_DIR not found; the corpus the floor is derived from is missing"

# evaluate <lock-path> <package-json-path> <gates-dir> -- one line per violation,
# empty when clean.
#
# ARGUMENTS ARE PATHS, NOT CONTENTS, and that is a scar rather than a style choice.
# The previous version passed the whole manifest text through temp files precisely
# because it could not pass it through argv: Linux caps a single argument at
# MAX_ARG_STRLEN (32 pages = 131072 bytes), and manifest.ts crossed it on 2026-08-24
# at 131359 bytes, one commit after sitting 96 bytes under. The symptom was not a
# gate finding but the interpreter refusing to start: "/usr/bin/python3: Argument
# list too long", exit 126, which reads like a broken runner rather than a gate that
# outgrew its own plumbing. gates.lock.json is 171 KB today and would hit the same
# wall, so the whole class is designed out: nothing but a path ever crosses argv,
# and the control writes its planted copies to temp FILES.
evaluate() {
    python3 - "$1" "$2" "$3" <<'PY'
import glob, json, os, re, sys

lock_path, pkg_path, gates_dir = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    with open(lock_path, encoding="utf-8") as fh:
        parsed = json.load(fh)
except (OSError, ValueError) as exc:
    print(f"PARSE: {lock_path} is not readable JSON ({exc}); cannot check anything. "
          f"It is generated by scripts/gen/gen-gates-lock.ts; run check:ci-gates-lock.")
    raise SystemExit(0)

if not isinstance(parsed, list):
    print(f"PARSE: {lock_path} is a {type(parsed).__name__}, not the expected JSON array of entries")
    raise SystemExit(0)

try:
    with open(pkg_path, encoding="utf-8") as fh:
        scripts = json.load(fh).get("scripts", {})
except (OSError, ValueError):
    print("PARSE: package.json is not valid JSON; cannot resolve npm aliases")
    raise SystemExit(0)

GATES = ".ci/scripts/test/gates/test-"
entries = [
    (g["id"], g["run"])
    for g in parsed
    if isinstance(g, dict) and isinstance(g.get("id"), str) and isinstance(g.get("run"), str)
]

def resolves_to_gate_script(run: str) -> bool:
    if run.startswith(GATES):
        return True
    m = re.match(r"npm run (?:--silent )?([A-Za-z0-9:._-]+)$", run.strip())
    if m:
        return scripts.get(m.group(1), "").strip().startswith(GATES)
    return False

subjects = [(gid, run) for gid, run in entries if resolves_to_gate_script(run)]

# THE FLOOR IS CORPUS-DERIVED, per driver-contract section 6: "a floor must be
# set-based or corpus-derived, never a hand-typed count". The old floor was the
# literal 40, and 40 is the number that let a 373-of-420 read look healthy.
#
# The corpus is the gate scripts ON DISK, deliberately not `git ls-files`. Section 5b
# of the contract records why: ls-files reads the INDEX, and this program keeps work
# uncommitted, so a newly written gate script is invisible to the index while being
# perfectly real to run-all.sh, which globs the directory exactly like this.
#
# The direction is the safe one. A NEW script not yet registered lifts the floor and
# reds this gate, which is a true finding (check:ci-gate-manifest asserts the same
# set equality). A COLLAPSED reader drops `subjects` below the floor and reds, which
# is the failure that went unseen for a month: at 135 subjects against 147 scripts,
# this floor would have fired on the old regex the day it was written.
on_disk = sorted(glob.glob(os.path.join(gates_dir, "test-*.sh")))
if not on_disk:
    print(f"FLOOR: no test-*.sh found under {gates_dir}; the corpus the floor is derived "
          f"from is empty, so every assertion below would pass while checking nothing")
    raise SystemExit(0)
if len(subjects) < len(on_disk):
    print(f"FLOOR: only {len(subjects)} of {len(entries)} lock entries resolve to a gates/ "
          f"script, but {len(on_disk)} test-*.sh files exist on disk. The reader is seeing "
          f"less than the corpus, and every assertion below would pass over the gap.")
    raise SystemExit(0)

for gid, run in subjects:
    if not gid.startswith("gate-test:"):
        # The sibling count is DERIVED, never typed. It read "57 siblings" when
        # this gate was written and "147" would be right today, which is exactly
        # how a number in a message goes stale and starts misleading the reader
        # it exists to persuade. Driver contract section 6, applied to prose.
        conforming = sum(1 for i, _ in subjects if i.startswith("gate-test:"))
        print(f"CONVENTION: '{gid}' runs a gates/ script but is not registered as "
              f"gate-test:<name> ({conforming} siblings are); run={run}")
    m = re.match(r"npm run (?:--silent )?([A-Za-z0-9:._-]+)$", run.strip())
    if m:
        print(f"ALIAS: '{gid}' reaches its gates/ script through the npm alias "
              f"'{m.group(1)}'; siblings invoke the script directly, so the alias is "
              f"a second name for one thing and drifts")

print(f"# SUBJECTS {len(subjects)} of {len(entries)} entries, floor {len(on_disk)}", file=sys.stderr)
PY
}

# ---- CONTROL 1: plant the exact shape that shipped on 2026-08-08 -------------
CONTROL_DIR="$(mktemp -d)"
trap 'rm -rf "$CONTROL_DIR"' EXIT

python3 - "$LOCK" "$CONTROL_DIR/lock.json" <<'PY'
import json, sys
entries = json.load(open(sys.argv[1], encoding="utf-8"))
entries.append({
    "id": "check:ci-planted-defect",
    "run": "npm run check:ci-planted-defect",
    "gate": True,
    "leaves": [".ci/scripts/test/gates/test-planted.sh"],
    "ci": {"kind": "local-only", "blocker": "planted control, never real"},
})
json.dump(entries, open(sys.argv[2], "w", encoding="utf-8"))
PY
python3 - "$PKG" "$CONTROL_DIR/package.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
d.setdefault("scripts", {})["check:ci-planted-defect"] = ".ci/scripts/test/gates/test-planted.sh"
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"))
PY

CONTROL_OUT="$(evaluate "$CONTROL_DIR/lock.json" "$CONTROL_DIR/package.json" "$GATES_DIR" 2>/dev/null)"
if [[ -z "$CONTROL_OUT" ]]; then
    fail "check-gate-id-convention: CONTROL 1 DID NOT FIRE. A gates/ script registered under a check:ci-* id via an npm alias -- the exact 2026-08-08 shape -- passed every assertion, so this gate cannot detect the defect it exists for."
fi
if ! grep -q '^CONVENTION:' <<<"$CONTROL_OUT"; then
    fail "check-gate-id-convention: CONTROL 1 fired but produced no CONVENTION line; it detected something other than the planted shape."
fi

# ---- CONTROL 2: truncate the lock and require the FLOOR to fire --------------
#
# This is the control the old version did not have, and its absence is why a reader
# that saw 373 of 420 entries reported success for a month. A short read must be a
# RED, not a quieter green.
python3 - "$LOCK" "$CONTROL_DIR/short.json" <<'PY'
import json, sys
entries = json.load(open(sys.argv[1], encoding="utf-8"))
json.dump(entries[:5], open(sys.argv[2], "w", encoding="utf-8"))
PY

FLOOR_OUT="$(evaluate "$CONTROL_DIR/short.json" "$PKG" "$GATES_DIR" 2>/dev/null)"
if ! grep -q '^FLOOR:' <<<"$FLOOR_OUT"; then
    fail "check-gate-id-convention: CONTROL 2 DID NOT FIRE. A five-entry lock -- a reader that has collapsed -- did not trip the corpus floor, so a shrinking field of view would still read as green. Output was: ${FLOOR_OUT:-<empty>}"
fi

# ---- the real run ------------------------------------------------------------
REAL_ERR="$CONTROL_DIR/real.err"
REAL_OUT="$(evaluate "$LOCK" "$PKG" "$GATES_DIR" 2>"$REAL_ERR")"
if [[ -n "$REAL_OUT" ]]; then
    echo "${RED}✗${NC} gate registration does not follow the gates/ convention:" >&2
    printf '  %s\n' "$REAL_OUT" >&2
    echo >&2
    echo "  Scripts under .ci/scripts/test/gates/ are registered as gate-test:<name>" >&2
    echo "  with run pointing at the script directly, and no package.json entry." >&2
    echo "  The subject is scripts/ci-runner/gates.lock.json, regenerated from" >&2
    echo "  manifest.ts by scripts/gen/gen-gates-lock.ts; if it is stale, check:ci-gates-lock" >&2
    echo "  is the gate that says so." >&2
    exit 1
fi

echo "${GREEN}✓${NC} every gates.lock.json entry that runs a gates/ script uses the gate-test: convention"
sed 's/^# /  scope: /' "$REAL_ERR"
echo "  control 1 fired on the planted check:ci-* alias ($(grep -c . <<<"$CONTROL_OUT") finding(s))"
echo "  control 2 fired the corpus floor on a truncated lock, so a shrinking read reds rather than quietly passing"
