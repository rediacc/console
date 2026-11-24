# PLAN: Console AI providers -- customer provider profiles in the encrypted config and the AI loop host in the org container executor
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-contract-semantics.md, PLAN-rmcp-decide.md, PLAN-rmcp-agent-grants.md -- tool definitions read the contract summaries and severities of plan 1 (C5, C6), every tool call is enforced through decide() (C33, C40), and the agent principal and its opt-in overrides come from the grant row and its executor session (remote-mcp D22, D23)
Priority: P1 -- no LLM product code exists (agent/programs/console-rework/01-verified-context.md section 5), and plans 9 to 12 of the program cannot start without a loop host and a provider
Concurrency: parallel -- wave 1: AP1, AP3, AP4 (file-disjoint); wave 2: AP2, AP5, AP9; wave 3: AP6, AP8, AP10; wave 4: AP7, AP11; wave 5: AP12 and the live boxes. Shared files are edited after their earlier owners land: packages/shared/src/config-schema/{schemas,sensitivity}.ts (PLAN-rmcp-policy-record.md, the backup plans), packages/cli/src/services/serve/server.ts (PLAN-rmcp-decide.md, PLAN-rmcp-writeback.md, PLAN-rmcp-executor-hardening.md; this plan adds one registration line), packages/cli/package.json and package-lock.json (PLAN-rmcp-local-mcp.md#LM1), private/account/src/routes/index.ts, private/account/web/src/router.tsx and nav-config.ts (PLAN-rmcp-agent-grants.md#AG-W and plans 2 to 6 of this program); each writer runs block_plan_concurrency before its first edit.
Owns: agent/plans/PLAN-console-ai-providers.md, packages/shared/src/ai/**, packages/shared/package.json, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/config-schema/__tests__/ai-field.test.ts, packages/shared/src/cli-contract/wire.ts, packages/shared/src/cli-contract/__tests__/wire-ai.test.ts, packages/cli/src/services/ai/**, packages/cli/src/services/serve/ai-routes.ts, packages/cli/src/services/serve/server.ts (AI route registration line only), packages/cli/src/services/serve/__tests__/ai-routes.test.ts, packages/cli/package.json, package-lock.json, private/account (gitlink bump only), private/account/src/routes/console-ai.ts, private/account/src/routes/index.ts, private/account/tests/integration/console-ai*.test.ts, private/account/web/src/pages/console/AiProviders.tsx, private/account/web/src/pages/console/__tests__/ai-providers.test.tsx, private/account/web/src/components/console/ai-providers/**, private/account/web/src/router.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/locales/*/aiProviders.json, private/account/e2e/tests/27-console/27-20-ai-providers.test.ts, packages/shared/src/ai/scripted/**, private/account/tests/integration/console-ai-scripted.test.ts, .ci/rediacc_ci/tests/test_no_ai_provider_secrets_in_ci.py
Live-Proof: bench -- the CLI loop host runs in the bench executor container and the settings page in the bench account portal; a customer-key chat streams through /console/ai/chat end to end

## Ask

The operator ruled that the in-console AI runs in the org container (C30), on a customer key stored as a secret leaf of the encrypted config at org or team level, a team profile overriding the org one, with two wire formats, presets and a tool-calling test on save (C31). Every command the AI runs goes through remote-mcp's decision function under an agent principal (C33, C40). The account Worker never sees a key (C30, the ruling at agent/plans/PLAN-rdc-feedback.md:37). Tests may use the Anthropic credential held in BWS, copied at run time and never committed (C41).

## Context

1. Secret config leaves have a precedent: `/credentials/cfDnsApiToken` (packages/shared/src/config-schema/sensitivity.ts:86) and `/resources/cloudProviders/*/apiToken` (packages/shared/src/config-schema/sensitivity.ts:237) are `kind: 'secret'`; their zod fields sit at packages/shared/src/config-schema/schemas.ts:492 and :509. The root schema is `.loose()` (packages/shared/src/config-schema/schemas.ts:566, :602), so an older CLI keeps a new top-level `ai` key whole.
2. The account server sees only blinded commitment keys and compares opaque HMACs (private/account/src/services/config.service.ts:694-702), so a config push cannot be gated per field on the server.
3. A config-session settings page exists: Permissions.tsx saves through `session.push` (private/account/web/src/pages/console/Permissions.tsx:261); step-up in the web app is `useReauth` (private/account/web/src/pages/Settings.tsx:14, :20).
4. The executor loads one config per principal, the team config first and the shared one as fallback (`pickConfig`, packages/cli/src/services/serve/container-config.ts:225). The principal has no kind field (packages/cli/src/services/serve/sessions.ts:35-43).
5. The only execution route is `POST /v1/command` (packages/cli/src/services/serve/server.ts:172), which runs `prepareCommand` before policy and calls `deps.authorize` at :226; route paths are shared through `PROXY_ROUTES` (packages/shared/src/cli-contract/wire.ts:348).
6. The NDJSON channel is `StreamLineSchema`, a discriminated union on `kind` (packages/shared/src/cli-contract/wire.ts:240); `WireEventSchema` (packages/shared/src/cli-contract/wire.ts:99) mirrors renet's own event shape, which the CLI render path consumes unchanged.
7. The container starts with `enableInternet: true` (workers/proxy/src/org-executor.ts:511) and only `account.internal` is intercepted (workers/proxy/src/org-executor-support.ts:12, :361); the egress allowlist covers account routes alone (workers/proxy/src/egress.ts:31-41). A customer provider call leaves the container directly and needs no egress change.
8. The console exec route proxies NDJSON from the account Worker to the executor (private/account/src/routes/console.ts:444).
9. Dependency policy: `ignore-scripts=true` and `allow-git=none` (.npmrc:12-13), a 1440-minute freshness window (.ci/config/release-age.json:10) applied by `npm run check:deps`, and lockfiles written by `npm run pins -- lockfiles` (package.json:311). No `ai` or `@ai-sdk/*` package is installed today.
10. The only Anthropic credential in BWS is `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` (.ci/config/bws-secret-map.json:148), an OAuth token, optional in the `bench-login-eu` profile (.ci/config/secret-supply.json:558).

## Design

D1. **Profile shape** (packages/shared/src/ai/profile.ts): `{format: 'anthropic-messages' | 'openai-chat', baseURL, key?, authScheme: 'x-api-key' | 'bearer', model, headers?: Record<string,string>, capabilities: {tools, streaming, parallelToolCalls, vision}, preset?, byokOnly?: boolean}`. `key` may be absent only with `byokOnly` (Cloudflare AI Gateway BYOK, where the gateway holds the provider key and the profile carries `cf-aig-authorization` in `headers`).

D2. **Storage**: top-level `ai: {providers: Record<name, Profile>, default?: name}` in `RdcConfigSchema`. Sensitivity: `/ai/providers/*/key` and `/ai/providers/*/headers/*` are `secret` (a header can carry auth), every other leaf and `/ai/default` are `public`.
Org level is the shared config, team level the team config.

D3. **Resolution**: the executor takes the team config's `ai.default` profile first, then the shared config's, pulled with the human session's key under remote-mcp D56 (`resolveProfile` in packages/shared/src/ai/resolve.ts, pure). An agent-grant session opens one config only (D55, D56), so it resolves inside that config.

D4. **Presets** (packages/shared/src/ai/presets.ts): Anthropic, OpenAI, Gemini (its OpenAI-compatible endpoint), Mistral, DeepSeek, Cloudflare AI Gateway (BYOK, and `byokOnly`), OpenRouter, Vercel AI Gateway, LiteLLM, Portkey. A preset fixes format, auth scheme, a base URL template and default capability flags; the model stays free text with a suggested default.

D5. **Base URL guard**: https only; a host that is `account.internal`, `ai.internal`, `localhost`, or a loopback, link-local or RFC 1918 literal is refused (`validateBaseUrl`), so a profile cannot aim the key at the egress intercept or the container itself. Self-hosted LiteLLM and Portkey endpoints must be public https.

D6. **Step-up and roles**: the page shows the shared config to org owners and admins and a team config to that team's admins; Save runs `useReauth` first. Context 2 rules out a server-side per-field gate under zero knowledge; the `secret` kind keeps the field commitment knowledge-gated, so a rewrite needs the current value, and C15's audit of config-editor saves (plan 3) records the save.

D7. **Loop host** (packages/cli/src/services/ai/): the Vercel AI SDK (`ai`, Apache-2.0) with `@ai-sdk/anthropic` for `anthropic-messages` and `@ai-sdk/openai-compatible` for `openai-chat`, both with custom `baseURL` and headers, at exact versions, the newest outside the release-age window when AP4 runs. `check:ci-runtime-imports-are-deps` keeps the declaration honest.

D8. **Wire**: a new `kind: 'ai'` member of `StreamLineSchema` carries `AiEventSchema` (`text_delta`, `tool_call`, `tool_result`, `approval_required`, `usage`, `finish`, `error`); each tool's renet events are forwarded as existing `event` lines tagged with the tool call id. `WireEventSchema` stays renet-shaped (context 6) instead of growing AI types, so every renet reader is untouched.
Routes `aiChat: '/v1/ai/chat'` and `aiTest: '/v1/ai/test'` join `PROXY_ROUTES`.

D9. **Agent principal**: the AI routes, never the request body, set `kind: 'agent'` on every tool call. Without a grant the overrides are `source: 'none'`, so decide() refuses grand-repo and cluster mutations for the agent; a chat bound to an agent grant (PLAN-rmcp-agent-grants.md) takes that grant's overrides through `overrides-grant.ts`. A `needs_confirmation` verdict ends the turn with an `approval_required` event; the approval surface and the autonomy modes are plan 9 (C33).

D10. **Tools**: definitions come from the LM1 registry (packages/shared/src/mcp/registry.ts); each tool runs in process through `prepareCommand` and the decide() enforcement point, never through a shell.
Tool output is untrusted: ANSI stripped, wrapped in a per-call random boundary, truncated to 16 KB as head plus tail with the cut marked, and the system prompt states that tool output is data, never instruction.

D11. **Caps in the loop**: at most 12 tool steps per turn, a per-turn output token cap from the profile (default 8,192), and an abort of the provider stream and any running tool when the client disconnects.

D12. **Test on save**: after the push the page calls `/console/ai/test`; the executor resolves the saved profile and runs one turn offering a single `echo_nonce` tool, passing only when the model calls it with the random nonce and streams a final message.
The result (pass, or the provider's status and message, latency, observed capabilities) is shown, not stored.

D13. **Account route**: `private/account/src/routes/console-ai.ts` forwards `/console/ai/chat` and `/console/ai/test` to the executor the way `/console/exec` does; its strict request schema refuses `key`, `apiKey`, `headers` and `baseURL` fields, so no provider secret rides a request through the Worker.

## Ordering against other live plans

- After PLAN-console-contract-semantics.md (tool descriptions use the C6 summaries), PLAN-rmcp-decide.md#D3 (executor enforcement), PLAN-rmcp-agent-grants.md#AG-X (grant sessions in the executor) and PLAN-rmcp-local-mcp.md#LM1 (the registry).
- PLAN-rmcp-writeback.md owns workers/proxy/src/egress.ts; this plan needs no egress edit (context 7). The `ai.internal` intercept of the Rediacc-provided tier belongs to PLAN-console-ai-credits.md.
- PLAN-console-ai-assistant.md (plan 9) renders the `ai` stream lines and owns the chat UI; this plan ships no chat surface beyond the settings page and its test.

## Tasks

- [x] AP1 [writer] Shared profile module: `profile.ts` (zod schema per D1), `presets.ts` (the ten presets of D4), `resolve.ts` (team-over-shared resolution per D3) and `base-url.ts` (the D5 guard), exported as `@rediacc/shared/ai`, with tests covering every preset, `byokOnly` without a key, refused `account.internal`, loopback and RFC 1918 base URLs, and team-over-org resolution.
  Owns: packages/shared/src/ai/**, packages/shared/package.json
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/ai)` rc 0.
    (ticked) 2026-11-23T18:17:56Z by ace763dd: commit:1618ab3660 landed; writer accept rc=0, lead re-verified on the landed tree
- [ ] AP2 [writer] Config field: `ai` in `RdcConfigSchema` per D2 and its sensitivity rows (`secret` for key and headers, `public` for the rest), with a round-trip test that a config carrying a profile survives push and pull with the key encrypted and its commitment knowledge-gated.
  Owns: packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/config-schema/__tests__/ai-field.test.ts
  Depends on: AP1.
  Accept: `(cd packages/shared && npx vitest run src/config-schema/__tests__/ai-field.test.ts src/config-schema/__tests__/coverage.test.ts)` rc 0.
- [x] AP3 [writer] Wire additions per D8: `AiEventSchema`, the `kind: 'ai'` stream line, the tool call id on forwarded `event` lines, and `aiChat` and `aiTest` in `PROXY_ROUTES`, with a test that every existing stream line still parses unchanged.
  Owns: packages/shared/src/cli-contract/wire.ts, packages/shared/src/cli-contract/__tests__/wire-ai.test.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/cli-contract/__tests__)` rc 0 and `npm run check:ci-cli-contract` rc 0.
    (ticked) 2026-11-23T18:18:08Z by ace763dd: commit:7e3922b7e6 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] AP4 [writer] Dependencies: `ai`, `@ai-sdk/anthropic` and `@ai-sdk/openai-compatible` at exact versions past the release-age window in packages/cli/package.json, the lockfile written by `npm run pins -- lockfiles`, each licence read as Apache-2.0 from the installed package.json and quoted in the commit body with the CLI bundle size before and after.
  Owns: packages/cli/package.json, package-lock.json
  Depends on: PLAN-rmcp-local-mcp.md#LM1.
  Accept: `npm run check:deps` rc 0, `npm run check:ci-lockfile` rc 0 and `npm run check:ci-runtime-imports-are-deps` rc 0.
    (ticked) 2026-11-24T21:44:10Z by d778be9d: AP4 ai, @ai-sdk/anthropic, @ai-sdk/openai-compatible pinned outside the freshness window; lockfile, deps, security audit gates rc 0
- [ ] AP5 [writer] Provider adapter `packages/cli/src/services/ai/provider.ts`: a profile becomes an AI SDK model for either format with base URL, auth scheme and headers applied and the D5 guard re-run at call time, tested against a local mock HTTP server speaking Anthropic Messages and OpenAI chat with streamed tool calls.
  Owns: packages/cli/src/services/ai/provider.ts, packages/cli/src/services/ai/__tests__/provider.test.ts
  Depends on: AP1, AP4.
  Accept: `(cd packages/cli && npx vitest run src/services/ai/__tests__/provider.test.ts)` rc 0.
- [ ] AP6 [writer] Tools `packages/cli/src/services/ai/tools.ts` per D9 and D10: LM1 registry entries become AI SDK tools run in process through `prepareCommand` and decide() with an agent principal set by the code path, output fenced and truncated by `untrusted.ts`, with tests that a grand-repo mutation without a grant is refused, `needs_confirmation` becomes `approval_required`, and an instruction injected into tool output stays inside its boundary.
  Owns: packages/cli/src/services/ai/tools.ts, packages/cli/src/services/ai/untrusted.ts, packages/cli/src/services/ai/__tests__/tools.test.ts
  Depends on: AP5, PLAN-rmcp-local-mcp.md#LM1, PLAN-rmcp-decide.md#D3.
  Accept: `(cd packages/cli && npx vitest run src/services/ai/__tests__/tools.test.ts)` rc 0.
- [ ] AP7 [writer] Loop host and routes: `packages/cli/src/services/ai/loop.ts` (D3 resolution from the session config, D11 caps, abort on disconnect, `ai` stream lines) and `ai-routes.ts` serving `/v1/ai/chat` and `/v1/ai/test`, registered by one line in server.ts, with grant-bound chats routed to the PLAN-rmcp-agent-grants.md#AG-X session.
  Owns: packages/cli/src/services/ai/loop.ts, packages/cli/src/services/serve/ai-routes.ts, packages/cli/src/services/serve/server.ts (AI route registration line only), packages/cli/src/services/serve/__tests__/ai-routes.test.ts
  Depends on: AP3, AP6, AP8, PLAN-rmcp-agent-grants.md#AG-X.
  Accept: `(cd packages/cli && npx vitest run src/services/serve/__tests__/ai-routes.test.ts)` rc 0 with cases for the 12-step cap, a client abort stopping the mock provider stream, a body-asserted `kind` ignored, and a team profile winning over the shared one.
- [ ] AP8 [writer] Tool-calling smoke `packages/cli/src/services/ai/smoke.ts` per D12: one turn offering `echo_nonce`, passing only on a call carrying the nonce and a streamed final message, otherwise failing with the provider's status and message.
  Owns: packages/cli/src/services/ai/smoke.ts, packages/cli/src/services/ai/__tests__/smoke.test.ts
  Depends on: AP5.
  Accept: `(cd packages/cli && npx vitest run src/services/ai/__tests__/smoke.test.ts)` rc 0, including a mock model that skips the tool and is reported as a failure.
- [ ] AP9 [writer] Account route `console-ai.ts` per D13: `/console/ai/chat` and `/console/ai/test` behind `sessionAuth()`, forwarding NDJSON to the executor as `/console/exec` does, with a strict schema refusing secret-bearing fields, registered in routes/index.ts.
  Owns: private/account/src/routes/console-ai.ts, private/account/src/routes/index.ts, private/account/tests/integration/console-ai*.test.ts
  Depends on: AP3.
  Accept: `(cd private/account && npx vitest run tests/integration/console-ai)` rc 0, including a body carrying `key` refused with 400.
- [ ] AP10 [writer] Settings page `AiProviders.tsx` and its components: profile list for the shared and team configs, preset picker, the D1 form with capability flags, Save behind `useReauth` and `session.push`, then the test-on-save call and its result, shown to the roles of D6; router entry, nav entry and endpoints.
  Owns: private/account/web/src/pages/console/AiProviders.tsx, private/account/web/src/pages/console/__tests__/ai-providers.test.tsx, private/account/web/src/components/console/ai-providers/**, private/account/web/src/router.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/endpoints.ts
  Depends on: AP1, AP2, AP9.
  Accept: `(cd private/account/web && npx vitest run src/pages/console/__tests__/ai-providers.test.tsx)` rc 0 and `(cd private/account && npm run typecheck:web)` rc 0.
- [ ] AP11 [writer] Locale file `aiProviders.json`: English first, then the 12 derived locales through the naturalization pipeline, writers on sonnet.
  Owns: private/account/web/src/i18n/locales/*/aiProviders.json
  Depends on: AP10.
  Accept: `npm run -s check:i18n` rc 0 and `npm run check:ci-i18n-account-key-usage` rc 0.
- [ ] AP12 [writer] Keyboard contract spec `27-20-ai-providers.test.ts` (C28): pick a preset, fill the form, save through the reauth step and read the test result, all by keyboard, against the mock executor.
  (corrected 2026-11-23, ruling C42) This spec runs against the scripted provider of PLAN-console-ai-providers.md#AP13 under TEST_MODE; no real provider key reaches CI.
  Owns: private/account/e2e/tests/27-console/27-20-ai-providers.test.ts
  Depends on: AP10, AP11.
  Accept: `(cd private/account/e2e && npx playwright test tests/27-console/27-20-ai-providers.test.ts)` rc 0.
- [ ] AP13 [writer] Scripted test provider (C42): deterministic AI scripts in packages/shared/src/ai/scripted/ (text, tool calls, an approval request, a refusal, a feedback offer, a provider error), served as the AI stream by the TEST_MODE console mock in place of the executor loop and fed to the executor unit tests through the AI SDK mock model, plus a test that fails when a .github/workflows job receives an AI provider secret.
  Owns: packages/shared/src/ai/scripted/**, private/account/src/routes/console-ai.ts (the TEST_MODE branch only), private/account/tests/integration/console-ai-scripted.test.ts, .ci/rediacc_ci/tests/test_no_ai_provider_secrets_in_ci.py
  Depends on: AP6, AP9.
  Accept: `(cd private/account && npx vitest run tests/integration/console-ai-scripted.test.ts)` rc 0 with every script replayed byte-identically twice; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_no_ai_provider_secrets_in_ci.py` rc 0, with a control workflow fixture passing `ANTHROPIC_API_KEY` to a job turning it red; `git grep -n -E "ANTHROPIC_|OPENAI_|AI_GATEWAY_" -- .github/workflows` prints nothing.
- [ ] AP-L1 [live] Customer-key chat on the eu bench: under `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile bench-login-eu`, save an Anthropic profile whose key is `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` with `authScheme: 'bearer'` and the OAuth beta header, see test-on-save pass, run a chat that calls `machine list`, and see a grand-repo mutation refused for the agent; when the provider refuses the OAuth token, the run uses an OpenAI-compatible profile on a Workers AI token the session mints. The key never reaches a log, a commit or the evidence.
  Depends on: AP7, AP10, LP-bench.
  Accept: the evidence names the preset, the smoke result and the tool call's decide() code, and `git grep -n -e "sk-ant-" -e "ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN=" -- .` prints nothing.
- [ ] LP-bench [live] Deploy the branch's account Worker and the proxy carrying the executor image built from this tree to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu` and `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench`), then run the CLI check; proxy-ready and account-smoke run as additional verification.
  Accept: live-proof bench cli-bench

## Risks

- The BWS credential is an OAuth token, not a Messages API key (context 10); AP-L1 carries the fallback instead of an operator question.
- Zero knowledge rules out a server-side per-field step-up (context 2); D6 states what stands in its place.
- The AI SDK adds weight to the CLI bundle; AP4 records the size before and after.
- A permissive base URL is an exfiltration path for the key; D5 refuses internal hosts and AP5 re-checks at call time.
