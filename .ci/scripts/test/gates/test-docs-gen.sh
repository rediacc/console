#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# lane: quality-security
# needs: node
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# ---- end gate ----
# The documentation generator, proved in both directions.
#
# WHY IT NEEDS A GATE AT ALL. scripts/gen-docs.ts exists because hand-typed registry numbers go
# stale in silence: `.dead-bash-allowlist` said "the 17 gate scripts" against 131,
# scripts/check-ci-parity.ts said "runs 57 gate tests", and docs/agent-reference/ci-gates.md said
# "254 fast gates" against a live 312. A generator that quietly stops generating puts the tree
# straight back into that state, and the symptom -- a document that looks fine -- is invisible.
#
# WHAT THIS FILE ACTUALLY PROVES, and why each case is here rather than assumed:
#
#   A. verify is GREEN on the tree as it stands. On its own this proves nothing, because a
#      generator with no targets, or one that silently renders nothing, is also green. Hence B
#      through E.
#   B. verify goes RED when one generated row is perturbed. This is the control. Without it, A is
#      a check that cannot fail, which is the exact shape docs/agent-reference/TRAPS.md exists
#      for. The perturbation is restored by a trap, and the restore is itself asserted.
#   C. two `--write` runs are byte-identical. Determinism is not a nicety here: verify compares
#      rendered text against a file, so a render that reorders on a whim reds on noise and
#      teaches everyone to run --write without reading. Note the ordering -- A runs first, so
#      by the time C writes, the write is provably a no-op.
#   D. `--selftest` passes AND still contains its planted-defect controls by name. Asserting the
#      exit code alone would keep passing after someone deletes the controls; asserting the
#      labels is what makes D non-vacuous.
#   E. the pre-port SET snapshot is present and well-formed. It is the only instrument that can
#      catch a port silently dropping rows, and it is worthless if it is absent, truncated, or
#      quietly re-baselined.
#
# WHAT THIS FILE DELIBERATELY DOES NOT ASSERT: that the live sets still equal the snapshot. They
# are SUPPOSED to diverge as the ports land; `gen-docs.ts --diff-snapshot` is where that
# comparison belongs, run by the wave that does the porting.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GEN="$REPO_ROOT/scripts/gen-docs.ts"
TARGET="$REPO_ROOT/scripts/data/doc-registry.md"
SNAP="$REPO_ROOT/scripts/data/doc-registry-preport.json"

[[ -f "$GEN" ]] || log_fail "scripts/gen-docs.ts is missing; the generator is gone"
[[ -f "$TARGET" ]] || log_fail "scripts/data/doc-registry.md is missing; nothing carries a region"
[[ -f "$SNAP" ]] || log_fail "scripts/data/doc-registry-preport.json is missing; the pre-port SET record is gone"

WORK="$(mktemp -d)"
BACKUP="$WORK/doc-registry.md.orig"
cp "$TARGET" "$BACKUP"
# Restore on ANY exit path. A killed run must not leave a perturbed row behind: the next verify
# would red, which is the safe direction, but the finding would name a defect nobody introduced.
restore() {
    if [[ -f "$BACKUP" ]] && ! cmp -s "$BACKUP" "$TARGET"; then
        cp "$BACKUP" "$TARGET"
    fi
    rm -rf "$WORK"
}
trap restore EXIT

gen() { (cd "$REPO_ROOT" && npx tsx "$GEN" "$@"); }

# ---- A. verify is green on this tree ---------------------------------------
log_test "A. verify mode accepts the tree as it stands"
if ! gen >"$WORK/a.out" 2>"$WORK/a.err"; then
    log_error "$(cat "$WORK/a.err")"
    log_fail "A. gen-docs verify failed. If a provider's inputs changed, run: npx tsx scripts/gen-docs.ts --write"
fi
grep -q '^ok ' "$WORK/a.out" || log_fail "A. verify passed while reporting no target at all -- vacuous"
log_pass "A. verify is green and named at least one target"

# ---- B. the control: a perturbed row must turn it red ----------------------
log_test "B. verify goes red when one generated row is perturbed"
if ! python3 - "$TARGET" <<'PY'; then
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().split("\n")
# The first data row of the first table: a line starting with "| " that is not the header and not
# the "|---|" separator. Found by shape, not by content, so this control survives every
# rewording of every provider.
for i, line in enumerate(lines):
    if line.startswith("| ") and not line.startswith("|---") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
        lines[i + 2] = lines[i + 2] + " <!-- PERTURBED -->"
        break
else:
    raise SystemExit("no generated table row found to perturb")
open(path, "w", encoding="utf-8").write("\n".join(lines))
PY
    log_fail "B. could not plant the perturbation"
fi
if gen >"$WORK/b.out" 2>"$WORK/b.err"; then
    log_fail "B. CONTROL DID NOT FIRE: verify passed over a perturbed generated row"
fi
grep -q 'DRIFT' "$WORK/b.err" || log_fail "B. verify failed but never said DRIFT: $(cat "$WORK/b.err")"
grep -q 'doc-registry.md' "$WORK/b.err" || log_fail "B. the drift report did not name the file"
log_pass "B. a single perturbed row is reported as DRIFT and exits non-zero"

cp "$BACKUP" "$TARGET"
cmp -s "$BACKUP" "$TARGET" || log_fail "B. restore failed -- the target is not what it was"
gen >/dev/null 2>&1 || log_fail "B. verify is still red after restoring the target"
log_pass "B. restored, and verify is green again"

# ---- C. determinism ---------------------------------------------------------
log_test "C. two --write runs are byte-identical"
before="$(sha256sum "$TARGET" | cut -d' ' -f1)"
gen --write >/dev/null 2>"$WORK/c1.err" || log_fail "C. first --write failed: $(cat "$WORK/c1.err")"
one="$(sha256sum "$TARGET" | cut -d' ' -f1)"
gen --write >/dev/null 2>"$WORK/c2.err" || log_fail "C. second --write failed: $(cat "$WORK/c2.err")"
two="$(sha256sum "$TARGET" | cut -d' ' -f1)"
assert_eq "$one" "$two" "C. two --write runs disagree -- the render is not deterministic"
assert_eq "$one" "$before" "C. --write changed a file that verify had just called clean"
log_pass "C. --write is deterministic and idempotent ($one)"

# ---- D. the selftest still carries its controls -----------------------------
log_test "D. --selftest passes and still plants its defects"
if ! gen --selftest >"$WORK/d.out" 2>"$WORK/d.err"; then
    log_error "$(cat "$WORK/d.out")"
    log_fail "D. gen-docs --selftest failed"
fi
grep -q '^FAIL' "$WORK/d.out" && log_fail "D. --selftest exited 0 with FAIL lines in its output"
# Named controls, not a count. A count survives someone deleting one control and adding another.
for want in \
    'planted: an unterminated region is refused' \
    'planted: a nested region is refused' \
    'planted: a close with no open is refused' \
    'planted: an unknown provider is refused' \
    'planted: a perturbed row makes the rewrite differ' \
    'but the SET diff names all 88 dropped rows' \
    'a count floor of 300 PASSES'; do
    grep -qF "$want" "$WORK/d.out" || log_fail "D. the selftest no longer runs the control: $want"
done
log_pass "D. --selftest is green with all $(grep -c '^PASS' "$WORK/d.out") controls present"

# ---- E. the pre-port SET snapshot is intact ---------------------------------
log_test "E. the pre-port row SET is recorded and well-formed"
if ! python3 - "$SNAP" "$WORK/e.txt" <<'PY'; then
import json, sys
snap = json.load(open(sys.argv[1], encoding="utf-8"))
problems = []
if snap.get("format") != 1:
    problems.append("format is %r, expected 1" % snap.get("format"))
if not snap.get("recorded_at_commit"):
    problems.append("recorded_at_commit is empty")
why = "\n".join(snap.get("why") or [])
# The reasoning is part of the artifact. A snapshot whose file does not say WHY a set beats a
# count is a pile of strings the next reader will feel free to regenerate.
for phrase in ("SET", "COUNT", "BEFORE"):
    if phrase.lower() not in why.lower():
        problems.append("the `why` block never mentions %s" % phrase)
providers = snap.get("providers") or {}
if len(providers) < 4:
    problems.append("only %d provider(s) recorded" % len(providers))
for name, entry in sorted(providers.items()):
    keys = entry.get("keys") or []
    if not keys:
        problems.append("%s recorded ZERO rows -- a snapshot of nothing catches nothing" % name)
    if entry.get("rows") != len(keys):
        problems.append("%s says %r rows but lists %d keys" % (name, entry.get("rows"), len(keys)))
    if len(set(keys)) != len(keys):
        problems.append("%s has duplicate keys, so it is not a set" % name)
    if keys != sorted(keys):
        problems.append("%s keys are not in a fixed order, so two diffs are not comparable" % name)
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(problems))
print("\n".join("%s: %d rows" % (n, len(e.get("keys") or [])) for n, e in sorted(providers.items())))
PY
    log_fail "E. the snapshot could not be parsed at all"
fi
if [[ -s "$WORK/e.txt" ]]; then
    while IFS= read -r problem; do log_error "E. $problem"; done <"$WORK/e.txt"
    log_fail "E. the pre-port snapshot is malformed"
fi
log_pass "E. the pre-port snapshot is well-formed"

echo "All gen-docs cases passed."
