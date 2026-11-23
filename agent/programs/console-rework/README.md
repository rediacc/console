# console-rework

The account web Console (`/account/console/*`) reworked on top of the CLI contract it already renders from: per-command severity, summaries and preview metadata in the contract; severity-tiered confirmation with server-side step-up; audit of every console action in R2; a server-side run index shown as a block stream; an own-core command line with recipes and real shell completions; a corrected information architecture; step-driven animations; and an in-console AI assistant on customer keys or enterprise credits, running in the org container under remote-mcp's decision function.

Planned in session `9b22c347` on 2026-11-23, branch `1121-1`, from an external brief whose code claims proved largely stale (`01-verified-context.md` section 6). One plan per PR (C2), no feature flag (C3).

## Read order

1. `02-decisions.md`: the operator rulings C1 to C41. Binding; cited by id.
2. `01-verified-context.md`: the findings with `file:line` evidence, read against the tree on 2026-11-23. Each citation is a hypothesis a writer re-reads before relying on it.
3. The plans, in the order below.

## The plans

| # | Plan | Box prefix | Delivers | Depends-On |
|---|---|---|---|---|
| 1 | `agent/plans/PLAN-console-contract-semantics.md` | `CS` | summaries in 13 locales, severity on every command, preview polarity, error origin, contract version injection, lazy contract import, `repo prune` severity, the MCP `reveal` drop (C5-C8, C24) | none |
| 2 | `agent/plans/PLAN-console-confirm-stepup.md` | `CF` | amber and red dialogs, typed name, server-side step-up at `/console/exec`, passkey elevation, org minimum, console reveal, production popup (C11-C14) | 1 |
| 3 | `agent/plans/PLAN-console-audit-r2.md` | `AU` | R2 audit objects, nightly compaction with a hash chain, paid visibility, admin "show from" date, retention and downgrade grace (C15-C20) | 2 |
| 4 | `agent/plans/PLAN-console-run-index.md` | `RI` | server run index, keep-awake, block-stream panel, status-bar pills, Jobs page, server history (C21, C22, C26) | 1 |
| 5 | `agent/plans/PLAN-console-command-line.md` | `CL` | own core in packages/shared, plain command box in the panel, above forms and in Cmd+K, recipes, `rdc completion`, keyboard and IME tests (C23-C28) | 1, 4 |
| 6 | `agent/plans/PLAN-console-ia.md` | `IA` | Variant A labels, runs-where badges and grouping, grouped reference, terminal-only pages, landing (C9, C10) | 1 |
| 7 | `agent/plans/PLAN-console-animations.md` | `AN` | step-driven animations, indeterminate fallback, reduced motion, the dead `animate-in` classes (C29) | 4 |
| 8 | `agent/plans/PLAN-console-ai-providers.md` | `AP` | provider profiles in the encrypted config, presets, tool-calling test, the loop host in the executor, egress (C30, C31, C41) | 1, rmcp-decide, rmcp-agent-grants |
| 9 | `agent/plans/PLAN-console-ai-assistant.md` | `AI` | action timeline, simple view, Ask, Auto and Skip with the judge, chips, branching, assistant-ui, microphone engines (C33-C38) | 4, 5, 8 |
| 10 | `agent/plans/PLAN-console-ai-credits.md` | `AC` | Unified Billing gateway, Workers AI tier, per-org ledger, every guard, admin grants, usage view (C32) | 8 |
| 11 | `agent/plans/PLAN-console-ai-feedback.md` | `AF` | feedback offers on Rediacc-origin failures, AI-written text, per-user and owner settings (C39) | 1, 9 |
| 12 | `agent/plans/PLAN-console-ai-in-pages.md` | `AX` | "Ask about this" bars, inline suggestions, background tasks feeding the timeline (C34) | 9 |

Plans 2 and 4 both edit private/account/drizzle/**, private/account/src/db/schema.ts and private/account/src/routes/console.ts, and neither depends on the other: they ride separate PRs, and `block_plan_concurrency` refuses concurrent writers on the shared files. `Owns:` in each plan header is the authoritative list; the column above is a summary. Where two plans touch one file, the later plan in `Depends-On` order owns the edit after the earlier one lands.

## Neighbours

- **remote-mcp** (`agent/programs/remote-mcp/`): plans 8 to 12 depend on `PLAN-rmcp-decide.md` and `PLAN-rmcp-agent-grants.md` (C40). `PLAN-rmcp-policy-record.md` moves the policy into its own record and edits `Permissions.tsx` and `console.json`; plan 2's org step-up minimum is a policy field and lands after that record exists. Remote-mcp D28 (policy edits need 2FA and an elevated session) and D31 (policy history as audit events) are reused, not rebuilt.
- **PLAN-tooling-code-reduction.md** CR2: every new gate in this program is declared in the CR2 gate header grammar, so gate-wiring boxes depend on CR2.
- **PLAN-d1-scaling.md**: C18 supersedes its D1-at-90-days audit ruling for console audit; plan 3 states the change and leaves plain CLI telemetry in Analytics Engine.
- **PLAN-account-sidebar-redesign.md**: its rulings stand (C9).
- **PLAN-rdc-feedback.md**: plan 11 reuses its endpoint and report shape.
