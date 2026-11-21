# PLAN: Site entry points -- onboarding docs links on www, a Downloads link on the home page, and install tabs in the portal

Status: approved -- operator /ask ASKED:2026-11-17T09:06Z ("Site fixes now, private later"); rulings in the Rulings section
Owner: d778be9d
Depends-On: no-dep -- no prerequisite plan; the work is portal and www copy plus a gitlink bump
Priority: P1 -- customer-facing broken links: every "Read tutorial" link on the portal's "Getting started with Rediacc" page answers 404 (the portal host has no /en/docs), and the home page has no way to reach /downloads
Concurrency: parallel -- Wave 1 runs three file-disjoint writers: the portal links (L1-L3), the www home link (D1), and the shared install commands (I1). Wave 2 (I2, I3) starts after I1 lands and both edit private/account/web/src/pages/TutorialSplash.tsx, so they run in sequence with L1, which also edits that file. This plan does not edit packages/www/src/pages/*/downloads.astro or packages/www/src/utils/latest-release.ts, so there is no overlap with PLAN-console-private R4. D1 and I1 both touch packages/www i18n and install.ts respectively, which are disjoint files. Before writing, check block_plan_concurrency for a live holder of the www en.json and the portal onboarding locale files.
Owns: agent/plans/PLAN-site-entry-points.md, private/account (gitlink bump only), private/account/web/src/pages/TutorialSplash.tsx, private/account/web/src/data/onboarding-content.json, private/account/web/src/data/study-content/ms6-compliance.ts, private/account/web/src/data/study-content/mt3-cli.ts, private/account/web/src/i18n/locales/*/onboarding.json, private/account/web/src/pages/__tests__/tutorial-splash-links.test.tsx, private/account/web/src/__tests__/no-relative-site-links.test.ts, packages/shared/src/config/install-commands.ts, packages/shared/src/config/__tests__/install-commands.test.ts, packages/www/src/config/install.ts, packages/www/src/components/solution-pages/SPHomeVideo.astro, packages/www/src/i18n/translations/*.json, packages/www/src/i18n/client-route/*.json, packages/www/src/i18n/.translation-hashes.json
Live-Proof: bench -- the www surface (D1) is proven on the bench www with www-smoke and the account portal surface (L1, I2) with the portal smoke; production is proven after release, edge eu first, then stable, per the release flow (PROD boxes)

## Ask

Operator words, verbatim (2026-11-17):

> "1st the links from private/account https://eu.rediacc.cloud/account/ like https://eu.rediacc.cloud/en/docs/tutorial-installation which appears on 'Getting started with Rediacc' onboarding page is broken! It should show the www page, doesn't it? 2nd I couldn't reach the https://www.rediacc.com/en/downloads page from home page. We should place a button to reach there. ... 3rd The section on account 'Install the CLI / Install the rdc CLI on your laptop with the one-liner from the install page.' shows static install commands but the user may want to install on another platform. How we should presentate it?"

Three outcomes:
1. Onboarding docs links open the www docs page.
2. The home page links to /downloads.
3. The portal install card offers every platform.

## Context (read 2026-11-17 against the tree; a writer re-reads each citation before relying on it)

1. **The broken onboarding link.**
   - `localizeDocsPath` swaps `/en/` for the user's language and returns a path with no origin (private/account/web/src/pages/TutorialSplash.tsx:98-101).
   - It is called at private/account/web/src/pages/TutorialSplash.tsx:200 and rendered as `<a href={docsPath} target="_blank">` at :232. A path with no origin resolves against the portal host, so the link goes to `https://eu.rediacc.cloud/en/docs/...`. The operator reports it as broken, and the lead's live probe saw 404 there and 200 at `https://www.rediacc.com/en/docs/tutorial-installation`.
   - The step data is private/account/web/src/data/onboarding-content.json. It has `docsPath` values such as `/en/docs/tutorial-installation` at :22 and :44, and `/en/docs/tutorial-ssh-keys`, `tutorial-add-server`, `tutorial-create-repo` and `tutorial-vscode-browser` at :66, :88, :110, :132, :154 and :176.
   - Ruling: all docs live on www (PLAN-website-routing-and-mail.md Ruling 12, line 17).
2. **The origin constant.**
   - `WK_SITE_ORIGIN = 'https://www.rediacc.com'` is at packages/shared/src/config/well-known.generated.ts:5.
   - Precedent: `documentUrl(page, lang)` returns `${WK_SITE_ORIGIN}/${lang}/${page}` (packages/shared/src/legal/index.ts:30-36).
   - packages/shared exports `./config/*` (packages/shared/package.json:204-206), so a new file in packages/shared/src/config is importable as `@rediacc/shared/config/<name>`.
3. **Other relative docs links in the portal.** The sweep found these:
   - Study content mostly uses absolute `https://www.rediacc.com/en/...` URLs (for example private/account/web/src/data/study-content/ms1-what-rediacc-is.ts:102, private/account/web/src/data/study-content/mc4-fork-migrate.ts:317).
   - Two have a bare relative path inside the text: private/account/web/src/data/study-content/ms6-compliance.ts:127 (`/en/docs/legal-nis2-dora`) and private/account/web/src/data/study-content/mt3-cli.ts:71 (`/en/docs/rdc-cheat-sheet`).
   - A grep for relative `/en/docs` or `"/docs/"` also lists private/account/web/src/data/enablement-content/competitive-positioning.ts, study-content/mc7-networking-safety.ts, study-content/ms7-competitive.ts and the `partner.json` locales (es, fr, ko, tr, zh, it, ...). Those hits were not read. The matches may be absolute URLs that contain `/en/docs`, so L2 and L3 must classify each hit before editing.
   - Not verified: whether the study renderer turns bare paths in `text` into anchors. If it renders plain text, the relative path is dead text rather than a broken link, and the fix is still to make it absolute so a reader can paste it.
4. **The home video section.** packages/www/src/components/solution-pages/SPHomeVideo.astro:23-27 is `section.sp-home-video > div.sp-home-video-inner.sp-hero-media > SPSolutionVideo slug="home"`. It has a local `<style>` block (:29 on). The lead found SPHomeVideo used only by SPHomePage; the writer re-greps.
5. **The existing Downloads link pattern.**
   - packages/www/src/pages/*/install.astro:31-34 renders `<a href={`/${lang}/downloads`} class="hero-downloads-link">{t('pages.install.hero.downloadsLink')} &rarr;</a>`.
   - The string `pages.install.hero.downloadsLink` is "Visit the Downloads page" (packages/www/src/i18n/translations/en.json:962; packages/www/src/i18n/client-route/en.json:69).
   - The hero ruling n6 (no CTA buttons in any hero, packages/www/src/components/solution-pages/SPHomeHero.astro:20-23) is respected because the link sits under the video, outside the hero.
6. **Install commands today.**
   - The portal onboarding step 1 stores `curl -fsSL https://www.rediacc.com/install.sh | bash` as `command` at private/account/web/src/data/onboarding-content.json:23.
   - TutorialSplash renders that command with a `CopyButton` (private/account/web/src/pages/TutorialSplash.tsx:219) after `substituteCommand` (:90-96).
   - www builds the same one-liners as `QUICK_INSTALL_UNIX` and `QUICK_INSTALL_WIN` from `SITE_URL` (packages/www/src/config/install.ts:42-43). `SITE_URL` comes from packages/www/src/config/constants.ts.
   - www already defines the platform tabs `linux`, `macos`, `windows` (packages/www/src/config/install.ts:25-31).
7. **The page that lists the other install methods.** `packages/www/src/content/docs/en/installation.md` ("Install the Rediacc CLI on Linux, macOS, or Windows") mentions brew, apt and pacman (6 matches on a grep for those words). Docs render at `/<lang>/docs/<slug>` through packages/www/src/pages/*/docs/[slug].astro. The writer opens installation.md to confirm it lists brew, apt, dnf, apk, pacman and Docker, and links to it if so.
8. **Portal strings.** Onboarding strings live in private/account/web/src/i18n/locales/<lang>/onboarding.json (for example `stepDocsLink` at private/account/web/src/i18n/locales/en/onboarding.json:16). The locale folders are ar, de, en, es, et, fr, it, ja, ko, pt, ru, tr, zh (13).
9. **The downloads page itself** builds from the GitHub API (packages/www/src/utils/latest-release.ts). That is out of scope here: PLAN-console-private R4 moves it to the R2 manifest. This plan only links to the page.
10. **Test home.** Portal page tests sit in private/account/web/src/pages/__tests__/ (for example admin-root-api-tokens.test.tsx). The `testing` skill decides placement and what counts as proof the test runs in CI.

## Rulings

- Ruling A (operator, 2026-11-05, via PLAN-website-routing-and-mail.md Ruling 12): "All docs on www."
- Ruling B (ASKED:2026-11-17T08:46Z), download entry on the home page: "Link under the video".
- Ruling C (answered earlier, about 08:0xZ, cite as 2026-11-17), install card: "Tabs, no detection".
- Ruling n6 (standing): no CTA buttons in any hero. Ruling B respects it.

## Design

### 1. Onboarding and portal links go through one helper

Add a helper in the portal, `siteUrl(path, lang)`, that returns `${WK_SITE_ORIGIN}${localized path}`. TutorialSplash uses it at :200 instead of `localizeDocsPath` alone, keeping the `/en/` to `/<lang>/` swap. `onboarding-content.json` keeps its relative `docsPath` values (they are site paths, not hrefs); the origin is added at render time. `target="_blank"` and `rel` stay.

The helper imports `WK_SITE_ORIGIN` from `@rediacc/shared/config/well-known.generated`, or from the package root if the portal already imports it that way (the writer matches the existing portal import style).

### 2. A regression test and a refusal for relative site links

- L1 test: render TutorialSplash for `en` and one other language, collect every anchor whose text is the `stepDocsLink` label, and assert each `href` starts with `WK_SITE_ORIGIN + '/'` and the language segment matches.
- L3 test: scan private/account/web/src (ts, tsx, json, excluding node_modules and locale files that hold prose) for an `href`, `docsPath` or markdown-link value that starts with `/en/docs`, `/docs/` or `/<lang>/docs`, and fail with the file and line. The writer decides, with the `testing` skill, whether a vitest suffices or a check-*.ts gate is warranted; the default is the vitest because the portal's vitest already runs in CI (the writer proves it by locating the CI job that runs it).
- The test allowlists `onboarding-content.json` `docsPath` (relative by design, absolutized at render) and asserts instead that TutorialSplash is the only consumer.

### 3. Study-content sweep

For each relative hit classified in Context 3, rewrite to `https://www.rediacc.com/en/docs/<slug>` (private/account/web/src/data/study-content/ms6-compliance.ts:127, private/account/web/src/data/study-content/mt3-cli.ts:71 first). Locale prose that holds an absolute URL is left alone. Wording is unchanged apart from the URL, so no study-content hash or translation churn is expected; the writer confirms no content-hash gate covers these files.

### 4. Home page Downloads link

In SPHomeVideo.astro, under `SPSolutionVideo` and inside `.sp-home-video-inner` or just after it in the section, add:

`<p class="sp-home-video-note"><a class="sp-home-video-link" href={`/${lang}/downloads`}>{t(...)} &rarr;</a></p>`

Styled locally in the component's `<style>` block: centred, same type scale as `.hero-downloads-link` (install.astro), a minimum tap target of 44px (`min-height: 44px; display: inline-flex; align-items: center`), focus ring from the site tokens, and a `sp-home-video-` prefix on every class to avoid global collisions. Use only existing design tokens.

Translation key: reuse `pages.install.hero.downloadsLink` ("Visit the Downloads page"), which is already in all 13 www locales, if the home component can reach it through its translator. If the writer prefers wording that fits the home context, add `pages.home.video.downloadLink` ("Download the CLI") to en.json and client-route/en.json, regenerate hashes (`npm run i18n:generate-hashes`), and run the naturalization pipeline with `--model haiku` for the 12 other locales per docs/i18n/CONVENTIONS.md. The default is the reuse, which creates no translation churn. A new key is chosen only if the existing string reads wrong under a video.

### 5. Install card: tabs, no detection

Shared module `packages/shared/src/config/install-commands.ts` exports, built from `WK_SITE_ORIGIN`:

- `QUICK_INSTALL_UNIX_COMMAND = curl -fsSL ${WK_SITE_ORIGIN}/install.sh | bash`
- `QUICK_INSTALL_WIN_COMMAND = irm ${WK_SITE_ORIGIN}/install.ps1 | iex`

These are the bare commands, without the `# Linux / macOS` comment lines that www prepends. www's `QUICK_INSTALL_UNIX` and `QUICK_INSTALL_WIN` in packages/www/src/config/install.ts keep their comment line and build on the shared constants, so rendered www output stays byte-identical. A unit test pins the exact strings.

Portal: on the step whose `command` is the install one-liner, TutorialSplash renders a two-tab control, "Linux / macOS" first (default) and "Windows", each tab with its own command and `CopyButton`, with no OS detection. Below the tabs, a link "More install methods" to `${WK_SITE_ORIGIN}/${lang}/docs/installation`. The step is marked in `onboarding-content.json` by a field such as `"installTabs": true` instead of a `command` string, so the hard-coded one-liner at :23 goes away, and every other step keeps using `command` through `substituteCommand`. The tabs use the portal's existing tab primitive if one exists (the writer checks private/account/web/src/components/ui); otherwise two buttons with `role="tab"` and keyboard support.

Portal strings in `onboarding.json` for all 13 locales: tab labels (`installTabUnix`, `installTabWindows`) and `installMoreMethods`. English is authored; the other 12 are written natural, not literal (CONVENTIONS section 2 applies to the www catalog, and the portal locales follow the same naturalization standard).

## Not verified (each owner re-checks)

- Whether the study renderer anchors bare paths (Context 3).
- Whether `partner.json`, competitive-positioning.ts, mc7 and ms7 hits are relative links or absolute URLs.
- Whether `docs/installation` lists brew, apt, dnf, apk, pacman and Docker (Context 7).
- Whether SPHomeVideo is used by SPHomePage only (Context 4).
- Which portal tab primitive exists.
- The names of the "www-smoke" and "portal smoke" runners, which the lead named; the writer finds the exact invocation in docs/agent-reference before filling the Accept lines marked below.

## Tasks

### Wave 1

- [x] L1 [writer] Onboarding docs links open www: add the `siteUrl` helper, use it in TutorialSplash, and add the vitest that renders TutorialSplash in `en` and one other language and asserts every docs anchor starts with `WK_SITE_ORIGIN`.
  - Owns: private/account/web/src/pages/TutorialSplash.tsx, private/account/web/src/pages/__tests__/tutorial-splash-links.test.tsx.
  - Accept: `cd /home/developer/console/private/account/web && npx vitest run src/pages/__tests__/tutorial-splash-links.test.tsx` rc 0, and `grep -n 'href={docsPath}' src/pages/TutorialSplash.tsx` prints nothing.
    (ticked) 2026-11-17T15:07:16Z by d778be9d: commit:21433b52d8 account 859bbc1; vitest tutorial-splash-links rc=0; grep href={docsPath} empty; tsc rc=0
- [x] L2 [writer] Study-content sweep: classify every relative `/en/docs` or `/docs/` hit from Context 3, and make the ones that are links or paste targets absolute (private/account/web/src/data/study-content/ms6-compliance.ts:127 and private/account/web/src/data/study-content/mt3-cli.ts:71 at minimum).
  - Owns: private/account/web/src/data/study-content/ms6-compliance.ts, private/account/web/src/data/study-content/mt3-cli.ts.
  - Accept: `cd /home/developer/console && grep -rnE "(^|[^/a-z.])/(en|[a-z]{2})/docs/" private/account/web/src/data/study-content | grep -v "rediacc.com/" | wc -l` prints 0.
    (ticked) 2026-11-17T15:07:18Z by d778be9d: commit:21433b52d8 account 859bbc1; ms6:127 and mt3:71 absolute; no-relative-site-links rc=0 (the box's own grep is vacuous, the test is the check)
    Note (2026-11-19): this note supersedes the tick's remark that the box's own grep is vacuous. Re-run 2026-11-19: the box's own grep prints 0 on the current tree, which alone cannot show the grep is live, since a grep that never matches also prints 0. The witness is the no-relative-site-links test, red before the fix and green after.
- [x] L3 [writer] Relative-link refusal: a test that fails on any relative `/en/docs`, `/<lang>/docs` or `/docs/` href in private/account/web/src, with `onboarding-content.json` `docsPath` allowlisted and TutorialSplash pinned as its only consumer. Run it once against the pre-fix tree (or a stash of L1) to show it fails there.
  - Owns: private/account/web/src/__tests__/no-relative-site-links.test.ts.
  - Accept: `cd /home/developer/console/private/account/web && npx vitest run src/__tests__/no-relative-site-links.test.ts` rc 0.
    (ticked) 2026-11-17T15:07:20Z by d778be9d: commit:21433b52d8 account 859bbc1; test red on the pre-fix tree (ms6:127, mt3:71, href={docsPath}), rc=0 after
- [x] D1 [writer] Home Downloads link under the video, styled locally with a 44px tap target, with the i18n decision from Design 4 (reuse by default; a new key only if recorded with the reason, then hashes regenerated and 12 locales naturalized).
  - Owns: packages/www/src/components/solution-pages/SPHomeVideo.astro, and, only if a new key is chosen, packages/www/src/i18n/translations/*.json, packages/www/src/i18n/client-route/*.json, packages/www/src/i18n/.translation-hashes.json.
  - Accept: `cd /home/developer/console && grep -c 'downloads' packages/www/src/components/solution-pages/SPHomeVideo.astro` prints at least 1, `grep -c 'sp-home-video-' packages/www/src/components/solution-pages/SPHomeVideo.astro` prints at least 3, and the www build for the home page contains `href="/en/downloads"` (the writer fills in the build command and the dist path they used).
    (ticked) 2026-11-17T15:07:21Z by d778be9d: commit:11e5072ec2 grep downloads=3, sp-home-video-=8; astro build rc=0, dist/en/index.html has href="/en/downloads"; reused pages.install.hero.downloadsLink, no new key
- [x] I1 [writer] Shared install commands: add packages/shared/src/config/install-commands.ts, a unit test pinning both strings, and make www's `QUICK_INSTALL_UNIX` and `QUICK_INSTALL_WIN` build on them with unchanged rendered output.
  - Owns: packages/shared/src/config/install-commands.ts, packages/shared/src/config/__tests__/install-commands.test.ts, packages/www/src/config/install.ts.
  - Accept: `cd /home/developer/console && npx vitest run packages/shared/src/config/__tests__/install-commands.test.ts` rc 0, and `grep -c 'install-commands' packages/www/src/config/install.ts` prints at least 1.
    (ticked) 2026-11-17T15:07:23Z by d778be9d: commit:959216f248 shared vitest install-commands rc=0 (3 passed, rerun on landed tree), shared build rc=0, www strings byte-identical
    Note (2026-11-19): re-run 2026-11-19: `grep -c 'install-commands' packages/www/src/config/install.ts` prints 1.

### Wave 2, after I1 lands

- [x] I2 [writer] Portal install tabs: Linux/macOS first and Windows, each with copy, no OS detection, plus "More install methods" to `${WK_SITE_ORIGIN}/${lang}/docs/installation`; the strings in all 13 `onboarding.json` locales; a vitest that renders the step and asserts both commands (from the shared constants), the default tab, switching, and the more-methods href.
  - Owns: private/account/web/src/pages/TutorialSplash.tsx, private/account/web/src/i18n/locales/*/onboarding.json, private/account/web/src/pages/__tests__/tutorial-splash-install-tabs.test.tsx.
  - Accept: `cd /home/developer/console/private/account/web && npx vitest run src/pages/__tests__/tutorial-splash-install-tabs.test.tsx` rc 0, and `for l in ar de en es et fr it ja ko pt ru tr zh; do grep -c installMoreMethods src/i18n/locales/$l/onboarding.json; done | sort -u` prints only 1.
    (ticked) 2026-11-17T15:21:27Z by d778be9d: commit:956e037614 account 2803c3c; vitest install-tabs red 4/4 before, rc=0 after; installMoreMethods once in each of 13 locales; vitest src/pages rc=0 (169 passed on landed tree); tsc rc=0
- [x] I3 [writer] Remove the hard-coded one-liner from onboarding-content.json (the install step uses the tabs marker), keeping every other step's `command` working through `substituteCommand`.
  - Owns: private/account/web/src/data/onboarding-content.json, private/account/web/src/pages/TutorialSplash.tsx.
  - Accept: `cd /home/developer/console && grep -c 'install.sh' private/account/web/src/data/onboarding-content.json` prints 0, and `cd private/account/web && npx vitest run src/pages/__tests__/tutorial-splash-links.test.tsx src/pages/__tests__/tutorial-splash-install-tabs.test.tsx` rc 0.
    (ticked) 2026-11-17T15:21:36Z by d778be9d: commit:956e037614 account 04fd467; install step uses the install-tabs widget, grep -c install.sh = 0; substitution test red before, rc=0 after
    Note (2026-11-19): re-run 2026-11-19: vitest tutorial-splash-links.test.tsx and tutorial-splash-install-tabs.test.tsx, 2 files and 8 tests passed, rc 0.

### Live queue: bench first (Ruling 4), then production after the PR merges

- [ ] LP-bench [live] The home page on the bench www links to /downloads, and that page answers.
  - Accept: live-proof bench www-smoke
  - Also: `curl -s https://<bench www host>/en/ | grep -c 'href="/en/downloads"'` prints at least 1.
- [ ] BP-portal [live] On the bench portal, the Getting started page shows the install tabs, and every "Read tutorial" link points at the www origin.
  - Accept: the portal smoke against the bench passes (exact invocation recorded by the writer), with a recorded check that each docs anchor on the Getting started page has an `href` starting `https://www.rediacc.com/`, and a `curl -s -o /dev/null -w '%{http_code}' https://www.rediacc.com/en/docs/tutorial-installation` that prints 200.
- [ ] PROD-edge [live] After the release flow's edge deploy of eu is green: repeat both bench checks against production edge eu.
  - Accept: `curl -s https://www.rediacc.com/en/ | grep -c 'href="/en/downloads"'` prints at least 1, and the portal smoke against edge eu passes.
- [ ] PROD-stable [live] After the stable promotion per the release flow: repeat on stable eu, and confirm the originally reported link no longer 404s from the portal page.
  - Accept: the portal smoke against stable eu passes, and the Getting started "Read tutorial" anchors on https://eu.rediacc.cloud/account/ all resolve to a 200 on www.rediacc.com.
