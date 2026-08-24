## SESSION b7baf3ee 2026-08-24T07:20:21Z

## Where things stand

Branch `0823-1`, **PR #571 open and READY**. ONE PR -- never `gh pr create`.
**Do NOT merge; `/pr-merge` is the operator's.** Everything committed and pushed
through `2175e4df`. No writers live; tree clean.

## Two todos the operator just gave, both OPEN

Screenshot: `/tmp/Screenshot 2026-08-24 064656.png` (readable with the Read tool).
- **t1 #4ae69b7e REMOVE** the "79 / 79" tally on /en/docs. It is
  `<output class="docs-browse-tally">` inside `.docs-browse-status`.
- **t2 #2f365184 ALIGN** the results heading ("Tutorials") with the rail heading
  ("Filter"): both have a rule beneath and they sit at different heights. Share a
  baseline. Do NOT change column widths.

## Round 6 + follow-ups: ALL DONE

n1 media, n2 tabs, n3 per-line copy, n4 layout, n5 stats order, n6 hero CTAs,
n7 hero video. Then four operator follow-ups in `9e370857` (hero language
dropdown was white-on-white 1.00 -> 18.86; persona stats order; docs browse hero
removed with the h1 kept sr-only; `--docs-prose` 34rem -> 44rem so content is
704 in an unchanged 800 column). Then `2175e4df`: tutorial pages now use the
SAME 3-column layout as every docs page (both are sidebar 31-281, content
313-1113, prose 361-1065).

## Media: BOTH prefixes are restored now

Tutorials AND solutions. The hero videos were 404 because I had only run
`--tutorials-only`; solution videos live under a separate R2 prefix.
`.ci/scripts/deploy/sync-media-from-r2.sh --solutions-only`, credentials from
`private/account/.env` (copied from `~/monorepo_archive/console/`), with
`R2_MEDIA_BUCKET=rediacc-www-media` (NOT in that .env) and
`AWS_DEFAULT_REGION=auto` (or list-objects returns an empty list). 1.7G total.

## CI and review

Last full run green on an earlier head. `Review Gate` / `Review Complete` go red
whenever the head moves ahead of the review; three review passes have each found
something real, the last being MY tautological selftest, fixed in `ab920350`.
Threads: 0 unresolved. After the next push, expect one more review pass.

## Environment

- Dev server RUNNING at :4321. `/en` works, `/en/` 404s.
- `agent-browser set viewport <w> <h>` -- NOT `agent-browser viewport`, which
  silently reports "Unknown command" and leaves you measuring at 1440.
- **Do NOT run `build:www`** here: it corrupts every running dev server in this
  checkout and deletes 14 tracked `search-index*.json`.
- Run `npx eslint <file>` AND `npm run check:format` on anything edited.

## Next action

1. Do t1 (remove the tally) and t2 (align the headings), measuring before/after.
2. Push, watch CI, then let the review re-fire and answer it.
3. NEVER merge, NEVER push main, NEVER a second PR.

## Carried, briefs written, no owner

Item 4's `<Sentences>` mechanism (`agent/PLAN-sentence-aware-wrapping.md`), then
wave D gates 2/4/5 (`agent/programs/www-round5/05-gates.md`).
