# PLAN: the scope gate's false-line assertion is locale-dependent, not key-dependent
Status: draft
Owner: 854ac1c6
Updated: 2026-08-26

## 0. Verdict, re-verified in this pass

| claim | evidence |
|---|---|
| `JOB_SURFACES` DOES contain `e2e_k8s_multinode` | scope-map.cjs:280 is `VM_E2E_JOB_KEYS`; :287 spreads it into `JOB_SURFACES` |
| `e2e_k8s_multinode` is an independent job, not a modifier | ct-tests.yml:961/:963/:1132; ci.yml:173,:917 |
| expected and actual are the SAME 17 keys | full failure block, both sides |
| they differ only in ORDER | `run_e2e_k8s` vs `run_e2e_k8s_ceph` transposed |
| cause is glibc collation, not the map | `LC_ALL=C bash <test>` = 8/8 PASS; bare = FAIL (re-verified independently) |
| CI is green | ci-quality.yml:1413 `quality-security` on ubuntu-latest (codepoint locale) |
| pre-existing | both sort sites blame to 4ed24686a (2026-07-31); ancestor of HEAD |
| production code is correct | scope-shadow.sh:234-244 sorts only in JS; emitter untouched by this fix |

Root cause: test-scope-gate-outputs.sh:254 uses a bare `sort`, comparing against
a node `.sort()`-derived list built at :187-196. Under en_US.UTF-8 glibc ignores
`=` and `_` at the primary collation level, so `run_e2e_k8s_ceph=false` sorts
before `run_e2e_k8s=false`. Node sorts by UTF-16 code unit, where the prefix wins.

**Re-verified independently in this session before implementation**: `locale -a`
confirms both `C.utf8` and `en_US.utf8` exist on this host; bare `bash <test>`
exits 1, `LC_ALL=C bash <test>` exits 0 with all 8 cases passing; `scope-map.cjs`
lines 274-287 read exactly as the finding states.

## 1. Fix (one file, two hunks)

### 1a. `.ci/scripts/test/gates/test-scope-gate-outputs.sh:254` — MANDATORY

Replace:

    actual="$(grep '^run_[a-z0-9_]*=false$' "$OUTFILE" | sort || true)"

with:

    # LC_ALL=C IS LOAD-BEARING, not tidiness. EXPECTED_FALSE is ordered by
    # node's Array.prototype.sort(), which is UTF-16 CODE UNIT order. A bare
    # `sort` uses the ambient locale, and glibc's en_US.UTF-8 collation ignores
    # `=` and `_` at the primary level: `run_e2e_k8s_ceph=false` then collates
    # as "rune2ek8scephfalse" and lands BEFORE `run_e2e_k8s=false`, while node
    # puts the shorter prefix first. Same 17 keys, different order, and the
    # assertion reds with a diff that reads like a missing key.
    #
    # It was green in CI and red on every developer machine with a UTF-8
    # collating locale, for 26 days: ubuntu-latest runs under a codepoint
    # locale, so CI never saw it. e2e_ceph/e2e_ceph_workers has the identical
    # prefix shape and does NOT diverge (there "false" < "workers" under both
    # orderings), which is why exactly one pair in eighteen exposes this.
    actual="$(grep '^run_[a-z0-9_]*=false$' "$OUTFILE" | LC_ALL=C sort || true)"

### 1b. `.ci/scripts/test/gates/test-scope-gate-outputs.sh:190-194` — HARDENING

Move `.sort()` AFTER `.map()` so both sides sort the identical byte strings:

        Object.keys(JOB_SURFACES)
          .filter((k) => !JOB_SURFACES[k].includes("www"))
          .map((k) => `run_${k}=false`)
          .sort()

Add above the node block:

    # Sorted AFTER the `run_<k>=false` suffix is applied, so this side and the
    # `LC_ALL=C sort` below are byte-order sorts over the SAME strings rather
    # than two sorts that merely agree today. Sorting the bare keys first is
    # not equivalent in general: `=` is 0x3D, below `_` (0x5F) and letters but
    # ABOVE the digits, so a future key pair like `foo` / `foo0bar` would
    # transpose between the two forms.

Verified today: both forms produce byte-identical output for the current 18-key
set, and `LC_ALL=C sort` is a fixed point of the JS bytewise order. 1b changes
nothing now; it removes the accidental-agreement dependency.

DO NOT CHANGE: scope-map.cjs (nothing wrong), scope-shadow.sh (nothing wrong),
WORKFLOW_CONTRACT_KEYS (already correct, its case passes today).

## 2. Controls (.claude/skills/testing/gates.md — plant, fire red, restore green)

test-gate-anti-vacuity.sh:249-262 records that this file is deliberately NOT
registered there and that its controls are INLINE, one per case. Keep that
shape: these three are run by hand at implementation time and their results are
recorded in the commit message, not added as new registrations.

C1 — THE LOCALE CONTROL (proves the fix is exactly the collation)
  before fix:  LC_ALL=en_US.UTF-8 bash <test>  => RED, transposed k8s pair
               LC_ALL=C           bash <test>  => GREEN, 8/8
  after fix:   LC_ALL=en_US.UTF-8 bash <test>  => GREEN, 8/8
               LC_ALL=C           bash <test>  => GREEN, 8/8
               bash <test>                     => GREEN, 8/8
  Available locales on this host: C.utf8, en_US.utf8 (`locale -a`).

C2 — MISSING-KEY PLANT (proves the assertion still detects a real emitter defect)
  The fixture copies $REPO_ROOT/.ci/scripts/ci wholesale (:93), so the plant
  goes in the REAL file and is reverted by hand afterwards. NEVER by
  git checkout/restore/stash (CLAUDE.md rule 1 — the tree holds other sessions'
  work).

  In .ci/scripts/ci/scope-shadow.sh:240, temporarily:
      for (const key of Object.keys(JOB_SURFACES).filter((k) => k !== "e2e_k8s_ceph")) {
  Expect: 16 false lines, case (a) RED naming the missing key. This targets
  precisely what the sorted comparison is FOR — set equality of key names — and
  it does not trip the drift refusal at :234-237, which reads plan.jobs rather
  than the emitted lines.
  Then restore `for (const key of Object.keys(JOB_SURFACES)) {` by hand and
  re-run: GREEN.

C3 — EMISSION-ORDER PLANT (must STAY GREEN — proves set-based, not order-based)
  In .ci/scripts/ci/scope-shadow.sh:240, temporarily:
      for (const key of [...Object.keys(JOB_SURFACES)].reverse()) {
  Expect: still GREEN. $GITHUB_OUTPUT is a key=value map and emission order is
  not part of the contract; if this reds, the test has regained an order
  dependency it must not have. Restore by hand.

  After C2 and C3, `git diff .ci/scripts/ci/scope-shadow.sh` MUST be empty.

Also keep unchanged: the zero-lines emitter control at :247-251 (and its
ordering note at :236-245 — it must keep running BEFORE the collection).

## 3. Blast radius

Zero on CI scheduling. The fix touches one test file and cannot change which
jobs run: the emitter, scope-map and every run_* value are untouched. The only
behavioural change is that the gate now fails/passes identically under every
locale instead of only under a codepoint one.

## 4. Siblings (swept, one latent)

Enumerated every bare `sort` in .ci/scripts/ci, .ci/scripts/test/gates,
.ci/scripts/quality, .ci/scripts/build, scripts/. Ran the four read-only
gate-test candidates under en_US.UTF-8: test-review-labels, test-ci-trace-branch,
test-breakpoint-drift, test-shrink-only-composition — ALL PASS.
  - test-scope-engine.sh:626-627 — same locale both sides, diagnostic only. Safe.
  - check-renet-tier-map.sh:67-68 — same locale both sides. Safe.
  - .ci/scripts/quality/check-profiler-coverage.sh:350 — LATENT: bare `sort`
    compared against the literal `interval=7,runner-label=ubuntu-slim,`. Same
    shape, correct today only because `i` < `r` under both orderings. Optional
    one-word hardening (`| LC_ALL=C sort`) in this same change; no behaviour
    change, no control needed since nothing is currently broken. If it is
    deferred, it must be recorded, not dropped.

No new gate is proposed for the class. Most bare `sort` calls in this repo are
dedupe or same-locale-both-sides and a grep-based gate would be noise. The
durable record belongs in docs/agent-reference/TRAPS.md instead (§5).

## 5. Documentation

Add to docs/agent-reference/TRAPS.md — this is squarely a TRAPS shape ("a check
that cannot fail where you are looking"): a gate green in CI for 26 days and red
on every developer machine, because ubuntu-latest collates by codepoint and a
UTF-8 desktop locale does not. Rule for future authors: any shell `sort` whose
output is compared against a list ordered by node/jq/python/a hand-written
literal must be `LC_ALL=C sort`. Cite test-scope-gate-outputs.sh:254 as the
measured instance.

## 6. Execution order

1. Apply 1a and 1b.
2. Run C1 (both locales, and bare) — 8/8 green each way.
3. Run C2: plant, RED, restore by hand, GREEN, `git diff` on scope-shadow.sh empty.
4. Run C3: plant, GREEN, restore by hand, `git diff` empty.
5. Optional 4's latent sibling.
6. Add the TRAPS.md entry.
7. `npm run check:ci-parity` (wiring untouched, but the manifest names this file
   at scripts/ci-runner/manifest.ts:3972 and parity is cheap).
8. Record C1/C2/C3 results in the commit message.

## 7. Packaging

RIDE PR #577. Reasoning: the fix touches NO production code (scope-map.cjs and
scope-shadow.sh are both correct and unmodified), so the risk argument for a
separate branch does not apply — a test-only comparison-collation fix carries no
scheduling risk to bundle away from #577's release-gating work. It is also
actively useful to #577: `npm run ci` currently fails locally for anyone on a
UTF-8 collating locale, on a gate unrelated to their work, and fixing it removes
a false red from #577's own verification loop. File-set disjointness confirmed
(`git log origin/main..HEAD -- <the three files>` is empty), so no merge
contention either way.

## Critical files

- `.ci/scripts/test/gates/test-scope-gate-outputs.sh` (the only file that
  changes: lines 190-194 and 254)
- `.ci/scripts/ci/scope-shadow.sh` (line 240 — planted-defect site for C2/C3
  only; must end byte-identical)
- `.ci/scripts/ci/scope-map.cjs` (lines 274-287 — verified correct, do not
  modify; read to confirm `VM_E2E_JOB_KEYS` feeds `JOB_SURFACES`)
- `docs/agent-reference/TRAPS.md` (new entry, §5)
- `.ci/scripts/quality/check-profiler-coverage.sh` (line 350 — optional latent
  sibling hardening)
