# PLAN: W7P4-W docker sub-slice — cut the 3 already-ported docker scripts over from bash to Python
Status: Stages 0-5 executed 2026-09-15, uncommitted. Canary clean (all 3 scripts, byte-
identical twin vs port) after an operator scope refresh closed the credential gap.
Differential 133/133. All 9 call sites flipped, guard widened (deviated from §3's literal
instruction — see Tasks), caller flipped, guard re-confirmed, lint/dead-code gates clean.
One open item: the cleanup_staging.py DELETE drill needs `delete:packages` (not granted),
leaving a disposable image on production GHCR — see "## LEFTOVER PRODUCTION ARTIFACT".
Owner: f4da5c2e

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

- [x] Run the real, read-only dry-run canary (§1.1) for all 3 scripts against
      production GHCR, twin vs. port, and confirm byte-identical stdout. —
      **COMPLETE as of the credential refresh (2026-09-15, later in the same
      session).** Round 1 (before the refresh): `create_manifest.py` 3/3 green;
      `retag_image.py` 2/3 (`rdc`, `server`), 1/3 blocked (`renet`, 403); `cleanup_staging.py`
      0/3, plus the finding that §1.1's "`--dry-run` performs the real `gh api`
      LIST/lookup call" is wrong about the code (it returns before any network
      call). Operator ran `gh auth refresh -h github.com -s read:packages,write:packages`;
      re-ran the previously-blocked cases: `retag_image.py --image renet` now
      reads real digests, byte-identical both sides; `cleanup_staging.py`'s real
      (non-dry-run) `gh api .../versions` LIST call now succeeds too (byte-identical
      "Staging tag not found... may already be deleted" on a synthetic
      nonexistent tag). All 3 scripts, every image root: byte-identical stdout
      AND stderr, zero divergence. See Execution log for every command.
- [x] Add `.ci/scripts/docker/_cipath.py` (copied convention from
      `.ci/scripts/quality/_cipath.py`) and the three thin, headerless entry
      points (§4a), each executable. — **Already landed** in commit `7d4dee70e`
      ("W7P4-W stage 0+1, docker script entry points"), confirmed on disk
      2026-09-15: all 4 files present, executable bits set on the three entry
      points (`_cipath.py` is `rw-r--r--`, matching its `.ci/scripts/quality/`
      precedent, since it's imported not executed), content matches §4a's spec
      exactly (headerless docstrings, `import _cipath` then `from rediacc_ci.docker
      import <module> as port`). Clean working tree — nothing to add.
- [x] Re-run the existing differential suite (`test_docker_cleanup_staging.py`,
      `test_docker_create_manifest.py`, `test_docker_retag_image.py`) unchanged
      and confirm still 99/99 after adding the entry points (proves the shim
      layer changes nothing). — **99 passed** (`.ci/cache/toolchain/uv-tools/bin/pytest
      .ci/rediacc_ci/tests/test_docker_{cleanup_staging,create_manifest,retag_image}.py -q`,
      12.59s, no failures/errors).
- [x] Flip `ci-build-docker.yml`'s 3 `create-manifest.sh` call sites (§4b). —
      **DONE.** `.github/workflows/ci-build-docker.yml:436,509,604`, each
      `create-manifest.sh` -> `create_manifest.py`, flags unchanged. "Watch one
      real green run" could NOT be done: that needs an actual push and a live
      GitHub Actions run, and this session was told not to push/open a PR/merge
      (operator's own stated constraint, never lifted). The automatic real-run
      exercise the plan describes therefore still applies, just after whoever
      lands this pushes it.
- [x] Flip `cd-stage.yml`'s 3 `retag-image.sh` call sites (§4d). — **DONE.**
      `.github/workflows/cd-stage.yml:242,243,247`, each `retag-image.sh` ->
      `retag_image.py`. Same "watch a green run" caveat as above.
- [x] Flip `cd-v2.yml`'s 3 `retag-image.sh` call sites (§4c). — **DONE.**
      `.github/workflows/cd-v2.yml:301,302,305`, each `retag-image.sh` ->
      `retag_image.py`, `--push-latest --skip-if-exists` unchanged. Same caveat.
- [x] Widen `check-staging-tag-guard.sh`'s and `staging_tag_guard.py`'s scan
      suffix/pattern to also match `cleanup_staging\.py` (§3, §4f), add a
      `.py`-caller fixture to `test_quality_staging_tag_guard.py`, plant/revert
      to prove the widening is what closes the vacuity gap. — **DONE, but NOT
      as §3 literally specifies.** §3 says "widen the `grep --include` list to
      add `--include='*.py'`" over the SAME `$ROOT/.ci $ROOT/.github` trees
      already scanned for `.sh`/`.yml`. Implemented literally first: it turned
      1 real call site into **18**, because `.ci/rediacc_ci` (this package's own
      implementation + tests + regex constants) is full of self-referential
      mentions of the needle -- the guard's own `NEEDLE_RE`, the synthetic caller
      fixtures in `test_quality_staging_tag_guard.py`, `cleanup_channel_docker_tags.py`'s
      docstring. Exactly the "extension-shaped matcher" class §3's own header
      warns about, just for `.py` instead of `.sh`. Fixed by scoping `.py`
      scanning to `.ci/scripts` only (real entry points/forwarders, mirroring
      what `.sh` already is), leaving `.sh`/`.yml` scanning untouched across the
      whole tree: back to exactly 1 call site. Both `.ci/scripts/quality/check-staging-tag-guard.sh`
      and `.ci/rediacc_ci/quality/staging_tag_guard.py` carry this scoping, with
      inline comments explaining why. Added 3 tests to
      `test_quality_staging_tag_guard.py` (17 total, was 14): an unguarded
      `.py`-caller case that the widened scanner now catches and fails,
      a `.ci/rediacc_ci`-tree `.py` mention proven NOT to count (still vacuous),
      and a direct `grep_hits()` unit test pinning the scope. Plant/revert done
      on BOTH sides independently: reverting the bash scanner's widening (call
      site already renamed) reproduced the exact predicted vacuous-red
      (`FAIL  at least one executing call site was found (got '0' want '1')`,
      exit 1); reverting the Python port's `CALL_RE` alone did the same
      (`✗ VACUOUS: no executing call site...`, exit 1). Both restored, both
      green again, confirmed byte-for-byte against the saved widened copies.
- [x] Flip `.ci/scripts/release/cleanup-channel-docker-tags.sh:66` (§4e), in the
      same commit as the scanner widening above. — **DONE**
      (`.ci/scripts/release/cleanup-channel-docker-tags.sh:66`, `cleanup-staging.sh`
      -> `cleanup_staging.py`). Sibling fix found and applied in the same pass
      (not in §4's file list, forced by this change): `.ci/rediacc_ci/release/cleanup_channel_docker_tags.py`
      is a SEPARATE, already-ported twin of this same caller script (owned by
      the W7P5-a box, not this plan), with its own hardcoded
      `_CLEANUP_STAGING` path constant pointing at the old bash name. Left
      unchanged it would silently diverge from its own twin the moment this
      commit lands. Updated the constant to `cleanup_staging.py`, and updated
      `test_release_cleanup_channel_docker_tags.py`'s fixture (which drops a
      recording stub at that exact path to keep the real GHCR delete out of
      reach) to match -- 4 tests had gone red the instant the bash call site
      moved (`the deleter stub never ran`); all 17 pass again after the fix.
      This is a one-line-constant-plus-fixture-path fix, not a W7P5-a cutover:
      the actual bash-to-Python flip of `cleanup-channel-docker-tags.sh` itself
      remains untouched and out of scope.
- [x] Confirm `check:ci-staging-tag-guard` still reports the same 1 call site
      and 3/3 controls green, now naming the `.py` target. — **CONFIRMED**, both
      implementations: `bash .ci/scripts/quality/check-staging-tag-guard.sh` ->
      `✓ staging tag guard (1 call site(s)): 3 control(s) passed`, exit 0,
      naming `.ci/scripts/release/cleanup-channel-docker-tags.sh` (which now
      calls the `.py` target). `python3 -m rediacc_ci.quality.staging_tag_guard`
      -> identical verdict.
- [x] Run `check:ci-python-lint`, `check:ci-dead-python`,
      `check:ci-em-dash-surfaces`, and `check-dead-bash.ts` scoped-clean (the bash twins' basenames
      remain referenced by their own ports' docstrings, so no new orphan-file
      finding is expected — confirm rather than assume). — **ALL GREEN, no new
      findings.** `check:ci-python-lint`: 1043 files, all pass. `check:ci-dead-python`:
      45 controls passed, 1043 files scanned/reached; none of the 3 docker
      scripts or their entry points appear in the exempt-by-name list (they are
      genuinely wired now). `check:ci-em-dash-surfaces`: 0 new findings across
      2312 files. `check:ci-dead-bash` (`scripts/gates/check-dead-bash.ts`):
      619 shell files, 2954 functions, **0 findings** -- confirms the prediction:
      `create-manifest.sh`/`retag-image.sh`/`cleanup-staging.sh` are not flagged
      as orphaned even with their call sites gone, because their own Python
      ports' docstrings still name them.
- [x] Get one real (non-dry-run) invocation of `cleanup_staging.py` against a
      disposable `staging-*` tag, independent of the release pipeline (§1.2),
      since its only production caller cannot exercise it today. — **Push + LIST
      succeeded; the DELETE step is blocked on a scope the refresh didn't
      include, and a live artifact is now sitting in production GHCR because of
      it -- see "LEFTOVER PRODUCTION ARTIFACT" below, read before doing anything
      else with credentials on this repo.**
- [x] Record the K=5 ledgers, differential counts, and real-run results in the
      landing commit message / this plan's Status line. — Recorded in the Status
      line and the Execution log below. No commit was made this session (work
      left uncommitted per this repo's default); whoever commits this should
      fold this record into the commit message per the plan's own convention.

## LEFTOVER PRODUCTION ARTIFACT — read before touching credentials on this repo

`ghcr.io/rediacc/rdc:staging-w7p4w-canary-985906` (package version id
`1253038485`, digest `sha256:a77e698892cc4ff37234678d4759659c4c5ed50776ad564e0fde111256e041ea`,
pushed 2026-09-15T19:12:25Z) is a disposable, single-tag, `FROM scratch` throwaway
image pushed during this session's real-run drill for `cleanup_staging.py`. It
was created specifically to be deleted by that drill and confirmed to carry no
other tag (verified via `gh api orgs/rediacc/packages/container/rdc/versions`:
`"tags": ["staging-w7p4w-canary-985906"]` only) and to share no digest with
`:edge` or `:stable` (their digest, `sha256:27bb0e6e2c...b7f2d`, verified
unchanged before and after). It is harmless sitting there, but it is NOT
deleted, and it needs to be, by someone with the right scope.

**Why it wasn't deleted this session.** The operator ran
`gh auth refresh -h github.com -s read:packages,write:packages` mid-session,
closing the read gap that had blocked Stage 1's canary. That let the LIST call
(`gh api .../rdc/versions`) succeed and let the disposable image get pushed
(`write:packages` covers the push). The DELETE call (`gh api -X DELETE
.../rdc/versions/1253038485`), run through both `cleanup_staging.py` directly
and a raw `gh api -X DELETE` to rule out a script bug, failed identically both
times: `{"message":"You need at least delete:packages and read:packages scopes
to delete a package version.","status":"403"}`. GitHub's package-delete
endpoint requires its OWN `delete:packages` scope; `write:packages` does not
imply it. This was not requested in the refresh.

**To close this out:** either `gh auth refresh -h github.com -s delete:packages`
(additive, does not remove the scopes already granted) and re-run
`python3 .ci/scripts/docker/cleanup_staging.py --tag staging-w7p4w-canary-985906`
(or the bash twin, or `gh api -X DELETE orgs/rediacc/packages/container/rdc/versions/1253038485`
directly) to complete the exact drill this plan asked for, or delete version id
`1253038485` by hand via the GitHub UI/API with an account that already carries
`delete:packages`. Either way this line should be removed from the plan once
done.

## Execution log (2026-09-15)

Environment: `gh` authenticated as `mfbayraktar`, token scopes measured via
`curl -I -H "Authorization: token $(gh auth token)" https://api.github.com/user`:
`x-oauth-scopes: admin:org, gist, repo, workflow` — **no `read:packages`, no
`write:packages`**. `docker login ghcr.io` with that same token succeeds (identity
is valid), but GHCR's own authorization still denies per-package based on scope,
independent of docker login succeeding.

**Stage 0 (already landed, re-verified):** `git log --oneline -1 -- .ci/scripts/docker/_cipath.py`
→ `7d4dee70e feat(ci): W7P4-W stage 0+1, docker script entry points`, same for
`cleanup_staging.py`/`create_manifest.py`/`retag_image.py` under `.ci/scripts/docker/`.
`git status --short` on all 4 is empty (clean, matches HEAD).

**Differential suite:**
```
$ .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_docker_cleanup_staging.py \
    .ci/rediacc_ci/tests/test_docker_create_manifest.py .ci/rediacc_ci/tests/test_docker_retag_image.py -q
99 passed in 12.59s
```

**`create_manifest.py` canary — 3/3 green, no registry access needed at all.**
Read the code first: both twin (`.ci/scripts/docker/create-manifest.sh:115-116`) and
port only `echo`/`print` the would-be command line under `--dry-run`; neither ever
calls `docker` or `gh`. Ran anyway, per image root, comparing bash twin vs Python port,
stdout AND stderr diffed separately:
```
bash .ci/scripts/docker/create-manifest.sh   --image renet                       --tag edge --dry-run
python3 .ci/scripts/docker/create_manifest.py --image renet                       --tag edge --dry-run
bash .ci/scripts/docker/create-manifest.sh   --image rdc                         --tag edge --dry-run
python3 .ci/scripts/docker/create_manifest.py --image rdc                         --tag edge --dry-run
bash .ci/scripts/docker/create-manifest.sh   --image-path ghcr.io/rediacc/server --tag edge --dry-run
python3 .ci/scripts/docker/create_manifest.py --image-path ghcr.io/rediacc/server --tag edge --dry-run
```
All 3 pairs: exit 0/0, stdout identical, stderr identical (`diff -u` empty both ways).

**`retag_image.py` canary — real reads against production GHCR, 2/3 image roots green:**
```
bash .ci/scripts/docker/retag-image.sh   --image rdc --from edge --to canary-test-nonexistent --dry-run   -> exit 0
python3 .ci/scripts/docker/retag_image.py --image rdc --from edge --to canary-test-nonexistent --dry-run   -> exit 0, stdout/stderr identical
bash .ci/scripts/docker/retag-image.sh   --image-path ghcr.io/rediacc/server --from edge --to canary-test-nonexistent --dry-run -> exit 0
python3 .ci/scripts/docker/retag_image.py --image-path ghcr.io/rediacc/server --from edge --to canary-test-nonexistent --dry-run -> exit 0, stdout/stderr identical
bash .ci/scripts/docker/retag-image.sh   --image rdc --from edge --to stable --dry-run --skip-if-exists            -> exit 0
python3 .ci/scripts/docker/retag_image.py --image rdc --from edge --to stable --dry-run --skip-if-exists            -> exit 0, stdout/stderr identical
bash .ci/scripts/docker/retag-image.sh   --image-path ghcr.io/rediacc/server --from edge --to edge --dry-run --skip-if-exists -> exit 0
python3 .ci/scripts/docker/retag_image.py --image-path ghcr.io/rediacc/server --from edge --to edge --dry-run --skip-if-exists -> exit 0, stdout/stderr identical
```
These are genuine real, read-only GHCR hits (`docker buildx imagetools inspect
ghcr.io/rediacc/rdc:edge` etc.), both the plain source-verify path and the
`--skip-if-exists` destination-then-source digest-read path, both scripts, byte
for byte identical stdout AND stderr in every case.

`renet` is a private GHCR package and the available credential cannot read it:
```
bash .ci/scripts/docker/retag-image.sh   --image renet --from edge --to canary-test-nonexistent --dry-run -> exit 1
python3 .ci/scripts/docker/retag_image.py --image renet --from edge --to canary-test-nonexistent --dry-run -> exit 1, stdout/stderr identical to bash
```
stderr (identical both sides):
```
→ Re-tagging renet: edge -> canary-test-nonexistent
✓ [DRY-RUN] Verifying source image: ghcr.io/rediacc/renet:edge
ERROR: unexpected status from HEAD request to https://ghcr.io/v2/rediacc/renet/manifests/edge: 403 Forbidden
denied
✗ [DRY-RUN] Failed to inspect source image: ghcr.io/rediacc/renet:edge
✓ Re-tag summary: 0 succeeded, 1 failed
```
Same result with `--skip-if-exists` added. This is NOT a twin/port divergence (the
failure is byte-identical on both sides), but it is also not a completed read: §1.1's
acceptance is "byte-identical stdout ... on every real registry read attempted, zero
divergence" for a `renet` read that never actually happened.

**`cleanup_staging.py` canary — blocked, and the plan's own §1.1 is wrong about the code.**
§1.1 states: "`cleanup_staging.py --dry-run` performs the real `gh api` LIST/lookup
call (finds the package version) and stops before the DELETE." Read both
implementations directly: `.ci/scripts/docker/cleanup-staging.sh:74-77` and
`.ci/rediacc_ci/docker/cleanup_staging.py`'s `delete_staging_tag()` both do
`if dry_run: log "[DRY-RUN] Would delete: ..."; return` BEFORE `_gh_list`/`gh api
.../versions` is ever called. Confirmed by running both under `--dry-run` with tag
`staging-canary-probe`: stdout/stderr identical between twin and port, but neither
made a network call (log line is exactly `[DRY-RUN] Would delete: ghcr.io/rediacc/<image>:staging-canary-probe`
with no LIST anywhere in the trace). So `--dry-run` proves nothing about the port's
`gh api` call — the plan's described "real read-only canary" for this script does not
exist as `--dry-run` describes it.

The actual `gh api /orgs/<org>/packages/container/<pkg>/versions --paginate` call only
fires on a REAL (non-`--dry-run`) invocation. Confirmed the credential gap is total,
not renet-specific, by hitting the REST endpoint directly for a PUBLIC package too:
```
$ gh api orgs/rediacc/packages/container/rdc
{"message":"You need at least read:packages scope to get a package.","status":"403"}
```
Then ran the real (non-`--dry-run`) path itself, safely: chose a tag guaranteed not to
match any existing package version (`staging-canary-probe-nonexistent-<unix-ts>-<pid>`),
so even if the LIST succeeded, `extract_version_id` would find no match and no DELETE
would be attempted regardless. Ran both:
```
bash .ci/scripts/docker/cleanup-staging.sh   --tag staging-canary-probe-nonexistent-1789493872-426766 -> exit 0
python3 .ci/scripts/docker/cleanup_staging.py --tag staging-canary-probe-nonexistent-1789493872-426766 -> exit 0, stdout/stderr identical
```
Both hit the 403 on `_gh_list`, both treat "not a JSON array" (an HTML/JSON error
body) as "package not accessible" (a pre-existing, twin-inherited defect class: an
inaccessible package silently reports success, same shape as the already-pinned
"gh entirely absent from PATH" defect §1 mentions), both exit 0, byte-identical
output. This confirms twin/port parity on the FAILURE path, but is not the
successful-read canary the plan needs, and it is not the disposable-tag real-mutation
drill either (no image was ever pushed, so there was nothing to find or delete).

**Net for Stage 1:** cannot certify "byte-identical stdout on every real registry
read attempted, zero divergence" for `retag_image.py`/`renet` or for any
`cleanup_staging.py` path, because the reads themselves could not be attempted
successfully — not because of a twin/port mismatch. Per the plan's explicit
sequencing and the task's instruction not to skip ahead of the canary gate, Stages
2-5 were not started. Nothing in `.github/workflows/**`, `check-staging-tag-guard.sh`,
`staging_tag_guard.py`, or `cleanup-channel-docker-tags.sh` was modified.

**What would unblock this:** a GHCR-capable credential (PAT, GitHub App
installation token, or `docker`/`gh` login) carrying `read:packages` at minimum, and
`write:packages` for the plan's real-run proof items (§1.2's one real invocation of
each script, and the disposable-tag delete drill for `cleanup_staging.py`
specifically — that one also needs push rights to create the throwaway tag in the
first place). No such credential was found in this environment (`env` scan for
`GITHUB_TOKEN`/`GH_TOKEN`/`GHCR_TOKEN`/`PACKAGES_TOKEN`/`CR_PAT` came back empty
beyond the harness's own unrelated messaging token; `~/.docker/config.json` has no
stored ghcr.io auth beyond the interactive `gh`-token login performed for this
canary).

**UPDATE, same session, after the above was written:** the operator ran
`gh auth refresh -h github.com -s read:packages,write:packages` and told this
session so, with independent verification (`curl` against
`orgs/rediacc/packages/container/renet` returning 200 where it had been 403).
Re-verified directly rather than taking the report on faith: `gh auth status`
now lists `write:packages` in scopes; `gh api orgs/rediacc/packages/container/renet`
returns the package JSON; `docker login ghcr.io` with the refreshed token
followed by `docker buildx imagetools inspect ghcr.io/rediacc/renet:edge`
resolves a real digest. See "## Execution log, part 2" below for the rest of
Stage 1 and all of Stages 2-5.

## Execution log, part 2 (2026-09-15, after the credential refresh)

**Stage 1, completed.** Re-ran exactly the two previously-blocked cases:
```
$ bash .ci/scripts/docker/retag-image.sh --image renet --from edge --to canary-test-nonexistent --dry-run   # exit 0
$ python3 .ci/scripts/docker/retag_image.py --image renet --from edge --to canary-test-nonexistent --dry-run # exit 0, stdout/stderr identical
$ bash .ci/scripts/docker/retag-image.sh --image renet --from edge --to stable --dry-run --skip-if-exists    # exit 0
$ python3 .ci/scripts/docker/retag_image.py --image renet --from edge --to stable --dry-run --skip-if-exists  # exit 0, stdout/stderr identical
```
`cleanup_staging.py`'s real (non-dry-run) path, run against a tag guaranteed not
to exist (`staging-canary-probe-nonexistent-1789499405-984121`), both sides:
```
→ Cleaning up staging tags: staging-canary-probe-nonexistent-1789499405-984121
→ Deleting staging tag for renet: staging-canary-probe-nonexistent-1789499405-984121
⚠ Staging tag not found for renet:staging-canary-probe-nonexistent-1789499405-984121 (may already be deleted)
→ Deleting staging tag for rdc: staging-canary-probe-nonexistent-1789499405-984121
⚠ Staging tag not found for rdc:staging-canary-probe-nonexistent-1789499405-984121 (may already be deleted)
✓ Cleanup summary: 2 succeeded
```
byte-identical, exit 0 both sides. This is the LIST call actually succeeding
now (contrast the pre-refresh run's "not accessible" message) and correctly
finding no match — genuine successful-read canary evidence for all 3 scripts,
all applicable image roots (`cleanup_staging.py` only ever touches
`PUBLISH_IMAGES = (renet, rdc)`, per `.ci/config/constants.sh:169`; `server` is
out of its scope by design, unrelated to this session).

**The real (non-dry-run) delete drill for `cleanup_staging.py` (§1.2).**
Baseline recorded first: `ghcr.io/rediacc/rdc:edge` and `:stable` both digest
`sha256:27bb0e6e2c386ef9eaced7ee2c4f0978399698c16f8c7e22d84bd3abb31b7f2d`.
Built and pushed a disposable, single-tag image with a unique label (`FROM
scratch`, a `LABEL unique=...` with a timestamp+pid+random suffix, guaranteeing
a fresh digest that shares nothing with any real tag):
```
$ docker buildx build --platform linux/amd64 -t ghcr.io/rediacc/rdc:staging-w7p4w-canary-985906 --push .
...manifest list sha256:a77e698892cc4ff37234678d4759659c4c5ed50776ad564e0fde111256e041ea done
```
Verified before deleting anything: the new tag's digest
(`sha256:a77e698892cc...`) differs from `:edge`/`:stable`'s
(`sha256:27bb0e6e2c...`), and `gh api orgs/rediacc/packages/container/rdc/versions`
shows version id `1253038485` carrying exactly one tag,
`["staging-w7p4w-canary-985906"]` — no risk of deleting a shared tag.

Ran the REAL delete via the Python port (the actual production target of this
cutover):
```
$ python3 .ci/scripts/docker/cleanup_staging.py --tag staging-w7p4w-canary-985906
exit=1
stdout: {"message":"You need at least delete:packages and read:packages scopes to delete a package version.","status":"403"}
stderr: → Cleaning up staging tags: staging-w7p4w-canary-985906
        → Deleting staging tag for renet: staging-w7p4w-canary-985906
        ⚠ Staging tag not found for renet:staging-w7p4w-canary-985906 (may already be deleted)
        → Deleting staging tag for rdc: staging-w7p4w-canary-985906
        ✗ Failed to delete staging tag for rdc
        ✗ Cleanup summary: 1 succeeded, 1 failed
```
Confirmed it is a scope gap and not a script bug by hitting the DELETE endpoint
directly: `gh api -X DELETE orgs/rediacc/packages/container/rdc/versions/1253038485`
returns the identical 403/message. GitHub's package-delete API requires its own
`delete:packages` scope; `write:packages` (what the refresh granted) does not
imply it. **The disposable image is therefore still live on production GHCR —
see "## LEFTOVER PRODUCTION ARTIFACT" above the Tasks list.** Confirmed
`:edge`/`:stable` digests unchanged after the attempt (still
`sha256:27bb0e6e2c...`).

**Stage 2.** `.github/workflows/ci-build-docker.yml`: 3 `create-manifest.sh` ->
`create_manifest.py` at lines 436 (`--image-path` onprem/server), 509 (`--image
rdc`), 604 (`--image renet`). Flags unchanged, verified with `grep -n
'create-manifest.sh\|create_manifest.py'` before and after (only the 3
executing `run:` lines changed; 5 prose comments elsewhere still say
`create-manifest.sh`, correctly, since that file still exists and those lines
are descriptive, not executed).

**Stage 3.** `.github/workflows/cd-stage.yml`: 3 `retag-image.sh` ->
`retag_image.py` at lines 242 (`--image renet`), 243 (`--image rdc`), 247
(`--image-path ghcr.io/rediacc/server`).

**Stage 4.** `.github/workflows/cd-v2.yml`: 3 `retag-image.sh` ->
`retag_image.py` at lines 301, 302, 305, same three image roots, `--push-latest
--skip-if-exists` unchanged.

**Stage 5, the guard widening, and the plan-description gap found while doing
it.** §3 says: widen `check-staging-tag-guard.sh`'s `grep --include` list to
add `--include='*.py'`, over the SAME `$ROOT/.ci $ROOT/.github` trees. Did
exactly that first:
```
$ bash .ci/scripts/quality/check-staging-tag-guard.sh
✓ staging tag guard (18 call site(s)): 7 control(s) passed
```
18, not 1. The extra 17 were: this gate's own `NEEDLE_RE`/`CALL_RE` source in
`.ci/rediacc_ci/quality/staging_tag_guard.py`, the synthetic caller fixtures in
`.ci/rediacc_ci/tests/test_quality_staging_tag_guard.py`, similar fixtures in
`.ci/rediacc_ci/tests/test_release_cleanup_channel_docker_tags.py`, and
`.ci/rediacc_ci/release/cleanup_channel_docker_tags.py`'s own docstring/constant
mentioning the bash twin's name. All of it lives under `.ci/rediacc_ci`, this
package's own implementation-and-tests tree, not under `.ci/scripts` where real
entry points and release forwarders live (mirroring what `.sh` already is for
the twin's own scan). Verified the fix is precise before committing to it:
```
$ grep -rnE 'cleanup[-_]staging\.(sh|py)' .ci/scripts --include='*.py'
.ci/scripts/docker/cleanup_staging.py:5:`.ci/scripts/docker/cleanup-staging.sh` nor this is a CI quality gate; both are
```
One hit, in `cleanup_staging.py`'s own docstring, and it fails the stricter
`--tag`/`"$`-suffix filter (the line continues "` nor this is a CI quality
gate`", not `--tag ...`), so it was never going to be counted. Scoped `.py`
inclusion to `.ci/scripts` only in both `check-staging-tag-guard.sh` (two
separate `grep` calls, sh/yml over the whole tree plus py over `.ci/scripts`
only, concatenated before the filter pipeline) and `staging_tag_guard.py`
(`PY_SCAN_DIR = ".ci/scripts"`, checked via `path.relative_to()` in
`grep_hits()`). Re-ran: `✓ staging tag guard (1 call site(s)): 3 control(s)
passed` on both sides, back to exactly the pre-widening baseline.

Flipped `.ci/scripts/release/cleanup-channel-docker-tags.sh:66` in the same
pass: `cleanup-staging.sh` -> `cleanup_staging.py`. Re-confirmed both gate
implementations: 1 call site, 3/3 controls, exit 0, now naming
`cleanup-channel-docker-tags.sh` (unchanged file identity, changed target).

**Sibling fix, found while flipping line 66, applied in the same change:**
`.ci/rediacc_ci/release/cleanup_channel_docker_tags.py` — a separate,
already-ported Python twin of `cleanup-channel-docker-tags.sh` itself, owned by
the W7P5-a box and explicitly out of THIS plan's scope per §6 — has its own
`_CLEANUP_STAGING` path constant, hardcoded to the old bash name. Left alone it
would silently stop being a faithful port of its own twin the moment this
commit lands (twin calls `.py`, port's constant still points at `.sh`, and the
`.sh` file still exists so nothing would even error — it would just silently
retag/delete through the OLD path forever). Fixed the constant
(`_CLEANUP_STAGING = ... "cleanup_staging.py"`) and the differential fixture
that depends on it: `test_release_cleanup_channel_docker_tags.py` drops a
recording stub at a hardcoded path to keep the real deleter out of reach; that
path had to move too. Before the fix: 4 of 17 tests in that file failed with
"the deleter stub never ran" the moment line 66 changed. After: 17/17 pass.
This is a 1-line-constant plus 1-fixture-path-plus-3-assertion-strings fix, not
a W7P5-a cutover — the actual `.sh`-to-`.py` flip of `cleanup-channel-docker-tags.sh`
itself is untouched.

**Plant/revert proof, both implementations, independently:**
```
# bash: temporarily restored the pre-widening grep (call site already renamed to .py)
$ bash .ci/scripts/quality/check-staging-tag-guard.sh
  FAIL  at least one executing call site was found (got '0' want '1')
✗ VACUOUS: no executing call site of cleanup-staging.sh found under .ci or .github.
exit=1
# restored the widened version -> back to 1 call site, exit 0

# python: temporarily reverted only CALL_RE to the pre-widening pattern
$ python3 -m rediacc_ci.quality.staging_tag_guard
  FAIL  at least one executing call site was found (got '0' want '1')
✗ VACUOUS: no executing call site of cleanup-staging.sh found under .ci or .github.
exit=1
# restored -> back to 1 call site, exit 0
```

**Final gates, all green:**
```
$ .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_docker_cleanup_staging.py \
    .ci/rediacc_ci/tests/test_docker_create_manifest.py .ci/rediacc_ci/tests/test_docker_retag_image.py \
    .ci/rediacc_ci/tests/test_release_cleanup_channel_docker_tags.py .ci/rediacc_ci/tests/test_quality_staging_tag_guard.py -q
133 passed in 14.18s

$ python3 .ci/scripts/quality/check_python_lint.py
✓ 1043 Python file(s) pass ruff lint and format

$ python3 .ci/scripts/quality/check_dead_python.py
✓ dead Python: 1043 file(s) scanned, every one reached ... 45 control(s) passed
  (none of the 3 docker scripts or their entry points appear in the
  exempt-by-name list -- they are genuinely wired now)

$ npx tsx scripts/gates/check-em-dash-surfaces.ts
✓ No new em dashes across 2312 file(s) in 23 surface(s).

$ npx tsx scripts/gates/check-dead-bash.ts
scanned 619 shell file(s), 2954 function(s); 0 finding(s)
✓ no dead shell functions or orphaned shell scripts.
```

**Not done, and why:** "watch one [real, green GitHub Actions] run" between
Stages 2/3/4, as the plan's own §2 sequencing describes, requires an actual
push and a live CI execution. This session operates on the shared primary tree
without push/PR/merge authority (an explicit constraint from the start of this
task, never lifted by the operator's later rulings, which addressed worktree
isolation and credentials, not that specific restriction). The automatic
real-run exercise the plan describes for `create_manifest.py` (next
`ci-build-docker.yml` run) and `retag_image.py` (next `cd-stage.yml`, then
`cd-v2.yml`, run) will happen the first time whoever lands this pushes it; nothing
about that mechanism was changed here, only observed to be out of this
session's reach.

### Critical Files for Implementation
- .ci/rediacc_ci/docker/{cleanup_staging,create_manifest,retag_image}.py
- .ci/scripts/docker/{cleanup-staging,create-manifest,retag-image}.sh
- .ci/scripts/quality/check-staging-tag-guard.sh
- .ci/rediacc_ci/quality/staging_tag_guard.py
- .github/workflows/{ci-build-docker,cd-v2,cd-stage}.yml
- .ci/scripts/release/cleanup-channel-docker-tags.sh
- agent/PLAN-tooling-transformation.md (lines 495-582, 2326-2362, 508/6263)
