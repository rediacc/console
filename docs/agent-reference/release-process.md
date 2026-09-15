# Release process

Single pipeline: CI validates everything BEFORE publish. CD is a thin promote step, and
if CI fails, CD never triggers.

```
CI: quality -> build -> dry-run -> validate install (6 platforms) -> ci-complete
CD (auto on CI success): promote Docker -> git tag -> GitHub Release -> R2 -> deploy edge
```

Install validation runs pre-publish against R2 staging artifacts. Docker is validated on
push-to-main only (PR images are dry-run on a PR).

The mechanical job topology (every workflow, folded to one row per stage of its `needs:`
graph) is generated, not hand-maintained: the `job-graph` region in
[scripts/data/doc-registry.md](../../scripts/data/doc-registry.md). This file explains the
concepts that table cannot show -- what `release_mode` means, when a soak period applies,
and the exact commands.

## Release to Edge (`cd-v2.yml`)

Dispatched automatically from CI's `finalize-release-sentinel` job right after the release
sentinel is sealed, or manually:

```
gh workflow run "Release to Edge" -f ci_run_id=<id> -f release_mode=patch|retry
```

`release_mode` is a `workflow_dispatch` `choice` input with only two values --
**GitHub itself rejects `minor`/`major`**, there is no in-repo validation to bypass:

- `retry` (the default) -- re-run publish for the version the sentinel already computed.
  Use this for a publish that failed after the version was decided (e.g. a transient R2 or
  Docker push failure); it does not recompute the version.
- `patch` -- recompute `next_version` from merged PR labels and existing git tags, then
  publish. This is the normal path for a manual or CI-triggered edge release.

Three more inputs, none in `CLAUDE.md` before this doc existed:

- `publish_stable` (boolean) -- also promote straight to the stable channel in the same
  run, skipping the normal 7-day soak. This is the **hotfix** path:
  ```
  gh workflow run "Release to Edge" -f ci_run_id=<id> -f release_mode=patch -f publish_stable=true
  ```
- `deploy_workers_only` (boolean) -- redeploy the Cloudflare Workers only, skipping the
  version bump, CLI build, Docker promote and GitHub Release. For when the release
  artifacts are already correct and only the Worker deploy needs to re-run.
- `allow_stale_ci_run_id` (boolean) -- bypasses the "`ci_run_id` must be the latest green
  Console CI on main" guard. Only for cherry-picking a specific prior CI run; using it to
  publish an old run ahead of a newer green one is exactly the case the guard exists to stop.

`ci_run_id` may be left empty to auto-derive the latest green Console CI on `main`.

## Release to Production (`promote-stable.yml`)

```
Daily cron: 0 6 * * * UTC
Manual:     gh workflow run "Release to Production" -f force=true
```

Promotes the current edge release to the stable channel (`eu`/`us`/`asia`), serving
`www.rediacc.com`. Runs on a daily cron and refuses to promote a version still inside its
`SOAK_DAYS` (7) window unless dispatched with `force: true`, which skips the soak check
entirely -- there is no partial-skip.

## Why this is a separate file

`CLAUDE.md`'s own rule is to stay under budget by cutting what already has a home
elsewhere (`agent/PLAN-tooling-transformation.md`, box W11 P5b). `release_mode`'s
semantics, the three less-visible dispatch inputs and the soak-skip behavior did not exist
in any `docs/` file before this one -- deleting them from `CLAUDE.md` without first writing
them somewhere would have discarded their only record. Verified against the two release
workflows directly (`.github/workflows/cd-v2.yml`, `.github/workflows/promote-stable.yml`),
not copied from `CLAUDE.md`'s prior wording.
