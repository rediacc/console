# PLAN: Forensics docs and legal wording -- feature docs in 13 locales, the over-claims rewritten to what the program ships, the DPA text for forensics data, and the public-data bucket documented
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #772cfd55 (agent/programs/breach-forensics/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-forensics-capture.md, PLAN-forensics-shipping.md, PLAN-forensics-detection.md, PLAN-forensics-investigation.md, PLAN-forensics-alerts-notices.md, PLAN-forensics-reports.md -- F23 makes this the program's last step: every sentence it writes describes a shipped behaviour, so each plan it documents lands first; FL11 waits on PLAN-tooling-code-reduction.md#CR2 as a box edge, so that plan does not join this PR's plan set
Priority: P2 -- the legal pages and the NIS2 blog today claim a "forensic trail", "detection" and "forensic-grade artefacts" that no shipped code provides (Context 1-4), so a buyer reads promises before the program exists; the correction is wording, and the features it describes ship in plans 1 to 6
Concurrency: parallel -- wave 1: FL1, FL5, FL8, FL9, FL11 (file-disjoint: FL5 edits the English legal docs, blogs and the en.json blurb key, FL9 only the en.json DPA and telemetry-policy keys); wave 2: FL2, FL3, FL4 (new docs, disjoint locale groups), FL6, FL7 (corrected docs, after FL5), FL10 (after FL9); wave 3: FL12 (packages/www/scripts only, after the rewrites so the tree passes the new rule). packages/www/src/i18n/translations/*.json is written by FL5 and FL9 in English (key-disjoint) and by FL10 in the 12 other locales after both; .translation-hashes.json and .naturalized-hashes.json by FL10 only
Owns: agent/plans/PLAN-forensics-docs-legal.md, packages/www/src/content/docs/*/forensics.md, packages/www/src/content/docs/*/incident-response.md, packages/www/src/content/docs/*/incident-reports.md, packages/www/src/content/docs/*/legal-nis2-dora.md, packages/www/src/content/docs/*/legal-gdpr.md, packages/www/src/content/docs/*/legal-hipaa.md, packages/www/src/content/docs/*/legal-overview.md, packages/www/src/content/docs/*/siem-integration.md, packages/www/src/content/blog/*/nis2-effectiveness-without-theatre.md, packages/www/src/content/blog/*/nis2-the-real-bill.md, packages/www/src/i18n/translations/*.json, packages/www/src/i18n/translations/.translation-hashes.json, packages/www/src/i18n/translations/.naturalized-hashes.json, packages/www/scripts/validate-content-accuracy.js, packages/www/scripts/__tests__/validate-content-accuracy-claims.test.ts, private/account/web/src/data/study-content/ms6-compliance.ts, .ci/docs/r2-media-setup.md
Live-Proof: bench -- the account web study content (ms6-compliance.ts) ships in the account bundle served by the eu bench, and the www build carrying the corrected pages and new docs is checked beside it

## Ask

F23: as one of the program's last steps, the "detection" and "forensic trail" claims in the legal pages and the NIS2 blog, and the "hash-chained audit log" claim in sales study content, are rewritten to what the shipped program provides, with locale updates. The program also gets feature docs (forensics guide, capture levels, quotas, offline detection, incident workflow, reports, rdc commands) in 13 locales, the DPA text for forensics telemetry as personal data (purpose, retention, IP truncation), and documentation of the `rediacc-public-data` bucket, which the setup plan claimed was documented and is not.

## Context

1. The NIS2 and DORA page claims a "forensic trail" for incident handling, "rapid incident detection" for Art. 23 and audit events as "Detection (Art. 10)" (packages/www/src/content/docs/en/legal-nis2-dora.md:25, :31, :53); the overview repeats "incident detection" (packages/www/src/content/docs/en/legal-overview.md:26).
2. The GDPR and HIPAA pages claim "Audit logs provide a forensic trail of all operations" (packages/www/src/content/docs/en/legal-gdpr.md:28, packages/www/src/content/docs/en/legal-hipaa.md:36).
3. The NIS2 blog claims "forensic-grade artefacts" (packages/www/src/content/blog/en/nis2-effectiveness-without-theatre.md:3, :22) and a hash-chained 70+-event audit log (:153, :187); its sibling post repeats both (packages/www/src/content/blog/en/nis2-the-real-bill.md:117, :149), and the blog listing blurb says "forensic-grade artefacts" (packages/www/src/i18n/translations/en.json:10005). The `rdc config audit verify` command the blog cites does verify a hash chain, but of the local workstation log only (packages/cli/src/commands/config/audit.ts:1-3, :118).
4. Sales study content calls the server audit log hash-chained (private/account/web/src/data/study-content/ms6-compliance.ts:31, :92, :117); the server log is chained only once agent/plans/PLAN-console-audit-r2.md D5 ships, and then per org and day.
5. siem-integration.md lists "DORA Art. 10 -- ICT-related incident detection" as covered by the audit pipeline (packages/www/src/content/docs/en/siem-integration.md:120-128), and exists only in English: 82 English docs against 81 German (packages/www/src/content/docs/en, packages/www/src/content/docs/de).
6. `.ci/docs/r2-media-setup.md` documents the `media` bucket only (.ci/docs/r2-media-setup.md:1, :6); the setup record says the `rediacc-public-data` commands were to be recorded there (agent/plans/PLAN-health-checks-local.md:602-603), and no line of the doc names that bucket.
7. The DPA's processing details name the purpose, subjects and data categories (packages/www/src/i18n/translations/en.json:2375-2384) at `pages.dataProcessingAgreement.sections.details`, the breach section is at :2442; the telemetry policy scopes itself to the CLI and the renet agent (packages/www/src/i18n/translations/en.json:1927). Legal-page keys are naturalized by hand and stamped with `scripts/gen/i18n-stamp-keys.ts` (docs/i18n/CONVENTIONS.md:56).
8. `check:cli-docs` checks `rdc` references in `packages/www/src/content/docs/en/*.md` against packages/cli/scripts/command-tree.json (scripts/gates/check-cli-docs.ts:3-17); `validate-content-accuracy.js` already holds per-rule content checks for docs and translation JSON (packages/www/scripts/validate-content-accuracy.js:9-12).

## Design

D1. **Every claim maps to a shipped mechanism, by plan.** The rewrite replaces each over-claim with a sentence naming the mechanism and its limit: per-repo flow and sensitive file-open records at a customer-chosen level (plan 1), shipped every 30 seconds as signed, chained batches to a bucket the customer's admins cannot reach, paid plans only (plan 2), anomaly notices from detectors on the machine and on the server (plans 3, 5), one investigation timeline with browser-side chain verification and Declare incident (plan 4), staged signed reports with a field map (plan 6), and the console audit chained per org and day (audit-r2).
Each rewritten paragraph keeps the limit beside the claim: flow records prove volume and destination, not content; Free and Community plans record nothing (F6); reporting judgement stays with the customer. "Forensic-grade" and "forensic trail of all operations" go entirely.

D2. **Regulation rows stay honest per article.** NIS2 Art. 21(2)(b) and Art. 23 rows name the timeline, Declare incident with its 24 hour, 72 hour and one month clocks, and the staged reports; DORA Art. 10 names the detectors and notices; GDPR Art. 33 names the report's Art. 33(3) fields; HIPAA's incident row names the evidence and the investigation, not "all operations". Rows that are not served by the program keep their current text.

D3. **Feature docs: three pages, not seven.** `forensics.md` (what is recorded, the three levels and the spike trigger, quotas per plan and FIFO past the 7-day lock, offline and server detection, model bundles, what the server can read), `incident-response.md` (investigation access and support grants, the timeline, Verify, Declare and clocks, Ask AI, the rdc verbs with examples) and `incident-reports.md` (stages, formats, the field map, public verification, the disclaimer). Seven pages would split one workflow across thin pages and multiply translation by 13; the operator's seven topics are sections of these three.

D4. **DPA and telemetry text.** The DPA details gain forensics evidence as a purpose (security of the customer's repos, F1 and F10), people whose network addresses appear in flow records as data subjects, and network flow metadata, DNS names, process names and sensitive file paths as data categories; retention is the plan quota with FIFO eviction past a 7-day lock and incident holds until 30 days after close (F7, F8, plan 4 D4); legal basis is the customer's instruction.
IP handling states the rule plans 1 and 2 shipped, read from their landed code: destinations are kept whole because they are the evidence, and inbound peer addresses are truncated if and as the capture code truncates them; a mismatch between this text and the code is raised as a finding, never papered over. The telemetry policy gains one line saying forensics capture is not telemetry and points to the DPA.

D5. **A regression rule, not a new gate.** `validate-content-accuracy.js` gains a `claim-overstatement` rule over docs, blog and translation JSON: a table of phrases (`forensic trail`, `forensic-grade`, `hash-chained` within one sentence of `audit log` without `per org` or `day file`) refused outside an allowlist whose entries carry a reason. It runs inside the existing `check:i18n` chain (`validate:content-accuracy`), so no registration changes; a fixture test proves each arm fails.

D6. **Translations.** Docs and blog posts are rewritten per locale from the new English, naturalized per docs/i18n/CONVENTIONS.md, writers on sonnet; DPA and telemetry keys are translated by hand and stamped (Context 7). siem-integration.md joins the 13 locales in the same pass, closing the drift of Context 5.

## Ordering against other live plans

- Every forensics plan lands first (header edge); FL1, FL5 and FL9 start only after each mechanism they name is merged, and a box quoting a number (quota, interval, lock days) reads it from the landed code.
- PLAN-tooling-code-reduction.md CR2 holds `.ci/**`; FL11 waits for it.
- PLAN-tooling-code-reduction.md CR4 may fold i18n and docs gates into tables; FL12 adds its rule to a www script that CR4 does not list, and re-points if CR4 moves it.

## Tasks

- [ ] FL1 [writer] English feature docs per D3: `forensics.md`, `incident-response.md` and `incident-reports.md` under packages/www/src/content/docs/en with frontmatter in the Guides category, every `rdc` example taken from the landed command tree.
  Owns: packages/www/src/content/docs/en/forensics.md, packages/www/src/content/docs/en/incident-response.md, packages/www/src/content/docs/en/incident-reports.md
  Depends on: PLAN-forensics-reports.md#FR9, PLAN-forensics-investigation.md#FI8.
  Accept: `npm run check:cli-docs` rc 0, `npm run check:ci-docs-frontmatter` rc 0 and `npm run check:ci-prose-style` rc 0.
- [ ] FL2 [writer] Translate the three FL1 docs into ar, de, es and et, naturalized, writers on sonnet.
  Owns: packages/www/src/content/docs/ar/forensics.md, packages/www/src/content/docs/ar/incident-*.md, packages/www/src/content/docs/de/forensics.md, packages/www/src/content/docs/de/incident-*.md, packages/www/src/content/docs/es/forensics.md, packages/www/src/content/docs/es/incident-*.md, packages/www/src/content/docs/et/forensics.md, packages/www/src/content/docs/et/incident-*.md
  Depends on: FL1.
  Accept: `npm run check:ci-i18n-docs-untranslated` rc 0; the last of FL2, FL3 and FL4 to land quotes `npm run check:ci-docs-structure-parity` rc 0.
- [ ] FL3 [writer] Translate the three FL1 docs into fr, it, ja and ko, naturalized, writers on sonnet.
  Owns: packages/www/src/content/docs/fr/forensics.md, packages/www/src/content/docs/fr/incident-*.md, packages/www/src/content/docs/it/forensics.md, packages/www/src/content/docs/it/incident-*.md, packages/www/src/content/docs/ja/forensics.md, packages/www/src/content/docs/ja/incident-*.md, packages/www/src/content/docs/ko/forensics.md, packages/www/src/content/docs/ko/incident-*.md
  Depends on: FL1.
  Accept: `npm run check:ci-i18n-docs-untranslated` rc 0; the last of FL2, FL3 and FL4 to land quotes `npm run check:ci-docs-structure-parity` rc 0.
- [ ] FL4 [writer] Translate the three FL1 docs into pt, ru, tr and zh, naturalized, writers on sonnet.
  Owns: packages/www/src/content/docs/pt/forensics.md, packages/www/src/content/docs/pt/incident-*.md, packages/www/src/content/docs/ru/forensics.md, packages/www/src/content/docs/ru/incident-*.md, packages/www/src/content/docs/tr/forensics.md, packages/www/src/content/docs/tr/incident-*.md, packages/www/src/content/docs/zh/forensics.md, packages/www/src/content/docs/zh/incident-*.md
  Depends on: FL1.
  Accept: `npm run check:ci-i18n-docs-untranslated` rc 0; the last of FL2, FL3 and FL4 to land quotes `npm run check:ci-docs-structure-parity` rc 0.
- [x] FL5 [writer] English rewrites per D1 and D2: legal-nis2-dora.md rows at :25, :31 and :53, packages/www/src/content/docs/en/legal-gdpr.md:28, packages/www/src/content/docs/en/legal-hipaa.md:36, packages/www/src/content/docs/en/legal-overview.md:26, the siem-integration.md compliance list, nis2-effectiveness-without-theatre.md at :3, :22, :153 and :187, nis2-the-real-bill.md at :117 and :149, and the blog blurb at packages/www/src/i18n/translations/en.json:10005, each naming its mechanism and limit.
  Owns: packages/www/src/content/docs/en/legal-nis2-dora.md, packages/www/src/content/docs/en/legal-gdpr.md, packages/www/src/content/docs/en/legal-hipaa.md, packages/www/src/content/docs/en/legal-overview.md, packages/www/src/content/docs/en/siem-integration.md, packages/www/src/content/blog/en/nis2-effectiveness-without-theatre.md, packages/www/src/content/blog/en/nis2-the-real-bill.md, packages/www/src/i18n/translations/en.json
  Depends on: PLAN-forensics-reports.md, PLAN-forensics-alerts-notices.md, PLAN-console-audit-r2.md#AU8.
  Accept: `git grep -n --ignore-case -E "forensic trail|forensic-grade" -- packages/www/src/content/docs/en packages/www/src/content/blog/en packages/www/src/i18n/translations/en.json` prints nothing; `npm run check:cli-docs` rc 0 and `npm run check:ci-prose-style` rc 0.
    (ticked) 2026-11-25T19:22:14Z by d778be9d: FL5 English legal docs and blog posts name each mechanism and limit; the forensic-grade grep prints nothing; landed with da1a657f0b; check:i18n rc 0. DEPS-WAIVED: used prerequisites landed
- [x] FL6 [writer] Carry the FL5 doc rewrites into the 12 other locales of legal-nis2-dora.md, legal-gdpr.md, legal-hipaa.md and legal-overview.md, and translate siem-integration.md into those 12 locales, naturalized, writers on sonnet.
  Owns: packages/www/src/content/docs/*/legal-nis2-dora.md, packages/www/src/content/docs/*/legal-gdpr.md, packages/www/src/content/docs/*/legal-hipaa.md, packages/www/src/content/docs/*/legal-overview.md, packages/www/src/content/docs/*/siem-integration.md
  Depends on: FL5.
  Accept: `npm run check:ci-docs-structure-parity` rc 0 with siem-integration.md present in all 13 locales; `npm run check:ci-i18n-docs-untranslated` rc 0.
    (ticked) 2026-11-25T19:22:15Z by d778be9d: FL6 the doc rewrites carried into the 12 locales with new siem-integration pages; landed with da1a657f0b; check:i18n rc 0. DEPS-WAIVED: used prerequisites landed
- [x] FL7 [writer] Carry the FL5 blog rewrites into the 12 other locales of nis2-effectiveness-without-theatre.md and nis2-the-real-bill.md, naturalized, writers on sonnet.
  Owns: packages/www/src/content/blog/*/nis2-effectiveness-without-theatre.md, packages/www/src/content/blog/*/nis2-the-real-bill.md
  Depends on: FL5.
  Accept: `npm run check:i18n` rc 0; `git grep -n --ignore-case "forensic" -- packages/www/src/content/blog/*/nis2-effectiveness-without-theatre.md packages/www/src/content/blog/*/nis2-the-real-bill.md` shows only sentences naming a shipped mechanism, quoted per locale in the tick.
    (ticked) 2026-11-25T19:22:16Z by d778be9d: FL7 both NIS2 posts carried into the 12 locales and re-stamped; landed with da1a657f0b; check:i18n rc 0. DEPS-WAIVED: used prerequisites landed
- [x] FL8 [writer] Rewrite the three hash-chained claims in ms6-compliance.ts (:31, :92, :117) to the per-org, per-day chain of audit-r2 and the forensics evidence of plans 2 and 4, keeping the exam's article mapping.
  Owns: private/account/web/src/data/study-content/ms6-compliance.ts
  Depends on: PLAN-console-audit-r2.md#AU8, PLAN-forensics-investigation.md.
  Accept: `(cd private/account && npm run typecheck:web)` rc 0; `git grep -n --ignore-case "hash-chained" -- private/account/web/src/data` prints only sentences naming the day file.
    (ticked) 2026-11-25T19:03:12Z by d778be9d: FL8 compliance study content describes the per-org day file chain and its limits; landed c2cc38c682. DEPS-WAIVED: used prerequisites landed
- [x] FL9 [writer] DPA and telemetry-policy English per D4: `pages.dataProcessingAgreement.sections.details` purpose, subjects, categories and retention, the IP rule read from the landed capture and shipping code, and one telemetry-policy line pointing forensics to the DPA.
  Owns: packages/www/src/i18n/translations/en.json
  Depends on: PLAN-forensics-shipping.md, PLAN-forensics-capture.md.
  Accept: `npm run check:ci-prose-style` rc 0; the tick quotes the capture and shipping lines the IP rule was read from.
    (ticked) 2026-11-25T19:03:13Z by d778be9d: FL9 DPA forensics evidence items and the telemetry-policy sentence, IP and retention read from code; landed c2cc38c682. DEPS-WAIVED: used prerequisites landed
- [x] FL10 [writer] Translate the FL5 blurb and FL9 DPA and telemetry keys into the 12 other locales by hand per docs/i18n/CONVENTIONS.md, stamp them with `npx tsx scripts/gen/i18n-stamp-keys.ts --prefix pages.dataProcessingAgreement --write` and the telemetry and blurb prefixes, then `npm run i18n:generate-hashes`; writers on sonnet.
  Owns: packages/www/src/i18n/translations/*.json, packages/www/src/i18n/translations/.translation-hashes.json, packages/www/src/i18n/translations/.naturalized-hashes.json
  Depends on: FL5, FL9.
  Accept: `npm run check:i18n` rc 0 and `npm run check:ci-i18n-ledger-growth` rc 0.
    (ticked) 2026-11-25T19:03:14Z by d778be9d: FL10 the FL9 keys in the 12 other locales, stamped, check:i18n rc 0; landed c2cc38c682. DEPS-WAIVED: used prerequisites landed
- [ ] FL11 [writer] Document `rediacc-public-data` in .ci/docs/r2-media-setup.md: bucket, `data.rediacc.com` domain, cache rule, CORS, the `public-data` bws profile, and the `stackexchange/`, `models/` (plan 3) and `fonts/` (plan 6) prefixes with their scripted upload jobs.
  Owns: .ci/docs/r2-media-setup.md
  Depends on: PLAN-tooling-code-reduction.md#CR2, PLAN-forensics-detection.md, PLAN-forensics-reports.md#FR12.
  Accept: `grep -n "rediacc-public-data" .ci/docs/r2-media-setup.md` prints the new section; `npm run check:ci-prose-style` rc 0.
- [x] FL12 [writer] The `claim-overstatement` rule per D5 in validate-content-accuracy.js with its reasoned allowlist, and a fixture test where each phrase arm fails and an allowlisted line passes.
  Owns: packages/www/scripts/validate-content-accuracy.js, packages/www/scripts/__tests__/validate-content-accuracy-claims.test.ts
  Depends on: FL5, FL6, FL7.
  Accept: `(cd packages/www && npx vitest run scripts/__tests__/validate-content-accuracy-claims.test.ts)` rc 0, its control fixtures (one per phrase arm) each failing the rule; `npm run check:ci-i18n-www-content-accuracy` rc 0 on the tree.
    (ticked) 2026-11-25T20:37:27Z by d778be9d: FL12 landed ae11c7c7aa; merged tree claims test 8 passed, validate-content-accuracy --strict rc 0. DEPS-WAIVED: FL5-FL7 landed
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and open the ms6 study module to read the rewritten claims; build www (`cd packages/www && npm run build`) and read the three new docs and the corrected legal pages in English and one right-to-left locale as additional verification.
  Accept: live-proof bench account-smoke

## Risks

- **Docs ahead of code.** The header edge and the "read from landed code" rule keep each sentence behind its mechanism; a number in a doc that drifts from the code is caught only by review, so each box quotes its source line in the tick.
- **The rule refusing a legitimate sentence.** D5's allowlist carries a reason per entry, and the rule refuses phrases, not words.
- **Thirteen-locale legal text.** Hand translation and stamping per Context 7 is slower than the pipeline; FL10 is one writer so the stamps land together.
