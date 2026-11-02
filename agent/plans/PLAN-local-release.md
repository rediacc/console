# PLAN: publish a release from the local machine (`npm run release:local -- --channel edge|stable [--dry-run]`)

Status: approved -- operator ruling ASKED:2026-10-27T06:37Z, promoted in the commit that adds this file
Depends-On: no-dep -- W1 starts now; L1 waits for the 1023-1 merge so HEAD equals origin/main, which is not a plan
Priority: P1 -- operator ruling; the R1 clean break needs a released CLI that sends x-config-envelope before the account Worker reaches eu stable
Concurrency: parallel -- inside the waves under Order; Owns per box are disjoint within a wave, and W3 lands as one clean break
Owns: .ci/rediacc_ci/release/local.py, .ci/rediacc_ci/release/local_gates.py, .ci/rediacc_ci/release/order.py, .ci/rediacc_ci/release/renet_key_gate.py, .ci/rediacc_ci/release/tag.py, .ci/config/release-requires.json, .ci/config/secret-supply.json (the release-local profile), .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/build/extract_renet_from_image.py, .ci/rediacc_ci/deploy/deploy_record.py, .ci/rediacc_ci/deploy/deploy_www.py, .ci/rediacc_ci/deploy/deploy_edge.py, .ci/rediacc_ci/release/check_soak_period.py, .ci/rediacc_ci/release/advance_contract_floor.py, .ci/rediacc_ci/release/update_homebrew_tap.py, .ci/rediacc_ci/security/ci_workflow_invariants.py, .ci/rediacc_ci/tests/test_release_*.py, .ci/rediacc_ci/tests/test_drills_vm_check.py, .ci/rediacc_ci/tests/test_deploy_*.py, .ci/rediacc_ci/tests/test_security_ci_workflow_invariants.py, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, .claude/rediacc_hooks/guards/block_unasked_release.py, .claude/rediacc_hooks/guards/test-block_unasked_release.py, .claude/rediacc_hooks/guards/block_git_hook_bypass.py, .claude/rediacc_hooks/guards/test-block_git_hook_bypass.py, .claude/rediacc_hooks/guards/block_host_toolchain_run.py, .claude/rediacc_hooks/git/githooks.py, .claude/rediacc_hooks/tests/test_githook_release_run.py, .github/workflows/cd-v2.yml, .github/workflows/promote-stable.yml, .github/workflows/cd-deploy-account.yml, .github/workflows/cd-deploy-worker.yml, .github/workflows/backfill-release-sentinel.yml, .github/workflows/local-release-assist.yml, .github/workflows/ci.yml, .github/workflows/cd-stage.yml, .github/workflows/ci-build-docker.yml, package.json (one script), CLAUDE.md, docs/agent-reference/release-process.md, docs/agent-reference/ci-gates.md, docs/agent-reference/versioning.md, .claude/skills/deploy/SKILL.md, .claude/commands/pr-merge.md, scripts/data/doc-registry.md
Owner: d778be9d
First-Seen: 2026-10-27
Worklist: #d67d4f15

**Operator ruling, 2026-10-27T06:37Z:** "with no customers yet, a release may be published from the local machine instead of CI/CD, provided local verification is green." One entry publishes what CD publishes today: the Docker images, the git tag, the GitHub Release, the R2 artifacts, Homebrew, and the account, www and proxy Worker deploys. Clean break: CD's publish path is deleted, not kept as a second path.

Design inputs, summarized below with file:line:
- agent/d778be9d/local-release-memo-a.md: the reuse map and timings (Plan agent a8259d47).
- The gates memo (Plan agent a8ca09ca).

## Tasks

### Wave 1 (disjoint, start now)

- [x] W1-A [writer] Receipt API.
  - Factor the verdict at `.claude/rediacc_hooks/guards/block_unverified_push.py:1678-1749` into a pure `receipt_refusal(root, tree, receipt) -> str | None`.
  - Drop the environment fail-opens: a missing `jq` allows at :1675, and a failed fetch allows at :850-855. Drop the event object too. `run()` calls the new function.
  - The reader tries the per-tree copy `.ci/cache/receipts/<headTree>.json` (`scripts/ci-runner/run.ts:3246-3250`) before the latest file.
  - Owns: block_unverified_push.py and test-block_unverified_push.py.
  - Accept: `python3 .claude/rediacc_hooks/run_tests.py -k unverified_push` rc=0 with the goldens unchanged, and `receipt_refusal` is None only on the push-green fixture.
    (ticked) 2026-10-27T09:31:13Z by d778be9d: 4301ac96b, c8acbfb78, 06291f19d: receipt_refusal and read_receipt in .claude/rediacc_hooks/guards/block_unverified_push.py; run_tests.py -k unverified_push rc=0 (1515, goldens unchanged)
- [x] W1-B [writer] `vm:check --base <ref>`.
  - On `main`, `--changed` diffs against origin/main, which is HEAD, so it checks nothing and writes no receipt (`.ci/rediacc_ci/drills/vm_check.py:28`, the `--changed` trigger module (`vm_check_trigger.py`, lines 275-310 of the release-cache copy)).
  - Add `--base`, recorded in the receipt as `trigger.base`.
  - Owns: vm_check.py and test_drills_vm_check.py.
  - Accept: the pytest rc=0, and a receipt written with `--base v2.4.0` names the ref.
    (ticked) 2026-10-27T07:39:43Z by d778be9d: 7ce8f5ce9: vm_check.py --changed --base <ref>, trigger.base in the receipt; pytest test_drills_vm_check.py rc=0 (252) with the main plus --base v2.4.0 case
- [x] W1-C [writer] Order declaration.
  - Add `.ci/config/release-requires.json`. Its first entry is R1-config-envelope: since account aaf3c251, with cli_commits 9d0172906 and 09d646273.
  - Add `rediacc_ci.release.order.account_refusal(channel, account_pointer)`:
    - An entry is active when `since` is an ancestor of the account pointer.
    - The channel's published CLI counts only when its R2 manifest version V has both the sentinel `cli/v<V>/.released` and the tag `v<V>`.
    - Every `cli_commits` entry must be an ancestor of `v<V>`. Otherwise the answer is `cli-behind`.
  - Correct `ENVELOPE_MIN_RDC` at `private/account/src/routes/configs.ts:145`. It names the version that writes v3, not the first one that sends the header. Set it from the release that ships the header.
  - Owns: release-requires.json, order.py and test_release_order.py.
  - Accept: the pytest rc=0, and R1 is active for the current account pointer and reports `cli-behind` against v2.4.0.
    (ticked) 2026-10-27T07:53:15Z by d778be9d: afd379a39: .ci/config/release-requires.json R1-config-envelope and rediacc_ci.release.order; pytest test_release_order.py rc=0 (14); live edge read rc=1 "cli-behind: R1-config-envelope needs 9d0172906, 09d646273 in a released CLI on edge; published v2.4.0 lacks them"
- [x] W1-D [writer] Release-run admission at the git layer.
  - The entry writes `.ci/cache/release/run-<id>.json` holding `{pid, pid_start, cmdline, tree, version, channel, pushes:[{toplevel, remote_ref, oid}]}` and exports `REDIACC_RELEASE_RUN`.
  - The `githooks.py` pre_push (:318-329) admits a pushed line only when all three hold:
    - the record's pid is in the hook's parent chain, with a matching `/proc` start time and a cmdline of `-m rediacc_ci.release.local`;
    - the record's tree equals the console `HEAD^{tree}`;
    - that exact `(toplevel, remote_ref, oid)` is listed.
  - `.claude/rediacc_hooks/guards/block_git_hook_bypass.py:11` refuses `REDIACC_RELEASE_RUN` set by an agent, as it already refuses `COMMIT_POLICY_OK`.
  - Owns: githooks.py, test_githook_release_run.py, block_git_hook_bypass.py and test-block_git_hook_bypass.py.
  - Accept: `run_tests.py -k "githook_release_run or git_hook_bypass"` rc=0, and a forged record, a wrong tree or an unlisted ref is refused.
    (ticked) 2026-10-27T08:03:42Z by d778be9d: 1f82c3695: .claude/rediacc_hooks/git/release_run.py and githooks.py pre_push admission plus block_git_hook_bypass; run_tests.py -k "githook_release_run or git_hook_bypass" rc=0 (23), with planted failures turning each check red
- [x] W1-E [writer] Renet key gate.
  - Today no release step refuses a renet built without the production key:
    - `private/renet/build.sh:414-444` falls back to the DEV key with only a warning.
    - The cached path, `.ci/rediacc_ci/build/extract_renet_from_image.py:478-486`, cross-builds darwin and windows renet with no key and no version.
  - Add `rediacc_ci.release.renet_key_gate`. It reuses the `go version -m` reader from `testrun/start_backup_plane.py --verify-renet` on every renet binary and every image, and refuses:
    - an empty key;
    - the DEV fingerprint;
    - `tags=nolicense`.
  - Remove the keyless cross-build from the cached path.
  - Owns: renet_key_gate.py with its test, and extract_renet_from_image.py.
  - Accept: the pytest rc=0, with fixtures for an empty key, the DEV key and the production key.
    (ticked) 2026-10-27T08:24:23Z by d778be9d: e53949495: .ci/rediacc_ci/release/renet_key_gate.py plus the keyed cached cross build and ci-build-renet.yml; pytest rc=0 (81); live run refused all 9 local binaries as DEV key

### Wave 2 (after W1)

- [x] W2-A [writer] Gates module, `rediacc_ci.release.local_gates`.
  - It imports W1-A's `receipt_refusal` (the way `.ci/rediacc_ci/ci/gate_model.py:113-117` imports the guard) and `vm_check_receipt.admit` (the receipt module's `admit` (`vm_check_receipt.py`, lines 374-388 of the release-cache copy)).
  - It refuses unless all of these hold:
    - a whole, green ci:quick receipt exists for HEAD's tree;
    - the vm:check hits since the channel's previous release tag are admitted by a VERIFIED receipt;
    - the backup receipt exists, when backup paths moved;
    - a fresh clone of HEAD with submodules, at `.ci/cache/release/<tree>/`, is clean, with every submodule at its pointer and unmodified (decision 1);
    - a fresh fetch succeeded (fail closed on a failed fetch), and HEAD equals origin/main;
    - the release lock is free: the R2 sentinel is absent and `check_existing_release` agrees.
  - For stable, factor a pure `select()` out of `check_soak_period.main` (:101). It needs the tag, the sentinel and an edge record `release-records/v<V>/edge.json` with smoke rc 0, aged at least SOAK_DAYS. `--force` skips the age only with a proven ASKED minute.
  - Owns: local_gates.py, check_soak_period.py and test_release_*.py for both.
  - Accept: pytest rc=0 over every case in the Tests section.
    (ticked) 2026-10-27T09:13:08Z by d778be9d: 2a499ada0: .ci/rediacc_ci/release/local_gates.py and check_soak_period select(); pytest rc=0 (79); live run names ci-quick, vm-check, backup, origin-main and lock refusals
- [x] W2-B [writer] The entry, `rediacc_ci.release.local`, plus `"release:local"` in package.json. It is one declarative `STEPS` table, in this order:
  1. Version: `resolve_version --bump-type`, from the labels since the last tag.
  2. Gates: W2-A.
  3. Builds, in the release clone, each step timed:
     - renet (`.ci/rediacc_ci/build/build_renet.py:582-607`) under `bws_env exec --profile release-local` for `ACCOUNT_ED25519_PUBLIC_KEY`, then the W1-E gate;
     - the CLI bundle and npm tarball;
     - the SEAs for linux-x64, the two musl targets, and linux-arm64 (in a linux/arm64 node:24 container);
     - the Docker renet, rdc and server images, through buildx.
  4. The local-release-assist dispatch, started at minute zero, for the mac and win SEAs and their install legs.
  5. Stage: steps C1-C9 in memo A.
  6. Seal (`write_release_sentinel`), then the tag at once (W2-E).
  7. Publish:
     - promote to `:V` and `:latest`;
     - the Stripe sync and webhook verify;
     - cleanup of the channel tags.
  8. Edge Worker deploys, each with a W2-D record:
     - www and the executor artifacts;
     - then per region: the account Worker behind `order.account_refusal`, the account secrets through `account_secrets_local`, the proxy, and the console executor.
  9. Smoke: `verify_edge_endpoints`, plus the Linux install quick check in local docker.
  10. Tag and release: `tag_submodules`, `update_homebrew_tap`, `advance_contract_floor` and `create_github_release`.
  11. The release record, written to R2.
    (ticked) 2026-10-27T10:15:13Z by d778be9d: d291e6690: .ci/rediacc_ci/release/local.py and the release:local script; pytest test_release_local.py rc=0 (31); npm run release:local -- --channel edge --dry-run prints 105 steps then refuses ci-quick, vm-check, backup, origin-main

  - `--channel stable` runs the promote-stable steps instead:
    - `promote_r2_to_stable`;
    - the Docker move from `:V` to `:stable` for renet, rdc and server;
    - the stable deploys;
    - `verify_stable_endpoints`;
    - `mark_production`.
  - `--dry-run` prints every step with profile and key names only. It reads no secret value and writes nothing.
  - Owns: local.py, test_release_local.py and package.json.
  - Accept:
    - `npm run release:local -- --channel edge --dry-run` prints the full step list and exits 0 on green receipts, or names the refusal;
    - a fake bws that returns `CANARY-...` never shows in stdout or stderr;
    - a `STEPS` invariant test passes: the sentinel is immediately followed by the tag, the tag comes before any step that can fail, and the CLI publish comes before any account deploy.
- [x] W2-C [writer] The `block_unasked_release` guard (pre-bash).
  - It admits `npm run release:local` without `--dry-run` only when it carries `RELEASE_ASKED=ASKED:<minute>`, proven through the transcript (`.claude/rediacc_hooks/guards/block_vm_unverified_push.py:655-669`).
  - It refuses these raw publish verbs from agent Bash:
    - `wrangler deploy` and `wrangler rollback`;
    - `gh release create`;
    - a `git push` of a `v*` tag;
    - `docker` or `buildx` with `--push`;
    - `-m rediacc_ci.deploy.*`;
    - `-m` on the release publishers (`create_github_release`, `tag_submodules`, `update_homebrew_tap`, `mark_production`).
  - A shell-write twin refuses agent writes under `.ci/cache/release/`.
  - Add a `("release:local","aws")` prerequisite row to `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:84-103`.
  - Owns: block_unasked_release.py, test-block_unasked_release.py and block_host_toolchain_run.py.
  - Accept: `run_tests.py -k unasked_release` rc=0; `--dry-run` passes; a raw `wrangler deploy` is refused.
    (ticked) 2026-10-27T09:13:10Z by d778be9d: eb34e6209: .claude/rediacc_hooks/guards/block_unasked_release.py; test-block_unasked_release.py rc=0 (147 cases); run_tests -k "unasked_release or host_toolchain" rc=0 (314)
- [x] W2-D [writer] Durable deploy records.
  - `deploy_record.after --sink r2` (`.ci/rediacc_ci/deploy/deploy_record.py:665`) writes `release-records/v<V>/<channel>/deploy-record-<target>-<region>.json` once, through `write_once_guard`. Today the record is a 3-day artifact (`.github/workflows/cd-deploy-account.yml:676`).
  - Add a www record (the version id before and after, the `wrangler rollback` command and the smoke rc) to `deploy_www.py` and `deploy_edge.py`, and put the account smoke rc into the account record.
  - Owns: deploy_record.py, deploy_www.py, deploy_edge.py and test_deploy_*.py.
  - Accept: pytest rc=0, and a www record carries the version id, the rollback command and the smoke rc.
    (ticked) 2026-10-27T08:24:25Z by d778be9d: 516105808: deploy_record after --sink r2 write-once records and the www record in deploy_www.py and deploy_edge.py; pytest rc=0 (73)
- [x] W2-E [writer] The tag module, `rediacc_ci.release.tag`.
  - Lift it from the inline bash at `.github/workflows/cd-v2.yml:256-272`. It creates `v<V>` idempotently and refuses on an unknown `ls-remote` result.
  - Add the `release-local` bws profile to `.ci/config/secret-supply.json`. It binds:
    - `ACCOUNT_ED25519_PUBLIC_KEY`;
    - `RELEASE_GPG_PRIVATE_KEY` and `RELEASE_GPG_PASSPHRASE`;
    - `GIT_BOT_NAME` and `GIT_BOT_EMAIL`;
    - `CLOUDFLARE_ZONE_ID`;
    - the R2 trio;
    - `STRIPE_SECRET_KEY`;
    - the www Worker secrets.
  - All of these names are already in `.ci/config/bws-secret-map.json`.
  - A GHCR token, and a GitHub token for the tag and the Release, are written into the store by the session through `bws_env store-from-env`.
  - Owns: tag.py, test_release_tag.py and the secret-supply profile.
  - Accept: pytest rc=0, and `npm run check:ci-secret-supply` rc=0.
    (ticked) 2026-10-27T08:05:24Z by d778be9d: 07e241f98: .ci/rediacc_ci/release/tag.py and the release-local profile in .ci/config/secret-supply.json; pytest test_release_tag.py rc=0 (7); npm run check:ci-secret-supply rc=0; AWS_SES_ACCESS_KEY_ID/SECRET exist only as regional pairs, left to W2-B

### Wave 3 (one clean break, after W2)

- [x] W3-A [writer] Workflows.
  - Delete these workflows:
    - `cd-v2.yml`;
    - `promote-stable.yml`, whose cron would race a local stable release;
    - `cd-deploy-account.yml`;
    - `cd-deploy-worker.yml`;
    - `backfill-release-sentinel.yml`.
  - In `ci.yml`, delete `finalize-release-sentinel` (:2127-2252) and its pipeline-sentinel assertion.
  - `cd-stage.yml` and `ci-build-docker.yml` stop writing edge, stable or GHCR on `main`. The PR's pr-N channel stays.
  - Add `local-release-assist.yml` (workflow_dispatch with version and sha). It builds the two mac and two win SEAs, runs the mac and win legs of `ct-install-methods.yml` against the staged bytes, and writes to R2 staging.
  - The `push: main` CI run on the released SHA stays as the after-the-fact check, and the entry records its run id in the release record.
  - Owns: the listed workflows.
  - Accept: actionlint is clean, and `npm run check:ci-workflows` and `npm run check:ci-workflow-invariants` exit rc=0.
    (ticked) 2026-10-27T10:19:52Z by d778be9d: 542888163: .github/workflows/local-release-assist.yml (scope narrowed by the ASKED:2026-10-27T09:45Z ruling, which keeps cd-v2 and promote-stable); check:ci-workflows, check:ci-actionlint, check:ci-parity, check:ci-workflow-invariants rc=0
- [x] W3-B [writer] Invariants and dead modules.
  - Port the release-order phase of `ci_workflow_invariants.py` (:33-60, :357-560) to check the W2-B `STEPS` table.
  - Delete these modules and their tests:
    - `dispatch_release`;
    - `resolve_ci_run`;
    - `decide_release_mode`;
    - `assert_artifact_version`;
    - `verify_artifact_attestation`;
    - `deployment_summary`;
    - `promote_r2_to_stable_hotfix` and `promote_docker_to_stable_hotfix`.
  - Owns: ci_workflow_invariants.py and its test, plus the deleted modules.
  - Accept: `npm run check:ci-pytest` rc=0, and the dead-python gate is green.
    (ticked) 2026-10-27T11:18:59Z by d778be9d: e5df30053: ci_workflow_invariants.py STEPS phase beside the kept CD phase (ruling ASKED:2026-10-27T09:45Z), no module deleted since cd-v2 still calls all eight; check:ci-workflow-invariants rc=0; pytest rc=0 (501)
- [x] W3-C [writer] Release state moves off `main`.
  - The contract floor becomes an ordinary commit in the next PR. `cd_preflight --checks c` warns when it lags.
  - The console's homebrew gitlink bump is dropped. The tap repository still receives its formula commit, admitted by W1-D.
  - Owns: advance_contract_floor.py, update_homebrew_tap.py and their tests.
  - Accept: pytest rc=0, and no code path pushes console `main`.
    (ticked) 2026-10-27T10:01:44Z by d778be9d: ee7d193e4: advance_contract_floor writes the floor in the working tree, update_homebrew_tap pushes only the tap, cd_preflight warns on lag; pytest rc=0 (111)
- [x] W3-D [writer] Docs.
  - CLAUDE.md, under Release Channels and the CI/CD Pipeline, says:
    - CI validates and `release:local` publishes;
    - stable is promoted by `release:local --channel stable` after the soak;
    - a merge is no longer a release.
  - `docs/agent-reference/release-process.md`: sections 3-9, 29-86 and 88-98.
  - `ci-gates.md`: lines 507-519 and 545.
  - `versioning.md`.
  - `.claude/skills/deploy/SKILL.md`: the raw local deploy path becomes `release:local --workers-only` (decision 3).
  - `.claude/commands/pr-merge.md`: step 6, where the resync trap goes away.
  - The job-graph region, regenerated.
  - Owns: the listed docs.
  - Accept: `npx tsx scripts/gen/gen-docs.ts --write` leaves no diff, and `check:ci-doc-region-parity` and `check:ci-prose-style` exit rc=0.
    (ticked) 2026-10-27T10:15:15Z by d778be9d: e41a00f15: CLAUDE.md, release-process.md, ci-gates.md, versioning.md, deploy SKILL.md, pr-merge.md to the 2026-10-27T09:45Z rulings; check:ci-prose-style, check:ci-doc-region-parity, check:cli-examples rc=0

### Live

- [ ] L1 [lead] One real edge release from the local machine, after the 1023-1 PR merges.
  - Record per-step timings in Results and compare them with the last CD pair: CI run 39898575743 plus CD run 39902042581, about 39 min to dispatch and about 60 min end to end.
  - Accept:
    - the release record in R2 shows every step ok;
    - `rdc --version` from the edge channel names V;
    - the R1 order entry reads satisfied;
    - the account Worker reaches eu edge after the CLI.
- [ ] L2 [lead] The first stable release through `release:local --channel stable` after the soak, together with the R3 live check (`subscription status` against `machine status hostinger --licenses`).
  - Accept: `verify_stable_endpoints` rc=0, and the stable deploy records are in R2.

## Order

| Box | Starts after |
|---|---|
| W1-A to W1-E | nothing (parallel) |
| W2-A | W1-A, W1-B, W1-C |
| W2-B | W1-C, W1-E, W2-A, W2-E |
| W2-C, W2-D | nothing |
| W3 | W2, landing as one commit series |
| L1 | W3 and the merged PR |
| L2 | L1 and the soak |

## Decisions (taken by default; the operator may veto through /ask)

1. Cleanliness is judged on a fresh clone of HEAD, not on the shared checkout. The shared checkout always holds ledgers from other sessions, so a literal rule there would always fail.
2. Both receipts are re-taken on `main` HEAD after the merge. The /pr-merge pointer moves change the tree, and no second admission path is added for tree-identical pointer moves.
3. The deploy skill's raw local path is replaced by `release:local --workers-only --regions`, so there is one path.
4. The backup receipt is required whenever backup paths moved since the previous tag. This matches the push guards.
5. The nightly soak waiver stays as written in release-process.md.
6. Artifacts are built locally, in the release clone.
   - Sigstore provenance needs the GitHub OIDC identity, so instead the release ships a SHA256 manifest signed with the release GPG key.
   - `verify_artifact_attestation` is deleted.
   - This is the decision most worth the operator's veto.
7. New bws entries are written by the session through `bws_env store-from-env`, following the 2026-10-23 ruling that there are no operator steps.

## Rulings (operator, ASKED:2026-10-27T09:45Z), which supersede the boxes and decisions above where they differ

1. Provenance for a local edge release is a SHA256 manifest of every artifact, signed with the release GPG key (decision 6 confirmed).
2. The tag, tap and GitHub Release pushes use the session's GitHub token (risk R3 accepted).
3. "EU/ASIA/US stable should be asked! They're CI/CD only. BUT edge and bench could be released via agent or with CI/CD."
   - Stable releases and stable Worker deploys stay CI/CD-only (`promote-stable.yml`), and always need a proven `RELEASE_ASKED`.
   - `release:local --channel stable` is refused.
   - Edge and bench are free for the agent.
4. Both edge paths stay. `cd-v2.yml` keeps releasing edge on every merge, and `release:local --channel edge` is the agent's extra, faster path. The two share the R2 sentinel lock (W2-A), so one version cannot be released twice.

Consequences for the boxes:
- W1-C did not edit `private/account/src/routes/configs.ts`; the `ENVELOPE_MIN_RDC` correction moved to worklist #61315099, landing with the L1 release commit, so it never entered W1-C's Owns.
- The `test_release_*.py` glob in the Owns header overlaps across boxes; each writer was in fact handed only its own named test files, so no two live writers shared a file.
- W3-A shrinks to adding `local-release-assist.yml`. `cd-v2.yml`, `promote-stable.yml`, the CD deploy workflows, ci.yml's `finalize-release-sentinel` and the main-branch R2 and GHCR publishes (not git pushes) in cd-stage and ci-build-docker all stay.
- W3-B keeps the CD release-order phase of `ci_workflow_invariants.py` and adds the `STEPS` invariant beside it. It deletes no module that CD still calls.
- W2-B refuses `--channel stable` and stable `--workers-only` targets.
- W2-C needs a proven ASKED for every stable target, in every region, and frees edge and bench.
- L2 becomes the first CI/CD stable promote after the soak, asked, with the R3 live check.
- The eu stable config store is mirrored into eu edge, and a local `eu-edge` config uses it (worklist #046d4339). Live checks such as R3 run there first.

## Timings (CI today; L1 measures local)

CI job times today:

| Job | Minutes |
|---|---|
| renet | 3.8 warm, 16.7 cold |
| SEA linux | 1.8 |
| SEA musl | 1.6 and 1.3 |
| SEA mac | 1.1 and 3.5 |
| SEA win | 2.4 and 9.0 |
| Docker renet | 6.9 |
| Docker server | 3.2 per arch |
| Docker rdc | 2.3 |
| stage | 10.7 |
| publish | 4.2 |
| www | 3.1 |
| account | 1.7 per region |
| install matrix | 5.6 |
| tag and Release | 3.8 |

The local estimate is 20-25 min with builds in parallel, against about 60 min for the CI round trip. The roughly 1.5 GB upload over the home line may dominate; L1 measures it.

## Gaps that stay on CI

The mac SEAs, the win SEAs, and the mac and win install legs all stay on CI. All four run in `local-release-assist.yml`, dispatched at minute zero and awaited before stage.
- **mac SEAs:** need a macOS host node and ad-hoc codesign (`.ci/rediacc_ci/build/build_cli_executables.py:714-760`).
- **win SEAs:** need a host `node.exe` and the native smoke test.
- **mac and win install legs:** need those runners.

## Risks

- **R1, dev key.** The DEV-key fallback is closed by W1-E before L1.
- **R2, sentinel then tag.** These are one unit, held by the W2-B `STEPS` invariant and by W3-B.
- **R3, tokens.** The tag and tap pushes run on the session's GitHub token, not the CI App token. If a ruleset refuses that token, W2-E adds a minimal dispatch job that mints the App token for those pushes only.
- **R4, missing host tools.** `aws`, `nfpm` and `clang` are missing on the host. The entry checks its prerequisites first, and the devbox is the fallback.
- **R5, racing releases.** Two local releases at once are prevented by the lock check in W2-A.
- **R6, server:stable.** The scheduled promote never moved `server:stable` (`.github/workflows/promote-stable.yml:215-227`), while the hotfix lane does. The local stable promote moves all three images on purpose.

## Results

(L1 and L2 record here.)
