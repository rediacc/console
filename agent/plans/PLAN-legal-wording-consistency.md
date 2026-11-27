# PLAN: Legal wording consistency: privacy policy and DPA version, telemetry policy, MCP destructive flags

Status: Draft
Depends-On: no-dep -- builds on the landed legal registry, the DPA forensics text and the MCP docs tables
Priority: P2
Concurrency: parallel -- wave 1: L1, L2, L5 (file-disjoint); wave 2: L3a, L3b, L3c after L1 (disjoint locale files); wave 3: L4 after L3a-c and L5; L6 (lead) after all
Owns: packages/www/src/i18n/translations/*.json, packages/www/src/i18n/translations/.translation-hashes.json, packages/www/src/i18n/translations/.naturalized-hashes.json, .ci/config/legal-documents.json, packages/www/public/legal/archive/**, packages/shared/src/legal/documents.generated.ts, scripts/gates/check-terms-version.ts, packages/cli/src/config/command-metadata.ts, docs/design/spec/03-cli-contracts.md, packages/shared/src/mcp/tools.generated.json, packages/shared/src/mcp/__tests__/tools-list.snapshot.json, packages/shared/src/cli-contract/data/**, packages/www/src/content/docs/*/ai-agents-mcp.md, scripts/gates/check-mcp-docs-parity.ts, scripts/gen/i18n-stamp-keys.ts, scripts/__tests__/i18n-stamp-keys.control.ts
Owner: d778be9d
Updated: 2026-11-26
Live-Proof: bench -- the new legal archives and the MCP docs tables render on the bench www deploy, and `rdc mcp` on bench lists both tools as destructive
Item: #fc7058c7

## Context

1. The hero line of every legal document is part of the archived text: `renderDocument` in `scripts/gen/gen-legal.ts` puts `hero.effectiveDate` on line 2. Privacy (`pages.privacyPolicy.hero.effectiveDate`) and DPA (`pages.dataProcessingAgreement.hero.effectiveDate`) still say "Effective Date: November 11, 2026", so the immutable archives privacy-policy-2026-11-24, data-processing-agreement-2026-11-24 and data-processing-agreement-2026-11-25 contradict their registry dates (75bdcc72.1, 75bdcc72.2, a473201c.2). Nothing checks this today.
2. Privacy `sections.dataSharing.items.2` says no telemetry is shared with third parties, while DPA section 7 lists Hostinger as the host of the telemetry endpoint (75bdcc72.3). Telemetry policy `sections.dataProcessing.items.3` carries the same claim.
3. DPA `sections.scope.content.2` says Customer Data on the Customer's Machines is not processed by Rediacc, while section 4 has Rediacc process forensics evidence from those machines (a473201c.3).
4. Privacy `dataSharing.items.4` lists the model provider as a recipient, while DPA `subprocessors.content2.2` says the provider is not a subprocessor (4f4dc043.1).
5. Any English change to a registry document trips check 1 of `npm run check:ci-terms-version` unless a new version entry exists; `gen-legal.ts --write` archives only the newest version. `material` drives acceptance only for the Terms of Service; for privacy and DPA it records whether the 30-day notice applies.
6. MCP: `packages/cli/src/config/command-metadata.ts` gives `config prune` and `backup toc-key sync` `destructive: false`, although prune deletes by default and `--replace` overwrites a key (f416cc62.1, f416cc62.3). Spec 03 section 5 calls prune non-destructive on purpose and is amended with it. Nine locale MCP tables (de, es, et, fr, ko, pt, ru, tr, zh) still carry a bare `<config>` path; English is already escaped by `escapeAngles`.
7. Locale legal keys are hand-translated and stamped; the stamp tool never rewrites an existing ledger entry, which has needed a one-off script twice.

## Design

D1. Version D is the UTC date of the L1 commit (expected 2026-11-26). New entries `privacy-policy {version: D, effective: D, material: false}` and `data-processing-agreement {version: D, effective: D, material: false}`; the privacy, DPA and telemetry heroes read the D date. The three superseded archives stay as they are.

D2. Materiality: non-material by default (the operator's decision, parked on #fc7058c7). The changes correct disclosures to match practice already published in the DPA; no processing, purpose or recipient changes.

D3. English wording, verbatim, shared phrases "neither selects it nor instructs it" and "own agreement with it":
- privacy `dataSharing.items.2`: `<strong>Telemetry processing</strong> for anonymized product usage data, which is sent to our own telemetry endpoint in the European Union for aggregation and analysis. The endpoint runs on virtual servers provided by Hostinger, which hosts the data for us as our processor, listed in our <a href="data-processing-agreement">Data Processing Agreement</a>, and does not use it for its own purposes. We do not sell telemetry data or share it with anyone else (see our <a href="telemetry-policy">Telemetry Policy</a>)`
- privacy `dataSharing.items.4`: `<strong>The model provider you connect</strong>, at your direction, when you use an AI agent through remote MCP: tool output returned to the agent goes to that provider, which processes it under your own agreement with it. That provider is not our processor or subprocessor, because Rediacc neither selects it nor instructs it. Some connectors, such as the Claude API MCP connector, are not eligible for zero data retention`
- DPA `scope.content.2`: `Apart from the network forensics evidence described in Section 4, which Rediacc receives only for a repository on which the Customer turns forensics on, Rediacc does not process Customer Data on the Customer's Machines. Encrypted configuration storage and hosted backups are encrypted with keys Rediacc does not hold, so Rediacc stores those blobs but cannot read their contents.`
- telemetry `dataProcessing.items.3`: `<strong>No third-party sharing:</strong> Telemetry data is not sold, and not shared with anyone for their own use. It is stored on virtual servers in the European Union provided by Hostinger, which hosts it for us as our processor (see our <a href="data-processing-agreement">Data Processing Agreement</a>).`
- the three `hero.effectiveDate` values: `Effective Date: <D as "November 26, 2026">`.

D4. Check 7 in check-terms-version: line 2 of every archive equals `Effective Date: ` plus its registry `effective` (en-US long date, UTC). A frozen `SUPERSEDED_ARCHIVES` record exempts the three known files by name, each with `supersededBy: D` and its defects, printed on every run; selftest controls for a wrong hero date and a fourth exemption.

D5. MCP flags: both entries become `destructive: true` with rewritten comments; spec 03 section 5 and its decision table amended; `COMMAND_SEVERITY` unchanged. Regenerate the CLI contract, the MCP registry, the tools/list snapshot and the English doc region; hand-edit the 12 locale tables' Destructive cells and code-span the bare path in the nine locales.

D6. Parity gate, two new checks per translated table: Destructive cells grouped by `destructiveHint` use exactly one value per group and the two values differ; a raw `<word>` outside a code span is a finding. Both with selftest controls.

D7. Locale deltas of the seven keys in 12 locales: tags and link targets exact, product names kept, the date in each locale's long form, natural legal phrasing ("not our processor or subprocessor" never becomes "not a third party"). Locale writers do not touch either ledger file.

D8. `i18n-stamp-keys.ts --restamp` rewrites an existing ledger entry only where the locale value differs from HEAD, with the normal refusals; otherwise it lists the key.

## Boxes

- [x] L1 [writer] Apply the D3 English values and the D date to en.json, add the two D1 entries without sha256 to `.ci/config/legal-documents.json`, run `npx tsx scripts/gen/gen-legal.ts` (dry run lists exactly 2 new archives, the manifest and documents.generated.ts), then `--write` and `npm run i18n:generate-hashes -- --surface www`. Accept: `npm run check:ci-terms-version` rc 0 and line 2 of both new archives is the D date.
    (ticked) 2026-11-26T17:01:47Z by d778be9d: L1 landed, check:ci-terms-version rc 0 commit:ddd7e99e4b
- [x] L1b [writer] Check 7 and `SUPERSEDED_ARCHIVES` per D4 with the two selftest controls. Accept: `npm run check:ci-terms-version` rc 0 with the three superseded entries printed and both controls PASS.
    (ticked) 2026-11-26T17:01:49Z by d778be9d: L1b landed, check:ci-terms-version rc 0 with the three superseded entries printed commit:af26b78dcf
    (corrected 2026-11-27, review 8f1097f9.1) The tick did not record the two controls its Accept names. Re-run on the current tree: `npx tsx scripts/gates/check-terms-version.ts --selftest` rc 0, "all controls fired", with the controls "a fourth SUPERSEDED_ARCHIVES entry is red" and "an exemption for an archive versioned on or after CHECK7_SINCE is red" both PASS; `npm run check:ci-terms-version` rc 0 printing the three superseded entries.
- [x] L2 [writer] MCP flags per D5 and parity checks per D6. Accept: `cd packages/cli && npx vitest run src/commands/mcp src/config` rc 0, `npm run check:ci-cli-contract` rc 0, `npm run check:ci-mcp-docs-parity` rc 0 with both new controls PASS.
    (ticked) 2026-11-26T15:46:36Z by d778be9d: L2 landed, check:ci-mcp-docs-parity and check:ci-cli-contract rc 0 commit:154bfe13fb
- [x] L3a [writer] D7 deltas for ar, de, es, et after L1. Accept: all seven keys differ from HEAD in each of the four locales and the stamp dry run rc 0.
    (ticked) 2026-11-26T17:08:21Z by d778be9d: L3a landed, seven keys differ from HEAD in each locale, stamp dry run rc 0 commit:394d10666b
- [x] L3b [writer] D7 deltas for fr, it, ja, ko after L1. Accept: as L3a.
    (ticked) 2026-11-26T17:08:22Z by d778be9d: L3b landed, seven keys differ from HEAD in each locale, stamp dry run rc 0 commit:85335d81b4
- [x] L3c [writer] D7 deltas for pt, ru, tr, zh after L1. Accept: as L3a.
    (ticked) 2026-11-26T17:08:23Z by d778be9d: L3c landed, seven keys differ from HEAD in each locale, stamp dry run rc 0 commit:76ce683f14
- [x] L5 [writer] `--restamp` per D8 with controls (re-translated stale key restamped, unchanged stale key listed only, placeholder mismatch refused). Accept: `npx tsx scripts/__tests__/i18n-stamp-keys.control.ts` rc 0.
    (ticked) 2026-11-26T15:26:15Z by d778be9d: L5 --restamp landed, npx tsx scripts/__tests__/i18n-stamp-keys.control.ts rc 0 commit:9baa26e9fb
- [x] L4 [writer] Stamp the four new-ledger keys, restamp the three existing ones, run `npm run i18n:generate-hashes` and `npm run i18n:naturalize-status` after L3a-c and L5. Accept: `npm run check:i18n`, `npm run check:ci-terms-version` and `npm run check:ci-prose-style` rc 0.
    (ticked) 2026-11-26T17:32:29Z by d778be9d: L4 landed, check:i18n rc 0, naturalize-status fresh commit:b6238aa1a9
    (corrected 2026-11-27, review 5d26e634.4) The tick omitted two of the three Accept commands. Re-run on the current tree: `npm run check:ci-terms-version` rc 0 and `npm run check:ci-prose-style` rc 0 ("no new findings").
- [ ] L6 [lead] Close 4f4dc043.1 with the L1 sha, f416cc62.1 and f416cc62.3 with the L2 sha, and 75bdcc72.1-.3 and a473201c.2-.3 with the L1b sha and `--test scripts/gates/check-terms-version.ts`. Accept: `npm run check:ci-review-resolutions` rc 0.
    (corrected 2026-11-27, review 8f1097f9.3) 75bdcc72.1-.3 and a473201c.2-.3 were closed as waived under #4966e06d ASKED:2026-11-26T17:03Z (superseded archives, commit 8f1097f9), which is the closure this box names for the L1b sha. The other findings it lists stay to close, and the box stays open for them and for the Accept run.
- [ ] LP-bench [live] A fresh bench receipt after L1 and L2: deploy the branch to bench with deploy_bench, check the two new archives and the MCP tables render, then record and tick through `worklist.py --live-proof`.
  Accept: live-proof bench account-smoke

## Operator-only

1. Materiality of version D (default non-material, effective D). If material: `material: true`, effective at least D+30, all heroes and locale dates follow, and the 30-day notice email goes out from the operator.
2. Amending spec 03 for `config prune` (default: flip to destructive; alternative: withhold `--orphan-repos` from MCP).
3. Raising `COMMAND_SEVERITY` of either command stays the operator's call (unchanged by default).
4. Naming Hostinger in the privacy and telemetry policies (default: name it, as the public DPA does).

## Risks

D is fixed by the L1 commit date; locale writers read D from the registry, not this plan. A second privacy or DPA edit on the same day needs the next day's version. The L2 snapshot update may need the CLI built first.
