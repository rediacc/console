# PLAN: account sidebar redesign -- one mode's links at a time behind a workspace switcher, a page search and the bell on top, a user menu with a confirmed sign-out at the bottom, and the raw offer-setup labels (P8) fixed
Status: approved -- operator answered O1-O7 on 2026-11-19 (ASKED:2026-11-19): the plan's defaults stand except where ## Rulings records otherwise (P8 adds the raw-key gate G1, O6 becomes a scripted bench test partner B1 and an automated bench walk-through B2)
Depends-On: no-dep -- builds on landed portal code; PLAN-account-notices.md W1 (NoticeBell, the AppSidebar bell slot) is ticked and its open P1 is a lead deploy box that edits no file here
Owner: d778be9d
First-Seen: 2026-11-19
Priority: P1 -- the footer row that shows the user's email signs out on one click with no confirmation (private/account/web/src/components/AppSidebar.tsx:546-555); users and an agent have signed out by accident
Concurrency: parallel -- writer boxes own disjoint files; wave 0 S1 and F1; wave 1 I1; wave 2 T1, W1, K1 and U1 (4 writers); wave 3 N1 and G1; wave 4 E1, B1 and B2; then X1, X2 and LP-bench in the main checkout. No live plan owns the portal files (checked 2026-11-19); partner.json is avoided because PLAN-partner-sales-track.md D3 owns it. B1 edits the root-grants files that PLAN-root-grants.md also owns; every code box there is ticked and its open boxes are live boxes that edit no file, so the two plans do not collide
Owns: agent/plans/PLAN-account-sidebar-redesign.md, private/account/web/src/components/AppSidebar.tsx, private/account/web/src/components/Layout.tsx, private/account/web/src/components/NoticeBell.tsx, private/account/web/src/components/ThemeToggle.tsx (deleted), private/account/web/src/components/LanguageSwitcher.tsx (deleted), private/account/web/src/components/SignOutConfirmDialog.tsx (new), private/account/web/src/components/sidebar/** (new), private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/palette-context.tsx (new), private/account/web/src/components/console/__tests__/command-palette*.test.ts*, private/account/web/src/components/ui/alert-dialog.tsx (new), private/account/web/src/components/ui/avatar.tsx (new), private/account/web/src/components/ui/toggle-group.tsx (new), private/account/web/src/components/__tests__/sign-out-confirm.test.tsx (new), private/account/web/src/components/__tests__/app-sidebar.test.tsx (new), private/account/web/src/components/__tests__/notice-bell.test.tsx, private/account/web/src/lib/nav-config.ts (new), private/account/web/src/lib/__tests__/nav-config.test.ts (new), private/account/web/src/hooks/use-theme.ts (new), private/account/web/src/hooks/use-persistent-state.ts (new), private/account/web/src/hooks/__tests__/use-theme.test.ts (new), private/account/web/src/hooks/__tests__/use-persistent-state.test.ts (new), private/account/web/src/i18n/config.ts, private/account/web/src/i18n/language-labels.ts (new), private/account/web/src/i18n/__tests__/nav-keys.test.ts (new), private/account/web/src/i18n/locales/*/common.json, private/account/web/src/i18n/locales/*/nav.json (new), private/account/web/src/i18n/locales/*/offerUi.json (new), private/account/web/src/i18n/locales/.translation-hashes.json, private/account/web/src/pages/partner/offer/types.ts, private/account/web/src/pages/partner/offer/OfferBuilder.tsx, private/account/web/src/pages/partner/offer/__tests__/ui-keys.test.ts (new), scripts/gates/check-account-i18n-key-usage.ts, private/account/e2e/src/pages/shared/NavigationComponent.ts, private/account/e2e/src/base/AuthenticatedTest.ts, private/account/e2e/tests/01-auth/01-02-login.test.ts, private/account/e2e/tests/01-auth/01-03-logout.test.ts, private/account/e2e/tests/01-auth/01-05-session.test.ts, private/account/e2e/tests/01-auth/01-06-logout-confirm.test.ts (new), private/account/e2e/tests/07-navigation/07-01-sidebar.test.ts, private/account/e2e/tests/07-navigation/07-02-sidebar-modes.test.ts (new), private/account/e2e/tests/08-journeys/08-01-customer-journey.test.ts, private/account/e2e/tests/08-journeys/08-02-admin-journey.test.ts, private/account/e2e/tests/13-invoices/13-02-admin-invoices.test.ts, private/account/e2e/tests/16-team/16-03-two-org-selection.test.ts, private/account/e2e/tests/19-i18n/19-01-language-sync.test.ts, private/account/e2e/tests/25-partner-admin/25-06-admin-menu-toggle.test.ts (replaced by 25-06-admin-mode.test.ts), private/account/e2e/tests/26-partner-program-chooser/26-01-chooser.test.ts, private/account/web/src/test/raw-key-scan.ts (new), private/account/web/src/test/__tests__/raw-key-render.test.tsx (new), scripts/gates/check-account-raw-keys.ts (new), scripts/__tests__/check-account-raw-keys.control.ts (new), .ci/config/account-raw-key-allowlist.json (new), package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .github/workflows/ci-quality.yml, docs/agent-reference/ci-gates.md, .ci/config/root-grants.json, .ci/rediacc_ci/ops/root_grants.py, .ci/rediacc_ci/tests/test_ops_root_grants.py, private/account/src/types/root-grants.ts, private/account/src/services/root-grants.service.ts, private/account/src/dto/root-grants.dto.ts, private/account/tests/integration/root-grants.test.ts, private/account/tests/integration/root-grants-parity.test.ts, private/account/e2e/playwright.live.config.ts, private/account/e2e/tests/07-navigation/07-90-live-sidebar.test.ts (new), private/account/e2e/src/utils/live-sidebar-walk.ts (new), private/account (gitlink bump only)
Live-Proof: bench -- the edited sources are the portal bundle under private/account/web and the root-grants route under private/account/src, both part of the account surface, which bench admits; X2 runs the automated walk-through (B2) against the bench portal

## Context (verified 2026-11-19 against the tree; a writer re-reads a line before relying on it)

The handoff, claim by claim. RIGHT means the code agrees; WRONG or INCOMPLETE says what the code shows instead.

1. **P2, RIGHT.** The footer button with `data-testid="sidebar-logout"` calls `logout` on click and its label is `user?.email` (private/account/web/src/components/AppSidebar.tsx:546-555). There is no confirmation. `logout` clears state and storage at once (private/account/web/src/auth/AuthContext.tsx:442-479).
2. **P3, WRONG in detail.** `org-switcher` shows the org name (`organization?.name ?? t('chooseOrganization')`), not the email, and it renders only when `orgs.length > 1` (private/account/web/src/components/AppSidebar.tsx:479-515). The rows that look alike are the org row and the email/logout row.
3. **P4, RIGHT.** `NoticeBell` sits alone in a header menu item that is hidden in the icon rail (private/account/web/src/components/AppSidebar.tsx:384-386). The bell is a popover with mark-all and "View all", capped at 99 (private/account/web/src/components/NoticeBell.tsx:23, :123-169). Handoff 3.7 would replace it with a plain link, which is a regression.
4. **P5, RIGHT.** The language, logout and theme controls share one footer row (private/account/web/src/components/AppSidebar.tsx:542-559). `ThemeToggle` only flips light and dark; its `useTheme`, which knows `system`, is private to the file (private/account/web/src/components/ThemeToggle.tsx:19-45, :47-64). The theme is a `data-theme` attribute, not a class (private/account/web/src/main.tsx:8-15, private/account/web/src/styles/app.css:3). `LanguageSwitcher` writes the language cookie before `changeLanguage` (private/account/web/src/components/LanguageSwitcher.tsx:38-41); the handoff sample skips the cookie.
5. **P1/P6, RIGHT, inventory INCOMPLETE.**
   - The customer list is private/account/web/src/components/AppSidebar.tsx:101-116; the admin list is :118-144.
   - Admin has 21 items, not 20. The handoff misses Feedback `/account/admin/feedback` (:127) and the on-prem-only "On-Premise Cert" (:243-248).
   - The handoff also misses the team switcher (:517-540).
   - It misses this gating: Partner Team needs `isPartnerAdmin` (:213-216); customer Delegation Certs needs a subscription (:221-232, :309); the Console group needs `useConsoleAccess` (:235-240, :313); Permissions needs `isOrgAdmin` (:190-191, :341).
   - The four console family items are generated from `FAMILY_PAGES` (:170-176; private/account/web/src/lib/resource-pages.ts:152-189). `FAMILY_NAV_ICONS.storages` (:164) is dead.
   - Nine labels are hardcoded English and untranslated in all locales (:104, :111, :113, :122, :128, :129, :197, :227, :246).
6. **Rule 1 "mode comes from the route", WRONG for partner mode.**
   - Partner mode is a property of the active org: `mode = isPartner ? 'partner' : 'customer'` (private/account/web/src/components/AppSidebar.tsx:333), where `isPartner = !!partner` (private/account/web/src/auth/AuthContext.tsx:483).
   - Entering or leaving it switches org and does a hard navigation (`enterPartnerMode`/`enterCustomerMode`, private/account/web/src/auth/AuthContext.tsx:370-410). `RequirePartner` auto-switches a single-partner-org user on `/account/partner/*` (private/account/web/src/auth/ProtectedRoute.tsx:88-175).
   - Shared pages (`/account/settings`, `/account/notices`, `/account/support`) are reached in partner mode, so route-only derivation would show customer links for a partner org.
   - Admin visibility today is `isRoot && (localStorage adminMenuVisible || on /account/admin)` (private/account/web/src/components/AppSidebar.tsx:319-331). That part is route-shaped, as the handoff says.
7. **Rule 3 active item, ALREADY TRUE.** `computeActivePath` already picks the longest prefix over the rendered nav. It maps `/account/partner/exam` to Study and matches the onboarding index `/account/` exactly (private/account/web/src/components/AppSidebar.tsx:255-277). The new helper must keep both special cases.
8. **Rule 5 ⌘K search, CONFLICTS with landed code.**
   - `CommandPalette` already binds Ctrl/⌘+K on `document` (private/account/web/src/components/console/CommandPalette.tsx:131, :167-176). It is mounted only for console-entitled users (private/account/web/src/components/Layout.tsx:52-62).
   - That comment also warns the provider tree must not branch on `allowed`.
   - A second palette would double-bind the key. The e2e console suites use `palette-input` (private/account/e2e/tests/27-console/27-01-console.test.ts:67 and six more).
9. **P8, MISDIAGNOSED.**
   - The seven labels are not i18n keys. They are `ui('...')` lookups (private/account/web/src/pages/partner/offer/sections/SetupSection.tsx:73, :120, :146, :218, :224, :234, :261) into the served catalog's English `uiText`.
   - `makeUi` returns the key itself when the catalog lacks it (private/account/web/src/pages/partner/offer/types.ts:23-29).
   - The served catalog is the active `catalog_versions` row (private/account/src/services/catalog.service.ts:107-119), seeded by migration 0034. The default catalog's `uiText` (private/account/src/pricing/catalog.default.ts:858-1121) also lacks exactly these seven.
   - The sweep compared the 146 distinct `ui('…')` literals under pages/partner/offer with the 234 `uiText` keys: these seven are missing and nothing else is.
10. **Key-usage gate.** `npx tsx scripts/gates/check-account-i18n-key-usage.ts` passes: 2844 references checked, 34 dynamic, 296 files. By its own header it cannot see `t(item.labelKey)`, and it does not read `ui()` at all. That is why P8 and the nine hardcoded labels got through. A nav built from config makes every label dynamic, so the new keys need their own resolution test (I1).
11. **"Communications" (`/account/notifications`) is the email preferences page.** See private/account/web/src/router.tsx:254, the e2e title "Communications Preferences" (private/account/e2e/tests/18-notifications/18-01-communications.test.ts:9), and agent/plans/PLAN-account-notices.md Context 11. It goes in the user menu, not a bell tab.
12. **`/account/machines` and `/account/console/machines` hold different data.** The first is the licence-slot page ("{{count}} active machines in {{max}} available slots", private/account/web/src/i18n/locales/en/machines.json). The second is the config machines of the web console. The routes are private/account/web/src/router.tsx:247 and :289.
13. **No partner application route in the portal.** The partner routes are private/account/web/src/router.tsx:357-388. The application form is on www (packages/www/src/components/PartnerApplicationForm.tsx), posting to `POST /partner/apply` with Turnstile (private/account/src/routes/partner-apply.ts:20-23).
14. **Primitives.**
   - `components/ui` has collapsible, command, dialog, dropdown-menu, popover and sheet. It has no alert-dialog, avatar or toggle-group, and sidebar.tsx exports no `SidebarRail` (private/account/web/src/components/ui/sidebar.tsx:477).
   - `radix-ui` (umbrella, private/account/web/package.json:27) and `cmdk` (:23) are already dependencies, so the three wrappers need no new package.
   - The sidebar's open/closed state already persists in the `sidebar_state` cookie (private/account/web/src/components/ui/sidebar.tsx:20).
   - `UserProfile.name` is an empty string until set (private/account/web/src/api/types.ts:3-15).
15. **e2e consumers of the footer IDs (grep of private/account/e2e).**
   - `admin-menu-toggle`: private/account/e2e/tests/07-navigation/07-01-sidebar.test.ts:72, :84; private/account/e2e/tests/08-journeys/08-02-admin-journey.test.ts:36; private/account/e2e/tests/25-partner-admin/25-06-admin-menu-toggle.test.ts:21, :36. The `adminPage` fixture seeds `adminMenuVisible` (private/account/e2e/src/base/AuthenticatedTest.ts:61-70).
   - `sidebar-logout`: private/account/e2e/src/pages/shared/NavigationComponent.ts:58, :116-118; private/account/e2e/tests/16-team/16-03-two-org-selection.test.ts:121.
   - `org-switcher`: 16-03:45.
   - `language-switcher-trigger` and `language-option-de`: private/account/e2e/tests/19-i18n/19-01-language-sync.test.ts:42-46.
   - `partner-mode-banner`: private/account/e2e/tests/26-partner-program-chooser/26-01-chooser.test.ts:79. `enter-partner-program`: 26-01:105, :132.
   - `theme-toggle` and `partner-mode-tier-badge`: no e2e consumer.
   - Selectors that are not test IDs and also break:
     - "First footer menu-button = logout": private/account/e2e/tests/01-auth/01-02-login.test.ts:34, private/account/e2e/tests/01-auth/01-03-logout.test.ts:23, private/account/e2e/tests/01-auth/01-05-session.test.ts:23.
     - Settings clicked in the sidebar: private/account/e2e/src/pages/shared/NavigationComponent.ts:46-48 `settingsLink`, `clickLink('Settings')` in 07-01:40, :110, :134 and 08-01:110.
     - The admin group label "Admin": private/account/e2e/src/pages/shared/NavigationComponent.ts:49-51; private/account/e2e/tests/13-invoices/13-02-admin-invoices.test.ts:10-12.
16. **i18n.**
    - Locale directories: ar de en es et fr it ja ko pt ru tr zh under private/account/web/src/i18n/locales/.
    - Namespaces are registered in private/account/web/src/i18n/config.ts:31-48.
    - One hash manifest, private/account/web/src/i18n/locales/.translation-hashes.json, is regenerated by `npm run i18n:generate-hashes`; every box that edits a locale file writes it.
    - Naturalization rules: docs/i18n/CONVENTIONS.md section 2 (naturalized, never word-for-word; haiku for cost) and the section on byte-identical-to-English values.
    - The gates used by the last portal locale change (private/account 141c3d8): `check:ci-i18n-completeness`, `placeholders`, `cross-locale`, `naturalization`, `hashes`, `account-key-usage`.
17. **Tests.**
    - Portal unit tests: vitest in jsdom, `src/**/*.test.{ts,tsx}`, with setup importing the real i18n config (private/account/web/vitest.config.ts:14-16, private/account/web/src/test/setup.ts). No sidebar unit test exists today.
    - Account e2e: `./run.sh account test e2e --grep <tag>` with `./run.sh account dev` running (private/account/CLAUDE.md, *E2E Tests*).

## Rulings
- Operator 2026-11-19 (requirements for this plan):
  - one plan file, mainly private/account, running in parallel with other work (disjoint Owns per writer box, Concurrency: parallel);
  - unit tests for every behaviour change, and e2e for the logout confirmation and mode switching;
  - keep or migrate every footer test ID the e2e suites use;
  - translations in all 13 locales, naturalized, never word-for-word;
  - every raw key with no mapping fixed, meaning the seven P8 keys plus any other key a sweep finds.
- Standing: one operator, clean break, no compatibility shims (CLAUDE.md rule 2). Retired test IDs and the `adminMenuVisible` key are removed, not aliased; the migration table in Design 8 is the record.
- The handoff's prototype is a layout reference only and is not ported (handoff appendix).
- Operator 2026-11-19 (ASKED:2026-11-19), answers to O1-O7:
  - O1 partner mode source, O3 console group, O4 no "Become a partner", O5 bell popover, O7 the seven labels only: the defaults stand.
  - O2 machines: "Keep both, rename one". The licence page stays "Machines" under Infrastructure and the web console page is "Console machines".
  - Search: "One palette, everyone". Design 5 runs as written: one Ctrl/⌘+K palette for every authenticated user.
  - P8: "Fix the 7, all locales AND improve CI to catch such issues". T1 fixes the seven in 13 locales, and the new box G1 adds a gate that catches a raw key reaching the UI by construction (Design 7).
  - O6 bench partner: "Create one via root grants but improve testing. It should not stay on context. We need automated testing even for partner mode." B1 creates a dedicated bench test partner org through root grants (scripted, idempotent, bench only, never production), B2 turns the bench walk-through into a committed, automated browser test, and X2 runs it. The local e2e partner suite (E1, 07-02) stays the CI net.

## Design 1: modes
- `navMode({pathname, isRoot, isPartner})` in private/account/web/src/lib/nav-config.ts returns:
  - `admin` when `isRoot` and the path is `/account/admin` or below;
  - otherwise `partner` when `isPartner`;
  - otherwise `customer`.
- A non-root user on an admin path gets the org mode (the root route guard still refuses the page).
- This corrects handoff rule 1 (Context 6). Partner mode stays a property of the active org (O1).
- Switching mode, by entry:
  - Customer account: `enterCustomerMode()`.
  - Partner program: `enterPartnerMode()`. That opens the program chooser when there are several partner orgs, which is the existing behaviour.
  - Admin console: `navigate('/account/admin')`.
  - Admin "Exit": navigates to the org mode's home (`/account/partner` when `isPartner`, else `/account/dashboard`).
- The two org-mode switches keep their hard navigation (private/account/web/src/auth/AuthContext.tsx:384-386, :406-407).
- Only one mode's links render. The `adminMenuVisible` preference and its toggle are deleted (clean break).

## Design 2: nav config (single source)
- `NAV: Record<NavMode, NavGroup[]>`.
- `NavItem = {id, labelKey, to, icon, requires?: Capability[], match?: 'exact'}`.
- `NavGroup = {id, labelKey?, collapsible?, defaultOpen?, items}`.
- `Capability` is one of `subscription | consoleAllowed | orgAdmin | partnerAdmin | onPremise`.
- `visibleNav(mode, caps)` drops gated items and empty groups.
- Customer:
  - home: Dashboard; Getting started (`/account/`, exact).
  - Infrastructure: Machines, Backup storage.
  - Console (collapsible, open by default, `consoleAllowed`): Console, Commands, Console machines, the four `FAMILY_PAGES` entries (still generated), Jobs, Config, Permissions (`orgAdmin`).
  - Billing: Subscription, Invoices.
  - Security: API tokens, Delegation certs (`subscription`), Config storage.
  - Organization: Organization and teams, Activity.
- Partner:
  - home: Dashboard.
  - Sell: Customers, Deals, Offers, Enablement.
  - Learn: Study, Daily drill, Certificates.
  - Organization: Team (`partnerAdmin`; the group disappears without it).
- Admin:
  - home: Overview, Activity.
  - Partners: Partners, Applications, Partner deals, Quotes, Delegation certs.
  - Billing: Subscriptions, Invoices, Eval licenses, Stripe.
  - Learning: Question bank, Certificates.
  - Outreach: Newsletter, Contact, Feedback.
  - Platform (collapsible, closed by default): Config storage, Version policy, Catalog versions, Root API tokens, Name changes, On-premise cert (`onPremise`).
- Out of the list:
  - Notices goes to the bell.
  - Communications becomes "Communication preferences" in the user menu (Context 11).
  - Settings goes to the user menu.
  - Support becomes "Help and support", pinned above the user row.
- `activeItemId(pathname, groups)` is a longest-prefix match. An `exact` item matches only itself. `/account/partner/exam/*` resolves as `/account/partner/study`, as today.
- `paletteEntries(caps, mode)` lists:
  - the current org mode's visible items;
  - the admin items when `isRoot`;
  - the account pages (Settings, Communication preferences, Notices, Help and support);
  - the mode-switch actions the user may take.
- It never lists the other org mode's pages, because reaching them takes an org switch.
- Group open state goes through `usePersistentState('sidebar:groups:<userId>', {})`. A group holding the active item is always open.
- Labels use the `nav` namespace (`nav:item.*`, `nav:group.*`), except the console group, which reuses `console:nav*` and the `FAMILY_PAGES` keys (`console:navConsole`, `navCommands`, `navJobs`, `navConfig`, `navPermissions`). `nav:item.consoleMachines` is new.

## Design 3: header (where am I)
- **WorkspaceSwitcher** (private/account/web/src/components/sidebar/WorkspaceSwitcher.tsx) is a DropdownMenu on a `size="lg"` SidebarMenuButton, `data-testid="workspace-switcher"`.
  - The trigger shows the logo, the org name (or `nav:workspace.chooseOrganization`), and a subtitle: "Customer account", or the partner name plus `TierBadge` (`testId="partner-mode-tier-badge"`, kept).
  - Menu, Organizations section: every org as `org-option-<orgId>`, with `TierBadge testId="org-option-tier-badge"` (kept) for partner orgs. Selecting one runs the `onSelectOrg` logic moved from private/account/web/src/components/AppSidebar.tsx:345-361.
  - Menu, Teams section: shown when there is more than one team, as `team-option-<teamId>` with `switchTeam` (the switcher at private/account/web/src/components/AppSidebar.tsx:517-540 moves here).
  - Menu, Workspace section: `enter-customer-mode` (only in partner mode); `enter-partner-program` (kept ID, shown when `hasPartnerOrg && !isPartner`); `switch-program` (in partner mode with several partner orgs; opens the chooser); `enter-admin` (`isRoot`).
  - In the icon rail only the logo shows, and the tooltip carries the org name.
- **AdminBanner** (components/sidebar/AdminBanner.tsx), in admin mode instead of the switcher: an amber button `data-testid="admin-banner"`, reading "Admin console" with "Exit" (`admin-exit`). Exit goes to the org mode's home. It must reach WCAG AA contrast in light and dark mode against app.css.
- **Search row:**
  - `SidebarSearch` (components/sidebar/SidebarSearch.tsx, `data-testid="sidebar-search"`) shows "Search" and a shortcut hint (⌘K on macOS, Ctrl K elsewhere). It opens the palette through `usePalette()`.
  - The existing `NoticeBell` sits beside it as a square icon button. Its test IDs are unchanged and its popover stays (O5). In the icon rail both become icons and stack vertically.
  - The mobile header bell (private/account/web/src/components/Layout.tsx:97-109) stays.

## Design 4: footer (who am I)
- **Help and support**: a SidebarMenuButton link to `/account/support`, `data-testid="nav-support"`.
- **NavUser** (components/sidebar/NavUser.tsx):
  - The trigger is `data-testid="user-menu-trigger"`, `aria-label` "Open account menu". It shows an avatar with initials from `name || email`, then the name (or the email when the name is empty) and the email in muted text.
  - The trigger only opens the menu. No element that shows the email can sign out.
  - Menu, in order:
    - a label with the name and email;
    - Settings;
    - Communication preferences (`/account/notifications`);
    - Theme: a ToggleGroup `data-testid="theme-toggle"` (kept) with `theme-option-light|dark|system`, through `useTheme`;
    - Language: a submenu whose trigger is `data-testid="language-switcher-trigger"` (kept), with items `language-option-<lang>` (kept); selecting runs `writeLanguageCookie` and then `i18n.changeLanguage`, labels from `i18n/language-labels.ts`;
    - Sign out, in the destructive colour, `data-testid="sidebar-logout"` (kept).
  - Sign out opens `SignOutConfirmDialog` (`sidebar-logout-confirm`, `sidebar-logout-cancel`). Only confirm calls `logout()`.
  - In the icon rail only the avatar shows.
- **SignOutConfirmDialog** (components/SignOutConfirmDialog.tsx) is controlled (`open`, `onOpenChange`) and built on a new `components/ui/alert-dialog.tsx` (radix AlertDialog, role `alertdialog`, focus starts on Cancel). It is reused by the user menu, the palette action, and the interim footer in S1.

## Design 5: one palette
- `CommandPalette` becomes the portal-wide palette with a single Ctrl/⌘+K handler.
- `Layout.tsx` mounts it for every authenticated user, inside the same `ConfigSessionProvider`/`ConsoleSessionScope`, without branching the tree. The `allowed` verdict becomes a prop.
- Open state lives in `components/console/palette-context.tsx` (`PaletteProvider`, `usePalette()`), so `SidebarSearch` and the key share it.
- Groups:
  - "Pages", tagged by mode, from `paletteEntries`;
  - "Actions": Toggle theme, Switch to partner program or customer account (when permitted), and "Sign out…", which opens the confirm dialog and never signs out directly;
  - console Recent, the domains and the resources, only when `allowed` (unchanged).
- Test IDs `palette-input` and `palette-list` are kept. New: `palette-page-item`, `palette-action-item`.
- The placeholder is "Search pages" without console access and "Search pages and commands" with it.

## Design 6: i18n
- New namespaces `nav` and `offerUi`, registered in i18n/config.ts.
- Sign-out strings go in `common` (S1, so the P2 fix ships alone): `signOutMenuItem`, `signOutTitle` ("Sign out of Rediacc?"), `signOutBody` ("Sign in again to continue."), `signOutConfirm`, `signOutCancel` ("Stay signed in").
- `nav.json`, every label in sentence case:
  - `item.*`, one per Design 2 item plus `notices`, `support`, `settings`, `communicationPrefs`, `helpAndSupport`;
  - `group.*`: infrastructure, billing, security, organization, sell, learn, partners, learning, outreach, platform;
  - `workspace.*`: organizations, teams, modes, customerAccount, partnerProgram, switchProgram, adminConsole, exit, chooseOrganization, openMenu;
  - `search.*`: button, shortcutMac, shortcutOther;
  - `palette.*`: pages, actions, modeCustomer, modePartner, modeAdmin, modeAccount, toggleTheme, signOut, switchToPartner, switchToCustomer, placeholderPages, placeholderAll;
  - `user.*`: openMenu, theme, themeLight, themeDark, themeSystem, language.
- Labels deduplicated per P7: admin "Subscriptions" against customer "Subscription", and "Console machines".
- `offerUi.json` holds the seven P8 keys. English, written from the JSX they label:
  - `offerNameLabel` "Offer name"
  - `quoteValidityLabel` "Quote valid for (days)"
  - `partnerTierServerForcedNote` "The partner tier is set by Rediacc and cannot be changed here."
  - `registeredDealDesc` "Link a registered deal to apply its deal-registration discount."
  - `registeredDealPickLabel` "Registered deal"
  - `registeredDealNoneOption` "No linked deal"
  - `registeredDealNoneAvailable` "No approved deal registrations to link yet."
- All 12 non-English locales are naturalized per docs/i18n/CONVENTIONS.md section 2 (haiku). Placeholders stay verbatim, no value is byte-identical to English unless a convention allows it, and no case suffix is glued onto a placeholder.
- Keys that become dead are removed from all 13 `common.json` files in N1: `adminMenuHideLabel`, `adminMenuShowLabel`, `adminSectionLabel`, `logoutButton`, `toggleThemeButton`, and any `*MenuItem` left with no reference.
- `partner.json` is not edited. `partner:nav.*` stays for its other readers; PLAN-partner-sales-track D3 owns that file.

## Design 7: P8 and the raw-key sweep
- `makeUi(catalog, t)` resolves `catalog.uiText[key]` when it is a string, else `t('offerUi:<key>')` when that key exists. Otherwise it returns a humanized fallback and logs `console.error` once per key in development. It never returns the bare key.
- The catalog text keeps priority, so a catalog that later carries the label wins. The 227 English catalog strings are not localized here (O7).
- Regression guards:
  - `pages/partner/offer/__tests__/ui-keys.test.ts`: every `ui('<literal>')` under pages/partner/offer resolves in `CATALOG.uiText` or in en/offerUi.json.
  - `scripts/gates/check-account-i18n-key-usage.ts` learns `ui('<literal>')` with the same resolution, plus a CONTROL (a literal in neither fires) and a SILENT (a literal in offerUi passes) self-test.
- Sweep, already done for this plan (Context 9, 10): the `t()` gate is green; `ui()` has these seven missing and no others; nine hardcoded English sidebar labels (Context 5) are fixed by Design 2. X2 repeats the sweep at runtime (a raw-key DOM scan on every nav page in en and de).
- The gate that catches the class (G1, operator ruling on P8), control-first, three layers:
  - (a) `ui('<literal>')` resolution stays in `scripts/gates/check-account-i18n-key-usage.ts` (T1 owns that file). G1's control script plants an unresolved `ui()` literal in a scratch copy and requires that gate to fire, so the layer cannot go silent.
  - (b) Dynamic keys from config: the new `scripts/gates/check-account-raw-keys.ts` finds every object literal under private/account/web/src whose `labelKey`, `titleKey`, `descKey` or `placeholderKey` property is a string literal (the `NAV` arrays, `FAMILY_PAGES` and their siblings) and resolves each `ns:key` against the en locale files, plus the same in all 13 locales for keys in `nav` and `offerUi`. These are exactly the keys the key-usage gate counts as dynamic and cannot see.
  - (c) Rendered pages: `private/account/web/src/test/raw-key-scan.ts` exports one scanner (text nodes and `aria-label`, `title` and `placeholder` attributes matching `^[a-z]+[A-Z][A-Za-z0-9]+$` or `^[a-zA-Z]+:[a-zA-Z0-9_.]+$`). `src/test/__tests__/raw-key-render.test.tsx` renders the sidebar in all three modes, expanded and collapsed, the user menu, the workspace switcher, the palette and the offer SetupSection with a catalog that lacks `uiText`, in en and de, and requires zero hits. It runs inside `check:ci-test-account-web`, which already runs the whole portal vitest tree in CI. B2 and E1's 07-02 reuse the same pattern list.
- The allowlist is `.ci/config/account-raw-key-allowlist.json`: each entry names the exact string, the surface and a `BLOCKER:` reason (docs/agent-reference/suppressions.md), and an entry without one, or one that no longer matches anything, fails the gate.
- Control-first: a planted raw key (an unknown `labelKey` in a scratch config array; a rendered `offerNameLabel`) fails each layer, and the clean tree passes. The controls run before the real scan, so a scanner that matches nothing cannot report green.

## Design 8: test-ID migration (old -> new)
| Old ID | Today | New | Consumers changed |
|---|---|---|---|
| `sidebar-logout` | footer email button, signs out (private/account/web/src/components/AppSidebar.tsx:551) | kept: S1 interim icon button, then the user-menu "Sign out" item; both open `sidebar-logout-confirm` / `sidebar-logout-cancel` | private/account/e2e/src/pages/shared/NavigationComponent.ts:58, :116-118; 16-03:121; footer first-button selectors 01-02:34, 01-03:23, 01-05:23 |
| `theme-toggle` | footer icon button (private/account/web/src/components/ThemeToggle.tsx:60) | kept on the user-menu ToggleGroup; items `theme-option-*` | none (unit only) |
| `language-switcher-trigger` | footer icon button (private/account/web/src/components/LanguageSwitcher.tsx:55) | kept on the user-menu Language sub-trigger | 19-01:42 (opens `user-menu-trigger` first) |
| `language-option-<lang>` | dropdown item | kept | 19-01:46 |
| `org-switcher` | footer org dropdown when there are more than one org (:487) | retired: `workspace-switcher` + `org-option-<orgId>` | 16-03:45 |
| `org-option-tier-badge` | badge in org list | kept | none |
| `partner-mode-banner` | footer button opening the chooser (:446) | retired: `workspace-switcher` (partner mode) + `switch-program` | 26-01:79 |
| `partner-mode-tier-badge` | badge in the banner (:454) | kept, in the switcher subtitle | none |
| `enter-partner-program` | footer button (:430) | kept, a switcher menu item | 26-01:105, :132 (open `workspace-switcher` first) |
| `admin-menu-toggle` | footer toggle (:468) | retired: `enter-admin`, `admin-banner`, `admin-exit` | 07-01:72, :84; 08-02:36; 25-06 rewritten as 25-06-admin-mode; private/account/e2e/src/base/AuthenticatedTest.ts:68 seed removed |
| (new) | | `workspace-switcher`, `enter-customer-mode`, `switch-program`, `enter-admin`, `team-option-<id>`, `admin-banner`, `admin-exit`, `sidebar-search`, `user-menu-trigger`, `nav-support`, `nav-<itemId>`, `nav-group-<groupId>`, `palette-page-item`, `palette-action-item` | |
| kept unchanged | | `notice-bell`, `notice-badge`, `notice-dropdown`, `notice-view-all`, `palette-input`, `palette-list` | |

Selectors that are not test IDs: `settingsLink` and `clickLink('Settings')` open the user menu; `adminLink` (the "Admin" group label) becomes `admin-banner`; 13-02:10-12 finds Invoices in admin mode through `nav-a-invoices`.

## Design 9: rail, mobile, keyboard
- `collapsible="icon"` stays (private/account/web/src/components/AppSidebar.tsx:364). No `SidebarRail` is added, because the primitive has none.
- Every menu button carries `tooltip`.
- The mobile Sheet renders the same tree.
- Menus use radix keyboard handling (arrows, Enter, Esc), with visible focus rings from the existing `focus-visible` styles.
- Group labels are buttons when collapsible, with `aria-expanded`.

## Design 10: bench test partner and the automated walk-through (O6 ruling)
- **Bench test partner (B1).** `.ci/config/root-grants.json` gains a `bench_test_partner` section: a second partner org named "Bench sidebar test partner", tier `silver`, root as `admin`, status `active`.
  - Its id is deterministic, uuidv5(`ROOT_GRANTS_NS`, "root-grants/bench-test-partner/" + userId), so the apply is idempotent and the read finds it by id.
  - The loader in .ci/rediacc_ci/ops/root_grants.py applies the section to `kind: bench` targets only and refuses rc 2 if a config would apply it to an edge target. The account service refuses it with 403 unless the server's environment is bench or development, so a production Worker never creates it, whatever the caller sends.
  - Root then holds a personal org (customer mode), the "Rediacc" partner org and the test partner org (partner mode, and two partner orgs make `switch-program` and the program chooser reachable), and root itself (admin mode). One bench sign-in covers all three modes.
  - The same NEVER list holds: no user created, no SQL write from the tool, the bookmark before any POST.
- **Automated walk-through (B2).** A committed Playwright spec, private/account/e2e/tests/07-navigation/07-90-live-sidebar.test.ts, matched by private/account/e2e/playwright.live.config.ts, against `LIVE_SIDEBAR_ORIGIN` (bench only; the spec refuses any origin that is not a bench host).
  - It signs in through the existing live login (private/account/e2e/src/utils/live-console-login.ts; bench takes the password and TOTP path, no Turnstile), with the credentials from `bws_env exec --profile bench-login-<region>`, never typed into the spec.
  - Steps, each a named `test.step`: customer, partner (the test partner org) and admin modes each show only their links; the workspace switcher's org and program entries; sign-out cancel stays and confirm lands on /account/login; Ctrl+K page search lists pages and finds Stripe only in root's admin entries; the bell count equals `GET /notices/unread-count`; the raw-key DOM scan on every nav page and on /account/partner/offers/<id>/setup, in en and de, finds nothing; screenshots in light and dark, expanded, icon rail and a 390 px mobile viewport, for all three modes.
  - Screenshots mask the user row and every email (Playwright `mask`) and land in the owner-only results directory the live config already creates. The run prints one line per step and a JSON summary (steps, scan hits per page and locale, screenshot paths) on stdout.
  - `private/account/e2e/src/utils/live-sidebar-walk.ts` holds the scan and the mode assertions, so 07-02 (local) and 07-90 (bench) assert the same things.

## Tasks
- [x] S1 [writer] P2, shipped first and alone. In the current footer the email becomes a plain, non-interactive label. `sidebar-logout` becomes a LogOut icon button that opens the new `SignOutConfirmDialog` (new `ui/alert-dialog.tsx`), and only confirm calls `logout`. The five `common` sign-out keys are added in 13 locales, naturalized, and the hash manifest is regenerated. e2e: `NavigationComponent.logout()` clicks `sidebar-logout` and then `sidebar-logout-confirm`; 01-02, 01-03, 01-05 and 16-03 use it; new `01-06-logout-confirm.test.ts` (@auth) covers cancel and confirm.
  Owns: private/account/web/src/components/AppSidebar.tsx, private/account/web/src/components/ui/alert-dialog.tsx, private/account/web/src/components/SignOutConfirmDialog.tsx, private/account/web/src/components/__tests__/sign-out-confirm.test.tsx, private/account/web/src/i18n/locales/*/common.json, private/account/web/src/i18n/locales/.translation-hashes.json, private/account/e2e/src/pages/shared/NavigationComponent.ts, private/account/e2e/tests/01-auth/01-02-login.test.ts, private/account/e2e/tests/01-auth/01-03-logout.test.ts, private/account/e2e/tests/01-auth/01-05-session.test.ts, private/account/e2e/tests/01-auth/01-06-logout-confirm.test.ts, private/account/e2e/tests/16-team/16-03-two-org-selection.test.ts
  Depends on: none
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/components/__tests__/sign-out-confirm.test.tsx && cd .. && npm run typecheck:web && npm run lint && cd ../.. && npm run check:ci-i18n-completeness && npm run check:ci-i18n-placeholders && npm run check:ci-i18n-naturalization && npm run check:ci-i18n-hashes && npm run check:ci-i18n-account-key-usage && ./run.sh account test e2e --grep @auth` rc 0. Covered:
    - clicking the email text calls `logout` 0 times (control: today 1);
    - `sidebar-logout` opens the dialog with `logout` not called;
    - Cancel and Esc close it without calling;
    - confirm calls it once;
    - e2e: cancel stays on /account/dashboard; confirm lands on /account/login and /account/dashboard then redirects to login.
    (ticked) 2026-11-19T12:58:44Z by d778be9d: commit:c1f61ee2d (private/account 1dd0834 S1 + b474fb0 e2e follow-up); vitest sign-out-confirm 5 passed, typecheck:web, lint, i18n completeness/placeholders/naturalization/hashes/key-usage rc 0; ./run.sh account test e2e --grep @auth 20 passed rc 0 with the gateway on TERMS_GATE=false
- [x] F1 [writer] Foundations, no UI change: `lib/nav-config.ts` (Design 1-2: `NAV`, `navMode`, `visibleNav`, `activeItemId`, `paletteEntries`, `MODE_HOME`), `hooks/use-theme.ts` (light/dark/system, `data-theme`, the `theme` key, the same logic as private/account/web/src/components/ThemeToggle.tsx:19-45), and `hooks/use-persistent-state.ts`, with unit tests.
  Owns: private/account/web/src/lib/nav-config.ts, private/account/web/src/lib/__tests__/nav-config.test.ts, private/account/web/src/hooks/use-theme.ts, private/account/web/src/hooks/use-persistent-state.ts, private/account/web/src/hooks/__tests__/use-theme.test.ts, private/account/web/src/hooks/__tests__/use-persistent-state.test.ts
  Depends on: none
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/lib/__tests__/nav-config.test.ts src/hooks/__tests__/use-theme.test.ts src/hooks/__tests__/use-persistent-state.test.ts && cd .. && npm run typecheck:web && npm run lint` rc 0. Covered:
    - mode: root on /account/admin/stripe gives admin; non-root there gives the org mode; `isPartner` on /account/settings gives partner (control: the handoff's `modeFromPath` gives customer);
    - active item: /account/partner/offers/x/setup gives only Offers; /account/partner gives only Dashboard; /account/partner/exam/sales gives Study; /account/ gives Getting started; /account/dashboard does not light Getting started; /account/console/machines/m1 gives Console machines and not Machines;
    - gating: no subscription hides Delegation certs; no console access drops the Console group; a non-admin loses Permissions; a non-partner-admin loses Team and the empty group; on-prem adds On-premise cert;
    - item ids are unique per mode, and every `FAMILY_PAGES` slug yields an item;
    - a customer non-root `paletteEntries` holds no `/account/admin` path;
    - `useTheme('system')` follows `matchMedia`;
    - `usePersistentState` survives malformed JSON.
    (ticked) 2026-11-19T12:58:45Z by d778be9d: commit:c1f61ee2d (private/account a6a8eef F1); vitest nav-config/use-theme/use-persistent-state 34 passed, typecheck:web rc 0, lint rc 0; ThemeToggle re-import left to N1, which deletes ThemeToggle.tsx
- [x] I1 [writer] i18n: `nav.json` and `offerUi.json` in 13 locales (Design 6), the English source first, then naturalized; both namespaces registered in i18n/config.ts; hashes regenerated. New `i18n/__tests__/nav-keys.test.ts` resolves every `NAV` labelKey (all modes, every item), every Design 6 `nav` key and the seven `offerUi` keys in all 13 locales.
  Owns: private/account/web/src/i18n/config.ts, private/account/web/src/i18n/locales/*/nav.json, private/account/web/src/i18n/locales/*/offerUi.json, private/account/web/src/i18n/locales/.translation-hashes.json, private/account/web/src/i18n/__tests__/nav-keys.test.ts
  Depends on: F1 (the test imports `NAV`), S1 (the hash manifest is written serially)
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/i18n/__tests__/nav-keys.test.ts && cd ../../.. && npm run check:ci-i18n-completeness && npm run check:ci-i18n-placeholders && npm run check:ci-i18n-cross-locale && npm run check:ci-i18n-naturalization && npm run check:ci-i18n-hashes && npm run check:ci-i18n-account-key-usage` rc 0. Covered:
    - a labelKey missing from one locale fails the test, naming the locale and key (control: delete one key in a scratch copy);
    - `{{count}}` and `{{tier}}` placeholders survive in all 13;
    - no non-English value equals the English one outside the conventions' allowlist.
    (ticked) 2026-11-19T13:20:49Z by d778be9d: commit:69d8866c8 (private/account e7290ad); nav-keys vitest 5 passed; i18n completeness, placeholders, cross-locale, naturalization, hashes, account-key-usage rc 0
- [x] T1 [writer] P8: `makeUi(catalog, t)` (Design 7) and its call site in OfferBuilder.tsx; `ui-keys.test.ts`; the key-usage gate learns `ui('<literal>')` with a CONTROL and a SILENT self-test.
  Owns: private/account/web/src/pages/partner/offer/types.ts, private/account/web/src/pages/partner/offer/OfferBuilder.tsx, private/account/web/src/pages/partner/offer/__tests__/ui-keys.test.ts, scripts/gates/check-account-i18n-key-usage.ts
  Depends on: I1 (offerUi.json)
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/pages/partner/offer/__tests__/ui-keys.test.ts && cd .. && npm run typecheck:web && cd ../.. && npx tsx scripts/gates/check-account-i18n-key-usage.ts --selftest && npm run check:ci-i18n-account-key-usage` rc 0. Covered:
    - `makeUi(catalogWithoutKey, t)('offerNameLabel')` gives "Offer name" in en and the German value in de (control: today it gives `offerNameLabel`);
    - a catalog that carries the key wins;
    - an unknown key never returns itself;
    - every `ui()` literal under pages/partner/offer resolves;
    - the gate fires on a planted unresolved `ui('zzzLabel')`.
    (ticked) 2026-11-19T13:35:57Z by d778be9d: commit:d65b720db (private/account 4646c1e) + console 1cbbb7465; on the landed tree with I1: ui-keys vitest passed, web tsc rc 0, lint rc 0, key-usage --selftest rc 0, check:ci-i18n-account-key-usage rc 0
- [ ] G1 [writer] The raw-key gate (Design 7, operator ruling on P8): `check-account-raw-keys.ts` for dynamic config keys (layer b) with its allowlist lint, the shared scanner `raw-key-scan.ts` and the render sweep `raw-key-render.test.tsx` (layer c), and a control script that plants a raw key in each of the three layers, layer (a) included, and requires each to fire. Wired the three-point way: a `check:ci-account-raw-keys` script in package.json, an entry in scripts/ci-runner/manifest.ts regenerated into scripts/ci-runner/gates.lock.json with `npm run gen:gates-lock`, and a step in the `quality-i18n` job of .github/workflows/ci-quality.yml; the gate is named in docs/agent-reference/ci-gates.md with its quick fix.
  Owns: scripts/gates/check-account-raw-keys.ts, scripts/__tests__/check-account-raw-keys.control.ts, .ci/config/account-raw-key-allowlist.json, private/account/web/src/test/raw-key-scan.ts, private/account/web/src/test/__tests__/raw-key-render.test.tsx, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .github/workflows/ci-quality.yml, docs/agent-reference/ci-gates.md
  Depends on: T1 (the `ui()` layer and offerUi), I1 (nav and offerUi keys)
  Needs: none
  Accept: `npx tsx scripts/__tests__/check-account-raw-keys.control.ts && npx tsx scripts/gates/check-account-raw-keys.ts && cd private/account/web && npx vitest run src/test/__tests__/raw-key-render.test.tsx && cd ../../.. && npm run check:ci-gates-lock && npm run check:ci-parity` rc 0. Covered:
    - control: an unknown `labelKey` in a scratch config array fails layer (b), naming file, line and key; a scratch `ui('zzzLabel')` fails layer (a); a component rendering `offerNameLabel` fails layer (c);
    - an allowlist entry without a `BLOCKER:` reason fails, and one that matches nothing fails as stale;
    - the clean tree passes all three layers;
    - the render sweep fails on today's offer SetupSection (control: before T1 it shows the seven raw keys) and passes after T1.
- [x] W1 [writer] `WorkspaceSwitcher` and `AdminBanner` (Design 3), with unit tests. Not yet mounted (N1 mounts them).
  Owns: private/account/web/src/components/sidebar/WorkspaceSwitcher.tsx, private/account/web/src/components/sidebar/AdminBanner.tsx, private/account/web/src/components/sidebar/__tests__/workspace-switcher.test.tsx, private/account/web/src/components/sidebar/__tests__/admin-banner.test.tsx
  Depends on: F1, I1
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/components/sidebar/__tests__/workspace-switcher.test.tsx src/components/sidebar/__tests__/admin-banner.test.tsx && cd .. && npm run typecheck:web && npm run lint` rc 0. Covered (mocked `useAuth`):
    - a customer with no partner org and no root sees no `enter-partner-program`, `switch-program` or `enter-admin`;
    - `hasPartnerOrg` shows `enter-partner-program`, whose select calls `enterPartnerMode()`;
    - root sees `enter-admin`, which navigates to /account/admin;
    - selecting a partner org calls `enterPartnerMode(id)`, a plain org from partner mode calls `enterCustomerMode(id)`, and plain to plain calls `switchOrg(id)` (the private/account/web/src/components/AppSidebar.tsx:345-361 matrix);
    - partner mode renders `partner-mode-tier-badge`;
    - two teams render `team-option-*`, which calls `switchTeam`;
    - Exit goes to /account/partner when `isPartner`, else /account/dashboard.
    (ticked) 2026-11-19T13:40:26Z by d778be9d: commit:7669bc452 (private/account 843d453); sidebar vitest 20 passed, web tsc rc 0, lint rc 0
- [x] K1 [writer] One palette (Design 5): `palette-context.tsx`; `CommandPalette` gains Pages and Actions groups and an `allowed` prop; `Layout.tsx` mounts `PaletteProvider` and the palette for everyone, with no tree branch; `SidebarSearch.tsx`; tests.
  Owns: private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/palette-context.tsx, private/account/web/src/components/console/__tests__/command-palette.test.ts, private/account/web/src/components/console/__tests__/command-palette-mount.test.tsx, private/account/web/src/components/console/__tests__/command-palette-pages.test.tsx, private/account/web/src/components/Layout.tsx, private/account/web/src/components/sidebar/SidebarSearch.tsx
  Depends on: F1, I1, S1 (reuses `SignOutConfirmDialog`)
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/components/console/__tests__/ && cd .. && npm run typecheck:web && npm run lint` rc 0. Covered:
    - Ctrl+K opens one dialog when console access is on, and when it is off (control: today nothing opens without console access);
    - with access off, no command or resource group renders and Pages lists the customer items;
    - a non-root user's Pages hold no admin page, and root's do;
    - "Sign out…" opens `sidebar-logout-confirm` and does not call `logout`;
    - `sidebar-search` opens the same dialog;
    - the existing palette tests still pass.
    (ticked) 2026-11-19T14:11:16Z by d778be9d: commit:012b26114 (SidebarSearch 1891fb4) + d65b720db (palette 643e096); console palette tests 536 passed, sidebar-search vitest passed, web tsc rc 0
- [x] U1 [writer] `NavUser` and the Help and support link (Design 4); new `ui/avatar.tsx` and `ui/toggle-group.tsx`; `LANGUAGE_LABELS` moved to `i18n/language-labels.ts` (LanguageSwitcher.tsx re-imports it until N1 deletes the file).
  Owns: private/account/web/src/components/sidebar/NavUser.tsx, private/account/web/src/components/sidebar/HelpLink.tsx, private/account/web/src/components/ui/avatar.tsx, private/account/web/src/components/ui/toggle-group.tsx, private/account/web/src/i18n/language-labels.ts, private/account/web/src/components/LanguageSwitcher.tsx, private/account/web/src/components/sidebar/__tests__/nav-user.test.tsx
  Depends on: F1, I1, S1
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/components/sidebar/__tests__/nav-user.test.tsx && cd .. && npm run typecheck:web && npm run lint` rc 0. Covered:
    - clicking the email or name text opens the menu and calls `logout` 0 times;
    - `sidebar-logout` opens the confirm, cancel calls nothing, and confirm calls once;
    - `theme-option-system` sets `localStorage.theme=system` and `data-theme` from `matchMedia`;
    - `language-option-de` writes the language cookie and switches to de;
    - Settings goes to /account/settings and Communication preferences to /account/notifications;
    - an empty `name` shows the email and initials from the email.
    (ticked) 2026-11-19T13:35:59Z by d778be9d: commit:d65b720db (private/account b4e6bab); nav-user vitest 6 passed, web tsc rc 0, lint rc 0
- [x] N1 [writer] The shell: AppSidebar.tsx rewritten to compose header (switcher or banner, the search and bell row), `NavGroups` (collapsible, persisted, `nav-<id>` and `nav-group-<id>`), and footer (Help, NavUser). `adminMenuVisible` removed; ThemeToggle.tsx and LanguageSwitcher.tsx deleted; NoticeBell gets its square trigger style; dead `common` keys removed in 13 locales and hashes regenerated.
  Owns: private/account/web/src/components/AppSidebar.tsx, private/account/web/src/components/sidebar/NavGroups.tsx, private/account/web/src/components/NoticeBell.tsx, private/account/web/src/components/__tests__/notice-bell.test.tsx, private/account/web/src/components/ThemeToggle.tsx, private/account/web/src/components/LanguageSwitcher.tsx, private/account/web/src/components/__tests__/app-sidebar.test.tsx, private/account/web/src/i18n/locales/*/common.json, private/account/web/src/i18n/locales/.translation-hashes.json
  Depends on: W1, K1, U1, T1 (the hash manifest)
  Needs: none
  Accept: `cd private/account/web && npx vitest run src/components/__tests__/app-sidebar.test.tsx src/components/__tests__/notice-bell.test.tsx src/components/__tests__/sign-out-confirm.test.tsx && npx vitest run && cd .. && npm run typecheck:web && npm run lint && cd ../.. && npm run check:ci-i18n-completeness && npm run check:ci-i18n-hashes && npm run check:ci-i18n-account-key-usage` rc 0. Covered:
    - a customer on /account/dashboard sees no partner or admin item (control: today root sees the Admin group beside customer items when the preference is set);
    - root on /account/admin/stripe sees only admin items plus `admin-banner`;
    - a partner on /account/settings sees partner items;
    - exactly one `[data-active=true]` on /account/partner/offers/x/setup;
    - the Platform group starts closed, its open state survives a remount through `sidebar:groups:<userId>`, and it is forced open on /account/admin/version-policy;
    - no element whose text is the email has a click handler reaching `logout`;
    - the collapsed state renders tooltips and the avatar-only user row;
    - no `adminMenuVisible` read remains (grep in test).
    (ticked) 2026-11-19T14:11:15Z by d778be9d: commit:012b26114 (private/account 1891fb4 + 30e9898); web vitest 1124 passed, web tsc rc 0, lint rc 0, i18n completeness/hashes/key-usage rc 0
- [ ] E1 [writer] e2e migration per Design 8, plus new suites.
  - `AuthenticatedTest.ts` drops the `adminMenuVisible` seed. `NavigationComponent` gains `openUserMenu()`, `openWorkspaceSwitcher()`, `enterAdmin()` and `exitAdmin()`; `settingsLink` and `adminLink` are re-pointed.
  - 07-01, 08-01, 08-02, 13-02, 16-03, 19-01 and 26-01 are updated. 25-06 is replaced by `25-06-admin-mode.test.ts`.
  - New `07-02-sidebar-modes.test.ts` (@navigation): customer, partner (seeded partner), admin and Exit, the active item on a nested offer route, Ctrl+K page search filtered by permission, and the collapsed rail.
  Owns: private/account/e2e/src/pages/shared/NavigationComponent.ts, private/account/e2e/src/base/AuthenticatedTest.ts, private/account/e2e/tests/07-navigation/07-01-sidebar.test.ts, private/account/e2e/tests/07-navigation/07-02-sidebar-modes.test.ts, private/account/e2e/tests/08-journeys/08-01-customer-journey.test.ts, private/account/e2e/tests/08-journeys/08-02-admin-journey.test.ts, private/account/e2e/tests/13-invoices/13-02-admin-invoices.test.ts, private/account/e2e/tests/16-team/16-03-two-org-selection.test.ts, private/account/e2e/tests/19-i18n/19-01-language-sync.test.ts, private/account/e2e/tests/25-partner-admin/25-06-admin-menu-toggle.test.ts, private/account/e2e/tests/25-partner-admin/25-06-admin-mode.test.ts, private/account/e2e/tests/26-partner-program-chooser/26-01-chooser.test.ts
  Depends on: N1, S1
  Needs: none
  Accept: with `./run.sh account dev` up, `./run.sh account test e2e` (the full suite) rc 0, and `grep -rn "admin-menu-toggle\|partner-mode-banner\|org-switcher\|adminMenuVisible" private/account/e2e private/account/web/src` prints nothing. Covered:
    - the customer fixture's switcher has no `enter-admin`;
    - root enters admin through `enter-admin`, sees `admin-banner`, and Exit lands on /account/dashboard;
    - the partner fixture's switcher shows `partner-mode-tier-badge`;
    - `enter-partner-program` then `program-chooser` works as in 26-01;
    - Ctrl+K "stripe" finds nothing for a customer and Stripe for root;
    - sign-out cancel and confirm (01-06 from S1 still green).
- [ ] B1 [writer] Bench test partner through root grants (Design 10): the `bench_test_partner` section in root-grants.json, its loader, plan and read in root_grants.py (bench targets only, rc 2 on an edge target), and the account service, DTO and types accepting it only when the environment is bench or development.
  Owns: .ci/config/root-grants.json, .ci/rediacc_ci/ops/root_grants.py, .ci/rediacc_ci/tests/test_ops_root_grants.py, private/account/src/types/root-grants.ts, private/account/src/services/root-grants.service.ts, private/account/src/dto/root-grants.dto.ts, private/account/tests/integration/root-grants.test.ts, private/account/tests/integration/root-grants-parity.test.ts
  Depends on: none
  Needs: none
  Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_root_grants.py -q && cd private/account && npx vitest run tests/integration/root-grants.test.ts tests/integration/root-grants-parity.test.ts && npm run typecheck` rc 0. Covered:
    - an absent test partner plans one create action on a bench target and none on an edge target;
    - a config that puts the section on an edge target exits 2 naming the key (control: the bench target passes);
    - the service answers 403 for the section under environment `production` and creates it under `bench` (control);
    - a second apply plans zero actions (idempotent), and the parity fixtures agree between Python `plan()` and the service.
- [ ] B2 [writer] The automated bench walk-through (Design 10): `07-90-live-sidebar.test.ts`, `live-sidebar-walk.ts`, and the live config matching it.
  Owns: private/account/e2e/tests/07-navigation/07-90-live-sidebar.test.ts, private/account/e2e/src/utils/live-sidebar-walk.ts, private/account/e2e/playwright.live.config.ts
  Depends on: N1, G1 (the scan pattern), B1 (the test partner org)
  Needs: none
  Accept: `cd private/account/e2e && npx tsc --noEmit -p tsconfig.json && LIVE_SIDEBAR_ORIGIN=https://www.rediacc.com npx playwright test --config playwright.live.config.ts tests/07-navigation/07-90-live-sidebar.test.ts` exits non-zero with the "bench origins only" refusal before any browser starts, and `npx playwright test --config playwright.live.config.ts --list` lists 07-90 beside 27-90 and 27-91. Covered:
    - a non-bench origin is refused (control: a bench origin is admitted);
    - the scan helper flags a planted `nav:item.zzz` text node in a fixture page and passes a clean one;
    - the run's stdout carries one line per step and the JSON summary.
- [ ] X1 [lead] Local proof chain: a VERIFIED `npm run vm:check -- --changed` on the head tree, then `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench`.
  Local-route: vm-check, deploy-bench -- the branch tree is proved on the fleet and deployed to bench from this checkout
  Owns: none (runs only). Accept: vm:check VERIFIED and deploy_bench rc 0 naming the deployed version.
- [ ] X2 [live] Run the automated bench walk-through on the deployed tree: B1's apply on bench eu (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --target bench-eu --apply`, then the dry run shows no drift), then `npm run login:bench -- --region eu` and the B2 spec through `bws_env exec --profile bench-login-eu`. No manual walk.
  Owns: none. Accept: the root-grants dry run on bench-eu rc 0 with zero actions, and the B2 run rc 0 with its JSON summary recorded in the tick: every step passed, scan hits 0 per page and locale (en and de), and the screenshot paths for light and dark, expanded, icon rail and 390 px mobile in all three modes.
  Needs: bench-deploy
- [ ] LP-bench [live] A fresh bench receipt after X2, recorded and ticked through `worklist.py --live-proof`.
  Accept: live-proof bench account-smoke

## Concurrency
- **Wave 0:** S1 (P2, ships first) and F1. Disjoint files.
- **Wave 1:** I1, after both: it imports F1's `NAV` and follows S1 on the hash manifest.
- **Wave 2:** T1, W1, K1 and U1 (4 writers, disjoint files). K1 alone touches Layout.tsx and CommandPalette.tsx, U1 alone LanguageSwitcher.tsx, T1 alone the offer builder and the gate.
- **Wave 3:** N1 (AppSidebar.tsx after S1; common.json and hashes after S1, I1 and T1) and G1 (after T1 and I1; it owns only the new gate files and the wiring files).
- **Wave 4:** E1 (NavigationComponent.ts after S1), B1 (root-grants files, disjoint from every portal box, so it may also start in wave 0 when a slot is free) and B2 (after N1, G1 and B1).
- **Then, in the main checkout:** X1 (holds the fleet lock), X2 (the B1 apply and the B2 run), LP-bench.
- The hash manifest is the one file many boxes write. They write it in turn (S1, then I1, then N1). Any other plan's locale edit landing meanwhile is merged by re-running `npm run i18n:generate-hashes`, never by hand-merging the JSON.

## Resolved questions (operator, 2026-11-19, ASKED:2026-11-19)
- O1 Partner mode source: resolved as the default. It stays derived from the active org (Context 6); only admin mode is route-derived.
- O2 `/account/machines` versus `/account/console/machines` (different data, Context 12): resolved "Keep both, rename one". The console one is labelled "Console machines" and the licence page stays "Machines" under Infrastructure.
- O3 Console as its own mode: resolved as the default. It is a collapsible group, open by default, absent without console access.
- O4 "Become a partner" for non-members: resolved as the default. It is omitted (no portal route; the form lives on www), and partner entries appear only with a partner org.
- O5 Bell: resolved as the default. The existing NoticeBell popover (mark-all, View all) stays as the square bell, not handoff 3.7's plain link.
- O6 Production and bench data: no production deploy box in this plan (the portal ships with the account Worker's normal edge path). The bench partner is resolved "Create one via root grants but improve testing": B1 creates it, B2 automates the walk-through, X2 runs it.
- O7 Offer builder localization: resolved as the default plus a gate. The seven missing labels are fixed through the portal `offerUi` namespace in 13 locales (T1), G1 catches the class in CI, and the 227 English catalog `uiText` strings stay English (catalog-driven by design, private/account/web/src/pages/partner/offer/types.ts:6-10); localizing them is a separate plan.
- Search: resolved "One palette, everyone" (Design 5 as written).

## Risks
- **Hard navigation on mode switch.** Entering or leaving partner mode reloads the page. The offer builder autosaves (pages/partner/offer/useOfferAutosave.ts), so no unsaved-changes guard is added here; it is a follow-up.
- **Palette for everyone.** private/account/web/src/components/Layout.tsx:20-42 warns against branching the provider tree on `allowed`. K1 keeps the tree fixed and passes `allowed` as a prop; command-palette-mount.test.tsx guards it.
- **Blind spots of the key gate.** `t(item.labelKey)` is invisible to it, so I1's test is the guard for every nav label.
- **e2e fixture change.** Removing the `adminMenuVisible` seed changes every `adminPage` test that navigated from the dashboard sidebar. E1 runs the full suite, not just the tagged ones.
- **partner.json** belongs to PLAN-partner-sales-track D3; this plan reads `partner:*` keys and never writes them.

## Follow-ups (not boxes; ranked by value over effort)
1. Breadcrumbs in the page header.
2. Per-item badges (pending partner applications for root, drill streak).
3. Recent pages in the palette (it already has recent commands).
4. `/account/eval-licenses` and `/account/terms` are routed (private/account/web/src/router.tsx:251, :256) but in no nav; decide whether the palette lists them.
5. Nav usage analytics.
6. An unsaved-changes guard on mode switch.
