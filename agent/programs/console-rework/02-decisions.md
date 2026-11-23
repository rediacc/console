# console-rework: operator decisions

Every ruling below was given by the operator in session `9b22c347` on 2026-11-23, through nineteen AskUserQuestion batches recorded on worklist item #b785e9ff. A plan in this program cites a decision by its id (`C7`), never by paraphrase, and does not re-litigate it. The external rework brief (`/tmp/rediacc-console-rework-prompt.md`, not committed) supplied intent only; where it disagrees with these rulings, the rulings win.

## Base and packaging

- **C1 Extend the existing CLI contract.** New per-command fields are added to `packages/shared/src/cli-contract` (types, zod schema, generator `packages/cli/scripts/generate-cli-contract.ts`) next to the existing ones. No parallel `rdc spec emit` manifest and no reshape of `pathKey`, `options` or `positionals`; every current reader (web console, worker allowlist, `rdc --proxy`, executor dispatch, MCP, redaction) keeps working unchanged.
- **C2 The rework is a program** under `agent/programs/console-rework/`, its plans in `agent/plans/`, one plan per PR.
- **C3 Rollout is plan by plan, with no feature flag.** Each plan replaces the old surface in its own PR (the repo's clean-break rule); no `console.v2` flag and no flag system is built.
- **C4 MCP stays with the remote-mcp program.** The rework owns no MCP files and adds no agent-policy field for the console, whose users are human; the one exception is C24.

## Command metadata

- **C5 Every command declares a severity**, one of `none`, `caution`, `destructive`, in the CLI metadata tables; a gate fails the build on any command without one, and the operator reviews the full list of 231 once before it ships.
- **C6 Every command carries a short summary** of at most 100 characters: the existing `.summary()` strings are exported into the contract, the missing ones are written in English, all are translated into the 13 locales through the existing translation pipeline, and a gate fails on a missing one.
- **C7 Preview-capable commands declare their preview flag and polarity** (`--dry-run` opt-in, or `--apply` to act), so the console offers Preview beside Run and the confirmation follows what will actually run.
- **C8 Every CLI error code declares an origin**: the user's input, the user's environment, or Rediacc. A gate fails on an error code without one. C33 reads it.

## Navigation and command surfaces

- **C9 Navigation is Variant A.** The sidebar redesign rulings stand (`agent/plans/PLAN-account-sidebar-redesign.md` ruling O2: the licence page stays "Machines", the console page is "Console machines"). Five labels change, routes do not: "Getting started" to "Get started", "Backup storage" to "Backup quota", "Config storage" to "Encrypted config sync", "Commands" to "All commands", "Config" to "Config file".
- **C10 Every command shows where it runs.** A badge on cards, palette rows and command pages reads one of: runs in the org container, edit in the browser (config), terminal only. The All commands page is grouped into those three sections, terminal-only folded. Run is disabled on terminal-only commands with the contract's real `proxyBlockedReason`. The class is derived from the contract (`proxyCapable`, `plane`, `interactive`), never from a hand list, because remote-mcp D57 moves commands onto the executor over time.

## Confirmation, step-up, reveal

- **C11 Confirmation follows severity.** `caution` shows an amber dialog with one click; `destructive` shows a red/dark dialog with the target name typed (GitHub style) and step-up re-verification; a preview run skips both.
- **C12 Step-up order is passkey, then TOTP, then email link, then account password**: the strongest method the user holds is offered first, and the org policy may require a minimum for destructive runs. Step-up is enforced on the server at `/console/exec`, not only in the UI. The account password here is the login password, distinct from the config key slots that remote-mcp D39 removes.
- **C13 Production means a grand repo**, and an action on one always asks for explicit confirmation in a popup, in every AI autonomy mode and for humans alike.
- **C14 Reveal of secrets is off by default.** An org owner or admin can turn it on for a short window after step-up and a red popup listing the risks; the act is audited; members and agents never can.

## Audit

- **C15 Every console action is audited**: every command run, config-editor saves, policy saves, step-ups, reveals, AI approvals and feedback sends. Each event carries who, what, the target and, for destructive runs, the verification method; secret parameters are never recorded.
- **C16 Audit is a paid feature.** Records are written for every org, shown only to orgs on a paid plan (PROFESSIONAL, BUSINESS, ENTERPRISE); a trial does not count as paid. On upgrade the existing history becomes visible.
- **C17 An admin-panel field per org, "show audit starting from"**, lets Rediacc support reveal older records to an org.
- **C18 Audit lives in R2 only.** Each event is written at once as its own object; the nightly 03:00 cron compacts each org's day into one `.ndjson.gz` whose header chains the previous day's hash. This supersedes, for console audit, the D1-at-90-days ruling of `agent/plans/PLAN-d1-scaling.md`.
- **C19 Retention follows the org plan**: 2 years for paid orgs, 90 days otherwise, for all audit events; licence-state events keep their existing 400 days. A bucket lifecycle rule deletes after 2 years; the nightly sweep deletes past 90 days for non-paid orgs.
- **C20 A downgrade gets 30 days of grace**: a re-upgrade inside the window restores the older records, then the 90-day rule applies.

## Runs and the command line

- **C21 Runs are indexed on the server per org.** The executor records each run's start and end; the console reads the list across devices and teammates; the container stays awake until a run ends.
- **C22 Runs are shown as a block stream plus status-bar pills.** A docked panel on every account page holds one scrolling feed of run blocks (finished ones fold to a line, running ones stay live, filters for the viewer's own runs, the team's runs, running and failed, the prompt at the bottom); while the panel is closed, a thin status bar shows running runs as pills.
- **C23 The command line starts as a plain text box**: suggestions in a list below it, errors as text beneath, history, Tab completes the highlighted suggestion. No editor library; the VS Code look can follow later because the core is ours.
- **C24 The core is ours, in `packages/shared`**: tokenizer, completion from the contract, diagnostics and the recipe parser, shared by the web line, the panel prompt, Cmd+K command mode and `rdc __complete`. The same plan drops `reveal` from the `config_show` MCP tool schema with a coverage test that no agent-refused option reaches any MCP schema (the one MCP edit, see C4).
- **C25 Recipes ship with the command line**: team-authored multi-line sequences with variables, run step by step, step-up asked once for the destructive steps.
- **C26 Command history is stored on the server per user**, secret values masked before saving.
- **C27 Real shell completions ship with the command line**: `rdc completion bash|zsh|fish|pwsh` and a hidden `rdc __complete`, machine and repo names read from the local config.
- **C28 UI tests added are keyboard and IME contract tests** (arrow, Tab, Esc, history, combobox `aria-activedescendant`, composition through CDP). No axe scans and no screenshot baselines in this program.

## Animations

- **C29 Animations use the step names renet already emits** and nothing new from renet. Operations without steps (backup to storage, restore, cluster operations) show an indeterminate animation. Reduced-motion is honoured.

## AI assistant

- **C30 The AI assistant runs in the org container.** The executor already holds the decrypted config in memory; it reads the AI key there, runs the loop, calls `decide()` for every command and streams to the UI. Keys never reach the account Worker, which keeps the ruling at `agent/plans/PLAN-rdc-feedback.md:37`.
- **C31 Customers bring their own key**, stored as a secret leaf in the encrypted config at org or team level (a team profile overrides the org one). The provider form supports two formats, Anthropic Messages and OpenAI-compatible, with base URL, key, model, optional headers, presets (Anthropic, OpenAI, Gemini, Mistral, DeepSeek, Cloudflare AI Gateway, OpenRouter, Vercel, LiteLLM, Portkey) and a tool-calling test on save.
- **C32 Rediacc-provided AI exists only for enterprise, on credits.** Two tiers: Workers AI open models as the cheap default, Anthropic and OpenAI through Cloudflare AI Gateway Unified Billing as premium at a higher credit rate. Every guard is mandatory: prepaid only, auto top-up off, a global gateway spend cap below the purchased balance, a worst-case reservation before each call, a per-org Durable Object ledger as the hard stop, loop, token and daily caps, margin pricing, a nightly reconcile against gateway logs, per-org and global kill switches, and credit expiry.
- **C33 Autonomy has three modes per chat: Ask, Auto, Skip.** Ask runs read-only commands and shows an approval card for everything else. Auto runs read-only commands and sends the rest to a judge model that never sees command output; three blocks in a row or twenty in a chat fall back to Ask. Skip runs whatever the policy allows. In every mode `decide()`, the policy, `REDIACC_ALLOW_*`, C13 and C11 are enforced in code; org admins can disable Auto or Skip in the policy.
- **C34 The AI experience is an action timeline** extending the block stream, with structured cards and risk-grouped approvals inside it; simple view is the same timeline in plain words; "Ask about this" bars on resource pages come later, feeding the same timeline.
- **C35 Simple view is a per-user switch**: a chat-style surface with plain-language action cards, an animation while each runs, short result summaries, and "Show details" revealing the exact command and logs. The input stays at the bottom and the view follows new output.
- **C36 Always-on chat fixes**: scroll pinning that never fights a user scrolling up, with a jump-to-latest control; visible context and usage chips (org, team, config, selected resources, credits); branching from any earlier message without losing the thread.
- **C37 The chat stack is assistant-ui (MIT) on shadcn**, with use-stick-to-bottom (MIT) and Streamdown (Apache-2.0); the timeline and run cards are ours.
- **C38 The microphone engine is user-selectable**, with the fallback order browser built-in recognition, then a local in-browser model, then the provider's transcription. The transcript is editable before sending.
- **C39 The AI offers an `rdc feedback` report only when a failure has Rediacc origin** (C8). The AI writes the description; the user sends, edits or declines; a per-user setting turns the offer off and the org owner can override it for the whole org. The executor's forced `--yes` is never used for a send: the worker posts to the feedback endpoint only on the user's click.
- **C40 The AI plans depend on remote-mcp's decision function and agent grants**: `agent/plans/PLAN-rmcp-decide.md` and `agent/plans/PLAN-rmcp-agent-grants.md`, which the operator promotes ahead of the AI plans. Plans 1 to 7 of this program do not wait for them.
- **C41 Testing may use the Anthropic key held in BWS**, copied at run time through `bws_env exec` for test and live-proof boxes and never committed.
