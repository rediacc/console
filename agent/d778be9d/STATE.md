## SESSION d778be9d 2026-11-12T13:21:49Z

# STATE d778be9d (2026-11-12, context epoch 27 hand-over)

## Big pieces
- PR 605 (branch 1104-1): ~166 unpushed commits, all review rounds and ci:quick repairs landed. vm:check bvys7h857 running on tree with the portal scope fix (last VERIFIED earlier at 7bcb3e070fc5; the 1112n run failed only A1.2 api-tokens-scopes, since fixed in d47b337710). Before the push: run `npm run ci:quick` (last reds all fixed on the tip; cli-examples green after P2 removal; lane-budget green), then `worklist.py --review-commit d778be9d`, then `TURBO_PUSH_REASON='red-fix: ci reds and review waves' git push origin 1104-1`, then `.ci/scripts/ci/ci-trace.py --wait`.
- PLAN-enterprise-tenants.md (QUEUE entry 68, epic c01fbf97): ticked Q0 E1 E2 E3 P1 L1 C3 C4 C5 C6 C9 C10 C12 P2(superseded by C7). Rulings in plan: R5-R8, single install path (rdc server install only), offline licence request/response + long cert (ASKED:2026-11-12T13:07Z), prerequisites-only packages + template re-apply refusing local edits + dedicated bench lab subscription (ASKED:2026-11-12T13:00Z), every plan may self-host (gates removed c167e0ddc9).
- Production fixes landed, deploy owed: delegation renew path /account/api/v1/delegation/renew (8ddacdc79a) -> deploy account Workers eu/us/asia via the deploy skill; signer probe + template LICENSE_SIGNER binding -> deploy signer-bench-eu then deploy_bench, then V1.

## Owed ticks
- C7 c3e44c99 when its writer lands (lease agent-ae96292538e907a06): land with `./run.sh worktree land <id>`, then `--ticks`, investigate (40+ char note, two pointer kinds: commit + fileline with an extension) and plan-tick.
- V1 49c93654 after the bench deploy and rerun.

## Delegated
- ae96292538e907a06 | #af61285a, #1ff32880 | packages/cli/src/commands/server.ts, services/server/**, utils/server-prompts.ts, machine/register.ts, services/machine/add-existing.ts, CLI locales | accept: `cd packages/cli && npx vitest run src/commands/__tests__/server src/services/server`, `npx tsc --noEmit -p packages/cli/tsconfig.json`, `npm run check:ci-cli-contract`, `npm run check:ci-i18n-hashes`, `npm run check:cli-examples`, `./rdc.sh server install --help`. Brief: C7 rdc server install|status|upgrade|backup|licence, existing-machine first, prompts, licence via POST /delegation/issue / --licence free / --cert, optional --bws-project (ours), owned-zone DNS only, recovery bundle.

## Next action
1. When C7 reports: spot-check, land, run its accept commands on the landed tree, tick C7, collect the tree.
2. Run ci:quick + vm:check --changed; fix any red with lease writers; then review-commit and push PR 605; ci-trace --wait.
3. After the push: `bws_env exec --profile deploy-signer -- python3 -m rediacc_ci.deploy.deploy_signer --target bench-eu`, `python3 -m rediacc_ci.ops.deploy_bench`, then `bws_env exec --profile enterprise -- ./run.sh enterprise proof signer --bench` (V1); deploy account Workers for the renew fix (deploy skill; eu/us/asia allowed by operator rulings).
4. Next enterprise boxes: C11 (bundle/offline install, after C7), C8 (renet release via release:local then machine setup hostinger), LD1, V3, V4, T1 (acme.rediacc.cloud --unlisted, owner muhammed@rediacc.com, 10 GB, bws enterprise project must be created first), HO1 via `./rdc.sh --config eu-bench server install hostinger ...`.
5. Open operator questions to ask when their boxes come up: a public VPS for CL3, whether the ghcr on-prem image is public (Q11).
