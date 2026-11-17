# PLAN-console-private: make rediacc/console private, run its CI from a public wrapper repo rediacc/rediacc, and ship releases without GitHub Releases

Status: proposed -- operator rulings ASKED:2026-11-17T05:43Z, ASKED:2026-11-17T07:02Z and ASKED:2026-11-17T08:46Z, plus the 07:07Z naming ruling (all quoted in Rulings). Q1-Q6 are answered (see "Answered questions"). Not promoted yet: operator /ask ASKED:2026-11-17T09:06Z "Site fixes now, private later" and "Next PR after #605 (Recommended)": promote it as the plan of the branch that follows PR #605's merge.
Owner: d778be9d
Depends-On: no-dep -- builds on what has already landed: R2 release delivery, `release-records/v<V>/` (cd_edge_record.py), the app-token action, the git-hook layer (.claude/rediacc_hooks/git/) and the backup trigger (spawn_backup, backup_ref.py). No box waits on another plan.
Priority: P1 -- the source of console (and through CI logs, part of private/*) is public today. The operator's goal is "Hide code, logs can leak".
Concurrency: exclusive -- every workflow, every `.github/actions` composite, about 44 `.ci` modules that read GITHUB_*, the release path, the git hooks and the merge hooks all change. A parallel CI plan would collide on ci.yml, cd-release-edge.yml, githooks.py and the parity gates. Waves 1-3 run as file-disjoint writers inside this plan. Wave 4 (cutover) is serial and live.
Owns: agent/plans/PLAN-console-private.md, .github/workflows/*.yml, .github/actions/**, .github/ISSUE_TEMPLATE/config.yml, .ci/rediacc_ci/wrapper/** (render.py, ping.py, sweep.py, check_runs.py, merge_gate.py), .ci/rediacc_ci/core/console_ctx.py, .ci/rediacc_ci/release/{create_github_release,release_notes,check_existing_release,assert_edge_tag_exists,verify_release_assets,mark_production,local,verify_artifact_attestation}.py, .ci/rediacc_ci/build/generate_cli_manifest.py, .ci/rediacc_ci/housekeeping/cleanup_versions.py, .ci/rediacc_ci/{ci,review,quality,version}/*.py (GITHUB_* sweep only), .ci/scripts/quality/check_console_context.py, .ci/scripts/quality/check_artifact_allowlist.py, .ci/config/well-known.env, .ci/config/wrapper.json, .ci/rediacc_ci/tests/test_wrapper_*.py, .ci/rediacc_ci/tests/test_console_ctx.py, .ci/rediacc_ci/tests/test_release_notes.py, .claude/rediacc_hooks/git/githooks.py, .ci/rediacc_ci/setup/githooks.py, .claude/hooks/post-bash/arm_ci_watch.py, .claude/hooks/stop/wl_prreview.py (the --answer ping only), .claude/rediacc_hooks/guards/block_wrapper_direct_push.py, .claude/rediacc_hooks/guards/block_unverified_console_merge.py, .claude/rediacc_hooks/tests/test_githook_wrapper_*.py, .claude/rediacc_hooks/tests/test_block_wrapper_direct_push.py, .claude/rediacc_hooks/tests/test_block_unverified_console_merge.py, .claude/rediacc_hooks/tests/test_arm_ci_watch_ping.py, packages/www/src/pages/[lang]/downloads.astro, packages/www/src/utils/latest-release.ts, packages/www/src/utils/release-parser.ts, packages/www/src/config/constants.ts, packages/www/src/content/docs/*/{siem-integration,rules-of-rediacc,experimental-vms}.md, scripts/gates/check-external-links.ts, README.md, CONTRIBUTING.md, private/homebrew-tap/README.md (gitlink bump), .claude/commands/pr-merge.md, .claude/skills/ci-watch/**, docs/agent-reference/ci-wrapper.md
Live-Proof: bench -- the www downloads page moves from the GitHub API to the R2 manifest (surface `www`, packages/www/src/**), proved by a fresh www-smoke receipt on bench. The CI and repo flips are not registry surfaces; the C-boxes prove them.

## Context (checked 2026-11-17 by the planning agent; a writer re-reads each citation before relying on it)

1. **Repos.** The submodules are private/renet, private/elite and private/account (private) and private/homebrew-tap (public) (.gitmodules:1-16). `gh api repos/rediacc/console` answers `visibility: public, has_discussions: true`. The org plan is `free`.
2. **The CI estate.** There are 38 workflows (19,217 lines) and 10 composites in .github/actions (1,279 lines). The workflows triggered by a console repo event are:
   - ci.yml (push main, pull_request opened/synchronize, schedule, workflow_dispatch; .github/workflows/ci.yml:3-42);
   - ci-obs-mirror.yml (push main and pull_request, both with `paths:` filters) and ci-vm-bake.yml (push main with `paths:`);
   - ops-claude-review.yml (workflow_run on "Console CI", pull_request ready_for_review, workflow_dispatch);
   - ops-cleanup-preview.yml (pull_request_target closed);
   - ops-cleanup-r2-staging.yml (pull_request closed);
   - ops-review-status.yml (workflow_run on "Claude Review", pull_request_review, pull_request_review_comment, issue_comment, workflow_dispatch).

   Every other workflow is schedule, workflow_dispatch, workflow_run or workflow_call, and those keep working unchanged inside one repo.
3. **Context reads in .github:**
   - `github.event_name` 110, `github.sha` 72, `github.event.pull_request` 53, `github.ref` 44, `github.repository` 24, `github.head_ref` 7, `github.run_id` 13;
   - `concurrency:` 25, `upload-artifact` 60, `environment:` 10 lines (live blocks at .github/workflows/cd-release-edge.yml:321, .github/workflows/cd-deploy-worker.yml:46, .github/workflows/cd-deploy-account.yml:257).

   In non-test `.ci` Python (excluding .ci/cache): 83 GITHUB_REPOSITORY lines and 17 GITHUB_SHA lines across 44 files that read GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_REF or GITHUB_EVENT_PATH. The largest readers are ci/initialize.py (8), ci/dispatch_release.py (8), version/detect_bump_type.py (5) and ci/cancel_older_runs.py (5). The brief's 262 and 63 counted the cache and tests. 159 non-test `.ci` files mention `.github/` paths (parity and reachability gates).
4. **Required checks today.** Ruleset 12344707 "Branch Protection" requires `CI Complete` and `Review Complete` with integration_id 15368 (GitHub Actions), strict, rebase-only merges. Its bypass actors are RepositoryRole 5 and Integration 2772000 (the App). Ruleset 24351140 holds deletion, linear history and non-fast-forward only. (Both read with `gh api repos/rediacc/console/rulesets/<id>`. The brief put the required checks on 24351140; they are on 12344707.)
   - `CI Complete` is the ci.yml job at .github/workflows/ci.yml:2076.
   - The App token has no checks scope today (.github/workflows/ci.yml:161-163 comment; .github/actions/app-token/action.yml presets readonly, pr-read, cd and housekeeping).
5. **Release reads of GitHub:**
   - .github/workflows/cd-release-edge.yml:681-692 (`gh release view` decides what a retry owes) and .github/workflows/cd-release-edge.yml:795 (create_github_release);
   - .ci/rediacc_ci/release/check_existing_release.py:54, .ci/rediacc_ci/release/assert_edge_tag_exists.py:158-161 (`probe_gh_release`), .ci/rediacc_ci/release/verify_release_assets.py:35-37;
   - .ci/rediacc_ci/release/mark_production.py:4, :138 and :227 (`--latest` on the GitHub Release);
   - .ci/rediacc_ci/housekeeping/cleanup_versions.py:4 and :480 (Phase 1 `gh release delete`).
   - .ci/rediacc_ci/release/local.py:25: SHA256SUMS and SHA256SUMS.asc "ride the GitHub Release" only.
6. **Customer delivery is already on R2:**
   - packages/www/public/install.sh:20, :351 and :374-376 (`releases.rediacc.com`);
   - packages/cli/src/services/update/updater.ts:33 and :53-56 (`${WK_RELEASES_ORIGIN}/cli/<ch>/manifest.json`);
   - rediacc-cli.rb:9-34.

   The live `cli/stable/manifest.json` carries `"releaseNotesUrl": "https://github.com/rediacc/console/releases/tag/v3.0.1"`, built at .ci/rediacc_ci/build/generate_cli_manifest.py:325. `WK_RELEASES_ORIGIN` is at .ci/config/well-known.env:28 and `WK_GH_REPO=rediacc/console` at .ci/config/well-known.env:63.
7. **The downloads page reads GitHub.**
   - packages/www/src/pages/[lang]/downloads.astro:29-37 calls `fetchLatestRelease()` and throws in a production build when it gets null.
   - packages/www/src/utils/latest-release.ts:36 reads `${WK_GH_API_BASE}/repos/${GITHUB_REPO}/releases/latest`.
   - packages/www/src/utils/release-parser.ts:42-47 uses `browser_download_url` and `size`.
   - Once console is private, this request answers 404 and **every www build fails**. So R-boxes must land before the flip.
8. **Public links to console:**
   - experimental-vms.md (13 locales) links issue #380;
   - packages/www/src/content/docs/en/rules-of-rediacc.md:125 (13 locales) links the heartbeat template tree;
   - packages/www/src/content/docs/en/siem-integration.md:24, :35 and :57 (en only) link compose/otel-collector and event-schema.ts and run `git clone`;
   - README.md:10, CONTRIBUTING.md:6, .github/ISSUE_TEMPLATE/config.yml:7 (discussions) and private/homebrew-tap/README.md:42.
   - scripts/gates/check-external-links.ts:846-857 builds API URLs from WK_GH_REPO.
9. **Source-bearing artifacts.** .github/workflows/ops-local-release-assist.yml:153-160 uploads `private/bin/` (renet binaries) as an artifact, even though the same set is already staged on R2 at `staging/local-release/v<V>/private-bin/` (.ci/rediacc_ci/release/local.py:23).
10. **The live-proof map.** Surface `www` covers `packages/www/src/**` with live target bench. Check `www-smoke` exists (.ci/config/proof-tiers.json `tiers.live.checks`).
11. **The git-hook layer (the new trigger's carrier; re-verified 2026-11-17).**
    - Git runs `.claude/rediacc_hooks/git/` hooks for agent, operator and `!` pushes and for subprocesses (githooks.py docstring :3). The installer `.ci/rediacc_ci/setup/githooks.py` wires `reference-transaction` in HOOK_NAMES at :24, in console and every checked-out submodule, as local config only.
    - `reference_transaction` (.claude/rediacc_hooks/git/githooks.py:281-283) acts only on the `prepared` state today and returns 0 for every other state.
    - `main` (.claude/rediacc_hooks/git/githooks.py:1347-1353) runs post-commit, post-rewrite and post-merge before the `COMMIT_POLICY_OK` check at :1353. `reference-transaction` and `pre-push` are routed after it (:1361-1364), so today the override would skip them.
    - A successful push updates `refs/remotes/origin/<b>`, which fires reference-transaction in its `committed` state (verified on git 2.53.0). A `git fetch` also moves `refs/remotes/origin/*` in the same state, so the trigger has to deduplicate (Design 2).
    - The detached-worker template: `spawn_backup` (.claude/rediacc_hooks/git/githooks.py:1284-1316) starts a worker in its own session with stdin closed and output going to `<git-dir>/rediacc-backup/log`, and never raises. `.ci/rediacc_ci/dev/backup_ref.py` runs under one flock (`<git-dir>/rediacc-backup/lock`, :154-169, :211) with `GIT_TERMINAL_PROMPT=0` (:106). It refuses any forced argv before running it (:83-112), and the next trigger retries a failed push (docstring :11).
    - `.claude/hooks/post-bash/arm_ci_watch.py` already reacts to `git push` and `gh pr create`, and arms a detached `ci-trace --wait` per head (docstring :2-10, :229).
    - Pre-bash guards are auto-discovered modules in `.claude/rediacc_hooks/guards/` (.claude/rediacc_hooks/dispatch.py:41). The older plan text named `.claude/hooks/pre-bash/**`, which does not exist. The hook tests run with `python3 .claude/rediacc_hooks/run_tests.py -k <expr>`, and no `hooks-selftest` npm script exists.

## GitHub product facts this plan relies on (fetched 2026-11-17)

- **Workflow version per run.** "Each workflow run will use the version of the workflow that is present in the associated commit SHA or Git ref of the event." So a push to a wrapper branch runs that commit's YAML, and a PR that edits workflows is tested with its own YAML with no extra mechanism. Source: https://docs.github.com/en/actions/writing-workflows/about-workflows (workflows page)
- **Which pushes start workflows.** Events made with the repository's GITHUB_TOKEN do not create new workflow runs; pushes made with a personal or `gh` user token, or a GitHub App installation token, do. Source: https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication (GITHUB_TOKEN page)
- **Schedules.** The shortest interval is once every 5 minutes. Scheduled runs can be delayed or dropped under high load. They run only from the default branch. In a public repository, scheduled workflows are disabled automatically after 60 days with no repository activity. Source: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- **Check runs.** Creating a check run requires a GitHub App. "Write permission for the REST API to interact with checks is only available to GitHub Apps." Source: https://docs.github.com/en/rest/checks/runs
- **Environments.** "Users with GitHub Free plans can only configure environments for public repositories." On a switch to private, configured protection rules and environment secrets are ignored and no environment can be configured. Source: https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment
- **Protected branches and compute.** GitHub Team lists "Protected branches" and "Required pull request reviewers" under "Advanced tools and insights in private repositories". Free lists "$12 USD of included compute usage per month" and "Deployment protection rules for public repositories". Source: https://docs.github.com/en/get-started/learning-about-github/githubs-plans
  - **Consequence: on Free, a private console has NO enforced ruleset, required check or auto-merge.** The merge gate becomes local (Design 4).
  - The about-rulesets page names no plan. Box A1 proves the fact on the live repo after the flip instead of trusting the summary.
- **Path filters on push.** The `paths` and `paths-ignore` filters on a `push` event are matched against the files changed by the pushed commits, here wrapper commits that touch only `.github/**` and `CONSOLE_CONTEXT.json`. So the renderer cannot keep a console path filter as a trigger filter (Design 1).

The workflows-page and GITHUB_TOKEN-page wording is as the 2026-11-17 investigation quoted it. A writer re-reads both pages before W1 and W5 rely on them.

## Rulings (quoted where the operator's words are the ruling; the 07:07Z rename is paraphrased, its words are in worklist item #12e2fd33)

- ASKED:2026-11-17T05:43Z:
  - images: "Keep ghcr, public (Recommended)";
  - GitHub Releases: "Stop creating them (Recommended)";
  - release notes: "Notes file on R2".
- ASKED:2026-11-17T07:02Z:
  - goal: "Hide code, logs can leak";
  - CI hosting: "Public wrapper repo".
- 2026-11-17T07:07Z: the operator renamed the wrapper from rediacc/rdc to **rediacc/rediacc**, because console already contains rdc (verbatim in worklist item #12e2fd33).
- ASKED:2026-11-17T08:46Z:
  - merge gate: "Local guard + merge verb (Recommended)";
  - CI trigger: "Git hook + 5-min sweep (Recommended)";
  - ping shape: "Rendered CI tree (Recommended)";
  - the operator's reason, verbatim: "We should not depend on external/manual steps. Can't we use git push/commit mechanisms? Maybe we with claude hooks we can enforce AI to push to both parent and child. We already have some mechanisms."
  - Defaults stand for Q2, Q4, Q5 and Q6.
- Earlier operator words, standing: "Backward compatibility is not important from the customer perspective." "We should keep the code minimal at rediacc/rediacc as much as possible." So this is a clean break with no compatibility shims (CLAUDE.md rule 2).

## Answered questions (ASKED:2026-11-17T08:46Z)

- **Q1 Trigger transport. ANSWERED: "Git hook + 5-min sweep (Recommended)".** The console git hooks push a rendered CI tree to the wrapper after each successful console push. A 5-minute sweeper on wrapper main catches anything the hook missed. There is no webhook, no Worker, no repository_dispatch and no console Actions minute (Design 2). Two push URLs on `origin` were ruled out, because they would upload private history to the public repo.
- **Q2 Per-PR workflow changes. ANSWERED: default stands, and it is now native.** GitHub runs the workflow version in the pushed commit, so a PR that edits workflows runs its own YAML on `run/pr-<N>`. No router or `workflow_dispatch --ref` is needed.
- **Q3 Merge gate. ANSWERED: "Local guard + merge verb (Recommended)"** (Design 4). GitHub Team is not bought.
- **Q4 Customer issue intake. ANSWERED: default.** Remove the discussions link and point to the www support page.
- **Q5 SIEM docs. ANSWERED: default.** Inline the collector config and the event-schema excerpt into the docs page.
- **Q6 Old GitHub Releases. ANSWERED: default.** Leave them; they become invisible with the repo, and housekeeping stops touching them.
- **Ping shape. ANSWERED: "Rendered CI tree (Recommended)".** The ping is a wrapper commit holding the rendered `.github` tree plus `CONSOLE_CONTEXT.json`. It is not an empty marker and not a dispatch.

## Design

### 1. What lives in rediacc/rediacc (minimal by construction)

- **Console stays the single source of truth.** The workflow YAML and composites stay in console's `.github/` with their native triggers, so the 159 parity and reachability gates keep reading real files, and native console CI keeps working during the shadow and after a rollback.
- **The wrapper holds only generated files:**
  - `.github/workflows/*.yml` and `.github/actions/**`, rendered from console by `.ci/rediacc_ci/wrapper/render.py`;
  - `CONSOLE_CONTEXT.json`: `{sha, ref, pr, base_sha, event}` (plus `review_id` on review pings);
  - a 10-line README saying "CI host for a private repository; nothing to see here";
  - a `WRAPPER-SOURCE` file naming the console sha it was rendered from.

  No hand-written code lives there.
- **Wrapper history never contains a console commit.** Each wrapper commit is built with `git commit-tree` from the rendered tree only. Its parent is the previous wrapper tip, and its author and committer are a fixed `rediacc-wrapper <noreply@rediacc.com>` identity, so no operator email appears. The message is `render <sha12> <ref> <event>`.
- **The renderer is close to a copy.** It:
  - (a) rewrites the `push`, `pull_request*`, `pull_request_target`, `pull_request_review*` and `issue_comment` triggers into one `on: push: branches: [...]` drawn from `[main, 'run/**', 'review/**']`, with a per-workflow filter set in `.ci/config/wrapper.json`:
    - ci.yml gets `[main, 'run/**']`;
    - ci-obs-mirror and ci-vm-bake get `[main]`, and ci-obs-mirror also gets `'run/**'`;
    - ops-claude-review and ops-review-status get `['review/**']`, plus their existing workflow_run trigger.

    The two cleanup workflows lose their event trigger and become `workflow_call` targets of the sweeper's closer job (Design 2). schedule, workflow_dispatch, workflow_run and workflow_call triggers pass through unchanged;
  - (b) moves any `paths:` or `paths-ignore:` filter out of the trigger into wrapper.json, where the `console-context` job evaluates it as `git diff --name-only <base_sha>..<sha>` on the console checkout and exposes `paths_match` (see the Product facts note on push path filters);
  - (c) writes a generated-file header.

  Every other rewrite lives in console's own YAML (the sweep in Wave 2), so the renderer stays small and its tests pin it byte for byte.
- **One wrapper-native workflow, `wrapper-sweep.yml`,** is rendered from console's `.github/workflows/wrapper-sweep.yml` like everything else. On console it is inert, because its jobs are guarded by `github.repository == 'rediacc/rediacc'`.
- **One new composite, `.github/actions/checkout-console`, replaces every `actions/checkout` of console.** It:
  - in the wrapper (`github.repository == 'rediacc/rediacc'`), reads `CONSOLE_CONTEXT.json` from the triggering wrapper commit (`github.sha`, or `github.event.workflow_run.head_sha` in a workflow_run follower). It then mints the App token (readonly preset, scoped to console, account, renet, elite and homebrew-tap) and checks out `rediacc/console` at the context sha with `submodules: recursive`;
  - on native console (shadow week, rollback), derives the same values from the native event, which makes it the one place outside console_ctx that reads `github.event.*`;
  - exports the context shim (Design 2).

### 2. Trigger, context shim and status bridge

- **Trigger: the git hook (`reference-transaction committed`).**
  - `main` in githooks.py routes `reference-transaction` with `argv[:1] == ["committed"]` **before** the `COMMIT_POLICY_OK` check, next to the post-* hooks (.claude/rediacc_hooks/git/githooks.py:1348-1353). A ping refuses nothing, and a push made under the override needs CI just as much. The `prepared` branch keeps its place after the override.
  - The committed handler reads stdin (`old new ref`) and keeps lines where `ref` is `refs/remotes/origin/<b>`, `new` is not the zero oid, and the repository's `origin` push URL is console's (submodules start nothing). For each line it calls `spawn_wrapper_ping(tree, branch, new)`. That function is modelled on `spawn_backup` (.claude/rediacc_hooks/git/githooks.py:1284-1316): detached with `start_new_session=True`, stdin closed, output appended to `<git-dir>/rediacc-wrapper/log`, the PYTHONPATH built the same way, and it never raises. Its argv is the seam `WRAPPER_PING_WORKER = ("-m", "rediacc_ci.wrapper.ping", "--ref", <b>, "--sha", <new>, "--quiet")`, which tests replace with a sleeper.
  - A lease tree starts nothing, because a lease never pushes.
  - The same state fires on a `git fetch` that moves `origin/<b>`. The worker's sha dedupe makes that a no-op whenever the wrapper already holds the sha. When it does not (a push made from another machine), the fetch-triggered ping is a useful catch-up.
- **The worker `.ci/rediacc_ci/wrapper/ping.py`** follows the backup_ref.py template. It takes one flock `<git-dir>/rediacc-wrapper/lock`; it waits up to 120 s and then exits 0 with `lock busy; sweeper covers <sha>` logged. It sets `GIT_TERMINAL_PROMPT=0` and refuses any forced argv before running it. Steps:
  1. Resolves the target. `--ref main` always proceeds. Any other branch runs `gh pr list -R rediacc/console --head <b> --state open --json number`, and no open PR means log and exit 0. Events: `push` for main, `pull_request` for a PR head, `review` or `ready_for_review` when passed with `--event`.
  2. Dedupes. It skips when `<git-dir>/rediacc-wrapper/state.json` already records `(target, sha, event)`. It also skips when the wrapper target's current `CONSOLE_CONTEXT.json` (read with `git ls-remote` plus a `--refmap=` fetch into the scratch repo) names the same sha and event.
  3. Renders `.github` from the console object database at `<sha>` (`render.py --from-object <sha>`, reading with `git ls-tree`/`cat-file`, no checkout) and writes the blobs, `CONSOLE_CONTEXT.json` (`sha, ref, pr, base_sha, event`), README and WRAPPER-SOURCE into the scratch bare repo `<git-dir>/rediacc-wrapper/repo.git`. That repo is created on first use with no `core.hooksPath` (no hook runs there, so nothing recurses) and has a single remote, the pinned `WRAPPER_URL`.
  4. Builds the commit with `mktree` and `commit-tree -p <previous wrapper tip of the target>`. A target branch's first commit uses the wrapper `main` tip as its parent, so the history never holds a console commit.
  5. Pushes without force to `refs/heads/main`, `refs/heads/run/pr-<N>` or `refs/heads/review/pr-<N>`, with the operator's `gh` credential (`gh auth git-credential`) or, inside Actions, the App token. Both start workflows (Product facts). A non-fast-forward rejection (a lost race) re-fetches the tip and rebuilds up to 3 times. A missing credential is logged and exits 0.
  6. Records the sha in state.json and logs the wrapper commit.

  It never refuses or delays the console push, which has already succeeded. `ping.py --ref <b> [--sha <s>] [--event <e>] [--review-id <id>]` is the one entry point shared by the hook, arm_ci_watch, wl_prreview, merge_gate, CD and the sweeper.
- **Other ping callers (pushes that no local console push covers):**
  - `arm_ci_watch.py` calls `ping.py --ref <b>` after `gh pr create` (the push before the PR existed was skipped as "no open PR") and with `--event ready_for_review` after `gh pr ready`. The watcher it arms re-pings once, with the state dedupe bypassed for that one call, when no wrapper run for the wrapper tip of `run/pr-<N>` appears within 3 minutes (`gh run list -R rediacc/rediacc --branch run/pr-<N>`).
  - `wl_prreview.py --answer` calls `ping.py --ref <b> --event review` after it posts, so Review Complete re-evaluates.
  - `merge_gate.py` calls `ping.py --ref main --sha <merged main sha>` after `gh pr merge`, because the merge moves console main on GitHub and no local push hook fires.
  - The CD steps that push the homebrew-tap pointer bump and the release-state commit to console main call `ping.py --ref main` with the App token. The sweeper backs this up.
- **Leak guards.**
  - `pre-push` in githooks.py gets a pinned `WRAPPER_URL` (https and ssh spellings of github.com/rediacc/rediacc). It refuses any push whose remote URL is the wrapper, from console or from any submodule. Only ping.py's hookless scratch repo pushes there.
  - The pre-bash guard `block_wrapper_direct_push` refuses an agent's `git push` naming the wrapper URL or a remote whose URL is the wrapper, and `git remote add|set-url` with the wrapper URL in console or a submodule.
  - Two push URLs on `origin` are ruled out: that would upload private history.
- **Context shim.**
  - Entry workflows lose the planned `workflow_dispatch` `console_*` inputs; `CONSOLE_CONTEXT.json` replaces them.
  - A first job, `console-context`, runs checkout-console and exposes `event, sha, ref, pr, base_sha, head_ref, paths_match` as job outputs. Job-level `if:` conditions read `needs.console-context.outputs.*`, because the GITHUB_ENV of one job is not visible to another job's `if:`.
  - A workflow_call child receives them as `with:` inputs; workflow_call inputs stay.
  - A workflow_run follower reads `CONSOLE_CONTEXT.json` from `github.event.workflow_run.head_sha`, which is the wrapper commit. This also mends the "workflow_run cannot resolve the PR" gap described in ops-review-status.yml.
  - Inside jobs, `checkout-console` exports `CONSOLE_REPOSITORY=rediacc/console`, `CONSOLE_SHA`, `CONSOLE_REF`, `CONSOLE_EVENT`, `CONSOLE_PR`, `CONSOLE_BASE_SHA` and `CONSOLE_HEAD_REF` to GITHUB_ENV.
  - Schedule runs on wrapper main read the `CONSOLE_CONTEXT.json` of that commit, so the YAML and the code come from the same console sha.
  - CI tests the PR head (`CONSOLE_SHA`), not a synthetic merge commit. merge_gate's strict "up to date with main" check makes the two the same at merge time.
  - Python reads context only through `rediacc_ci.core.console_ctx`. Local runs derive the same values from git, with no GITHUB_* fallback.
  - Run, artifact, cache, workflow and deployment API calls target `WK_GH_CI_REPO=rediacc/rediacc`, a new well-known. PR, issue, commit, check-run and tag calls target `WK_GH_REPO=rediacc/console`.
  - The gate the new `ci-console-context` gate (npm script `check:` prefix added when written) refuses `github.sha|ref|head_ref|event_name|event.pull_request` and the GITHUB_SHA/REF/HEAD_REF/EVENT_PATH/REPOSITORY reads outside checkout-console and the accessor. It allowlists `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}` (wrapper run URLs) and `github.ref_name` in `concurrency.group` (Design 3).
- **Status.**
  - The `console-context` job creates the App check-run `CI Complete` (in_progress) on `CONSOLE_SHA`, so ci-watch and the sweeper see the run at once. A user-token ping cannot do this, because only Apps create check-runs.
  - The jobs that are `CI Complete` and `Review Complete` today end with a step that PATCHes or POSTs the check-run through the App, with a `details_url` pointing at the wrapper run. This needs the App permission `checks: write` (an operator grant, A2) and a new app-token preset `checks` (checks:write only, console only).
  - ci-watch, pr-merge and detect_pointer_bump read check-runs filtered to the App's id (2772000), so a check-run from any other actor never counts.
- **Sweeper (`wrapper-sweep.yml` on wrapper main, `*/5`).** It uses a new app-token preset `wrapper-sync`: contents:write and workflows:write on rediacc/rediacc, contents/pull-requests/checks read on console. An App-token push starts workflows; a GITHUB_TOKEN push would not. `sweep.py`:
  - for console main's head and every open PR head that is older than 3 minutes, has no App `CI Complete` check-run, and is not the sha in the wrapper target's `CONSOLE_CONTEXT.json`, runs the same render-and-push as ping.py (shared code, run from a scratch bare repo in the runner);
  - for reviews and review comments on open PRs updated since the last sweep (`since` in a cache entry), pushes to `review/pr-<N>` with `event: review`;
  - runs the orphan closer: an in_progress App check-run older than the CI timeout is closed `failure` with "orphaned run" as its summary. For a closed PR it calls the cleanup workflows (preview and R2 staging) through `workflow_call` with the PR number, then deletes `run/pr-<N>` and `review/pr-<N>`.

  GitHub may delay or drop scheduled runs under load, and schedules run from the default branch only. Wrapper main gets a push on every console main push, so the public repo never reaches 60 idle days and the schedule is never auto-disabled.
- **Removed from the earlier draft:** `workers/ci-bridge`, the console webhook, the repository_dispatch hop, router.yml's render-and-dispatch, and the `workflow_dispatch` `console_*` inputs.

### 3. Concurrency

Every group keys on a ref that maps one-to-one to a console ref:
- `ci-${{ github.ref_name }}`. On the wrapper that is `main`, `run/pr-<N>` or `review/pr-<N>`, a one-to-one image of console main and PR N. On native console (shadow, rollback) it is `main` or `<N>/merge`, also unique per PR;
- stage, release and deploy groups keep their current version or channel keys (.github/workflows/ci.yml:1203-1205 is already ref-free).

the new `ci-console-context` gate (npm script `check:` prefix added when written) refuses a `concurrency.group` that reads `github.ref` (full), `github.head_ref` or `github.event.pull_request`, which are empty or wrong on a wrapper push.

### 4. Merge gate, rulesets and environments on Free

- **Console after the flip.** Rulesets and protection are not enforced on Free private repos, and auto-merge needs them. Both rulesets become inert; delete them (clean break) once A1 confirms it.
- **The merge path becomes:**
  1. the pr-merge skill waits with ci-watch on the App's `CI Complete` = success and `Review Complete` = success on the head sha;
  2. it then runs `merge_gate.py`, which runs `gh pr merge <N> --rebase --match-head-commit <sha>`. `--match-head-commit` closes the race with a later push;
  3. merge_gate then pings `--ref main` with the merged sha (Design 2).
- **Guard.** A pre-bash guard `block_unverified_console_merge` refuses any `gh pr merge` against rediacc/console, and any `--auto`, unless the command came from the merge verb `.ci/rediacc_ci/wrapper/merge_gate.py`. That verb re-reads both check-runs (filtered by App id), the strict "branch up to date with main" condition (compare API) and rebase-only, and refuses otherwise.
  - Honest limit: this binds agents only. With one seat, the operator is the only other actor.
- **`block_*` guards and `wl_prreview`** that read the `CI Complete` check today switch to the App-filtered reader. ci-trace and ci-watch look up runs in rediacc/rediacc on `run/pr-<N>` and `main`.
- **Environments.** The blocks at .github/workflows/cd-release-edge.yml:321, .github/workflows/cd-deploy-worker.yml:46 and .github/workflows/cd-deploy-account.yml:257 stay. The environments are created in the public wrapper, where Free allows them; they protect the wrapper's runs.
  - Housekeeping's deployment-record and environment phases target WK_GH_CI_REPO.
  - The attest-build-provenance steps (.github/workflows/cd-stage.yml:412, :420) now sign as `rediacc/rediacc/.github/workflows/cd-stage.yml`, so verify_artifact_attestation.py expects that signer identity.
- **ghcr.** server and rdc stay public; renet and devcontainer stay internal (ruling). The wrapper's GITHUB_TOKEN must be granted write under each package's "Manage Actions access" (A3), or pushes from the wrapper are refused.

### 5. Release path without GitHub Releases

- **`release_notes.py`** (new) renders `RELEASE_NOTES.md` from conventional commits between the previous `v*` tag and `v<V>`. Sections are feat, fix, perf, and other with breaking changes first. Trailers and PR-TASK lines are stripped and no internal paths appear. The notes are uploaded to `cli/v<V>/RELEASE_NOTES.md`.
- **SHA256SUMS.** `SHA256SUMS` and `SHA256SUMS.asc` go to `cli/v<V>/`, uploaded by the step that made them (local.py provenance, CD stage).
- **Manifest.** .ci/rediacc_ci/build/generate_cli_manifest.py:325 sets `releaseNotesUrl = ${RELEASES_BASE_URL}/cli/v<V>/RELEASE_NOTES.md`. Each `binaries.<platform>` gains `size` (bytes), which the downloads page needs.
- **Downloads page.** downloads.astro and latest-release.ts read `${WK_RELEASES_ORIGIN}/cli/stable/manifest.json` once per build, still throwing on null in production. release-parser.ts becomes `parseManifest`. `GITHUB_REPO` leaves packages/www/src/config/constants.ts.
- **Pipeline reads move to R2:**
  - .github/workflows/cd-release-edge.yml:681-692 owed-decision, .ci/rediacc_ci/release/check_existing_release.py:54 and .ci/rediacc_ci/release/assert_edge_tag_exists.py:158-161 read `release-records/v<V>/edge.json` and `cli/v<V>/.released`. A 404 is "absent"; any other failure is UNKNOWN and refused, as today.
  - verify_release_assets.py checks the R2 objects (binaries, SHA256SUMS, .asc, RELEASE_NOTES.md) against the manifest.
  - mark_production.py keeps the moving `production` tag and drops the `gh release edit --latest` leg.
  - create_github_release.py is deleted, along with .github/workflows/cd-release-edge.yml:795 and the Release leg in local.py.
  - cleanup_versions.py drops Phase 1 (release delete) and keeps tag retention.

### 6. Cutover order (rollback = make console public again; every step before C4 is invisible to customers)

1. Waves 1-3 land in console while it is still public, and native console CI stays the gate. The new hooks reach every checkout through the existing `git-hooks-path` setup phase.
2. The wrapper is created, secrets and environments are registered, the App is granted checks:write and installed on the wrapper, and the first `ping.py --ref main` seeds wrapper main. From then on every console push pings automatically, with no webhook and no manual step.
3. A shadow week: both run. Console's native CI is still required, and the wrapper posts its check-runs under the shadow names `CI Complete (wrapper)` and `Review Complete (wrapper)`.
4. Proof: a PR that edits a workflow goes green through `run/pr-<N>` with its own YAML; a main push releases edge through the wrapper (stage, deploy and the R2 release notes); and with the ping worker killed for one push, the sweeper re-pushes within 10 minutes.
5. The shadow suffix is dropped, console Actions are disabled and the console rulesets are deleted.
6. The flip: `gh repo edit rediacc/console --visibility private --accept-visibility-change-consequences`.
7. Verification:
   - anonymous ghcr pull of server and rdc;
   - install.sh, install.ps1, brew, apt, rpm, apk and pacman from R2;
   - the downloads page and `rdc update` notes URL;
   - anonymous 404 on github.com/rediacc/console;
   - the external-link gate;
   - one full PR-to-merge-to-edge loop.

Rollback after the flip is `--visibility public` plus re-enabling console Actions. Console's YAML keeps its native triggers (only the wrapper copy is rewritten), and checkout-console has a native mode, so native CI resumes as it was. The wrapper can keep running alongside.

### 7. Repo hygiene

- README.md stays an internal README (the clone URL works for members). CONTRIBUTING.md loses the external-contributor section.
- .github/ISSUE_TEMPLATE/config.yml drops the discussions link and points to the www support page (Q4). Discussions are switched off.
- Docs:
  - experimental-vms (13 locales): drop the issue link and keep "planned";
  - rules-of-rediacc:125 (13 locales): link the heartbeat template's docs page or inline it;
  - siem-integration: inline the collector config and event-schema excerpt (Q5) and drop `git clone`.
- The homebrew-tap README links https://www.rediacc.com/docs.
- check-external-links gains a refusal: no `github.com/rediacc/console` or `raw.githubusercontent.com/rediacc/console` link in packages/www content, packages/www/public or the tap. Its WK_GH_REPO selftest stays generic.

### 8. Exposure trims (cheap ones only; the logs leak is accepted)

- .github/workflows/ops-local-release-assist.yml:153-160 stops uploading `private/bin/`. Consumers fetch from the R2 staging prefix that local.py already stages.
- the new `ci-artifact-allowlist` gate (npm script `check:` prefix added when written) lists every upload-artifact name with a class (report, json, log). It refuses `private/**`, `dist/**` binaries and `*.go` or `*.ts` source paths.
- `git diff` on failure becomes `git diff --stat`.
- renet `go test -v` becomes non-verbose with `-json` reduced to failures in CI.
- Artifact retention stays 1-3 days.

## Boxes

### Wave 0: decisions and GitHub-side setup

- [ ] A0 [lead] Put Q1-Q6 to the operator and record the answers in this plan's Rulings (done in this revision; the lead ticks it on the accept). Accept: `grep -c 'ASKED:2026-11-17T08:46Z' agent/plans/PLAN-console-private.md` prints at least 2, and `grep -c 'ANSWERED' agent/plans/PLAN-console-private.md` prints at least 7
- [ ] A2 [live] The operator grants the App the `checks: write` permission and accepts it on the org installation. Accept: `gh api /orgs/rediacc/installations --jq '.installations[] | select(.app_id==2772000) | .permissions.checks'` prints `write`
  GitHub-only: CI parity -- App permissions are set in GitHub's App settings UI; no local path changes them
- [ ] A3 [live] Create rediacc/rediacc (public, Issues off, Wiki off, Discussions off). Register BWS_ACCESS_TOKEN and ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN. Create the environments named in the three workflows. Install the App on it with contents and workflows write. Grant the wrapper write Actions access on ghcr server, rdc, renet and devcontainer. Accept: `gh api repos/rediacc/rediacc --jq .visibility` prints `public`, and `gh secret list -R rediacc/rediacc | wc -l` prints 2, and `gh api repos/rediacc/rediacc/environments --jq '.total_count'` is at least 3, and `gh api repos/rediacc/rediacc/installation --jq '.permissions.workflows'` prints `write`
  GitHub-only: CI parity -- repository creation, secrets, App installation and package Actions access exist only on GitHub

### Wave 1: wrapper, shim, trigger and status code (writers, file-disjoint)

- [ ] W1 [writer] `.ci/rediacc_ci/wrapper/render.py` plus `.ci/config/wrapper.json`: per-workflow push branch filters, `paths` moved into wrapper.json, `--from-object <sha>` reading the console object database, and the `CONSOLE_CONTEXT.json` writer. Tests: every event trigger becomes `on: push: branches` drawn from `[main, 'run/**', 'review/**']`; `paths:` is absent from the rendered trigger and present in wrapper.json; schedule, workflow_run and workflow_call pass through; the cleanup workflows have no event trigger; rendering is byte-stable; a control fixture with a `pull_request` trigger left in fails. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_wrapper_render.py` rc 0
- [ ] W2 [writer] `.github/actions/checkout-console` composite (wrapper mode reads `CONSOLE_CONTEXT.json` from `github.sha` or the workflow_run head_sha; native mode derives the same values from the event), the `console-context` job pattern, and the app-token presets `checks` and `wrapper-sync`. Tests: the action exports every CONSOLE_* name in both modes; `checks` grants checks:write only; `wrapper-sync` grants contents and workflows write on rediacc/rediacc only. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_wrapper_checkout_action.py` rc 0, and `npm run -s check:ci-workflow-env-provision` rc 0
- [ ] W3 [writer] `rediacc_ci.core.console_ctx` (env, then git-derived locally, no GITHUB_* fallback) and `WK_GH_CI_REPO` in well-known.env. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_console_ctx.py` rc 0, and `npm run -s check:ci-env-manifest` rc 0
- [ ] W4 [writer] `.github/workflows/wrapper-sweep.yml` (`*/5`, guarded to rediacc/rediacc) driven by `.ci/rediacc_ci/wrapper/sweep.py` with a recording gh transport: the missing-check-run re-push, the review/comment re-push, and the orphan closer with cleanup workflow_call and wrapper branch deletion. Tests: a head with an App `CI Complete` is skipped; a head younger than 3 minutes is skipped; a head already named in the wrapper context is skipped; a missing head is re-pushed once; a new review pushes `review/pr-<N>`; an orphan older than the timeout is closed failure; a closed PR calls both cleanups and deletes its branches; a check-run by another app id is ignored (control).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_wrapper_sweep.py` rc 0
- [ ] W5 [writer] `.ci/rediacc_ci/wrapper/ping.py` (Design 2): lock with the 120 s wait, the open-PR check (main exempt), state and wrapper-context dedupe, render from the object database, `commit-tree` whose parent is the wrapper tip only, scratch bare repo `<git-dir>/rediacc-wrapper/repo.git` with no hooksPath, push without force with up to 3 race retries, the log, and `--ref/--sha/--event/--review-id`.
  Tests against a local bare "wrapper" and "console" fixture: the pushed commit's ancestry contains no console commit (control: a fixture that passes a console parent is refused); no argv carries `--force`, `-f` or `+`; a no-PR branch pushes nothing while main does; a repeated sha pushes nothing; a lost race is rebuilt on the new tip; a busy lock exits 0 with `lock busy` logged; the scratch repo has no `core.hooksPath`; `CONSOLE_CONTEXT.json` has exactly `sha, ref, pr, base_sha, event` (plus `review_id` on reviews). Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_wrapper_ping.py` rc 0
- [ ] W6 [writer] `.ci/rediacc_ci/wrapper/check_runs.py` (create the in_progress `CI Complete` from the `console-context` job; create or update `CI Complete` and `Review Complete` on CONSOLE_SHA at the end; App-filtered read) wired into ci.yml and the Review Complete job. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_wrapper_check_runs.py` rc 0
- [ ] W7 [writer] Git hooks in `.claude/rediacc_hooks/git/githooks.py`: route `reference-transaction committed` before the `COMMIT_POLICY_OK` check; `spawn_wrapper_ping` with the `WRAPPER_PING_WORKER` seam (console origin only, not in a lease tree, `refs/remotes/origin/*` non-delete lines only); the pinned `WRAPPER_URL` refusal in `pre-push` for console and submodules. `.ci/rediacc_ci/setup/githooks.py` keeps `reference-transaction` in HOOK_NAMES (:24) and gains a test that pins it.
  Tests: a real push to a fixture origin starts the sleeper seam exactly once with the pushed sha; it starts with `COMMIT_POLICY_OK=1` set; a `prepared` state, a delete, a non-origin ref, a submodule and a lease tree start nothing; a push to the wrapper URL (https and ssh) from console and from a submodule is refused; a push to origin is admitted (control). Accept: `python3 .claude/rediacc_hooks/run_tests.py -k "githook_wrapper"` rc 0
- [ ] W8 [writer] `block_wrapper_direct_push` guard; `arm_ci_watch.py` pings after `gh pr create` and `gh pr ready` and re-pings once when no wrapper run appears in 3 minutes; `wl_prreview.py --answer` pings `--event review`. Tests: `git push https://github.com/rediacc/rediacc.git HEAD:main`, `git push wrapper` (a remote with the wrapper URL) and `git remote add w git@github.com:rediacc/rediacc.git` are refused; `git push origin HEAD` is admitted (control); `gh pr create` calls the ping seam with the branch; a watcher seeing no run after the window calls it once more and not a third time. Accept: `python3 .claude/rediacc_hooks/run_tests.py -k "wrapper_direct_push or arm_ci_watch_ping or prreview"` rc 0

### Wave 2: the sweep (after W2 and W3)

- [ ] S1 [writer] The gate the new `ci-console-context` gate (npm script `check:` prefix added when written) (Design 2 and 3 rules, with a control fixture per rule, including `github.ref_name` admitted in a concurrency group and `github.head_ref` refused). Accept: `npm run -s check:ci-console-context -- --selftest` rc 0
- [ ] S2 [writer] Sweep .github: every `actions/checkout` of console becomes `checkout-console`; each entry workflow gains the `console-context` job; `github.sha|ref|head_ref|event_name|event.pull_request` become `needs.console-context.outputs.*` (job `if:`), `env.CONSOLE_*` (steps) or workflow_call inputs (children); `paths`-filtered workflows gate on `paths_match`; concurrency groups move to `github.ref_name`. Accept: `npm run -s check:ci-console-context` rc 0, and `npm run -s check:ci-actionlint` rc 0, and `npm run -s check:ci-workflows` rc 0
- [ ] S3 [writer] Sweep the 44 `.ci` modules onto `console_ctx`. Run, artifact and workflow calls move to `WK_GH_CI_REPO`. The release-publish steps that push to console main call `ping.py --ref main`. Accept: `npm run -s check:ci-console-context` rc 0, `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests` rc 0, and `grep -rnE 'GITHUB_(SHA|REF|HEAD_REF|REPOSITORY|EVENT_PATH)' .ci --include=*.py --exclude-dir=cache --exclude-dir=tests | grep -v console_ctx.py | wc -l` prints 0
- [ ] S4 [writer] ci-watch, the run-trace tool (runs on rediacc/rediacc `run/pr-<N>`), the pr-merge skill and the merge guard (Design 4): `merge_gate.py` (which pings `--ref main` once merged) and `block_unverified_console_merge`. Tests: `gh pr merge --auto` is refused; a red or absent App check-run refuses; another app's green check-run refuses (control); a matching head merges with `--match-head-commit` and calls the ping seam with the merged sha. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_wrapper_merge_gate.py` rc 0, and `python3 .claude/rediacc_hooks/run_tests.py -k "unverified_console_merge"` rc 0
- [ ] S5 [writer] verify_artifact_attestation.py expects the signer `rediacc/rediacc/.github/workflows/cd-stage.yml`. Housekeeping's deployment, environment, run, artifact and cache phases target `WK_GH_CI_REPO`. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests -k "attestation or cleanup_versions"` rc 0

### Wave 3: release path, hygiene and trims (parallel with Wave 2)

- [ ] R1 [writer] `release_notes.py` (Design 5) plus its upload to `cli/v<V>/RELEASE_NOTES.md`. Tests: sections and order, breaking changes first, trailers stripped, no `private/` paths. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_release_notes.py` rc 0
- [ ] R2 [writer] generate_cli_manifest.py writes `releaseNotesUrl` on R2 and `size` per binary; SHA256SUMS and .asc are uploaded to `cli/v<V>/`. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests -k "manifest or local_release"` rc 0, and `grep -c 'releases/tag' .ci/rediacc_ci/build/generate_cli_manifest.py` prints 0
- [ ] R3 [writer] Pipeline reads move to release-records and the R2 sentinel (Design 5): check_existing_release, assert_edge_tag_exists, verify_release_assets, the cd-release-edge owed step and mark_production. Delete create_github_release.py and its callers, and Phase 1 of cleanup_versions. Accept: `grep -rn 'gh.*release \(view\|create\|edit\|delete\|list\)\|create_github_release' .ci .github --exclude-dir=cache | wc -l` prints 0, and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests` rc 0
- [ ] R4 [writer] Downloads page reads the R2 manifest (Design 5) and `GITHUB_REPO` leaves www. Accept: `cd packages/www && npx vitest run src/utils` rc 0, `npm run -s build -w packages/www` rc 0 with GITHUB_TOKEN unset, and `grep -rn 'GITHUB_REPO\|browser_download_url' packages/www/src | wc -l` prints 0
- [ ] H1 [writer] Docs links (13 locales x 2 pages plus siem-integration, per Q5) and the check-external-links refusal rule with a control fixture. Accept: `npx tsx scripts/gates/check-external-links.ts --selftest` rc 0, and `grep -rln 'github.com/rediacc/console' packages/www/src packages/www/public | wc -l` prints 0
- [ ] H2 [writer] README.md, CONTRIBUTING.md, ISSUE_TEMPLATE config (Q4) and the homebrew-tap README (tap PR first, then the gitlink bump). Accept: `grep -rn 'github.com/rediacc/console' CONTRIBUTING.md .github/ISSUE_TEMPLATE private/homebrew-tap/README.md | wc -l` prints 0
- [ ] X1 [writer] Exposure trims (Design 8) and the new `ci-artifact-allowlist` gate (npm script `check:` prefix added when written). Accept: `npm run -s check:ci-artifact-allowlist` rc 0, and `grep -n 'private/bin/' .github/workflows/ops-local-release-assist.yml | grep -c upload` prints 0
- [ ] D1 [writer] docs/agent-reference/ci-wrapper.md covers the topology, the hook trigger and ping worker, the leak guards, the shim names, the sweeper, the merge path and rollback; CLAUDE.md and the ci-watch skill point at it. Accept: `npm run -s check:ci-doc-region-parity` rc 0

### Wave 4: shadow, proof and cutover (serial, live)

- [ ] C1 [live] Seed wrapper main with `PYTHONPATH=.ci python3 -m rediacc_ci.wrapper.ping --ref main`, then push the plan branch with an open PR through the normal hook path. Shadow check-run names carry the `(wrapper)` suffix.
  Accept: `gh api repos/rediacc/rediacc/contents/CONSOLE_CONTEXT.json --jq .content | base64 -d | jq -r .sha` equals `git rev-parse origin/main` at seed time; `grep -c "$(git rev-parse HEAD)" "$(git rev-parse --absolute-git-dir)/rediacc-wrapper/log"` is at least 1 after the branch push; `git -C "$(git rev-parse --absolute-git-dir)/rediacc-wrapper/repo.git" config core.hooksPath` prints nothing; and `gh api repos/rediacc/console/commits/$(git rev-parse HEAD)/check-runs --jq '.check_runs[] | select(.app.id==2772000) | .name'` lists `CI Complete (wrapper)`
  GitHub-only: CI parity -- the proof is that a hook-driven wrapper push starts a GitHub Actions run, which no local runner reproduces
- [ ] C2 [live] A PR that edits a workflow goes green through `run/pr-<N>` with its own YAML. Then, with the ping worker killed for one push (hold its lock with `flock -n "$(git rev-parse --absolute-git-dir)/rediacc-wrapper/lock" sleep 600 &` before pushing, so the worker logs `lock busy` and exits), the sweeper re-pushes within 10 minutes.
  Accept: `python3 .ci/scripts/ci/ci-trace.py --repo rediacc/rediacc --pr <N>` reports CI Complete success; `grep 'lock busy' "$(git rev-parse --absolute-git-dir)/rediacc-wrapper/log"` names the held sha S; within 10 minutes of the push `gh api repos/rediacc/console/commits/S/check-runs --jq '[.check_runs[] | select(.app.id==2772000 and (.name|startswith("CI Complete")))] | length'` is at least 1; and the latest `wrapper-sweep.yml` run log (`gh run view -R rediacc/rediacc --log $(gh run list -R rediacc/rediacc --workflow wrapper-sweep.yml --limit 1 --json databaseId --jq '.[0].databaseId')`) names S
  (corrected 2026-11-17) GitHub-only: CI parity -- the wrapper run and the scheduled sweeper exist only on GitHub Actions
- [ ] C3 [live] A main push releases edge through the wrapper: stage, attestation, deploy and R2 notes. Accept: `curl -fsS https://releases.rediacc.com/cli/edge/manifest.json | jq -r .releaseNotesUrl` prints an R2 URL that answers 200, `curl -fsSI https://releases.rediacc.com/cli/v<V>/SHA256SUMS.asc` gives 200, and `gh release view v<V> -R rediacc/console` answers not found
  GitHub-only: CD -- only the release pipeline in the wrapper publishes edge
- [ ] C4 [live] Cutover: drop the shadow suffix (re-render and ping main), disable console Actions, delete rulesets 12344707 and 24351140, turn off Discussions, then `gh repo edit rediacc/console --visibility private --accept-visibility-change-consequences`. Accept: `gh api repos/rediacc/console --jq .visibility` prints `private`, and `curl -s -o /dev/null -w '%{http_code}' https://github.com/rediacc/console` prints 404, and `gh api repos/rediacc/console/actions/permissions --jq .enabled` prints `false`
  GitHub-only: CI parity -- visibility, Actions enablement and rulesets are GitHub settings
- [ ] A1 [live] Confirm the Free facts on the private repo: rulesets and auto-merge are refused. Accept: `gh api repos/rediacc/console/rulesets -X POST --input .ci/config/wrapper-probe-ruleset.json` answers 403 or "Upgrade", and `gh pr merge <N> --auto` answers refused; both are recorded here
  GitHub-only: CI parity -- only GitHub's plan enforcement can prove it
- [ ] C5 [live] Post-flip customer paths. Accept: `docker logout ghcr.io; docker pull ghcr.io/rediacc/server:latest && docker pull ghcr.io/rediacc/rdc:latest` rc 0; `curl -fsSL https://www.rediacc.com/install.sh | bash -s -- --dry-run` rc 0; the most recent `ct-install-methods.yml` run in the wrapper, started after the flip, reports success (`gh run list -R rediacc/rediacc --workflow ct-install-methods.yml --limit 1 --json conclusion --jq '.[0].conclusion'` prints `success`), which covers brew, apt, rpm, apk and pacman; `npx tsx scripts/gates/check-external-links.ts` rc 0
  Local-route: www-local, bench-cli -- the docker, install.sh and link probes are anonymous HTTP from this machine; the package-manager matrix is read from the wrapper run
- [ ] C6 [live] One full loop after the flip: a PR goes green in the wrapper, merges through the merge gate (which pings main), and edge releases. Accept: the `merge_gate.py` log shows both App check-runs success on the merged sha and a ping of `main`, and `curl -fsS https://releases.rediacc.com/cli/edge/manifest.json | jq -r .commit` equals the merged sha
  GitHub-only: CD -- the edge release runs only in the wrapper pipeline
- [ ] LP-bench [live] Fresh bench receipt for the downloads page reading the R2 manifest (R4) deployed to bench.
  Accept: live-proof bench www-smoke

## Risks

1. **The merge gate is not enforced by GitHub after the flip** (Free, private). It is enforced by local guards and the merge verb only (ruling 08:46Z). It binds agents; the operator is the only other actor.
2. **Public wrapper logs and artifacts stay readable by signed-in users** (accepted ruling). Test names, lint lines and step output can name private code. Wave 3 X1 trims only the cheap leaks.
3. **Private history reaching the public wrapper.** Three layers guard against it. ping.py builds commits with `commit-tree` from the rendered tree only, with the wrapper tip as the only parent and a fixed bot identity (W5 control test). `pre-push` refuses any push to the pinned WRAPPER_URL from console or a submodule. `block_wrapper_direct_push` refuses an agent's push or remote-add. Two-remote origin push URLs are ruled out.
4. **The App's write tokens now run console PR code in a public repo's runner.** Console is private and single-seat, so no fork PR exists. The wrapper has no pull_request trigger; its push triggers fire only on pushes by the operator's token or the App, so a fork of the wrapper cannot start anything in it. Keep presets narrow: `checks` and `wrapper-sync` are presets of their own.
5. **ghcr packages set to inherit access from console could turn private at the flip.** C5's anonymous pull catches it. The fix is a package visibility setting, not a rollback.
6. **A lost ping** (a crashed worker, a busy lock, a missing credential, a laptop that went offline mid-push) is covered by the sweeper within one to two 5-minute periods. GitHub may delay or drop scheduled runs under load. arm_ci_watch's one re-ping after 3 minutes covers agent sessions faster. C2 proves the sweeper path live.
7. **Pushes the hook cannot see.** These are operator machines without the hooks installed, commits made in the GitHub UI or API, merges, and CD pushes to main. merge_gate and CD ping explicitly, and the sweeper covers every other case.
8. **A `git fetch` fires the same `committed` state.** The state-file and wrapper-context dedupe make it a no-op for a sha already in the wrapper. Otherwise it is a legitimate catch-up ping.
9. **Wrapper path filters cannot see console paths.** The renderer moves them into the `console-context` job (Design 1). A missed workflow would run on every push instead of skipping: wasteful, but not unsafe.
10. **Scheduled-workflow auto-disable after 60 idle days** would stop the sweeper. Wrapper main gets a push on every console main push, so this needs 60 days without a console merge.
11. **Attestation identity changes to rediacc/rediacc.** Any external verifier pinned to rediacc/console must be updated (S5).
