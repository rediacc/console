# PLAN: Console information architecture -- Variant A labels, a runs-where badge on every command, grouped reference, terminal-only pages and a real landing
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-contract-semantics.md -- cards and palette rows show the contract `summary`, and the terminal-only page shows the translated `proxyBlockedReasonKey`, both added by that plan, and that plan's CS11 moves the console pages onto the lazy contract this plan builds on
Priority: P1 -- 69 commands (47 on plane `other`, 22 non-proxyable on plane `machine`) show an enabled Run that the executor refuses, and the landing's 22 domain cards all open the same unfiltered list
Concurrency: parallel -- wave 1: IA1 (every string), IA2 (helper and badge); wave 2 after both: IA3, IA4, IA5, IA6, IA7 (file-disjoint); wave 3: IA8 (e2e), IA9 (lead). IA1 is the only box that adds keys to the locale files; IA5 only deletes `notProxyCapableHint`. agent/plans/PLAN-rmcp-policy-record.md W1 also edits console.json, key-disjoint from this plan
Owns: agent/plans/PLAN-console-ia.md, private/account/web/src/i18n/locales/*/nav.json, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/*/backupStorage.json, private/account/web/src/i18n/locales/.translation-hashes.json, private/account/web/src/pages/__tests__/backup-storage-*.test.tsx, private/account/e2e/tests/27-console/27-01-console.test.ts, private/account/web/src/lib/runs-where.ts, private/account/web/src/lib/__tests__/runs-where.test.ts, private/account/web/src/lib/contract-i18n.tsx, private/account/web/src/components/console/RunsWhereBadge.tsx, private/account/web/src/lib/command-groups.ts, private/account/web/src/lib/__tests__/command-groups.test.ts, private/account/web/src/pages/console/Commands.tsx, private/account/web/src/pages/console/Console.tsx, private/account/web/src/pages/console/CommandPage.tsx, private/account/web/src/pages/console/__tests__/**, private/account/web/src/components/console/CommandForm.tsx, private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/__tests__/command-palette.test.ts, private/account/web/src/components/console/__tests__/command-form-runs-where.test.tsx, private/account/web/src/lib/__tests__/nav-label-collisions.test.ts
Live-Proof: bench -- the account web console bundle (nav labels, Commands, palette, command pages, landing); LP-bench runs account-smoke after deploy_bench

## Ask

Navigation is Variant A: the sidebar redesign rulings stand (licence page "Machines", console page "Console machines", ruling O2), and five labels change while routes do not: "Getting started" to "Get started", "Backup storage" to "Backup quota", "Config storage" to "Encrypted config sync", "Commands" to "All commands", "Config" to "Config file" (C9). Every command shows where it runs: org container, edit in the browser (config) or terminal only, on cards, palette rows and command pages; All commands is grouped into those three sections with terminal-only folded; Run is disabled on terminal-only commands with the contract's real `proxyBlockedReason`; the class is derived from the contract, never from a hand list (C10).

## Context

1. The five labels are `nav:item.gettingStarted`, `nav:item.backupStorage`, `nav:item.configStorage` (private/account/web/src/i18n/locales/en/nav.json:4, private/account/web/src/i18n/locales/en/nav.json:6, private/account/web/src/i18n/locales/en/nav.json:12), `console:navCommands` and `console:navConfig` (private/account/web/src/i18n/locales/en/console.json:4, private/account/web/src/i18n/locales/en/console.json:111), read by private/account/web/src/lib/nav-config.ts:111, private/account/web/src/lib/nav-config.ts:119, private/account/web/src/lib/nav-config.ts:135, private/account/web/src/lib/nav-config.ts:140 and private/account/web/src/lib/nav-config.ts:166. The admin Platform group reuses `nav:item.configStorage` (private/account/web/src/lib/nav-config.ts:255).
2. `console:navStorages` (private/account/web/src/i18n/locales/en/console.json:63) is referenced by no source file; the storage domain was retired.
3. Page headings repeat two of the labels word for word: `console:commandsTitle` (private/account/web/src/i18n/locales/en/console.json:10) and `console:configEditorTitle` (private/account/web/src/i18n/locales/en/console.json:113), and `backupStorage:pageTitle` (private/account/web/src/i18n/locales/en/backupStorage.json:3), which two unit tests find by text (private/account/web/src/pages/__tests__/backup-storage-live-waiting.test.tsx:63).
4. The e2e check clicks `getByRole('link', { name: 'Config', exact: true })` (private/account/e2e/tests/27-console/27-01-console.test.ts:307).
5. Contract classes counted on 2026-11-23 (`proxyCapable`, `plane`, `interactive`): 96 proxy-capable machine commands; 55 config-plane non-interactive; 80 others (47 on `other`, 22 non-proxyable `machine`, 11 interactive).
6. CommandForm disables Run for interactive, config-plane and locked cases only (private/account/web/src/components/console/CommandForm.tsx:130), so the 69 non-interactive commands outside those classes keep Run enabled and show the fixed `notProxyCapableHint` (private/account/web/src/components/console/CommandForm.tsx:256) instead of the contract's reason. The config-plane case already links to the editor (private/account/web/src/components/console/CommandForm.tsx:238).
7. Commands groups by domain only (private/account/web/src/pages/console/Commands.tsx:25) and shows the long label and a destructive badge; the palette marks only destructive rows (private/account/web/src/components/console/CommandPalette.tsx:301); CommandPage shows the raw plane as a badge (private/account/web/src/pages/console/CommandPage.tsx:145).
8. The landing maps every domain card to the same `/commands` link (private/account/web/src/pages/console/Console.tsx:39). Unlocked resources come from `ConsoleResources` (private/account/web/src/components/console/ResourceContext.tsx:53), whose `ready` is false while locked.
9. Ruling O2 is at agent/plans/PLAN-account-sidebar-redesign.md:82; the existing nav test already pins the Machines and Console machines split by route (private/account/web/src/lib/__tests__/nav-config.test.ts:84) but nothing checks label collisions.

## Design

D1. **One string box.** IA1 changes the five labels, makes each page heading that repeats its nav label word for word follow it (`console:commandsTitle`, `console:configEditorTitle`, `backupStorage:pageTitle`), deletes `console:navStorages`, and adds every new key this plan renders: the three badge labels and tooltips, the three section titles, the fold toggle with a count, the browser-card link "Edit in Config file", the terminal-only Run note, and the landing strings (unlock call to action, resource counts, All commands entry). The admin Platform item keeps sharing `nav:item.configStorage`, so it reads "Encrypted config sync" too: one feature, one name. Translations into the 12 other locales are naturalized by a sonnet writer.

D2. **One classifier**, `runsWhere(entry)` in private/account/web/src/lib/runs-where.ts: `container` when `proxyCapable`; `browser` when `plane === 'config'` and not `interactive`; `terminal` otherwise. No command name appears in it (private/account/web/src/lib/contract-form.ts:11 forbids branching on ids), so a command remote-mcp D57 moves onto the executor changes class with the next contract. `RunsWhereBadge` renders the class with an icon and the translated label, used on cards, palette rows and CommandPage.

D3. **All commands, grouped.** Three sections in the order container, browser, terminal; terminal starts folded behind a toggle that names its count.
Inside a section, commands group by domain (`path[0]`), and inside a domain, commands sharing `path[1]` with at least two members form a sub-group; `groupByPath()` in private/account/web/src/lib/command-groups.ts derives this from contract paths, so no count is hardcoded. Cards show the translated `summary`, the badge and, for `browser`, a link to the Config file editor. Search filters across all sections and unfolds terminal when a match is there.

D4. **Terminal-only command page.** CommandForm adds `runsWhere(entry) === 'terminal'` to the Run-disabled condition and replaces `notProxyCapableHint` with the contract's reason translated through `proxyBlockedReasonKey` (English `proxyBlockedReason` as the fallback when a bundle lacks the key); the form and its CLI line stay, so the page still teaches the command. `notProxyCapableHint` is deleted from the 13 locales.

D5. **Landing.** The domain grid goes. Locked: an unlock call to action that opens the existing unlock flow. Unlocked: counts of machines, repositories, datastores and the other config families from `ConsoleResources`, each linking to its page. Always: the palette hint and an All commands entry with the contract's command count.

D6. **Collision test, not a gate.** private/account/web/src/lib/__tests__/nav-label-collisions.test.ts resolves every item label per mode in all 13 locales and fails when two labels in different groups are equal or one's word set is contained in the other's. The allowlist holds one pair, `machines` and `consoleMachines`, citing ruling O2; a locale that collides elsewhere gets its translation fixed rather than an allowlist row.

## Ordering against other live plans

- agent/plans/PLAN-console-contract-semantics.md lands first (CS4 to CS7 for summaries and reason keys, CS11 for the lazy contract in these pages).
- agent/plans/PLAN-console-confirm-stepup.md edits CommandForm.tsx and DestructiveConfirm for severity dialogs after this plan; IA5 touches only the Run-disabled condition and the hint.
- agent/plans/PLAN-account-sidebar-redesign.md has only lead and live boxes open, so nav.json is free; its rulings stand.

## Tasks

- [x] IA1 [writer] Strings (D1): the five label changes, the three heading changes, `console:navStorages` deleted, and every new key of D1 in English, then the same in the 12 other locales naturalized by a sonnet writer per docs/i18n/CONVENTIONS.md; private/account/e2e/tests/27-console/27-01-console.test.ts:307 now finds `Config file`, and the two backup-storage unit tests find `Backup quota`.
  Owns: private/account/web/src/i18n/locales/*/nav.json, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/*/backupStorage.json, private/account/web/src/i18n/locales/.translation-hashes.json, private/account/web/src/pages/__tests__/backup-storage-*.test.tsx, private/account/e2e/tests/27-console/27-01-console.test.ts
  Depends on: PLAN-console-contract-semantics.md#CS11.
  Accept: `npm run i18n:generate-hashes` then `npm run check:i18n:hashes`, `npm run check:i18n:completeness` and `npm run check:ci-i18n-naturalization` rc 0; `(cd private/account/web && npm test)` rc 0; `git grep -n navStorages -- private/account/web/src` prints nothing.
    (ticked) 2026-11-24T12:47:10Z by d778be9d: landed account 50df1217 (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
    (corrected 2026-11-27T04:34:40Z, f36152b1.2) The tick above is the IA1 evidence, though it names no gate of the Accept; those that run on the tree at 2026-11-27T04:34:40Z: `npm run check:i18n:completeness` rc 0, `npm run check:ci-i18n-naturalization` rc 0, and `grep -rn navStorages private/account/web/src` prints nothing (rc 1). `npm run check:i18n:hashes` is rc 1 on this tree for one new CLI key (`errors.agent.policyUnjudged`), another surface and a later commit than IA1.
- [x] IA2 [writer] Classifier and badge (D2): `runsWhere()` and `RunsWhereBadge`, plus `useSummary()` and `useBlockedReason()` in contract-i18n.tsx reading `summaryKey` and `proxyBlockedReasonKey` with the English fields as fallback.
  Owns: private/account/web/src/lib/runs-where.ts, private/account/web/src/lib/__tests__/runs-where.test.ts, private/account/web/src/components/console/RunsWhereBadge.tsx, private/account/web/src/lib/contract-i18n.tsx
  Depends on: PLAN-console-contract-semantics.md#CS11.
  Accept: `(cd private/account/web && npx vitest run src/lib/__tests__/runs-where.test.ts)` rc 0, asserting that the three classes partition every contract command, that each class matches its rule, and a fixture control per class (a config-plane interactive command lands in `terminal`).
    (ticked) 2026-11-24T12:47:11Z by d778be9d: landed account 53355271 (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [x] IA3 [writer] All commands page (D3): three sections with terminal folded, `groupByPath()` sub-groups, summaries and badges on cards, the Config file link on browser cards, and search across sections.
  Owns: private/account/web/src/pages/console/Commands.tsx, private/account/web/src/lib/command-groups.ts, private/account/web/src/lib/__tests__/command-groups.test.ts, private/account/web/src/pages/console/__tests__/commands-page.test.tsx
  Depends on: IA1, IA2.
  Accept: `(cd private/account/web && npx vitest run src/lib/__tests__/command-groups.test.ts src/pages/console/__tests__/commands-page.test.tsx)` rc 0, covering section order, terminal folded by default, a sub-group formed only at two or more members, and a search hit inside terminal unfolding it.
    (ticked) 2026-11-24T12:47:12Z by d778be9d: landed account fecab172 (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [x] IA4 [writer] Palette rows (D2, D3): the badge and the translated summary on every command row, ranking unchanged.
  Owns: private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/__tests__/command-palette.test.ts
  Depends on: IA1, IA2.
  Accept: `(cd private/account/web && npx vitest run src/components/console/__tests__/command-palette.test.ts)` rc 0 with a row of each class rendering its badge.
    (ticked) 2026-11-24T12:47:13Z by d778be9d: landed account 3e51d42d (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [x] IA5 [writer] Command page and form (D4): the badge in place of the raw plane badge, Run disabled for terminal-only commands with the translated contract reason, and `notProxyCapableHint` deleted from the 13 locales.
  Owns: private/account/web/src/pages/console/CommandPage.tsx, private/account/web/src/components/console/CommandForm.tsx, private/account/web/src/components/console/__tests__/command-form-runs-where.test.tsx, private/account/web/src/i18n/locales/*/console.json
  Depends on: IA1, IA2.
  Accept: `(cd private/account/web && npx vitest run src/components/console/__tests__/command-form-runs-where.test.tsx)` rc 0: a terminal-only machine command (`repo sync upload`) and an `other`-plane command both render Run disabled with their own reason, a container command keeps Run enabled; `npm run check:ci-i18n-account-key-usage` rc 0.
    (ticked) 2026-11-24T12:47:14Z by d778be9d: landed account 33c32477 (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [x] IA6 [writer] Landing (D5): the domain grid replaced by the locked unlock call to action, the unlocked resource counts with links, the palette hint and the All commands entry.
  Owns: private/account/web/src/pages/console/Console.tsx, private/account/web/src/pages/console/__tests__/console-landing.test.tsx
  Depends on: IA1, IA2.
  Accept: `(cd private/account/web && npx vitest run src/pages/console/__tests__/console-landing.test.tsx)` rc 0 with a locked case (call to action, no counts) and an unlocked case (counts equal to the fixture families, the All commands link carrying the contract's count).
    (ticked) 2026-11-24T12:47:15Z by d778be9d: landed account f0c57d33 (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [x] IA7 [writer] Nav label collision test (D6) with the one O2 allowlist pair and a control fixture where "Config" and "Config file" in different groups fail.
  Owns: private/account/web/src/lib/__tests__/nav-label-collisions.test.ts
  Depends on: IA1.
  Accept: `(cd private/account/web && npx vitest run src/lib/__tests__/nav-label-collisions.test.ts)` rc 0 across 13 locales, and the test fails with the O2 allowlist row removed.
    (ticked) 2026-11-24T12:47:15Z by d778be9d: landed account 570d1a3b (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [x] IA8 [writer] E2E for the new structure: All commands shows the three sections with terminal folded, a terminal-only command page shows Run disabled with its reason, and the landing shows the All commands entry.
  Owns: private/account/e2e/tests/27-console/27-01-console.test.ts
  Depends on: IA3, IA5, IA6.
  Accept: `npx playwright test tests/27-console/27-01-console.test.ts` in private/account/e2e rc 0 against the local account dev stack.
    (ticked) 2026-11-24T12:47:16Z by d778be9d: landed account b43d586e (gitlink 8e87753bfc); account+web tsc rc 0, web console 597 passed, Web Console e2e 22 passed. DEPS-WAIVED per survey f8c0541b
- [ ] IA9 [lead] Plan-record refresh after the plan file is committed: `npm run check:ci-plan-boxes -- --update` and `npm run check:ci-plan-record -- --update`.
  Depends on: none.
  Accept: both checks rc 0 after the regeneration and `npm run check:ci-prose-style` rc 0 on this file.
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and run the console smoke; additional verification: on the bench portal the sidebar shows the five new labels, All commands shows three sections, and a terminal-only command page has Run disabled.
  Accept: live-proof bench account-smoke

## Risks

- **A label change breaking a test that matches text.** IA1 sweeps private/account/web/src and private/account/e2e for each old label and heading before committing, and runs both suites.
- **A class drifting as remote-mcp moves commands.** D2 reads only contract fields, and IA2's partition test counts against the live contract, so a moved command changes class without a code edit.
- **A translated label colliding with another.** IA7 runs all 13 locales and allows only the O2 pair.
