# 02. Locked decisions

Status: **Locked by the operator (do not relitigate)**, 2026-08-17/18.

Each was answered directly by the operator. Re-opening one wastes the round trip
that settled it. Where a decision has a consequence the operator did not state,
that consequence is marked as an inference and is yours to sanity-check.

## Scope

**L1. Everything rides ONE big-bang change.** Design simplification plus all 24
bugs plus the 12 regression gates, on one branch. Gates go in **RED-first** where
they encode a bug that exists today, so each fix turns one green and the gate and
the fix prove each other.

**L2. Do not descope, and do not write "defer".** The operator's words: *"Keep in
mind 'defer' like words are not liked here."* Ordering inside one change is
legitimate and must be written as ordering. Postponement is not. If a piece
genuinely cannot be done, say which piece and why, out loud.

## Product and design

**L3. Anchors: F1 AND F2, together.** F1 makes `generateTOCFromHtml` read the `id`
it already matched, after which `stringToSlug` has zero callers and is deleted.
F2 moves to stable English fragments across all locales, the way
`docs.claude.com` does it. F2 also fixes 30 hand-written dead anchors and makes
the search fragment locale-independent by construction. 920 of 936 translated
files already have matching heading counts; 16 need a hand pass.

**L4. Illustrations carry NO TEXT AT ALL. Revised by the operator 2026-08-18**,
and the revision is cheaper than what it replaces. Their words: *"I think
illustrations should not have texts like in other example websites that we target
to look like for simplicity. So, that can also reduce the cost of maintenance."*

This supersedes the earlier "de-text into live HTML text" plan. The difference
matters:

- **Earlier plan:** lift 92 baked-in strings out of the SVGs into live HTML text,
  putting about **1,196 locale values** into the translation pipeline and
  requiring an importer that does not exist.
- **Locked plan:** the drawings become **textless diagrams**, matching the
  reference. claude.com's three homepage drawings use `viewBox="0 0 500 500"`,
  two fills and **zero `<text>` elements**. The meaning is carried by the shape.

Consequences, all improvements:
- **573 files collapse to roughly 21**, one per slug, because the 26-per-slug
  explosion existed ONLY to carry per-locale and per-viewport baked text.
- **Near-zero new locale values**, against 1,196. The translation-pipeline cost
  this decision was weighed against largely disappears.
- **No SVG-text importer is needed.** That spike (S3) is cancelled.
- Maintenance drops permanently, which is the operator's stated reason.

Where a label is genuinely load-bearing, it moves into the **surrounding HTML**
as a caption or heading, translated through the normal key path. Judge that case
by case and keep it rare; the default is no text.

This still resolves dark mode, since 521 of 521 currently open with a hardcoded
`#f5f5f5` background.

**L5. Delete the fake terminal from the homepage hero.** Largest object above the
fold, fails contrast in three classes, breaks at 390 px, and ships a disclaimer
apologising for being simulated. Neither reference site puts a simulated artifact
in its hero.

**L6. Rename the disaster-recovery service tiers to Recovery Assessment /
Recovery Program / Recovery Retainer.** Chosen by the operator 2026-08-18. They
currently reuse `Professional` / `Business` / `Enterprise` from the software plans
for a human-delivered engagement. The new names describe the engagement rather
than a subscription level, so nothing collides. **The prices are correct and
intentional; fix the label, never the number.** (See L11.)

**L7. `announcement.enabled` off everywhere.** English is right; the twelve other
locales are stale. The operator also asked for a CI check so the class cannot
regress, which is gate G12.

**L8. Community stays hidden.** It is a state, not a product: `private/account`
reverts an account to community when payment lapses or a trial is cancelled.
Remove the full comparison column it occupies, add no card and no signup path,
and remove the FAQ entry that contradicts that table on three points.

**L9. The solution constellation is IN, in dependency order.** Not a smaller
substitute, not a postponement:
1. `role` re-taxonomy (Copy / Test / Recover / property). The geometry is
   meaningless without it.
2. Label harvest: normalise `explore.solutions[]` into 42 keys. **-6,474 locale
   values**, and the replacements already exist and are already naturalized.
3. The full 21-node constellation, built on the two above.
4. The compact 4-node variant is the **same component with a filtered node set**,
   dropped into the hero slot L5 vacates. A render mode, not a lesser version.

**L10. Add the CI regression gates.** The operator's words: *"Wouldn't it be nice
if we also enhance `.github/workflows/ci.yml` for regression?"* Answer: yes, and
it is the half that makes the other half stick. See `03-bugs-and-gates.md`.

## Corrections the operator made to this program's own findings

These were reported as defects and are **not**. Re-filing one is a regression in
the record, not a discovery.

**L11. The disaster-recovery prices are not a contradiction.** $1,299 / $3,999
against the software plans' $49 / $59 is a **human-delivered services offer**. The
price gap was the point. A specialist inferred a bug from the gap alone.

**L12. 3.2 TB in 4.7 s and 241 GB in under 60 s are different tests, both
stable.** Not a contradiction. Do not re-file.

**L13. `claude-sonnet-5` in the i18n ledger is deliberate.** Translations are
delegated to sub-agents on sonnet to save cost. Do not "fix" it back to haiku.

**L14. The nav relabel is not a 273-string bill.** `explore.solutions[].title`
already holds a short 1-to-3-word name per solution, already translated in all 13
locales, merely denormalised about nine times. Harvesting is close to free and
nets **-6,474** values.

## Working conventions

**L15. Agent knowledge files must be self-contained.** The operator's words:
*"make agents general! They should not depend on external md files!"* The three
touched this session (`www-site.md`, `browser-probe.md`, `i18n-guardian.md`)
reference no program document. Keep it that way, and if you write a new one,
inline the knowledge rather than pointing at this suite.

**L16. No artifact.** The operator declined a published Artifact for this program.
Markdown in the repo is the deliverable.


## Execution mandate, 2026-08-18

**L17. Work uncommitted on `main`.** The operator chose this over cutting an
`MMDD-N` branch, overriding the note in `agent/RULES.md`. No commits, no branch,
no push, no PR. Another agent branches and merges later. Because there is no git
rollback point, write a full tree patch to the program `checkpoints/` directory at
every wave boundary.

**L18. Run all eleven waves. Stop only when genuinely blocked**, meaning a gate
that cannot be made to fail, a decision no default covers, or a destructive step
outside what has been sanctioned. The operator is away for a long stretch and
expects a finished tree and a report, not a queue of questions.
