# Release process

CI validates and CD publishes. Edge is released two ways, sharing the R2 sentinel lock: CD (`cd-v2.yml`) on every merge to main, and `npm run release:local -- --channel edge` from the operator's machine as the agent's faster extra path. Stable is CI/CD only (`promote-stable.yml`, after the soak) and a stable deploy always needs `RELEASE_ASKED`.

```
CI: quality -> build -> dry-run -> validate install (6 platforms) -> ci-complete
CI on main: ci-complete -> finalize-release-sentinel (seal cli/v<V>/.released, dispatch CD)
CD: init (git tag v<V>) -> promote Docker -> deploy edge -> smoke + install validation -> submodule tags, Homebrew, GitHub Release
release:local (edge): version -> gates -> builds -> stage -> seal + tag -> publish -> deploy -> smoke -> tag and release -> record
```

Install validation runs pre-publish against R2 staging artifacts. Docker is validated on push-to-main only (PR images are dry-run on a PR).

## Release channels

Two channels, both production-quality:

- **edge** -- released by CD on every merge to main, or by `release:local --channel edge`, downloaded from
`releases.rediacc.com/cli/edge/` (R2 bucket `rediacc-releases`), serving `edge.rediacc.com`.
- **stable** -- the default, promoted from edge by `promote-stable.yml` (see Release to Production below),
downloaded from `releases.rediacc.com/cli/stable/`, serving `www.rediacc.com`.

R2 layout: `rediacc-releases/cli/{edge,stable}/{manifest.json,latest.json,rdc-*}`.

**CORRECTION to a claim that was in CLAUDE.md: edge's D1 is NOT cloned from production daily.** `.github/workflows/edge-clone-d1.yml`'s own header says otherwise: *"Edge D1 databases are now persistent for the beta channel. Daily cloning from production is disabled; use workflow_dispatch for manual runs."* The workflow still exists for a manual, on-demand clone -- it is not
scheduled.

The mechanical job topology (every workflow, folded to one row per stage of its `needs:` graph) is generated, not hand-maintained: the `job-graph` region in [scripts/data/doc-registry.md](../../scripts/data/doc-registry.md). This file explains the concepts that table cannot show -- what `release_mode` means, when a soak period applies, how the local edge entry orders its steps and which gates refuse it, and how a release is rolled back.

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

`check:ci-workflow-invariants` (`.ci/rediacc_ci/security/ci_workflow_invariants.py`, release-order phase) enforces the shape on the job graph. It refuses a version-tag step behind any job other than `init`, a tag step or job whose `if:` reads `retry_mode`, a dispatch that does not immediately follow the seal under the same `if:`, `contents: write` anywhere in cd-v2, an inline `git push` in a cd-v2 `run:` step that is not on the `preset: cd` App token, and a `cd` preset that stops requesting `workflows: write`.

### CD preflight: CD failures predicted before the merge

`rediacc_ci.release.cd_preflight` is read-only and judges the live release state: (a) the sentinel/tag bijection now, (b) the bijection after the next housekeeping runs and this release, (c) the contract floor and channel pointers, (d) the version under release, and the Validate Promotion budget. An unreadable answer (no `aws`, no credentials, R2 or `git ls-remote` unreachable, zero sentinels) is UNCHECKED and exits non-zero like DRIFT. It runs at three sites:

- `ci.yml` job `cd-preflight` (CD Preflight), on same-repo PRs and on pushes to `main`, with `--phase pr --release-version <initialize next_version> --checks a,b,c,d,promotion`. Fork PRs skip it (no secrets). `homebrew` is deselected because its dry run needs the private tap submodule and real checksums. CI Complete aggregates it in the soft tier.
- `cd-v2.yml` `init`, step `CD preflight`, with `--phase cd --checks a,c,d`, AFTER `Create version tag`: before that step v<V> is sealed and untagged, so an earlier preflight would red every release.
- `housekeeping.yml` `cleanup`, step `Release-state preflight`, with `--checks a,c`, after the retry step and before `cleanup_versions`, which has no status function and is skipped when the preflight is red.

`check:ci-workflow-invariants` pins all three sites, their check lists, the PR arm of the job's `if:` and the step order. Locally: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile r2-artifacts -- python3 -m rediacc_ci.release.cd_preflight --phase pr --release-version X.Y.Z`, with the `aws` CLI on `PATH`.

The `release` PR label sets `publish_stable` on the automatic dispatch. When the merged PR carries the exact label `release` and not `bump-none`, `initialize` records `publish_stable=true` and finalize-release-sentinel dispatches cd-v2 with `-f publish_stable=true`, so the merge publishes to edge AND stable with no soak (operator ruling 2026-09-30). A failed PR lookup still releases, to edge only. The decision lives in `.ci/rediacc_ci/ci/dispatch_release.py`.

## Release to Production (`promote-stable.yml`)

```
Daily cron: 0 6 * * * UTC
Manual:     gh workflow run "Release to Production" -f force=true
```

Promotes the current edge release to the stable channel (`eu`/`us`/`asia`), serving `www.rediacc.com`. Runs on a daily cron and refuses to promote a version still inside its `SOAK_DAYS` (7) window unless dispatched with `force: true`, which skips the soak check entirely -- there is no partial-skip.
A green scheduled nightly (`Console CI` on `main`) also triggers it through `workflow_run`, and that run skips the soak only when the edge tag's commit is the nightly's `head_sha` or an ancestor of it (`rediacc_ci.release.nightly_tested_edge`); an edge the nightly did not contain, or any failed lookup, falls back to the soak rule. The rollback-label check and every deploy and verify job run the same on all three triggers, a `promote-stable` concurrency group queues them rather than running two at once, and the summary names the trigger and the rule (`force`, `nightly` or `soak`) that decided.

Both R2 promotes (this one and the `publish_stable` hotfix lane) copy `<dir>/edge/` to `<dir>/stable/` server-side with one `aws s3api copy-object` per object, so no release bytes pass through the runner; only the four channel pointers (`cli/install.sh`, `cli/install.ps1`, `rpm/rediacc.repo`, `archlinux/rediacc.conf`) are fetched, stamped for stable and uploaded after the rest of their tree. `.ci/rediacc_ci/deploy/r2_promote.py` carries the plan and R2's copy limits.

## Local edge release (`release:local`)

```
npm run release:local -- --channel edge [--dry-run]
npm run release:local -- --channel edge --workers-only --regions eu,us [--dry-run]
```

`rediacc_ci.release.local` is one declarative `STEPS` table, the agent's local path to edge, sharing the R2 sentinel lock with CD. `--dry-run` prints every step with profile and key names, reads no secret value and writes nothing. `--workers-only` redeploys the Cloudflare Workers for the listed regions and skips the version, builds, Docker and Release steps.

Edge and bench need no ask. A stable deploy always needs `RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z`, the minute of the operator's answer in the transcript, enforced by the `block_unasked_release` guard (`ci-gates.md`, *Never push to `main` or cut a release unasked*).

The version comes from `resolve_version --bump-type` inside the entry, from the labels merged since the last tag (`versioning.md`).

### Steps, in order

1. **Gates** (below), all refusing before any build.
2. **Builds**, in the release clone, each step timed: renet under the `release-local` bws profile (the production `ACCOUNT_ED25519_PUBLIC_KEY`) followed by the signing-key gate, the CLI bundle and npm tarball, the Linux SEAs (linux-x64, both musl targets, linux-arm64 in a `linux/arm64` node container) and the Docker renet, rdc and server images through buildx.
3. **Assist dispatch**, started at minute zero: `local-release-assist.yml` builds the mac and win SEAs and runs the mac and win install legs against the staged bytes. The entry awaits it before stage.
4. **Stage**: signed packages, manifest, pages, package repos, the `:edge` Docker retag, validation and the R2 upload.
5. **Seal and tag**: `write_release_sentinel` seals `cli/v<V>/.released`, and `rediacc_ci.release.tag` creates `v<V>` at once. The pair is one unit, held by the `STEPS` invariant test: the tag precedes every step that can fail.
6. **Publish**: promote to `:V` and `:latest`, the Stripe sync and webhook verify, cleanup of the channel tags.
7. **Deploys**, each with a deploy record: www and the executor artifacts, then per region the account Worker (behind the order check), the account secrets, the proxy and the console executor.
8. **Smoke**: `verify_edge_endpoints` and a Linux install quick check in local docker.
9. **Tag and release**: submodule tags, the Homebrew tap formula commit, the contract-floor ratchet and the GitHub Release.
10. **Record**: the release record in R2.

Neither the local entry nor CD pushes console `main` for release state. The tap repository receives its formula commit, admitted at the git layer by the release-run record; the contract floor is an ordinary commit in the next PR, and `cd_preflight --checks c` warns when it lags.

## Gates

`rediacc_ci.release.local_gates` refuses unless every one of these holds:

- a whole, green `ci:quick` receipt exists for the exact `HEAD` tree;
- every `vm:check` hit since the channel's previous release tag is admitted by a VERIFIED `vm:check` receipt for that tree, and the backup receipt exists when backup paths moved;
- a fresh clone of `HEAD` with submodules, at `.ci/cache/release/<tree>/`, is clean, with every submodule at its pointer and unmodified;
- a fresh fetch succeeded and `HEAD` equals `origin/main`; a failed fetch refuses;
- the release lock is free: the R2 sentinel is absent and `check_existing_release` agrees.

The clean check runs on the clone because the shared checkout always holds other sessions' ledgers. Builds run in the same clone. Both receipts are re-taken on `main` after a merge, since a pointer move changes the tree.

## The order check

`.ci/config/release-requires.json` declares which published CLI an account deploy needs. `rediacc_ci.release.order.account_refusal(channel, account_pointer)` treats an entry as active once its `since` commit is an ancestor of the account pointer. The channel's published CLI counts only when its R2 manifest version V has both the sentinel `cli/v<V>/.released` and the tag `v<V>`, and every `cli_commits` entry must be an ancestor of `v<V>`; otherwise the answer is `cli-behind` and the account Worker is not deployed. The account Worker therefore reaches a channel after the CLI that it requires.

## The signing-key gate

`rediacc_ci.release.renet_key_gate` reads the build info of every renet binary and image with `go version -m` and refuses an empty key, the DEV key fingerprint and `tags=nolicense`. The cached cross-build path builds darwin and windows renet with the production key and version, so the gate has nothing keyless to admit.

## Provenance

A local edge release ships a SHA256 manifest signed with the release GPG key (`RELEASE_GPG_PRIVATE_KEY`, bound by the `release-local` profile). Sigstore provenance needs the GitHub OIDC identity, so it belongs to the CD path. Pushes of the tag and the tap formula use the session's GitHub token.

## Deploy records and the release record

`deploy_record after --sink r2` writes `release-records/v<V>/<channel>/deploy-record-<target>-<region>.json` once, through a write-once guard: worker names, version ids before and after, the D1 bookmark, the smoke rc, artifact manifest sha256s and the rollback command. The www record carries the version id before and after, the `wrangler rollback` command and the smoke rc. The release record, one per version and channel under `release-records/`, lists every step with its outcome and timing, and holds the run id of the main CI run on the released SHA.

## Rollback

The model is fix-forward: cut the corrected release through CD or the entry. For an immediate revert, the deploy record names the previous version id and the exact command, `wrangler rollback <version-id> --config <wrangler config> -y`, run under the `deploy-workers` bws profile. A D1 migration is not undone by a Worker rollback, so the record's D1 bookmark is the restore point. A failed local run after the seal and tag is repaired by running the entry again for the same version; the tag step is idempotent and refuses on an unknown `ls-remote` answer.

## Secrets

The `release-local` bws profile in `.ci/config/secret-supply.json` binds the signing public key, the GPG key and passphrase, the bot identity, the Cloudflare zone id, the R2 credentials, the Stripe key and the www Worker secrets. The GHCR and GitHub tokens are written into the store by the session through `bws_env store-from-env`. The entry checks its host prerequisites (`aws`, `nfpm`) first, and the devbox is the fallback for a missing tool.

## Release-run admission

The entry writes `.ci/cache/release/run-<id>.json`, a record of its pid, start time, command line, tree, version, channel and the exact pushes it will make, and exports `REDIACC_RELEASE_RUN`. The git `pre_push` hook (`.claude/rediacc_hooks/git/release_run.py`) admits a pushed line only when the record's pid is in the hook's parent chain with a matching start time, the tree equals `HEAD^{tree}` and the `(toplevel, remote_ref, oid)` is listed. `block_git_hook_bypass` refuses `REDIACC_RELEASE_RUN` set by an agent.


## Package tree retention

Each Linux package tree (`apt/<channel>/`, `rpm/<channel>/`, `apk/<channel>/`, `archlinux/<channel>/`) keeps only what its index lists (operator ruling 2026-10-06), on `edge`, `stable` and every `pr-N` channel. Pinned old versions stay installable from the immutable `cli/v<semver>/`, which nothing here touches.

- **Upload** (`rediacc_ci.deploy.upload_repos_to_r2`): after every sync, install-script upload, snapshot seal and cache purge, each built tree is listed, the listing must hold every file of `dist/repos/<fmt>`, and then every other object in `<fmt>/<channel>/` is deleted. On `edge` the keep set also holds the package files named by the sealed snapshot of any other version `check_soak_period` may still select (newer than stable), because the soak-gated promote copies those packages from `<fmt>/edge/`.
- **Promote** (both lanes, `r2_promote.promote_tree`): after a tree is copied, its pointers are written and the stable listing shows every promoted key, every other `<fmt>/stable/` object is deleted. A snapshot promote copies only the selected version's packages, so stable ends holding exactly that version.
- **Order and floors**: upload or copy first, list, delete second, so an index never names a missing file. Nothing is deleted when the listing lacks a file the run wrote, when a candidate snapshot's marker cannot be read, or when a tree was not built (a missing `dist/repos/<fmt>`; an empty one is refused before any write). Only those four trees, under a one-segment channel, are ever pruned: never `cli/`, `npm/`, `snapshots/` or another channel. The deletes are batched `delete-objects` calls whose per-key `Errors` fail the run.
- **Housekeeping** Phase 8f keeps the top `R2_NPM_KEEP_VERSIONS` (20) semvers of `npm/<channel>/` only; the package trees are not its concern.

## Why this is a separate file

`CLAUDE.md` stays under budget by cutting what already has a home elsewhere (`agent/plans/PLAN-tooling-transformation.md`, box W11 P5b). The entry's flags, gates and records are described here and verified against `.github/workflows/cd-v2.yml`, `.github/workflows/promote-stable.yml` and `.ci/rediacc_ci/release/` (`local.py`, `local_gates.py`, `order.py`, `renet_key_gate.py`, `tag.py`) and `agent/plans/PLAN-local-release.md`.
