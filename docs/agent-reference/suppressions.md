<!-- Split out of CLAUDE.md. CLAUDE.md carries the standing rules that must be
obeyed every turn; this file is lookup material, read when the thing it
describes actually happens. Keep the pointer line in CLAUDE.md in sync. -->

# Suppression mechanisms and the BLOCKER convention

Every escape hatch in the repo (allowlists, blocklists, overrides, ignore lists) must carry a substantive `BLOCKER:` comment. CI enforces the presence and quality of each BLOCKER through a shared validator; this is the single escape mechanism — no lazy `# no fix` or `# tbd` suppressions.

### When a suppression is the wrong answer

**Suppressions are for when the alternative is worse. Reach for one only after
establishing that.** The test is not "is this annoying to fix" — it is whether the
BLOCKER reason you are about to write is *true*.

A suppression whose stated reason does not hold is worse than no suppression at
all, because the next reader inherits a false justification and has no way to tell
it apart from a real one. That reader will not re-derive it; the whole point of the
convention is that they trust it.

Worked example (2026-08-05). A Go dependency bump deleted an API renet used, and
blocklisting the module at its 0.x line looked reasonable: it would keep emitted
telemetry byte-identical while the migration waited. Checking what actually flowed
through the call site showed every attribute was already a string, so the "keeps
behaviour identical" reason was vacuous — there was no behaviour to preserve. The
3-line migration was strictly better, and the suppression would have parked an
untrue reason in the tree indefinitely. **Verify the reason before you write it,
the same way you would verify a gate's finding.**

### Current sites

**WHICH mechanisms exist is derived, not listed here.** The authority is the `suppressions`
region of [`scripts/data/doc-registry.md`](../../scripts/data/doc-registry.md), rewritten from
the tree by `npx tsx scripts/gen-docs.ts --write`: every tracked non-source, non-prose file
carrying a `BLOCKER:` line, with its comment form. A new allowlist appears there the moment it
exists, and `gate-test:docs-gen` fails if the region has drifted from the tree.

The table below is the part that CANNOT be derived, and it is deliberately narrower: which
script READS each mechanism, and the per-mechanism liveness arrangements. The generator refuses
to compute the reader column, and the reason is measured rather than aesthetic -- a
grep-for-the-basename version was built and observed flipping mid-run when an unrelated peer
session staged a file, so the cell churned on edits that touched no suppression at all. Read
this table for the notes; read the derived region for the inventory. **It is not exhaustive, and
must not be read as a census** -- a mechanism absent from these rows is not thereby unknown to
the repository.

**Where they live.** Fifteen of these files sat at the repository root until W4 P2 moved them
into `.ci/policy/` (2026-09-06). `scripts/lib/policy-paths.ts` is the single seam that answers
where one is; `.ci/policy/README.md` carries the predicate for what belongs there and the
recorded reason `.ci-trigger` stayed at the root. Readers still name them by BARE NAME through
that seam, so a grep for `.deps-upgrade-blocklist` will find the name in code that is correct.

| Mechanism | File | Reader |
|---|---|---|
| Prod npm audit allowlist | `.ci/policy/.audit-prod-allowlist` | `.ci/scripts/security/audit.sh` |
| Dev npm audit allowlist | `.ci/policy/.audit-allowlist` | same |
| npm dep upgrade blocklist | `.ci/policy/.deps-upgrade-blocklist` | `scripts/check-deps.ts` |
| Go dep upgrade blocklist | `.ci/policy/.go-deps-upgrade-blocklist` | `.ci/scripts/quality/check-go-deps.sh` |
| Embed-asset upgrade blocklist | `.ci/policy/.embed-assets-upgrade-blocklist` | `scripts/check-embed-asset-freshness.ts` |
| GitHub Actions upgrade blocklist | `.ci/policy/.actions-upgrade-blocklist` | `scripts/check-actions.ts` |
| Breakpoint drift acceptance | `.ci/breakpoint/.breakpoint-drift-accept` | `.ci/breakpoint/scripts/check-breakpoint-drift.sh` |
| Dead-bash discovery allowlist | `.ci/policy/.dead-bash-allowlist` | `scripts/check-dead-bash.ts` |
| CI parity exemptions (direction-tagged) | `.ci/policy/.ci-parity-exempt` | `scripts/check-ci-parity.ts` |
| `package.json` overrides | `package.json`: `overrides` + `_overridesReasons` | `scripts/check-overrides-reasons.ts` |
| knip suppressions (`ignore*` arrays) | `knip.jsonc` (inline `// BLOCKER:` comments) | `scripts/check-knip-blockers.ts` |
| Plan-file housekeeping exemptions | `.ci/policy/.plan-housekeeping-allowlist` | `.ci/scripts/quality/check-plan-housekeeping.sh` |
| Runner sizing exemptions | `.ci/policy/.runner-advice-allowlist` | `.ci/scripts/quality/check_runner_advice.py`. Liveness is enforced **in-gate** rather than by a `check-suppression-liveness.ts` probe, because the oracle (does this entry still suppress a MOVE_TO_SLIM finding?) *is* the comparison the gate already performs; same arrangement as `.profiler-coverage-allowlist`. Note the gate's own bootstrap rule, which is a suppression of a different kind: while `runner-sizing-baseline.json` is **pristine** (`refreshed_at` null and zero jobs) the gate warns and exits 0, because nothing has been measured yet; every other below-floor shape is a hard refusal, and `--refresh` will not write a baseline below the 5-job floor. Seeded therefore always means enforced, which is the only reason the pristine pass is not a permanent hole. The baseline carries `"format": 1`; an unknown, missing or corrupt version and any malformed job record are refused by name (naming the job and the field), never as a traceback, and `--refresh` refuses to merge into a version it cannot read |
| syncpack source exclusions | `.ci/config/syncpack-source-exclusions.json` | `.ci/scripts/quality/check_syncpack_sources.py`. A manifest declaring dependencies must be matched by a `source` glob or excluded here with a `BLOCKER:` reason; eight are, deliberately (two tutorial sample apps whose versions are part of the lesson text, four independently deployed Workers, `private/account/e2e`, and `private/account/web`'s own React tree). Liveness is **in-gate** rather than a `check-suppression-liveness.ts` probe, on the `.runner-advice-allowlist` precedent: the oracle (is this path still a tracked manifest that declares dependencies?) *is* the comparison the gate already performs, and it refuses an entry that suppresses nothing. The gate also refuses outright — CANNOT VERIFY, not a pass — when a directory its config names is absent, because it is about a SUBMODULE and an unchecked-out submodule turns a correct exclusion into a "dead entry" finding |
| Language-policy exemptions | `.ci/policy/.language-policy-allowlist` | `.ci/scripts/quality/check_language_policy.py`. Ruling 7 (`docs/ci-overhaul/04-decisions.md`) makes `.ci` and `.claude` Python; this list is the bash that survives that ruling permanently, and it is NOT the backlog. The 521 files still awaiting the port are frozen in `.ci/config/language-policy-baseline.json`, which is generated, shrink-only and deliberately not in `.ci/policy/` (it fails the README's predicate clauses 1 and 2: it is a measurement, not a decision, and its entries carry no reason). Two entry kinds because the oracle differs: a `tree:<prefix>/` entry is live while the directory still holds bash, a `shim:<path>` entry is live while the file exists AND its effective body is still ONE line -- a shim that grew into a program is refused by name, because "one-line shim" was the whole of its justification. Liveness is enforced **in-gate** on the `.runner-advice-allowlist` precedent: the oracle (does this entry still cover a real bash file?) *is* the comparison the gate already performs, so a probe in `check-suppression-liveness.ts` would be a second implementation of one question. The BLOCKER QUALITY rule is not reimplemented either: the gate shells out to `.ci/scripts/lib/blocker-validator.sh` and prints what it says, because that rule already has three implementations and `test-blocker-golden-corpus.sh` exists to collapse them, not to grow a fourth |

### Format

**Comment-friendly files** (shell / conf / txt):
```
# BLOCKER: <reason explaining who pins what / why fix cannot be taken / when to revisit>
<entry>
```
A blank line resets the tracked BLOCKER, so a single BLOCKER covers a grouped list until the next blank line.

**Inline** (`.deps-upgrade-blocklist` / `.go-deps-upgrade-blocklist`):
```
package-name  # BLOCKER: <reason>
```

**Direction-tagged** (`.ci-parity-exempt`), because parity is a two-way relation
and the two directions need different justifications:
```
# BLOCKER: <reason>
ci-only  .ci/scripts/quality/check-branch.sh
```
`ci-only` means CI runs it and the local gate set deliberately does not;
`local-only` is the reverse. The liveness oracle differs per direction, so the
tag is load-bearing rather than documentation: a `ci-only` entry is live while
some workflow still invokes it, and a `local-only` entry is live while the local
gate set still runs it. The shared parser takes the first whitespace-separated
token, so `scripts/check-ci-parity.ts` and the liveness probe both split the
second column off explicitly.

**JSONC files** (knip.jsonc) use real `// BLOCKER: <reason>` comments with the same
group semantics as shell files: one BLOCKER covers the entries after it until a blank
line or the end of the array. Staleness of knip ignore entries is enforced by knip
itself (`--treat-config-hints-as-errors`), not by the BLOCKER validator.

**JSON files** (no comment support) use a parallel `_reasons` object with identical keys:
```jsonc
"overrides":         { "follow-redirects": "^1.16.0" },
"_overridesReasons": { "follow-redirects": "BLOCKER: axios pins <1.16.0; 1.16.0 fixes GHSA-r4q5-vmmm-2653" }
```

### Quality rules

A BLOCKER reason must be at least 30 characters (after normalization) and must not match any phrase in the banned-phrase list (`no fix`, `tbd`, `todo`, `ok`, `ack`, `later`, `will fix`, `dev only`, etc.).

Full banned list + implementation: `.ci/scripts/lib/blocker-validator.sh` (bash) / `scripts/lib/blocker-validator.ts` (TypeScript). Keep the two in sync when modifying.

### Liveness: is the entry still needed?

The BLOCKER convention proves a reason **exists**. It cannot prove the reason is
still **true**. Those are different failures, and the second one is invisible:
Electron was removed from the product and **101 suppression entries justified by
electron dependency chains stayed behind** — the entire `.audit-allowlist` (18)
plus 83 in `.audit-prod-allowlist` — because nothing checked whether the
suppressed thing still existed.

`npm run check:ci-suppression-liveness` (`scripts/check-suppression-liveness.ts`)
closes that half. One **probe** per mechanism, each pairing the suppression file
with the *oracle* that decides whether an entry is load-bearing:

| Mechanism | Oracle | Tier |
|---|---|---|
| `.ci/policy/.deps-upgrade-blocklist` | name declared in some `package.json` | fail |
| `.ci/policy/.go-deps-upgrade-blocklist` | module in a `go.mod` `require` | fail |
| `.ci/policy/.embed-assets-upgrade-blocklist` | base is a renet Dockerfile `ARG` **and** a known source | fail |
| `.ci/policy/.actions-upgrade-blocklist` | action has a `uses:` under `.github` | fail |
| `package.json` `overrides` | key resolves to a `package-lock.json` node | **warn only** |
| `.ci/policy/.dead-bash-allowlist` | glob root exists / dispatch prefix matches a function / manual file exists | fail |
| `.ci/policy/.ci-parity-exempt` | a `ci-only` entry is still invoked by some workflow | fail |
| `.audit-*` | advisory present in `npm audit` | fail — owned by `audit.sh` |
| `knip.jsonc` | — | knip self-detects via `--treat-config-hints-as-errors` |

Three rules this gate is built on, all learned the hard way:

- **No oracle, no verdict.** Each probe declares a `minUniverse` floor and skips
  loudly when its oracle returns less than that — the generalization of the
  `total_vulns > 0` guard in `audit.sh`. It is deliberately NOT a ratio ("all
  entries condemned ⇒ suspicious"): that would have silenced the electron
  cleanup, which was right about 101 of 101 entries.
- **Overrides warn, never fail, and are never auto-removed.** An npm override is
  prophylactic as much as reactive — it constrains what npm may resolve
  *tomorrow*. "Absent from the lockfile today" is not proof it is dead. Start its
  reason with `BLOCKER: preventive —` to opt out of the warning permanently.
- **Offline by construction.** Every oracle is a fact about the current
  checkout, so a verdict can only change in the same commit that changes the
  repo. No probe may consult a registry, publish date, or version comparison —
  that is what `minimum-release-age` deferral exists to prevent elsewhere.

### Adding / extending

- **New entry to an existing list**: prepend a `# BLOCKER: <reason>` line. The validator tells you exactly what to add when the gate fails.
- **New suppression mechanism**: (a) parse the list via the shared library's `parse_blockered_list` / `parseBlockeredList`; (b) validate via `verify_all_blockers` / `verifyAllBlockers`; (c) add a gate test under `.ci/scripts/test/gates/test-<mechanism>.sh` modelled on `test-overrides-reasons.sh`; (d) register a liveness probe in `scripts/check-suppression-liveness.ts`, or state explicitly why the mechanism cannot have one (some genuinely cannot — `.cli-i18n-orphan-allowlist` holds runtime-assembled key *prefixes*, so proving one dead needs exactly the static analysis the allowlist exists to escape).

### Age policy (planned, not yet enforced)

The shared library `.ci/scripts/lib/age-check.sh` provides `check_entry_age` which warns at 180 days and fails at 365 days. Not yet wired into every reader — planned for a follow-up.

### Running the gate tests locally

```bash
npm run test:quality-gates   # runs every .ci/scripts/test/gates/test-*.sh
npm run check:ci-security-audit       # the BLOCKER-gated npm audit
npm run check:ci-overrides-reasons    # the BLOCKER-gated package.json overrides
```
