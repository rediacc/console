# PLAN: app-wide org selection -- refuse ambiguity instead of the first membership

Status: approved
Owner: d778be9d
First-Seen: 2026-09-24
Depends-On: PLAN-config-passkey-optional.md -- builds on its uncommitted org-scoping work (configs.ts resolveConfigOrg, web/src/api/config.ts), which must land first
Worklist: #793f9237
Priority: P2 -- seed: Status approved, 3 open box(es)
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: private/account/src/services/*.ts, private/account/src/routes/*.ts, private/account/src/middleware/error-handler.ts, private/account/e2e/src/setup/global-setup.ts, private/account/src/middleware/partner.ts, private/account/src/middleware/org-role.ts, private/account/web/src/auth/ProtectedRoute.tsx, private/account/web/src/auth/AuthContext.tsx, private/account/src/utils/request.ts, private/account/web/src/pages/*.tsx, private/account/web/src/components/AppSidebar.tsx, private/account/web/src/api/*.ts, packages/cli/src/services/account/account-client.ts, packages/cli/src/services/account/subscription-device-auth.ts, private/account, private/account/tests/integration/*.ts, private/account/e2e/tests/20-config-storage/20-11-prf-provider-matrix.test.ts, private/account/e2e/src/base/AuthenticatedTest.ts, private/account/e2e/tests/16-team/16-01-team.test.ts

Finding from the org-scoping writer (2026-09-24): orgService.resolveUserOrg falls back to the FIRST membership app-wide. Fixed at the root per the fix-in-session rule; ships as ONE PR and ONE deploy (server-only would strand two-org users with organization:null and no switcher).

- [ ] T1 [A] Server + integration tests (section 6, Writer A).
- [ ] T2 [B] Web + e2e (section 6, Writer B).
- [ ] T3 Lead: the e2e run, then deploy eu together with T1+T2.

# Plan: when a request names no org, refuse instead of using the first membership

## 0. What I found

- **The bug:** `OrgService.resolveUserOrg` is at `private/account/src/services/org.service.ts:170-179`. When a request names an org, it checks the org exists and that the caller is a member. When no org is named it calls `ensureUserOrg` (`:102`), which calls `getOrgForUser` (`:92-100`). That function is the "first membership" read: `select().from(orgMemberships).where(userId).get()`, with no ordering.
- **Server grep result:** `getOrgForUser` is the only first-membership read on the server. The only caller of `getOrgForUser` is `ensureUserOrg`, and the only caller of `ensureUserOrg` is `resolveUserOrg`. So fixing `resolveUserOrg` fixes every route at once. No other code does `memberships[0]`, `orgs[0]` or `.get()` on memberships without an org in the filter. The `.get()` calls at `private/account/src/services/org.service.ts:184-188, 461-465, 535-539, 604-608` all filter on (orgId, userId), so they are fine.
- **The model to reuse:** `resolveConfigOrg` at `private/account/src/routes/configs.ts:177-205`.
- **Error body:** `AppError` details are spread into the body (`private/account/src/middleware/error-handler.ts:70-73`). So `{error, code:'org_selection_required'}` reaches the client as-is.
- **Uncommitted work in the tree:** the configs fix is not committed. `git status` shows `src/routes/configs.ts`, `src/routes/proxy.ts`, `src/routes/test.ts`, `web/src/api/config.ts`, the new `tests/integration/config-org-scope.test.ts` and many e2e files as modified or untracked. Both writers must build on this tree and must not reset it.
- **Multi-org users are common, not only invitees:**
  - Approving a partner application for an existing user adds a second org (`private/account/src/services/partner-application.service.ts:148-162`).
  - Adding a partner-managed customer for an existing user does the same (`private/account/src/services/partner-customer.service.ts:59-90`).
  - The e2e partner fixture is a two-org user (`private/account/e2e/src/setup/global-setup.ts:236-240`).

## 1. Every caller and what depends on it

All of these call `resolveUserOrg(userId, getOrgIdFromRequest(c))`, so today they all fall back to the first membership:

| file:line | Route / feature |
|---|---|
| `private/account/src/services/billing.service.ts:95` (`resolveSubscription`) | `src/routes/portal.ts`: `/portal/me` :77, `/subscription` :157, `/activity?scope=organization` :207, `/machines` :377, `/backup-storage` :398, `/checkout` :594, `/billing` :653, `/subscription/change` :710 |
| `private/account/src/routes/portal.ts:50` (`resolvePortalTeamScope`) | Portal routes that use team scope |
| `private/account/src/routes/organization.ts:36, 54, 91, 121, 145, 161, 175, 197, 286, 303` | `/portal/org` GET, `/members`, `POST /invitations`, `GET /invitations`, `DELETE /invitations/:id`, `PUT /members/:id/role`, `DELETE /members/:id`, `/transfer-ownership`, `GET /teams`, `POST /teams` |
| `private/account/src/routes/organization.ts:327, 339` | `/teams/archive`, `/teams/rename`. They use `header ?? team.orgId`, so the team decides the org. They stay resource-anchored. |
| `private/account/src/middleware/partner.ts:28` (`requirePartner`) | All `/partner/*`: `partner.ts`, `partner-deals.ts`, `partner-certification.ts`, `partner-learning.ts`, `partner-customers.ts`, `partner-offers.ts`. It catches every error and returns 403 `NO_ACTIVE_ORG` (`:29-31`), which would hide the new 409. |
| `private/account/src/middleware/org-role.ts:28` (`requireOrgRole`) | Admin actions in `private/account/src/routes/portal-delegation-certs.ts:45`. It also swallows errors into 403 `NO_ACTIVE_ORG` (`:29-38`). |
| `private/account/src/routes/portal-delegation-certs.ts:59` (`verifyOwnership`), `:266` | `/portal/delegation-certs/*`, `/auto-renew-token` |
| `private/account/src/routes/portal-eval.ts:30, 39` | `/portal/eval-licenses`, `/:id/download` |
| `private/account/src/routes/portal-invoices.ts:46` | `/portal/invoices` |
| `private/account/src/routes/api-tokens.ts:53, 126, 154` | `POST /api-tokens`, `GET /api-tokens`, `DELETE /api-tokens/:id` |
| `private/account/src/routes/device-codes.ts:54` and `private/account/src/services/device-code.service.ts:133` | `POST /device-codes/:userCode/approve`. This mints the CLI token, so it is the most important one. |
| `private/account/src/routes/proxy.ts:138` | `POST /proxy/session-token` |
| `private/account/src/routes/console.ts:57` (`resolveCaller`) | `/console/exec` :327, `/console/session` :387, `/console/session/:id/cek` :435 |
| `private/account/src/routes/test.ts:68, 813` | Test-only routes `/test/org-customer-id` and the config-store seeding. The code relies on auto-creating an org for users with none (comment at `:811`). |

**Related "first" picks that are not about orgs (out of scope):**
- `resolveUserTeam` defaults to `teamsForUser[0]` (`private/account/src/services/org.service.ts:442`), and `/portal/org/teams` uses `teams[0]` (`private/account/src/routes/organization.ts:291`). Both stay inside one org. The recommendation is a separate follow-up.
- On the client, `RequirePartner` switches to `partnerOrgs[0]` (`private/account/web/src/auth/ProtectedRoute.tsx:84`), and `enterPartnerMode` uses the first partner org (`private/account/web/src/auth/AuthContext.tsx:307`). That is a guess when the user has more than one partner org; see 3.2.

**Routes that already get the org another way, so no change is needed:**
- Bearer-token routes take the org from the token's subscription: `private/account/src/routes/license.ts:100, 221`, `private/account/src/routes/proxy.ts:58-61`, `private/account/src/routes/configs.ts:884-893` (password-enroll).
- Store-scoped config routes use `requireStoreAccess` (`private/account/src/routes/configs.ts:216-233`).
- `private/account/src/routes/configs.ts:305-315` uses `body.orgId`.

## 2. Server design

### 2.1 One shared resolver in `OrgService`, generalized from `resolveConfigOrg`

```ts
/** The org a session request acts on. Named → 404 org_not_found / 403 not_org_member.
 *  Unnamed → the caller's only org; several → 409 org_selection_required; none → null.
 *  Never "the first membership". */
async selectUserOrg(userId, orgId?): Promise<{ org: Organization; role: OrgRole } | null>

async resolveUserOrg(userId, orgId?): Promise<Organization> {
  const sel = await this.selectUserOrg(userId, orgId);
  return sel ? sel.org : this.provisionFirstOrg(userId); // zero memberships only
}
```

- **Delete `getOrgForUser`** (`private/account/src/services/org.service.ts:92-100`). `ensureUserOrg` becomes `provisionFirstOrg` and is only reached when the user has no memberships at all.
  - Why keep creating an org for zero-membership users: it is setting the user up, not guessing between orgs. Such users do exist: users made by `private/account/src/routes/test.ts:102` `/ensure-login`, and an owner who handed off ownership and was then removed (`private/account/src/services/org.service.ts:455-484`).
- **Keep the name and signature of `resolveUserOrg`.** Then about 30 call sites get the fix without edits.
  - Callers that also call `getMemberRole` straight after (`private/account/src/routes/portal.ts:51`, `private/account/src/services/billing.service.ts:96`, `private/account/src/routes/api-tokens.ts:65, 128, 155`) can move to `selectUserOrg` to save a query. This is optional.
- **Configs:** `resolveConfigOrg` (`private/account/src/routes/configs.ts:177-205`) becomes a one-line wrapper around `selectUserOrg`. Its zero-org case (`null`) stays as it is.
- **Middleware** (`private/account/src/middleware/partner.ts:27-32`, `private/account/src/middleware/org-role.ts:27-38`): let an `AppError` pass through (409, 403 `not_org_member`, 404). Keep 403 `NO_ACTIVE_ORG` only for anything else.
- **Malformed org ids:** `getOrgIdFromRequest` (`private/account/src/utils/request.ts:32-36`) silently drops a non-UUID `X-Org-Id`/`?orgId`. With the new rule, a single-org user would then quietly get their only org even though the request named something. The recommendation is to answer 400 `invalid_org_id` when a value is present but malformed, via a new `readRequestedOrgId(c)` that the resolver path uses.
- **`private/account/src/routes/test.ts:68, 813`:** accept an optional `orgId` in the body and pass it through. The seeded users have one org, so nothing else changes.

### 2.2 Routes that stay org-agnostic

These must return 200 for a two-org user with no header:
- `/portal/org/list` (`private/account/src/routes/organization.ts:241`), `/portal/org/switch` (`:219`, org in the body), `/portal/org/create` (`:61`), `/portal/org/accept-invitation` (`:203`), `/portal/org/teams/switch` (`:309`, team decides the org)
- User-scoped portal routes: `/portal/security/*`, `/communications`, `/newsletter/*`, `/set-password`, `/settings`, `/confirm-email`, and `/activity` in personal scope
- **`/portal/me`: soft handling, never a 409.** It catches `org_selection_required` and returns `{user, organization:null, subscription:null, teams:[], activeTeam:null, partner:null, environment, orgSelectionRequired:true}`.
  - This matters because a 409 on `/me` would log the user out: `private/account/web/src/auth/AuthContext.tsx:161-172` sets `user=null` on any non-401/403/404 error.
  - A named non-member org stays 403. The portal's recovery at `private/account/web/src/auth/AuthContext.tsx:142-153` depends on that.

### 2.3 Error contract

| Status | Body | When |
|---|---|---|
| 409 | `{error:'Member of more than one organization: name one with X-Org-Id', code:'org_selection_required'}` | No org named, user has several |
| 403 | `{code:'not_org_member'}` | Named org, caller is not a member |
| 404 | `{code:'org_not_found'}` | Named org does not exist |
| 400 | `{code:'invalid_org_id'}` | Malformed org id (if adopted) |

The org list is not included in the 409; the client already has `/portal/org/list`.

## 3. Portal design

### 3.1 How it works today

- `activeOrgId` is written in these places:
  - `private/account/web/src/auth/AuthContext.tsx:119`: every successful `/me` writes back whatever the server resolved. This is how the first-membership guess gets saved.
  - `:275` (`switchOrg`), `:311` (`enterPartnerMode`), `:339` (`enterCustomerMode`)
  - `private/account/web/src/pages/InviteAccept.tsx:42` and `private/account/web/src/pages/PartnerInviteAccept.tsx:48`
- It is removed at `:147` (the 403/404 retry) and `:383` (logout; `lastCustomerOrgId` is removed at `:384`).
- The sidebar org switcher is `private/account/web/src/components/AppSidebar.tsx:339-350, 472-500`. It only renders when `orgs.length > 1 && organization` (`:472`). If the server returns `organization: null`, the user would have no way to pick an org.
- `components/ProgramChooserModal.tsx` already lists every org, split into partner and customer sections (`:82-126`). It auto-shows only for partner-plus-customer users on the landing paths (`:12, 61-67`).

### 3.2 Picking an org on first load

1. `loadMe` sends the stored `activeOrgId` if there is one. With one org, the server resolves it and nothing changes.
2. If `/me` returns `orgSelectionRequired`:
   - Read the per-user key `lastOrgId:<user.id>`. It is written next to every `activeOrgId` write and is not cleared at logout. Keying it by user avoids leaking the choice to another user on the same browser.
   - If that org is in `orgs`, set `activeOrgId` and call `loadMe` once more.
   - Otherwise set the new state `orgSelectionRequired=true`.
3. Turn `ProgramChooserModal` into the org chooser:
   - Show it when `orgSelectionRequired`, on any path, even without a partner org.
   - Hide the dismiss button in this mode, because there is no fallback org to stay in.
   - A customer choice uses a soft `switchOrg` so the user stays on the current path. A partner choice uses the existing `enterPartnerMode`.
   - Choosing marks `programChoiceMade`.
4. `private/account/web/src/components/AppSidebar.tsx:472`: render the switcher whenever `orgs.length > 1`. With no organization, the trigger shows a "Choose organization" label.
5. `RequirePartner` (`private/account/web/src/auth/ProtectedRoute.tsx:84-98`): auto-switch only when `partnerOrgs.length === 1`; otherwise open the chooser.
6. `private/account/web/src/pages/Authorize.tsx:22-56` (the device-code approval that mints the CLI token): when `orgs.length > 1`, show an org select, prefilled with the active org, and send it as `X-Org-Id` on the approve call. The org the CLI token belongs to should be an explicit choice.

### 3.3 Every org-scoped call sends X-Org-Id

- In `web/src/api/client.ts`, merge the two prefix blocks (`:56-69` and `:72-86`) into one exported `ORG_SCOPED_PREFIXES = ['/portal','/partner','/api-tokens','/device-codes','/console','/proxy']` and export `activeOrgHeaders()`.
  - `/proxy` is new. No browser code calls `/proxy/session-token` today; only `tests/integration/proxy-session-token.test.ts` does.
- Reuse `activeOrgHeaders()` in the three copies that exist now: `private/account/web/src/api/config.ts:48-55`, `private/account/web/src/api/console.ts:68-77` (raw fetch for `/console/exec`), and `private/account/web/src/api/executor-session.ts:77-81`.
- Raw fetches that need no change:
  - `configPush` (`private/account/web/src/api/config.ts:373`) authenticates with the config token.
  - The `device-codes/:code/config-handoff` fetch (`private/account/web/src/pages/ConfigRemote.tsx:190`) has no auth by design (`private/account/src/routes/device-codes.ts:34`).

### 3.4 Handling a 409 everywhere

- Add a tiny notifier in `client.ts`: `notifyOrgSelectionRequired()` dispatches a window `CustomEvent('rediacc:org-selection-required')`.
- Call it wherever a 409 with that code can arrive: `apiFetch`, `apiDownload`, `configFetch`, the console exec fetch, and `executor-session`. The error is still thrown, so pages show their error state.
- `AuthContext` listens for the event, sets `orgSelectionRequired=true` and opens the chooser.
- Result: deep links that make org-scoped calls get the chooser. Resource-anchored pages (config member-accept with `storeId`, invite accept) never receive a 409, so the chooser does not block them.
- Add `orgSelectionRequired?: boolean` to `MeResponse` (`private/account/web/src/api/types.ts:258`).
- New chooser strings need all 14 locales and a re-baseline of `.translation-hashes.json`, following the pattern of commit `2d1da22`.

## 4. The CLI: no change needed

- `accountServerFetch` (`packages/cli/src/services/account/account-client.ts:189`) only calls bearer-token routes: `licenses/*`, `backups/*`, `telemetry/config`, `configs/password-enroll`, and the device-code init/poll.
- The server takes the org for all of these from the token's subscription (see section 1).
- The only session route in the CLI login flow is the browser approval (`private/account/web/src/pages/Authorize.tsx:48`), and the CLI stores the org it gets back (`packages/cli/src/services/account/subscription-device-auth.ts:70-78`).
- No external consumers: grepping the repo for these routes outside `private/account` finds nothing.

## 5. Tests

### Server integration (Writer A), written to fail first

New file `tests/integration/org-selection.test.ts`:
- **Two-org user:** register (own org A), then give them org B, either with `orgService.createOwnedOrg` (as `private/account/tests/integration/proxy-session-token.test.ts:196` does) or by accepting an invitation.
- **Table-driven, one row per route family.** Each row checks three things: no header gives 409 `org_selection_required`; `X-Org-Id: B` succeeds and acts on B; a single-org user with no header gives the same result as before.
  - Rows: `/portal/org` routes, `/portal/{subscription,machines,backup-storage,activity?scope=organization,invoices,eval-licenses,delegation-certs}`, `/api-tokens` POST/GET/DELETE, `/device-codes/:code/approve`, `/console/session`, `/proxy/session-token`, a `/partner/*` route (409, not 403 `NO_ACTIVE_ORG`), and a `requireOrgRole` route.
- **`/portal/me`:** 200 with `orgSelectionRequired:true` and `organization:null`. A named non-member org gives 403.
- **Org-agnostic routes:** `/portal/org/list`, `/switch` and `/portal/security/sessions` give 200 with no header.
- **Zero-membership user:** still gets an org created. Malformed `X-Org-Id` gives 400 (if adopted).

Existing tests that make users multi-org must name the org. They mostly do already (`private/account/tests/integration/portal.test.ts:407, 523, 824-855`; `organization.test.ts`, 22 `orgId=` uses). Run the full suite and add headers where it goes red. Likely spots (hypothesis):
- `client2` calls in `organization.test.ts` after an invitation is accepted (e.g. `:254-290, 1129-1217`)
- `private/account/tests/integration/partner-membership.test.ts:286, 395`
- `private/account/tests/integration/config-member-add.test.ts:162`, `private/account/tests/integration/config-remote.test.ts:153`, `private/account/tests/integration/config-password-enroll.test.ts:498`

`private/account/tests/integration/portal-delegation-certs.test.ts:297` deletes the user's own membership first, so that user has one org and is not affected.

### Portal unit tests (Writer B)

Following `web/src/api/__tests__/config-org-header.test.ts`:
- `api/__tests__/org-header.test.ts`: every prefix sends the header; `/auth` and `/admin` do not.
- A 409 with the code dispatches the event; the config, console and executor raw fetches do the same.
- An `AuthContext` test:
  - `orgSelectionRequired` with a valid `lastOrgId:<uid>` reloads with that org.
  - Without one, the chooser opens with no dismiss button.
  - Logout keeps `lastOrgId`.
- `ProgramChooserModal`: shows for multiple customer orgs with no partner org.

### One e2e (Writer B)

New `e2e/tests/16-team/16-03-two-org-selection.test.ts`:
1. Register user X. The global-setup customer invites X. Accept through the API.
2. In a fresh context, inject cookies with no `activeOrgId` and go to `/account/dashboard`. The chooser shows with no dismiss button. Pick org B.
3. The org name shows B, `activeOrgId` is B, and after a reload there is no chooser.
4. `/account/machines` and `/account/api-tokens` load without errors.
5. Clear `activeOrgId`, open `/account/machines` directly: the chooser appears. Log out and back in: the last-used org B is restored without the chooser.

### Existing e2e affected

- **`26-partner-program-chooser/26-01-chooser.test.ts`:**
  - The header comment `:7-11` describes the "two-org trap". It must be rewritten.
  - The test "dismissing the chooser keeps it closed across a reload" (`:87-101`) must become "a choice persists across reload", because dismiss is gone in this mode.
  - The other cases should still pass, since they use the same `program-chooser` testids (hypothesis).
- **`e2e/src/utils/config-store-helpers.ts`:**
  - `loginPageWithCookies` (`:654`) should take an optional `orgId` and pin `activeOrgId`.
  - `addOrgMember` (`:614-652`) creates two-org members. `private/account/e2e/tests/20-config-storage/20-11-prf-provider-matrix.test.ts:230` logs one in, but only on a page anchored to a `storeId`, so it should not see the chooser (hypothesis; verify).
- **Probably fine:**
  - `16-02-org-onboarding` (InviteAccept pins the org). Check any step that uses a fresh context.
  - The `partnerPage` fixture already pins the org (`private/account/e2e/src/base/AuthenticatedTest.ts:85-88`).
  - `partner-helpers.ts` already sends `X-Org-Id` (`:177, 257, 367, 440`).
  - Single-org fixtures (customer, admin, `ensure-login` dev seeding) are unchanged.
  - `private/account/e2e/tests/16-team/16-01-team.test.ts:140-167` (invalid saved org) still works for a single-org user.

## 6. Writers, order, risks

**Writer A: server and integration tests**
- `src/services/org.service.ts`
- `src/routes/configs.ts` (`resolveConfigOrg` becomes a wrapper)
- `src/middleware/partner.ts`, `src/middleware/org-role.ts`
- `src/routes/portal.ts` (soft `/me`)
- `src/utils/request.ts`
- `src/routes/test.ts`
- Optional role clean-ups: `src/services/billing.service.ts`, `src/routes/api-tokens.ts`
- `tests/integration/org-selection.test.ts` (new), plus fixes to existing integration tests

**Writer B: web and e2e**
- `web/src/api/client.ts`, `config.ts`, `console.ts`, `executor-session.ts`, `types.ts`
- `web/src/auth/AuthContext.tsx`, `ProtectedRoute.tsx`
- `web/src/components/ProgramChooserModal.tsx`, `AppSidebar.tsx`
- `web/src/pages/Authorize.tsx`
- i18n files
- Web `__tests__`
- `e2e/tests/16-team/16-03-*` (new), `26-01-chooser.test.ts`, `e2e/src/utils/config-store-helpers.ts`

**Order:**
1. Agree the contract first: the 409 body and `/me.orgSelectionRequired`.
2. Writer A writes the failing integration tests, then the resolver, then fixes existing tests.
3. Writer B works in parallel against the contract.
4. The e2e run happens only after both are in.
5. **Ship together, in one PR and one deploy.** With only the server change, a two-org user with no stored org gets `organization:null` and has no switcher (`private/account/web/src/components/AppSidebar.tsx:472`), so they are stuck.

**Risks:**
- **The working tree is dirty.** `proxy.ts`, `test.ts`, `configs.ts` and `web/src/api/config.ts` are uncommitted edits from the configs fix. The writers must build on them.
- **Race when creating a first org.** Two requests at once for a zero-membership user could each create an org. The user would then have two orgs, and every later call would get a 409. Before this change the first-membership fallback hid that. Mitigate by recreating the membership check inside `runAtomic`, or accept it given how rare zero-org users are (hypothesis).
- **Swallowed errors.** Anywhere that catches the resolver error broadly will hide the 409: the two middlewares, and `/me`'s own fallback at `private/account/web/src/auth/AuthContext.tsx:142`.
- **Chooser deadlock.** If the chooser never renders on a page and a call there gets a 409, the user is stuck. The global event handler covers this; e2e step 5 tests it.
- **Existing tests.** Integration tests that quietly relied on the first membership will now fail with 409. That is intended, but it is extra work.

### Critical Files for Implementation
- /home/developer/console/private/account/src/services/org.service.ts
- /home/developer/console/private/account/src/routes/portal.ts
- /home/developer/console/private/account/src/middleware/partner.ts
- /home/developer/console/private/account/web/src/auth/AuthContext.tsx
- /home/developer/console/private/account/web/src/api/client.ts
