## SESSION d778be9d 2026-11-13T05:03:54Z

# STATE d778be9d (2026-11-13 05:05Z, branch 1104-1, PR 605)

## Where things stand
- PR 605 head pushed 61d3034452; ~30 commits unpushed fixing CI run 43360983417 (pytest leaks a3cde3d8/e837c36a/a30f8b4557, Go renet 2dbfd667/8012e0f5, Account E2E b7e661a321) plus account digest/portal-origin fixes (de542e7, 5bcca23), drill TOTP, region-loss step. Push pipeline chain bsetphzlm (vm:check --base 61d3034452, drill backup + backup-onprem, ci:quick) running; push red-fix when green.
- Operator ASKED:2026-11-13T05:02Z: publish branch 1104-1 to public eu/us/asia NOW via `release:local --channel edge --workers-only --branch-release` (shared Workers account-<r> are the edge channel; stable = company Workers via rings), and align stale release docs.

## Delegated
- ac73798df1029219b #a2887f2a: --branch-release in local.py/local_gates.py + guard (RELEASE_ASKED proof), record fields, APP_VERSION <live>+1104-1.<sha8>. Accept: tests + dry run.
- a78111739597f6186 #a2887f2a: align release-process.md, deploy skill, CLAUDE.md Release Channels.
- a715775b6051485a8: list internal-only rdc subcommands (proxy-token etc.) + hide mechanism; answer the operator, then implement.

## Next action
1. Land the branch-release writer (cherry-pick, run its tests), then live: `RELEASE_ASKED=ASKED:2026-11-13T05:02Z PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- npm run release:local -- --channel edge --workers-only --branch-release --regions eu,us,asia` after deploy_bench; read each deploy record; then repair_org_customer_ids per region (#bf47a483); verify Turnstile on www (#5ac354e6) and /notices unread-count route (#a1ecc191 P1); tick.
2. Land the docs writer.
3. Answer the operator's CLI question with the investigator's list and a recommendation; implement hiding.
4. When bsetphzlm is green: review-commit, push red-fix, ci-trace --wait.
5. [?] #8a0b8240 enterprise token lacks R2: DEFAULT widens it (runs ~06:50Z).

## Big pieces
- PLAN-enterprise-tenants.md (C8, C11, LD1, V3, V4, T1, HO1 open); PLAN-enterprise-isolation.md (V1-V11, X1, X2, H1 live); PLAN-onprem-relicence-inbox.md (L1, LP-bench, LP-hostinger).

## Owed ticks
- PLAN-health-checks-local.md#85f55665
- PLAN-proxy-cd-six-targets.md#abe9b4eb
- PLAN-production-key-only.md#6a1ca4a4
- PLAN-enterprise-isolation.md#2878e08d
- PLAN-enterprise-isolation.md#a8892e0c
- PLAN-enterprise-isolation.md#0a6e5712
- PLAN-enterprise-isolation.md#e8b5ad6f
- PLAN-enterprise-isolation.md#6041744e
- PLAN-enterprise-isolation.md#f4b49503
- PLAN-enterprise-isolation.md#0fbd62dc
- PLAN-enterprise-isolation.md#cc583290
- PLAN-enterprise-isolation.md#b343464b
- PLAN-backup-program.md#0a237b2e
- PLAN-backup-program.md#575e0098
- PLAN-backup-program.md#07955f58 -- live-owed: code landed; bench, hostinger or fleet runs close them.
- LP-bench owed: PLAN-licence-expiry-notices 9c610a87, PLAN-account-notices ec915c2d, PLAN-signer-bench-stop-binding-reattach 89d70106 (deploy at head, then --live-proof with nothing committed between).

## Overnight
- Ticked: B1, Terms, licence-expiry L1, account-notices X1/X2, PR red push 61d3034452.
- Found and fixed: sales digest named no org for self-registered subscriptions; cron mails had no portal link in production (PUBLIC_SITE_URL unset everywhere).
