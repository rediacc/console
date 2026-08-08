#!/usr/bin/env bash
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
# CONTROL-FIRST: plants the exact 2026-08-08 shape (a gates/ script invoked via an
# `npm run check:ci-*` alias) and requires detection. If the plant passes, the gate
# declares ITSELF broken and exits non-zero.

set -euo pipefail

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MANIFEST="$REPO_ROOT/scripts/ci-runner/manifest.ts"
PKG="$REPO_ROOT/package.json"

fail() {
    echo "${RED}✗${NC} $*" >&2
    exit 1
}

[[ -f "$MANIFEST" ]] || fail "check-gate-id-convention: $MANIFEST not found; refusing to pass while measuring nothing"
[[ -f "$PKG" ]] || fail "check-gate-id-convention: $PKG not found"

# evaluate <manifest-text> <package-json-text> -- one line per violation, empty when clean.
evaluate() {
    python3 - "$1" "$2" <<'PY'
import json, re, sys

manifest, pkg_text = sys.argv[1], sys.argv[2]
try:
    scripts = json.loads(pkg_text).get("scripts", {})
except ValueError:
    print("PARSE: package.json is not valid JSON; cannot resolve npm aliases")
    raise SystemExit(0)

GATES = ".ci/scripts/test/gates/test-"
entries = re.findall(r"\{\s*id:\s*'([^']+)'\s*,\s*run:\s*'([^']+)'", manifest)

# FLOOR first: an empty or tiny entry list makes every check below vacuously true,
# which is the exact failure shape this repo keeps paying for.
if len(entries) < 40:
    print(f"FLOOR: only {len(entries)} manifest entries parsed; the regex is broken and "
          f"every assertion below would pass while checking nothing")
    raise SystemExit(0)

def resolves_to_gate_script(run: str) -> bool:
    if run.startswith(GATES):
        return True
    m = re.match(r"npm run (?:--silent )?([A-Za-z0-9:._-]+)$", run.strip())
    if m:
        return scripts.get(m.group(1), "").strip().startswith(GATES)
    return False

for gid, run in entries:
    if not resolves_to_gate_script(run):
        continue
    if not gid.startswith("gate-test:"):
        print(f"CONVENTION: '{gid}' runs a gates/ script but is not registered as "
              f"gate-test:<name> (57+ siblings are); run={run}")
    m = re.match(r"npm run (?:--silent )?([A-Za-z0-9:._-]+)$", run.strip())
    if m:
        print(f"ALIAS: '{gid}' reaches its gates/ script through the npm alias "
              f"'{m.group(1)}'; siblings invoke the script directly, so the alias is "
              f"a second name for one thing and drifts")
PY
}

MANIFEST_TEXT="$(cat "$MANIFEST")"
PKG_TEXT="$(cat "$PKG")"

# ---- CONTROL: plant the exact shape that shipped on 2026-08-08 ---------------
CONTROL_MANIFEST="${MANIFEST_TEXT}
  { id: 'check:ci-planted-defect', run: 'npm run check:ci-planted-defect', gate: true },"
CONTROL_PKG="$(python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
d.setdefault("scripts",{})["check:ci-planted-defect"]=".ci/scripts/test/gates/test-planted.sh"
print(json.dumps(d))' "$PKG")"
CONTROL_OUT="$(evaluate "$CONTROL_MANIFEST" "$CONTROL_PKG")"
if [[ -z "$CONTROL_OUT" ]]; then
    fail "check-gate-id-convention: CONTROL DID NOT FIRE. A gates/ script registered under a check:ci-* id via an npm alias -- the exact 2026-08-08 shape -- passed every assertion, so this gate cannot detect the defect it exists for."
fi

# ---- the real run ------------------------------------------------------------
REAL_OUT="$(evaluate "$MANIFEST_TEXT" "$PKG_TEXT")"
if [[ -n "$REAL_OUT" ]]; then
    echo "${RED}✗${NC} gate registration does not follow the gates/ convention:" >&2
    printf '  %s\n' "$REAL_OUT" >&2
    echo >&2
    echo "  Scripts under .ci/scripts/test/gates/ are registered as gate-test:<name>" >&2
    echo "  with run pointing at the script directly, and no package.json entry." >&2
    exit 1
fi

echo "${GREEN}✓${NC} every manifest entry that runs a gates/ script uses the gate-test: convention"
echo "  control fired on the planted check:ci-* alias ($(wc -l <<<"$CONTROL_OUT") finding(s)), so this green means the check can fail"
