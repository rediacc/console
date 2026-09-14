# PLAN: W7P4-W docker sub-slice — cut the 3 already-ported docker scripts over from bash to Python
Status: draft — design only, not implemented

## Why

A writer dispatched to add `---- gate ----` headers to
`.ci/rediacc_ci/docker/{cleanup_staging,create_manifest,retag_image}.py` correctly
refused: their bash twins carry no gate header and are not CI quality gates at
all. They are direct workflow `run:` targets and a release-script forwarder that
perform REAL production mutations against GHCR (image manifest pushes, tag
promotions, and a package-version DELETE). Their real cutover is W7P4-W's job
("flip 215 distinct scripts / 348 call sites from bash to their ported Python
equivalents") — this plan scopes and sequences exactly that, for this one
disjoint, fully-ported sub-slice, and explicitly declines to attempt the rest of
W7P4-W's surface in the same box (see §6).

Campaign context: `agent/PLAN-tooling-transformation.md:582` (W7P4-W box),
`:495` (W7P4-Q, the sibling quality-gate cutover convention, not directly
applicable here since these 3 are not gates), `:2326-2362` (the 28th porting
wave that produced these 3 ports, 2026-09-13/14, 99/99 differential tests, all
3 ledgers K=5, real defects found and pinned), `:508` and `:6263` (the
`staging_tag_guard` permanent-red ledger, excluded for cause — read before
assuming `cleanup_staging.py`'s cutover is simple; see §3).

## 1. What the existing proof covers, and what it does not

`.ci/rediacc_ci/docker/__init__.py`'s docstring states this precisely and is
the load-bearing citation for this whole plan:

> "Every one of these three talks to a REGISTRY. The differential drives both
> sides against recording fakes for `docker` and `gh` on a scratch PATH...
> Nothing in this package has ever been run against a real registry from a
> test, and nothing here should be."

Measured directly in this pass:

| script | port | twin | differential | K=5 ledger |
|---|---|---|---|---|
| `cleanup-staging.sh` | `.ci/rediacc_ci/docker/cleanup_staging.py` (379 lines) | 135 lines | `test_docker_cleanup_staging.py` | `.ci/shadow/w7p6-cleanup-staging.observations.jsonl`, **5 rows** |
| `create-manifest.sh` | `.ci/rediacc_ci/docker/create_manifest.py` (370 lines) | 173 lines | `test_docker_create_manifest.py` | `.ci/shadow/w7p6-create-manifest.observations.jsonl`, **5 rows** |
| `retag-image.sh` | `.ci/rediacc_ci/docker/retag_image.py` (360 lines) | 223 lines | `test_docker_retag_image.py` | `.ci/shadow/w7p6-retag-image.observations.jsonl`, **5 rows** |

All three: argv/stdout/stderr/exit-code equivalence against recording fakes for
`gh`/`docker` on a closed, explicit-symlink PATH (chosen specifically because an
inherited `PATH` reached real `ghcr.io` before the twin's first log line during
porting — a process finding worth repeating here). This proves the LOGIC is
faithful to the bash twin's logic, including its known defects (e.g.
`cleanup-staging.sh` silently succeeding when `gh` is entirely absent from
PATH — reproduced and pinned, not fixed, since fixing it here would be a
behavior change riding on a cutover). It proves nothing about whether the
port's actual HTTP/registry-shaped calls (`gh api`, `docker buildx imagetools
create/inspect`) succeed against the real GHCR API today, under real auth, real
rate limits, or a real multi-arch manifest shape.

**Required before trusting real mutations in CI:**

1. **A real, read-only dry-run comparison against production GHCR**, twin vs.
   port, byte-for-byte on stdout, for each of the three:
   - `retag_image.py --dry-run` (and the twin) already perform a REAL
     `docker buildx imagetools inspect` against the source tag
     (`.ci/rediacc_ci/docker/retag_image.py:284-297`) — this is a genuine read against GHCR with no
     write. Run both against each of the 3 real image roots
     (`ghcr.io/rediacc/{renet,rdc}`, `ghcr.io/rediacc/server`) with the
     `--skip-if-exists` digest-read path (`.ci/rediacc_ci/docker/retag_image.py:270-282`) also
     exercised, and diff output.
   - `create_manifest.py --dry-run` (and the twin) print the exact
     `docker buildx imagetools create` command lines without running them
     (`.ci/rediacc_ci/docker/create_manifest.py:342-350`) — run both against a real existing tag for
     each of the 3 image roots and diff.
   - `cleanup_staging.py --dry-run` performs the real `gh api` LIST/lookup call
     (finds the package version) and stops before the DELETE
     (`.ci/rediacc_ci/docker/cleanup_staging.py:309` area) — run both against a real, disposable
     `staging-*` tag (create one throwaway tagged image first) and diff.
   - Acceptance for this step: byte-identical stdout (module-name/self-path
     differences aside — see the `sys.argv[0]`/usage-string note in §4) on
     every real registry read attempted, zero divergence.
2. **One real (non-dry-run) invocation of each script**, matching the
   `w7p6-<slug>` real-run technique already used for `.ci/shadow/w7p5a-*`
   (`agent/PLAN-tooling-transformation.md:608`, "Golden dry-run parity plus one
   real run each, K=5 ledger before any deletion" — this box's proof bar should
   match that convention even though the acceptance language for W7P4-W itself
   doesn't require it, because these are real-mutation scripts, not gate
   checks). The lowest-blast-radius real target for each:
   - `create_manifest.py`: exercised automatically by the very next
     `ci-build-docker.yml` run after cutover (it runs on every `workflow_call`,
     touches a build-specific tag, not `:latest`/`:stable`).
   - `retag_image.py`: exercise via `cd-stage.yml` first (channel promotion,
     lower stakes) before `cd-v2.yml` (release promotion, touches `:stable`
     and `--push-latest`).
   - `cleanup_staging.py`: cannot get a *production* real-run today because its
     only caller's guard never passes it a `staging-*` tag (see §3). Get the
     real-run proof by invoking it directly, once, against a disposable
     `staging-*` tag pushed to GHCR for this purpose and deleted as intended,
     independent of the release pipeline.

## 2. Staged / canary rollout

Yes — a staged rollout is warranted and cheap, because every one of the three
already has the two seams needed (`--dry-run`, and a naturally low-stakes first
real call site):

```
Stage 0  Land plumbing only (entry points + workflow diffs are written but this
         stage is "build it, prove it in isolation" — no PR yet):
           - new .ci/scripts/docker/_cipath.py, create_manifest.py,
             retag_image.py, cleanup_staging.py (thin entry points)
           - run the existing differential suite unchanged: 99/99 must still
             pass (proves the new entry points don't change behavior)
Stage 1  Real dry-run canary (§1.1) against production GHCR, read-only, twin vs
         port, for all 3. Do not proceed on any divergence.
Stage 2  Flip ci-build-docker.yml's 3 create-manifest.sh call sites.
         First real exercise: automatic, next normal build. Lowest stakes
         (build-tag manifests, never :latest/:stable).
Stage 3  Watch one green ci-build-docker.yml run. Flip cd-stage.yml's 3
         retag-image.sh call sites (channel promotion).
Stage 4  Watch one green cd-stage.yml run. Flip cd-v2.yml's 3 retag-image.sh
         call sites (release promotion — highest stakes: :stable, --push-latest).
Stage 5  Flip cleanup-channel-docker-tags.sh:66's internal call, IN THE SAME
         COMMIT as the check-staging-tag-guard.sh + staging_tag_guard.py
         scanner widening (§3). This is last because it is the one call site
         that touches a shared, currently-green CI gate.
```

Each stage is independently revertible (pure text diff, no state migration);
see §5 for the rollback mechanics. Splitting into stages also means a bad
Stage N does not implicate Stages 1..N-1's already-observed real runs.

## 3. The `staging_tag_guard` constraint (real, and different from the ledger)

**What does NOT block this cutover:** the permanent-red K=5 shadow ledger
(`.ci/shadow/w7p2-stagingtag.observations.jsonl`) for `staging_tag_guard`,
recorded at `agent/PLAN-tooling-transformation.md:508,540,6263`. Read directly:
its `MISMATCH_FINDINGS` rows disagree only on an output STRING the Python port
added ("1 call site(s)" vs "1 call site(s) across 2 file(s) scanned") —
`findingCount`, `exit`, and control pass/fail all AGREE on every disqualified
row. That ledger governs cutting the `staging_tag_guard` GATE itself over to
Python — explicitly excluded for cause, and this plan does not touch that
exclusion or attempt that cutover.

**What DOES block this cutover, found in this design pass, and independently
verified by the driver:** `.ci/scripts/quality/check-staging-tag-guard.sh` — a
live, currently-GREEN, registered gate (`package.json:188`,
`scripts/ci-runner/manifest.ts:2350`, step "Staging tag guard" in
`ci-quality.yml`'s `quality-security` job, no `paths:` scoping so it runs
broadly) — discovers "executing call sites" of `cleanup-staging.sh` with:

```bash
grep -rn 'cleanup-staging\.sh' "$ROOT/.ci" "$ROOT/.github" \
  --include='*.sh' --include='*.yml' | ...
```

Its Python port `.ci/rediacc_ci/quality/staging_tag_guard.py` reproduces this
exactly (`SCAN_SUFFIXES = (".sh", ".yml")`, `NEEDLE_RE =
re.compile(r"cleanup-staging\.sh")`, `CALL_RE` the same pattern). Today's ONE
real call site is `.ci/scripts/release/cleanup-channel-docker-tags.sh:66`
(verified directly by the driver, along with the CHANNEL guard's dead-code
claim below). Renaming that call site's target to a `.py` entry point makes
`n_calls == 0` on BOTH the bash gate and its Python port, which trips the
ANTI-VACUITY refusal (exit 1, `"VACUOUS: no executing call site of
cleanup-staging.sh found"`) — this is a hard, immediate CI failure on the very
PR that makes the change, not a silent gap. This is the same "extension-shaped
matcher" class of bug the campaign has hit before (`check:ci-shell-size`'s
`paths: ['**/*.sh']`, `check-ci-parity.ts`'s `check-[\w.-]+\.sh`).

**Fix, required in the same commit as Stage 5 (§2), in BOTH files (they are
still meant to be twins, even though their cutover is separately parked):**
- `check-staging-tag-guard.sh`: widen the `grep --include` list to add
  `--include='*.py'`, and the discovery pattern to match either
  `cleanup-staging\.sh` or `cleanup_staging\.py`.
- `staging_tag_guard.py`: widen `SCAN_SUFFIXES` to `(".sh", ".yml", ".py")`,
  and `NEEDLE_RE`/`CALL_RE` to match either spelling.
- Do NOT touch `DEFAULT_TARGET_REL` / `TARGET` (still the bash twin — the
  safety-rail regex check on it stays valid since the twin is byte-untouched
  per invariant 5). Optionally, and out of scope for this box, flag as a
  follow-up: the rail check only verifies the BASH twin's `^staging-` guard,
  which after this cutover is no longer what actually executes in production;
  a future (separate, and likely inside the parked `staging_tag_guard`
  cutover, not this one) change should also assert the guard exists in
  `.ci/rediacc_ci/docker/cleanup_staging.py:116` (`re.match(r"staging-", tag)`, already present and
  already pinned by the port's own differential — just not checked by this
  gate).
- Re-run `.ci/rediacc_ci/tests/test_quality_staging_tag_guard.py` (8 tests)
  after the widening — it constructs synthetic caller fixtures and should be
  extended with one more fixture naming a `.py` caller, proving the widened
  regex is what closes the gap (plant: revert the widening, watch it go
  vacuous-red again; restore, green).
- `bash .ci/scripts/quality/check-staging-tag-guard.sh` measured GREEN today
  (1 call site, 3/3 controls) before this plan's changes — confirm still green
  after, with the SAME 1 call site (now naming the `.py` target).

**Independently verified by the driver (2026-09-14):** `.ci/scripts/release/cleanup-channel-docker-tags.sh:63-66`
does guard `if [[ ! "$CHANNEL" =~ ^staging- ]]` before ever calling
`cleanup-staging.sh --tag "$CHANNEL"`, and its own comments confirm `CHANNEL`
is always `edge` or `stable` in production — "this cannot succeed today...
a KNOWN GAP, not a token-scope problem, and it is non-critical". Flipping
line 66's call target changes zero observed production behavior today.

## 4. Exact file-level diffs

### 4a. Three new entry-point files (new, thin, headerless — matching the
convention at `.ci/scripts/quality/check_editorconfig.py` /
`.ci/scripts/quality/_cipath.py`, the closest existing precedent for "a
workflow can't run a package module by `-m`, and nothing puts `.ci` on
`sys.path` for a bare path invocation")

New: `.ci/scripts/docker/_cipath.py` — copy of
`.ci/scripts/quality/_cipath.py`'s logic (same `parents[2]` depth: both are two
directories below `.ci`), not a shared import (each entry point's own
directory is what lands on `sys.path[0]`, per that file's own docstring). This
is the FIRST `_cipath.py` outside `.ci/scripts/quality/` — confirm no other
copy exists elsewhere in `.ci/scripts/**` before assuming this is a copy vs.
should-be-shared decision (measured in this pass: it is the only one; a
second, disjoint copy is consistent with the existing pattern, not a new one).

New: `.ci/scripts/docker/create_manifest.py`, `.ci/scripts/docker/retag_image.py`,
`.ci/scripts/docker/cleanup_staging.py` — each:
```python
#!/usr/bin/env python3
"""Entry point for the ported <name> docker script. Logic is in the package.

THIS ENTRY POINT IS DELIBERATELY HEADERLESS, matching its bash twin: neither
`.ci/scripts/docker/<name-with-hyphens>.sh` nor this is a CI quality gate; both
are direct workflow `run:` targets / release-script forwarders. See
`.ci/rediacc_ci/docker/__init__.py`'s docstring for why nothing in this package
carries a `---- gate ----` header.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.docker import <module> as port

if __name__ == "__main__":
    raise SystemExit(port.main(sys.argv[1:]))
```
Set the executable bit (`chmod +x`) on all four new files — the workflow
invokes them directly by path with no `python3` prefix, exactly like the
existing `.sh` call sites, so a missing `+x` fails loudly (permission denied)
on the very next CI run touching that step. `check-script-exec-bit.sh`'s own
scope (`.ci/rediacc_ci/quality/script_exec_bit.py:106,149-152`) only matches
`./x.sh`-shaped references and won't catch a missing bit on these `.py`
entries — this is a manual pre-flight check, not a gate you can rely on to
catch it, so verify explicitly with `git diff --stat` (mode-bit changes show)
before pushing.

Known, accepted non-issue: `sys.argv[0]` (and therefore any `usage()` /
`--help` string) will differ between this direct-exec entry-point invocation
and the differential test's `[sys.executable, path]` invocation shape. No
workflow call site inspects that string; not a blocker.

### 4b. `.github/workflows/ci-build-docker.yml` — 3 call sites (approximate
line numbers, re-verify at implementation time — the file moves)

`create-manifest.sh` is called 3 times (onprem/server with `--image-path`,
rdc with `--image rdc`, renet with `--image renet`). Flags after the script
name are unchanged in all 3 (proven identical by the 99-test differential's
argv coverage).

### 4c. `.github/workflows/cd-v2.yml` — 3 call sites

`retag-image.sh --image renet --from "$CHANNEL" --to "$VERSION" --push-latest
--skip-if-exists` (renet, rdc, and `--image-path ghcr.io/rediacc/server`
variants) — verified present, ~line 301-305 with an unrelated comment
interleaved.

### 4d. `.github/workflows/cd-stage.yml` — 3 call sites

Same three-image shape as 4c, staging channel instead of version — verified
present, ~line 242-247 with an unrelated comment interleaved.

### 4e. `.ci/scripts/release/cleanup-channel-docker-tags.sh:66` — one line

```diff
-elif "$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag "$CHANNEL"; then
+elif "$SCRIPT_DIR/../docker/cleanup_staging.py" --tag "$CHANNEL"; then
```
This is a bash file editing its own internal call target; it is not a new
`.sh` file (P-C's "creates no new .sh files" invariant is about new bash
shims, not about editing an existing one's target — unaffected here). Must
land together with §3's gate-scanner widening.

### 4f. `.ci/scripts/quality/check-staging-tag-guard.sh` and
`.ci/rediacc_ci/quality/staging_tag_guard.py` — scanner widening, per §3.

## 5. Sequencing / rollback

Sequencing: §2's Stage 0-5 order (create-manifest lowest stakes first,
cleanup-staging + gate-scanner widening last since it's the only one touching
shared CI-gate machinery).

Rollback: every diff in §4 is a pure text change with no state migration
(no lockfile, no lock-json registration since these are not gates, no
allowlist entry). A revert of the commit/PR is sufficient and instant. The
irreversibility risk is NOT in the code change, it is in what a REAL run does
between merge and a caught problem:
- `create_manifest.py`/`retag_image.py` real runs push/retag real registry
  content. A bad push cannot be "unpushed", but every one of these has an
  IDEMPOTENT-shaped fix: re-run the same step with the (reverted) bash twin
  against the same tag and it overwrites the bad manifest/tag with the correct
  one — this is normal operation for these scripts already (retagging is
  idempotent by design; recreating a manifest is idempotent by design).
- `cleanup_staging.py`'s DELETE is the one truly non-reversible action (a
  deleted package version cannot be restored). Given §1's finding that its
  only real caller is dead code today (CHANNEL never matches `^staging-`),
  merge Stage 5 but treat the ACTUAL enabling of that code path (i.e., ever
  making `cleanup-channel-docker-tags.sh` receive a real `staging-*` CHANNEL)
  as a separate decision gated on its own review, unrelated to this cutover.
- Practical rollback trigger: if Stage N's first real run's output diverges
  from what the twin would have produced (compare against the twin's last
  known-good real-run log for the same job), revert that stage's workflow diff
  immediately; do not wait for a second data point given the mutation is real.

## 6. Scope decision: yes, scope this box down to just these 4 files

Recommend tracking this as its own small, disjoint sub-box under W7P4-W (e.g.
"W7P4-W-docker") rather than staffing the full 215-script/348-call-site
surface at once:

- **Fully ready, unlike almost everything else in W7P4-W's remaining surface**:
  all 3 scripts are already ported (W7P6, closed), 99/99-tested, K=5-ledgered.
  154 of the 215 W7P4-W scripts have NO port at all yet (`agent/PLAN-tooling-transformation.md:586-589`), and the 48-file deploy/release chunk (which
  overlaps this backlog) is a separately-staffed box (W7P5-a) that has its own
  open acceptance gap ("placement not quality", `:649-655`) and is nowhere
  near done (9 of 48 at the bar as of the last measurement). Bundling a
  ready-now slice behind that unfinished work serves nobody.
- **Genuinely disjoint**: this touches exactly 3 workflow files
  (`ci-build-docker.yml`, `cd-v2.yml`, `cd-stage.yml`) plus 1 release script.
  None of these files are touched by the in-flight W7P4-Q quality-gate cutover
  (which lives in `ci-quality.yml`) or by W7P5-a's deploy/release ports. The
  box's own text says "partition by WORKFLOW FILE... the workflows are the
  contended, driver-only resource" — this slice needs no coordination lock
  with any other writer.
- **The box's stated acceptance criterion doesn't cleanly fit this slice
  anyway**: "every removed path has a lock entry whose `leaves` name the
  replacement" describes gate registrations; these 3 scripts have no
  `gates.lock.json` entry (they aren't gates) and never will. Trying to
  satisfy that criterion literally for this slice would be a category error;
  the correct proof shape here is the K=5 ledger + differential + real-run
  evidence in §1, which this plan substitutes explicitly.
- **The box's own "DESIGN 2026-09-08" note already flags it isn't ready to
  staff as one unit**: the `PRE-B2` dependency doesn't exist, and the
  comment-line counting bug inflates the acceptance metric. Neither blocks
  this narrow slice (it depends on nothing but the already-closed W7P6 port),
  but both should be resolved before anyone attempts the other ~144 unported
  or ~48 W7P5a-owned files as a single box.

Everything else named in the 215/348 surface (test 18, ci 15, autopilot 14,
build 14, infra 9, private 9, security 7, housekeeping 6, quality 6, review 4,
plus the 48 deploy/release files under W7P5-a) is explicitly deferred, not
addressed by this plan.

## Tasks

- [ ] Run the real, read-only dry-run canary (§1.1) for all 3 scripts against
      production GHCR, twin vs. port, and confirm byte-identical stdout.
- [ ] Add `.ci/scripts/docker/_cipath.py` (copied convention from
      `.ci/scripts/quality/_cipath.py`) and the three thin, headerless entry
      points (§4a), each executable.
- [ ] Re-run the existing differential suite (`test_docker_cleanup_staging.py`,
      `test_docker_create_manifest.py`, `test_docker_retag_image.py`) unchanged
      and confirm still 99/99 after adding the entry points (proves the shim
      layer changes nothing).
- [ ] Flip `ci-build-docker.yml`'s 3 `create-manifest.sh` call sites (§4b).
      Watch one real green run before proceeding.
- [ ] Flip `cd-stage.yml`'s 3 `retag-image.sh` call sites (§4d). Watch one real
      green run before proceeding.
- [ ] Flip `cd-v2.yml`'s 3 `retag-image.sh` call sites (§4c).
- [ ] Widen `check-staging-tag-guard.sh`'s and `staging_tag_guard.py`'s scan
      suffix/pattern to also match `cleanup_staging\.py` (§3, §4f), add a
      `.py`-caller fixture to `test_quality_staging_tag_guard.py`, plant/revert
      to prove the widening is what closes the vacuity gap.
- [ ] Flip `.ci/scripts/release/cleanup-channel-docker-tags.sh:66` (§4e), in the same commit as the
      scanner widening above.
- [ ] Confirm `check:ci-staging-tag-guard` still reports the same 1 call site
      and 3/3 controls green, now naming the `.py` target.
- [ ] Run `check:ci-python-lint`, `check:ci-dead-python`,
      `check:ci-em-dash-surfaces`, and `check-dead-bash.ts` scoped-clean (the bash twins' basenames
      remain referenced by their own ports' docstrings, so no new orphan-file
      finding is expected — confirm rather than assume).
- [ ] Get one real (non-dry-run) invocation of `cleanup_staging.py` against a
      disposable `staging-*` tag, independent of the release pipeline (§1.2),
      since its only production caller cannot exercise it today.
- [ ] Record the K=5 ledgers, differential counts, and real-run results in the
      landing commit message / this plan's Status line.

### Critical Files for Implementation
- .ci/rediacc_ci/docker/{cleanup_staging,create_manifest,retag_image}.py
- .ci/scripts/docker/{cleanup-staging,create-manifest,retag-image}.sh
- .ci/scripts/quality/check-staging-tag-guard.sh
- .ci/rediacc_ci/quality/staging_tag_guard.py
- .github/workflows/{ci-build-docker,cd-v2,cd-stage}.yml
- .ci/scripts/release/cleanup-channel-docker-tags.sh
- agent/PLAN-tooling-transformation.md (lines 495-582, 2326-2362, 508/6263)
