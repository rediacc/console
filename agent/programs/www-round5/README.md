# www round 5: comprehension, docs information architecture, typographic enforcement

Scope: `packages/www`, the marketing and documentation site. Round 5 follows four landed
rounds (last: `28b152649 feat(www): round-4 docs browse, thumbnails, tutorial player, voice
rewrite`). The through-line is that the site is now correct but still reads as
machine-assembled: text-heavy sections with no visual anchor, a docs taxonomy that exists in
the data and is never surfaced, chrome that fades itself to nothing, and line breaks that
fall mid-sentence. Round 5 makes the existing structure legible and adds gates so the
regressions cannot come back.

Planned by session `a68f3ab4` (`console-39`) on 2026-08-23, in `~/monorepo/console` before
the repo moved to `~/console`. Every measurement in this suite was taken live against
`http://localhost:4321` with `agent-browser`, not read off a file. Branch at handoff: `0823-1`.

- Program state: `~/.claude/projects/-home-muhammed-console/programs/www-round5/`
- Memory pointer: `project_www_round5.md`
- Raw evidence: `evidence/` in this directory (four agent reports plus the session plan)

## Read order

1. `01-verified-context.md` - what is actually true today, including three premises the
   planning session got wrong and corrected.
2. The wave document you are on: `02-marketing-comprehension.md`,
   `03-chrome-and-surfaces.md`, `04-docs-surface.md`, `05-gates.md`.
3. `06-execution-guide.md` before writing anything.
4. `agent/PLAN-sentence-aware-wrapping.md` before touching item 4.
5. `evidence/*` only when you need the underlying `file:line` detail. Those four reports
   cost about forty minutes of sweeping and every claim in them is citation-backed.

## Non-negotiable working ethos

**Validate, do not believe.** Every `file:line` reference in this suite is a hypothesis
until you re-verify it against the tree. Run the real thing rather than reading it. Read
stdout and stderr separately. Plant a control before trusting any zero: a gate that reports
success without having run is the failure mode this repo has paid for repeatedly.

**Everything stays local and uncommitted.** No commit, branch, push or PR unless the
operator asks in-task. The operator runs `/pr-babysit` at the end. Never
`git checkout`, `restore`, `stash` or `clean`: the tree carries other sessions' work and
there is no safety net. Repair forward.

**Testing and concurrency support are first-class deliverables**, not an afterthought bolted
on once the feature renders.

**No em dashes in any authored text, in any language.**

## Staffing

Opus is the default for coding sub-agents. **Fable for the challenging pieces and for all
planning agents.** Sonnet for translation and naturalization work only.

At most **2 concurrent writers**, with disjoint file ownership stated verbatim in every
prompt and everything else explicitly forbidden. Investigation agents fan out freely.
Every sub-agent report is spot-checked against the artifact before anything builds on it:
their reports are accurate about intent and quietly wrong about placement.

**Fable-tier pieces in this program:**
- The item-4 sentence-wrapping mechanism and its two gates. It touches 818 multi-sentence
  English leaves across 80 call sites in 34 files, spans 13 locales including RTL and CJK,
  and its browser gate has an anti-vacuity floor to design.
- The surface-colour ladder in wave A. Three unreconciled mechanisms sit on one token
  layer, and collapsing them without regressing a page is a judgement problem, not a
  find-and-replace.
- The docs subcategory vocabulary in wave C. It widens a `z.enum` that 61 documents must
  then be assigned against, in a way a gate can enforce forever.

## Scope

- **Wave A, chrome and surfaces**: operator item 3 (condense the nav instead of blanking
  it), item 5 (the footer language switcher), item 6 (one surface ladder), and the
  accessibility defects that live in wave A's files.
- **Wave B, marketing comprehension**: item 1 (visualise the Difference section by
  extracting the pricing alternating pattern into a real component), item 2 (score and cut
  the FAQ), and the item-4 fixes in marketing copy once wave D's mechanism exists.
- **Wave C, docs surface**: item 7 (per-category subcategories, topic on the card, open the
  facet), item 8 (prose measure and player cap), item 9 (close the article/browse gap and
  ship Ask Assistant at zero API spend), item 10 (put the existing per-doc SVG on the page).
- **Wave D, gates**: the sentence-wrapping pair, docs topic coverage, accessibility with a
  shrink-only baseline, and section-surface adjacency.

**Explicitly OUT**

- Any LLM API spend. Ask Assistant forwards to the user's own provider account and calls
  nothing of ours. This is an operator decision, not a budget guess.
- Microsoft Copilot as an Ask Assistant target. Its prefill URL auto-executes with no user
  interaction, which is CVE-2026-24307. Do not ship it even though it works.
- Gemini, AI Studio and Mistral as Ask Assistant targets: no native prefill exists.
- Rewriting the docs content itself. This round changes how docs are structured, surfaced
  and framed, not what they say.
- The homepage FAQ. There is not one; the FAQ work is the pricing surface and its siblings.
- `SPSocialProof.astro`. It is deliberate dead code tied to rediacc/console#519
  (fabricated social proof) and carries re-enable instructions. Do not sweep it up.
- Regenerating the docs thumbnails. The generator that drew them is gone and they are now
  hand-authored; a new doc needs a hand-authored file, which is why wave D gates coverage.

## Operator decision points (ask EARLY, in one round)

Four of these the operator has already answered and they are locked. Two are open.

**Locked by the operator (do not relitigate):**

1. **Header (item 3).** Condense the nav into a persistent slim context bar carrying the
   mark, a breadcrumb of where you are, search and the primary CTA. The full nav returns on
   scroll-up. Nothing is ever blanked.
2. **FAQ (item 2).** Score every question on buying-decision value, merge the duplicate
   clusters, cut to about six. Prune the orphaned keys from all 13 locales.
3. **Ask Assistant (item 9).** Build it this round at zero API spend, by deep-linking the
   question into the user's own AI provider account. Ship Claude and ChatGPT behind an
   abstraction that takes more providers later.
4. **Delivery.** Clean worktree, everything uncommitted, operator runs `/pr-babysit` at the
   end.

**Open, each with a RECOMMENDED default that executes if unanswered:**

5. **The player cap at 1440 (item 8).** Plain `min(960px, 80%)` gives a good 960px at 1920
   but **612px at 1440, narrower than the 688px paragraph above it** and narrower than
   today. RECOMMENDED: `min(960px, max(80%, var(--docs-prose)))`, so the player is never
   narrower than the text it illustrates. Alternative: tie it to the prose with
   `min(960px, calc(var(--docs-prose) * 1.4))`.
6. **How far to take the reference parity (item 9).** The `/tmp/aim.png` reference also has
   a nested collapsible TOC, a persistent question composer and a copy-page dropdown.
   RECOMMENDED: ship the category eyebrow, the grouped sidebar, What's next cards,
   `Ctrl/Cmd+K` and the inline language picker; leave the persistent composer out, since the
   Ask Assistant menu already covers that job without a floating element.
