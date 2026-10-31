# PLAN: Limit the production signing keys exported by bws-secrets to the steps that consume them
Status: executing
Owner: d778be9d
Updated: 2026-10-30
Epic: 9f92c43e (worklist #ad2571af)
Priority: P1 -- the production licence-signing key (and the X25519 and release GPG private keys) can be read by every step after the fetch in 18 jobs (the 17 signing-key jobs, three of them also fetching X25519, plus cd-stage's GPG pair), including third-party actions and test code. Anyone who reads it can mint valid licences.
Depends-On: no-dep -- the change uses only the existing bws-secrets action, plus a new scrub action and a new gate.
Owns: .github/actions/bws-scrub/**, .github/actions/bws-secrets/action.yml, .ci/config/bws-step-scoped.json, .ci/scripts/quality/check_bws_step_scope.py, .ci/rediacc_ci/quality/bws_step_scope.py, .ci/rediacc_ci/tests/test_quality_bws_step_scope.py, .github/workflows/{ct-tests,ci,ct-e2e-probe,cd-deploy-worker,cd-deploy-account,ci-ops-test,cd-stage}.yml (only the fetch, consumer and scrub windows), package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml (gate-bind region)
Concurrency: parallel -- the workflow edits are a few lines next to each consumer. Conflicts with other plans editing ct-tests.yml are textual only.

## Context
- `.github/actions/bws-secrets/action.yml:3-4` says the action exports secrets "for the rest of the job". `.github/actions/bws-secrets/fetch.sh:9` writes each value to GITHUB_ENV and GITHUB_OUTPUT after `::add-mask::`. The `uses: bitwarden/sm-action` fallback (`action.yml:~225`) writes GITHUB_ENV directly and cannot be changed.
- Verified: 17 fetches and 17 consumer lines, exactly one consumer step per job. Steps after the consumer (counted to the end of the job):
  - ct-tests.yml:
    - test-e2e-workers 435/493, 16 steps
    - test-e2e-ceph 666/719, 13
    - test-e2e-ceph-workers 833/886, 13
    - test-e2e-ceph-workers-rpm 1192/1241, 15
    - test-e2e-k8s 1357/1410, 13
    - test-e2e-k8s-ceph 1526/1579, 13
    - test-e2e-k8s-multinode 1699/1772, 13
    - test-e2e-migrate 2161/2214, 14
    - test-fork-isolation 2345/2398, 18
    - test-renet-go 2565/2605, 13
    - test-account-e2e 2929/3006, 2
  - ci.yml: stripe-sandbox 792/838, 2; deploy-preview 1556/1677, 1
  - ct-e2e-probe.yml: probe-file 106/161, 13
  - cd-deploy-worker.yml: deploy 63/206, 1
  - cd-deploy-account.yml: deploy 280/591, 6
  - ci-ops-test.yml: ops-vm-provision 129/195, 23
- There are also 10 to 60 lines of steps between each fetch and its consumer, for example `.github/workflows/ct-tests.yml:437-490`: app-token, docker/login-action, setup-go, setup-workspace and the CLI build.
- Other private keys exported the same way:
  - ACCOUNT_X25519_PRIVATE_KEY: 3 jobs (`.github/workflows/cd-deploy-worker.yml:67`, `.github/workflows/cd-deploy-account.yml:284`, `.github/workflows/ci.yml:1560`), consumed in the same steps as ED25519.
  - RELEASE_GPG_PRIVATE_KEY and RELEASE_GPG_PASSPHRASE: `.github/workflows/cd-stage.yml:113-114`, with two consumer steps (S4 names them by the line numbers of the tree it was written against) and unrelated steps between them.
- Other high-value names in the same class, counted by `NAME > BWS_` lines:
  - GITHUB_APP_PRIVATE_KEY (63)
  - DOCKERHUB_TOKEN (23)
  - CLOUDFLARE_R2_SECRET_ACCESS_KEY (16)
  - CLOUDFLARE_API_TOKEN (15)
  - STRIPE_SANDBOX_SECRET_KEY (7)
  - ACCOUNT_JWT_SECRET (6)
  - ACCOUNT_SERVER_API_KEY (5)
  - STRIPE_SECRET_KEY (3)
  - AWS_SES_SECRET_ACCESS_KEY_{EU,US,ASIA}
  - STRIPE_WEBHOOK_SECRET_*
  - ACCOUNT_CONFIG_SERVER_KEY_* (6)
  - ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_*
  - ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN (2)
  - CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN (2)
- Remaining exposure this plan does not remove: `.ci/rediacc_ci/testrun/start_account.py:242-253` starts a long-lived server with `**os.environ`. The key stays in that process's environment for the rest of the job, so a later step running as the same user can read it from `/proc/<pid>/environ`.
- Why option (c) is rejected: `.ci/rediacc_ci/core/bws_env.py:370-379` needs the `bws` CLI, which CI runners do not have. Its `exec` verb also never prints `::add-mask::`, so if a child process printed the key, the public log would show it unmasked.

## Decision
Option (b), plus moving the fetch, done through a config-driven set of names:
- Remove each scoped name from the job-start fetch.
- Add a dedicated `bws-secrets` step that fetches only the scoped names, placed immediately before the first consumer. This leaves no steps between fetch and consumer.
- Add a new `.github/actions/bws-scrub` step with `if: always()` immediately after the last consumer. It writes `NAME=` to GITHUB_ENV, so the value is blank in every later step whether the consumer passed or failed.

Masking is unchanged: the mask is registered at fetch time and stays for the whole job. The second fetch is cheap because the prewarm step finds the binary already in place.

Why not option (a): composite action outputs must be declared by name in advance, a temp file is a new place for the key to leak, and the sm-action fallback writes GITHUB_ENV anyway, so (a) would still need a scrub.

`continue-on-error` is never used. It is banned by check:ci-workflows.

In scope: ACCOUNT_ED25519_PRIVATE_KEY, ACCOUNT_X25519_PRIVATE_KEY, RELEASE_GPG_PRIVATE_KEY and RELEASE_GPG_PASSPHRASE. The rest of the class goes to a follow-up item. The config list can only grow.

- [x] S1 Add `.github/actions/bws-scrub/action.yml`:
  - Input `names`: one `BWS_[A-Z0-9_]+` per line. Reject a malformed or empty list with `::error::`.
  - Append `NAME=` to GITHUB_ENV for each name. Never echo a value.
  - Update the `.github/actions/bws-secrets/action.yml:3-4` description to point at step-scoped use.
    (ticked) 2026-10-30T23:23:50Z by d778be9d: commit:eed3a09c .github/actions/bws-scrub/action.yml:1; the scrub refuses an empty or malformed list and writes NAME= only; check:ci-workflows rc 0

  Accept: `npm run check:ci-actionlint && npm run check:ci-workflows`
- [x] S2 Add `.ci/config/bws-step-scoped.json` listing the four in-scope names. Each entry needs a substantive `BLOCKER:`-style reason, following `docs/agent-reference/suppressions.md`.
    (ticked) 2026-10-30T23:23:53Z by d778be9d: commit:eed3a09c .ci/config/bws-step-scoped.json:1; four names with BLOCKER reasons; check:ci-bws-map rc 0

  Accept: `npm run check:ci-bws-map`
- [x] S3 Sweep the 17 ED25519 jobs listed in Context. In each: remove the name from the job-start fetch, add the dedicated fetch immediately before the consumer, and add bws-scrub with `if: always()` immediately after it. In the 3 deploy jobs, X25519 moves into the same dedicated fetch.
    (ticked) 2026-10-30T23:23:56Z by d778be9d: commit:eed3a09c .github/workflows/ct-tests.yml:1; 17 jobs swept, X25519 in the three deploy jobs; check:ci-bws-step-scope rc 0

  Accept: `npm run check:ci-bws-step-scope && npm run check:ci-workflow-env-provision`
- [x] S4 cd-stage: give each GPG consumer (`.github/workflows/cd-stage.yml:158`, `:197`) its own fetch and scrub pair, so the unrelated steps between them no longer see the keys.
    (ticked) 2026-10-30T23:23:59Z by d778be9d: commit:eed3a09c .github/workflows/cd-stage.yml:1; two fetch and scrub pairs; check:ci-bws-step-scope rc 0

  Accept: `npm run check:ci-bws-step-scope`
- [x] S5 Add the gate `check:ci-bws-step-scope`:
  - Logic goes in `.ci/rediacc_ci/quality/bws_step_scope.py` and reuses `check_bws_map.parse_requests` to parse the `NAME > ENV` lines.
  - Entry point: `.ci/scripts/quality/check_bws_step_scope.py`, with gate header `step: Bitwarden step-scoped secrets`, `lane: quality-security` and `selftest: true`.
  - For each config name, in every job, the gate refuses:
    - (i) the name requested by a fetch that also requests names not in the config;
    - (ii) any step between that fetch and the last consumer that is not itself a consumer;
    - (iii) no bws-scrub naming it immediately after the last consumer;
    - (iv) a scrub without `if: always()`;
    - (v) any reference to `env.BWS_<name>` after the scrub.
    (ticked) 2026-10-30T23:24:02Z by d778be9d: commit:eed3a09c .ci/rediacc_ci/quality/bws_step_scope.py:1; five rules, floor and reason checks; red before the sweep (296 problems), green after

  Accept: `npm run check:ci-bws-step-scope`
- [x] S6 Control, using a `WORKFLOW_DIR` fixture seam like the one in `.ci/scripts/quality/check_workflows.py`:
  - Each of five planted fixtures, one per rule (i) to (v), must turn the gate red and name its rule. One plant is the pre-fix .github/workflows/ct-tests.yml:435/493 shape.
  - The fixed fixture must stay green, and so must the real tree.
  - Pytest covers both directions.
    (ticked) 2026-10-30T23:24:05Z by d778be9d: commit:eed3a09c .ci/rediacc_ci/tests/test_quality_bws_step_scope.py:1; selftest 29 controls rc 0; pytest 14 passed; each rule planted into ct-tests.yml fired

  Accept: `npm run check:ci-bws-step-scope -- --selftest && .ci/cache/toolchain/uv-tools/bin/pytest .ci/rediacc_ci/tests/test_quality_bws_step_scope.py`
- [x] S7 Wiring, per CLAUDE.md:
  - Add `"check:ci-bws-step-scope": ".ci/scripts/quality/check_bws_step_scope.py"` to package.json.
  - Run `npm run gate:bind` to generate the `.github/workflows/ci-quality.yml` step in the gate-bind region (job quality-security).
  - Add the gen-manifest entry in `scripts/ci-runner/manifest.ts`, modelled on check:ci-bws-map at `scripts/ci-runner/manifest.ts:1609`.
    (ticked) 2026-10-30T23:24:09Z by d778be9d: commit:eed3a09c scripts/ci-runner/manifest.ts:1; manifest, gates.lock, gate-bind step; check:ci-parity, reachability and gate-bind rc 0

  Accept: `npm run check:ci-gen-manifest && npm run check:ci-gate-bind && npm run check:ci-workflow-gates`
- [x] S8 Open a follow-up worklist item under epic 9f92c43e for the rest of the class listed in Context, starting with GITHUB_APP_PRIVATE_KEY (63 jobs, consumed by app-token straight after the fetch), and for the remaining `/proc` exposure in start_account.
    (ticked) 2026-10-30T23:24:12Z by d778be9d: commit:eed3a09c .ci/config/bws-step-scoped.json:1; follow-up item #a3910bfd added under epic 9f92c43e

  Accept: `.claude/hooks/stop/worklist.py --list | grep -F bws-step-scope-followup`
- [ ] S9 Live proof, branch push: on "Console CI" for the PR head, the "Console CT - Tests" legs test-e2e-workers, test-renet-go and test-account-e2e, plus stripe-sandbox and deploy-preview, all pass, and each scrub step shows in the job log.

  Accept: `.ci/scripts/ci/ci-trace.py --wait --until-final`
- [ ] S10 POST-MERGE: on main, "Deploy Account Workers" (job deploy), "Deploy WWW Worker" (job deploy) and "CD - Stage Artifacts (Reusable)" pass on the edge CD run. "CI - OPS Tests" (job ops-vm-provision) passes on its next dispatch.

  Accept: `.ci/scripts/ci/ci-trace.py --branch main --wait --until-final`

### Critical Files for Implementation
- /home/developer/console/.github/actions/bws-secrets/action.yml
- /home/developer/console/.github/workflows/ct-tests.yml
- /home/developer/console/.github/workflows/cd-deploy-account.yml
- /home/developer/console/.ci/scripts/quality/check_bws_map.py
- /home/developer/console/scripts/ci-runner/manifest.ts
