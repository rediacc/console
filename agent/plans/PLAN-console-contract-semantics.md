# PLAN: Console contract semantics -- summaries, severity, preview polarity, error origin and a real version in the CLI contract, loaded lazily by the web console
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: no-dep -- every box builds on the 1121-1 tip; CS9 waits on PLAN-tooling-code-reduction.md#CR2 as a box dependency rather than a plan edge, so the two plans do not join one PR plan set
Priority: P1 -- plans 2 to 12 of agent/programs/console-rework read these fields; `repo prune --apply` carries no destructive flag today, 118 of 231 commands have no summary, and the contract version is always `dev`, so the executor's mismatch check never fires
Concurrency: parallel -- wave 1: CS1, CS2, CS3, CS4, CS13 (file-disjoint); wave 2: CS5 (generator, after CS1 to CS4); wave 3: CS6, CS7 (translations, disjoint locales), CS8, CS10, CS14 (lead); wave 4: CS9 (after CR2), CS11 (after CS10). CS13 edits one entry of packages/cli/src/config/command-metadata.ts, whose `mcp` fields agent/plans/PLAN-rmcp-local-mcp.md owns; CS13 lands first and LM1 keeps the exclusion
Owns: agent/plans/PLAN-console-contract-semantics.md, packages/shared/src/cli-contract/types.ts, packages/shared/src/cli-contract/validation.ts, packages/shared/src/cli-contract/index.ts, packages/shared/src/cli-contract/core.ts, packages/shared/src/cli-contract/load.ts, packages/shared/src/cli-contract/data/**, packages/shared/src/cli-contract/__tests__/**, packages/cli/scripts/generate-cli-contract.ts, packages/cli/scripts/command-tree.json, packages/cli/src/config/command-safety.ts, packages/cli/src/config/__tests__/command-safety.test.ts, packages/cli/src/config/command-metadata.ts (the config show entry only), packages/cli/src/types/errors.ts, packages/cli/src/types/error-origins.ts, packages/cli/src/types/__tests__/error-origins.test.ts, packages/cli/src/utils/errors.ts, packages/cli/src/commands/**/*.ts (summary calls only), packages/cli/src/i18n/locales/*/cli.json (descriptionShort and proxyBlocked keys only), packages/cli/src/commands/mcp/__tests__/agent-refused-options.test.ts, packages/cli/src/services/serve/__tests__/contract-version-mismatch.test.ts, .ci/rediacc_ci/quality/cli_contract_coverage.py, .ci/rediacc_ci/quality/cli_contract.py, .ci/rediacc_ci/tests/gates/test_gate_cli_contract_coverage.py, private/account/web/src/lib/contract-provider.tsx, private/account/web/src/lib/contract-context.ts, private/account/web/src/lib/contract-form.ts, private/account/web/src/lib/contract-i18n.tsx, private/account/web/src/lib/resource-options.ts, private/account/web/src/hooks/usePickerOptions.ts, private/account/web/src/hooks/useResourceList.ts, private/account/web/src/api/console.ts, private/account/web/src/components/Layout.tsx, private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/RunHistory.tsx, private/account/web/src/pages/console/*.tsx, private/account/web/src/lib/__tests__/contract-*.test.ts, private/account/web/src/components/console/__tests__/**, private/account/web/src/i18n/locales/*/console.json (contractVersionMismatch key only), private/account/web/src/i18n/locales/.translation-hashes.json
Live-Proof: bench -- the shared contract, the CLI the bench executor serves and the account web console bundle; LP-bench runs account-smoke after deploy_bench

## Ask

The console rework extends the existing CLI contract rather than adding a manifest (C1). Every command declares a severity of `none`, `caution` or `destructive`, gated, with one operator review of the full list before it ships (C5). Every command carries a summary of at most 100 characters, exported from `.summary()`, written in English where missing and translated into the 13 locales, gated (C6). Preview-capable commands declare their flag and polarity (C7). Every CLI error code declares an origin of user, environment or Rediacc, gated (C8). The same plan drops `reveal` from the `config_show` MCP schema with a coverage test (C24, the one MCP edit allowed by C4).

## Context

1. The contract's command shape is `ContractCommand` at packages/shared/src/cli-contract/types.ts:237; `destructive` (packages/shared/src/cli-contract/types.ts:290) is copied only from an MCP annotation (packages/cli/scripts/generate-cli-contract.ts:572), so the 138 commands without an `mcp` entry carry none. Counted from packages/shared/src/cli-contract/data/contract.json on 2026-11-23: 231 entries, 27 `destructive: true`, 66 false, 138 unset.
2. `repo prune` has a `grandGuard` and an `mcpExcludeReason` but no `mcp` entry (packages/cli/src/config/command-metadata.ts:908), so it ships unflagged although `--apply` deletes and `--offline` stops the Docker daemon (packages/cli/src/commands/repo-prune.ts:83).
3. Walking the live Commander tree with tsx: 113 of the 231 contract commands return a non-empty `.summary()`, none longer than 100 characters; 118 have none (backup 28, config 30, machine 16, repo 12, subscription 8, job 6, ops 6, vscode 6, server 4, mcp 1, term 1). The generator emits `label` from `.description()` and never the summary.
4. Preview flags in the contract: 23 commands take `--dry-run`; three take `--apply`, of which `repo gc` and `repo prune` preview by default and `config edit --apply` only skips `$EDITOR`, so derivation from the flag name alone is wrong.
5. Error codes come in two tiers: 15 envelope codes in `ERROR_CODES` (packages/cli/src/types/errors.ts:31, typed by `ErrorCode` at packages/cli/src/types/errors.ts:8) and named `errorCode` strings scattered through the source (for example packages/cli/src/remote/sftp/connect-error.ts:50); the JSON envelope is built at packages/cli/src/utils/errors.ts:111.
6. The generator's version defaults to `dev` (packages/cli/scripts/generate-cli-contract.ts:264) and nothing passes `--version`, so packages/shared/src/cli-contract/data/contract.generated.ts:7 is `dev` and the executor comparison at packages/cli/src/services/serve/server.ts:187 always agrees. The web sends the constant from private/account/web/src/api/console.ts:109; no test drives the 409 path in packages/cli/src/services/serve/__tests__/.
7. The drift gate excludes the version from its diff (.ci/rediacc_ci/quality/cli_contract.py:12).
8. packages/shared/src/cli-contract/index.ts:8 re-exports the full contract literal, and 14 web modules import values from that entry; routes are eager (private/account/web/src/router.tsx:276) and the palette scans `CLI_CONTRACT.commands` portal-wide (private/account/web/src/components/console/CommandPalette.tsx:242). The entry chunk workers/account/dist/account/assets/index-B05RA6e2.js measured 4,429,785 bytes raw and 1,189,085 gzip on 2026-11-23 and contains ``pathKey:`backup browse` ``.
9. `config show` is an MCP tool with no `excludeOptions` (packages/cli/src/config/command-metadata.ts:564), while the handler refuses `--reveal` to an agent at run time (packages/cli/src/commands/config.ts:232).
10. agent/plans/PLAN-rmcp-local-mcp.md:8 owns the `mcp`, `mcpExcludeReason` and `mcpSurface` fields of command-metadata.ts and packages/cli/src/commands/mcp/**; its LM1 (agent/plans/PLAN-rmcp-local-mcp.md:54) moves MCP tools into a generated registry.

## Design

D1. **Additive fields only (C1).** `ContractCommand` gains `summaryKey: string | null`, `summary: string`, `severity: 'none' | 'caution' | 'destructive'`, `preview?: { flag: string; polarity: 'opt-in' | 'default' }` and `proxyBlockedReasonKey?: string`. `opt-in` means the flag makes the run a preview (`--dry-run`); `default` means the command previews unless the flag is given (`--apply`). `CliContract` gains `errorCodes: { code: string; origin: 'user' | 'environment' | 'rediacc' }[]`. `destructive` stays as the MCP annotation; the console moves to `severity` in agent/plans/PLAN-console-confirm-stepup.md.

D2. **Severity and preview live in a new table, `packages/cli/src/config/command-safety.ts`, not in command-metadata.ts.** Reason: command-metadata.ts is already split between two remote-mcp plans by field (Context 10), most of its entries exist only for MCP, and severity must cover all 231 commands. The table is keyed by pathKey; the generator refuses a contract command with no entry, an entry naming no command, an MCP `destructive: true` command declared `none`, and any command taking `--dry-run` or `--apply` that is neither in the preview table nor in a `NOT_PREVIEW` list with a reason (`config edit`). Drafting rule: `destructive` deletes or overwrites state that is not trivially undone; `caution` changes state reversibly; `none` reads.
`repo prune` is `destructive` with preview `{flag: 'apply', polarity: 'default'}`.

D3. **Summaries are `.summary(t('commands.<path>.descriptionShort'))` calls**, so CLI help and the contract read one string. The generator exports the resolved key and the English text; the 13 locales arrive through the contract's i18n bundles. `proxyBlockedReason` gains a key under `commands.proxyBlocked.*` so the console can show the real reason translated (plan 6 reads it).

D4. **Origin lives in `packages/cli/src/types/error-origins.ts`**: `ERROR_CODE_ORIGINS` typed `Record<ErrorCode, ErrorOrigin>` (the type checker refuses a missing envelope code) and `NAMED_ERROR_ORIGINS` for named codes, where a named code's origin overrides its envelope code's.
Classing: `rediacc` is a defect or outage on Rediacc's side (`SERVER_ERROR`, an uncaught exception); `environment` is the network, a machine, SSH, Docker or disk; `user` is input, auth, permission or plan limits. The JSON envelope gains `origin` beside `code`; consumers of the served stream look the origin up in the contract's `errorCodes`, so the wire schema is untouched.

D5. **The version is a content hash, not the release version.** Reason: the web bundle and the executor image ship separately, and what must match is the command surface each was built against, not the release tag; a hash also keeps regeneration deterministic, so the drift gate stops needing its version exclusion.
The generator computes sha256 over the canonical JSON of `{commands, languages, errorCodes}` (translations excluded: they do not change what the executor accepts), keeps the first 16 hex characters, writes it into `contract.generated.ts`, `contract.json` and a tiny `data/contract-version.generated.ts`, and drops `--version`.

D6. **Lazy contract.** `packages/shared/src/cli-contract/core.ts` holds the data-free helpers taking a contract argument (`indexContract(contract)` returning `getCommand`, `commandsByDomain`, `commandsForContext`, `proxyCapableCommands`); `load.ts` exports `loadCliContract()` as a dynamic import of the data; the root entry keeps its synchronous exports for the CLI and the worker.
The web imports only `@rediacc/shared/cli-contract/core`, `/load` and the version file, through a `ContractProvider` mounted in Layout that loads once on the first console route or palette open; a test refuses any value import of the root entry under private/account/web/src.

D7. **The `reveal` drop.** `config show` gets `excludeOptions: ['reveal']`. A coverage test declares a table of agent-refused options (each `isAgentEnvironment()` call site under packages/cli/src/commands classified as refusing named options or `none -- <reason>`), asserts no built MCP tool schema exposes a refused option, and fails when a new call site is unclassified.

D8. **Coverage gate**, in the CR2 header grammar, reads the committed contract and its bundles: every command has a severity, a `summaryKey`, a summary of 1 to 100 characters present and non-empty in all 13 bundles, every `preview.flag` names a real option, every `errorCodes` row has an origin. Header block: `step: CLI contract coverage`, `needs: node`, `selftest: true`, `lane: quality-packages`. The CLI-side tests (D2, D4, D7) are the type-level half; the gate checks the artifact the web and executor read.

## Ordering against other live plans

- CS13 lands before agent/plans/PLAN-rmcp-local-mcp.md LM1; LM1 carries `excludeOptions: ['reveal']` into its registry and keeps agent-refused-options.test.ts green.
- agent/plans/PLAN-rmcp-decide.md edits packages/cli/src/services/serve/server.ts; this plan adds only a test file beside it.
- agent/plans/PLAN-rmcp-policy-record.md W1 edits console.json in 13 locales; CS11 adds one key, so the two are key-disjoint.
- CS9 waits on PLAN-tooling-code-reduction.md#CR2, which holds .ci/** and root package.json for its rewrite.
- agent/plans/PLAN-console-ia.md and agent/plans/PLAN-console-confirm-stepup.md read these fields and land after this plan.

## Tasks

- [x] CS1 [writer] Contract types and schema (D1): `summaryKey`, `summary`, `severity`, `preview`, `proxyBlockedReasonKey` on `ContractCommand`, `errorCodes` on `CliContract`, the zod schema, and `checkContractInvariants` refusing a summary over 100 characters and a `preview.flag` that names no option of its command.
  Owns: packages/shared/src/cli-contract/types.ts, packages/shared/src/cli-contract/validation.ts, packages/shared/src/cli-contract/__tests__/**
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/cli-contract)` rc 0 with a fixture per invariant that fails before the fix; `(cd packages/shared && npx tsc --noEmit)` rc 0.
    (ticked) 2026-11-23T15:59:18Z by ace763dd: commit:1d848f8303 landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
- [x] CS2 [writer] The severity and preview table (D2): `packages/cli/src/config/command-safety.ts` with a drafted severity for every one of the 231 commands, `repo prune` destructive, the preview table for the 23 `--dry-run` commands plus `repo gc` and `repo prune`, and `NOT_PREVIEW` holding `config edit` with its reason.
  Owns: packages/cli/src/config/command-safety.ts, packages/cli/src/config/__tests__/command-safety.test.ts
  Depends on: none.
  Accept: `(cd packages/cli && npx vitest run src/config/__tests__/command-safety.test.ts)` rc 0, asserting coverage of every contract pathKey, no stale key, no MCP-destructive command at `none`, `repo prune` destructive with polarity `default`, and every `--dry-run`/`--apply` command classified, each with a control fixture that turns it red.
    (ticked) 2026-11-23T15:59:20Z by ace763dd: commit:90db5f63ce landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
    (corrected 2026-11-27T04:34:40Z, 3b307aa2.2) The tick cites the shared cli-contract run, which is not CS2's Accept. The Accept ran on the tree at 2026-11-27T04:34:40Z: `(cd packages/cli && npx vitest run src/config/__tests__/command-safety.test.ts src/commands/mcp/__tests__/agent-refused-options.test.ts src/commands/mcp/__tests__/mcp-coverage.test.ts)` rc 0, 27 passed in 3 files.
- [x] CS3 [writer] Error origins (D4): `packages/cli/src/types/error-origins.ts` with `ERROR_CODE_ORIGINS` over the 15 envelope codes and `NAMED_ERROR_ORIGINS` over every named code the source emits, `origin` in the JSON envelope, and an inventory test that scans packages/cli/src for `errorCode:` literals, `*_CODE = '...'` constants and `CliExitError` first arguments and fails on an unlisted code.
  Owns: packages/cli/src/types/error-origins.ts, packages/cli/src/types/errors.ts, packages/cli/src/utils/errors.ts, packages/cli/src/types/__tests__/error-origins.test.ts
  Depends on: none.
  Accept: `(cd packages/cli && npx vitest run src/types/__tests__/error-origins.test.ts)` rc 0 with a control source fixture holding an unlisted code that turns it red; `(cd packages/cli && npm run typecheck)` rc 0; `(cd packages/cli && npm test)` rc 0.
    (ticked) 2026-11-23T15:59:21Z by ace763dd: commit:5b54f55b40 landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
- [x] CS4 [writer] English summaries and blocked-reason keys (D3): a `.summary(t('commands.<path>.descriptionShort'))` call and its English key in packages/cli/src/i18n/locales/en/cli.json for each of the 118 commands without one, each at most 100 characters, plus one `commands.proxyBlocked.*` English key per distinct `proxyBlockedReason` text.
  Owns: packages/cli/src/commands/**/*.ts (summary calls only), packages/cli/src/i18n/locales/en/cli.json
  Depends on: none.
  Accept: a tsx walk of the Commander tree prints 231 of 231 contract commands with a summary of at most 100 characters; `npm run check:ci-i18n-cli-key-usage` rc 0; `(cd packages/cli && npm test)` rc 0; `npm run export:command-tree -w @rediacc/cli` then `npm run check:ci-command-tree` rc 0.
    (ticked) 2026-11-23T15:59:22Z by ace763dd: commit:31e8fcef10 landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
- [x] CS5 [writer] Generator (D1 to D5): export `summaryKey`, `summary`, `severity`, `preview`, `proxyBlockedReasonKey` and `errorCodes`, refuse the D2 curation problems, compute the content-hash version into contract.generated.ts, contract.json and `data/contract-version.generated.ts`, drop `--version`, and regenerate the committed contract.
  Owns: packages/cli/scripts/generate-cli-contract.ts, packages/shared/src/cli-contract/data/**
  Depends on: CS1, CS2, CS3, CS4.
  Accept: `npm run generate:cli-contract -w @rediacc/cli` rc 0 and a second run leaves no diff; `CLI_CONTRACT_VERSION` is 16 hex characters; deleting one entry from command-safety.ts in a scratch copy makes the generator exit 1 naming it; `npm run check:ci-cli-contract` rc 0; `(cd packages/shared && npx vitest run src/cli-contract)` rc 0.
    (ticked) 2026-11-23T15:59:24Z by ace763dd: commit:24aad35d46 landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
- [x] CS6 [writer] Translate the new summaries and `commands.proxyBlocked.*` keys into ar, de, es, et, fr and it, naturalized per docs/i18n/CONVENTIONS.md, by a sonnet writer, then regenerate the contract bundles.
  Owns: packages/cli/src/i18n/locales/{ar,de,es,et,fr,it}/cli.json, packages/shared/src/cli-contract/data/i18n/{ar,de,es,et,fr,it}.json
  Depends on: CS5.
  Accept: `npm run check:i18n:completeness` and `npm run check:ci-i18n-naturalization` rc 0; `npm run generate:cli-contract -w @rediacc/cli` leaves no diff after the commit.
    (ticked) 2026-11-23T18:17:36Z by ace763dd: commit:23bdb87af6 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CS7 [writer] Translate the new summaries and `commands.proxyBlocked.*` keys into ja, ko, pt, ru, tr and zh, naturalized per docs/i18n/CONVENTIONS.md, by a sonnet writer, then regenerate the contract bundles.
  Owns: packages/cli/src/i18n/locales/{ja,ko,pt,ru,tr,zh}/cli.json, packages/shared/src/cli-contract/data/i18n/{ja,ko,pt,ru,tr,zh}.json
  Depends on: CS5.
  Accept: `npm run check:i18n:completeness` and `npm run check:ci-i18n-naturalization` rc 0; `npm run generate:cli-contract -w @rediacc/cli` leaves no diff after the commit.
    (ticked) 2026-11-23T18:17:38Z by ace763dd: commit:4ffcfd9391 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CS8 [writer] Contract version mismatch test (D5): a test that drives `createServeApp` with a client version differing from `CLI_CONTRACT_VERSION` and expects 409 `contract_version_mismatch` carrying both versions, and with the equal version expects no 409.
  Owns: packages/cli/src/services/serve/__tests__/contract-version-mismatch.test.ts
  Depends on: CS5.
  Accept: `(cd packages/cli && npx vitest run src/services/serve/__tests__/contract-version-mismatch.test.ts)` rc 0, and the mismatch case fails when the comparison at packages/cli/src/services/serve/server.ts:187 is short-circuited in a scratch copy.
    (ticked) 2026-11-23T18:17:39Z by ace763dd: commit:ad69d23bc8 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CS9 [writer] Coverage gate (D8): `.ci/rediacc_ci/quality/cli_contract_coverage.py` with its CR2 header and a selftest, its gate test, and the version exclusion removed from cli_contract.py now that the version is deterministic.
  Owns: .ci/rediacc_ci/quality/cli_contract_coverage.py, .ci/rediacc_ci/quality/cli_contract.py, .ci/rediacc_ci/tests/gates/test_gate_cli_contract_coverage.py
  Depends on: CS5, CS6, CS7, PLAN-tooling-code-reduction.md#CR2.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.quality.cli_contract_coverage` rc 0 on the tree; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/gates/test_gate_cli_contract_coverage.py` rc 0 with controls (a missing severity, a 101-character summary, a summary key absent from one bundle, an error code without origin) each turning the gate red; `npm run check:ci-cli-contract` rc 0 with the version now diffed; `npm run check:ci-gate-reachability-coverage` rc 0.
    (ticked) 2026-11-24T09:17:36Z by d778be9d: landed b2ffbf5527,b6917624b6; gate selftest 23 controls, 27 tests, check:ci-cli-contract rc 0. DEPS-WAIVED: CR2 code landed, open only for C4:operator
- [x] CS10 [writer] Shared lazy entry (D6): `core.ts` with `indexContract`, `load.ts` with `loadCliContract`, the version file exported on its own subpath, and the root index re-exporting both so the CLI and worker keep their synchronous imports.
  Owns: packages/shared/src/cli-contract/core.ts, packages/shared/src/cli-contract/load.ts, packages/shared/src/cli-contract/index.ts, packages/shared/src/cli-contract/__tests__/**
  Depends on: CS5.
  Accept: `(cd packages/shared && npx vitest run src/cli-contract)` rc 0 with a test that core.ts imports nothing from `data/contract.generated`; `(cd packages/shared && npm run build)` rc 0; `(cd packages/cli && npm run typecheck)` rc 0.
    (ticked) 2026-11-23T15:59:25Z by ace763dd: commit:2b2746df2e landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
    (corrected 2026-11-27T04:34:40Z, 3b307aa2.3) The tick omits the build leg of the Accept: `(cd packages/shared && npm run build)` rc 0 on the tree at 2026-11-27T04:34:40Z.
- [ ] CS11 [writer] Web console on the lazy contract (D5, D6): `ContractProvider` in Layout, every value import of the root contract entry under private/account/web/src replaced by the provider hook or the core and version subpaths, a translated `contractVersionMismatch` message on a 409 in all 13 locales by a sonnet writer, and an import-guard test.
  Owns: private/account/web/src/lib/contract-provider.tsx, private/account/web/src/lib/contract-context.ts, private/account/web/src/lib/contract-form.ts, private/account/web/src/lib/contract-i18n.tsx, private/account/web/src/lib/resource-options.ts, private/account/web/src/hooks/usePickerOptions.ts, private/account/web/src/hooks/useResourceList.ts, private/account/web/src/api/console.ts, private/account/web/src/components/Layout.tsx, private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/RunHistory.tsx, private/account/web/src/pages/console/*.tsx, private/account/web/src/lib/__tests__/contract-*.test.ts, private/account/web/src/components/console/__tests__/**, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/.translation-hashes.json
  Depends on: CS10.
  Accept: `(cd private/account/web && npm test)` and `(cd private/account/web && npm run build)` rc 0; the new entry chunk under workers/account/dist/account/assets holds no ``pathKey:`backup browse` `` and a separate chunk does; entry chunk raw and gzip bytes quoted against 4,429,785 and 1,189,085; `npm run check:ci-i18n-account-key-usage` rc 0; `npx playwright test tests/27-console/27-01-console.test.ts` in private/account/e2e rc 0.
- [ ] CS12 [lead] Operator review of the full severity list (C5): render command-safety.ts as one table of 231 rows (pathKey, severity, preview), put it to the operator once, and commit the corrections with CS2's test green.
  Depends on: CS2.
  Accept: the tick carries the operator's answer minute (`ASKED:<YYYY-MM-DDTHH:MM>Z`) and the correction commit; `(cd packages/cli && npx vitest run src/config/__tests__/command-safety.test.ts)` rc 0 on it.
- [x] CS13 [writer] The `reveal` drop (D7, C24): `excludeOptions: ['reveal']` on `config show` and agent-refused-options.test.ts classifying every `isAgentEnvironment()` call site under packages/cli/src/commands and asserting no MCP tool schema exposes a refused option.
  Owns: packages/cli/src/config/command-metadata.ts (the config show entry only), packages/cli/src/commands/mcp/__tests__/agent-refused-options.test.ts
  Depends on: none.
  Accept: `(cd packages/cli && npx vitest run src/commands/mcp/__tests__/agent-refused-options.test.ts src/commands/mcp/__tests__/mcp-coverage.test.ts)` rc 0; the test fails with `reveal` restored to the schema and fails on an unclassified call site fixture.
    (ticked) 2026-11-23T15:59:27Z by ace763dd: commit:2b807c9710 landed; shared vitest src/cli-contract 81 passed rc 0, check:ci-cli-contract rc 0, packages/cli tsc --noEmit rc 0 on b671913c7f
    (corrected 2026-11-27T04:34:40Z, 3b307aa2.4) The tick cites the shared cli-contract run, which is not CS13's Accept. The Accept's two test files ran on the tree at 2026-11-27T04:34:40Z in the one run recorded under CS2 (`(cd packages/cli && npx vitest run ...)` rc 0, 27 passed in 3 files); the restored-`reveal` and unclassified-call-site red controls were not re-run.
- [ ] CS14 [lead] Plan-record refresh after the plan file is committed: `npm run check:ci-plan-boxes -- --update` and `npm run check:ci-plan-record -- --update`.
  Depends on: none.
  Accept: both checks rc 0 after the regeneration and `npm run check:ci-prose-style` rc 0 on this file.
- [ ] LP-bench [live] Deploy the branch to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and run the console smoke; additional verification: a `./rdc.sh --config eu-bench --proxy repo list` run returns no `contract_version_mismatch`, and the bench console lists commands once the lazy chunk loads.
  Accept: live-proof bench account-smoke

## Risks

- **Help output changes.** 118 new `.summary()` strings change Commander's subcommand listings, which tutorial casts and help-render gates capture; CS4 runs `npm run check:ci-i18n-cli-help-render` and names any recast it needs.
- **A hash that ignores a field the executor reads.** D5 hashes the whole command list, so any change to options, planes or proxy fields moves the version; translations alone do not.
- **Severity drafted wrong at scale.** CS12 puts all 231 rows to the operator once before merge, and plan 2 reads severity only after it lands.
- **The palette opening before the chunk loads.** CS11 shows the palette's loading row until `loadCliContract()` resolves; the import-guard test keeps the data out of the entry chunk.
