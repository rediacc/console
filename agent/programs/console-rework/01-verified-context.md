# console-rework: verified context

Read against the tree on 2026-11-23 by eighteen read-only agents and spot-checked by the planning session. Each citation is a hypothesis a writer re-reads before relying on it. The external brief this program started from described the deployed app; where it disagreed with the tree, the tree is recorded here and the brief's claim is listed under "Corrections".

## 1. The contract the console already renders from

- **A generated, drift-gated contract exists.** packages/cli/scripts/generate-cli-contract.ts walks the live Commander tree (`cli` from packages/cli/src/cli.ts) and joins packages/cli/src/config/command-metadata.ts, command-planes.ts, command-docs.ts, command-registry.ts and the CLI i18n catalogues, writing packages/shared/src/cli-contract/data/contract.generated.ts, contract.json and `i18n/<lang>.json`. Types live in packages/shared/src/cli-contract/types.ts (`ContractCommand` from line 237, `ContractOption` lines 182-234), the zod schema in validation.ts (non-strict, so added fields break no reader). `check:ci-cli-contract` regenerates and diffs it; `check:ci-command-tree` holds packages/cli/scripts/command-tree.json.
- **231 entries, 228 leaf commands, 22 top-level domains** (three groups also run as commands: `backup retention`, `repo replicate`, `server licence`). The `storage` domain was retired in commit:c6e5863aa1.
- **Readers, by field:** the worker allowlist (private/account/src/routes/console.ts:453, `getCommand`), `rdc --proxy` (packages/cli/src/services/executor/proxy-command.ts), executor dispatch (packages/cli/src/services/serve/command-dispatch.ts:187-277) and policy (packages/cli/src/services/serve/policy.ts), MCP (packages/cli/src/commands/mcp/tool-factory.ts:236-268), redaction (packages/cli/src/services/feedback/redact.ts), and the web console (private/account/web/src/lib/contract-form.ts, components/console/CommandForm.tsx, CommandPalette.tsx).
- **Fields present today:** `destructive` (types.ts:290, set on 27 commands, 138 unannotated), `idempotent`, `agentBlocked` (15 cluster and datastore commands), `grandGuard`, `forkBlocked`, `plane`, `interactive`, `proxyCapable` (96) with `proxyBlockedReason`, `detachable`, option `tier`, `sensitive`, `kinds`, `format`, `examples` (43 commands), `keywords` (46), output hints `{primaryKey, columns}` (12).
- **Missing today:** a short summary (113 of the 231 commands carry a Commander `.summary()`, from 146 source call sites and 136 `descriptionShort` keys in the English catalogue, and the generator exports none of them; `label` exceeds 100 characters on 99 commands, up to 1928 for `repo admin template apply`), severity beyond the boolean, preview polarity, error origin.
- **Version is always `dev`**: `CLI_CONTRACT_VERSION` (contract.generated.ts:7) has no build injection; the executor's 409 `contract_version_mismatch` check (packages/cli/src/services/serve/server.ts:186-197) therefore never fires.
- **Payload:** the contract is statically imported into the main bundle (363 KB minified, 55 KB gzip, measured on workers/account/dist); locale bundles are lazy but carry about 2,600 keys of which about 860 are referenced.

## 2. The web console

- React 19, Vite, react-router 7 (private/account/web/src/router.tsx:269-306), Tailwind 4 with shadcn, plain fetch and hooks. Navigation is one table, `NAV` in private/account/web/src/lib/nav-config.ts:105, labels in `i18n/locales/<lang>/nav.json` and `console.json`; the sidebar redesign landed.
- Landing domain cards all link to the unfiltered list (private/account/web/src/pages/console/Console.tsx:39); the subtitle count is computed.
- The terminal panel is live, not static: private/account/web/src/components/console/CliEquivalent.tsx:21 rebuilds the line from form values.
- The palette ranks on path plus full description and ignores `keywords` (private/account/web/src/components/console/CommandPalette.tsx:242-245).
- No component branches on a command id (private/account/web/src/lib/contract-form.ts:11 forbids it).
- Run is enabled on 69 commands the executor refuses: CommandForm.tsx:130 checks only interactive, config-plane and the session lock, so the 47 non-interactive commands on plane `other` and the 22 machine-plane exclusions keep an enabled Run; `proxyBlockedReason` is English-only in the contract and never shown.
- Leaving a running command page aborts the fetch and writes no history (private/account/web/src/hooks/useCommand.ts:87); browser run history is localStorage capped at 50 entries (private/account/web/src/lib/run-history.ts:4); the job id `useCommand` holds is dropped by CommandPage.
- The Jobs page needs a typed machine name and runs `job list --machine` once (private/account/web/src/pages/console/Jobs.tsx:66).
- The only typed-name dialog is private/account/web/src/components/console/DestructiveConfirm.tsx; a warning tone exists as a token but no warning dialog. The shadcn `animate-in` classes are dead because `tw-animate-css` is not installed.
- The existing Combobox lacks `aria-activedescendant` (private/account/web/src/components/console/Combobox.tsx:175-177).
- Arabic is one of the 13 locales and flips the page to RTL (private/account/web/src/i18n/language.ts:71).

## 3. Running a command, and its safety

- Browser to `/console/exec` (NDJSON) to the worker route (private/account/src/routes/console.ts:444-504) to the per-org container executor `rdc serve` (workers/proxy, packages/cli/src/services/serve/server.ts). The executor prepends `--output json --yes` (packages/cli/src/services/serve/command-dispatch.ts:284-305), so the console's dialog is the only confirmation, and refuses undeclared flags (:202-215).
- Gap: `repo prune --apply` deletes with no console confirmation because `destructive` is unset on it; harmless previews still demand a typed name.
- Container: `sleepAfter = '2m'` (workers/proxy/src/org-executor.ts:96); the in-flight count ends when the response body closes, so a synchronous run whose client left may be killed when the container sleeps (inferred, untested).
- Detachable runs become renet jobs automatically after a 20 s attach window (packages/cli/src/services/jobs/attach.ts:23). Jobs live on the machine; `job list` without `--machine` reads an ephemeral ticket store inside the container. No D1 or Durable Object index of runs exists.
- Step-up exists: `requireElevated()` (private/account/src/middleware/elevated.ts) on about 47 routes, 10-minute window, email link or TOTP, with `useReauth` and `ReauthStep` in the web app. A passkey assertion route exists (private/account/src/routes/configs.ts, `/passkey/auth-verify`) but does not elevate. Console runs do not use step-up.
- Agent detection is CLI-only (packages/cli/src/utils/agent-guard.ts:34-46); the console exec principal has no kind field (packages/cli/src/services/serve/sessions.ts:35-43), so an AI's commands would count as the human's until remote-mcp's grants land.

## 4. Audit, retention, plans

- Console runs emit `cli.*` audit events (packages/cli/src/services/serve/audit.ts); `cli.*` is telemetry (`TELEMETRY_TYPES`, private/account/src/services/event-log.service.ts:35) and goes to Analytics Engine where bound, never reaching the D1 `event_log` the Activity page reads.
- A nightly purge already deletes `event_log` rows past 90 days for every org (private/account/src/services/event-log.service.ts:234-265), run from the 03:00 cron in private/account/src/entry/cloudflare.ts.
- `config.push` rows carry no org id, so Activity never shows config or policy saves (private/account/src/services/config.service.ts:866-871).
- Plans: FREE, COMMUNITY, PROFESSIONAL, BUSINESS, ENTERPRISE (packages/shared/src/subscription/types.ts:11); `PLAN_METADATA.paid` marks the last three.
- Admin per-org column pattern: `organizations.console_executor_blocked_at` with an elevated root route (private/account/src/routes/root.ts:458-490).
- The account worker already binds regional R2 buckets with EU jurisdiction (workers/account/wrangler.eu.toml:55-66).

## 5. Other consumers and neighbours

- MCP tools are built from the contract, opt-in through `COMMAND_METADATA[...].mcp`; no human-only command is exposed, but the `config_show` tool lists a `reveal` input that only a runtime agent check refuses (packages/cli/src/config/command-metadata.ts:564, packages/cli/src/commands/config.ts:225-250).
- Docs read packages/cli/scripts/command-tree.json and the CLI catalogues through packages/www/scripts/generate-cli-docs.js, not the contract. No shell completions exist.
- `rdc feedback report|list|show` exists (packages/cli/src/commands/feedback.ts); an agent without `--yes` gets a preview and the send command only (:126-130).
- No LLM product code exists. private/generative is local GPU speech and image tooling.
- The only Anthropic credential in BWS is `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` (.ci/config/bws-secret-map.json:148), optional in the `bench-login-eu` profile; C41 testing uses it with bearer auth, falling back to a Workers AI token the session mints if the provider refuses it.
- The org container starts with internet access (workers/proxy/src/org-executor.ts:511), so customer-key traffic to a provider needs no egress change; only Rediacc-tier traffic goes through an intercepted host.
- Renet emits stable step ids for fork, push, pull, up, down and migrate, written at each call site through the `StepTimer` in private/renet/pkg/output/steps.go:47-110 (for example private/renet/cmd/renet/repository_fork.go:368 and private/renet/pkg/orchestration/workflows.go:79); packages/cli/src/utils/timeline.ts:8-90 labels most but not `cow_sync`, `cow_reflink` or `cutover_complete`; backup to storage, restore and cluster operations emit none; no structured byte progress exists.

## 6. Corrections to the external brief

| Brief claim | Tree |
|---|---|
| 175 commands in 17 domains | 231 entries, 228 leaves, 22 domains; no `storage` domain |
| Destructive on about 58, over-applied | 27 flagged, 138 unannotated (under-applied) |
| The console needs a new manifest emitter | the contract exists and is drift-gated (C1) |
| The terminal panel is static | it is live |
| Nav labels Onboarding, Storages, Organization and Teams | Getting started, no Storages, Team; the redesign already deduplicated Machines |
| Every resource page shows only "No config store yet" | only when no store exists; a locked store shows the unlock form |
| Naively appending `--dry-run` to `repo gc` deletes | the executor refuses undeclared flags; the real gap is `repo prune` |
| A feature flag `console.v2` | no flag system exists; C3 rules none |
