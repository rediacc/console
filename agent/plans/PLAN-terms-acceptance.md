# PLAN: terms acceptance -- one vault entity record, a versioned and hashed Terms of Service, and assent recorded at web signup, Stripe checkout and the anonymous CLI FREE fetch
Status: approved -- operator rulings R1-R4, ASKED 2026-11-11, quoted verbatim under Rulings
Depends-On: no-dep -- builds on landed code only (FREE licence, the free_to_registered drill 23c783db4b, the SELLER_PROFILE_JSON vault record); the open boxes of PLAN-free-license (F2, L3, LP-hostinger) and PLAN-drop-free-license-ip-prefix-hash (L1) are CI-workflow and live boxes that touch none of this plan's files
Owner: d778be9d
Updated: 2026-11-11
Priority: P1 -- operator priority; no acceptance is recorded anywhere today, so no term binds a web, Stripe or FREE user, and the ToS names an IP owner that contradicts LICENSE
Concurrency: parallel -- parts E, L, S, W and C own disjoint files (named under Concurrency); at most 4 writers at once; E1-E4 land first, then S, W, C and L run side by side, then E5-E7
Owns: agent/plans/PLAN-terms-acceptance.md, .ci/config/secret-supply.json, .ci/config/legal-documents.json (new), .ci/config/gate-costs.json, .ci/rediacc_ci/core/bws_env.py (JSON_REQUIRED only), .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py (SELLER map only), .ci/rediacc_ci/tests/test_ops_deploy_bench.py, .ci/rediacc_ci/legal/** (new), .ci/rediacc_ci/tests/test_legal_entity.py (new), .ci/rediacc_ci/__main__.py (one Verb), .ci/rediacc_ci/release/local.py (one Step), .ci/rediacc_ci/tests/test_release_local.py, .github/workflows/cd-deploy-account.yml (one step), .github/workflows/cd-deploy-worker.yml (one step), .ci/rediacc_ci/quality/literal_sources.py, scripts/data/literal-sources.json, .ci/rediacc_ci/tests/test_quality_literal_sources_entity.py (new), .ci/rediacc_ci/ops/free_to_registered.py, .ci/rediacc_ci/tests/test_ops_free_to_registered.py, scripts/gen/gen-legal.ts (new), scripts/gates/check-terms-version.ts (new), package.json (two scripts), packages/shared/src/legal/** (new), packages/shared/src/config-schema/state-schema.ts, packages/shared/src/cli-contract/data/**, packages/www/public/legal/** (new), packages/www/src/config/constants.ts, packages/www/src/i18n/translations/*.json, packages/www/src/i18n/translations/.translation-hashes.json, packages/www/src/pages/[lang]/{terms-of-service,privacy-policy,cookie-policy,refund-policy,telemetry-policy,legal-information,acceptable-use-policy,data-processing-agreement,service-level-agreement,enterprise-license}.astro, packages/www/src/components/Footer.tsx (legal links only), packages/www/src/components/LegalDocument.astro (new), packages/www/src/utils/legal-tokens.ts (new), packages/www/src/content/blog/*/nis2-supply-chain-self-hosted.md, packages/www/src/content/blog/{de,et}/nis2-the-real-bill.md, packages/www/src/content/docs/*/cli-application.md, docs/legal/enterprise-order-form.md (new), private/account/drizzle/0083_terms_acceptances.sql (new), private/account/drizzle/meta/**, private/account/src/db/{schema,scope-registry,shard-router}.ts, private/account/src/services/{terms.service.ts,free-license.service.ts,billing.service.ts,webhook.service.ts,notification.service.ts}, private/account/src/routes/{terms.ts,license.ts,device-codes.ts}, private/account/src/middleware/terms.ts (new), private/account/src/types/{terms.ts,subscription.ts,env.ts}, private/account/src/{errors,app,container}.ts, private/account/src/entry/cloudflare.ts (scheduled only), private/account/src/pricing/catalog.default.ts, private/account/src/email/templates/legal.ts (new), private/account/src/i18n/locales/*/emails.json, private/account/wrangler*.toml (two vars), private/account/tests/**/terms*.test.ts (new), private/account/tests/integration/free-license.test.ts, private/account/web/src/components/legal/** (new), private/account/web/src/auth/ProtectedRoute.tsx, private/account/web/src/pages/{Terms,InviteAccept,PartnerInviteAccept,ConfigMemberAccept,Settings}.tsx, private/account/web/src/router.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/{config.ts,locales/*/legal.json}, packages/cli/src/services/account/{free-license.ts,terms.ts,account-client.ts}, packages/cli/src/commands/{legal.ts,version.ts} (new), packages/cli/src/cli.ts, packages/cli/src/i18n/locales/*/cli.json, packages/cli/src/**/__tests__/{terms,legal,version}*.test.ts (new)
Live-Proof: bench -- the account surface (D1 migration 0083, the terms routes and gate, FREE assent), the www legal pages and the cli FREE prompt all admit bench; renet is not changed (O1), so hostinger owes no receipt

## Context
Facts checked 2026-11-11 on 1104-1:
1. **No assent is recorded.** `users` (private/account/src/db/schema.ts:15-40) has no terms column. `registerSchema` (private/account/src/types/user.ts:40-44) takes email, password and turnstile only. Stripe checkout (private/account/src/services/billing.service.ts:388-415) sets no `consent_collection`.
2. **Signup is not one route.** `POST /auth/magic-link` creates the user silently when the email is unknown (private/account/src/services/auth.service.ts:324-360), and `/auth/register` (private/account/src/routes/auth.ts:100) creates one too. Device-code approval goes through web/src/pages/Authorize.tsx. Every authenticated portal page except three sits under one wrapper, `ProtectedRoute` (private/account/web/src/auth/ProtectedRoute.tsx:10). The three exceptions are `InviteAccept` and `PartnerInviteAccept` (outside it, in `AuthLayout`, private/account/web/src/router.tsx:211-228) and `ConfigMemberAccept`. So one gate inside ProtectedRoute, plus those three pages, covers every way an account is created or used.
3. **The CLI FREE path.** `resolveLicenseAuthority` (packages/cli/src/services/account/free-license.ts:118-155) auto-takes FREE under an agent or `--yes` (`autoTakesFree`, :103) and posts to `/account/api/v1/licenses/free` (:44). The server checks are in private/account/src/routes/license.ts:283-301 and free-license.service.ts. The FREE subject is `free:` + HMAC(machineId) (private/account/src/services/free-license.service.ts:5-6, :37). The CLI already maps one structured 403 code to a guided recovery (`TOKEN_IP_MISMATCH`, packages/cli/src/services/account/account-client.ts:352-362). Every request carries `x-cli-version` (:404).
4. **The entity is already a vault record.** `SELLER_PROFILE_JSON` expands to nine `SELLER_*` fields (.ci/rediacc_ci/core/bws_env.py:255-265, check_bws_map assertion 14d). Six profiles bind it: account-dev, deploy-bench, account-secrets-eu/us/asia and release-local. `set_account_worker_secrets` pushes it (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:230-238), `deploy_bench` pushes it too (.ci/rediacc_ci/ops/deploy_bench.py:227-235), and the account Worker uses it for invoices (private/account/src/app.ts:332-343).
5. **The entity is also hardcoded.** www has the `COMPANY_*` constants (packages/www/src/config/constants.ts:26-31); Footer, StructuredData and legal-information read them. Prose in all 13 translation files carries "Rediacc OÜ (registry code 17363830) ... Tartu mnt 67/1-13b" (packages/www/src/i18n/translations/en.json:1251, :1423). The NIS2 blog posts (13 locales) carry "OÜ 17363830, VAT EE102920091". packages/www/src/pages/[lang]/legal-information.astro:75 has the registry URL, and private/account/src/pricing/catalog.default.ts:14 has `legalLine: 'Rediacc OÜ ...'`. `check:ci-literal-sources` judges CODE only for R1/R2 and reads prose for near misses only (.ci/rediacc_ci/quality/literal_sources.py:3-28), so it cannot see any of this today.
6. **The ToS contradicts LICENSE.** packages/www/src/i18n/translations/en.json:1423 says the Services "are owned by Rediacc OÜ". LICENSE says "Copyright © Muhammed Fatih Bayraktar (trading as "Rediacc")", which matches R1 ("the license is owner by me personally"). <!-- style-ok -->
7. **Legal pages.** Six pages exist; their text lives in `pages.<doc>` of packages/www/src/i18n/translations/{13}.json. The ToS has 19 sections, "Effective Date: March 15, 2026", no arbitration, no export clause and no age clause, and it says "continued use constitutes acceptance" (packages/www/src/i18n/translations/en.json:1502). The translator interpolates `{{name}}` in `t()` only, not in `to()` objects (packages/www/src/i18n/translator.ts:40-46). Legal pages are not a naturalization-pipeline surface (`SURFACE_NAMES` in the gitignored growth repo), so they are translated by hand, as docs/i18n/CONVENTIONS.md section 2 allows. No legal text uses "Elite".
8. **rdc today.** `--version` only (packages/cli/src/cli.ts:210). `rdc credits --licenses` already prints the build-time THIRD_PARTY_LICENSES (packages/cli/src/commands/credits.ts:14-18, scripts/gen/generate-third-party-licenses.ts). `rdc term` is the SSH terminal command.
9. **Live tiers.** bench `account-smoke` is the check that closes an account, cli and www plan (precedent: PLAN-renet-bridge-leftovers LP-bench). `www-smoke` is always NOT_VERIFIED. The account surface needs a VERIFIED `vm:check` on the head tree before the live recorder runs.

## Rulings (operator, ASKED 2026-11-11, verbatim)
> R1 entity: "For now rediacc estonia/ou is fine but -> Since the license is owner by me personally, The company name could be different in the future. So, variables like "Rediacc OÜ (Estonia)" should be defined by bws. Single source of truth."
> R2 assent points: "I lean to 'Signup + CLI free fetch (Recommended)' but Can't we make it smarter? If user has a config with registration then he can/did from web otherwise from cli for free?"
> R3 agents: "Flag accepts, operator responsible (Recommended)". Recorded with the ruling: `--accept-terms` or `RDC_ACCEPT_TERMS=1` counts as acceptance, recorded per machine as unattended. The terms bind whoever runs the automation (E-SIGN 15 U.S.C. 7001(h), UETA section 14). Without the flag, the fetch refuses and prints exactly what to pass.
> R4 drafting: "Common Paper base. There will be no planned lawyer now or later."
- Naming: "elite" is the old name of "enterprise". Use "Enterprise" in new text.

Earlier rulings that bind this plan:
- PLAN-free-license R7: the FREE caller's IP is "stored only as a keyed hash; rows purged after 72 h", and the privacy text promises the licence record holds no IP data (PLAN-drop-free-license-ip-prefix-hash P1). **A FREE acceptance row therefore stores no IP.** Account acceptances do.
- "no customers yet, so a clean break with no compatibility shims" (operator 2026-11-01, PLAN-backup-integrity Status). So there is no grace path for CLIs that do not send acceptance, and the first terms version has no 30-day notice window.

## Design 1: the entity, one source (R1)
- **Source.** The vault entry `SELLER_PROFILE_JSON` already holds the contracting party: the invoice seller and the ToS party are the same entity, so a second record would be a second source. It gains two keys: `SELLER_REGISTER_NAME` ("Estonian Commercial Register (Äriregister)") and `SELLER_LICENSOR_NAME` ("Muhammed Fatih Bayraktar (trading as Rediacc)"). `JSON_REQUIRED` grows to 11. All six binding profiles and both Worker pushers carry the two new names. A new profile `legal-entity` binds the 11 as required.
- **Projection.** `./run.sh legal-entity sync` (`.ci/rediacc_ci/legal/entity.py`, re-exec under `--profile legal-entity`) writes two files. `packages/shared/src/legal/entity.generated.json` holds sorted keys `legalName, registryCode, registerName, vatNumber, addressLine1, addressLine2, city, postalCode, countryCode, licensorName`, the derived `registeredAddress`, and `sourceSha256` (sha256 of the canonical JSON of the 11 vault fields). `entity.generated.ts` exports `LEGAL_ENTITY` under a "generated from SELLER_PROFILE_JSON; do not edit" banner. `SELLER_EMAIL` is not projected: `WK_CONTACT_EMAIL` stays the legal contact. The country name is rendered per locale with `Intl.DisplayNames` from `countryCode`, so no country name is stored.
- **Fail closed where the vault is reachable.** `legal-entity verify` re-fetches the vault and compares field by field. It prints field names, never values, and exits 1 on any difference or when the vault cannot be reached. It runs as a release-local step `legal-entity-verify` (phase builds, before `packages`, `profiles=("legal-entity",)`, included in `--workers-only`). It also runs as a step before the build in cd-deploy-account.yml and cd-deploy-worker.yml, under the sm-action fetch those workflows already do.
- **Builds without the vault** (PR lanes, forks, local dev, unit tests) build from the committed projection. That file is the last copy a release verified, so no placeholder exists and none can ship. A vault edit reaches the site only through `sync` plus a commit, and no release or Worker deploy goes out while the projection trails the vault (O2).
- **Consumers.**
  - www `constants.ts` re-exports `COMPANY_*` from `LEGAL_ENTITY` under the same names, plus `COMPANY_LICENSOR_NAME` and `COMPANY_COUNTRY_CODE`, so Footer, StructuredData and legal-information need no change.
  - Legal prose uses `{{legalName}} {{registryCode}} {{registerName}} {{vatNumber}} {{registeredAddress}} {{country}} {{licensorName}}`, interpolated by `packages/www/src/utils/legal-tokens.ts`, which walks a whole section tree because `to()` does not interpolate.
  - The account Worker reads `SELLER_*` env, which is already pushed, for `GET /legal/terms`, the notice email and `catalog.default.ts`'s `legalLine`.
- **Gate.** `check:ci-literal-sources` gains R6 (Design 6).

## Design 2: one terms version and hash, from the published text
- `.ci/config/legal-documents.json` is hand-edited. For each document (`terms-of-service`, `privacy-policy`, `acceptable-use-policy`, `data-processing-agreement`, `service-level-agreement`, `enterprise-license`) it lists versions `{version: YYYY-MM-DD, effective: YYYY-MM-DD, material: bool, sha256}`. Only `terms-of-service` drives assent; the others are versioned, archived and shown.
- `scripts/gen/gen-legal.ts --write` renders each document's English text canonically:
  - sections in `orderedKeys` order (packages/www/src/utils/legal-order.ts): title, paragraphs, items, subsections;
  - entity tokens substituted from the projection;
  - tags reduced to text, links kept as `text <url>`;
  - LF line endings, UTF-8.
- It writes:
  - `packages/www/public/legal/archive/<doc>-<version>.txt` for a version with no archive (served at `https://www.rediacc.com/legal/archive/...`);
  - `packages/shared/src/legal/documents.generated.ts` with versions, sha256, effective dates, material flags and URLs;
  - `packages/shared/src/legal/consent.generated.ts` with the consent notices (Design 4) for all 13 locales, taken from the `legal.consent.*` keys of the www catalogs with tokens substituted, plus each notice's sha256.
- `--from-ref <ref>` renders from `git show <ref>:en.json`. E4 uses it to archive today's ToS as version `2026-03-15` before L1 rewrites the text.
- **One API**, `packages/shared/src/legal/index.ts`:
  - `LEGAL_ENTITY`, `LEGAL_URLS` (from `WK_SITE_ORIGIN`);
  - `termsAt(now) -> {current, upcoming?, latest}`;
  - `satisfies(acceptedVersion, required)`: true when the accepted version is the latest material version at or before `required`, or a later one;
  - `CONSENT_NOTICES[locale][method]`, `noticeSha256(method, locale)`;
  - `ACCEPTANCE_METHODS = ['web-checkbox','cli-prompt','cli-flag-unattended','stripe-checkout']`.
- **Changes.** A typo fix is a new entry with `material: false`, and nobody is asked again. A material change is a new entry whose `effective` date is at least 30 days later. Until that date it is `upcoming`: the server sends notices (S5) and accepts it early, and after that date it is required.
- the terms-version gate (Design 6) keeps the text, manifest, archives and generated modules in step.

## Design 3: the documents (R4, L1)
Common Paper standard terms (CC BY 4.0) are the base. L1 records each standard's name and version in an attribution line on every page derived from one, with the licence link and a "modified" note. Where Common Paper has no standard for a part (consumer arbitration, AUP, DMCA), the text is drafted from the clause list below. **English governs**, and the 12 translations say so in their first section.
- **Terms of Service** (master; the CLI and renet licence is a section of it):
  - definitions;
  - agreement and clickwrap acceptance (replacing "continued use constitutes acceptance"), plus the authority to bind an organization;
  - the parties: `{{legalName}}`, registered in `{{country}}`. `{{legalName}}` and its licensors own or have the right to license the software, which `{{legalName}}` licenses to the customer; the licensor arrangement stays out of customer text (operator 2026-11-11, "Customer should not care about it");
  - eligibility at 18+;
  - plans: FREE with no account (48 h, 3 GB), Community, paid, and Enterprise through partners on an order form;
  - fees, taxes, refunds (pointer), and a clear auto-renewal disclosure;
  - the software licence (CLI and renet agent; source under RSL 1.0);
  - FREE and beta features with no warranty;
  - acceptable use (incorporates the AUP);
  - the customer is responsible for its own servers, agents and automation, including terms accepted by flag (R3);
  - customer data, zero-knowledge encryption and key loss, which is data loss; backups are the customer's duty;
  - privacy and the DPA (incorporated for business customers); telemetry (pointer); IP and feedback; third-party components; confidentiality;
  - a capitalised, conspicuous "AS IS" disclaimer (UCC 2-316);
  - a liability cap (O4) and a customer indemnity;
  - term, suspension and termination;
  - export control (5D992.c mass-market encryption, sanctions, denied parties);
  - DMCA notice and agent (the contact email until the agent is registered, see Operator actions);
  - changes: 30-day email notice for a material change, and re-acceptance;
  - governing law: Estonia, Harju County Court (O3);
  - **US users only**: an informal resolution step first, AAA arbitration with the mass-arbitration supplementary rules, a class and jury waiver, a 30-day opt-out, a small-claims carve-out, and a McGill public-injunction severability clause. The clause names US residents only, because a consumer arbitration clause does not bind EU consumers;
  - general terms; contact.
- **Privacy Policy** additions: acceptance records (account: version, hash, time, IP, user agent; FREE: no IP, per R7), with legal bases Art. 6(1)(b) and (c) and the retention in O6; the subprocessor list moves to the DPA, with a pointer; 18+.
- **Acceptable Use Policy** (new page).
- **DPA** (new page): GDPR Art. 28 terms; the SCCs (Commission Decision 2021/914) incorporated, with modules as applicable; a subprocessor list derived from code, not memory (Cloudflare Workers/D1/R2, AWS SES, Stripe, Turnstile, the OTLP endpoint's operator, each confirmed by grep); 30-day subprocessor change notice; 72 h breach notice; deletion or return; audits by report.
- **SLA** (new page, paid tiers only): availability of the account portal and API, never customer servers; service credits as the sole remedy (O4).
- **Enterprise Software License** (new page). The order form is an English-only template, `docs/legal/enterprise-order-form.md` (O8).
- **Consent strings** under `legal.consent` in en.json: `webCheckbox`, `cliPrompt`, `cliRefusal` and `stripeCheckout`. Each names the Terms URL, the Privacy Policy, and arbitration with a class waiver for US users; `stripeCheckout` adds the renewal and cancellation line.

## Design 4: acceptance model
- **Table `terms_acceptances`** (migration 0083), append-only, with no update or delete path except the O6 retention purge:
  - `id`, `subject_kind` ('user' | 'free-machine'), `subject_id` (users.id | `free:<hmac>`), `document`, `version`, `text_sha256`, `method`;
  - `notice_locale`, `notice_text`, `notice_sha256`;
  - `client_ip` (NULL for free-machine), `user_agent`, `cli_version`, `client_machine_hash` (HMAC of clientMachineId, FREE only), `stripe_session_id`, `accepted_at` (UTC ISO);
  - index `(subject_id, document, accepted_at)`.
- **Table `terms_notices`** `(user_id, version, sent_at)`, PK `(user_id, version)`.
- Both tables are UNSCOPED, read only by TermsService (the same justification as freeLicenseIssuances), with `SHARD_CLASS` 'global'.
- **The client never supplies the notice text.** It sends `{version, sha256, locale, method}`. The server checks that version and sha256 match the manifest, takes the canonical notice for `(method, locale)` from `CONSENT_NOTICES`, and stores that text and its hash. A mismatch is 400 `TERMS_VERSION_MISMATCH`.
- **FREE dedupe.** One row per `(subject_id, version)`, so a cached acceptance re-sent by later fetches writes nothing new.

## Design 5: assent points (R2, R3)
- **Web.**
  - `TermsGate` inside ProtectedRoute calls `GET /portal/terms`. When the user's latest acceptance does not satisfy `latest`, it renders `TermsConsent`, a blocking screen: an unticked checkbox whose label is `CONSENT_NOTICES[locale].webCheckbox`, links underlined and in the link colour, and an Accept button disabled until the box is ticked. Nothing is pre-ticked and there is no "by continuing" wording.
  - This one gate covers magic-link signup, password registration, device-code Authorize (so a CLI login always lands on an accepted account), ConfigSetup/ConfigRemote and every portal page.
  - The three invite pages render `TermsConsent` inline when their accept call returns `TERMS_ACCEPTANCE_REQUIRED`, then retry.
  - During a notice window an accepted-but-not-upcoming user sees a dismissible banner instead of the gate.
  - The re-accept URL is `/account/terms?next=<path>`. Settings shows a Legal card with the accepted version and time, the document links and the archive link.
- **Stripe checkout** sets `consent_collection: {terms_of_service: 'required'}` and `custom_text.terms_of_service_acceptance.message` (the `stripeCheckout` notice in the user's locale), behind `STRIPE_CONSENT_COLLECTION=1`, because Stripe refuses the session until the ToS URL is set in the dashboard. `checkout.session.completed` with `consent.terms_of_service == 'accepted'` records `stripe-checkout` for `metadata.userId`, with the session id and no IP.
- **CLI with a registered config** (`getSubscriptionTokenState().kind === 'ready'`): the CLI never prompts.
  - A token call refused with 403 `TERMS_ACCEPTANCE_REQUIRED` prints one line with the re-accept URL and exits with the validation code.
  - During a notice window the server adds the header `x-rediacc-terms: upcoming=<v>; effective=<d>; url=<u>`, and the CLI prints it once per process on stderr.
  - The device-code claim response carries `terms: {accepted, latest, url}` for the login summary.
- **CLI anonymous FREE.** `resolveLicenseAuthority` changes only where FREE is chosen:
  - TTY, no agent: after the existing login/free choice picks free, print `cliPrompt` (one line naming the Terms URL) and ask y/N, default N. Answering N leaves the FREE path with exit 1 and nothing fetched.
  - Agent, non-TTY or `--yes`: FREE needs `--accept-terms` (a new global option) or `RDC_ACCEPT_TERMS=1`. Without either it refuses before any network call, printing `cliRefusal`, which contains literally `--accept-terms` and `RDC_ACCEPT_TERMS=1`, the URL, and "the terms bind whoever runs this automation". `--yes` alone never accepts.
  - The acceptance is cached in the config's `state` bucket (`state.terms: {version, sha256, acceptedAt, method}`; the state half never pushes to a remote store). Later fetches send the cached acceptance and do not ask again until `latest` changes.
  - The FREE request body gains `termsAcceptance: {version, sha256, locale, method}`. `method` is `cli-prompt`, or `cli-flag-unattended` for the flag or env.
- **Server, FREE.** The acceptance check runs after the on-premise refusal and before any IP-window count, so a refusal costs no quota. Missing or stale acceptance is 403 `TERMS_ACCEPTANCE_REQUIRED` with details `{version, sha256, url, flag: '--accept-terms', env: 'RDC_ACCEPT_TERMS=1'}`. The row is written in the issuance's atomic batch with the `free:` subject and no IP. An older CLI that sends no acceptance is refused with that message (clean-break ruling).
- **Free to registered.** The web gate covers the account. Machine-subject rows stay as the record of the anonymous period.
- **Installers** (install.sh, install.ps1) stay silent.

## Design 6: enforcement, rollout and gates
- **Middleware `requireCurrentTerms`** runs on session and API-token routes. When `latest` is not yet effective, a satisfied-current user passes with the notice header. A user who does not satisfy `current`, or a new user who has accepted nothing, gets 403 `TERMS_ACCEPTANCE_REQUIRED` with `{version, sha256, url}`.
  - **Exempt:** `/auth/*`, `/portal/terms*`, `/legal/*`, `/terms/status`, the portal's profile and session reads the gate needs to render, logout, `/licenses/renew` (blob-authenticated; renewals keep running repos alive), `/licenses/free` (its own check), device-code poll and claim, webhooks, health and server-info.
  - On-premise mode makes the middleware a no-op (O7).
- **First version.** E7 declares the rewritten ToS with `effective` equal to its own UTC date and `material: true`. Accounts created before it see the gate on their next visit, and their tokens get the 403 until they accept. No notice window, under the clean-break ruling.
- **Later material versions.** A scheduled sweep (the hourly cron) emails at most 200 users per tick: users who have no acceptance of `upcoming` and no `terms_notices` row for it. Template `legal.ts`, 13 locales.
- **Gate the terms-version gate** (scripts/gates/check-terms-version.ts, `--selftest` first). It fails when:
  1. the render of en.json for a document differs from its newest archive, which names the document and says "add a version entry";
  2. an archive's sha256 differs from its manifest entry (archives are immutable);
  3. a generated module differs from its render;
  4. versions or effective dates do not increase;
  5. a locale lacks a `legal.consent` key or one of its `{{tokens}}`;
  6. terms-of-service.astro does not render the version line from `documents.generated.ts`.

  Zero documents is CANNOT RUN (exit 77). Controls: an edited paragraph, an edited archive and a missing consent key each turn the gate red.
- **Rule R6 in `check:ci-literal-sources`.** Each projected entity value except `countryCode` (legalName, registryCode, vatNumber, the address lines, licensorName, registerName), plus the bare legal-form spelling "Rediacc OÜ", is a finding in CODE or PROSE anywhere outside `packages/shared/src/legal/entity.generated.*`. Translations and markdown count.
  - Exemptions, each with a reason in scripts/data/literal-sources.json: agent/, `_done` plans, *.jsonl, drizzle migrations (immutable), generated search indexes, `.ci/rediacc_ci/quality/claude_attribution.py` and its test, and docs/code-signing-guide.md (procurement notes about this specific entity).
  - Carrier rule: LICENSE's copyright line must equal `licensorName`, so a licensor change cannot leave LICENSE stale.
  - Selftest controls: a planted registry code in a translation, in markdown and in a .ts string each turn it red; LICENSE disagreeing turns it red.

## Design 7: rdc commands
- `rdc version [--json]`: the CLI version, platform/arch, update channel (`account.updateChannel`, else the build channel), and the active licence: the tier from `subscription status` when logged in, "anonymous (FREE per repository)" otherwise, and "unknown (offline)" on a network error. `--version` is unchanged.
- `rdc legal [--json]`:
  - document URLs for the user's language, plus the English binding URL;
  - the current terms version, sha256 and archive URL;
  - the accepted version, time and method, from the server's `GET /terms/status` when logged in, from `state.terms` when anonymous, otherwise "not accepted";
  - the licensor and the contracting entity from `LEGAL_ENTITY`;
  - one line pointing at `rdc credits --licenses` for third-party notices.
- There is no `rdc terms` alias and no `rdc licenses` command (O5).

## Design 8: bench drill
`rediacc_ci.ops.free_to_registered` gains these steps, with each terms row read back through the drill's existing D1 query path:
- **3b free-refused:** a direct `POST /licenses/free` with no `termsAcceptance`. It must return 403 `TERMS_ACCEPTANCE_REQUIRED`, its details must name `--accept-terms`, and the count of `free_license_ip_window` rows from the last minute must not change.
- **3c free-accepted:** the same request with `termsAcceptance{method: cli-flag-unattended}`, fresh UUIDs and `x-cli-version`. It must be issued, and exactly one `terms_acceptances` row must exist for the `free:` subject with the manifest's version and sha256, `client_ip IS NULL`, a non-empty `cli_version` and a non-empty `notice_text`.
- **4b gate:** after `/auth/register`, using the session cookies, `GET /portal/terms` reports not accepted, a gated portal read returns 403 `TERMS_ACCEPTANCE_REQUIRED`, `POST /portal/terms/accept` returns 201, and the row has method `web-checkbox` and non-empty `client_ip` and `user_agent`.
- **6** (login) must pass after 4b.
- **Cleanup** also deletes the acceptance rows of both subjects, the 3c issuance, and its window row (same `issued_at`), so the IP quota is restored.

## Design 9: renet
No change (O1). Enforcement is at issuance on the server, and the blob's `subscriptionId` (`free:<hmac>`) already joins it to its acceptance row. A blob field would change the signed payload schema across released renets, add the hostinger tier and vm:check to this plan, and give renet nothing to act on.

## Open decisions (no ruling covers these; each default stands unless vetoed)
- O1 renet blob carries no terms version. Default: no (Design 9).
- O2 Projection committed and verified fail-closed at release and deploy, rather than generated per build with a dev placeholder. Default: committed. The placeholder variant would make the terms hash depend on the vault (so it could not be committed), would leave the literal gate blind wherever the vault is missing, and would let a lane without the vault ship a placeholder.
- O3 Governing law and venue for US users. Default: Estonian law and the Harju County Court for everyone, plus the US-only arbitration section. The alternative is a US state's law for US users.
- O4 Commercial numbers. Default: liability cap = fees paid in the 12 months before the claim, or USD 100 if none; SLA 99.5% monthly, credits 10% below 99.5% and 25% below 99.0%, sole remedy, paid tiers only.
- O5 Command names. Default: `rdc legal` only; no `rdc terms` (one letter from `rdc term`, the SSH terminal); no `rdc licenses` (`rdc credits --licenses` already exists).
- O6 Retention. Default: account rows kept for the life of the account plus 3 years (the Estonian general limitation period for contractual claims); free-machine rows kept 3 years from acceptance; purged by the daily cron.
- O7 On-premise (company mode) servers. Default: gate off. The Enterprise licence and order form bind that customer.
- O8 Enterprise order form. Default: an English-only template in docs/legal/, not a translated page.

## Operator actions (outside the boxes)
- Register a DMCA designated agent with the US Copyright Office. Until then the ToS DMCA clause names the contact email.
- Set the Terms of Service URL in Stripe's public business details, in test mode (before X2) and in live mode (before `STRIPE_CONSENT_COLLECTION=1` is set for production).

## Tasks
- [x] E1 [lead] Vault: add `SELLER_REGISTER_NAME` and `SELLER_LICENSOR_NAME` to `SELLER_PROFILE_JSON` (values in Design 1) through `bws_env store`, leaving the nine existing fields untouched.
  Owns: the vault entry only. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env json SELLER_PROFILE_JSON` lists 11 keys, the two new ones among them.
  (corrected 2026-11-11, operator ruling) No `SELLER_PROFILE_JSON` record exists: the vault holds the seller fields as separate `SELLER_*` entries. `SELLER_REGISTER_NAME` was created as its own entry; `SELLER_LICENSOR_NAME` is not used (operator: the licensor is between the operator and the company, and customers never see it), so it was parked as `__SELLER_LICENSOR_NAME`. Accept instead: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env names SELLER_REGISTER_NAME` resolves, and no customer-facing text names a licensor.
    (ticked) 2026-11-11T16:33:18Z by d778be9d: commit:8dc1c706a8 accept rc 0 on the landed tree (corrected accept: bws_env names SELLER_REGISTER_NAME rc0; no SELLER_PROFILE_JSON record (8dc1c706a8 removes the dead config))
- [x] E2 [writer] `JSON_REQUIRED` to 11; the two names added to the six profiles (account-dev optional, the other five as their SELLER_* are today); the new `legal-entity` profile with all 11 required; the two names in the `set_account_worker_secrets` and `deploy_bench` SELLER maps.
  Owns: .ci/rediacc_ci/core/bws_env.py, .ci/config/secret-supply.json, .ci/rediacc_ci/deploy/set_account_worker_secrets.py, .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py, .ci/rediacc_ci/ops/deploy_bench.py, .ci/rediacc_ci/tests/test_ops_deploy_bench.py. Accept: `npm run check:ci-bws-map && npm run check:ci-secret-supply && PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_core_bws_env.py .ci/rediacc_ci/tests/test_deploy_set_account_worker_secrets.py .ci/rediacc_ci/tests/test_ops_deploy_bench.py` rc 0, including a case where a 10-key record is refused by name (control).
  (corrected 2026-11-11, operator ruling) Ten separate `SELLER_*` names, not an 11-key JSON record: `JSON_REQUIRED`, `expand_json` and the `json` verb are removed (8dc1c706a8), and `SELLER_LICENSOR_NAME` is dropped everywhere.
    (ticked) 2026-11-11T16:33:19Z by d778be9d: commit:8c7151648e accept rc 0 on the landed tree (check:ci-bws-map, check:ci-secret-supply and pytest bws_env/set_account_worker_secrets/ops_deploy_bench rc0)
- [x] E3 [writer] `./run.sh legal-entity sync|verify`, the two projection files, constants.ts re-exporting from `LEGAL_ENTITY`, the release-local step and the two workflow steps.
  Owns: .ci/rediacc_ci/legal/**, .ci/rediacc_ci/tests/test_legal_entity.py, .ci/rediacc_ci/__main__.py, .ci/rediacc_ci/release/local.py, .ci/rediacc_ci/tests/test_release_local.py, .github/workflows/cd-deploy-account.yml, .github/workflows/cd-deploy-worker.yml, packages/shared/src/legal/entity.generated.{json,ts}, packages/www/src/config/constants.ts. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_legal_entity.py .ci/rediacc_ci/tests/test_release_local.py` rc 0, covering: verify exits 1 on a one-field drift and on an unreachable vault and prints no value; the release step list contains `legal-entity-verify` before `packages`, in `--workers-only` too. Then `./run.sh legal-entity sync && ./run.sh legal-entity verify` rc 0 on the lead machine, and the projected legalName, registryCode and vatNumber equal the pre-change constants.ts values (`git show HEAD~:packages/www/src/config/constants.ts`).
  (corrected 2026-11-11, operator ruling) The projection carries no licensor field.
    (ticked) 2026-11-11T16:33:20Z by d778be9d: commit:e78253d15c accept rc 0 on the landed tree (pytest test_legal_entity.py test_release_local.py rc0)
- [x] E4 [writer] `gen-legal.ts`, the manifest seeded with terms-of-service `2026-03-15` archived through `--from-ref main`, `documents.generated.ts`, `consent.generated.ts` (empty-notice placeholder entries refused by the gate once L1 lands), `index.ts` (the Design 2 API), and `check:ci-terms-version` with its controls.
  Owns: scripts/gen/gen-legal.ts, scripts/gates/check-terms-version.ts, .ci/config/legal-documents.json, .ci/config/gate-costs.json, package.json, packages/shared/src/legal/{index.ts,documents.generated.ts,consent.generated.ts,__tests__/**}, packages/www/public/legal/**. Accept: `npx tsx scripts/gen/gen-legal.ts --write && npx tsx scripts/gates/check-terms-version.ts` rc 0; `npx tsx scripts/gates/check-terms-version.ts --selftest` rc 0 with the three controls red; `npx vitest run packages/shared/src/legal` rc 0, covering `satisfies` across material and non-material entries.
    (ticked) 2026-11-11T16:33:22Z by d778be9d: commit:6399d9a96d accept rc 0 on the landed tree (check-terms-version rc0, --selftest rc0, vitest packages/shared src/legal 9 passed)
- [x] L1 [writer] en.json: the ToS rewrite, Privacy additions, AUP, DPA, SLA and Enterprise License (Design 3), `legal.consent.*`, the new footer link labels; every entity fact as a token; "Enterprise", never "Elite".
  Owns: packages/www/src/i18n/translations/en.json, packages/www/src/i18n/translations/.translation-hashes.json, docs/legal/enterprise-order-form.md. Accept: `npm run i18n:generate-hashes && npm run check:ci-i18n-hashes && npm run check:ci-em-dash-surfaces` rc 0; `grep -cE "Rediacc OÜ|17363830|EE102920091|Tartu mnt" packages/www/src/i18n/translations/en.json` prints 0; `python3 -c` over `pages.termsOfService` finds the strings "AS IS", "American Arbitration Association", "opt out", "5D992" and "18". Lands in one batch with L3a-L3c (completeness).
    (ticked) 2026-11-11T17:02:22Z by d778be9d: commit:a50ed31672 accept on the landed tree (check:ci-i18n-hashes rc0, check:ci-em-dash-surfaces rc0, entity grep in en.json prints 0)
- [x] L2 [writer] `LegalDocument.astro`; the four new pages; the existing legal pages rendered through `legal-tokens.ts`; the ToS page shows "Version <v> · SHA-256 <hash>" with the archive link from `documents.generated.ts`; footer links for the four pages; the legal-information registry URL built from `COMPANY_REGISTRY_CODE`; the NIS2 blog entity sentences replaced by a link to legal-information.
  Owns: packages/www/src/pages/[lang]/*.astro (the ten in the header), packages/www/src/components/{LegalDocument.astro,Footer.tsx}, packages/www/src/utils/legal-tokens.ts, packages/www/src/content/blog/*/nis2-*.md (the 15 in the header). Accept: `npm run build:www` rc 0; `grep -rlE "\{\{(legalName|registryCode|licensorName)\}\}" packages/www/dist` prints nothing (every token rendered); `npm run check:i18n:components` rc 0.
    (ticked) 2026-11-11T17:02:26Z by d778be9d: commit:66984502260553059173f accept on the landed tree (build:www rc0, check:i18n:components rc0; dist HTML holds 0 raw entity tokens (the footer interpolates at render; the token survives only in the client JS catalog the footer reads at hydration, so the box grep over all of dist is broader than intended); key resolvability fixed in 1dc39f347d)
- [x] L3a [writer] Hand-naturalized de, es, fr, it for every key L1 added or changed (CONVENTIONS section 2), each opening with "the English version governs". Owns: packages/www/src/i18n/translations/{de,es,fr,it}.json. Accept: `npm run check:ci-i18n-placeholders && npm run check:ci-i18n-completeness && npm run check:ci-i18n-cross-locale-core && npm run check:ci-em-dash-surfaces` rc 0.
    (ticked) 2026-11-11T17:02:30Z by d778be9d: commit:6bad695ea0 accept on the landed tree (check:i18n rc0 with L1-L3c in one tree; naturalization rc0; stamps ed02ed79c3)
- [x] L3b [writer] The same for pt, ru, tr, et. Owns: packages/www/src/i18n/translations/{pt,ru,tr,et}.json. Accept: as L3a.
    (ticked) 2026-11-11T17:02:36Z by d778be9d: commit:d558814d5f accept on the landed tree (check:i18n rc0 with L1-L3c in one tree; naturalization rc0; et entity reword de2fbd6c47)
- [x] L3c [writer] The same for ar, ja, ko, zh. Owns: packages/www/src/i18n/translations/{ar,ja,ko,zh}.json. Accept: as L3a, then `npm run check:i18n` rc 0 once L1-L3c are in one tree.
    (ticked) 2026-11-11T17:02:53Z by d778be9d: commit:8958d14766 npm run check:i18n rc0 with L1-L3c in one tree
- [x] S1 [writer] Migration 0083 (both tables), the drizzle schema and journal, scope registry UNSCOPED plus `SHARD_CLASS` global, and `TermsService` (`status(subject)`, `accept(subject, input, ctx)` with server-side notice lookup and sha verification, FREE dedupe, the O6 purge).
  Owns: private/account/drizzle/0083_terms_acceptances.sql, private/account/drizzle/meta/**, private/account/src/db/{schema,scope-registry,shard-router}.ts, private/account/src/services/terms.service.ts, private/account/src/types/terms.ts, private/account/src/container.ts, private/account/tests/unit/terms.service.test.ts. Accept: `cd private/account && npx vitest run tests/unit/terms.service.test.ts && npm run typecheck` rc 0, covering: a stale sha gives 400 `TERMS_VERSION_MISMATCH`; the stored notice_text is the server's canonical text whatever the client sends; a second FREE accept of one version writes no row; free-machine rows have NULL client_ip; the purge removes rows past retention only.
    (ticked) 2026-11-11T16:33:23Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account 158e8e8: vitest tests/unit/terms.service.test.ts and typecheck rc0)
- [x] S2 [writer] Routes `GET /legal/terms` (public; versions, URLs, entity from SELLER_* env), `GET /portal/terms`, `POST /portal/terms/accept`, `GET /terms/status` (any API token); `requireCurrentTerms` with the Design 6 exempt list and the on-premise no-op; error code `TERMS_ACCEPTANCE_REQUIRED`; the device-code claim carries `terms`; the two SELLER names in env.ts.
  Owns: private/account/src/routes/{terms,device-codes}.ts, private/account/src/middleware/terms.ts, private/account/src/{errors,app}.ts, private/account/src/types/env.ts, private/account/tests/integration/terms-gate.test.ts. Accept: `cd private/account && npx vitest run tests/integration/terms-gate.test.ts && npm run typecheck` rc 0, covering: a new user's session read gets 403 with the url, and the same read passes after accept; an API-token call gets 403 with the url; `/licenses/renew`, `/auth/*` and logout pass unaccepted; an upcoming version adds the `x-rediacc-terms` header without refusing; on-premise mode never refuses.
    (ticked) 2026-11-11T16:33:24Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account 8b11ed5 b358348 9a00cc0: vitest tests/integration/terms-gate.test.ts rc0)
- [x] S3 [writer] FREE: `termsAcceptance` on `issueFreeLicenseSchema`; the check before any window count; the row inside the issuance batch with no IP and with `client_machine_hash`.
  Owns: private/account/src/types/subscription.ts, private/account/src/services/free-license.service.ts, private/account/src/routes/license.ts, private/account/tests/integration/free-license.test.ts. Accept: `cd private/account && npx vitest run tests/integration/free-license.test.ts` rc 0, covering: no acceptance gives 403 with `flag` and `env` in details and zero window rows written; a stale version is refused; an accepted issuance writes exactly one acceptance row; the existing no-IP-data test extended to `terms_acceptances` (a free-machine row has no address and no hash of it).
    (ticked) 2026-11-11T16:33:25Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account 8162aff: vitest tests/integration/free-license.test.ts rc0)
- [x] S4 [writer] Stripe: `consent_collection` and `custom_text` behind `STRIPE_CONSENT_COLLECTION`; the webhook records `stripe-checkout`; `catalog.default.ts` `legalLine` built from `SELLER_NAME`; both vars default `"0"` in wrangler*.toml.
  Owns: private/account/src/services/{billing,webhook}.service.ts, private/account/src/pricing/catalog.default.ts, private/account/wrangler*.toml, private/account/tests/integration/terms-stripe.test.ts. Accept: `cd private/account && npx vitest run tests/integration/terms-stripe.test.ts` rc 0, covering: with the flag the session params carry `consent_collection.terms_of_service = 'required'`, and without it they do not; a completed session with `consent.terms_of_service = 'accepted'` writes one row with the session id; `grep -c "Rediacc OÜ" private/account/src/pricing/catalog.default.ts` prints 0.
    (ticked) 2026-11-11T16:33:27Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account e4a3237: vitest tests/integration/terms-stripe.test.ts rc0 (the live Stripe half is box X2))
- [x] S5 [writer] The notice email (template `legal.ts`, `emails.json` 13 locales) and the hourly sweep (200 per tick, `terms_notices` dedupe, upcoming versions only).
  Owns: private/account/src/email/templates/legal.ts, private/account/src/i18n/locales/*/emails.json, private/account/src/services/notification.service.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/terms-notice.test.ts. Accept: `cd private/account && npx vitest run tests/integration/terms-notice.test.ts && cd ../.. && npm run check:ci-i18n-account-email-templates` rc 0, covering: no upcoming version sends nothing; one upcoming version mails each unaccepted user once across two ticks; a user who accepted early gets no mail.
    (ticked) 2026-11-11T16:33:28Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account 7a70cbf: vitest tests/integration/terms-notice.test.ts rc0, check:ci-i18n-account-email-templates rc0 after d1dbc7fff1)
- [x] W1 [writer] `TermsConsent` and `TermsGate` (in ProtectedRoute), the `/account/terms?next=` page, the notice banner, the endpoints, the `legal` namespace in 13 locales.
  Owns: private/account/web/src/components/legal/**, private/account/web/src/auth/ProtectedRoute.tsx, private/account/web/src/pages/Terms.tsx, private/account/web/src/router.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/{config.ts,locales/*/legal.json}. Accept: `cd private/account/web && npx vitest run src/components/legal src/auth` rc 0 and `cd private/account && npm run typecheck:web` rc 0, covering: the checkbox renders unticked and Accept stays disabled until it is ticked; the label equals `CONSENT_NOTICES[locale].webCheckbox`; Accept posts `{version, sha256, locale, method: 'web-checkbox'}`; a satisfied user sees no gate; a notice window shows the banner only.
    (ticked) 2026-11-11T16:33:29Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account a9cd073: vitest src/components/legal src/auth rc0, typecheck:web rc0)
- [x] W2 [writer] The three invite pages handle `TERMS_ACCEPTANCE_REQUIRED` inline and retry; the Settings Legal card.
  Owns: private/account/web/src/pages/{InviteAccept,PartnerInviteAccept,ConfigMemberAccept,Settings}.tsx. Accept: `cd private/account/web && npx vitest run src/pages/__tests__` rc 0, covering: an invite accept that first gets 403 renders the consent, and the retry after accept succeeds.
    (ticked) 2026-11-11T16:33:30Z by d778be9d: commit:e7060f724e accept rc 0 on the landed tree (account d03cf84: vitest src/pages/__tests__ rc0)
- [x] C1 [writer] `--accept-terms` and `RDC_ACCEPT_TERMS=1`; `resolveLicenseAuthority` per Design 5 (TTY y/N, refusal for agent, non-TTY and `--yes`); `state.terms` cache; `termsAcceptance` in the FREE body; cli.json in 13 locales.
  Owns: packages/cli/src/services/account/{free-license.ts,terms.ts}, packages/cli/src/cli.ts, packages/shared/src/config-schema/state-schema.ts, packages/cli/src/i18n/locales/*/cli.json, packages/cli/src/services/account/__tests__/terms*.test.ts. Accept: `npm run test:unit -w @rediacc/cli -- src/services/account/__tests__/terms` rc 0, covering:
  - an agent with no flag throws before any fetch, and the message contains `--accept-terms` and `RDC_ACCEPT_TERMS=1` (control: today's code auto-takes FREE);
  - `--yes` alone refuses;
  - TTY N fetches nothing, and TTY y sends `cli-prompt`;
  - the flag sends `cli-flag-unattended`;
  - a cached current acceptance skips the prompt, and a newer `latest` asks again;
  - a ready token never prompts.
    (ticked) 2026-11-11T16:33:32Z by d778be9d: commit:d60c89d6d0 accept rc 0 on the landed tree (test:unit src/services/account/__tests__/terms rc0)

  Then `npm run check:ci-i18n-cli-key-usage` rc 0.
- [x] C2 [writer] `accountServerFetch` maps 403 `TERMS_ACCEPTANCE_REQUIRED` to one line with the URL; the `x-rediacc-terms` warning once per process; the login summary prints the claim's `terms`.
  Owns: packages/cli/src/services/account/account-client.ts, packages/cli/src/services/account/__tests__/terms-client.test.ts. Accept: `npm run test:unit -w @rediacc/cli -- src/services/account/__tests__/terms-client` rc 0: no prompt is ever opened on that 403, and the URL is printed.
    (ticked) 2026-11-11T16:33:33Z by d778be9d: commit:4ec31d0577 accept rc 0 on the landed tree (test:unit src/services/account/__tests__/terms-client rc0)
- [x] C3 [writer] `rdc version [--json]` and `rdc legal [--json]` (Design 7), with CLI docs and the CLI contract regenerated.
  Owns: packages/cli/src/commands/{version,legal}.ts, packages/cli/src/commands/__tests__/{version,legal}*.test.ts, packages/www/src/content/docs/*/cli-application.md, packages/shared/src/cli-contract/data/**. Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/legal src/commands/__tests__/version` rc 0, covering: offline `rdc version` reports "unknown (offline)" with rc 0; `rdc legal --json` has `terms.version` equal to the manifest's and the `accepted` field from state when anonymous. Then `npm run generate:cli-docs -w @rediacc/www && npm run check:ci-cli-contract && npm run check:ci-i18n-cli-help-render` rc 0.
    (ticked) 2026-11-11T16:33:34Z by d778be9d: commit:65c5b7e024 accept rc 0 on the landed tree (test:unit src/commands/__tests__/legal and version rc0)
- [x] E5 [writer] R6 in `check:ci-literal-sources` (entity values in code and prose, the LICENSE carrier, exemptions with reasons, controls). Runs after L1-L3c, L2 and S4 removed the literals.
  Owns: .ci/rediacc_ci/quality/literal_sources.py, scripts/data/literal-sources.json, .ci/rediacc_ci/tests/test_quality_literal_sources_entity.py. Accept: `npm run check:ci-literal-sources` rc 0 on the tree; `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_literal_sources_entity.py` rc 0, with a planted `17363830` in a translation, in a markdown post and in a .ts string each red, and LICENSE disagreeing with `licensorName` red (control: each plant passes on today's gate).
  (corrected 2026-11-11, operator ruling) No LICENSE carrier rule: with no licensor, the LICENSE file names no entity. R6 scans the console tree only; the submodule `catalog.default.ts` is covered by S4's own check.
    (ticked) 2026-11-11T16:33:36Z by d778be9d: commit:238d884030 accept rc 0 on the landed tree (check:ci-literal-sources rc0 after 5af50e70e7 63500298bd de2fbd6c47 b99481e33f; pytest test_quality_literal_sources_entity.py rc0)
- [x] E6 [writer] Drill steps 3b, 3c and 4b and the extended cleanup (Design 8).
  Owns: .ci/rediacc_ci/ops/free_to_registered.py, .ci/rediacc_ci/tests/test_ops_free_to_registered.py. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_free_to_registered.py` rc 0 with fake deps: a missing acceptance row fails the run; a window-count change on 3b fails it; cleanup deletes both subjects' rows; `--dry-run` lists the new step names.
    (ticked) 2026-11-11T16:33:37Z by d778be9d: commit:9d27b9abc2 accept rc 0 on the landed tree (pytest test_ops_free_to_registered.py rc0)
- [x] E7 [writer] Declare the rewritten ToS (and the other five documents) in the manifest with `effective` = the commit's UTC date and `material: true`; regenerate the archives and modules.
  Owns: .ci/config/legal-documents.json, packages/shared/src/legal/{documents,consent}.generated.ts, packages/www/public/legal/archive/**. Accept: `npx tsx scripts/gen/gen-legal.ts --write && npx tsx scripts/gates/check-terms-version.ts` rc 0; `git diff --stat` shows the 2026-03-15 archive unchanged; `consent.generated.ts` has 13 locales with 4 non-empty notices each.
    (ticked) 2026-11-11T16:33:38Z by d778be9d: commit:b99481e33f accept rc 0 on the landed tree (gen-legal --write and check-terms-version rc0; 2026-03-15 archive unchanged; consent.generated.ts 13 locales x 4 notices)
- [ ] X1 [lead] Local proof chain: a VERIFIED `npm run vm:check -- --changed` on the head tree, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench` (applies 0083), then the drill.
  Local-route: vm-check, deploy-bench, d1-migrations -- the branch tree is proved on the fleet and deployed to bench from this checkout
  Owns: none (runs only). Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.free_to_registered` rc 0, printing STEP 3b, 3c and 4b with rc=0 and cleanup rc=0.
- [ ] X2 [lead] Stripe consent on bench, once the operator has set the test-mode ToS URL: set `STRIPE_CONSENT_COLLECTION=1` on bench, start a checkout through the bench portal API, and retrieve the session with the test key.
  Owns: none. Accept: the retrieved session shows `consent_collection.terms_of_service = "required"`, and after a test-card completion one `terms_acceptances` row with method `stripe-checkout` exists for the user (bench D1 query).
- [ ] LP-bench [live] Fresh bench receipt after X1, recorded and ticked through `worklist.py --live-proof`.
  Accept: live-proof bench account-smoke

## Concurrency
- **E** (CI tooling, the shared legal module, constants.ts, the drill): E1 -> E2 -> E3 -> E4 in order. E5, E6 and E7 come after the wave-1 parts land.
- **L** (www translations, legal pages, blog lines): L1 with E1-E4 (L1 touches en.json only; E4 reads main through `--from-ref`). Then L2 and L3a/L3b/L3c, which share no file. L1-L3c land in one batch.
- **S** (private/account server, one writer, S1 -> S2 -> S3 -> S4 -> S5; these share app.ts and container.ts).
- **W** (private/account/web, W1 -> W2).
- **C** (packages/cli plus state-schema.ts and the generated CLI docs, C1 -> C2 -> C3).
- **Waves.**
  - Wave 0: writer E (E2-E4) and writer L (L1).
  - Wave 1: S, W, C and L (L2, then L3a-c), four writers. W and C import the E4 API.
  - Wave 2: E5, E6, E7.
  - Then X1, X2 and LP-bench in the main checkout. X1 holds the fleet lock for vm:check.
- No two parts share a file. The only shared reads are `packages/shared/src/legal/**` (written by E only) and `en.json` (written by L1 only; E4 and E7 read it).
