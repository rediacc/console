# PLAN: Orphan recovery: find every volume and fork the hosted executor created without a saved config record, and settle each one

Status: approved -- operator ruling 2026-11-20 in session 6c87d631 ("approved but do not promote", agent/programs/remote-mcp/02-decisions.md D51); not in QUEUE.md ## Promoted until the operator promotes it
Depends-On: PLAN-rmcp-writeback.md#WB0, PLAN-rmcp-executor-hardening.md#EHOP2 -- the sweep is final only once WB0 stops new orphans from appearing; OR-OP-L1 runs on the on-premise harness and scenario runner EHOP2 ships
Owner: 6c87d631
Priority: P1 -- every proxied `repo create` or `repo fork` before WB0 may have left an image on a host with no config entry and no key
Concurrency: parallel -- one writer for the ops tool (OR1, OR2) and one for the CLI listing (OR3); the sweep boxes run after both land
Owns: agent/plans/PLAN-rmcp-orphan-recovery.md, .ci/rediacc_ci/ops/executor_orphans.py, .ci/rediacc_ci/tests/test_ops_executor_orphans.py, .ci/config/secret-supply.json, packages/cli/src/commands/repo-admin-orphan.ts, packages/cli/src/services/repo/orphan-repos.ts, packages/cli/src/services/repo/__tests__/orphan-repos-executor.test.ts, packages/cli/src/i18n/locales/*/cli.json, .ci/rediacc_ci/testrun/onprem_suites/orphan.py, .ci/rediacc_ci/tests/test_onprem_suite_orphan.py
Live-Proof: bench -- the tool and the listing are proved against the eu bench first (OR-L1); the production test orgs of D32 are swept afterwards with the same tool (OR-L2); detection against an on-premise account server is proved locally in OR-OP-L1
Updated: 2026-11-20
First-Seen: 2026-11-20

## Ask

Every encrypted image, fork or VM the hosted executor created while its config writes were discarded is found, matched to the account audit trail, and settled: deleted when no key exists, or re-registered when the record can be rebuilt. The operator confirmed every config store in the three regions belongs to Rediacc (D32), so the sweep covers all of them without customer contact.

## Context (read 2026-11-20 against the tree; a writer re-reads each citation before relying on it)

1. **The defect.** The container tier keeps config writes in request memory (`packages/cli/src/services/core/request-context.ts:115`); a proxied `repo create` registers the credential (`packages/cli/src/commands/repo-create-delete.ts:236-239`) before the host job (`:311`), so the image exists while its key died with the request.
2. **An orphan listing exists.** `packages/cli/src/commands/repo-admin-orphan.ts:2` (`repo admin orphan {list,delete}`, worklist #48d790e1), built on `classifyMachineRepos` (`packages/cli/src/services/repo/orphan-repos.ts:59`), which marks an image `orphaned` or `protected` with a reason (`:25-26`, `:88-93`). It reads one machine at a time.
3. **The executor audits each command.** `packages/cli/src/services/serve/audit.ts` maps a function name to an event type, falling back to `cli.command`, and sends it with `onBehalfOfTokenId`; the account stores it in `event_log` (`private/account/src/db/schema.ts:609-622`: `type`, `source`, `user_id`, `org_id`, `data`).
4. **A read-only D1 tool pattern exists.** `.ci/rediacc_ci/ops/executor_orgs.py` reads a target's D1 through `wrangler d1 execute --remote --json`, prints ids by 8-character prefix, and re-executes under `bws_env exec --profile` when credentials are missing.
5. **The inventory.** The 2026-11-20 read found 9 config stores: eu 2 (the operator's, the one non-Rediacc-domain store owner), us 4 (three `live-console-edge-us-*`, the operator's), asia 3 (two `live-console-edge-asia-*`, the operator's). Every store has one member and one slot (agent/programs/remote-mcp/02-decisions.md D32).
6. **On-premise audit events live elsewhere.** An on-premise install keeps `event_log` in the Node account server's SQLite database (`private/account/src/entry/on-premise.ts:2-21`), not in D1, so a tool that reads only through `wrangler d1` cannot see it; a daemon executor audits through the same `audit.ts` path, so the events have the same shape.

## Decisions

D49 and D50 (detection works against an on-premise account server too), D3 (fixed in this program), D6 (an orphan is the visible cost of memory holding the only copy of a record), D32 (every store is Rediacc's own; migration and cleanup are manual and need no customer contact).

## Design

1. **`executor_orphans` ops tool.** `PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orphans list --target bench|stable [--region R]` reads `event_log` rows whose `source` is the executor and whose function is `repository_create`, `repository_fork` or `machine_provision`, and prints org prefix, machine, repo name, GUID (when the event data carries it) and time. Read-only; ids printed by prefix as in `executor_orgs`.
2. **Executor-origin hint in the CLI listing.** `rdc repo admin orphan list --machine <m> --json` gains `--executor-events <file>`: the tool's JSON output joins on GUID or name, and a matched orphan's reason becomes `executor-created, config write discarded` with the event time.
3. **Settling rule.** An orphan whose credential cannot be recovered is deleted with `rdc repo admin orphan delete <guid> --machine <m>`. A fork orphan whose parent is in the config is re-registered (same credential as the parent, new GUID from the image) instead of deleted. A provisioned VM with no machine entry is deprovisioned through the provider.
4. **Report.** Each region's result is recorded in this plan's `## Outcome`: orphans found, matched to events, deleted, re-registered, and any unmatched image (an orphan with no executor event is reported, not deleted, because another cause produced it).
5. **On-premise source.** `executor_orphans list --target onprem --env .onprem/stack.env` reads the same rows read-only from the on-premise account server's SQLite file (`--sqlite <path>`, the path the stack env names; the on-premise route factory has no admin routes, `private/account/src/entry/on-premise.ts:4-5`, so no HTTP read is added), and prints the same JSON lines; the `orphan` on-premise suite plants one orphan by deleting a fresh repo's config entry through the daemon, then requires the tool and `repo admin orphan list --executor-events` to name it.

## Boxes

- [ ] OR1 [writer] `executor_orphans` tool (Design 1) with its `secret-supply.json` consumer. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_executor_orphans.py` rc 0, the test running the tool's SQL against a seeded sqlite with executor and non-executor events and a control row that must not appear.
- [ ] OR2 [writer] Tool output contract: one JSON line per event with `org`, `machine`, `repo`, `guid`, `at`, `function`; `--json` and the human table. Accept: the same pytest file rc 0 with the contract case.
- [ ] OR3 [writer] `--executor-events` join in `repo admin orphan list` (Design 2), i18n reason in 13 locales. Accept: `(cd packages/cli && npx vitest run src/services/repo/__tests__/orphan-repos-executor.test.ts)` rc 0: a matched orphan carries the executor reason, an unmatched one keeps its old reason, a protected image stays protected.
- [ ] OR-OP1 [writer] On-premise source for the tool and the `orphan` suite (Design 5). Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_executor_orphans.py .ci/rediacc_ci/tests/test_onprem_suite_orphan.py` rc 0, with an on-premise SQLite fixture and a control where the planted orphan is absent and the suite must fail.
- [ ] LP-bench [live] Build the CLI from this tree and read the subscription through the eu-bench config, so OR-L1 lists orphans with the listing this branch builds.
  Accept: live-proof bench cli-bench
- [ ] OR-L1 [live] eu bench: create one orphan on purpose with a pre-WB0 build (or by deleting a fresh repo's config entry), run the tool and the listing, settle it by Design 3. Accept: the transcript recorded in `## Outcome` and `rdc repo admin orphan list --machine <m>` printing no orphan afterwards. Local-route: deploy-bench, bench-cli -- the eu bench account Worker holds the event and the CLI from this tree lists and deletes on a bench machine
- [ ] OR-L2 [live] Production sweep of the 9 stores in D32: the tool per region against `stable`, the listing per machine of each store's config, settling by Design 3, recorded per region in `## Outcome`. Accept: for every machine of every store, `rdc repo admin orphan list --machine <m>` prints no executor-matched orphan, and every unmatched image is listed in `## Outcome` with its machine and GUID. Local-route: bench-cli -- the CLI from this tree runs each store's own config against its machines; the D1 read uses the read-only tool from this checkout
- [ ] OR-OP-L1 [live] On-premise stack: `onprem_stack up --machines vm`, then the `orphan` suite. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_scenarios --suite orphan` rc 0, transcript recorded in this plan. Local-route: e2e-local -- the on-premise stack and its ops VMs run on this machine through the harness of PLAN-rmcp-executor-hardening.md

## Docs touched

None on the public site: the listing flag is described by its `--help`. `docs/agent-reference/cli.md` gains one line on `--executor-events`, edited by PLAN-rmcp-docs.md.
