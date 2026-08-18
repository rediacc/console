# www-simplification

Simplify `packages/www` against two references the operator named: **claude.com**
for simple design generally, and **anthropic.com** for its homepage motion. Also
fix every bug found on the way, and add the CI regression gates that stop all of
it coming back.

Produced by session `e6500e92` on 2026-08-17/18, from fourteen parallel
specialists. Their evidence is in `research/` (17 documents). Program state lives
at `~/.claude/projects/-home-muhammed-monorepo-console/programs/www-simplification/`.
Memory pointer: `project_www_simplification.md`.

**Nothing has been implemented.** `git status --porcelain packages/www/` returns
zero lines, verified on `main` at 2026-08-18T05:13Z.

## Read order

1. This file.
2. `01-verified-context.md` - what is true in the tree, re-verified on `main`.
3. `02-locked-decisions.md` - the operator's rulings. Do not relitigate these.
4. `03-bugs-and-gates.md` - the 24 defects and the 12 gates that catch them.
5. `04-execution-guide.md` - order, gates, staffing, definition of done.
6. `research/01-SYNTHESIS.md` when you need the argument behind a decision, and
   the matching `research/RESEARCH-*.md` when you need the measurement behind a
   number. Do not re-run the research; it is done.

## The one finding that explains the rest

**Nothing is shared.** Nine independent specialists, working disjoint domains
without comparing notes, each found the same shape: a shared thing already
exists, and the code goes around it.

| Exists | Bypassed | Verified on `main` |
|---|---|---|
| A complete form system | **zero consumers** | `main.css:2717`, `grep -rl form-input src/` returns 0 files |
| A `--radius-*` scale | ignored; `100px` x6, `6px` x5 hardcoded | `main.css:248-254` |
| One `:root` token set | five blocks, the last silently wins | `BaseLayout.astro:279` |
| One primary CTA | built 9 times in two greens | `#556B2F`, `#4A7C3F` |
| One card | 33 shells, 7 radii | - |
| One overlay | 6, focus trap byte-identical in 3 files | - |
| A scroll-reveal system | ships sitewide, used on 8 elements | `main.css:3348-3387` |
| Short nav labels, translated | denormalised ~9x, menu uses marketing H1 instead | `explore.solutions[].title` |
| A heading id | TOC recomputes a worse one and discards it | `sidebar-behavior.ts:62` |

**This is a subtraction program.** Most of the win is deleting bypasses and
connecting what is already there, not designing anything new.

## Non-negotiable working ethos

Validate, do not believe: every `file:line` reference is a hypothesis, re-verify
it against the tree, run the real thing, read stdout and stderr separately, and
plant a control before trusting any zero. This program caught four instruments
reporting success without having run; assume yours will too.

Everything stays local and uncommitted: no commit, branch, push or PR unless the
operator asks in-task; never `git checkout/restore/stash/clean`; repair forward.

**The tree is parked on `main`, so nothing here can be committed as-is. Cut a
fresh `MMDD-N` branch BEFORE editing any tracked file.**

Testing and concurrency support are first-class deliverables, not follow-ups.

NO em dashes in any authored text, in any language.

## Staffing

**Opus** is the default for coding sub-agents. **Fable for the challenging pieces
and for all planning agents.** **Sonnet for every translation and naturalization
run**, delegated to sub-agents, which is the operator's cost policy and is why the
ledger records sonnet.

At most **2 concurrent writers**, with disjoint file ownership stated verbatim in
every prompt. Investigation agents fan out freely. Every sub-agent report is
spot-checked against the artifact before anything builds on it.

**Fable-tier pieces, named:** w5 (anchors F1+F2, because F2 rewrites fragment
identity across 936 translated files), w8 (illustration de-texting, because the
translations must be imported out of 573 SVGs and no tool does that today), and
w9 (the constellation, because its geometry has to encode a taxonomy that does
not exist yet).

**Never put the hero and the below-fold homepage work in one slot.** They share
`src/pages/[lang]/index.astro`. The same applies to the token layer and the
primitive layer, which share `public/styles/main.css`.

## Scope

- **w1 Wave 0** - gate scaffolding and the RED-first regression gates.
- **w2 Wave 1** - locale chunking, the 6.7 MB client bundle.
- **w3 Wave 2** - collapse the token layer to one `:root`.
- **w4 Wave 3** - one primitive vocabulary; adopt the dead form system.
- **w5 Wave 4** - anchors F1 and F2, plus the locale-derived-identifier class.
- **w6 Wave 5** - homepage: hero and below-fold.
- **w7 Wave 6** - pricing and docs surfaces.
- **w8 Wave 7** - illustrations become textless, 573 files to about 21.
- **w9 Wave 8** - solution constellation: re-taxonomy, label harvest, then build.
- **w10 Wave 9** - motion: adopt the scroll-reveal already shipping.
- **w11 Wave 10** - verification and the before/after scorecard.

### Live file ownership, ratified 2026-08-18 10:05

Two writers collided once in `main.css` because a scope expansion granted to one was
never propagated to the other. The boundary is now explicit.

**A correction to how this fence was justified, kept because the error is instructive.**
It was originally ratified on a "second near-collision" in `legal-page.css` and
`professional-services-page.css`, both apparently written at 09:55:18 in one scripted
pass. **That did not happen.** `ls --time-style=+%H:%M:%S` prints only the time and DROPS
THE DATE: the real mtime on both files is **2026-06-06**, and `git diff --quiet` reports
both **UNMODIFIED** against HEAD. The `var(--font-size-*)` density read as a
forcing-table signature was original to those files.

The fingerprint was plausible, self-consistent, and wrong, and it was believed without
the one-command control that would have refuted it. The fence below is still correct and
still wanted, because the `solution-pages.css` and `pricing-page.css` grant was real.
Only its justification was fiction. **Add `--time-style=full-iso` to the trap list: a
truncated timestamp turns a two-month-old file into this morning's edit.**

| Owner | Files |
|---|---|
| `w3-tokens` | all of `packages/www/src/styles/*.css` and the forcing table across them, plus the completed value-only pass in `pricing-page.css` |
| `w4-primitives` | `packages/www/public/styles/main.css`, its components, the four stylesheets it DELETES (`contact-modal`, `search-modal`, `region-picker`, `platform-tabs`), and the four it edited to drop those imports (`newsletter`, `install-page`, `downloads-page`, `lead-magnet-modal`) |

**`packages/www/src/i18n/translations/` is SERIALISED and owned by NOBODY.** Multiple
waves delete keys their own cuts orphan, and all of them write the same 13 files. A wave
collects its orphan branch list and reports it; the LEAD applies every deletion in ONE
consolidated pass at the end, then runs `npm run i18n:generate-hashes` **once**. That is
better than merely safer: the hashes script rewrites every tree and has been observed
touching `packages/cli`'s manifest and writing through into `private/account`, so running
it per-wave multiplies that blast radius.

**Nobody touches `pricing-page.css` structurally.** w7 deletes 771 of its 2,321
lines and the value-only diff was kept to 56 lines with no line moved so that
deletion stays readable.

**If a writer finds residue inside a file another writer holds, it reports it with
`file:line` and leaves it.** Reaching in for a one-line change is exactly how the
`main.css` overlap happened.

**The forcing table is being consumed as it is applied.** w3 handed w4 199 off-ladder
font sizes, 77 radii, 34 shadows; measured at 10:02 the tree was at **112 / 43 / 10**,
with `solution-pages.css` at zero across 121 declarations. Per-wave credit is
meaningless here: the programme target is the painted-value count on the built site,
so a wave that reports a "shortfall" because another wave took the declarations first
has not missed anything.

**Explicitly OUT**

- Anything in `private/account`. The portal owns the checkout redirect that drops
  `?checkout=` params, and the community-fallback behaviour. Report, do not touch.
- `.github/workflows/ci.yml` itself. Gates are reached through `npm run ci` and
  `scripts/ci-runner/manifest.ts`; the workflow file needs no change, which was
  verified.
- `SPSocialProof.astro` and its re-enable comments. Deliberate dead code tied to
  rediacc/console#519. A cleanup sweep must not remove it.
- Re-running any research. Fourteen specialists finished; `research/` is the record.
- The four metrics we already beat: unused-CSS percentage, DOM node count and
  depth, above-fold interactive density, accessibility violation count. Optimising
  these is theatre.

## Operator decision points (ask EARLY, in one round)

1. **Do the two safe-defaulted design questions stand?** RECOMMENDED: demote Blog
   and Partners from the bar to the footer they already appear in, and move
   `sp-why-now` (786px) to a subpage.
2. **What are the new disaster-recovery service tier names?** The rename is locked;
   the names are not. RECOMMENDED: propose three and get a yes, rather than block.
3. **Does the constellation replace the mega menu outright, or sit alongside it
   until w9 lands?** RECOMMENDED: replace outright at w9, since keeping both is how
   the site gains a fourth nav system.
4. **Is there a second `astro dev` on this tree?** One ran on port 4802 for over a
   day during research, owned by another session. RECOMMENDED: check and ask before
   assuming the rig has the tree to itself.
