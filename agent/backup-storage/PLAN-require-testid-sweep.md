# PLAN: enable custom/require-testid across private/account/web
Status: done
Owner: 97604f47
Updated: 2026-08-15

**2026-08-15 CLOSED, on a resolved config rather than an inference.**
`npx eslint --print-config private/account/web/src/App.tsx` returns
`custom/require-testid -> [2, {...}]`, i.e. severity 2 (error) with the full element
config, for a real file in the target tree. The rule is enabled there because the block
at `eslint.config.js:272` scopes to `**/*.{js,jsx,ts,tsx}` and the global ignores exclude
only `private/account/web/node_modules/**` and `.../dist/**`, not the source. And
`npm run check:lint` (`eslint packages scripts private/account --max-warnings 0`) exits
0, so the rule is on at error level across that tree with ZERO outstanding violations.

Both halves are needed and neither alone would prove it: enabled-but-unlinted would be a
dead rule, and lint-clean-but-disabled would be a vacuous pass.

Operator decision (2026-08-15): ENABLE the rule. Not "leave it recorded", not "delete it".
Their sequence: investigate with a sub-agent, enable, employ a plan agent to fix, then
validate. This file is the plan; it was written by the lead, not by the Plan agent, because
that agent's output never arrived twice in a row and a `Plan` subagent has no Write tool, so
its work cannot survive a lost report. Every number below was derived by the lead from the
survey's RAW eslint JSON (`/tmp/testid-account.json`), not from its summary.

## 1. Where the rule stands right now

- `packages/www`: **already enabled and clean.** Measured 0 findings across all 28
  `.tsx/.jsx` files, so the switch cost nothing. Verified `npx eslint packages/www/src`
  exit 0 after enabling.
- `packages/e2e-tests/**` and the `__tests__` globs: **stays off, deliberately.** Test
  files do not need testids.
- `private/account/**/*.{ts,tsx}`: **still off.** That single `'custom/require-testid': 'off'`
  line (in the block whose `files:` is `['private/account/**/*.{ts,tsx}']`) is the last
  thing between here and the rule being fully on. Removing it is step 4 below.
- `.ci/scripts/quality/lint-rule-liveness.mjs` has `KNOWN_UNREACHABLE = {}` and the gate
  now reports `require-testid=3` directories reached. The gate REFUSES a stale exception,
  so nothing may be re-added there to paper over this.

## 2. What the rule actually demands (configured, not default)

`eslint.config.js` `'custom/require-testid': ['error', { ... }]`:

- `requiredElements: ['Modal', 'Drawer']`
- `interactiveElements: ['Button']`
- `formElements`: the Ant Design data-entry set (`Input` and its variants, `Select`,
  `Checkbox`, `Radio`, `Switch`, `Upload`, ...)

The satisfying attribute is `data-testid`. Getting this wrong is 287 wasted edits, which is
why it is quoted from the config rather than from the rule's defaults.

## 3. The 287, broken down (from the raw JSON)

| Element | Findings |
|---|---|
| `Button` | 162 |
| `Input` | 84 |
| `Modal` | 36 |
| `Switch` | 3 |
| `Select` | 2 |
| **total** | **287** across **68 files** |

All five are Ant Design components, so every fix is "add `data-testid="..."` to a JSX
element", with no structural change. There is no class here that should be exempted
instead: `Modal`/`Button`/`Input` are exactly the interactive surface the rule exists to
make selectable, and the tree already labels 477 of them.

## 4. The convention to FOLLOW, not invent

`private/account/web/src` already carries **477** `data-testid` values. The convention,
from the most frequent real examples:

- kebab-case, semantic, no component-name prefixes:
  `table-empty` (×20), `filter-bar` (×15), `pagination` (×8), `status-filter` (×6),
  `stat-grid` (×6), `recovery-code` (×4), `quote-status` (×3)
- page-level roots use a `-page` suffix: `partner-exam-session-page`, `partner-study-page`,
  `partner-study-module-page`

**Values are view-scoped, NOT globally unique** — `table-empty` legitimately appears 20
times across different pages. So uniqueness is required only WITHIN a rendered view. This
is the single most important thing for a writer to know: do not "fix" the repeats, and do
not invent globally-unique names to avoid a collision that the convention does not treat as
one.

## 5. Collision safety inside `.map()`

An element rendered in a loop needs a discriminator or every row gets the same testid.
Follow the surrounding code: use a stable field from the row (an id, a slug, a key), never
the array index alone, because index-based ids change when the list reorders and silently
retarget a test at a different row.

## 6. Rename blast radius: additions only

These e2e page objects and specs select on testids (`getByTestId` / `[data-testid=...]`):
`private/account/e2e/src/pages/**` (PortalDelegationCertsPage, portal/InvoicesPage,
partner/PartnerCustomersPage, partner/OfferBuilderPage, admin/AdminActivityPage,
admin/AdminReconcilePage, ...) and specs under `private/account/e2e/tests/**`.

**ADDING an attribute is safe. RENAMING an existing one breaks selectors.** No existing
`data-testid` value may be changed by this sweep, in any file, for any reason.

## 7. Batching: two writers, disjoint file ownership

The 68 files split into two balanced, strictly disjoint batches (hard cap of 2 concurrent
writers in this repo):

- **Batch A** — 34 files, 144 findings. File list: `/tmp/batchA.txt`.
  Heaviest: `pages/Team.tsx` (21), `pages/admin/SubscriptionDetail.tsx` (13),
  `pages/admin/VersionPolicy.tsx` (11), `pages/admin/QuestionBank.tsx` (10).
- **Batch B** — 34 files, 143 findings. File list: `/tmp/batchB.txt`.
  Heaviest: `pages/DelegationCerts.tsx` (15), `pages/admin/DelegationCerts.tsx` (15),
  `pages/Settings.tsx` (11), `pages/admin/DealQueue.tsx` (10).

Note both trees contain a `DelegationCerts.tsx` at different paths; they are DIFFERENT
files and both live in batch B, so no writer needs the other's.

## 8. The enabling edit

In `eslint.config.js`, in the block whose `files:` is `['private/account/**/*.{ts,tsx}']`,
delete the `'custom/require-testid': 'off',` line. Do this only AFTER both batches are
clean, so the tree is never left red.

## 9. Validation, which must be more than "eslint passes"

1. `npx eslint private/account/web/src --ext .ts,.tsx` exits 0 with the rule ON.
2. `npm run check:ci-lint-rule-liveness` exits 0 and still reports 30 rules fired,
   `0 enabled-but-unreachable`, and now a higher `require-testid=` reach count.
3. No existing testid changed: `git diff` must show only ADDED `data-testid` attributes.
   Verify by diffing the set of existing values before and after.
4. No duplicate testid within a single file that did not already have one.
5. **Prove the rule is not a no-op**: after enabling, delete one `data-testid` from a
   swept file and confirm eslint reports exactly that element, then restore it with `cp`.
   A rule that was enabled but silent would look identical to a clean sweep.
