# remote-mcp

A hosted, per-user MCP endpoint that agents use with no local install, and every defect the investigation behind it found: config writes the hosted executor drops, a policy any member can rewrite, guards that differ between the local and remote paths, `REDIACC_ALLOW_CONFIG_EDIT`, executor auth gaps, and stale docs.

Planned in session `6c87d631` on 2026-11-20, branch `1104-1`. The ten plans ship in one PR (D4).

## Read order

1. `02-decisions.md`: the operator rulings. Binding; cited by id.
2. `01-verified-context.md`: the findings with `file:line` evidence, read against the tree on 2026-11-20. Each citation is a hypothesis a writer re-reads before relying on it.
3. `03-external-research.md`: the MCP spec (2026-07-28), client support, and Cloudflare facts, with sources.
4. The plans, in the order below.

## The plans

| # | Plan | Box prefix | Owns (summary) | Depends-On |
|---|---|---|---|---|
| 1 | `agent/plans/PLAN-rmcp-writeback.md` | `WB` | executor config write path: `packages/cli/src/services/core/request-context.ts`, `adapters/config-file-storage.ts`, `services/config/synced-write.ts`, `services/serve/{server.ts,container-config.ts,audit.ts,job-poll.ts,job-routes.ts}`, `workers/proxy/src/egress.ts`, account `routes/configs.ts` write-chain parts, `services/config.service.ts` executor-token parts | none; box `WB0` (the stop-gap, D5) is first |
| 2 | `agent/plans/PLAN-rmcp-policy-record.md` | `PR` | the separate policy record: `packages/shared/src/policy/*`, `packages/shared/src/config-schema/{schemas,sensitivity}.ts` policy parts, account policy route/service/schema/migration, `private/account/web/src/pages/console/{Permissions,ConfigEditor}.tsx`, `components/console/PolicyRuleEditor*`; key slots folded in by D36: password slots removed (`packages/shared/src/config-crypto/slots.ts`, account slot routes and migration, web enrollment pages, CLI master-password enroll commands), the mandatory recovery kit, the safety net, machine secrets replacing password-enroll, phone-over-QR enrollment; on-premise route check and live box (P-OP1, P-OP-L1); per-config subkeys under the org CEK with envelope v4 (D56, boxes SK*) | none |
| 3 | `agent/plans/PLAN-rmcp-decide.md` | `DC` | one shared decision function and one enforcement point: `packages/shared/src/policy/decide.ts` (new), `packages/cli/src/utils/{agent-guard,grand-env,process-ancestry}.ts`, `services/serve/policy.ts`, `services/serve/command-dispatch.ts`, `services/core/mutation-gate.ts` guard parts, an eslint rule (box D7, the remote parity leg, moved to PLAN-rmcp-remote-worker.md as RW-PAR); cloud versus on-premise parity leg (D8, D-OP-L1) | PLAN-rmcp-policy-record.md (schema) |
| 4 | `agent/plans/PLAN-rmcp-config-edit-removal.md` | `CE` | `REDIACC_ALLOW_CONFIG_EDIT` everywhere: `commands/config/edit.ts`, the override branch of `mutation-gate.ts`, CLI i18n keys in 13 locales, tests | PLAN-rmcp-decide.md |
| 5 | `agent/plans/PLAN-rmcp-executor-hardening.md` | `EH` | `services/serve/{auth.ts,sessions.ts}`, `proxy-client*.ts`, account `routes/proxy.ts` introspect, `middleware/rate-limit.ts`, `workers/proxy/src/ready.ts`, `commands/serve.ts`, device-code token storage; EH8: occupancy readable only by the account Worker (D52), public `/v1/ready` liveness and version only | PLAN-rmcp-writeback.md |
| 6 | `agent/plans/PLAN-rmcp-agent-grants.md` | `AG` | `config_agent_grants` schema and migration, `packages/shared/src/config-crypto/agent-grant.ts` (new), account agent-grant routes and service, `POST /configs/agent-session`, grant UI pages in account web, revocation cascades; grants wrap one config's subkey (D56), exactly one config per grant (D55), 7 days default and 30 at most (D54), rows in the org region's D1 (D58) | PLAN-rmcp-writeback.md, PLAN-rmcp-executor-hardening.md, PLAN-rmcp-decide.md, PLAN-rmcp-policy-record.md#SK1 |
| 7 | `agent/plans/PLAN-rmcp-local-mcp.md` | `LM` | `packages/cli/src/commands/mcp/*`, the shared tool registry module, SDK v2 dependency, `command-metadata.ts` MCP fields, tool-surface coverage gate; D57: the 44 non-proxy tools remote-capable by default, LM10 moves them onto the executor | PLAN-rmcp-decide.md, PLAN-rmcp-writeback.md#WB1, #WB4 |
| 8 | `agent/plans/PLAN-rmcp-remote-worker.md` | `RW` | `workers/mcp/**` (new Worker: transport, OAuth provider, grant resolution, rate-limit DO, revocation), its wrangler files, deploy/CD wiring, DNS, logging guards, the remote parity leg RW-PAR; the runtime-portable handler in `packages/shared/src/mcp-host/` hosted by the Worker and by the Node on-premise entry, database-backed OAuth store and rate limits, the daemon transport, on-premise and air-gapped live boxes (RW-OP0-RW-OP-L2, D48); workers-oauth-provider on both hosts over a SQLite KV adapter on Node, spike RW-OP0 first (D53); per-region Workers with wrong-region refusal (D58) | PLAN-rmcp-agent-grants.md, PLAN-rmcp-local-mcp.md |
| 9 | `agent/plans/PLAN-rmcp-orphan-recovery.md` | `OR` | detection of host volumes and forks with no config record, using `commands/repo-admin-orphan.ts` and account audit events; the sweep of every test org | PLAN-rmcp-writeback.md#WB0 |
| 10 | `agent/plans/PLAN-rmcp-docs.md` | `DO` | `packages/www/src/content/docs/*/` (ai-agents-mcp, ai-agents-safety, ai-agents-overview, ai-agents-claude-code, account-security, proxy-and-executor, on-premise, cli-application, ai-agents-json-output), `.claude/skills/rdc/*`, `docs/DESIGN-CONFIG-STORAGE.md`, `docs/environment-variables.md`, generated tool tables and their gates, threat model, privacy wording, the new `security-model.md` guide with six diagrams under `packages/www/public/img/security-*.svg` (D37, D47), config-storage.md, and the DESIGN-CONFIG-STORAGE.md unlock-method rewrite (D38); on-premise.md gains remote MCP and the daemon executor, the guide notes on-premise differences; security guide covers URL lifetime, single-config scope, subkey blast radius and per-region residency (D54-D56, D58) | every other plan |

The on-premise test harness (local stack, CI lane, air-gapped image) belongs to PLAN-rmcp-executor-hardening.md (boxes `EHOP*`, D49-D50); other plans reference those boxes. `Owns:` in each plan header is the authoritative list; the column above is a summary. Where two plans touch one file, the later plan in `Depends-On` order owns the edit after the earlier one lands.

## Program rules

- **Memory is never the only copy of a record** (D6). An unsaved record fails the operation before any host side effect.
- **One decision function, one enforcement point** (D18): every caller (CLI, local MCP, remote MCP, `--proxy`, web console) reaches `decide()` at command dispatch.
- **Clean break** (CLAUDE.md rule 2): no shims, no deprecation windows, no dual paths.
- **Tests are deliverables**: every plan carries its own test boxes, and the cross-path parity fixture (PLAN-rmcp-decide.md) runs against every surface.
- **Docs ship with the feature** (D7): each plan names the doc pages it changes; PLAN-rmcp-docs.md owns the shared pages and the drift gates.
