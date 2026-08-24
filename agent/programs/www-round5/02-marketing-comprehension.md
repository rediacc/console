# 02. Marketing comprehension (Wave B)

Status: planned, not started. Covers operator items 1, 2, and the item-4 fixes in
marketing copy.

**File ownership for this wave.** `src/components/solution-pages/SPHomeNotASlice.astro`,
the `HomeDifference` component, the shared FAQ component, `PricingTrustSection.astro`,
`src/styles/pricing-page.css`, `src/i18n/translations/*.json`.
**`public/styles/main.css` belongs to wave A alone** and must not be touched here.

## Item 1: visualise the Difference section

Today `.home-difference` is an H2 plus two bordered cards of four sentence pairs each: 532px
of text with no visual. The operator wants the treatment used by the pricing page's
`No Lock-In. Ever.` section, which alternates left-text/right-visual then
right-text/left-visual with inline mock-UI SVGs.

That pattern is not reusable today. It exists once, its alternation is hard-coded rather
than derived from a row index, and it uses a `direction: rtl` hack that breaks the
alternation under `/ar/`. Meanwhile the previous alternating implementation of the
Difference section is still sitting in the stylesheet as dead CSS.

**Do it in this order:**

1. **Extract a real component** taking `{title, description, visual}` per row, with the
   alternation derived from the row index and expressed with `order` or `grid-column`
   rather than `direction: rtl`. This is what makes `/ar/` correct.
2. **Repoint the pricing section at it.** Same rendering, one implementation. Fix the stray
   dashed rectangle on the first row while you are in there.
3. **Rebuild the Difference section on it**, cut from eight text lines to **four
   before/after rows**, each with a visual: copy in 60 seconds, hourly backups without extra
   storage, recovery tested in 60 seconds, a fresh copy per developer.
4. Tell wave A that `main.css:1956-2090` (`.difference-row*`, `.difference-zoom*`) is now
   safe to delete, and confirm `check:ci-dead-css` and `check:ci-css-dom-refs` stay green.

Source the visuals from the 22 SVGs in `src/assets/images/illustrations/`, or author new
ones in the same stroke-only house style. `evidence/EXPLORE-home.md` section D has the full
inventory and the two embedding mechanisms.

**Verification.** Screenshot `.home-difference` at 1440x900 and 390x844 before and after.
Four visual rows must be present, and `/ar/` must alternate in the mirror direction.

## Item 2: score and cut the FAQ

`/en/pricing` carries 12 questions. Verbatim: free trial / credit card / upgrade or
downgrade / annual billing / payment methods / how machines are counted / runs on my own
servers / machines per plan / what Enterprise includes / education and nonprofit discounts /
what happens if I cancel / how cluster nodes are counted.

**Locked by the operator:** score every question on buying-decision value, merge the
duplicate clusters, cut to about six.

Two clusters are already visible. Three questions are all about counting machines ("How are
machines counted?", "How many machines does each plan cover?", "How are cluster nodes
counted?") and belong in one answer. Two are billing mechanics ("Do you offer annual
billing?", "What payment methods do you accept?") and belong in one.

Score the rest against a single question: **does a prospect need this answered before they
will pay?** Anything that is really a support question belongs in docs, not on the pricing
page.

`evidence/EXPLORE-home.md` section C carries the full 55-item inventory across nine data
sets, the three rendering paths, and the exact cost of a deletion.

**The deletion is not free.** Removing a question orphans its keys in all 13 locale
catalogs, and `check-dead-translation-keys.ts` fails on orphans. Prune the locales in the
same change. Note also that the FAQ feeds structured data, so a deletion changes the
emitted schema.

**Verification.** Item count drops to about six; `npm run check:i18n` and the dead-key gate
both stay green.

## Item 4 fixes in marketing copy

The mechanism, the evidence that chose it, the sweep and both gates live in
`agent/PLAN-sentence-aware-wrapping.md`. Read it before touching this. What matters here:

**The operator's literal rule is unsatisfiable and was corrected.** "A line must not both
end one sentence and begin another" turns `.sp-slice-winner-description`, which is five
sentences on two lines, into five lines. The enforceable rule is: **a sentence that occupies
more than one line must not share either of those lines with a neighbour.** Two whole
sentences on one line is fine.

Measured on `/en` at 1440x900 with one detector across four mechanisms: today 11 defects,
`text-wrap: pretty !important` 11 (it moves nothing), `text-wrap: balance !important` 8,
sentence spans **0**. Cross-locale with sentence spans: `/ja` 12 to 1, `/ar` 8 to 1, `/zh` 4
to 1, `/en` at 390x844 18 to 1. No horizontal overflow at any viewport, page height cost at
most +1.2%.

Rendered proof: "Most tools copy one / piece. We copy all of it." becomes "Most tools copy
one piece. / We copy all of it."

**One of the operator's examples is not this defect.** `/en/docs` rendering "Creating Your /
First Repository" is one sentence in a 124px `.docs-card-link` that already has
`text-wrap: balance`. It needs a width or type fix in wave C, and the sentence mechanism
does nothing for it. Say so rather than quietly leaving it broken.

Scope for this wave: the marketing call sites among the 80 identified across 34 files.
Markdown docs need zero call-site edits because they go through a rehype plugin.
