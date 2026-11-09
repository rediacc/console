# PLAN-enterprise-isolation: every Enterprise company gets its own Workers, database and buckets, and no production account Worker holds the licence signing key

Status: executing -- promoted by operator 2026-11-08; design settled in the operator talk of 2026-11-05 (own Workers per company, one signer per region, release rings, manual removal, deploys both local and from GitHub)
Depends-On: PLAN-product-domain-rename.md, PLAN-website-routing-and-mail.md#W1, PLAN-website-routing-and-mail.md#W8, PLAN-website-routing-and-mail.md#M3 -- company hosts and shared Workers come from the rename; W1 is the lookup writer `enterprise add` calls, W8 is the other edit of auth.ts, and M3 is the sender of the owner invitation
Owner: d778be9d
Priority: P1 -- the Enterprise offer does not exist without it, and the signing key leaves every account Worker here
Concurrency: parallel -- operator 2026-11-08 ("go in parallel as much as possible", "make queue.md to ultra and try to start again"): the first-wave boxes (N1, N3, S1, K1, P1) add new files only and N2 also edits cf_usage_report.py and cf_leftovers.py, which `block_plan_concurrency` checks against the Owns lines of the other live plans; the signing-path, shared-Worker-config and ring-runner boxes (S2-S4, D1, D2, A1, A2, K2, G1) land after the rename batch and still meet the Owns overlap check
Owns: agent/plans/PLAN-enterprise-isolation.md, .ci/rediacc_ci/enterprise/**, .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/core/run_verbs.py, .ci/rediacc_ci/release/rings.py, .ci/rediacc_ci/release/rings_run.py, .ci/rediacc_ci/quality/enterprise_leak.py, .ci/rediacc_ci/ops/cf_usage_report.py, .ci/rediacc_ci/housekeeping/cf_leftovers.py, .ci/rediacc_ci/deploy/deploy_account.py, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/deploy/deploy_record.py, .ci/rediacc_ci/deploy/console_executor.py, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/deploy/deploy_signer.py, .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/tests/test_enterprise_*.py, .ci/rediacc_ci/tests/test_release_rings_*.py, .ci/rediacc_ci/tests/test_deploy_signer.py, .ci/rediacc_ci/tests/test_deploy_company_target.py, .ci/config/secret-supply.json, .claude/rediacc_hooks/guards/block_unasked_release.py, .claude/rediacc_hooks/guards/test-block_unasked_release.py, .github/workflows/cd-enterprise-release.yml, workers/signer/**, workers/account/enterprise.template.toml, workers/account/wrangler.*.toml, workers/account/.gitignore, workers/account/src/index.ts, workers/proxy/wrangler.template.toml, workers/proxy/.gitignore, workers/proxy/src/index.ts, workers/proxy/src/__tests__/allowlist.test.ts, private/account/control/**, private/account/src/services/license-signer.service.ts, private/account/src/services/signer-client.ts, private/account/src/services/crypto.service.ts, private/account/src/services/subscription.service.ts, private/account/src/services/free-license.service.ts, private/account/src/services/delegation-cert.service.ts, private/account/src/services/reminder.service.ts, private/account/src/services/auth.service.ts, private/account/src/services/enterprise-bootstrap.service.ts, private/account/src/app.ts, private/account/src/types/env.ts, private/account/src/types/subscription.ts, private/account/src/entry/cloudflare.ts, private/account/src/routes/subscriptions.ts, private/account/src/routes/auth.ts, private/account/rotation-manifest.json, private/account/scripts/rotation/**, private/account/tests/integration/**, private/account/docs/enterprise.md, private/account/CLAUDE.md, private/account (gitlink bump only)
Live-Proof: bench -- bench proves the signers, a company's whole life and the rings with fake companies; renet does not change, so hostinger's renewal through signer-eu is proven by H1 rather than a receipt
First-Seen: 2026-11-05

## Rulings (source: operator talk 2026-11-05)

- Ruling 1. "Failures are acceptable and fixed forward. There are no real customers."
- Ruling 4. "Bench first always."
- Ruling 6. "ONE SIGNER PER REGION: asia, eu, us", because "without signer on each region, if the geographical internet connection lose between servers, all customers are locked". The shared tier moves behind the signers in this plan, and no production account Worker holds the licence signing key. renet keeps one baked public key.
- Ruling 7. Delegation certificates stay self-service, through the regional signer, which checks the subscription. Refusing them on company Workers is not what was chosen.
- Ruling 8. Company deploys run both locally and from GitHub. "Deleting runs ONLY through the local script."
- Ruling 9. "Rings: bench, fast tier with 7-day soak, internal canary company, small under 10 machines, medium 10 to 49, large 50 and up. 24 h pause after small, 48 h after medium." Ring from machine count with a per-company override, optional per-company upgrade windows. "A security order skips pauses, and waives the 7-day soak only if it says so."
- Ruling 10. "Removal is manual: export first, no timer, no automatic deletion. Command only, no portal page. Limits on the subscription."
- Ruling 11. "IP allowlist opt-in, in the Worker, exempting only POST /licenses/renew. No Cloudflare Pro now."
- Ruling 12, the part this plan carries. Hosts `<company>.rediacc.cloud` and `<company>-proxy.rediacc.cloud`; internal tier name `enterprise`; channels stay `edge` and `stable`; lookup on by default, a contract can mark a company unlisted, free-mail domains refused.

This plan is public: no customer name appears in it or in any tracked file. `acme` is the fake example.

## Design

**Shape.** Each company has `account-<company>`, `proxy-<company>`, D1 `account-<company>`, buckets `configs-<company>` and `backups-<company>`, its own secrets and container app, in the one region its contract names. There is no shared Enterprise pool and no migration from the shared tier. Cloudflare hardware stays shared: a Worker is an isolate, not a machine.

**Signers.** `signer-eu`, `signer-us` and `signer-asia` have no route and are reached only by service binding. All three hold the same private key, because renet bakes one public key. A shared Worker binds its region's signer, and a company Worker binds the signer of its contract region. Today every account Worker receives the key in one bulk push (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:197) and reads it at boot (private/account/src/app.ts:250, private/account/src/services/reminder.service.ts:64). After S3 and S4 no production account Worker has it. The RPC offers typed methods only, never raw `sign(bytes)`, because blob and licence are both base64 JSON with no type tag. The sites that move: private/account/src/services/subscription.service.ts:1689, private/account/src/services/subscription.service.ts:1932, the FREE licence path, and private/account/src/services/delegation-cert.service.ts:231 and :350.

**Scope data: a control database per region.** `control-eu`, `control-us` and `control-asia`, plus `control-bench-eu` and `control-bench-us`, each bound only to its own signer and holding only its own region's companies. A single control database is what ruling 6 forbids, since a lost link to it stops every region's renewals. Carrying all scope in binding props was the other candidate: it needs no database, but a suspension or a limit change then takes a redeploy of a company Worker, and that Worker is the thing being suspended. A region's control database adds no new failure domain, because the caller's own D1 sits in the same region. Props carry identity only: `{tier, company id, region}` from the caller's deploy-time binding, which Worker code cannot change. The runtime form is already read at workers/proxy/src/egress.ts:187, and no tracked config sets props on a binding yet, so V1 proves it. The fallback, if it fails, is a per-caller HMAC secret with its hash in the control row.

**What a signer checks.** For a company: the subscription is the one registered in its control row, the `renewalUrl` host is exactly `<company>.rediacc.cloud`, plan and size are within the registered limits, expiry is bounded, and the company is not suspended. For the shared tier, which has many subscriptions: the signer binds its own region's `account-<r>` read-only, checks the row, requires the host `<r>.rediacc.cloud`, and refuses plan ENTERPRISE. FREE licences keep their 3 GB and 48 h bounds with no row. Each issue writes no state on the signer except an audit row for certificates.

**Delegation certificates.** Self-service stays, through a typed signer method. The signer checks the caller owns an active subscription, the certificate's plan, size and issuance fields match it, and validity is within `PLAN_DELEGATION_CERT_MAX_DAYS` (packages/shared/src/subscription/constants.ts:367). Known limit, recorded: renet does not enforce revocation, since only the account server checks it (private/account/src/services/repo-license-verify.service.ts:280), and a certificate can live up to 365 days. A leaked delegated key plus its certificate signs licences for that one subscription, plan and size until `validUntil`, which packages/www/src/content/docs/en/on-premise.md:280 already says. The plan flag `delegationCerts` is read by nothing at issuance, and the docs say every plan may self-serve (packages/www/src/content/docs/en/account-management.md:87), so this plan leaves both as they are.

**Known limits of the signer.** A compromised company Worker can still mint licences for its own subscription and any machine id, since renet checks the signature and the machine or repository fields. A compromised shared Worker can write its region's D1, so it can mint up to BUSINESS in that region, and neither can touch another region's companies or forge Enterprise. Three signers share one key, so a leak from one is a leak of all. One Cloudflare account remains one blast radius.

**A lost region.** Current licences keep working when a signer is gone: `up` skips expiry (private/renet/pkg/license/validator.go:177-186), and only new work stops at expiry. V2 removes one bench signer and shows the other region's company renews. Bench cannot prove a real network partition between Cloudflare regions, a D1 primary outage, or a failure of Cloudflare's control plane, and it runs one account.

**Bench and local dev.** Bench binds the production key by standing ruling (.ci/rediacc_ci/ops/deploy_bench.py:25), so a released renet verifies its licences. `account-bench` holds no key and `signer-bench-eu` and `signer-bench-us` do, so bench runs the production form. The Node entries keep a local signer, because they have no Worker to bind: `dev-gateway.ts`, `node.ts`, CI's `start_account` and `on-premise.ts`, where the key is the customer's delegated one. `LicenseSigner` picks local or binding; `entry/cloudflare.ts` refuses a private key and refuses a missing binding.

**Secrets per company.** Generated and per company: `ACCOUNT_X25519_*`, because a shared one lets one breached Worker open another company's captured traffic; `ACCOUNT_JWT_SECRET`; `ACCOUNT_CONFIG_SERVER_KEY`, stored durably because losing it loses layer 3 data; `ACCOUNT_SERVER_API_KEY`; an IAM user on the shared sender; a bucket-scoped backup token. Shared: the public Ed25519 key, the Turnstile widget, regional OTLP. Absent: the private key, `FREE_LICENSE_HMAC_KEY`, which means no FREE licences (private/account/src/services/free-license.service.ts:128), Stripe and `SELLER_*`, because contract billing lives outside. The pusher demands the FREE key today (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:244), so companies get their own required list. Store names are opaque `c<hex>` in a separate bws project.

**Config generation.** `regions.json` is public and stays untouched. Generated tomls go to gitignored `workers/{account,proxy}/enterprise.<company>.toml`, a name that escapes `CONFIG_GLOB` (.ci/rediacc_ci/deploy/proxy_configs.py:43). The proxy template gains a route placeholder that leaves shared output byte-identical, and the account side gains its first template.

**Routing.** A proxied `*.rediacc.cloud` record with Worker Routes for `<company>` and `<company>-proxy`. Custom Domains cannot be used: per the docs each issues its own certificate, which would publish company names in certificate logs, and they refuse wildcard DNS. Region and service labels are reserved, as is any `*-proxy` company name. Unknown labels fail the same way as known ones, so the DNS answers name no company. V4 proves Universal SSL covers the wildcard.

**Company lifecycle.** `./run.sh enterprise add <company> --region <r> --owner <mail> --storage-gb <n> [--allow-ip ...] [--unlisted] [--lookup-domain <d>] [--bench]`, resumable from an onboarding table, runs: validate the name against every region's control database (an unreachable region refuses the add); write the control row; create D1 and migrate; create buckets; write secrets; generate tomls; deploy through the binding-cycle bootstrap; bootstrap the org and an active ENTERPRISE subscription with limits on it (`create` ends `inactive` and takes no storage field: private/account/src/services/subscription.service.ts:221, private/account/src/types/subscription.ts:74); smoke both hosts; write the lookup entry unless unlisted; send the invitation; audit. `/register` is open and creates COMMUNITY (private/account/src/services/auth.service.ts:86), so company mode closes it to anyone not invited. `list`, `update`, `suspend`, `export` and `remove` follow. `remove` needs a completed export, keeps data unless `--delete-data --confirm <company>`, has no timer, refuses under `GITHUB_ACTIONS`, and no workflow calls it.

**Allowlist.** Opt-in per company, in the Worker's default fetch handler, named entrypoints untouched. Only `POST` on `LICENSE_RENEW_PATH` (packages/shared/src/subscription/constants.ts:426) is exempt, because a machine outside the list would otherwise lose renewal; the licence blob is its bearer proof. It reduces exposure and replaces nothing: login still applies.

**Rings.** Stages in order: bench, the fast tier's 7-day soak through `check_soak_period`, canary, small, medium, large. Pauses are 24 h after small and 48 h after medium, from the last company finished in that ring, with a re-smoke before leaving. Ring comes from machines: small under 10, medium 10 to 49, large 50 and up, with a per-company override. The count is `COUNT(DISTINCT machine_id)` over `subscription_activations` (private/account/src/db/schema.ts:143); rows prune on a float, so the control row keeps a high-water mark sampled at each release. A company outside its window holds its ring open. A failure latches a stop naming the company until `--resume V --company <id>`. A security order skips pauses with `--skip-pauses --order <id>`, and waives the soak only with `--waive-soak` on that same order. The core is a pure `decide(state, now)` returning `deploy`, `wait`, `window`, `stop` or `done`; the runner is stateless per invocation and uses one `Run` per company, because `Run.execute` rolls back every armed target on a failure (.ci/rediacc_ci/release/local.py:1475). Company steps drop `account-secrets`. Records go to the control database, never the releases bucket, which sits behind a public origin (.ci/rediacc_ci/release/local.py:80). An unreachable region stops only its own companies and is named.

**Two deploy paths.** Local: `./run.sh enterprise release`, the same module. GitHub: `cd-enterprise-release.yml`, `workflow_dispatch` only, in a public repository where inputs can be visible. The input is the opaque `c<hex>`, never a name; the first step masks it, and the step that resolves it to a name and hosts masks those before anything prints; wrangler output is captured, not echoed. There is no delete input. The claim that this keeps a name out of the logs and the run's API output is unverified until V10 runs against a fake company. `release_record`, the two public reports (`cf_usage_report`, `cf_leftovers`) and `secret-supply.json` are the other leak paths, closed by N2.

**Renet order.** Channels stay `edge` and `stable` (ruling 12), which replaces the report's per-ring channel trees; those also needed a re-login, since the CLI saves its channel at login or on a version refusal (packages/cli/src/commands/subscription.ts:161, packages/cli/src/services/account/account-client.ts:299). So `stable` publishes once, ahead of the canary, which keeps publish-before-deploy, and every company Worker reports `stable`. The rings order Workers, not machines: a machine takes the new CLI and renet on its own next mutating verb, in any ring, and no central push exists. V9 proves both directions a spread release creates, an old renet against a new Worker and a new renet against an old Worker. The per-company `version_policy` floor stays the hard stop.

**Limits.** Workers Paid allows 500 scripts, so about 245 companies, then Workers for Platforms; 1,000 routes per zone. The figures came through a summarizing tool, and V8 re-reads them.

## Tasks

`./run.sh enterprise ...` is built by C1, C2 and K2, and every `./run.sh enterprise proof <verb>` by P1. Writers land in the wave order.

### Wave 1

- [x] N1 [writer] Company name validation: reserved region, service and `*-proxy` names, derived from `regions.json` and well-known.
  Owns: .ci/rediacc_ci/enterprise/__init__.py (new), .ci/rediacc_ci/enterprise/names.py (new), .ci/rediacc_ci/tests/test_enterprise_names.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_names.py` rc 0.
    (ticked) 2026-11-08T16:04:34Z by d778be9d: commit:74075193c7 names.check refuses malformed, reserved (derived from regions.json and well-known plus service labels, notify added in 0a3ea72044), -proxy and opaque names; pytest test_enterprise_names.py 28 passed rc 0
- [x] N2 [writer] Leak gate refusing a tracked `enterprise.*.toml` or a non-opaque store name, and masking in the two public reports of anything not derived from `regions.json`.
  Owns: .ci/rediacc_ci/quality/enterprise_leak.py (new), .ci/rediacc_ci/ops/cf_usage_report.py, .ci/rediacc_ci/housekeeping/cf_leftovers.py, .ci/rediacc_ci/tests/test_enterprise_leak.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_leak.py` rc 0.
    (ticked) 2026-11-08T18:46:43Z by d778be9d: commit:1cddd943e2 N2 landed 1cddd943e2; accept pytest test_enterprise_leak.py rc 0 on the batch tip
- [x] N3 [writer] Control schema, one per region (companies, scope, ring, override, window, onboarding, rollout, audit), and a registry client that reads all regions and names an unreachable one.
  Owns: private/account/control/migrations/0001_control.sql (new), .ci/rediacc_ci/enterprise/registry.py (new), .ci/rediacc_ci/tests/test_enterprise_registry.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_registry.py` rc 0.
    (ticked) 2026-11-08T16:04:35Z by d778be9d: commit:74075193c7 control schema private/account control/migrations/0001_control.sql (account 129ebad, gitlink 6387aa3efc) with companies, scope, ring, ring_override, upgrade_window, onboarding, rollout, audit; registry reads every region through an injected query and raises RegistryUnreachableError naming each failed region; 35 tests rc 0; the live D1 transport plugs into Query in C1
- [x] S1 [writer] Oracle: the signer scope matrix, all refused: foreign subscription, wrong host, over limit, suspended, raw bytes, a shared caller asking for ENTERPRISE, a certificate over its ceiling. A legitimate certificate is admitted. It runs against fixtures until S2.
  Owns: private/account/tests/integration/license-signer-scope.test.ts (new).
  Accept: `(cd private/account && npx vitest run tests/integration/license-signer-scope.test.ts)` rc 0.
    (ticked) 2026-11-08T16:04:33Z by d778be9d: commit:6387aa3efc landed as account 8b40e77 (gitlink 6387aa3efc): the signer scope oracle, 42 refused and 8 admitted rows as it.todo until S2 exists, 10 matrix tests pass; vitest 107 passed 51 todo rc 0; a throwaway reference signer made all 61 pass and dropping its host checks failed exactly those 8 rows
    (corrected 2026-11-09, d778be9d) 4c31822a.1: S1 is closed on the oracle, not on a full matrix run: 42 refused and 8 admitted rows are `it.todo` until S2 exists, so the accept's rc 0 covers 10 executing tests. The refusals and the admit execute at S2. Owed: the accept command again once S2 lands, with zero todo rows reported.
- [x] K1 [writer] Oracle and pure core: `decide`, with planted failure, pauses, windows, override, thresholds, security order with and without a soak waiver.
  Owns: .ci/rediacc_ci/release/rings.py (new), .ci/rediacc_ci/tests/test_release_rings_decide.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_release_rings_decide.py` rc 0.
    (ticked) 2026-11-08T16:04:37Z by d778be9d: commit:b07a21b44c pure decide(state, now) with stages, ring thresholds, pauses, upgrade windows, override, failure latch and security order with and without a soak waiver; pytest test_release_rings_decide.py 41 passed rc 0, ruff and mypy rc 0
- [x] P1 [writer] Proof verbs `signer`, `region-loss`, `add`, `routing`, `release`, `replay`, `proxy`, `cost`, `renet`, `github`, `remove` and `keys`, each exiting non-zero on a broken claim, tested with recording fakes.
  Owns: .ci/rediacc_ci/enterprise/proof.py (new), .ci/rediacc_ci/tests/test_enterprise_proof.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_proof.py` rc 0.
    (ticked) 2026-11-08T16:04:38Z by d778be9d: commit:5b19ed4322 12 proof verbs (signer, region-loss, add, routing, release, replay, proxy, cost, renet, github, remove, keys), each exiting 1 on a broken claim, tested with a recording fake and 32 break cases; pytest 65 passed rc 0; the live Lab binding has no owning box yet (raised)
    (corrected 2026-11-09, d778be9d) 4c31822a.3: P1's accept exercises the proof verbs with recording fakes only, as the tick says. The live transport is exercised by the bench boxes below (`./run.sh enterprise proof <verb> --bench`), which are the owed proof; the live binding the tick raised has no owning box beyond them, and the first of those boxes to run must bind it.

### Wave 2

- [x] N4 [writer] Account template, proxy route placeholder, and a generator using `config_refusals` for a company target.
  Owns: workers/account/enterprise.template.toml (new), workers/proxy/wrangler.template.toml, workers/account/.gitignore, workers/proxy/.gitignore, .ci/rediacc_ci/deploy/proxy_configs.py, .ci/rediacc_ci/enterprise/configs.py (new), .ci/rediacc_ci/tests/test_enterprise_configs.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_configs.py` rc 0 and `npm run check:ci-proxy-configs` rc 0.
    (ticked) 2026-11-09T03:16:09Z by d778be9d: commit:cbbb88a368; pytest test_enterprise_configs.py + test_deploy_proxy_configs.py 83 passed rc 0; npm run check:ci-proxy-configs rc 0 (5 proxy configs hold)
- [ ] S2 [writer] Signer service and Worker with no route, modelled on `ExecutorIssuer`, with typed methods, a `probe()` and its deploy module.
  Owns: private/account/src/services/license-signer.service.ts (new), workers/signer/** (new), .ci/rediacc_ci/deploy/deploy_signer.py (new), .ci/rediacc_ci/tests/test_deploy_signer.py (new).
  Accept: `(cd private/account && npx vitest run tests/integration/license-signer-scope.test.ts)` rc 0 and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_deploy_signer.py` rc 0.
- [ ] S3 [writer] `LicenseSigner`: local `CryptoService` for the Node entries, or the binding client on Cloudflare, with the refusals in the Design. Every signing site moves, delegation included. `create` takes a given id.
  Owns: private/account/src/services/crypto.service.ts, private/account/src/services/subscription.service.ts, private/account/src/services/free-license.service.ts, private/account/src/services/delegation-cert.service.ts, private/account/src/services/reminder.service.ts, private/account/src/services/signer-client.ts (new), private/account/src/app.ts, private/account/src/types/env.ts, private/account/src/types/subscription.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/signer-client.test.ts (new).
  Accept: `(cd private/account && npx vitest run tests/integration/signer-client.test.ts)` rc 0 and `npx tsc --noEmit -p private/account` rc 0.

### Wave 3

- [ ] S4 [writer] The shared tier moves: `wrangler.<r>.toml` and `wrangler.bench.toml` bind their signer, the pusher and profile drop the private key, a signer profile carries it, and rotation's consumers point at the signers. A test refuses the key name in any account Worker's secret list.
  Owns: workers/account/wrangler.*.toml, .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/config/secret-supply.json, private/account/rotation-manifest.json, private/account/scripts/rotation/**, .ci/rediacc_ci/tests/test_enterprise_no_key_on_account.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_no_key_on_account.py .ci/rediacc_ci/tests/test_ops_deploy_bench.py` rc 0, `npm run check:ci-secret-supply` rc 0, and `(cd private/account && npx vitest run tests/integration/rotation-worker-consumer.test.ts)` rc 0.
- [ ] A1 [writer] Company mode: API-key bootstrap creating org, active ENTERPRISE subscription, limits and owner mail, idempotently; `/register` closed except to invited addresses. The invitation path for a person with no account is untraced, so the test covers it.
  Owns: private/account/src/routes/subscriptions.ts, private/account/src/routes/auth.ts, private/account/src/services/auth.service.ts, private/account/src/services/enterprise-bootstrap.service.ts (new), private/account/tests/integration/enterprise-bootstrap.test.ts (new).
  Accept: `(cd private/account && npx vitest run tests/integration/enterprise-bootstrap.test.ts)` rc 0.
- [x] A2 [writer] The opt-in allowlist on both Workers' default fetch, exempting only `POST` on the renew path, with `POST` to any other path and `GET` on the renew path refused in the test.
  Owns: workers/account/src/index.ts, workers/proxy/src/index.ts, workers/proxy/src/__tests__/allowlist.test.ts (new).
  Accept: `(cd workers/proxy && npx vitest run src/__tests__/allowlist.test.ts)` rc 0.
    (ticked) 2026-11-09T02:42:59Z by d778be9d: commit:16f57d6db9 commit:1dfcd7f371 commit:b0a6e261a7; vitest workers/proxy ip-allowlist + index 38 passed rc 0, private/account worker-allowlist 3 passed rc 0, tsc -p workers/proxy and -p workers/account rc 0; the accept file is named ip-allowlist.test.ts, not allowlist.test.ts
- [x] D1 [writer] `--company` on the deploy modules, with the record sink at the control database, never the releases bucket.
  Owns: .ci/rediacc_ci/deploy/deploy_account.py, .ci/rediacc_ci/deploy/deploy_proxy.py, .ci/rediacc_ci/deploy/deploy_record.py, .ci/rediacc_ci/deploy/console_executor.py, .ci/rediacc_ci/tests/test_deploy_company_target.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_deploy_company_target.py` rc 0.
    (ticked) 2026-11-09T03:59:02Z by d778be9d: commit:0f1d42cac3; pytest test_deploy_company_target.py 50 passed rc 0 on the landed tree (with test_enterprise_secrets 104 passed); writer ran 632 neighbour tests rc 0
- [x] D2 [writer] Company secrets: generate, store under opaque names, mint the R2 token and IAM user, push through `wrangler_argv`, with the company's own required list.
  Owns: .ci/rediacc_ci/enterprise/secrets.py (new), .ci/rediacc_ci/tests/test_enterprise_secrets.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_secrets.py` rc 0.
    (ticked) 2026-11-09T03:59:03Z by d778be9d: commit:57f7d3fa12; pytest test_enterprise_secrets.py 54 passed rc 0, red-first (ImportError rc 2 before the module)

### Wave 4

- [ ] C1 [writer] `./run.sh enterprise add`, resumable; `--bench` selects bench signers and control with `ENVIRONMENT=bench`, so mail capture works; it calls the lookup writer unless unlisted.
  Owns: .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/core/run_verbs.py, .ci/rediacc_ci/enterprise/cli.py (new), .ci/rediacc_ci/enterprise/onboarding.py (new), .ci/rediacc_ci/tests/test_enterprise_add.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_add.py` rc 0.
  (corrected 2026-11-09, d778be9d) The live runner found two owners missing (no box listed them): .ci/rediacc_ci/enterprise/lab.py, which proof.py's load_lab binds for every V box, and creating the control-<region> and control-bench-<region> D1 databases with control/migrations/0001_control.sql. Both join C1 (lab.py, control_db.py, test_enterprise_lab.py, test_enterprise_control_db.py); C1's accept adds those two test files and `./run.sh enterprise proof signer --bench` reaching the lab.
- [ ] C2 [writer] `list`, `update`, `suspend`, `export`, `remove` per the Design.
  Owns: .ci/rediacc_ci/enterprise/lifecycle.py (new), .ci/rediacc_ci/tests/test_enterprise_lifecycle.py (new).
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_lifecycle.py` rc 0.
- [ ] K2 [writer] Ring runner over `Step` and `Run`, one `Run` per company, machine sampling, `--company` taking the opaque id. `block_unasked_release` keeps its ask for a real company's release and admits `--bench`.
  Owns: .ci/rediacc_ci/release/rings_run.py (new), .ci/rediacc_ci/tests/test_release_rings_run.py (new), .claude/rediacc_hooks/guards/block_unasked_release.py, .claude/rediacc_hooks/guards/test-block_unasked_release.py.
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_release_rings_run.py` rc 0 and `python3 .claude/rediacc_hooks/guards/test-block_unasked_release.py` rc 0.
- [ ] G1 [writer] `cd-enterprise-release.yml` per the Design, and a test that no workflow file calls `enterprise remove` and that the mask step comes first.
  Owns: .github/workflows/cd-enterprise-release.yml (new), .ci/rediacc_ci/tests/test_enterprise_workflow.py (new).
  Accept: `npm run check:ci-workflows` rc 0 and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_enterprise_workflow.py` rc 0.

### Bench, one sequential runner, fake companies only

- [ ] V1 [live] Signers: deploy `signer-bench-eu` and `signer-bench-us`, cut `account-bench` over, and prove the binding across Workers, `ctx.props` honoured, scope refused, no private key in the account or company secret list, certificates issued through the signer, and a stopped signer giving a named error while a machine's current licence keeps working.
  Accept: `./run.sh enterprise proof signer --bench` rc 0.
- [ ] V2 [live] A lost region: a fake company on each bench signer, then the eu signer and its control database made unreachable. The us company issues and renews, the eu company gets the named error and its current licence works, and restoring eu renews it. Bench cannot prove a real partition, a D1 primary outage or a control-plane failure, and the box records that.
  Accept: `./run.sh enterprise proof region-loss --bench` rc 0.
- [ ] V3 [live] `enterprise add` end to end for two fake companies: a killed run resumes, a rerun changes nothing, owner mail is captured, the lookup hits for one and misses for an unlisted one, a free-mail domain is refused.
  Accept: `./run.sh enterprise proof add --bench` rc 0.
- [ ] V4 [live] Routing: the wildcard record and routes reach each Worker, the Universal certificate serves `<company>` and `<company>-proxy`, `eu` and company hosts do not collide, specific records win over the wildcard, certificate logs lack the fake name, Turnstile covers the subdomains.
  Accept: `./run.sh enterprise proof routing --bench` rc 0.
- [ ] V5 [live] Rings: 4 fake companies across canary, small, medium, large with shortened pauses. A planted failure stops and names one company, the others and the fast tier stay unchanged, and `--skip-pauses` without `--order` is refused.
  Accept: `./run.sh enterprise proof release --bench` rc 0.
- [ ] V6 [live] Sessions, API tokens, config tokens and E2E envelopes from one fake company all fail on the other.
  Accept: `./run.sh enterprise proof replay --bench` rc 0.
- [ ] V7 [live] Proxy and executor per company: separate container app and Durable Object, one company's token refused by the other's proxy, a console command runs, and the allowlist blocks a foreign IP while renewal still passes.
  Accept: `./run.sh enterprise proof proxy --bench` rc 0.
- [ ] V8 [live] Cost and time per company and per release, from records and `cf_usage_report`, with the image rebuild measured and the Cloudflare limits re-read.
  Accept: `./run.sh enterprise proof cost --bench` rc 0.
- [ ] V9 [live] Renet order on a fleet VM: a mutating verb moves renet and a read-only verb does not, an executor refuses to upload, the previous renet renews against the new Worker, and the new renet renews against the previous Worker.
  Accept: `./run.sh enterprise proof renet --bench` rc 0.
- [ ] V10 [live] GitHub path, after this workflow reaches the default branch: dispatch a release for a fake company, then grep the logs, the jobs API, the run API and the step summary for the fake name and hosts. Any hit fails the box, and the design changes before a real company rides it. This settles the visibility claim.
  Accept: `./run.sh enterprise proof github --bench` rc 0.
- [ ] V11 [live] Both paths of delete: the local script exports, then removes one fake company with data, and a second attempt under `GITHUB_ACTIONS=1` and a scan of the workflows both refuse. The GitHub path has no delete to run.
  Accept: `./run.sh enterprise proof remove --bench` rc 0.
- [ ] LP-bench [live] Fresh bench receipts after V11.
  Accept: live-proof bench account-smoke

### Production

- [ ] X1 [live] After bench: create `control-<r>`, deploy `signer-eu`, `signer-us` and `signer-asia`, cut the three shared Workers over, delete the private key from each, and re-read every account Worker's secret names. Ruling 4 covers these shared deploys. Each region then issues a licence.
  Accept: `./run.sh enterprise proof keys` rc 0 and `.ci/scripts/quality/check_region_consistency.py --live` rc 0.
- [ ] H1 [live] hostinger renews through `signer-eu` after X1. Mutating verbs here use released renet, as agent/plans/PLAN-product-domain-rename.md states; the Workers' cut-over itself waits on no merge.
  Accept: `./rdc.sh --config eu-remote machine status hostinger` rc 0 with a licence renewed after X1 recorded here.
- [ ] X2 [live] Create the internal canary company through `enterprise add`, unlisted, and run one release to it through the local path and one through GitHub.
  Accept: `./run.sh enterprise list` rc 0, naming the canary as healthy on both paths' last release.
- [ ] L1 [writer] Operator runbook, the X25519 line corrected in `private/account/CLAUDE.md` (it does the request tunnel, not config storage), and the signer's limits and the certificate limit written down.
  Owns: private/account/docs/enterprise.md (new), private/account/CLAUDE.md.
  Accept: `test -s private/account/docs/enterprise.md` rc 0 and `npm run -s check:ci-prose-style` rc 0.

## Not verified

- `ctx.props` being honoured and deploy-only on a service binding: V1.
- A workflow input's visibility in a public repository, and whether a mask reaches every surface: V10.
- Universal SSL over `*.rediacc.cloud`, Turnstile over subdomains, routes on a wildcard record: V4.
- Whether `release-records/` is readable per key at the public origin, treated as public.
- The invitation path for a person with no account: A1.
- Whether `console_executor --enable` is idempotent, and whether the executor image rebuilds per company and at what cost: V8.
- The Cloudflare figures in Limits.
- Whether dispatch needs the workflow file on the default branch, assumed in V10.
