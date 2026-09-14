# PLAN: W9 P2 script relocation, remaining legs (scripts/gen, scripts/ops)
Status: draft -- design only, not implemented
Owner: f4da5c2e

## Why

`agent/PLAN-tooling-transformation.md:5730` (box "W9 P2 S, ALONE IN ITS WAVE") is HALF DONE as of its last edit, 2026-09-09 (`0d582b57a`). The `scripts/gates/` leg (125 `check-*.ts` files) and 8 of 10 generators are done and verified. What remains, measured directly against the live tree on 2026-09-14, is smaller and more precisely scoped than the box's original text implies:

- **`scripts/gen/` leg, remaining subject: 2 files.** `scripts/gen-docs.ts` and `scripts/gen-gates-lock.ts` are still at `scripts/` root. `scripts/data/domains.json:143` (`generators` rule) blocks them explicitly: "Same merge queue as `gates`. scripts/gen-docs.ts, scripts/gen-gates-lock.ts, scripts/lib/doc-providers.ts and scripts/lib/doc-regions.ts are W11 and W2 files under active concurrent edit; they move only once those workstreams have handed over."
- **`scripts/ops/` leg, remaining subject: 15 files.** 13 under `scripts/dev/`, 1 under `scripts/docker/` (`build-server.sh`), and `scripts/backup-cutover-preflight.sh` at root. `scripts/data/domains.json:94` (`operator-bash` rule) blocks this on "Driver contract section 2, the `scripts/dev` ownership row: W8 deletes its dead script, W0 and W8 make their edits at the current path, THEN W9 moves the directory. Not before."
- **`scripts/ci/` leg has no subject.** Zero `.cjs` exist anywhere under `scripts/` today (confirmed by direct listing). The box's own "HALF DONE" note already recorded this; nothing changed since. This leg should be formally closed as N/A rather than left open.

This plan covers only the two legs with a real subject. It answers the six cross-reference questions the box was assigned, with everything below independently re-measured against the tree at commit range through 2026-09-14 rather than trusted from the box's prior notes.

Campaign context: `agent/PLAN-tooling-transformation.md:5730` (the box), `:5704` (W9 P2.0, the enforcement gate this leans on), `scripts/gates/check-domain-partition.ts` (clause 1/2/3 enforcement), `scripts/data/domains.json` (the partition), `scripts/data/domain-layout-baseline.json` (the shrink-only baseline, currently 39 entries).

## 0. The baseline's 39 entries are two unrelated problems, not one

`scripts/data/domain-layout-baseline.json` currently lists 39 out-of-place files. Splitting them by owning rule:

- **22 are `incoming-*` rule matches under `.ci/scripts/{autopilot,build/sea-inject,ci,docs,quality,test}`.** These are W7's relocation-into-`scripts/` moves (`.ci/scripts/ci/*.cjs` -> `scripts/ci`, etc.), not W9 P2's job. They are NOT part of this plan's scope and should not be touched by it. (This is also the tree that coupling (a) in the original box -- the `doc-registry-preport.json` / `ci-tree` key coupling -- actually applies to; see section 1 below.)
- **17 are this box's remaining scope**: `scripts/backup-cutover-preflight.sh` (1), 13 files under `scripts/dev/`, `scripts/docker/build-server.sh` (1), `scripts/gen-docs.ts` and `scripts/gen-gates-lock.ts` (2).

So "15 operator scripts" in the box's original text is almost exactly right (15 = 13 `scripts/dev/*` + `scripts/docker/build-server.sh` + `scripts/backup-cutover-preflight.sh`), and the `scripts/gen/` remainder is 2 files, not 10 (8 already moved).

## 1. `scripts/gen-docs.ts:268`'s "MISSING keys are fatal" mechanism, and `doc-registry-preport.json`, re-measured

The citation has drifted: the line is now `scripts/gen-docs.ts:354` ("MISSING keys are fatal to `--diff-snapshot`; ADDED keys are reported as normal growth."), not `:268`. The mechanism (`diffSnapshot()` at `scripts/gen-docs.ts:410`) compares each provider's recorded pre-port key set against its live set; a `missing` key not present in `retired.<provider>` in `scripts/data/doc-registry-preport.json` is printed as `DROPPED` and the run exits 1.

`doc-registry-preport.json` has exactly one provider recorded, `ci-tree` (55 rows), whose keys include `.ci/scripts/ci`, `.ci/scripts/build/sea-inject`, `.ci/scripts/autopilot` (directory row keys). These are the paths the 22 `incoming-*` entries above will vacate when W7's moves land -- that coupling is real, but it belongs to whoever executes the `incoming-*` legs, not to this plan. **Ran `npx tsx scripts/gen-docs.ts --diff-snapshot` directly against the current tree: exit code 1 today**, but the failure is unrelated to either remaining W9 P2 leg -- it is `DROPPED suppressions: .ci/config/bws-unrequested.json`, a pre-existing red the prior session already noted ("`--diff-snapshot` was already exiting 1 before the move began"). `ci-tree` itself reports `ok` (55 recorded, 87 live, 0 unexplained missing). Moving `scripts/gen-docs.ts`, `scripts/gen-gates-lock.ts`, or the 15 operator scripts touches none of `ci-tree`'s recorded keys (none of them are `.ci/scripts/{ci,build/sea-inject,docs,autopilot}` paths), so **coupling (a) does not apply to the two legs this plan covers.** Re-run `--diff-snapshot` before and after each leg's move as a control, but do not expect it to be the mechanism that reds from this work; if it does turn newly red, that is a real finding, not the known pre-existing one.

## 2. `derivedId()`: moving a file does NOT change its gate id

There is one `derivedId()`, in `scripts/lib/gate-header.ts:326` (`scripts/gate-bind.ts` imports it, does not redefine it):

```
export function derivedId(repoPath: string): string {
  const base = (repoPath.split('/').pop() ?? '').replace(/\.(py|sh|ts|cjs|mjs)$/, '');
  if (repoPath.includes('/test/gates/'))
    return `gate-test:${base.replace(/^test[-_]/, '').replace(/_/g, '-')}`;
  return `check:ci-${base.replace(/^check[-_]/, '').replace(/_/g, '-')}`;
}
```

It derives from the **basename only** (`.pop()` on the split), except for one path-substring special case (`/test/gates/`, which none of the 17 remaining files' new paths match: `scripts/gates/`, `scripts/gen/`, `scripts/ops/` are all clear of that substring). Moving `check-foo.ts` from `scripts/` to `scripts/gates/` therefore derives the identical id before and after, which is exactly why the 121 renamed gates in the completed leg needed zero `id:` overrides -- confirmed independently here rather than just re-asserted from the prior note. **For this plan's two legs the ids are anyway mostly explicit, not derived**: `check:ci-gates-lock`, `check:ci-doc-region-parity`, `gen:gates-lock`, `gen:docs` in `scripts/ci-runner/manifest.ts:2200-2293` do not match what `derivedId()` would compute from `gen-docs.ts` / `gen-gates-lock.ts`, meaning they are hand-written `id:` fields already, unaffected by a path change either way. The ids it would derive instead, quoted here inside a fence because they name gates that deliberately do not exist and `check:ci-plan-citations` reads bare ids anywhere else on the line:

```
check:ci-gen-docs
check:ci-gen-gates-lock
```
 **The 15 operator scripts under `scripts/dev/` and `scripts/docker/` have zero `manifest.ts` entries at all** (grepped: no hits) -- consistent with `domains.json`'s own description of them as "no workflow, npm key, run.sh verb or gate invokes them" -- so there is no id-derivation risk there either. Conclusion: item 2's feared "every manifest.ts entry needs its id checked" blast radius does not materialize for either remaining leg.

## 3. Precedent: this box's own history is the mechanics reference

There is no need to reach for a different box (W1P4 or otherwise); the completed `scripts/gates/` and 8-of-10 `scripts/gen/` legs of this same box already establish the mechanics, and they are the precedent to repeat:

- `git mv` per file so history/blame survives and diff shows as `R` renames (121 of 125 in the gates leg were R renames).
- A **fail-closed transform** for relative imports/`__dirname` joins broken by the new directory depth: anything the transform doesn't recognize is reported, not silently passed through. This is how the gates leg caught 11 `path.join(__dirname, '../X')` cases with the `..` embedded inside a longer literal, and how it later caught its own negative-lookbehind bug (`(?<!/)` blocking a live `"$REPO_ROOT/scripts/..."` invocation) by re-grepping without the guard.
- A **whole-file identity proof**: collapsing both the old and new path forms to a sentinel and diffing should leave the file identical, per file moved.
- **Baseline before/after, taken as a copy first**, never read off the gate's own post-hoc arithmetic (the gates leg measured "47 -> 39, exactly the 8 moved, 0 added" this way).
- **Rule text updated in the same commit as the move it describes** -- `domains.json`'s `gates` rule was rewritten from a `stays: false` destination declaration into a `stays: true`, narrowed-`paths`, no-`blockedOn` description of the finished state. The `operator-bash` and `generators` rules need the same treatment once their moves land (see section 6).

## 4. `gates.lock.json`'s real edit surface

Confirmed: `gates.lock.json` is generated, never hand-edited. `package.json:181` -- `"check:ci-gates-lock": "tsx scripts/gen-gates-lock.ts --selftest && tsx scripts/gen-gates-lock.ts"` -- verifies it against `manifest.ts`; `package.json:169` -- `"gen:gates-lock": "tsx scripts/gen-gates-lock.ts --write"` -- is what actually rewrites it. So the real hand-edit surface for both legs is:

1. `scripts/ci-runner/manifest.ts` -- `paths:`/`leaves:` string literals naming the moved files (2 entries reference `scripts/gen-gates-lock.ts`, 1 references `scripts/gen-docs.ts`, all in the `check:ci-gates-lock` / `gen:gates-lock` / `gen:docs` block at `scripts/ci-runner/manifest.ts:2195-2293`; zero entries reference any `scripts/dev/**` or `scripts/docker/**` path, since none are registered).
2. `package.json` -- the `gen:docs` / `gen:gates-lock` / `check:ci-gates-lock` / `check:ci-doc-region-parity` script strings if any hardcode the old path (checked: they invoke by npm script name and `tsx scripts/gen-gates-lock.ts` / `tsx scripts/gen-docs.ts` literally -- both need the path segment updated).
3. Run `npm run gen:gates-lock` -- regenerate, never hand-edit `gates.lock.json`.
4. Run `npm run check:ci-gates-lock` and `npx tsx scripts/gates/check-ci-parity.ts` -- verify drift is zero.

This confirms the task brief's suspicion: the real edit surface for the driver-only files is `manifest.ts` (a handful of literal strings) plus `package.json` (script command strings), not "185 / 159 / 157 references" -- that count was for the much larger, already-completed `scripts/gates/` leg, not what remains here.

## 5. Sub-batching: yes, by leg, and it is already forced by the blockers

The two remaining legs are blocked by two **independent, already-different** external conditions (W11/W2 handover for `scripts/gen`; W8's dead-script deletion plus W0/W8 edits at the current path for `scripts/ops`), so they cannot be executed as one atomic move even if desired -- they will clear at different times. Treat them as two sub-batches:

- **Sub-batch A: `scripts/gen/` leg (2 files).**
- **Sub-batch B: `scripts/ops/` leg (15 files).**

Each gets its own before/after `check:ci-parity`, `check:ci-gate-bind` (or `gen:gates-lock` + `check:ci-gates-lock`), and `check:ci-domain-partition` cycle, exactly as the completed `scripts/gates/` leg did. Do not wait for both blockers to clear before starting either -- whichever clears first should land first, verified independently, so a defect in one sub-batch's rewrite does not block or contaminate the other's review.

**Before starting either sub-batch, re-check the blocker at execution time, not from this document.** `scripts/data/domains.json:99` and `:156` still carry their original `blockedOn` text as of 2026-09-14 (5 days after the box's last edit); that is the authoritative signal that neither has been lifted. If a workstream has since handed over, the correct first step is to update the rule's `blockedOn` field (or remove it) in the same commit as the move, not to leave stale text describing a blocker that no longer applies.

## 6. What breaks beyond the 3 driver-only files, per leg

### 6a. `scripts/gen/` leg (gen-docs.ts, gen-gates-lock.ts)

**The domains.json trap does NOT re-fire here.** The `generators` rule's `paths` already includes `scripts/gen/**` (added 2026-09-09, per its own comment: "THE HOME ITSELF IS THE FIRST PATTERN... the rule declared `scripts/gen` as a destination and matched only files still sitting OUTSIDE it"). Moving these 2 files into a home the rule already recognizes will not produce an `UNCLASSIFIED` finding. Once both files land, flip this rule the same way `gates` was flipped: `stays: false` -> `true`, drop the now-satisfied `blockedOn`, and narrow `paths` to describe the finished state (matching the precedent in section 3).

Functional edits required in the same commit as the move:
- `scripts/ci-runner/manifest.ts:2206`, `:2208`, `:2231` region (`check:ci-gates-lock`), `:2276` (`gen:gates-lock`), `:2287` (`gen:docs`) -- update the 3 literal path strings.
- `package.json:169-170,181` -- the 3 npm script command strings.
- `.ci/scripts/quality/check-gate-id-convention.sh:67,98,126,258` -- prose/error-message references to `scripts/gen-gates-lock.ts`; not path-matching logic, but should move in the same commit per invariant 9 ("comments are the asset").
- `.ci/scripts/test/gates/test-docs-gen.sh:47,51,74` -- `GEN="$REPO_ROOT/scripts/gen-docs.ts"` and 2 error-message/rerun-hint literals. **Functional**: the `[[ -f "$GEN" ]]` existence check would fail loudly (good, not silently green) but still needs updating.
- `.ci/scripts/test/gates/test-doc-region-parity.sh:50,52,106,137,144` -- **functional and the highest-risk item found in this review**: `GEN="$REPO_ROOT/scripts/gen-docs.ts"` (used to run the real generator against a fixture), the `copy_tracked` call at `:137` that explicitly lists `scripts/gen-docs.ts scripts/lib/doc-providers.ts scripts/lib/doc-regions.ts` as fixture inputs ("a file is not a literal inside itself" -- dropping these from that line reproduces exactly the "Cannot find module" failure the file's own comment warns about), and `fixgen()` at `:144` which invokes `"$FIX/scripts/gen-docs.ts"`. All must be updated to the new path in the same change, or this gate's own fixture copy breaks.
- `knip.jsonc:12-36` -- **found in this review, not previously documented anywhere in the campaign, independently verified by the driver.** `scripts/gen-docs.ts` and `scripts/gen-gates-lock.ts` are currently matched as entry points by the root `"scripts/*.ts"` glob at line 12 (they are invoked only via npm script, never imported, so knip needs them declared as entries or it reports them as dead files). `knip.jsonc`'s own comment at lines 32-33 explains why `scripts/gen/` deliberately has NO glob entry (`"scripts/gen/*.ts"`) -- it lists `scripts/gen/generate-third-party-licenses.ts` and `scripts/gen/fetch-directive-snapshot.ts` explicitly instead, "so a genuinely dead file appearing next to them is still reported." Moving `gen-docs.ts` and `gen-gates-lock.ts` out from under the root glob without adding them to this explicit list will make knip report both as unused files. **Add two more explicit entries at `knip.jsonc:34-36`, each with a BLOCKER-shaped comment** (mirroring the existing two: "invoked by `npm run gen:docs`" / "`npm run gen:gates-lock`", never imported).
- Prose-only citations that should move but will not break anything if briefly stale (loud, not silent): `scripts/lib/doc-providers.ts:2`, `scripts/gates/check-doc-region-parity.ts` (14 separate `scripts/gen-docs.ts:NNN` line citations -- these will also need their line numbers re-verified after the file moves, not just its path, since the file's own line count may shift by the same "one more `..`" pattern the gates leg saw), `scripts/gates/check-ci-step-env-parity.ts:416`, `scripts/gates/check-quality-complete.ts:367`, `scripts/gen/gen-manifest.ts:27`.

### 6b. `scripts/ops/` leg (13 files under scripts/dev/, scripts/docker/build-server.sh, scripts/backup-cutover-preflight.sh)

**The domains.json trap DOES fire here and must be fixed before/atomically with the move.** Unlike `generators`, the `operator-bash` rule's `paths` (`scripts/data/domains.json:95-97`: `["scripts/dev/**", "scripts/docker/**", "scripts/backup-cutover-preflight.sh"]`) name only the CURRENT locations -- there is no `"scripts/ops/**"` entry yet (independently confirmed by the driver: grepping `domains.json` for `scripts/ops` finds only the rule's own `"home": "scripts/ops"` declaration, never in `paths`). `scripts/gates/check-domain-partition.ts`'s clause 1 (total classification) is **enforcing**, not baselined: the moment these 15 files land under `scripts/ops/`, they stop matching any rule and every one becomes `UNCLASSIFIED`, hard-failing the gate. This is precisely the "finish-line trap" the `generators` rule's own comment names by analogy ("the same line will be needed for `scripts/ops` when the operator-script leg lands") -- and it has not yet been paid down. **The first edit in this sub-batch, in the same commit as the `git mv`, must add `"scripts/ops/**"` to `operator-bash`'s `paths`** (or replace the three old-location globs with it, mirroring how `gates`' rule was narrowed to its final-state form once its move completed).

Manifest/package.json: **no entries exist for any of these 15 files** (confirmed by direct grep) -- this leg is lighter on the 3 driver-only files than the box's original framing suggested. The real work is the `domains.json` rule fix above plus the following, all already named as `breaksIfMoved` in `scripts/data/domains.json:104-112` and independently re-confirmed here at current line numbers:

- `.ci/scripts/security/shfmt.sh:107-116` -- `for dir in scripts/dev scripts/docker; do if [[ -d "$dir" ]]; ...` -- **silently green**: if the directories no longer exist at the old paths, this loop simply finds nothing to format and exits clean. Must be repointed to `scripts/ops`.
- `.ci/scripts/quality/check-silent-failure-patterns.sh:68` -- `SCAN_DIRS=(".ci/scripts" "scripts/dev")` -- **silently green** for the same reason. Must be repointed.
- `scripts/gates/check-worker-secret-names.ts:66` -- `{ file: 'scripts/dev/deploy-bench.sh', floor: 20 }` -- functional, loud failure (file-not-found) if not updated, but still required.
- `.ci/scripts/quality/check_bws_map.py:121` -- `RENAME_TABLE = ROOT / "scripts" / "dev" / "secret-rename.py"` -- functional, loud failure if not updated.
- `.ci/scripts/test/gates/test-scrub-sentinel-empty.sh:40,56`, `.ci/scripts/test/gates/test-worktree-devbox-teardown.sh:42`, `.ci/scripts/test/gates/test-bws-map.sh:40,58`, `.ci/scripts/test/gates/test-vacuity-floors.sh:115` -- all invoke or reference `scripts/dev/*` by literal path; functional, must move with the files.
- `.ci/legacy/run-legacy.sh:488-489` (a **second**, independent shfmt-style sweep: `if [[ -d "scripts/dev" ]]; then find scripts/dev -name "*.sh" ...`) and `:793` (`"$ROOT_DIR/scripts/dev/worktree.sh" "$@"`, a live dispatch target, not dead code -- `domains.json`'s own `operator-bash` exceptions note this dispatch but cites a stale line number (`:1066`; actual is `:793` today, itself a small instance of the citation-drift problem `agent/PLAN-citation-fragility.md` documents). Both need updating; the `:488-489` block is a second silently-green candidate not previously called out anywhere in the campaign text.
- `Dockerfile:12,32` -- comment-only references to `scripts/docker/build-server.sh`; update for accuracy, no functional effect (this is also the thing that keeps `build-server.sh` out of `check-dead-bash`'s findings today, per `domains.json`'s own note -- worth re-verifying `check-dead-bash` still sees a live caller after the move, since a dead-bash false-positive here would be a new, self-inflicted finding).
- Prose-only (comments, no functional effect, should move for hygiene): `scripts/gates/check-dead-bash.ts:13`, `scripts/gates/check-env-credential-drift.ts:41`, `scripts/gates/check-builder-env-contract.ts:57,661`, `scripts/lib/env-file.sh:38`.

No CI workflow YAML references any of these 15 files (checked `.github/workflows/*.yml` directly; the only `scripts/docker/`-shaped and `scripts/dev/`-shaped hits found were in `.ci/scripts/docker/` -- an unrelated, pre-existing tree under `.ci/scripts/`, not `scripts/docker/`, confirmed by the differing prefix). No `census-plan-record.jsonl` or `agent/INDEX.md` reference needs updating -- both are machine-generated by their own tools (`npm run check:ci-plan-record -- --update` for `INDEX.md`) and describe plan-file metadata, not script paths.

## 7. Verification checklist, per sub-batch

1. Before: `git ls-files scripts | wc -l`, copy of `scripts/data/domain-layout-baseline.json`, `npx tsx scripts/gates/check-domain-partition.ts` output, `npx tsx scripts/gen-docs.ts --diff-snapshot` exit code (expect 1, from the pre-existing unrelated `bws-unrequested.json` drop -- confirm no NEW dropped keys after the move).
2. `git mv` every file in the sub-batch.
3. Apply the fail-closed relative-import/path rewrite to every moved file (one more `..` for files landing one directory deeper than their old parent, same technique as the gates/generators legs).
4. Edit `scripts/data/domains.json`'s rule for this leg: for `scripts/ops`, add `"scripts/ops/**"` to `paths` BEFORE or IN the same commit as the move (mandatory, see 6b); for `scripts/gen`, no `paths` edit needed, but flip `stays`/drop `blockedOn` once done.
5. Edit the functional-breakage list from section 6a or 6b for this leg (manifest.ts + package.json + knip.jsonc for the gen leg; domains.json + shfmt.sh + check-silent-failure-patterns.sh + run-legacy.sh + the 4 test-*.sh files + check-worker-secret-names.ts + check_bws_map.py for the ops leg).
6. Run, in order: `npm run gen:gates-lock` (only if manifest.ts changed -- the ops leg has no manifest entries, so this step is a no-op there), `npm run check:ci-gates-lock`, `npx tsx scripts/gates/check-ci-parity.ts`, `npx tsx scripts/gates/check-domain-partition.ts` (expect the moved files to drop out of `outOfPlace`, nothing new to appear), `npx tsx scripts/gates/check-doc-region-parity.ts` (gen leg only), `npx tsx scripts/gen-docs.ts --diff-snapshot` (both legs, as a control -- expect the SAME pre-existing exit-1 finding, nothing new).
7. `npx tsx scripts/gates/check-domain-partition.ts --write-baseline` to drain this leg's entries out of `scripts/data/domain-layout-baseline.json` (refuses to add, so a botched move that leaves a stray out-of-place file will be visible as a refusal here, not a silent partial credit).
8. Whole-file identity proof on every moved file (sentinel-collapse diff against the pre-move content), per the section 3 precedent.
9. `.ci/scripts/security/shfmt.sh`, `.ci/scripts/quality/check-silent-failure-patterns.sh`, and the 6 test-*.sh files from section 6b: run each directly against the post-move tree and confirm the file counts they report did not silently drop to zero for the ops leg.

## Tasks

- [ ] Re-check `scripts/data/domains.json:99` (`operator-bash`) and `:156` (`generators`) blocker status live at execution time; do not start either sub-batch until its blocker is confirmed cleared by whoever owns W8/W0/W11/W2's handover.
- [ ] Sub-batch A (`scripts/gen/`, 2 files): move `scripts/gen-docs.ts` and `scripts/gen-gates-lock.ts` into `scripts/gen/`, with the manifest.ts/package.json/knip.jsonc/test-docs-gen.sh/test-doc-region-parity.sh/check-gate-id-convention.sh edits from section 6a, all in one commit.
- [ ] Sub-batch A verification: `check:ci-gates-lock`, `check:ci-parity`, `check:ci-doc-region-parity`, `check:ci-domain-partition`, `gen-docs.ts --diff-snapshot` (control), all green or at the known pre-existing red only.
- [ ] Flip `domains.json`'s `generators` rule to its finished-state form (`stays: true`, `blockedOn` removed) once sub-batch A lands.
- [ ] Sub-batch B (`scripts/ops/`, 15 files): add `"scripts/ops/**"` to `domains.json`'s `operator-bash.paths` in the same commit as the `git mv` of all 15 files (13 under `scripts/dev/`, `scripts/docker/build-server.sh`, `scripts/backup-cutover-preflight.sh`), plus the shfmt.sh / check-silent-failure-patterns.sh / run-legacy.sh / 4 test-*.sh / check-worker-secret-names.ts / check_bws_map.py edits from section 6b.
- [ ] Sub-batch B verification: `check:ci-domain-partition` (expect zero UNCLASSIFIED, not a hard-fail), a direct re-run of shfmt.sh and check-silent-failure-patterns.sh confirming their scan counts did not drop, the 4 affected test-*.sh gate tests passing against the new path.
- [ ] Flip `domains.json`'s `operator-bash` rule to its finished-state form (`stays: true`, `paths: ["scripts/ops/**"]`, `blockedOn` removed) once sub-batch B lands.
- [ ] Drain `scripts/data/domain-layout-baseline.json` via `--write-baseline` after each sub-batch (expect it to fall from 39 to 37 after A, to 22 after B -- the 22 `incoming-*` entries are out of this plan's scope and belong to W7).
- [ ] Formally close the `scripts/ci/` leg as N/A in the parent box's next status update: zero `.cjs` files exist under `scripts/` to move.
- [ ] Re-run `npx tsx scripts/gen-docs.ts --diff-snapshot` after both sub-batches and confirm the only red is the pre-existing, unrelated `bws-unrequested.json` drop (or that it has since been fixed by someone else, in which case this should exit 0).

### Critical Files for Implementation

- /home/developer/console/scripts/data/domains.json
- /home/developer/console/scripts/gates/check-domain-partition.ts
- /home/developer/console/scripts/ci-runner/manifest.ts
- /home/developer/console/package.json
- /home/developer/console/knip.jsonc
- /home/developer/console/.ci/scripts/test/gates/test-doc-region-parity.sh
- /home/developer/console/.ci/scripts/security/shfmt.sh
- /home/developer/console/.ci/scripts/quality/check-silent-failure-patterns.sh
