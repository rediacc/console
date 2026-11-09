# PLAN-website-routing-and-mail: www.rediacc.com routes people to the right product host, and product mail sends from notify.rediacc.cloud

Status: executing -- promoted by operator 2026-11-08; design settled in the operator talk of 2026-11-05 (region popup with a 5-second login forward, company lookup by email domain, apex 301, Public Suffix List, product mail on .cloud)
Depends-On: PLAN-product-domain-rename.md#W3, PLAN-product-domain-rename.md#W4, PLAN-product-domain-rename.md#L5, PLAN-product-domain-rename.md#L6, PLAN-product-domain-rename.md#L8 -- W3 and W4 own the hosts in regions.json, well-known.env and every Wrangler config; L5, L6 and L8 put those hosts on Cloudflare
Owner: d778be9d
Priority: P1 -- every login reaches the product through this routing, and the mail sender moves off rediacc.com
Concurrency: parallel -- its code is packages/www, the www Worker source and the mail config; the one overlap with PLAN-enterprise-isolation.md, private/account/src/routes/auth.ts, is ordered by that plan's edge on W8
Owns: agent/plans/PLAN-website-routing-and-mail.md, packages/www/src/**, packages/www/public/**, packages/www/scripts/probe-region-picker.ts, workers/www/src/**, workers/proxy/src/index.ts (host literal only), .ci/rediacc_ci/ops/apply_cf_redirect_rules.py, .ci/rediacc_ci/ops/enterprise_lookup.py, .ci/config/free-mail-domains.json, .ci/rediacc_ci/tests/test_ops_apply_cf_redirect_rules.py, .ci/rediacc_ci/tests/test_ops_enterprise_lookup.py, .ci/rediacc_ci/deploy/deploy_www.py, .ci/rediacc_ci/ops/deploy_bench.py, scripts/gates/check-dkim-notify.ts, packages/cli/src/services/serve/auth.ts, packages/cli/src/services/serve/container-config.ts, packages/shared/src/cli-contract/data/** (regenerated only), private/account/scripts/rotation/lib/config.ts, private/account/src/email/templates/shared.ts, private/account/src/services/pdf/certificate-pdf.ts, private/account/src/types/env.ts, private/account/src/types/rotation-manifest.ts, private/account/rotation-manifest.json, private/account/src/routes/auth.ts, private/account/src/types/user.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/auth/AuthContext.tsx, private/account/docs/**, private/account/tests/integration/**, private/account (gitlink bump only)
Live-Proof: bench -- the www Worker, the account mail config, the magic-link change and the host literals are the www, account and proxy surfaces, whose live target is bench; the CLI edit is two host literals under services/serve, which bench admits
First-Seen: 2026-11-05

## Rulings (source: operator talk 2026-11-05)

- Ruling 1. "Failures are acceptable and fixed forward. There are no real customers. No downtime avoidance, no compatibility windows, no dual names, no migration phases."
- Ruling 3. The zone `rediacc.cloud` is done; "the apex 301 and the AI bot setting" remain, and the AI bot setting "is left at default-allow until the product goes live, then blocked".
- Ruling 4. "Bench first always."
- Ruling 12. "Public Suffix List: submit now. Lookup: on by default, a contract can mark a company unlisted, free-mail domains refused. Apex 301 to www. Login auto-forward 5 seconds, none at signup. All docs on www. Product mail from notify.rediacc.cloud in the same AWS account."

## Already done

The zone is on Cloudflare with null MX, `v=spf1 -all` and `_dmarc` reject with strict alignment, per agent/plans/PLAN-product-domain-rename.md. That plan also owns `regions.json`, `well-known.env`, every Wrangler config including the KV binding `ENTERPRISE_LOOKUP` on the `www` Worker, the Turnstile widget domains, and the generated CLI default origin.

## Design

**Popup.** `packages/www/src/components/RegionPickerModal.tsx` forwards at once from a stored region (packages/www/src/components/RegionPickerModal.tsx:123) and guesses from the time zone (packages/www/src/components/RegionPickerModal.tsx:11). Mode comes from the target path, since the callers pass nothing else. At login: a visible 5-second countdown with Cancel and Change, announced to screen readers, forward by the country from `/api/geo`, with the time-zone guess on failure. At signup: region preselected only, because region decides where data lives. A stored `rediacc_region` preselects and never forwards silently. `/api/geo` reads `request.cf.country`, answers `no-store` and calls no third party.

**Lookup.** "Enterprise customer?" on the popup opens a company-domain form. The client sends only the domain part, never an address, to `POST /api/enterprise-lookup` on `www`; the answer is `{host}` or a neutral miss of the same shape. Every address at a domain behaves the same, so no user's existence is exposed. Entries are an HMAC of the domain under a server-side pepper, in KV. Turnstile and a rate limit guard the route. `ops/enterprise_lookup.py` is the one writer: it refuses a free-mail domain against `.ci/config/free-mail-domains.json`, and PLAN-enterprise-isolation.md's `enterprise add` calls it unless the contract marks the company unlisted. Company names stay out of tracked files.

**Zone rules.** One extension of `apply_cf_redirect_rules`, whose zone id is fixed today (.ci/rediacc_ci/ops/apply_cf_redirect_rules.py:31): the `rediacc.cloud` apex and `www.rediacc.cloud` 301 to `https://www.rediacc.com/`, and `edge.rediacc.com` 301 to `www`, then goes. A redirect rule needs a proxied record, so the apex gains a placeholder. PLAN-enterprise-isolation.md puts a proxied `*.rediacc.cloud` record and Worker routes beside it, replacing the earlier suggestion of no wildcard; specific records win over a wildcard, which its V4 proves.

**Public Suffix List.** The entry goes in the PRIVATE section with a `_psl` TXT record. Until browsers carry it, sibling hosts count as one site, and the defences are host-only cookies with no `Domain` attribute and SameSite Strict (private/account/src/services/session.service.ts:211), per-host RP IDs, and reserved labels. W8 pins the cookie with a test. The list's rules, including the registration term it asks for, come from general knowledge and are unverified until Z2 reads them.

**Magic link.** `/magic-link` reveals a password's existence with `hasPassword: true` (private/account/src/routes/auth.ts:334), which is the leak this design avoids, so W8 closes it. The `/login` 423 path appears uniform for unknown addresses, and a test proves or refutes it. The in-memory rate limit stays out of scope, because it does not touch routing.

**Mail.** One domain is hard-coded in `private/account/scripts/rotation/lib/config.ts`, `rotation-manifest.json`, the bench default in `deploy_bench.py` and the region labels (private/account/src/email/templates/shared.ts:7). `check:ci-dkim-notify` reads the domain from the manifest, so it follows. Pattern: BYODKIM, MAIL FROM `bounce-<r>.notify.rediacc.cloud`, SPF `include:amazonses.com -all` on those hosts, DMARC reject with strict DKIM, config set `notify-default`. Asia sends through eu-central-1, because ap-northeast-1 is a sandbox. Same AWS account, so reputation and quota stay shared. Volume is about 10 mails a day, so no warm-up. Enterprise uses the shared sender, with its own identity by contract. `rediacc.com` keeps human mail and `support@rediacc.com`; `rediacc.io` stays for infrastructure.

**Translation delta.** About 11 keys and 2 doc pages, in 12 locales, delta only, on sonnet, following docs/i18n/CONVENTIONS.md.

## Tasks

### Zone

- [x] W0 [writer] `apply_cf_redirect_rules` takes a zone and a rule list, with the rediacc.com apex rule unchanged and the two new rules added.
  Owns: .ci/rediacc_ci/ops/apply_cf_redirect_rules.py, .ci/rediacc_ci/tests/test_ops_apply_cf_redirect_rules.py.
  Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_apply_cf_redirect_rules.py` rc 0.
    (ticked) 2026-11-08T16:04:40Z by d778be9d: commit:0b7598ae43 apply_cf_redirect_rules takes --zone rediacc.com or rediacc.cloud; rediacc.com keeps its apex rule and gains edge.rediacc.com to www; rediacc.cloud apex and www 301 to www.rediacc.com; a zone with no redirect ruleset gets one; pytest 21 passed rc 0
- [x] Z1 [live] Apply the three rules with the placeholder records. PLAN-product-domain-rename.md L11 waits on the `edge.rediacc.com` one.
  Accept: `curl -sI https://rediacc.cloud | grep -qi 'location: https://www.rediacc.com'` rc 0, the same for `https://www.rediacc.cloud` and `https://edge.rediacc.com`.
    (note 2026-11-09T08:07Z, d778be9d) Rollback handles, read before the change: the rediacc.com redirect ruleset held only the apex rule; rediacc.cloud had no `http_request_dynamic_redirect` ruleset and no apex or www address record; `edge.rediacc.com` is AAAA 100:: proxied and stays. Every object the change created is new, so the rollback is a delete of each by the Cloudflare id below (ids sit in a fence because they are Cloudflare ids, not git objects).
    (result 2026-11-09T08:49Z, d778be9d) Applied through bws profile `bench-access`. Two placeholder records through the Cloudflare DNS API (no repo verb creates them); `apply_cf_redirect_rules --zone rediacc.com` rc 0; `--zone rediacc.cloud` rc 1 on the first run, Cloudflare refusing the fixed target `"https://www.rediacc.com/"` as a `target_url.expression` ("Filter parsing error (1:1) ... expected identifier character"), then rc 0 after the module sends a fixed target as `target_url.value` (uncommitted fix with its test). Accept: the three curls rc 0 at 08:49Z; the two `.cloud` ones failed earlier only because the local resolver held a negative answer cached before the records existed, while `curl --doh-url https://cloudflare-dns.com/dns-query` returned rc 0 at 08:37Z.
    ```
    before  rediacc.com ruleset         689dec7a76b14defa69241fd3e71a605
    before  rediacc.com apex rule       55a9afab86bf4f68a68ea7f0be560b24
    before  edge.rediacc.com AAAA       af0fff56bc8b60c9f7257fb9120fdfba
    created rediacc.com edge rule       e8be57e032aa4577ba135bb15628afe3
    created rediacc.cloud ruleset       05d6b6884946495cb7c162fa5a0378df  (cloud-apex and cloud-www rules)
    created rediacc.cloud AAAA 100::    eacc2d6d695d49adc4ac2038f831f35f
    created www.rediacc.cloud AAAA 100:: fad2e913e4792aebda1968b5f4f1373a
    ```
    (ticked) 2026-11-09T09:02:15Z by d778be9d: accept read 2026-11-09T08:49Z: curl -sI https://rediacc.cloud, https://www.rediacc.cloud and https://edge.rediacc.com each grep location https://www.rediacc.com rc 0; apply_cf_redirect_rules --zone rediacc.com rc 0 and --zone rediacc.cloud rc 0 (after the target_url.value fix at .ci/rediacc_ci/ops/apply_cf_redirect_rules.py:66, uncommitted). DEPS-WAIVED: zone rules for the marketing and product apex do not depend on the L6/L8 regional deploys
- [ ] Z2 [live] Read the list's current guidelines and the registration term, open the `publicsuffix/list` PR for `rediacc.cloud`, publish `_psl.rediacc.cloud` with the PR URL, and record the URL here. The box closes on submission; browser adoption takes months.
  Accept: `curl -fsS -H 'accept: application/dns-json' 'https://cloudflare-dns.com/dns-query?name=_psl.rediacc.cloud&type=TXT' | jq -e '.Answer[].data|test("publicsuffix/list/pull")'` rc 0.
    (result 2026-11-09T08:55Z, d778be9d) Blocked on the operator. The guidelines (github.com/publicsuffix/list/wiki/Guidelines) require a PRIVATE entry's expiry to be more than 2 years after the PR date, and the submitter to be an authorized representative using the domain owner's email. RDAP (`curl -fsSL https://rdap.org/domain/rediacc.cloud`) reads registration 2026-10-22, expiry 2027-10-22, so a PR today is refused. Owed: a renewal past 2028-11-09 (a purchase), then the PR from the owner's account, then `_psl.rediacc.cloud` with its URL. They also say small projects are likely declined.
- [ ] Z3 [live] When the operator says the product is live, block AI bots on `rediacc.cloud`. Until then the default-allow stands, and this box stays open under an `Operational-Reason:` line on the PR. The API field name is unverified.
  Accept: `curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "https://api.cloudflare.com/client/v4/zones/$ZONE/bot_management" | jq -e '.result.ai_bots_protection=="block"'` rc 0, under the deploy profile.

### Website

- [x] W1 [writer] The www Worker gains `GET /api/geo` and `POST /api/enterprise-lookup`. `ops/enterprise_lookup.py` gains put, delete and the free-mail refusal, and `deploy_www` pushes the pepper.
  Owns: workers/www/src/index.ts, workers/www/src/geo.ts (new), workers/www/src/enterprise-lookup.ts (new), workers/www/src/__tests__/**, .ci/rediacc_ci/ops/enterprise_lookup.py (new), .ci/config/free-mail-domains.json (new), .ci/rediacc_ci/tests/test_ops_enterprise_lookup.py (new), .ci/rediacc_ci/deploy/deploy_www.py.
  Accept: `(cd workers/www && npm run test:unit)` rc 0 and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_enterprise_lookup.py` rc 0.
    (corrected 2026-11-09, d778be9d) 703fde3a.1: the 703fde3a message and trailer claimed W1 ticked, but no tick was recorded and the box stays open. The code landed in 11ccb9e8b2 (workers/www/src/geo.ts, workers/www/src/enterprise-lookup.ts, .ci/rediacc_ci/ops/enterprise_lookup.py). Owed: the accept `(cd workers/www && npm run test:unit)` rc 0 and `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_ops_enterprise_lookup.py` rc 0, read before `--plan-tick` records it.
    (ticked) 2026-11-09T08:07:06Z by d778be9d: commit:11ccb9e8b2 W1 code landed in 11ccb9e8b2; accept re-read 2026-11-09: (cd workers/www && npm run test:unit) rc 0, 92 tests; pytest test_ops_enterprise_lookup.py rc 0, 9 passed. DEPS-WAIVED: W1 is code against the W4 KV binding (ticked); L6/L8 regional deploys do not bear on it
- [x] W2 [writer] The popup per the Design. `marketing-host.ts` collapses the stable and edge split to one mapping, and the inline copy in `BaseLayout.astro` follows. An English privacy row names `rediacc_region` and the new English keys land, then the hashes are regenerated. `packages/www/scripts/probe-region-picker.ts` drives the popup in a real browser and exits non-zero on a failed step.
  Owns: packages/www/src/components/RegionPickerModal.tsx, packages/www/src/components/__tests__/RegionPickerModal.test.tsx (new), packages/www/src/utils/marketing-host.ts, packages/www/src/utils/__tests__/marketing-host.test.ts, packages/www/src/layouts/BaseLayout.astro, packages/www/src/types/globals.d.ts, packages/www/src/config/regions.ts, packages/www/src/i18n/translations/en.json, packages/www/src/i18n/translations/.translation-hashes.json, packages/www/scripts/probe-region-picker.ts (new).
  Accept: `(cd packages/www && npx vitest run src/components/__tests__/RegionPickerModal.test.tsx src/utils/__tests__/marketing-host.test.ts)` rc 0 and `npm run check:i18n` rc 0.
    (ticked) 2026-11-08T18:46:39Z by d778be9d: commit:f9d8fabab4 W2 landed f9d8fabab4; accept vitest RegionPickerModal and marketing-host rc 0 and check:i18n rc 0 on the batch tip
- [x] W3 [writer] Translations of W2's keys in 12 locales, delta only, on sonnet.
  Owns: packages/www/src/i18n/translations/{ar,de,es,et,fr,it,ja,ko,pt,ru,tr,zh}.json, packages/www/src/i18n/translations/.naturalized-hashes.json.
  Accept: `npm run check:i18n` rc 0.
    (ticked) 2026-11-08T18:46:40Z by d778be9d: commit:f0576ec7a4 W3 landed f0576ec7a4; accept check:i18n rc 0 on the batch tip
- [x] W4 [writer] Rewrite `data-regions.md` and `release-channels.md` for the new hosts and the one-site model in English, then the 12 locales.
  Owns: packages/www/src/content/docs/*/data-regions.md, packages/www/src/content/docs/*/release-channels.md.
  Accept: `npm run check:i18n` rc 0 and `! grep -rl 'edge-eu\.rediacc\.com' packages/www/src/content/docs/*/data-regions.md` rc 0.
    (ticked) 2026-11-08T18:46:41Z by d778be9d: commit:abc292b1b7 W4 landed abc292b1b7; accept check:i18n rc 0 and no edge-eu.rediacc.com in data-regions pages on the batch tip
- [x] W5 [writer] The rest of the `packages/www` host sweep: 84 lines in 43 source files and 77 under `public`, counted by the rename survey, with `edge.rediacc.com` and every `edge-<r>` and bare `<r>.rediacc.com` account host moved to `.cloud`.
  Owns: packages/www/src/** except W2's and W4's files, packages/www/public/**.
  Accept: `! git grep -nE '(edge-)?(eu|us|asia)\.rediacc\.com|edge\.rediacc\.com' -- packages/www/src packages/www/public` rc 0 and `(cd packages/www && npm run build)` rc 0.
    (ticked) 2026-11-09T08:19:24Z by d778be9d: commit:fde9b014d8; accept re-read 2026-11-09: ! git grep old product hosts -- packages/www/src packages/www/public rc 0 (0 hits); (cd packages/www && npm run build) rc 0, 1853 pages built. DEPS-WAIVED: the www sweep reads only the W3 host source, ticked
- [x] W6 [writer] Mail code and config: `notify.rediacc.cloud` and `bounce-<r>.notify.rediacc.cloud` in `dkimNotify` and the SES senders, zone `rediacc.cloud`, `REGION_LABELS`, the bench `AWS_SES_FROM` default, the gate's comments. `rotation-manifest.json` is M2's, since the tool rewrites it.
  Owns: private/account/scripts/rotation/lib/config.ts, private/account/src/email/templates/shared.ts, private/account/src/types/rotation-manifest.ts, .ci/rediacc_ci/ops/deploy_bench.py, scripts/gates/check-dkim-notify.ts, private/account/tests/integration/rotation-*.test.ts.
  Accept: `(cd private/account && npx vitest run tests/integration/rotation-dkim-state.test.ts tests/integration/rotation-bitwarden-names.test.ts)` rc 0.
    (ticked) 2026-11-09T08:13:19Z by d778be9d: commit:71f25f3e8f with account 4a68078 in gitlink 612778aa; accept re-read 2026-11-09: (cd private/account && npx vitest run tests/integration/rotation-dkim-state.test.ts tests/integration/rotation-bitwarden-names.test.ts) rc 0, 36 passed. DEPS-WAIVED: mail config code does not depend on the L6/L8 regional deploys
- [x] W7 [writer] Mail docs for `.cloud` under `private/account/docs`, leaving `incidents/` as history. They state that the `rediacc.cloud` apex sends nothing and human mail stays on `rediacc.com`.
  Owns: private/account/docs/** except incidents.
  Accept: `! grep -rn 'notify\.rediacc\.\(com\|io\)\|ses\.rediacc\.io' private/account/docs --include=*.md --exclude-dir=incidents` rc 0.
    (ticked) 2026-11-09T08:17:08Z by d778be9d: commit:1fe5bac440 carries the account docs change; accept re-read 2026-11-09: the W7 grep over private/account/docs excluding incidents rc 0 (0 hits); apex-sends-nothing at private/account/docs/email/architecture.md:50. DEPS-WAIVED: docs do not depend on the L6/L8 regional deploys
- [x] W8 [writer] Close the magic-link leak: always the generic body, `hasPassword` gone from the response, the portal client offering both options. Tests: the 423 path for an unknown address, and the session cookie carrying no `Domain` attribute.
  Owns: private/account/src/routes/auth.ts, private/account/src/types/user.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/auth/AuthContext.tsx, private/account/tests/integration/auth-no-existence-leak.test.ts (new).
  Accept: `(cd private/account && npx vitest run tests/integration/auth-no-existence-leak.test.ts)` rc 0.
    (ticked) 2026-11-08T16:04:41Z by d778be9d: commit:6387aa3efc account 9fd7659 and acb392e (gitlink 6387aa3efc): the magic-link route always sends the link and returns one body, hasPassword and skipIfHasPassword removed, Login follows; auth-no-existence-leak.test.ts (generic body, 423 for an unknown address, no Domain on session cookies) failed before and passes; auth vitest rc 0, account and web tsc rc 0
- [x] W9 [writer] Host literals left outside `packages/www`: two under the CLI's `services/serve`, `workers/proxy/src/index.ts`, the account's certificate PDF and `types/env.ts`, and the CLI contract regenerated from them.
  Owns: packages/cli/src/services/serve/auth.ts, packages/cli/src/services/serve/container-config.ts, workers/proxy/src/index.ts, private/account/src/services/pdf/certificate-pdf.ts, private/account/src/types/env.ts, packages/shared/src/cli-contract/data/**.
  Accept: `! git grep -nE '(edge-)?(eu|us|asia)\.rediacc\.com' -- packages/cli/src packages/shared/src workers/proxy/src workers/www/src` rc 0, the same grep under `private/account/src`, and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.
    (ticked) 2026-11-08T18:51:13Z by d778be9d: commit:1fe5bac440 W9: no <region>.rediacc.com product host left in the CLI, shared, proxy, www worker or account sources (both accept greps 0 hits); npx tsc --noEmit -p packages/cli/tsconfig.json rc 0

### Mail, live

- [x] M1 [live] Through the bws `rotation` profile, create the identity `notify.rediacc.cloud` in eu-central-1, us-east-1 and ap-northeast-1 with BYODKIM, MAIL FROM, config set and SNS. Publish SPF, DMARC and bounce records.
  Accept: `aws --region eu-central-1 sesv2 get-email-identity --email-identity notify.rediacc.cloud --query DkimAttributes.Status --output text | grep -qx SUCCESS` rc 0 under that profile, repeated per region.
    (ticked) 2026-11-09T08:37:41Z by d778be9d: commit:c651371218; accept read 2026-11-09 under the rotation profile: GET /v2/email/identities/notify.rediacc.cloud (the sesv2 get-email-identity call; the aws CLI is not installed here, so it was signed with private/account/scripts/rotation/lib/aws-sigv4.ts) returned DkimAttributes.Status SUCCESS in eu-central-1, us-east-1 and ap-northeast-1, script rc 0; BYODKIM, MAIL FROM, notify-default and its SNS destination read back. DEPS-WAIVED: SES identities do not depend on the L6/L8 regional deploys
- [ ] M2 [live] `./run.sh rotation rotate dkim-notify` rewrites `rotation-manifest.json`. New IAM policies limited to `*@notify.rediacc.cloud` replace the wider `*@notify.rediacc.*` the docs describe, whose live text is unread. Mint keys through `./run.sh rotation rotate ses-<r>`, bench on its own user.
  Accept: `npm run check:ci-dkim-notify` rc 0.
    (result 2026-11-09T08:55Z, d778be9d) Partial. Done: the dkim-notify rotation (manifest on notify.rediacc.cloud, landed via c651371218), and `npm run check:ci-dkim-notify` rc 0. Live IAM read through the rotation profile: the inline policies of `rediacc-ses-eu`, `-us`, `-asia` and `-bench` all still allow `ses:FromAddress` `*@notify.rediacc.*`. bws `AWS_SES_FROM` (one entry, bound by `account-secrets-<r>` and `deploy-bench`) still names `notify.rediacc.com`, so narrowing the policies first would stop every send. Owed, in order: `AWS_SES_FROM` to `noreply@notify.rediacc.cloud` and an account redeploy per region and bench, then the narrowed policies, then `rotate ses-<r>`. No repo verb writes the three production policies. The bench policy comes from `benchSesPolicy` (private/account/scripts/rotation/commands/rotate.ts:2141), outside this plan's Owns. `rotate ses-<r>` pushes to `worker:account-<r>`, which the rename runner owns and which do not exist yet under those names (rename L6, L8).
- [ ] M3 [live] One real mail from bench first, then one per region, with headers showing DKIM, SPF and DMARC pass.
  Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.portal_health bench.rediacc.cloud` rc 0, and the received headers recorded here.
    (result 2026-11-09T08:55Z, d778be9d) Blocked. Bench sends with bws `AWS_SES_FROM`, which still names `notify.rediacc.com` (M2), so a bench mail today would not prove the `.cloud` sender. Waits on M2's sender switch and a bench account redeploy (rename-runner resource).

### Routing, live

- [ ] R1 [live] Deploy the www Worker to a `pr-<n>` preview first, seed one fake entry for `acme.example`, and drive the popup end to end: countdown, cancel, change, forward, signup preselect, company link. Then `www.rediacc.com`.
  Accept: `npx tsx packages/www/scripts/probe-region-picker.ts <preview-host>` rc 0 (built by W2), the same for `www.rediacc.com`, and `curl -sD- https://www.rediacc.com/api/geo -o /dev/null | grep -qi 'cache-control: no-store'` rc 0.
    (result 2026-11-09T08:55Z, d778be9d) Blocked on rename L8 and L7. `workers/www/wrangler.toml` binds service `account-eu`, and the account's Worker list (read 2026-11-09 through `deploy-workers`) has no `account-eu`, only `rediacc-account-eu` and `edge-rediacc-account-eu`. A deploy of `www` or a `pr-<n>` preview fails on that binding. `www.rediacc.com` is still a custom domain of `rediacc-www` (rollback handle: its current version 9a3b8f9e-e54f-4bc5-aadb-e0df270e3b5d), and moving that domain is rename L7's unverified step. `curl -sD- https://www.rediacc.com/api/geo` answers 404 today. Ready: `packages/www` builds rc 0 (1853 pages), and the W1 code is tested.
- [ ] R2 [live] Passkey register and login on bench under the new RP ID. A lookup hit and a miss answer the same shape.
  Accept: `curl -fsS -X POST https://www.rediacc.com/api/enterprise-lookup -d '{"domain":"unknown.example"}' | jq -e '.host==null'` rc 0, and the bench passkey login recorded here.
- [ ] LP-bench [live] Fresh bench receipt after R2.
  Accept: live-proof bench account-smoke

### Cleanup

- [ ] C1 [live] After M3 and R1, delete the SES identities `notify.rediacc.com`, `notify.rediacc.io` and `ses.rediacc.io` in every region, their DNS records and the old IAM keys.
  Accept: `! aws --region eu-central-1 sesv2 list-email-identities --query 'EmailIdentities[].IdentityName' --output text | grep -E 'notify\.rediacc\.(com|io)|ses\.rediacc\.io'` rc 0 under the rotation profile, and `npm run check:ci-dkim-notify` rc 0.

## Not verified

- The Public Suffix List's process, its minimum registration term and its effect on a Cloudflare zone apex.
- Turnstile covering subdomains of a listed domain; PLAN-product-domain-rename.md L6 proves it.
- The IAM policy's live text, `AWS_SES_FROM` in bws, whether a lock notification goes to an unknown address, and precedence between a wildcard record and a specific one.
- The bot-management API field in Z3.
