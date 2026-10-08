# Release process

Single pipeline: CI validates everything BEFORE publish. CD is a thin promote step, and if CI fails, CD never triggers.

```
CI: quality -> build -> dry-run -> validate install (6 platforms) -> ci-complete
CI on main: ci-complete -> finalize-release-sentinel (seal cli/v<V>/.released, dispatch CD)
CD: init (git tag v<V>) -> promote Docker -> deploy edge -> smoke + install validation -> submodule tags, Homebrew, GitHub Release
```

Install validation runs pre-publish against R2 staging artifacts. Docker is validated on push-to-main only (PR images are dry-run on a PR).

## Release channels

Two channels, both production-quality:

- **edge** -- tagged and released on every merge to main, downloaded from
`releases.rediacc.com/cli/edge/` (R2 bucket `rediacc-releases`), serving `edge.rediacc.com`.
- **stable** -- the default, promoted from edge (see Release to Production below),
downloaded from `releases.rediacc.com/cli/stable/`, serving `www.rediacc.com`.

R2 layout: `rediacc-releases/cli/{edge,stable}/{manifest.json,latest.json,rdc-*}`.

**CORRECTION to a claim that was in CLAUDE.md: edge's D1 is NOT cloned from production daily.** `.github/workflows/edge-clone-d1.yml`'s own header says otherwise: *"Edge D1 databases are now persistent for the beta channel. Daily cloning from production is disabled; use workflow_dispatch for manual runs."* The workflow still exists for a manual, on-demand clone -- it is not
scheduled.

The mechanical job topology (every workflow, folded to one row per stage of its `needs:` graph) is generated, not hand-maintained: the `job-graph` region in [scripts/data/doc-registry.md](../../scripts/data/doc-registry.md). This file explains the concepts that table cannot show -- what `release_mode` means, when a soak period applies, and the exact commands.

## Release to Edge (`cd-v2.yml`)

Dispatched automatically from CI's `finalize-release-sentinel` job right after the release sentinel is sealed, or manually:

```
gh workflow run "Release to Edge" -f ci_run_id=<id> -f release_mode=patch|retry
```

`release_mode` is a `workflow_dispatch` `choice` input with only two values -- **GitHub itself rejects `minor`/`major`**, there is no in-repo validation to bypass:

- `retry` (the default) -- re-run publish for the newest git tag (`resolve_version --current`), without recomputing the version.
Use this for a publish that failed after init tagged the version (a transient R2 or Docker push failure, a red install validation). Because the version comes FROM the tags, a retry cannot see a sealed version that never got its tag; that case needs `patch`.
- `patch` -- recompute `next_version` from merged PR labels and existing git tags, then
publish. This is the normal path for a manual or CI-triggered edge release.

Three more inputs, none in `CLAUDE.md` before this doc existed:

- `publish_stable` (boolean) -- also promote straight to the stable channel in the same
run, skipping the normal 7-day soak. This is the **hotfix** path:
  ```
  gh workflow run "Release to Edge" -f ci_run_id=<id> -f release_mode=patch -f publish_stable=true
  ```
- `deploy_workers_only` (boolean) -- redeploy the Cloudflare Workers only, skipping the
version bump, CLI build, Docker promote and GitHub Release. For when the release artifacts are already correct and only the Worker deploy needs to re-run.
- `allow_stale_ci_run_id` (boolean) -- bypasses the "`ci_run_id` must be the latest green
Console CI on main" guard. Only for cherry-picking a specific prior CI run; using it to publish an old run ahead of a newer green one is exactly the case the guard exists to stop.

`ci_run_id` may be left empty to auto-derive the latest green Console CI on `main`.

### Job order: the tag and the sentinel are one unit

`finalize-release-sentinel` in `ci.yml` seals `cli/v<V>/.released` and, in the very next step under the same `if:`, dispatches this workflow. Check Release State requires a `v<V>` git tag for every sentinel, so the tag is cd-v2's FIRST write: the `Create version tag` step at the end of `init`, behind only the read-only guards `check-existing-release` and `assert-artifact-version`.

Everything that can fail after the seal runs after the tag: `publish` (Docker promote), both edge deploys, the smoke test and `validate-install-published`. `tag-and-release` still waits for all of them, and now does only the parts users consume: submodule tags, the Homebrew formula, the contract-floor ratchet and the GitHub Release.

The tag used to live in `tag-and-release`. On 2026-10-08 CD run 37749637824 (v2.2.0) went red on a Rocky 9 DNF stall in post-publish install validation, the tag job was skipped, and the sealed sentinel was left with no tag, which reddened main.

Retry behaviour, per step:

- `Create version tag` runs on `retry` too and is idempotent. It asks `git ls-remote` for the tag: present means a no-op, absent means create it at the CI commit (`ci_sha`, the commit the sentinel records), and any other `ls-remote` failure is refused as unknown. On a `patch` run, a tag already present at a different commit is refused.
- `tag-and-release` runs on `retry` too. Its first step asks whether the GitHub Release exists: if it does, every later step is skipped; if it is missing (`release not found`), the run completes submodule tags, Homebrew, the floor and the Release. Any other `gh` error is refused.
- `deploy_workers_only` cuts no version, so both are skipped.

What can still split the pair: `init` failing before its tag step, or the dispatch never arriving. The sentinel then has no tag, Check Release State names it, and the repair is a `release_mode=patch` re-dispatch (it recomputes the same version, because no tag exists for it yet).

`check:ci-workflow-invariants` (`.ci/rediacc_ci/security/ci_workflow_invariants.py`, release-order phase) enforces the shape on the job graph. It refuses a version-tag step behind any job other than `init`, a tag step or job whose `if:` reads `retry_mode`, a dispatch that does not immediately follow the seal under the same `if:`, `contents: write` anywhere in cd-v2, a `git push` not on the `preset: cd` App token, and a `cd` preset that stops requesting `workflows: write`.

The `release` PR label sets `publish_stable` on the automatic dispatch. When the merged PR carries the exact label `release` and not `bump-none`, `initialize` records `publish_stable=true` and finalize-release-sentinel dispatches cd-v2 with `-f publish_stable=true`, so the merge publishes to edge AND stable with no soak (operator ruling 2026-09-30). A failed PR lookup still releases, to edge only. The decision lives in `.ci/rediacc_ci/ci/dispatch_release.py`.

## Release to Production (`promote-stable.yml`)

```
Daily cron: 0 6 * * * UTC
Manual:     gh workflow run "Release to Production" -f force=true
```

Promotes the current edge release to the stable channel (`eu`/`us`/`asia`), serving `www.rediacc.com`. Runs on a daily cron and refuses to promote a version still inside its `SOAK_DAYS` (7) window unless dispatched with `force: true`, which skips the soak check entirely -- there is no partial-skip.
A green scheduled nightly (`Console CI` on `main`) also triggers it through `workflow_run`, and that run skips the soak only when the edge tag's commit is the nightly's `head_sha` or an ancestor of it (`rediacc_ci.release.nightly_tested_edge`); an edge the nightly did not contain, or any failed lookup, falls back to the soak rule. The rollback-label check and every deploy and verify job run the same on all three triggers, a `promote-stable` concurrency group queues them rather than running two at once, and the summary names the trigger and the rule (`force`, `nightly` or `soak`) that decided.

Both R2 promotes (this one and the `publish_stable` hotfix lane) copy `<dir>/edge/` to `<dir>/stable/` server-side with one `aws s3api copy-object` per object, so no release bytes pass through the runner; only the four channel pointers (`cli/install.sh`, `cli/install.ps1`, `rpm/rediacc.repo`, `archlinux/rediacc.conf`) are fetched, stamped for stable and uploaded after the rest of their tree. `.ci/rediacc_ci/deploy/r2_promote.py` carries the plan and R2's copy limits.

## Package tree retention

Each Linux package tree (`apt/<channel>/`, `rpm/<channel>/`, `apk/<channel>/`, `archlinux/<channel>/`) keeps only what its index lists (operator ruling 2026-10-06), on `edge`, `stable` and every `pr-N` channel. Pinned old versions stay installable from the immutable `cli/v<semver>/`, which nothing here touches.

- **Upload** (`rediacc_ci.deploy.upload_repos_to_r2`): after every sync, install-script upload, snapshot seal and cache purge, each built tree is listed, the listing must hold every file of `dist/repos/<fmt>`, and then every other object in `<fmt>/<channel>/` is deleted. On `edge` the keep set also holds the package files named by the sealed snapshot of any other version `check_soak_period` may still select (newer than stable), because the soak-gated promote copies those packages from `<fmt>/edge/`.
- **Promote** (both lanes, `r2_promote.promote_tree`): after a tree is copied, its pointers are written and the stable listing shows every promoted key, every other `<fmt>/stable/` object is deleted. A snapshot promote copies only the selected version's packages, so stable ends holding exactly that version.
- **Order and floors**: upload or copy first, list, delete second, so an index never names a missing file. Nothing is deleted when the listing lacks a file the run wrote, when a candidate snapshot's marker cannot be read, or when a tree was not built (a missing `dist/repos/<fmt>`; an empty one is refused before any write). Only those four trees, under a one-segment channel, are ever pruned: never `cli/`, `npm/`, `snapshots/` or another channel. The deletes are batched `delete-objects` calls whose per-key `Errors` fail the run.
- **Housekeeping** Phase 8f keeps the top `R2_NPM_KEEP_VERSIONS` (20) semvers of `npm/<channel>/` only; the package trees are not its concern.

## Why this is a separate file

`CLAUDE.md`'s own rule is to stay under budget by cutting what already has a home elsewhere (`agent/plans/PLAN-tooling-transformation.md`, box W11 P5b). `release_mode`'s semantics, the three less-visible dispatch inputs and the soak-skip behavior did not exist in any `docs/` file before this one -- deleting them from `CLAUDE.md` without first writing them somewhere would have
discarded their only record. Verified against the two release workflows directly (`.github/workflows/cd-v2.yml`, `.github/workflows/promote-stable.yml`), not copied from `CLAUDE.md`'s prior wording.
