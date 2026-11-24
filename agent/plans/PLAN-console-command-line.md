# PLAN: Console command line -- an own core in packages/shared behind a plain command box in the run panel, above every form and in Cmd+K, with team recipes and real shell completions
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-contract-semantics.md, PLAN-console-run-index.md -- completion reads that plan's summaries, severity and blocked reasons through its lazy contract (C6, C10, CS10, CS11); the panel prompt fills the run panel's prompt slot and history reads the server history of the run index plan (C22, C26); the dialogs of PLAN-console-confirm-stepup.md are box-level edges (CL6, CL7, CL10), so that plan does not join this PR's plan set
Priority: P2 -- no shell completions exist (agent/programs/console-rework/01-verified-context.md section 5) and the only typed surface is a read-only CLI line under each form (private/account/web/src/components/console/CommandForm.tsx:217); nothing is broken, and the core is the base for PLAN-console-ai-assistant.md
Concurrency: parallel -- wave 1: CL1, CL9 (file-disjoint, packages/shared); wave 2: CL2, CL3 (packages/shared/src/command-line, one writer in sequence); wave 3: CL4, CL10, CL12 (web component, account route, CLI command, disjoint); wave 4: CL6, CL7, CL8, CL11 (each owns its files); wave 5: CL13 (translations), CL14 (e2e). Shared files and their earlier owners are listed under "Ordering against other live plans".
Owns: agent/plans/PLAN-console-command-line.md, packages/shared/src/command-line/**, packages/shared/package.json, packages/cli/scripts/lib/example-parse.ts, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/config-schema/__tests__/console-recipes.test.ts, packages/cli/src/commands/completion.ts, packages/cli/src/commands/__tests__/completion*.test.ts, packages/cli/src/cli.ts, packages/cli/src/config/command-planes.ts, packages/cli/src/config/command-safety.ts, packages/cli/src/i18n/locales/*/cli.json, packages/cli/scripts/command-tree.json, packages/shared/src/cli-contract/data/**, packages/www/src/content/docs/*/cli-application.md, private/account (gitlink bump only), private/account/src/routes/console-recipes.ts, private/account/src/routes/console.ts, private/account/src/services/console-stepup.ts, private/account/tests/integration/console-recipe-grant.test.ts, private/account/web/src/components/console/command-line/**, private/account/web/src/components/console/recipes/**, private/account/web/src/components/console/Combobox.tsx, private/account/web/src/components/console/__tests__/combobox.test.tsx, private/account/web/src/components/console/runs/RunPanel.tsx, private/account/web/src/components/console/CommandForm.tsx, private/account/web/src/components/console/CliEquivalent.tsx, private/account/web/src/components/console/RunHistory.tsx, private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/__tests__/command-palette-rdc-mode.test.tsx, private/account/web/src/pages/console/CommandPage.tsx, private/account/web/src/i18n/locales/*/console.json, private/account/e2e/tests/27-console/27-05-command-line-keyboard.test.ts, private/account/e2e/tests/27-console/27-06-command-line-ime.test.ts
Live-Proof: bench -- the account web bundle with the command box, Cmd+K command mode and recipes runs against the eu bench executor (CL-L1); the `rdc completion` CLI is checked against the eu-bench config as additional verification

## Ask

C23: the command line starts as a plain text box with suggestions in a list below, errors as text beneath, history, and Tab completing the highlighted suggestion; no editor library. C24: the core is ours, in packages/shared (tokenizer, completion from the contract, diagnostics, the recipe parser), shared by the web line, the panel prompt, Cmd+K command mode and `rdc __complete`; the `reveal` MCP drop of C24 belongs to PLAN-console-contract-semantics.md CS13. C25: team-authored recipes with variables, run step by step, step-up asked once for the destructive steps. C27: `rdc completion bash|zsh|fish|pwsh` and a hidden `rdc __complete`, names from the local config. C28: keyboard and IME contract tests only.

## Context

1. The quote-aware tokenizer and the example value parser live in the generator's helper (packages/cli/scripts/lib/example-parse.ts:25, :68); only packages/cli/scripts/generate-cli-contract.ts imports it, and it returns tokens without spans.
2. `ContractCommand` carries `plane`, `interactive` and the proxy flags (packages/shared/src/cli-contract/types.ts:250, :313, :316); `ResourceKind` is the noun set of `kinds` (:81).
3. Picker values come from the unlocked config through `configOptions(resources, kind, ctx)` (private/account/web/src/lib/resource-options.ts:95) and discovery requests (:247).
4. `buildCliCommand` (private/account/web/src/lib/contract-form.ts:335) and `formValuesFromExec` (:409) already convert form values to a line and back; CommandForm holds values in react-hook-form (private/account/web/src/components/console/CommandForm.tsx:97, :105) and renders the read-only line at :217.
5. The palette ranks commands on path and description (private/account/web/src/components/console/CommandPalette.tsx:242-245).
6. The Combobox input sets `role="combobox"`, `aria-expanded` and `aria-controls` but no `aria-activedescendant` (private/account/web/src/components/console/Combobox.tsx:175-177).
7. Arabic flips the document to RTL (private/account/web/src/i18n/language.ts:71).
8. The Config file editor pushes a new config version through the shared session (private/account/web/src/pages/console/ConfigEditor.tsx:188-208); `RdcConfigSchema` is the config root (packages/shared/src/config-schema/schemas.ts:566) and `/policy` is one committed identifier leaf (packages/shared/src/config-schema/sensitivity.ts:91).
9. CLI cold start is 0.43 to 0.49 s for `rdc --version` and compiling the 22 MB bundle alone takes 0.22 to 0.25 s (packages/cli/dist/cli-bundle.cjs, measured on this host 2026-11-23); the SEA config disables the code cache (packages/cli/sea-config.json:6). Hidden commands such as `executor-daemon` (packages/cli/src/commands/executor-daemon.ts:30) stay out of the contract.
10. The CLI reference page is generated per locale into packages/www/src/content/docs/<lang>/cli-application.md (packages/www/scripts/generate-cli-docs.js:34).

## Design

D1. **Core in `packages/shared/src/command-line/`**, exported as `@rediacc/shared/command-line`, pure functions over a `CliContract` and a `ResourceSource` (`(kind, ctx) => string[] | 'locked'`): `tokenize(line)` returns tokens with `[start, end)` spans and quote state (the generator's tokenizer moves here and example-parse.ts imports it); `parse(contract, tokens)` resolves the longest command path and binds flags and positionals as `formValuesFromExec` expects; `complete(state, cursor)` returns ranked suggestions; `diagnose(state)` returns span-anchored problems; `parseRecipe(text)`; `HistoryCursor`.

D2. **Completion order.** Domains, then subcommands with their summaries (C6), then required positionals first, then flags with common before advanced (option `tier`), then values: `choices` first, then resource names for an option or positional with `kinds` when the source is unlocked, else one inert row "Unlock to suggest" that opens the unlock form. Prefix match first, then subsequence; ties by contract order.

D3. **Diagnostics.** Unknown command or flag with a nearest-match suggestion (Damerau-Levenshtein at most 2 against the command's own flags and path), a missing required positional or flag, a value outside `choices`, a flag given twice. Each carries a span and a message key; the UI prints them as text under the box.

D4. **Plain box (C23).** `CommandLine`: a native `<input>` with `role="combobox"`, a listbox below with `aria-activedescendant`, diagnostics beneath as a live region; Up and Down move in the list when open, else through history (`HistoryCursor` keeps the draft); Tab accepts the highlighted suggestion; Esc closes the list, a second Esc clears; Enter acts. Composition is respected: no key handling while `isComposing`. The input and every code span carry `dir="ltr"` and `lang="en"` so Arabic pages keep the command left to right.

D5. **Enter routes by where the command runs** (C10): proxy-capable runs through the existing exec path with the confirmation and step-up of PLAN-console-confirm-stepup.md, and the run appears in the panel; `plane: 'config'` opens the Config file editor; anything else copies the line and shows the contract's blocked reason.

D6. **Three placements.** The panel prompt fills the run panel's slot; above each command form the box replaces the read-only CliEquivalent line with two-way binding (form edits rewrite the line through `buildCliCommand`; a parsed line resets the form through `formValuesFromExec`; a line naming another command navigates to it with the values); in Cmd+K a query starting with `rdc ` switches the palette to command mode, listing the core's suggestions instead of ranked pages.

D7. **Recipes (C25).** Stored as `console.recipes` in the team's encrypted config (record by name: `description`, `body`, `updatedAt`), one committed identifier leaf like `/policy`, saved through the shared config session; zero knowledge and team scoping come from the config store.
Body: `# description` lines, `$name = required "prompt"` or `$name = "default"` declarations, then one `rdc` line per step with `$name` substitutions. Every step must be proxy-capable; a config-plane or terminal-only step is a recipe diagnostic. Running a recipe asks the variables once, shows the step plan, and runs steps in order through the panel, stopping at the first failure.

D8. **Step-up once per recipe.** When a recipe holds destructive steps, the user steps up once; `POST /console/recipes/grant` (elevated) returns a grant bound to user, org, recipe body hash and the listed destructive steps with their targets, valid until the recipe ends or 60 minutes; `/console/exec` accepts it in `console-stepup.ts` for exactly those steps.

D9. **Shell completions (C27).** `rdc completion <shell>` prints a script whose command, flag and choice words are generated from the contract through the core at print time, so static completion is pure shell; values for a resource-kind slot call the hidden `rdc __complete --kind <k> [--config <n>]`, which reads the local config file without loading the Commander tree and prints one name per line; the script caches the answer per shell session keyed on the config file's mtime. Reason: the bundle's compile alone exceeds 100 ms (Context 9), so the budget holds for static words and cached names, and only the first name lookup per config change pays one CLI start.

## Ordering against other live plans

Shared files edited after their earlier owner lands: CommandForm.tsx (PLAN-console-confirm-stepup.md CF5), CommandPage.tsx and CommandPalette.tsx (PLAN-console-contract-semantics.md CS11 and PLAN-console-run-index.md RI7), console-stepup.ts and console.ts (PLAN-console-confirm-stepup.md CF3), packages/shared/src/config-schema/schemas.ts and sensitivity.ts (PLAN-console-ai-providers.md edits them too; whichever lands second rebases), packages/cli/src/cli.ts (one register line beside PLAN-rmcp-decide.md's edits).

- PLAN-console-contract-semantics.md and PLAN-console-run-index.md land first (header edges); CL7 waits on PLAN-console-confirm-stepup.md#CF5, CL6 on #CF4 and #CF6, CL10 on #CF3.
- PLAN-console-ai-providers.md adds its own leaf to schemas.ts and sensitivity.ts; CL9 touches only the `console` key and its registry row.
- PLAN-console-ai-assistant.md reuses the core and the box; it starts after this plan.

## Tasks

- [x] CL1 [writer] Tokenizer with spans (D1): `tokenize` in packages/shared/src/command-line/tokenize.ts with the `./command-line` export in packages/shared/package.json, and packages/cli/scripts/lib/example-parse.ts importing it in place of its own `tokenizeExampleCommand`.
  Owns: packages/shared/src/command-line/tokenize.ts, packages/shared/src/command-line/index.ts, packages/shared/src/command-line/__tests__/tokenize.test.ts, packages/shared/package.json, packages/cli/scripts/lib/example-parse.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/command-line/__tests__/tokenize.test.ts)` rc 0 (quotes, escapes, an unclosed quote with its span, Arabic text inside quotes); `npm run check:ci-cli-contract` rc 0 with the generated contract byte-identical.
    (ticked) 2026-11-23T18:17:57Z by ace763dd: commit:e20b39e7ed landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CL2 [writer] Parser, completion and diagnostics (D1 to D3): `parse`, `complete` and `diagnose` over a `CliContract` and a `ResourceSource`, with the order, the locked row and the nearest-match suggestion of D2 and D3.
  Owns: packages/shared/src/command-line/parse.ts, packages/shared/src/command-line/complete.ts, packages/shared/src/command-line/diagnose.ts, packages/shared/src/command-line/__tests__/complete.test.ts, packages/shared/src/command-line/__tests__/diagnose.test.ts
  Depends on: CL1.
  Accept: `(cd packages/shared && npx vitest run src/command-line/__tests__/complete.test.ts src/command-line/__tests__/diagnose.test.ts)` rc 0 against the real generated contract: `rdc re` suggests `repo` first, `rdc repo fork ` suggests the required positional before flags, a locked source yields the unlock row, `--dyr-run` suggests `--dry-run`, a missing required value is reported with its span.
    (ticked) 2026-11-23T18:17:58Z by ace763dd: commit:e20b39e7ed landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CL3 [writer] Recipe parser and history model (D1, D7): `parseRecipe` returning variables, steps and span-anchored problems (including a non-proxy-capable step), and `HistoryCursor` with draft keeping and prefix filtering.
  Owns: packages/shared/src/command-line/recipe.ts, packages/shared/src/command-line/history.ts, packages/shared/src/command-line/__tests__/recipe.test.ts, packages/shared/src/command-line/__tests__/history.test.ts
  Depends on: CL2.
  Accept: `(cd packages/shared && npx vitest run src/command-line/__tests__/recipe.test.ts src/command-line/__tests__/history.test.ts)` rc 0: an undeclared `$var` and a `term` step are problems, a default fills, Up then Down restores the draft.
    (ticked) 2026-11-23T18:17:59Z by ace763dd: commit:e20b39e7ed landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CL4 [writer] The plain box (D4): `CommandLine` and `useCommandLine` under components/console/command-line/, a `ResourceSource` over `configOptions`, history from the run index plan's `useRunHistory`, the `dir="ltr"` rule, English strings in console.json; and `aria-activedescendant` on the existing Combobox input.
  Owns: private/account/web/src/components/console/command-line/**, private/account/web/src/components/console/Combobox.tsx, private/account/web/src/components/console/__tests__/combobox.test.tsx, private/account/web/src/i18n/locales/en/console.json
  Depends on: CL3, PLAN-console-run-index.md#RI7.
  Accept: `(cd private/account/web && npx vitest run src/components/console/command-line src/components/console/__tests__/combobox.test.tsx)` rc 0: Tab accepts the highlighted row, Up and Down move the list then the history, Esc closes then clears, no key acts while composing, `aria-activedescendant` names the highlighted option in both components.
    (ticked) 2026-11-24T21:44:01Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [x] CL5 [writer] Enter routing (D5): `routeCommand(entry)` in components/console/command-line/route.ts returning run, open-config or copy-with-reason, with run delegating to the exec path and the confirmation of PLAN-console-confirm-stepup.md.
  Owns: private/account/web/src/components/console/command-line/route.ts, private/account/web/src/components/console/command-line/__tests__/route.test.ts
  Depends on: CL4.
  Accept: `(cd private/account/web && npx vitest run src/components/console/command-line/__tests__/route.test.ts)` rc 0 over every contract command: each lands in exactly one route, and a copy carries a non-empty blocked reason.
    (ticked) 2026-11-24T21:44:02Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [x] CL6 [writer] Panel prompt (D6): the box rendered in the run panel's prompt slot, Enter on a runnable line opening the confirmation and adding the run to the feed.
  Owns: private/account/web/src/components/console/runs/RunPanel.tsx, private/account/web/src/components/console/command-line/PanelPrompt.tsx, private/account/web/src/components/console/command-line/__tests__/panel-prompt.test.tsx
  Depends on: CL5, PLAN-console-run-index.md#RI8, PLAN-console-confirm-stepup.md#CF4, PLAN-console-confirm-stepup.md#CF6.
  Accept: `(cd private/account/web && npx vitest run src/components/console/command-line/__tests__/panel-prompt.test.tsx)` rc 0: a destructive line opens the red dialog, a read-only line runs at once and shows a block.
    (ticked) 2026-11-24T21:44:03Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [x] CL7 [writer] Two-way form binding (D6): the box above each command form in CommandPage, CommandForm taking external values and reporting changes, CliEquivalent.tsx removed and RunHistory's copy line built by `buildCliCommand` directly.
  Owns: private/account/web/src/pages/console/CommandPage.tsx, private/account/web/src/components/console/CommandForm.tsx, private/account/web/src/components/console/CliEquivalent.tsx, private/account/web/src/components/console/RunHistory.tsx, private/account/web/src/components/console/command-line/__tests__/form-binding.test.tsx
  Depends on: CL5, PLAN-console-confirm-stepup.md#CF5.
  Accept: `(cd private/account/web && npx vitest run src/components/console/command-line/__tests__/form-binding.test.tsx)` rc 0: typing a flag sets the field, editing the field rewrites the line, a line naming another command navigates; `git grep -n "CliEquivalent" -- private/account/web/src` prints nothing.
    (ticked) 2026-11-24T21:44:04Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [x] CL8 [writer] Cmd+K command mode (D6): a palette query starting with `rdc ` lists the core's suggestions and diagnostics, Tab completes, Enter routes through `routeCommand`.
  Owns: private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/__tests__/command-palette-rdc-mode.test.tsx
  Depends on: CL5.
  Accept: `(cd private/account/web && npx vitest run src/components/console/__tests__/command-palette-rdc-mode.test.tsx)` rc 0: `rdc repo` lists subcommands with summaries, a plain query still ranks pages and commands.
    (ticked) 2026-11-24T21:44:05Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [x] CL9 [writer] Recipes leaf (D7): `console.recipes` in `RdcConfigSchema` and `/console/recipes` as one committed identifier row in the sensitivity registry.
  Owns: packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/config-schema/__tests__/console-recipes.test.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/config-schema/__tests__/console-recipes.test.ts src/config-schema/__tests__/coverage.test.ts)` rc 0 and `npm run check:ci-schema-coverage` rc 0.
    (ticked) 2026-11-24T21:44:21Z by d778be9d: CL9 landed; console-recipes and coverage tests pass, check:ci-schema-coverage rc 0
- [x] CL10 [writer] Recipe step-up grant (D8): `routes/console-recipes.ts` with `POST /console/recipes/grant` behind `requireElevated()`, one mount line in console.ts, and console-stepup.ts accepting the grant for exactly its listed destructive steps.
  Owns: private/account/src/routes/console-recipes.ts, private/account/src/routes/console.ts, private/account/src/services/console-stepup.ts, private/account/tests/integration/console-recipe-grant.test.ts
  Depends on: PLAN-console-confirm-stepup.md#CF3.
  Accept: `(cd private/account && npx vitest run tests/integration/console-recipe-grant.test.ts)` rc 0: a listed step passes without a fresh elevation, an unlisted destructive step is refused, a changed body hash is refused, a grant past 60 minutes is refused, another user's grant is refused.
    (ticked) 2026-11-24T21:44:06Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [x] CL11 [writer] Recipes UI (D7, D8): a recipes dialog opened from the panel prompt listing, editing (the core's diagnostics under the text area) and saving recipes through the shared config session, and a runner asking variables once, taking the grant once when a step is destructive, and running steps through the panel.
  Owns: private/account/web/src/components/console/recipes/**
  Depends on: CL3, CL6, CL9, CL10.
  Accept: `(cd private/account/web && npx vitest run src/components/console/recipes)` rc 0: a save pushes a new config version, a run with two destructive steps asks step-up once, a failed step stops the run.
    (ticked) 2026-11-24T21:44:07Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [ ] CL12 [writer] Shell completions (D9): `rdc completion bash|zsh|fish|pwsh` and the hidden `rdc __complete` in packages/cli/src/commands/completion.ts, registered in cli.ts, a plane entry in command-planes.ts, a `none` row in command-safety.ts, English help strings in cli.json, then the contract, command-tree.json and the CLI reference pages regenerated.
  Owns: packages/cli/src/commands/completion.ts, packages/cli/src/commands/__tests__/completion*.test.ts, packages/cli/src/cli.ts, packages/cli/src/config/command-planes.ts, packages/cli/src/config/command-safety.ts, packages/cli/src/i18n/locales/en/cli.json, packages/cli/scripts/command-tree.json, packages/shared/src/cli-contract/data/**, packages/www/src/content/docs/*/cli-application.md
  Depends on: CL2.
  Accept: `(cd packages/cli && npx vitest run src/commands/__tests__/completion.test.ts)` rc 0: each shell's script passes its syntax check (`bash -n`, `zsh -n`, `fish --no-execute` where installed), static words match the contract, `__complete --kind repo` prints the repos of a fixture config; `npm run check:ci-cli-contract`, `npm run check:ci-command-tree` and `npm run check:cli-docs` rc 0; a timing test shows the generated bash completion of `rdc repo f` under 100 ms p50 over 20 runs.
- [ ] CL13 [writer] Translations: the new console.json keys into the 12 other web locales and the completion help keys into the 12 other CLI locales, naturalized per docs/i18n/CONVENTIONS.md, writers on sonnet.
  Owns: private/account/web/src/i18n/locales/*/console.json, packages/cli/src/i18n/locales/*/cli.json
  Depends on: CL4, CL6, CL7, CL8, CL11, CL12.
  Accept: `npm run check:ci-i18n-account-key-usage` rc 0, `npm run check:ci-i18n-cli-key-usage` rc 0, and `npm run ci -- --narrow` rc 0.
- [x] CL14 [writer] Keyboard and IME contract tests (C28): arrow, Tab, Esc, history and `aria-activedescendant` on the panel prompt, the form line and Cmd+K; composition through CDP `Input.imeSetComposition` then `Input.insertText` asserting no suggestion is accepted mid-composition and the committed text lands; an Arabic page keeps the box `dir="ltr"`.
  Owns: private/account/e2e/tests/27-console/27-05-command-line-keyboard.test.ts, private/account/e2e/tests/27-console/27-06-command-line-ime.test.ts
  Depends on: CL6, CL7, CL8.
  Accept: `(cd private/account/e2e && npx playwright test tests/27-console/27-05-command-line-keyboard.test.ts tests/27-console/27-06-command-line-ime.test.ts --project=chromium)` rc 0.
    (ticked) 2026-11-24T21:44:08Z by d778be9d: landed in 2f4a1cec99: console command line cluster, web vitest console and pages 953 passed, web tsc rc 0, keyboard and IME e2e passed in the lease
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) so CL-L1 drives the bundle this branch builds; cli-bench runs as additional verification for `rdc completion`.
  Accept: live-proof bench account-smoke
- [ ] CL-L1 [live] eu bench: type `rdc repo fork <repo> --tag t1` in the panel prompt with Tab completion of the repo name, run it, then run a two-step recipe holding one destructive step (step-up asked once), and source `./rdc.sh --config eu-bench completion bash` in a bash shell to complete a bench repo name. Local-route: deploy-bench, bench-cli -- the branch account Worker serves the eu bench portal and the CLI from this tree reads the eu-bench config.
  Depends on: LP-bench.
  Accept: the transcript, the panel's two run rows and the completion output recorded in this plan.

## Risks

- A sourced completion script goes stale after a CLI upgrade; `eval "$(rdc completion bash)"` in the shell profile regenerates it per shell start at the cost of one CLI start.
- `console.recipes` is a committed leaf, so a recipe edit racing a config push conflicts like any committed field and the editor shows the existing conflict path.
- The core runs on every keystroke over 231 commands; the parse is linear in tokens, and CL2's test keeps a 1 ms per call ceiling on the real contract.
