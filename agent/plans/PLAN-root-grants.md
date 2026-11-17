# PLAN: Root grants: one names-to-ids reconcile gives the root email every panel in every region

Status: approved -- operator rulings of 2026-11-17 quoted under Rulings: partner org "Rediacc, registered (Recommended)", durable form "Yes: ops tool + ops-health check (Recommended)", and the method "Need a better and consistent solution. Maybe we should use the same code with names to IDs, mapping." Defaults R1-R7 run unless the operator vetoes them.
Owner: d778be9d
Depends-On: PLAN-root-api-token.md#OP1, PLAN-root-api-token.md#LP0 -- only the production apply boxes LA-eu, LA-us and LA-asia wait for these. They need the root-token routes live on the production account Workers and the eu token minted. Every code, bench, health and operator box runs now.
Priority: P1 -- today muhammed@rediacc.com has admin in every region, but console only in eu, no partner/sales panel anywhere, and a COMMUNITY inactive subscription in us and asia (worklist cd796a07)
Concurrency: parallel -- Wave 1 runs two file-disjoint writers against the wire contract fixed in Design 4: S1 (account server) and C1 (ops tool). Wave 2 (P1, H1, D1) starts after both land. S1 edits private/account/src/routes/index.ts, src/container.ts, src/routes/root.ts and private/account/CLAUDE.md, which PLAN-root-api-token also owns. Every code box there is ticked and only live boxes stay open, so no writer of that plan is live. H1 edits .ci/rediacc_ci/ops/ops_health.py and its test, both owned by PLAN-health-checks-local. C1 adds one consumer to .ci/config/secret-supply.json, which many plans list. Each writer runs block_plan_concurrency before its first edit.
Owns: agent/plans/PLAN-root-grants.md, private/account (gitlink bump only), private/account/src/types/root-grants.ts, private/account/src/services/root-grants.service.ts, private/account/src/routes/root-grants.ts, private/account/src/dto/root-grants.dto.ts, private/account/src/dto/index.ts, private/account/src/routes/index.ts, private/account/src/container.ts, private/account/src/services/org.service.ts, private/account/src/routes/root.ts, private/account/tests/integration/root-grants*.test.ts, private/account/CLAUDE.md, .ci/config/root-grants.json, .ci/rediacc_ci/ops/root_grants.py, .ci/rediacc_ci/tests/test_ops_root_grants.py, .ci/rediacc_ci/ops/ops_health.py, .ci/rediacc_ci/tests/test_ops_health.py, .ci/config/ops-health.json, .ci/config/secret-supply.json, .ci/config/env-manifest.json, .ci/config/python-env-registry.json
Live-Proof: bench -- the account route (S1) reaches the eu, us and asia benches through deploy_bench and is applied there first (LB-*). Production edge eu, us and asia (the same D1 that stable serves) are proved by hand in LA-* once the edge Workers serve the route. No registry target can stand in for that.
Updated: 2026-11-17
First-Seen: 2026-11-17

## Ask

At `https://<region>.rediacc.cloud/account/`, a sign-in as the root email must show four things in eu, us and asia: the normal user panels, the console, the admin group, and the partner/sales panels.

Two constraints:
- **The fix is declarative and durable.** A committed config names the desired state by names. One tool resolves those names to each region's ids and applies them through the account service's own code. An ops-health check goes red when a region drifts.
- **Ad-hoc SQL is ruled out.**

## Context (read 2026-11-17 against the tree; a writer re-reads each citation before relying on it)

1. **Admin is `users.role = 'root'`.**
   - The enum is at private/account/src/db/schema.ts:29-31. `requireRole` compares `userRole` (private/account/src/middleware/session.ts:36-44).
   - Sign-in promotes the user whose email equals `ROOT_EMAIL`, by exact string equality, through `userService.update` with event `auth.auto_promote_root` (private/account/src/routes/auth.ts:63-80).
   - The value comes from `envConfig.rootEmail` (private/account/src/app.ts:631), validated at private/account/src/types/env.ts:153.
   - Every /admin factory now builds `rootAuth()` (private/account/src/routes/root.ts:54, private/account/src/routes/root-partner.ts:31; exported at private/account/src/middleware/root-auth.ts:127). So a root API token session is accepted on any new /admin route without further work.
2. **Console needs four things.**
   - A primary subscription that is live and on a plan with `webConsole`. PLAN_METADATA is at packages/shared/src/subscription/constants.ts:573-614: FREE and COMMUNITY are false, PROFESSIONAL, BUSINESS and ENTERPRISE are true.
   - An org that is not blocked (private/account/src/services/console-entitlement.service.ts:73).
   - A config store row that holds `server_recoverable_org_passphrase` (private/account/src/services/console-entitlement.service.ts:85-90).
   - The ops tool executor_orgs mirrors the same rule in read-only SQL (.ci/rediacc_ci/ops/executor_orgs.py:47, :49).
3. **Partner is a separate org.** `requirePartner` needs an `active` partner_profiles row and a partner_members row for the active org (private/account/src/middleware/partner.ts:22-71). The sidebar picks partner or customer navigation per active org (private/account/web/src/components/AppSidebar.tsx:332). So the partner grant must be a second org beside the personal one.
4. **Why `partnerApplicationService.approve` cannot be reused as is.**
   - It requires a `new` application row (private/account/src/services/partner-application.service.ts:140-144).
   - It creates a user when the email is unknown (:146-152).
   - It mints a magic link and mails it (:186-195).
   - Each of those breaks a "never" rule in Design 5. The parts it does call are reusable: `orgService.createOwnedOrg` (:154-159) and the two inserts with tier `registered` and partner_role `admin` (:161-178).
5. **`createOwnedOrg` builds four tables and a team in one atomic batch.** It writes the org, the owner membership, a subscription built by `buildInitialSubscriptionFields` and the `subscription_shards` directory row, then calls `ensureDefaultTeam` (private/account/src/services/org.service.ts:213-263). Every id is random (:223-226), so a rerun with no other key would create a duplicate.
6. **A plan change must go through the subscription service.**
   - `updateSubscription` (private/account/src/services/subscription.service.ts:609-701) derives size, issuance, features and activation limits from the plan code (:639-651).
   - It then re-signs the license blob (:699-701), and the signing key exists only in the Worker. A SQL `UPDATE subscriptions SET plan_code` would leave the served license on the old plan.
   - The root route `PUT /admin/subscriptions/:id` wraps it (private/account/src/routes/root.ts:234-275), and its schema is at private/account/src/types/subscription.ts:205-230.
7. **Tiers and plans.** Partner tiers are `registered|silver|gold|platinum` (private/account/src/db/schema.ts:995; private/account/src/types/partner.ts:5). Plan codes the admin schema accepts are `COMMUNITY|PROFESSIONAL|BUSINESS|ENTERPRISE` (private/account/src/types/subscription.ts:28).
8. **Every table this plan touches is shard class `global`,** so one regional D1 holds them: subscriptions (private/account/src/db/shard-router.ts:57), organizations (:115), partner tables (:67-68). Signed blobs are tenant class, which is one more reason the blob is not written by hand.
9. **The us/asia `data_region = 'eu'` comes from the code, not from data entry.**
   - The first-org provisioning hard-codes `'eu'` (private/account/src/services/org.service.ts:149), and so does `createOrg` (:70).
   - `createOwnedOrg` takes the region (:236), and the approve route passes `envConfig.region` (private/account/src/routes/root-partner.ts:57-64).
   - Each Worker's `REGION` var names its own region (workers/account/wrangler.us.toml:12-13; workers/account/wrangler.bench-us.toml:22-23).
10. **Credentials and targets.**
    - Production root calls go through `root_login.open_token_session(target, region)` (.ci/rediacc_ci/ops/root_login.py:520-525). It returns an `AdminClient` with `post` (:421), reads `ROOT_API_TOKEN_<SUFFIX>` per region (:168) and has `TARGETS = ("stable", "edge")` (:44).
    - The `root-login` consumer requires the EU token and the seed; US and ASIA are optional until minted (.ci/config/secret-supply.json:691-703).
    - The eu mint is PLAN-root-api-token OP1, still open (agent/plans/PLAN-root-api-token.md:296).
    - Benches have no root token. login_bench opens a cookie session with `AccountApi` (.ci/rediacc_ci/ops/login_bench.py:328-345) and elevates headless through the reauth mail with `elevate` (.ci/rediacc_ci/ops/login_bench.py:486-502).
    - Edge and stable share one Worker set and one D1 per region (agent/plans/PLAN-root-api-token.md Context 9), so a grant on edge is a grant on stable.
    - Bench rows in regions.json are deployable for eu, us and asia. Configs resolve through `account_config` and `resolve_target` (.ci/rediacc_ci/deploy/console_executor.py:291-345).
11. **Precedents.**
    - D1 reads go through `executor_orgs.d1_argv` (.ci/rediacc_ci/ops/executor_orgs.py:110-122), which puts SQL on argv as `--command`.
    - The dry-run-first, bookmark-before-write pattern is in .ci/rediacc_ci/ops/repair_org_customer_ids.py:10. The bookmark helper is `deploy_record.d1_bookmark` (.ci/rediacc_ci/deploy/deploy_record.py:254-262).
    - The route-against-ops parity test spawns the Python that owns the ops logic and compares database snapshots (private/account/tests/integration/root-console-block.test.ts:309-346).
    - Python tests build sqlite from private/account/drizzle/*.sql in journal order (.ci/rediacc_ci/tests/test_ops_mirror_config_store.py:116; .ci/rediacc_ci/tests/test_d1_shard_move.py:3).
12. **Ops-health.**
    - Subprocess checks are registered in `SUBPROCESS_CHECKS` (.ci/rediacc_ci/ops/ops_health.py:87-92) and run by `subprocess_check` with a 0/1/2 contract (.ci/rediacc_ci/ops/ops_health.py:946-965). TTLs come from `local_ttl_minutes` keyed by the check name with `-` replaced by `_` (.ci/rediacc_ci/ops/ops_health.py:176-181).
    - The state set is `green|red|unknown` (workers/ops-health/src/targets.ts:24), and the off-box ingest refuses `amber` with 400 (workers/ops-health/src/__tests__/state.test.ts:201-203). So amber cannot be a fourth state on the wire.

## Rulings

Operator words (2026-11-17), verbatim:
- "At https://*.rediacc.cloud/account/ when I logged in with muhammed@rediacc.com I should see the normal user panels + console + admin + partner/sales for all regions. Can you please investigate and update the database for me?"
- "maybe we should bind it into a CI rule for all instances based on root email?"
- On the per-region plan fix and the partner creation: "Need a better and consistent solution. Maybe we should use the same code with names to IDs, mapping."
- Partner org: "Rediacc, registered (Recommended)". Durable: "Yes: ops tool + ops-health check (Recommended)".
- Production and edge writes run under the standing ruling ASKED:2026-11-16T05:39Z (worklist fec5f05a).

Defaults logged for veto:
- **R1. Writes go through a new root route; SQL is read-only.**
  - The route runs the account services and holds the signing key. A plan change re-signs the license blob (Context 6), and a new org spans four tables and a team (Context 5), so neither can be reproduced by hand SQL without drift.
  - The tool and the health check read the D1 with SELECTs only. That needs no TOTP step and no IP-bound token, so a 6-hourly check does not take the operator's 30 s steps.
  - Zero SQL writes. The only non-route write the tool makes is the time-travel bookmark read.
  - Rejected alternative: guarded SQL writes in the style of executor_orgs. They would leave the signed blob stale and copy `createOwnedOrg` by hand.
- **R2. The root email never travels.**
  - The route acts only on the user whose email equals the Worker's own `ROOT_EMAIL` (`envConfig.rootEmail`, exact equality as at private/account/src/routes/auth.ts:68). The request body carries no email and no id.
  - The tool reads ROOT_EMAIL from bws only to select the same user in the read SQL. The email goes into a 0600 temp `--file`, never into argv.
- **R3. Amber is local.** A missing config store gives rc 0 (green on the wire) with an `AMBER operator:` line in the detail and the cache. Grant drift gives rc 1 (red, mailed by the alerter). No fourth state is added to the Worker.
- **R4. A console block is not undone.** A set `console_executor_blocked_at` is a deliberate root kill switch. The tool reports it as red `console.blocked` and never unblocks it.
- **R5. Stripe-managed subscriptions are left alone.** A primary subscription whose `customer_id` starts `cus_` is billing-managed. If its plan is below the target it is reported red (`subscription.billing_managed`) and never written, so the tool never fights the webhook.
- **R6. The `data_region` fix is scoped to the root's two orgs.** The general default at private/account/src/services/org.service.ts:149 is a separate product defect. It is filed as a follow-up worklist item, not fixed here.
- **R7. More than one owned non-partner org is refused.** If the root user owns more than one non-partner org in a region, the region reports red `personal_org.ambiguous` with the id prefixes. Nothing is written there until the operator names the org (a `personal_org.name` key, added then).

## Design

### 1. The grants, by name

| Grant | Desired (config) | Resolved per region by | Written by |
|---|---|---|---|
| Admin | `role: root` | user = exact `ROOT_EMAIL` match | `userService.update(id, {role:'root'})`, as sign-in does |
| Personal org region | `data_region` = the target's own region | the one org with `owner_user_id = user` that has no partner_profiles row and is not the partner id | new `orgService.setDataRegion` |
| Console plan | `plan: BUSINESS`, `status: active` | the org's primary subscription by `customer_id`, ranked as executor_orgs ranks it | `subscriptionService.updateSubscription` (blob re-signed) |
| Console store | present | config_stores row of the personal org with the passphrase | never written; operator item |
| Partner org | `name: Rediacc`, `data_region` = region | deterministic id `uuidv5(NS, "root-grants/partner/" + userId)` | `orgService.createOwnedOrg(..., {orgId})` |
| Partner profile | `status: active`, `tier: registered` as a floor | partner_profiles by that org id | insert as approve does; `partnerService.reactivate`; `partnerService.setTier` only when below the floor |
| Partner member | `partner_role: admin` | partner_members by (org, user) | insert as approve does, or a role update |

Plan and tier are floors. A higher plan (ENTERPRISE) or a higher tier stays as it is. The namespace UUID `NS` is a constant in private/account/src/types/root-grants.ts and in .ci/rediacc_ci/ops/root_grants.py, held equal by P1.

### 2. The committed config: .ci/config/root-grants.json

```json
{
  "$comment": ["Desired grants for the root email, by name. Ids are resolved per region at run time. The email itself is ROOT_EMAIL in bws and is never committed."],
  "version": 1,
  "user": {"email_secret": "ROOT_EMAIL", "role": "root"},
  "personal_org": {"plan": "BUSINESS", "status": "active"},
  "partner_org": {"name": "Rediacc", "tier": "registered", "partner_role": "admin", "status": "active"},
  "console": {"config_store": "operator"},
  "targets": [
    {"id": "edge-eu", "kind": "edge", "region": "eu", "data_region": "eu"},
    {"id": "edge-us", "kind": "edge", "region": "us", "data_region": "us"},
    {"id": "edge-asia", "kind": "edge", "region": "asia", "data_region": "asia"},
    {"id": "bench-eu", "kind": "bench", "region": "eu", "data_region": "eu"},
    {"id": "bench-us", "kind": "bench", "region": "us", "data_region": "us"},
    {"id": "bench-asia", "kind": "bench", "region": "asia", "data_region": "asia"}
  ]
}
```

The loader refuses each of these, with rc 2 and the key named:
- a `kind` other than `edge` or `bench` (so `stable` is refused by name, and no `enterprise.*.toml` config is ever resolved);
- a region absent from regions.json, or a bench region whose `bench.deployable` is not true;
- a `data_region` that differs from its target's region;
- a plan outside the admin enum;
- a tier outside the tier enum;
- a `partner_role` other than `admin`.

### 3. Why a route (R1), and where SQL stays

- **Writes:** only through `POST /admin/root-grants/apply` on the target's own Worker. That runs the services in Design 1, the same code paths sign-in, `PUT /admin/subscriptions/:id` and the partner approve already run.
- **Reads:** one SELECT batch (`READ_SQL` in root_grants.py) through `wrangler d1 execute --remote --json --file <0600 temp>`. It reads the user row matched by email, owned orgs, memberships, the primary subscription candidates, partner rows, config store presence (never the value) and the block flag.
- **The bookmark:** `wrangler d1 time-travel info`. It is a read.

### 4. Wire contract (fixed here so S1 and C1 run in parallel)

All paths are under `/account/api/v1`. Errors use the existing `{error, code}` shape.

| Method and path | Auth | Body / answer |
|---|---|---|
| `POST /admin/root-grants/plan` | `rootAuth`, root | body `Desired`; 200 `Report` with `applied:false`; writes nothing |
| `POST /admin/root-grants/apply` | `rootAuth`, root, `requireElevated()` | body `Desired`; 200 `Report` with `applied:true`; a token session counts as elevated |

`Desired` is a strict zod object, also in private/account/src/types/root-grants.ts:

```ts
{ role: 'root',
  personalOrg: { plan: PlanCode, status: 'active' },
  partnerOrg: { name: string(1..120), tier: PartnerTier, partnerRole: 'admin', status: 'active' },
  dataRegion: string }
```

The route refuses these:
- 400 `DATA_REGION_MISMATCH` when `dataRegion` differs from `envConfig.region`;
- 409 `ROOT_EMAIL_UNSET` when `envConfig.rootEmail` is unset.

`Report` has this shape:

```ts
{ region,
  user: {state:'present'|'absent', idPrefix?},
  actions: [{code, subject:{kind, idPrefix}, from?, to?}],
  skipped: [{code, reason}],
  operator: [{code, subject, where}],
  applied }
```

- Every id is cut to its first 8 characters. No email appears.
- Action codes are `role.promote`, `org.data_region`, `subscription.raise`, `partner.org_create`, `partner.profile_create`, `partner.profile_activate`, `partner.tier_raise`, `partner.member_add` and `partner.member_role`.
- Skipped codes are `user.absent`, `personal_org.absent`, `personal_org.ambiguous`, `subscription.absent`, `subscription.billing_managed` and `console.blocked`.
- Operator codes are `config_store.missing` (where `/account/config-storage`).
- An apply writes one event, `root_grants.applied` (source `account-root`, the action codes in `data`), plus the events the called services already write. root.ts gets a title and description for `root_grants.applied` beside the `root_token.*` cases (private/account/src/routes/root.ts:903, :951).

### 5. The planner, and the never list

`planGrants(snapshot, desired)` is a pure function in root-grants.service.ts that both routes call. `plan()` in root_grants.py is its Python mirror over READ_SQL rows; P1 pins the two equal. Apply runs the actions in this order: role, personal org region, subscription, partner org, profile, member. Each step re-checks its own precondition before writing, so a crashed apply finishes on the next run, and a second run reports zero actions.

Never:
- create a user (an absent email gives `user.absent`, "absent, skipped", rc 0);
- read or write another user's rows (selection is the exact email; P1 fixtures include near-miss emails);
- create a personal org (sign-in provisions it);
- write a config store;
- lower a plan or tier;
- delete or deactivate any subscription;
- write a `cus_` subscription;
- unblock a console;
- resolve a stable target or an enterprise config;
- apply before the bookmark is recorded;
- print an email, token, seed or full id.

### 6. The tool: `rediacc_ci.ops.root_grants`

```
PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants [--target <id>|all] [--dry-run|--apply] [--json]
```

- **Defaults:** `--target all` and `--dry-run`. A bare run is the health check's command.
- **Phases.** Each runs under exactly one existing or new bws consumer, re-executed with a scrubbed child environment so `bws_env exec` never meets a name that is already bound:
  1. **`read`** runs under the new consumer `root-grants` (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, ROOT_EMAIL). It runs READ_SQL, then `plan()`, and prints one line per target, for example `edge-us user=35eb… actions=3 skipped=0 operator=1`, then one line per action.
  2. **`bookmark`** (apply only, same consumer) records `BOOKMARK <database> <bookmark>` before any POST. A failed bookmark exits 2 with nothing written. A target with zero planned actions takes no bookmark and makes no POST.
  3. **`post`** (apply only):
     - edge runs under `root-login` and calls `open_token_session("edge", region).post("/admin/root-grants/apply", desired)`;
     - bench runs under `bench-login-<region>` and uses `AccountApi(bench origin)`: sign-in with password and TOTP, `login_bench.elevate`, then the same POST.
     - A missing token or bench seed exits 2 and names the remedy: the mint page `<region>.rediacc.cloud/account/admin/root-tokens`, or `npm run login:bench -- --region <r>`.
  4. **`verify`** re-runs `read`. Remaining actions after an apply give exit 1.
- **Exit codes:** 0 when no target has an action or a red skip (absent users and AMBER operator items allowed); 1 on drift or a red skip; 2 on setup, refusal or an unreadable D1.
- **Output:** the server `Report` is printed through the same formatter as the dry-run, so the two read alike. A sentinel test asserts that no bws value reaches stdout, stderr or argv.

### 7. Ops-health check

- `SUBPROCESS_CHECKS["root-grants"] = ("root-grants", "rediacc_ci.ops.root_grants")`, TTL key `root_grants` = 360 minutes in .ci/config/ops-health.json and `DEFAULTS`.
- rc 1 (red) on grant drift in any target. rc 0 with `AMBER operator: config_store.missing <target>` lines when only stores are missing. rc 2 when a D1 cannot be read.
- The source posts to the alerter as `local-root-grants`.
- The check never applies anything. The remedy line names `--apply --target <id>`.

### 8. The immediate application

Expected actions from the 2026-11-17 read:
- **edge-eu:** `partner.org_create`, `partner.profile_create`, `partner.member_add`.
- **edge-us and edge-asia:** `subscription.raise` (COMMUNITY inactive to BUSINESS active), `org.data_region` (eu to us or asia), the three partner actions, and the operator item `config_store.missing`.
- **Benches:** whatever their own D1s show. `user.absent` is a valid outcome there.

Order:
1. Benches.
2. Production edge eu, then us, then asia, each with its bookmark recorded in the tick evidence.
3. The operator creates the us and asia config stores in the portal.

### 9. Out of scope

- The general `data_region` default (R6, follow-up worklist item).
- Minting the eu root token (PLAN-root-api-token OP1).
- Any change to sign-in promotion.

## Not verified (load-bearing; each owner re-checks)

- U1. The CLOUDFLARE_API_TOKEN in `deploy-proxy` can read the bench D1s `account-bench-us` and `account-bench-asia` as well as production. deploy-proxy-bench-eu uses the same entry name for account-bench. C1 confirms with one read per target.
- U2. The eu subscription's `type` and `expires_at`. S1 reads the eu row (SELECT only) before fixing whether `subscription.raise` also sets `expiresAt: null` when the row is past expiry. The default sets plan and status only.
- U3. The root user exists on the us and asia benches. If not, those targets report `user.absent`, which is correct.
- U4. The bench config store that `login_bench` step 5b creates carries `server_recoverable_org_passphrase`. If it does not, the bench AMBER item stays an operator item.
- U5. The production root user's TOTP seed is ROOT_TOTP_SEED (PLAN-root-api-token U3).
- U6. `createOwnedOrg` callers: only partner approve and the org-create route pass through it today. The new optional `{orgId}` argument leaves both unchanged.

## Tasks

### Wave 1: two writers, file-disjoint, against Design 4

- [ ] S1 [writer] Account server. Scope:
  - the route file `root-grants.ts`, mounted at `/admin` in index.ts, with both handlers on `rootAuth()` and apply also on `requireElevated()`;
  - the service `RootGrantsService` with `planGrants`, wired in container.ts;
  - the types and DTOs through `responds()`;
  - `orgService.createOwnedOrg(..., ids?: {orgId})` and `orgService.setDataRegion`;
  - the `root_grants.applied` humanizer in root.ts.

  Integration tests in `root-grants.test.ts` cover:
  - absent root email: apply writes nothing (full table snapshot equal);
  - near-miss emails (`+tag`, other domain, other case) untouched;
  - partial state completed, then a second apply with zero actions and an equal snapshot;
  - an org at the deterministic id without a profile gains a profile and a member, and no second org;
  - ENTERPRISE and `cus_` rows unchanged;
  - signed blob shows BUSINESS after the raise;
  - config_stores count unchanged and the `config_store.missing` item reported;
  - `DATA_REGION_MISMATCH` 400;
  - 401 with no session, 403 for a customer, 403 `reauthRequired` on an unelevated apply while plan answers 200.

  Accept: `(cd private/account && npx vitest run tests/integration/root-grants.test.ts tests/integration/admin-root-token-coverage.test.ts tests/integration/partner-application.test.ts tests/integration/root-console-block.test.ts)` rc 0, `(cd private/account && npm run typecheck)` rc 0, and `npm run -s check:ci-account-layer-isolation` rc 0.
- [ ] C1 [writer] Ops tool and config. Scope:
  - .ci/config/root-grants.json as in Design 2;
  - root_grants.py with the loader refusals, READ_SQL through a 0600 `--file`, `plan()`, the phases in Design 6 and the formatter;
  - the `root-grants` consumer in secret-supply.json, plus env-manifest and python-env-registry entries if their gates ask.

  test_ops_root_grants.py runs on sqlite built from the drizzle migrations behind a fake `wrangler` on PATH and a fake POST. It covers:
  - every loader refusal, including `stable` and an enterprise config;
  - absent user printing `absent, skipped` with rc 0;
  - partial grants;
  - a second run with zero actions;
  - a near-miss email untouched;
  - a dry-run that writes nothing: no non-SELECT SQL, no bookmark, no POST;
  - apply calling the bookmark before the first POST, and refusing on a failed bookmark;
  - verify exiting 1 on leftover actions;
  - a sentinel email, token and seed absent from output and argv.

  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_root_grants.py` rc 0, `npm run -s check:ci-secret-supply` rc 0, `npm run -s check:ci-env-manifest` rc 0, and `npm run -s check:ci-python-types` rc 0.

### Wave 2: after S1 and C1 land

- [ ] P1 [writer] Parity test `root-grants-parity.test.ts`. For four fixtures (absent, partial, complete, near-miss) it runs `READ_SQL` from Python on the test sqlite, feeds the rows to Python `plan()`, and requires the same action list as `POST /admin/root-grants/plan`. It also requires Python `uuid5` and the TS derivation to give the same partner id for a sample user id. A control mutates one action code and must fail. Accept: `(cd private/account && npx vitest run tests/integration/root-grants-parity.test.ts)` rc 0.
- [ ] H1 [writer] Ops-health check as in Design 7. test_ops_health.py adds: the check registered under its profile, rc 1 mapped to red, rc 0 with AMBER lines kept green and the AMBER text in the cached detail, and rc 2 mapped to unknown. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_health.py` rc 0, and `PYTHONPATH=.ci python3 -c "from rediacc_ci.ops import ops_health as o; assert 'root-grants' in o.SUBPROCESS_CHECKS"` rc 0.
- [ ] D1 [writer] Docs: one private/account/CLAUDE.md paragraph on `/admin/root-grants/*` and the never list, and the tool's module docstring with usage, phases, profiles and exit codes. Accept: `grep -c "root-grants" private/account/CLAUDE.md` prints at least 1, and `npm run -s check:ci-prose-style` rc 0.

### Live: bench first

- [ ] LP-bench [live] Fresh bench receipt after S1 reached the eu bench through `deploy_bench --region eu`. Local-route: deploy-bench -- deploy_bench pushes the branch's account Worker to the eu bench from this machine.
  Accept: live-proof bench account-smoke
- [ ] LB-eu [live] Apply on bench eu after `npm run login:bench -- --region eu`, then the dry-run shows no drift. Local-route: deploy-bench -- the route reaches the eu bench by deploy_bench and the tool runs from this machine. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-eu --apply` rc 0 printing `BOOKMARK account-bench`, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-eu` rc 0.
- [ ] LB-us [live] The same on bench us after `deploy_bench --region us` and `npm run login:bench -- --region us`. Local-route: deploy-bench -- the route reaches the us bench by deploy_bench and the tool runs from this machine. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-us --apply` rc 0, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-us` rc 0.
- [ ] LB-asia [live] The same on bench asia after `deploy_bench --region asia` and `npm run login:bench -- --region asia`. Local-route: deploy-bench -- the route reaches the asia bench by deploy_bench and the tool runs from this machine. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-asia --apply` rc 0, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-asia` rc 0.

### Live: production edge (standing ruling ASKED:2026-11-16T05:39Z)

- [ ] LE0 [live] The edge Workers serve the route in all three regions. Accept: `for r in eu us asia; do curl -s -o /dev/null -w '%{http_code}\n' -X POST https://$r.rediacc.cloud/account/api/v1/admin/root-grants/plan; done` prints 401 three times.
- [ ] OP-us [operator] The operator signs in at https://us.rediacc.cloud/account/admin/root-tokens, steps up with TOTP, mints `agent-root-us` and pastes it into the Bitwarden entry ROOT_API_TOKEN_US. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target edge --region us --check` rc 0.
- [ ] OP-asia [operator] The same at https://asia.rediacc.cloud/account/admin/root-tokens into ROOT_API_TOKEN_ASIA. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target edge --region asia --check` rc 0.
- [ ] LA-eu [live] Apply on edge eu, after PLAN-root-api-token OP1 and LP0, with the bookmark quoted in the tick. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-eu --apply` rc 0 printing `BOOKMARK account-eu` and `partner.org_create`, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-eu` rc 0.
- [ ] LA-us [live] Apply on edge us, after OP-us, with the bookmark quoted in the tick. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-us --apply` rc 0 printing `BOOKMARK account-us` and `subscription.raise`, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-us` rc 0 with only the `AMBER operator: config_store.missing` line.
- [ ] LA-asia [live] Apply on edge asia, after OP-asia, with the bookmark quoted in the tick. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-asia --apply` rc 0 printing `BOOKMARK account-asia` and `subscription.raise`, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-asia` rc 0.
- [ ] OS-us [operator] The operator creates the personal org's config store at https://us.rediacc.cloud/account/config-storage. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orgs verify --target stable --region us --org 35eb74dc` rc 0, and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-us` rc 0 with no `AMBER` line.
- [ ] OS-asia [operator] The same at https://asia.rediacc.cloud/account/config-storage. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orgs verify --target stable --region asia --org 35eb74dc` rc 0, and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target edge-asia` rc 0 with no `AMBER` line.
- [ ] LH [live] The ops-health check is green across all six targets. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.ops_health refresh --force --check root-grants` rc 0, with `root-grants` green in `.ci/cache/ops-health/state.json`.
- [ ] F* [writer] Fix-forward boxes, opened under this plan for each claim a live box disproves, each owning only the file the claim names. Accept: the failing live box's command rc 0.
