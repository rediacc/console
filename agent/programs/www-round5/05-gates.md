# 05. Gates (Wave D)

Status: planned, not started. Four gates.

**File ownership for this wave.** `scripts/check-*.ts`, root `package.json`,
`scripts/ci-runner/manifest.ts`, `.github/workflows/ci.yml`, `scripts/data/*baseline*.json`.

## The three-point wiring

Adding a blocking gate is exactly three edits, and `check:ci-parity` enforces all three
bidirectionally: miss one and that gate fails. There are 271 gate ids and 175 `check:*`
keys today.

1. Root `package.json`: a `check:ci-<name>` key. The control-first form, used by every gate
   that has a self-test and strongly preferred here:
   `"check:ci-foo": "tsx scripts/check-foo.ts --selftest && tsx scripts/check-foo.ts"`
2. `scripts/ci-runner/manifest.ts`: the gate entry.
3. `.github/workflows/ci.yml`: the workflow step.

`evidence/EXPLORE-chrome.md` section 4.2 names `check:ci-layout-overflow` as the gate to
copy verbatim, 4.3 documents the shrink-only baseline pattern precisely, and 4.4 covers
`check:ci-parity` and `check:ci-gate-reachability-coverage`. Read those three sections
before writing a line.

## The rule every gate here obeys

**A gate that cannot fail is a defect, not a pass.** Every gate below ships with a control
that mutates something real and requires the gate to go red. State in the gate's own header
what the control mutates and why that specific mutation proves the detection works rather
than proving a file exists.

CI has a hard 15-minute cap on the slim runner. Budget accordingly and say what each gate
costs.

## Gate 1 and 2: sentence wrapping

Designed in full in `agent/PLAN-sentence-aware-wrapping.md`. Two gates, deliberately.

**`check:ci-sentence-wrapping`** (static, `quality-content`, under 2s). Every multi-sentence
catalog value rendered in text position must go through the `<Sentences>` mechanism.
Shrink-only baseline. **Control: stub the sentence counter to always return 1 and require
the positive fixture to flip green** - that proves the finding comes from detection rather
than from a file existing.

**`check:ci-sentence-lines`** (browser, `quality-www-build`, needs `build:www`, budget 120s).
Playwright over `dist`: 13 locales x 6 page families x 2 viewports = 156 measurements at
about 0.5s each. **Control: strip `display:inline-block` from a fixture and require the
count to rise.** Plus an anti-vacuity floor: at least 8 candidate blocks per measurement,
otherwise a 404 or an empty route passes silently and the gate is measuring nothing.

The plan rejected rewriting `dist/**/*.html` for good reasons: six hydrated islands per page
drop injected spans on hydration and five multi-sentence blocks per page live inside them,
it needs an HTML parser the repo does not have, and it never runs under `npm run dev`.

## Gate 3: docs topic coverage

The operator's words: "this should be enforced by ci.yml for future cases as well. No
exception. For all the items we have."

Assert, over every doc in every locale:

- `subcategory` is present and is valid **for that doc's category** under the widened
  vocabulary from wave C.
- The browse card renders it.
- `public/img/docs-thumbs/<slug>.svg` exists for the doc's base slug. There is no
  regenerate script, so a new doc without a hand-authored thumbnail must fail here rather
  than ship a blank card.

This is a static gate over frontmatter plus a filesystem check: cheap, deterministic, and it
can run on every push.

**Control:** remove the subcategory from one fixture doc and require a red. Then remove one
thumbnail and require a second, distinct red - one control per assertion, because a single
control only proves one branch runs.

Note the count to expect: 79 English docs, 1,015 rendered. If the gate reports fewer than
79 candidates it is not seeing the collection, and it should say so rather than pass.

## Gate 4: section surface

Assert that every `<section>` resolves to a token in the ladder, and that **no two adjacent
sections resolve to the same surface**. That second half is the one that catches the
`/en/pricing` defect where six consecutive `section-light` sections made the page read as
one undifferentiated slab.

Route set at minimum: `/en`, `/en/pricing`, `/en/for-devops`, `/en/disaster-recovery`. This
needs computed styles, so it is a browser gate; fold it into the same Playwright pass as
gate 2 rather than paying for a second browser launch.

**Control:** point one section at a raw hex instead of a token and require a red; then make
two adjacent sections share a surface and require a different red.

## Gate 5, optional but recommended: accessibility

axe-core over a route sample with a **shrink-only baseline** seeded at today's count, so it
can only improve. The baseline today on `/en` is 2 violations and 4 incomplete; wave A
clears most of them, so seed the baseline **after** wave A lands, not before, or you
enshrine defects you already fixed.

**Control:** the shrink-only pattern has a known composition trap documented in
`evidence/EXPLORE-chrome.md` 4.3. Read it. The control must prove the gate fails when the
count grows, not merely that it reads the baseline file.

---

## Status after the 0823-1 wave, and a blocker that was NOT one

**Gate 1 `check:ci-sentence-wrapping` — BUILT, wired, green in CI** (`7a5b9632`).
22 selftest controls including the counter-mutant leg. Shrink-only baseline
seeded at **51 unwrapped renders**, not the 818 this suite predicted: 818 counted
catalog LEAVES, 51 counts text-position RENDERS. Different denominators, not a
discrepancy.

**Gate 3 — SHRANK, then BUILT** (`362baf11`). Its per-doc subcategory legality
assertion moved into the content collection schema itself: `content/config.ts`
carries `z.enum(DOC_SUBCATEGORY_VALUES)` plus a `superRefine` checking category
legality, verified by planting an illegal value and watching it rejected by name.
Re-implementing that in a script would have been a weaker second copy of a check
that already cannot be bypassed, so the gate ships as thumbnail coverage only:
79 docs, 79 thumbnails, six selftest controls plus a live one.

**Gates 2, 4 and 5 — NOT built, and the reason I kept giving was WRONG.**

I repeatedly recorded these as "blocked on a built site, because `build:www` is
forbidden in this shared tree". That is true LOCALLY and irrelevant to CI:

- `.github/workflows/ci-quality.yml` already has a `quality-www-build` job
  (`:1220`) that already runs `npm run build:www` (`:1269`). A browser gate wired
  there needs NO new build step.
- `.ci/scripts/quality/browser-smoke.sh` is the harness to copy. It runs
  Playwright in the official `mcr.microsoft.com` container (anonymous, not rate
  limited), derives the image tag from the installed package so it cannot drift,
  and offers `REDIACC_SMOKE_NO_DOCKER=1` to run against a local Chromium.
- `check:ci-browser-smoke` is already wired at `:1290` and is the three-point
  precedent.

So the real constraint is only that their CONTROLS cannot be verified against
`dist` in this tree. Take a base-URL parameter: the running dev server at
`localhost:4321` locally to prove each control fires, the built preview in CI.

Gate 5's sequencing correction still stands and is separate: this document says
seed the accessibility baseline "after wave A lands". Wave A landed early, but
waves B and C changed the a11y surface afterwards, so seeding then would have
enshrined defects they were about to fix. Seed after ALL waves.

Gate 4 also needs an EXEMPTION this document does not anticipate: after wave A,
the only remaining adjacent-same surface pairs are DELIBERATE dark-band merges
(`/en` closing band into the footer; `/en/for-devops` benefits + cta + footer as
one band). Without it the gate reports the fixed state as broken.
