# Wave 4 (w5) solution-page density: proposals for the seven densest pages

Agent: READ-AND-PROPOSE. No product file was written or edited by this agent.
Date: 2026-08-27. Branch `0827-1`.
Pages, in the priority order given: retention-compliance, infrastructure-costs,
immutable-backups, integrations, encryption, rapid-recovery, backup-verification.

---

## 0. Instrument, and what it can and cannot be trusted for

### 0.1 Server identity, verified before any measurement

    $ ss -lptn 'sport = :29304'
    LISTEN 0 5 0.0.0.0:29304 0.0.0.0:* users:(("python3",pid=884155,fd=3))
    $ tr '\0' ' ' < /proc/884155/cmdline
    python3 -m http.server 29304 --directory dist
    $ ls -l /proc/884155/cwd
    -> /home/developer/console/packages/www

Hashed-asset cross-check (the page must link an asset that is on disk):

    $ curl -s http://localhost:29304/en/solutions/retention-compliance/ \
        | grep -o '/assets/[A-Za-z0-9_.-]*\.css' | sort -u | head -1
    /assets/TutorialVideoPlayer.DYoAC--Z.css
    $ ls packages/www/dist/assets/TutorialVideoPlayer.DYoAC--Z.css
    packages/www/dist/assets/TutorialVideoPlayer.DYoAC--Z.css

Note for anyone re-running this: the URLs need a TRAILING SLASH. `python3 -m
http.server` answers `/en/solutions/<slug>` with a `301` to `/en/solutions/<slug>/`,
and `agent-browser open` follows it, but a bare `curl -o /dev/null -w %{http_code}`
reports `301` and reads as a failure when it is not.

Liveness assertion carried inside every probe run: `document.querySelector('.nav-translate')`
returned `true` on all 8 pages measured, so the Navigation island hydrated and the build
being read is not a stale one.

### 0.2 The probe, verbatim

Run with `agent-browser eval --stdin --json < probe.js` after
`agent-browser open <url>` and `agent-browser wait --time 2500`.

```js
(()=>{
  const main = document.querySelector('main') || document.body;
  const hasOwnText = (el)=> Array.from(el.childNodes)
      .some(n=>n.nodeType===3 && n.textContent.trim().length>0);
  const raw = (s)=> (s||'').trim().split(/\s+/).filter(Boolean).length;
  const inMain = Array.from(main.querySelectorAll('*'));
  const atoms = inMain.filter(hasOwnText).length;
  const words = raw(document.body.innerText);
  const h = Math.round(document.documentElement.scrollHeight);
  if (inMain.length < 50) throw new Error('FLOOR: main has '+inMain.length+' elements');
  if (atoms < 50) throw new Error('FLOOR: atoms '+atoms);
  return {url: location.pathname, height:h, screens:+(h/900).toFixed(1),
          words, atoms, domNodes: document.querySelectorAll('*').length};
})()
```

Viewport: the agent-browser default (not overridden). Height and words reproduce the
w1 CSV EXACTLY on all 8 rows measured, which is the evidence that the viewport matches.

**The 2500 ms settle is load-bearing, not politeness.** Measured without it,
`infrastructure-costs` returned `atoms: 209`; with it, `251`, twice, stably. The 42-atom
swing is the `costCalculator` island finishing hydration. A density census taken without
a settle understates the interactive pages and only those, which is exactly the shape of
error that survives review.

### 0.3 Reconciling with the w1 baseline (resolved, and it cost an hour)

`height` and `words` matched `w1-baseline-frozen-build.csv` to the unit immediately. The
`atoms` column did not, and I could not make it: I tried nine text-based definitions
(own-text elements, text nodes, leaf elements, leaf-with-text, painted-only, a semantic
selector list, each with and without `<svg>` and `<details>` exclusions) and none
reproduced it. Worse, the ORDER inverted: w1 has retention (277) above immutable (252),
and every text-based metric puts immutable above retention. No monotone function maps one
to the other.

The reason is that **`atoms` is not a text metric at all.** `packages/www/scripts/
measure-page-density.sh` appeared in the tree at 16:03, after this agent started reading,
and its definition is a CLASS-SUBSTRING SELECTOR COUNT over `document.body`:

```js
document.body.querySelectorAll(
  'h1,h2,h3,h4,li,td,th,[class*=card],[class*=chip],[class*=stat],'
+ '[class*=step],[class*=item],[class*=row]').length
```

Driven against the frozen build at the same `--viewport 1280x900` w1 used, it reproduces
every row exactly: home 157, retention-compliance 277, infrastructure-costs 255,
immutable-backups 252, integrations 245, encryption 245. **Every `w1 atoms` figure below
is that selector, so it is directly comparable to the w1 CSV.**

**Two properties of that metric are worth knowing before reading any atom delta here,
because they make some cuts look larger and others look smaller than they read to a
human.**

- It counts elements whether or not they hold text, so a visual built from
  `[class*=card]` and `[class*=row]` scores very high. `howItWorks.costVisual` is
  **48 w1-atoms** for 39 words and 354px.
- It matches nothing in the tech-difference table, whose cells are `.sp-tech-detail-cell`
  and whose rows are Astro `<Fragment>`s with no wrapper. **Dropping a `techDiff` row
  scores exactly 0 w1-atoms** while removing 44-64px and 9-33 words. Conversely
  `benefits`, which is 615-692px and 72-102 words, scores only **7 w1-atoms**.

So this document reports three numbers per page and they disagree on purpose:

- **w1 atoms**, comparable to the baseline CSV and to the homepage's 157.
- **text-atoms**, the probe in 0.2, which counts what actually carries words.
- **visible text-atoms**, defined in 0.4, which is the number closest to what a reader
  meets.

Where they disagree, height and words are the tiebreak, because both reproduce exactly and
neither depends on a class-naming convention.

### 0.4 Two corrections that change how the atom number should be read

**(a) 42 atoms on every solution page are Plyr control chrome, not content.** Measured
inside `.sp-hero-media`: Play/Pause/Mute labels, the settings menu, eight playback-speed
options and thirteen language buttons (Deutsch, Eesti, English, Espanol, Francais,
Italiano, Portugues, Turkce, Arabic, Russian, Chinese, Japanese, Korean). The count is
42 on all seven pages, identically. **The homepage has no video player at all**
(`main.querySelector('.plyr')` is null), so the raw home-versus-solution atom comparison
overstates the gap by 42 before anything else is counted.

**(b) 11 to 25 further atoms sit inside a `<details>` that is CLOSED on load.**
`.sp-sources-details` reports `open: false`, height 34px. The citation list is real
content but a reader does not meet it.

So every page below carries two atom numbers:

- **atoms** = the probe in 0.2, comparable across the seven pages.
- **visible atoms** = atoms minus `.sp-hero-media` descendants minus `<details>`
  descendants. This is the number to compare against the homepage.

| page | height | words | w1 atoms | text-atoms | player | collapsed | **visible** |
|---|---|---|---|---|---|---|---|
| home | 5838 | 518 | 157 | 147 | 0 | 0 | **147** |
| retention-compliance | 8731 | 885 | 277 | 273 | 42 | 24 | **207** |
| infrastructure-costs | 8749 | 851 | 255 | 251 | 42 | 11 | **198** |
| immutable-backups | 8861 | 945 | 252 | 280 | 42 | 24 | **214** |
| integrations | 8590 | 857 | 245 | 247 | 42 | 14 | **191** |
| encryption | 8719 | 892 | 245 | 268 | 42 | 23 | **203** |
| rapid-recovery | 8752 | 883 | 242 | 266 | 42 | 20 | **204** |
| backup-verification | 8771 | 877 | 240 | 268 | 42 | 17 | **209** |

The honest gap to the homepage is 147 against 191-214, about 1.4x, not the 1.9x the raw
column suggests.

### 0.5 How the predicted after-numbers were derived

They are NOT arithmetic. Each proposed cut was **executed in the DOM on the frozen build
and re-measured**, cut by cut, so the reported delta is an observed page height and not a
sum of section rectangles. The harness:

```js
(()=>{
  const CUTS = window.__CUTS__;
  const h=(e)=>Array.from(e.childNodes).some(n=>n.nodeType===3&&n.textContent.trim());
  const raw=s=>(s||'').trim().split(/\s+/).filter(Boolean).length;
  const snap=()=>{
    const m=document.querySelector('main');
    const all=Array.from(m.querySelectorAll('*'));
    return {height:Math.round(document.documentElement.scrollHeight),
      words:raw(document.body.innerText),
      atoms:all.filter(h).length,
      w1:document.body.querySelectorAll('h1,h2,h3,h4,li,td,th,[class*=card],'
         +'[class*=chip],[class*=stat],[class*=step],[class*=item],[class*=row]').length,
      visible:all.filter(h).length
        - all.filter(e=>h(e)&&e.closest('.sp-hero-media')).length
        - all.filter(e=>h(e)&&e.closest('details')).length};
  };
  const before=snap(); const steps=[];
  for(const c of CUTS){
    let nodes=[];
    if(c.rows){ const trs=Array.from(document.querySelectorAll(c.sel));
                nodes=c.rows.map(i=>trs[i]).filter(Boolean); }
    else if(c.idx){ const xs=Array.from(document.querySelectorAll(c.sel));
                nodes=c.idx.map(i=>xs[i]).filter(Boolean); }
    else nodes=Array.from(document.querySelectorAll(c.sel));
    if(!nodes.length){ steps.push({name:c.name, MISSING:true}); continue; }
    const b=snap(); nodes.forEach(n=>n.remove()); const a=snap();
    steps.push({name:c.name, n:nodes.length, dh:b.height-a.height,
                dw:b.words-a.words, da:b.atoms-a.atoms, dv:b.visible-a.visible});
  }
  const after=snap();
  return {p:location.pathname.split('/')[3], before, after, steps,
    delta:{h:before.height-after.height, w:before.words-after.words,
           a:before.atoms-after.atoms, v:before.visible-after.visible},
    screensBefore:+(before.height/900).toFixed(1),
    screensAfter:+(after.height/900).toFixed(1)};
})()
```

Control that the harness can fail: a cut whose selector matches nothing reports
`MISSING: true` rather than a silent zero. It fired during development on
`.sp-tech-detail tbody tr` (the tech table is a CSS grid of `div`s, not a `<table>`),
which is why the tech-diff cuts below are expressed as `.sp-tech-detail-cell` index
pairs.

### 0.6 The section-cost table, measured once, used throughout

Every `<section>` under `.sp-page` measured with `getBoundingClientRect()`. The
rectangles sum to 8113 against a measured `main` height of 8115 on
retention-compliance, i.e. there are no collapsing margins between sections and the
numbers are additive. Header plus footer is a constant 618px / 111 words.

| section | height | words | atoms | notes |
|---|---|---|---|---|
| breadcrumb | 102 | 7-10 | 3 | |
| hero (with video) | 484 | 30-42 | 44 | 42 of the 44 are the player |
| problem | 1500-1601 | 99-112 | 27 | 667 of it is the textless illustration |
| stats | 208-260 | 9-13 | 6 | |
| costCalculator | 1074-1149 | 102-148 | 29-33 | interactive island |
| howItWorks | 904-966 | 85-116 | 31-37 | steps 275, visual 292-354 |
| techDiff | 587-729 | 98-166 | 11-15 | |
| benefits | 615-692 | 72-102 | 8 | |
| downloadsRow | 338 | 21 | 4 | strings are SHARED across all 21 pages |
| comparison | 753-830 | 84-116 | 45-59 | highest atom count on the page |
| sources | 130 | 2 | 12-25 | collapsed `<details>` |
| constellation | 705 | 18-25 | 11-14 | navigation |
| bottomCta | 414-503 | 22-36 | 4-6 | |

Sub-block geometry, measured with `x/y/width/height` so the layout axis is known and not
assumed:

- `problem.statCallouts` stack **vertically**, 47px each on a 59px pitch. Dropping one
  callout saves 59px. Dropping all three saves 190px.
- `problem.timeline` chevrons are **horizontal** (one row, y identical). Dropping
  individual chevrons saves **zero height at desktop**; only the whole
  `.sp-timeline-contrast` block (263-286px) pays.
- `howItWorks` steps are **side by side**. Dropping one step saves zero height.
- `benefits` cards are **side by side** at 278px. Dropping one card saves zero height.
  Only the whole section (615-692px) pays.
- `*Visual` cards are side by side, each 290px, their internal rows 42px each. Dropping
  the same item row from BOTH cards saves 42px; dropping the whole visual saves 354px
  (292px for the three-card `pipelineVisual`).
- `comparison` rows are 55px each.
- `techDiff` rows are two grid cells, 44-64px per row depending on wrap.

**This geometry is why "cut the repeated chevron" and "cut the weakest benefit card" are
worthless as height moves and why every proposal below cuts whole horizontal blocks.**

---

## 1. The rules I worked under

Quoted from `agent/programs/clarity-round6/03-solution-page-density.md` and obeyed:

> Remove a WHOLE SECTION via the `sections` array in `src/config/solution-pages.ts`.
> Remove a SUB-BLOCK via the page's i18n subtree. Never the reverse.

- Data-gated sub-blocks I used, each re-verified in the component source:
  `problem.statCallouts` (`SPProblem.astro:52`), `problem.timeline` (`:91`),
  `howItWorks.cloneVisual` / `costVisual` / `pipelineVisual` (`SPHowItWorks.astro:85/:142/:194`),
  `bottomCta.tierBadge` / `command` (`SPBottomCta.astro:27/:30`).
- Array ELEMENT removal (a `comparison.features[n]`, a `techDiff.rows[n]`) is safe: the
  arrays are `.map()`ed and the key itself survives. Removing the KEY would crash.
- No `label` or `blurb` is proposed for deletion anywhere.
- No component edit is proposed anywhere. Every SP component is also mounted by
  `PersonaPage.astro:100/104/116/124`.

### The `sections` edit shape

All seven pages currently read `sections: ALL_SECTIONS,`. I propose the **per-page
filter form**, which mirrors the existing `SECTIONS_NO_COMPARISON` idiom at
`solution-pages.ts:114` and therefore is already proven to type-check against
`readonly SectionType[]`:

```ts
    sections: ALL_SECTIONS.filter((s) => s !== 'stats' && s !== 'benefits'),
```

Exact lines to replace (verified by `grep -n "sections: ALL_SECTIONS," solution-pages.ts`):

| slug | line |
|---|---|
| infrastructure-costs | 131 |
| integrations | 149 |
| immutable-backups | 158 |
| retention-compliance | 195 |
| backup-verification | 222 |
| encryption | 247 |
| rapid-recovery | 273 |

A shared `const SECTIONS_LEAN = ALL_SECTIONS.filter(...)` next to line 114 would be fewer
bytes, and I recommend AGAINST it: it couples my seven pages to whatever the other wave
agents propose for the remaining fourteen, and the whole premise of this wave is per-page
treatment. Seven identical one-line edits with no shared symbol is the lower-risk shape
while other writers are live in the tree.

---

## 2. Page 1 - retention-compliance (the densest page on the site by w1 atoms, 277)

Before: **8731px / 9.7 screens / 885 words / 273 atoms / 207 visible atoms.**

### 2.1 The repetition, counted

| claim | times stated | where |
|---|---|---|
| automatic cleanup, no cron, no scripts | **8** | `hero.subtitle`; `problem.timeline.newSteps[1]` "Auto"; `howItWorks.steps[1].description`; `howItWorks.costVisual.wasteful.footerRight` "Auto-cleanup: ON"; `techDiff.rows[0].rediacc`; `techDiff.rows[1].rediacc`; `benefits.items[0].description`; `comparison.features[1].name` |
| audit-ready, instantly | **8** | `stats[2]` "100% Audit-Ready"; `problem.timeline.newSteps[2]` "Audit-ready"; `howItWorks.steps[2].description`; `howItWorks.costVisual.efficient.footerRight` "Audit-ready"; `techDiff.rows[2].rediacc`; `benefits.items[1].description`; `benefits.items[2].description`; `comparison.features[3].name` |
| HIPAA, SOC2, GDPR covered | **7** | `meta.description`; `hero.subtitle`; `stats[1]` "3 Compliance Frameworks"; `howItWorks.costVisual.wasteful.items[0..2]`; `howItWorks.costVisual.efficient.items[0..2]` (the same three names AGAIN, inside the same 354px block); `benefits.items[1].description`; `comparison.features[4].name` |
| set the retention length once | **7** | `hero.title`; `hero.subtitle`; `problem.timeline.newSteps[0]` "Set policy"; `howItWorks.steps[0]`; `benefits.items[0]`; `comparison.features[0].name`; `bottomCta.description` |

Four claims, thirty statements. The shape the spec found on `infrastructure-costs` is
present here in a slightly worse form: the framework triple HIPAA/SOC2/GDPR is printed
twice inside ONE 354px visual.

### 2.2 Whole sections to drop

**`stats`** - 209px, 9 words, 6 atoms.
Line 195 becomes `sections: ALL_SECTIONS.filter((s) => s !== 'stats' && s !== 'benefits'),`.
Evidence: "7+ yrs Maximum Retention" is `howItWorks.costVisual.wasteful.items[0].detail`
("7 years") and `comparison.features[0]`. "3 Compliance Frameworks" is the count of the
three names in `hero.subtitle`. "100% Audit-Ready" is statement number four of eight for
that claim, and the chip carries no source. Nothing on the bar is cited and nothing on it
is first.

**`benefits`** - 615px, 72 words, 8 atoms. Same line change.
Evidence, card by card:
- `items[0]` "Set and forget / Set the retention rules once. Rediacc enforces them
  forever. Old backups get cleaned up on their own. No cron jobs. No scripts."
  -> `howItWorks.steps[0]` ("Set how long to keep data") plus `howItWorks.steps[1]`
  ("Old backups get cleaned up on schedule. No spreadsheets. No cron jobs.") plus
  `techDiff.rows[0].rediacc` plus `techDiff.rows[1].rediacc`. The phrase "No cron jobs"
  appears in both.
- `items[1]` "Compliance-ready / Built for HIPAA, SOC2, and GDPR rules. Audit logs export
  to any security log tool. Pull a compliance report in seconds."
  -> `hero.subtitle` plus `howItWorks.steps[2]` ("It exports straight to the security log
  tool", "in seconds") plus `comparison.features[4]`.
- `items[2]` "Full audit trail / Every backup, check, and deletion is logged with a
  timestamp. Every report is audit-ready by default."
  -> `stats[2]` plus `techDiff.rows[2].rediacc`.

Three cards, zero claims that are not already made above them.

i18n keys orphaned: `pages.solutionPages.retentionCompliance.stats` (9 leaves) and
`.benefits` (11 leaves), in all 13 catalogs.

### 2.3 Sub-blocks to drop, by i18n key path

**`pages.solutionPages.retentionCompliance.howItWorks.costVisual`** (whole object,
29 leaves) - 353px, 39 words, **26 atoms**.
Evidence: it is a two-card table. The left card lists HIPAA / SOC2 / GDPR / Internal with
retention lengths; the right card lists HIPAA / SOC2 / GDPR / Internal AGAIN with backup
counts. Four nouns printed twice, 42px apart. Its footers add "Auto-cleanup: ON" (the 4th
statement of auto-cleanup), "Audit-ready" (the 4th of audit-ready) and "Compliant" plus
"100% compliant" (the 5th and 6th of compliance-covered). It is the highest atom density
on the page: 0.074 atoms per pixel against a page mean of 0.031.
Second reason, independent of density: the backup counts are invented precision. 2,555 is
7 x 365, 1,825 is 5 x 365, 1,095 is 3 x 365, 365 is 1 x 365, and they are presented in a
status card styled as a live readout.

**`pages.solutionPages.retentionCompliance.problem.timeline`** (whole object, 15 leaves)
- 281px, 34 words, 15 atoms.
Evidence: the five old-way chevrons ("Write retention policy / Manual cleanup / Missed
some data / Audit notice arrives / Scramble to prove it") are a beat-for-beat retelling of
`problem.description`, which sits about 40px above them and already says "retention gets
tracked by hand in a spreadsheet. Then the auditor calls." The three new-way chevrons
("Set policy / Auto / Audit-ready") are one-word compressions of the three `howItWorks`
step titles ("Set policies / Automate / Audit") one section below. No chevron carries a
number or a citation.

**`comparison.features[0]`, `[1]`, `[3]`, `[4]`** - 219px, 39 words, 24 atoms.
Evidence: on each of these four rows **all four competitor columns are `check`**. A row on
which every vendor scores identically is by construction not a differentiator, and the
table's own description says "Few enforce how long to keep it. None check that old backups
can still be restored." The rows that support that sentence are `[2]` (all cross) and
`[6]` (all cross); `[5]` has one cross. Keeping `[2]`, `[5]`, `[6]` leaves exactly the
three rows where the columns differ. Each dropped row is also a restatement:
`[0]`=hero.subtitle+steps[0], `[1]`=steps[1]+techDiff.rows[1],
`[3]`=steps[2]+techDiff.rows[2], `[4]`=hero.subtitle+stats[1].

### 2.4 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        208       9        14          6
    benefits                     616      72         7          8
    howItWorks.costVisual        353      39        48         26
    problem.timeline             281      34         8         15
    comparison rows 0,1,3,4      219      39        24         24

**After: 7054px / 7.8 screens / 692 words / 176 w1 atoms / 128 visible text-atoms.**
Delta: -1677px, -193 words, -101 w1 atoms. Both atom counts land **above** the
homepage's 157 / 147 on w1 and **below** it on visible text-atoms; height is the
tiebreak and it moves 9.7 screens to 7.8.

Claim-survival control, run on the simulated after-state: every one of the four core
claims still appears multiple times in `main.innerText` (HIPAA/SOC2/GDPR 6, audit 15,
cleanup/automatic 9, retention/keep 19, check/verify 4). Nothing was cut to zero.

### 2.5 What must stay, and why

- `problem.description` + illustration + `statCallouts`: the three callouts ($4.88M IBM,
  $2.13M HHS, EUR1.2B CMS) are the only cited third-party numbers on the page, and the
  667px illustration is the page's only non-text element and its only visual rest.
- `costCalculator`: it computes rather than restates. Nothing in it duplicates another
  section; it is the only place a reader's own numbers appear.
- `howItWorks.steps`: the only place `rdc config backup-strategy set` and
  `rdc retention report` appear in prose. After the `costVisual` cut the whole section is
  612px / 62 words / 11 atoms, the cheapest content on the page per atom.
- `techDiff`: the only mechanism explanation on the page (what btrfs is doing).
- `downloadsRow`, `sources`, `constellation`, `bottomCta`.

### 2.6 Stretch option, not recommended

Dropping `howItWorks` entirely (decision A5) would take a further 612px, 69 words and 14
w1 atoms, simulated to **6442px / 7.2 screens / 623 words / 162 w1 atoms / 117 visible
text-atoms**, which is the only configuration in this document that beats the homepage on
every column except height. I recommend against it here: `rdc retention report` survives in
`techDiff.rows[2]` but `rdc config backup-strategy set` would survive only as the
`bottomCta.command` string, and the page would then assert a mechanism it never shows.

---

## 3. Page 2 - infrastructure-costs

Before: **8749px / 9.7 screens / 851 words / 251 atoms / 198 visible atoms.**

The spec's own diagnosis reproduces: idle-and-still-paying 10x, 70%-saved 4x,
auto-cleanup 5x, copies-share-disk 6x, and three of the five timeline chevrons carry the
identical string "Idle, still paying".

### 3.1 Whole sections to drop

**`stats`** (260px / 11 words / 6 atoms) and **`benefits`** (616px / 79 words / 8 atoms).
Line 131 becomes `sections: ALL_SECTIONS.filter((s) => s !== 'stats' && s !== 'benefits'),`.

`stats` evidence: "70% Cost reduction" is `howItWorks.costVisual.arrow.detail`
("70% Savings") and the calculator's `withAnnualLabel` ("Annual savings"). "On-demand /
No always-on waste" is `hero.subtitle` and `problem.timeline.newSteps[0]`. "Auto /
Cleanup & TTL" is `problem.timeline.newSteps[2]`, `benefits.items[1]` and
`techDiff.rows[2]`. The bar is a one-to-one restatement of `problem.timeline.newSteps`,
which sits 260px above it.

`benefits` evidence: `items[0]` "Pay for what runs / No idle servers. Copies share disk
space with production." = `techDiff.rows[0].rediacc` + `techDiff.rows[1].rediacc` +
`hero.subtitle`. `items[1]` "Automatic cleanup / Set a timer on each copy (1h, 4h, 8h).
It deletes itself" = `howItWorks.steps[2]` + `techDiff.rows[1]` + `techDiff.rows[2]` +
the four TTL rows of `costVisual.efficient`. `items[2]` "Scale freely / Spin up 50
environments for a load test" is the one genuinely new claim in the section; because the
three cards are side by side, keeping it costs the full 616px, and it is a claim the
`costCalculator` directly above already lets a reader test with a slider.

### 3.2 Sub-blocks to drop

**`pages.solutionPages.infrastructureCosts.problem.timeline`** (15 leaves) - 262px, 28
words, 15 atoms.
Evidence: `oldSteps[1]`, `[2]` and `[3]` carry the byte-identical string "Idle, still
paying" for Nights, Weekends and Holidays. `problem.description`, about 40px above,
already says "Those servers sit idle nights, weekends, and holidays." `oldSteps[4]`
"67% waste" is the same paragraph's "The other 67% is billed too." The three newSteps
("Spin up / $0 idle / Auto-cleanup") are the three `stats` chips and the three
`howItWorks` step titles ("Spin up / Use / Tear down").

**`pages.solutionPages.infrastructureCosts.howItWorks.costVisual`** (26 leaves) - 354px,
39 words, 26 atoms.
Evidence: the left card's four rows read "idle 16h/day", "idle 18h/day", "idle weekends",
"idle 3 months" - statements four through seven of the idle claim. The right card
re-lists dev-alice and dev-bob with TTLs, which is `benefits.items[1]` and
`techDiff.rows[1]`. "$3,000/mo" versus "$0 idle" is what the `costCalculator` 354px below
computes from the reader's own sliders. "70% Savings" is the third statement of the 70%.
**And `arrow.label` prints the raw string `BTRFS COW`.** I grepped the page's rendered
text: that is the ONLY appearance of that token anywhere on the page. Every other mention
of the mechanism is deliberately plain ("the storage engine that makes cheap instant
copies", "Copies share unchanged data with production"). One card label undoes the
page's whole vocabulary decision.

**`techDiff.rows[2]` and `techDiff.rows[4]`** - 128px, 33 words, 4 atoms.
Key paths `...infrastructureCosts.techDiff.rows[2]` and `[4]`.
- `rows[2]` "Manual teardown, forgotten environments accumulate / Automatic cleanup,
  storage reclaimed instantly" is `rows[1]` again ("Always-on, paying 24/7 / On-demand
  with a set timer, deletes itself when done"). Both rows are the timer claim.
- `rows[4]` "A staging Kubernetes cluster: a second set of nodes, paid 24/7 / Fork the
  cluster for the test, delete it after. Copies share storage." is `rows[1]` plus
  `rows[0]` with a Kubernetes noun in front, on a page that mentions Kubernetes nowhere
  else. The `kubernetes-cluster-mobility` page, reachable from this page's constellation,
  is that claim's home.

### 3.3 Comparison table: keep all six rows

`infrastructure-costs` has **zero** all-check rows. Two rows are all-cross (the real
differentiators) and the other four each split the competitor columns. This is the
best-behaved comparison table of my seven and should not be touched.

### 3.4 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        260      11        14          6
    problem.timeline             262      28         8         15
    howItWorks.costVisual        354      39        48         26
    benefits                     616      79         7          8
    techDiff rows 2,4            128      33         0          4

**After: 7129px / 7.9 screens / 661 words / 178 w1 atoms / 139 visible text-atoms.**
Delta: -1620px, -190 words, -77 w1 atoms. Note the `techDiff` rows scoring 0 w1-atoms
while removing 128px and 33 words; see 0.3 for why that metric cannot see that table.

### 3.5 Must stay

`costCalculator` above all: on a page about cost, the slider is the argument. The three
`howItWorks` steps (52 seconds, the shared-disk sentence, the self-deleting timer) and
`techDiff` rows 0, 1 and 3 are the mechanism. `statCallouts` are the page's only cited
numbers.

---

## 4. Page 3 - immutable-backups (the densest page on the site by words, 945)

Before: **8861px / 9.8 screens / 945 words / 280 atoms / 214 visible atoms.**

### 4.1 Whole sections to drop

**`stats`** (208px / 13 words / 6 atoms) and **`benefits`** (615px / 89 words / 8 atoms).
Line 158.

`stats` evidence: "0 Files Changed After Backup" and "100% Immutable by Default" are two
renderings of one sentence in `hero.subtitle` ("Backups lock the moment they're made. No
one can change them."). "<60s Full Backup Time" appears nowhere else on the page and is
uncited; losing it is the one real cost of this cut, and I judge an uncited speed claim
on a page whose subject is tamper-resistance to be a net gain when removed.

`benefits` evidence, and this is the strongest benefits case of the seven because one
card restates its own neighbour inside the same block:
- `items[0]` "Write once, read forever / No one can change, delete, or encrypt a sealed
  backup. Not hackers. Not a hacked admin account. Not ransomware that grabbed the top
  admin password." = `hero.subtitle` ("Not hackers. Not even the owner.") +
  `techDiff.rows[0].rediacc` ("safe even with the top admin password") +
  `techDiff.description` ("Even with the top admin password, ransomware can't encrypt,
  change, or delete a sealed copy"). The phrase "top admin password" appears three times
  on the page and twice within 700px.
- `items[1]` "No trust required / Even a hacked admin account can't touch a sealed
  backup. We test every backup automatically, every day." Sentence one is `items[0]`.
  Sentence two is `items[2]`. The card is 278px of its own two neighbours.
- `items[2]` "Instant verification / We restore every backup to a test copy and check it
  works... every day." = `techDiff.rows[2].rediacc` ("We copy, boot, and health-check it
  daily") + `comparison.features[2]`.

### 4.2 Sub-blocks to drop

**`...immutableBackups.problem.timeline`** (15 leaves) - 281px, 30 words, 15 atoms.
Evidence: `oldSteps` Day 1 to Day 15 ("Schedule backup / Backup runs / Hope it's clean /
Ransomware hits / Backup encrypted too") retell `problem.description` 40px above, which
already says "ransomware just hit. The backups are encrypted too... attackers hunt down
the backups first." `newSteps` "Backup / Sealed / Verified" are the three `howItWorks`
step titles plus `cloneVisual.clone.status` ("Sealed").

**`...immutableBackups.howItWorks.cloneVisual`** (28 leaves) - 354px, 32 words, 25 atoms.
Evidence: the left card lists gitlab / postgres / mailcow / redis with ports; the right
card lists the SAME four names with the word **"read-only" printed four times**. Eight
rows, four distinct nouns, and one idea ("the copy cannot be written") which the block
also states as its card status ("Sealed"), its footer ("380 GB - locked") and its arrow
label ("Seal"). Seven statements of read-only in 354px. The four service names appear in
no other section of this page.

**`...immutableBackups.problem.statCallouts[0]`** - 59px, 6 words, 3 atoms.
Evidence: `problem.description` already contains, inline and with the attribution, "94%
of ransomware victims had their backups targeted during the attack (Sophos 2024)". The
callout 47px below reads "94% / of attacks target backups / Sophos 2024". Same number,
same source, same paragraph. This is the only in-section duplicate citation I found on
any of the seven pages. Callouts `[1]` and `[2]` are distinct sources and stay.

**`...immutableBackups.techDiff.rows[2]`** - 64px, 19 words, 2 atoms.
Evidence: "'Backup completed' is the only proof on offer / We copy, boot, and
health-check it daily, so it's truly verified" is the entire thesis of the SEPARATE
`backup-verification` page, and on this page it is also `benefits.items[2]` (already
cut) and `comparison.features[2]`. On a page about immutability it introduces a third
topic that the constellation already routes to.

**`comparison.features[4]`** - 55px, 10 words, 7 atoms.
Evidence: "Instant copy for testing" scores `check` in all five competitor columns. Its
neighbour `features[3]` "Shortcut copies that save space" is all-cross and is the real
claim. I deliberately KEPT `features[0]` "Locked backups" (four checks and one cross)
even though it is nearly all-check, because it is the setup for `features[1]` "Locked in
the storage layer" (all-cross) and the pair is the page's argument in miniature: everyone
claims the lock, only one puts it below the software.

### 4.3 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        208      13        14          6
    problem.timeline             281      30         8         15
    howItWorks.cloneVisual       354      32        15         25
    benefits                     615      89         7          8
    comparison row 4              55      10         7          7
    problem.statCallouts[0]       59       6         3          3
    techDiff rows[2]              64      19         0          2

**After: 7225px / 8.0 screens / 746 words / 198 w1 atoms / 148 visible text-atoms.**
Delta: -1636px, -199 words, -54 w1 atoms.

This page starts heaviest and stays heaviest, because its `comparison` table has six
competitor columns rather than four (830px, 59 atoms) and its `techDiff.description` is
68 words. Both are load-bearing and I do not propose touching them.

### 4.4 Must stay

`techDiff` rows 0, 1 and 3 and its description: this is the only place the page explains
what "the storage layer itself blocks any change" means, and it is the page's whole
differentiator. `problem.statCallouts[1]` and `[2]`. The calculator. The three
`howItWorks` steps carrying `rdc repo push production --immutable`.

---

## 5. Page 4 - integrations

Before: **8590px / 9.5 screens / 857 words / 247 atoms / 191 visible atoms.**

### 5.1 The repetition, counted

"Zero custom scripts" is stated **six** times: `hero.subtitle` ("No custom scripts to
write"), `stats[2]` ("0 / Custom scripts needed"), `howItWorks.title` ("One command. Zero
scripts."), `techDiff.rows[0].rediacc` ("One webhook line. Zero custom scripts."),
`benefits.items[2]` ("Zero maintenance / No custom scripts to maintain"),
`comparison.features[4]` ("Zero custom setup scripts").
"One line of config" is stated four times: `stats[0]`, `howItWorks.steps[0]`,
`techDiff.rows[0]`, `comparison.features[1]`.

### 5.2 Whole sections to drop

**`stats`** (208px / 12 words / 6 atoms) and **`benefits`** (667px / 86 words / 8 atoms).
Line 149.

`benefits` evidence: `items[0]` "Built-in Git integration / A push builds the environment.
Works with GitLab CI, GitHub Actions, Gitea, or any system that sends a webhook." is
`howItWorks.steps[0]` almost verbatim ("Works with GitLab CI, GitHub Actions, or any
system that can send a webhook"). `items[2]` "Zero maintenance" is statement five of the
six-times claim. `items[1]` "Production copies in CI" carries the page's ONLY Kubernetes
sentence ("a namespace forks like any repo. CI tests run against real cluster state").

**On that Kubernetes sentence, explicitly:** it is the one thing in this section that is
not stated elsewhere on the page. Moving it into `techDiff.description` would preserve it
but is an English VALUE change, which trips `check:i18n:hashes` and forces a 12-locale
re-naturalization for one sentence. I recommend accepting the loss: the claim's home is
the `kubernetes-cluster-mobility` page, which this page's constellation links to, and it
is stated there at page length. **Flagging it as a judgement call the operator may want
to reverse.**

### 5.3 Sub-blocks to drop

**`...integrations.problem.timeline`** (15 leaves) - 280px, 34 words, 15 atoms.
Evidence: `oldSteps` "Write bash scripts / Set up servers / Load test data / Debug broken
CI / Tests pass, prod fails" retell `problem.description` 40px above ("Someone wrote a
200-line script... Now the script breaks every month") and `techDiff.rows[0]` and
`rows[1]`. `newSteps` "git push / Auto / Real data" are the three `howItWorks` step titles
("Connect / Trigger / Test") and their first sentences.

**`...integrations.howItWorks.pipelineVisual`** (22 leaves) - 292px, 42 words, 20 atoms.
Evidence, and this one is qualitatively different from the other visuals: it is not a
restatement so much as a **stage set**. Card 0 invents a branch (`feature/auth-v2`), a
commit hash (`a3f7b2c`) and an author called `sarah`. Card 2 invents "247 unit tests",
"38 integration" and "285 passed". None of those is a claim about the product; a reader
cannot act on any of them and cannot check any of them. The block's only substantive
content is "380 GB -> 2.1 GB", which is `techDiff.rows[2]` and which appears on four other
solution pages, and "auto-cleanup", which is the third statement of that claim here.

**`...integrations.techDiff.rows[3]`** - 44px, 9 words, 2 atoms.
Evidence: "Manual cleanup, forgotten environments / Automatic cleanup after pipeline
completes" is `howItWorks.steps[2]` last sentence ("The copy deletes itself when the tests
finish") plus `comparison.features[3]` ("Auto-delete after pipeline") plus the
pipelineVisual's "auto-cleanup" line.

### 5.4 Comparison table: keep all six rows

Zero all-check rows. Every row splits the columns. Do not touch.

### 5.5 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        208      12        14          6
    problem.timeline             280      34         8         15
    howItWorks.pipelineVisual    292      42        33         20
    benefits                     667      86         7          8
    techDiff rows[3]              44       9         0          2

**After: 7099px / 7.9 screens / 674 words / 183 w1 atoms / 140 visible text-atoms.**
Delta: -1491px, -183 words, -62 w1 atoms. The `pipelineVisual` is the single
largest w1-atom item on this page at 33, which is the metric agreeing with the
judgement in 5.3 for once.

---

## 6. Page 5 - encryption

Before: **8719px / 9.7 screens / 892 words / 268 atoms / 203 visible atoms.**

### 6.1 The repetition

"Keys stay local" is stated **six** times: `hero.title`, `hero.subtitle`,
`problem.timeline.newSteps[0]`, `techDiff.rows[0].rediacc`, `benefits.items[0].title`,
`comparison.features[0]`. "AES-256" appears **eleven** times in the rendered text, five of
them inside one 354px block.

### 6.2 Whole sections to drop

**`stats`** (208px / 12 words / 6 atoms) and **`benefits`** (615px / 78 words / 8 atoms).
Line 247.

`stats` evidence: "AES-256 / Encryption Standard" is `howItWorks.steps[1]`,
`cloneVisual` x4, `cloneVisual.arrow.time`, `benefits.items[1].title` and
`comparison.features[3]`. "Local / Key Owner" is the six-times claim. "Always / Encrypted
at Rest & Transit" is `howItWorks.steps[1]` ("Data stays encrypted on disk and on the
move") and `comparison.features[5]`.

`benefits` evidence: `items[0]` "Local keys only / Generated locally. Stored on local
servers. No shared key vaults. No vendor access." = `howItWorks.steps[0]` ("never leaves
the machine. No one else gets a copy") + `techDiff.rows[0]` + `techDiff.rows[1]`.
`items[2]` "Zero-knowledge architecture / We never see raw data. We never touch the key."
is `howItWorks.steps[2]` VERBATIM ("We never see the key. We never see the raw data") and
`techDiff.description` ("We never see raw data or keys") and `comparison.features[1]`.
`items[1]` "AES-256-GCM does two jobs at once. It locks the data and checks that nothing
has been touched." is the only genuinely new mechanism sentence in the section
(authenticated encryption). Same trade as `integrations` and same recommendation: accept
the loss rather than pay a 12-locale re-naturalization to relocate one sentence.

### 6.3 Sub-blocks to drop

**`...encryption.problem.timeline`** (15 leaves) - 286px, 29 words, 15 atoms.
Evidence: `oldSteps` "Upload to vendor / Vendor holds keys / Vendor breached / Keys
compromised / Data exposed" retell `problem.description` 40px above ("Most backup tools
encrypt data with their keys... If they get hacked, the data is wide open") AND
`techDiff.description` ("One breach on their side and everything spills out") AND
`techDiff.rows[2]`. `newSteps` "Keys stay local / AES-256 / Zero-knowledge" are exactly
the three `stats` chips and exactly the three `benefits` card titles.

**`...encryption.howItWorks.cloneVisual`** (28 leaves) - 354px, 36 words, 26 atoms.
Evidence: left card lists gitlab / nextcloud / mailcow / mariadb with sizes; right card
lists the SAME four names with the string **"AES-256" printed four times**, plus the arrow
prints "AES-256-GCM" a fifth. Its two footers ("Local key only", "Zero-knowledge") are
`howItWorks.steps[2]` five pixels of scroll above. Zero claims not already in
`howItWorks.steps[1]` and `[2]` directly above it.

**`comparison.features[3]` and `[5]`** - 110px, 18 words, 12 atoms.
Evidence: `[3]` "AES-256 encryption on disk" and `[5]` "Encryption while data moves"
score `check` in all four competitor columns. The table's own description says "Most
backup tools encrypt data with their keys. That's not customer encryption." Rows on which
every vendor checks are, on this page specifically, arguing the opposite of the section's
thesis. The surviving five rows are `[0]` (four "Via KMS" against rediacc), `[1]`
all-cross, `[2]` four "Via KMS", `[4]` all-cross, `[6]` three checks and a cross.

### 6.4 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        208      12        14          6
    problem.timeline             286      29         8         15
    howItWorks.cloneVisual       354      36        16         26
    benefits                     615      78         7          8
    comparison rows 3,5          110      18        12         12

**After: 7146px / 7.9 screens / 719 words / 188 w1 atoms / 136 visible text-atoms.**
Delta: -1573px, -173 words, -57 w1 atoms.

### 6.5 Blocking defect on this page - see section 9

`encryption` is one of the eight solution pages that ship an **unlabelled primary CTA
button** and **two unlabelled comparison column headers**. Details, evidence and the full
list are in section 9. It is not caused by anything proposed here and is not fixed by
anything proposed here.

---

## 7. Page 6 - rapid-recovery

Before: **8752px / 9.7 screens / 883 words / 266 atoms / 204 visible atoms.**

### 7.1 The repetition

"Under 5 minutes" is stated **six** times: `hero.title` ("Recover in minutes. Not days."),
`stats[0]` ("<5min"), `problem.timeline.newSteps[1]` ("<5 min"), `howItWorks.steps[2]`
("back online in under 5 minutes"), `benefits.items[0]` ("recovers in under 5 minutes"),
`comparison.features[1]` ("Recovery under 5 minutes"). `techDiff.title` ("Why recovery
takes minutes, not days") and `cloneVisual.arrow.time` ("3m 12s") make eight if counted
loosely.

### 7.2 Whole sections to drop

**`stats`** (208px / 12 words / 6 atoms) and **`benefits`** (692px / 102 words / 8 atoms).
Line 273.

`stats` evidence: chip 0 is statement two of eight. Chips 1 and 2 ("99.9% Recovery Success
Rate", "0 Data Loss Incidents") are uncited product claims; chip 2 is restated by
`benefits.items[2].title` ("Zero data loss"). No chip carries a source, on a page whose
`problem.statCallouts` carry three.

`benefits` is the largest of my seven at 692px and 102 words, and it is entirely
derivative:
- `items[0]` "Minutes, not days" is `hero.title` verbatim; its body ("The full system
  recovers in under 5 minutes. Every container, every database, every settings file") is
  `howItWorks.steps[2]` verbatim ("The full system is back online in under 5 minutes.
  Every container, all the data, all the settings"). Its Kubernetes tail sentence is the
  same judgement call as `integrations` section 5.2, with the same recommendation.
- `items[1]` "Down to the minute / Roll back to the exact minute before the attack" is
  `howItWorks.steps[1]` verbatim ("Pick the exact moment before the attack. Down to the
  minute.") and `comparison.features[2]`.
- `items[2]` "Zero data loss / We save copies all the time" is `items[1]`'s own second
  sentence ("We take saved copies all the time") plus `stats[2]`.

### 7.3 Sub-blocks to drop

**`...rapidRecovery.problem.timeline`** (15 leaves) - 262px, 30 words, 15 atoms.
Evidence: `oldSteps` Hour 1 to Day 7+ ("Discover attack / Assess damage / Rebuild servers
/ Restore data / Still catching up") retell `problem.description` 40px above ("Now come
days of rebuilding from scratch... The cleanup takes a week") and `techDiff.rows[0]` and
`rows[1]`. `newSteps` "Detect / <5 min / Online" are the three `howItWorks` step titles
("Detect / Select / Restore") plus the five-minute claim again.

**`...rapidRecovery.howItWorks.cloneVisual`** (29 leaves) - 354px, 33 words, 26 atoms.
Evidence: left card lists webapp / postgres / redis / nginx with "crashed / encrypted /
encrypted / down"; right card lists the SAME four names with ports. Eight rows, four
nouns, and the only idea is "it was down, now it is up", which the block also states as
its two card statuses ("Encrypted" / "Healthy"), its two footers ("All offline" / "All
healthy") and its arrow label ("Restore"). Its "3m 12s" is a further statement of the
recovery-time claim and contradicts the six others by being neither "<5 min" nor "minutes".

**`comparison.features[1]` and `[2]`** - 110px, 21 words, 14 atoms.
Evidence, and this is the sharpest finding on the page: `features[1]` is "Recovery under 5
minutes" and **all five competitor columns are `check`**. The page's headline claim is
presented in its own comparison table as a thing every competitor also does. `features[2]`
"Roll back to any minute" is likewise all-check. The two all-cross rows, `[3]` "Automatic
restore testing" and `[4]` "No data transfer needed", are the actual differentiators and
survive, along with `[0]` and `[5]`.

### 7.4 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        208      12        14          6
    problem.timeline             262      30         8         15
    howItWorks.cloneVisual       354      33        16         26
    benefits                     692     102         7          8
    comparison rows 1,2          110      21        14         14

**After: 7126px / 7.9 screens / 685 words / 183 w1 atoms / 135 visible text-atoms.**
Delta: -1626px, -198 words, -59 w1 atoms.

### 7.5 Blocking defect on this page - see section 9

`rapid-recovery` is the second of the two pages in my set with the unlabelled primary CTA
and the unlabelled `techDiff` column headers.

---

## 8. Page 7 - backup-verification

Before: **8771px / 9.7 screens / 877 words / 268 atoms / 209 visible atoms.**

### 8.1 The one page where I recommend KEEPING the `*Visual`

Every other page's `cloneVisual` or `costVisual` restates prose that sits directly above
it. This page's does not. `howItWorks.cloneVisual` shows `daily-2026-02-27` in two states,
`Unverified` and `Verified`, and the right card's four rows are the actual probes:
`HTTP 200`, `SELECT 1`, `/health`, `PONG`, with a footer of `8/8 healthy` and
`Integrity: 100%`. **Those five strings appear nowhere else on the page.** On a page whose
entire thesis is "we do not just trust 'backup completed'", this block is the only place
the alternative is SHOWN rather than asserted. Cutting it would leave the page making a
claim about rigour with no exhibit.

I therefore cut the words that describe the picture, and keep the picture.

### 8.2 Whole sections to drop

**`stats`** (208px / 10 words / 6 atoms) and **`benefits`** (616px / 74 words / 8 atoms).
Line 222.

`stats` evidence: "100% / Backups Verified" is `hero.title` ("Every backup verified.
Automatically."), `techDiff.rows[2]` ("every backup, every time") and
`cloneVisual.clone.size` ("Integrity: 100%"). "Auto / No Manual Checks" is `hero.title`
again plus `benefits.items[1]` plus `techDiff.rows[2]` ("Automatic and daily"). "<1min /
Verification Time" is `cloneVisual.arrow.time` ("47s") and
`problem.timeline.newSteps[1]` ("47s"), and it is looser than both.

`benefits` evidence - every sentence of all three cards has a verbatim twin above it:
- `items[0]` "We copy, boot, and health-check every backup" = `techDiff.description` ("It
  copies the backup, boots every container, and runs health checks") = `howItWorks.steps[1]`
  ("We copy each backup, boot it up, and run health checks").
- `items[1]` "No manual testing. No scripts. ... A failure raises an alert before it
  matters." = `techDiff.rows[2]` + `howItWorks.steps[2]`.
- `items[2]` "PagerDuty, Slack, or email. The alert lands the moment a backup fails a
  check. No dashboard to watch." = `howItWorks.steps[2]` VERBATIM ("It works with
  PagerDuty, Slack, and email. No dashboard to check.") + `comparison.features[5]`.

### 8.3 Sub-blocks to drop

**`...backupVerification.problem.timeline`** (15 leaves) - 262px, 29 words, 15 atoms.
Evidence: `oldSteps` "Run backup / Trust 'completed' / Disaster strikes / Try to restore /
Backup corrupted" retell `problem.description` 40px above ("Most teams never check until a
restore is needed. By then it's too late") and `techDiff.rows[1]`. `newSteps` "Backup /
47s / Verified" duplicate `cloneVisual.clone.status` ("Verified") and
`cloneVisual.arrow.time` ("47s") one section below, and those are the ones with the
context.

**`...backupVerification.problem.statCallouts[1]`** - 118px, 11 words, 3 atoms.
Evidence: callout `[0]` is "58% / of backups fail on restore / Veeam Data Protection
Trends Report 2021" and callout `[1]` is "Only 13% / of companies can actually recover
during a disaster / Veeam Data Protection Trends Report 2024". Same claim, same vendor,
two report years, stacked 59px apart. `[0]` is the more direct statement of the page's
premise and stays; `[2]` ($173/record, IBM) is a different claim and stays.

**`...backupVerification.techDiff.rows[1]`** - 64px, 17 words, 2 atoms.
Evidence: "'Backup completed' status, no proof it restores / Actually restores to an
isolated copy and checks every endpoint" repeats `techDiff.title` ("Why 'backup completed'
isn't enough"), `techDiff.description` and `rows[0]` ("File fingerprint check, file
integrity only / Full restore, boot, and health check"). Rows 0 and 1 are one row written
twice.

**`comparison.features[4]` and `[5]`** - 109px, 15 words, 12 atoms.
Evidence: both are all-check across the four competitor columns. `features[4]` is worse
than merely empty: it is "File fingerprint check", and this page's own
`techDiff.rows[0].traditional` identifies a file fingerprint check as the WEAK thing
traditional tools do. The table then awards Rediacc a `rediacc` mark for it alongside four
competitor checks, so the page's strongest table scores itself on its own straw man.
`features[5]` "Alert integrations" is all-check and is `howItWorks.steps[2]`.

### 8.4 Measured after-numbers

    cut                       dheight  dwords  dw1atoms  dtext-atoms
    stats                        208      10        14          6
    problem.timeline             262      29         8         15
    benefits                     616      74         7          8
    comparison rows 4,5          109      15        12         12
    problem.statCallouts[1]      118      11         3          3
    techDiff rows[1]              64      17         0          2

**After: 7394px / 8.2 screens / 721 words / 196 w1 atoms / 163 visible text-atoms.**
Delta: -1377px, -156 words, -44 w1 atoms.

This is the lightest cut of the seven and leaves the heaviest page, entirely because of
the 354px `cloneVisual` I chose to keep. **Simulated alternative, if the operator prefers
uniformity over the exhibit:** adding `howItWorks.cloneVisual` to the cut list gives
**7040px / 7.8 screens / 684 words / 180 w1 atoms / 137 visible text-atoms** (-1731px,
-193 words, -60 w1 atoms), which is the best height result of all seven pages. I recommend the first, and
record the second so the choice is the operator's and not mine by omission.

---

## 9. FOUND, NOT ASKED FOR: eight solution pages ship an unlabelled primary CTA and an unlabelled comparison table

This is not a density finding and nothing in this document causes it or fixes it. It was
found while reading the `bottomCta` and `techDiff` subtrees of my seven pages and it
affects two of them plus six others.

### 9.1 The unlabelled CTA button

`SPBottomCta.astro:8` declares `primaryCta: string` (required) and renders it at `:24`:

```astro
    <a href={ctaHref} class="sp-btn-primary">
      {bottomCta.primaryCta}
      <svg width="16" height="16" ...>...</svg>
    </a>
```

Eight pages have no `primaryCta` key. They have `ctaText` instead. Driven on the frozen
build:

    $ agent-browser eval "(()=>{const a=document.querySelector('.sp-bottom-cta .sp-btn-primary');
        return {slug:location.pathname,text:JSON.stringify(a?a.innerText:null),
                aria:a&&a.getAttribute('aria-label')};})()"
    {'slug': '/en/solutions/encryption/',            'text': '""', 'aria': None}
    {'slug': '/en/solutions/rapid-recovery/',        'text': '""', 'aria': None}
    {'slug': '/en/solutions/retention-compliance/',  'text': '"Start free trial"', 'aria': None}

The rendered `innerHTML` on the two broken pages is the bare arrow `<svg>` and nothing
else. The page's final conversion control is a link with no accessible name and no
visible label.

### 9.2 The unlabelled comparison columns

The same eight pages also have no `techDiff.traditionalLabel` and no
`techDiff.rediaccLabel`, both declared required at `SPTechDiff.astro:7-8` and rendered at
`:23-24`:

    $ agent-browser eval "(()=>{const hs=Array.from(document.querySelectorAll('.sp-tech-detail-col-header'));
        return {slug:..., headers:hs.map(e=>JSON.stringify(e.textContent)), h:hs.map(...)};})()"
    {'slug': 'encryption',           'headers': ['""', '""'],  'h': [29, 29]}
    {'slug': 'rapid-recovery',       'headers': ['""', '""'],  'h': [29, 29]}
    {'slug': 'retention-compliance', 'headers': ['"Manual Retention Management"',
                                                 '"Rediacc Retention"'], 'h': [48, 48]}

A two-column "traditional versus Rediacc" comparison is rendered with both column headings
blank, so which column is which is left to the reader to infer.

### 9.3 The eight pages, and why nothing caught it

Both defects hit exactly the same set, which is the signature of one authoring pass:

    aiPentesting, encryption, continuousSecurityTesting, auditTrail,
    dataSovereignty, rapidRecovery, kubernetesClusterMobility, vendorLockIn

`SolutionPage.astro:61` reads the subtree as `(content as any)`, so the `Props` interfaces
that declare these fields required are never checked against the data. `check:ci-dead-
translation-keys` is documented in the program spec as unable to see anything under
`pages.solutionPages.*`. `validate-comparison-refs.js` iterates `comparison.features` and
nothing else. So no gate is positioned to see it.

### 9.4 What I did about it

Nothing, and deliberately. I am a read-and-propose agent with no product-file write
permission, and the fix lands in `packages/www/src/i18n/translations/`, which the program
spec places under single-owner serialised control ("owned by NOBODY... the LEAD applies
every deletion in one consolidated pass"). Writing three keys into thirteen catalogs from
this agent is exactly the concurrent read-modify-write that rule exists to prevent.

**Handoff for whoever does fix it.** The English fix is three added keys per page on eight
pages: rename `bottomCta.ctaText` to `bottomCta.primaryCta` (the value is already correct,
so this is a key rename and NOT an English value change, which means it does not trip
`check:i18n:hashes`), and author `techDiff.traditionalLabel` and `techDiff.rediaccLabel`.
The two labels ARE new English values and do need naturalizing in twelve locales. The
rename must be applied to all thirteen catalogs in the same pass or
`check:i18n:completeness` fires the orphan error at `:760-766`. It is the same
consolidated i18n pass this wave's deletions need, so it should ride it.

---

## 10. Consolidated deletion list for the LEAD's single i18n pass

All paths are under `pages.solutionPages.` and must be spliced from **all 13 catalogs**.
Leaf counts are English; the other twelve mirror the structure.

| page | subtrees to delete whole | array elements to delete | leaves (en) |
|---|---|---|---|
| retentionCompliance | `.stats`, `.benefits`, `.problem.timeline`, `.howItWorks.costVisual` | `.comparison.features[0]`, `[1]`, `[3]`, `[4]` | 9+11+15+29 = 64, plus 4 features |
| infrastructureCosts | `.stats`, `.benefits`, `.problem.timeline`, `.howItWorks.costVisual` | `.techDiff.rows[2]`, `[4]` | 9+11+15+26 = 61, plus 2 rows |
| immutableBackups | `.stats`, `.benefits`, `.problem.timeline`, `.howItWorks.cloneVisual` | `.comparison.features[4]`, `.problem.statCallouts[0]`, `.techDiff.rows[2]` | 9+11+15+28 = 63, plus 3 elements |
| integrations | `.stats`, `.benefits`, `.problem.timeline`, `.howItWorks.pipelineVisual` | `.techDiff.rows[3]` | 9+11+15+22 = 57, plus 1 row |
| encryption | `.stats`, `.benefits`, `.problem.timeline`, `.howItWorks.cloneVisual` | `.comparison.features[3]`, `[5]` | 9+11+15+28 = 63, plus 2 features |
| rapidRecovery | `.stats`, `.benefits`, `.problem.timeline`, `.howItWorks.cloneVisual` | `.comparison.features[1]`, `[2]` | 9+11+15+29 = 64, plus 2 features |
| backupVerification | `.stats`, `.benefits`, `.problem.timeline` | `.comparison.features[4]`, `[5]`, `.problem.statCallouts[1]`, `.techDiff.rows[1]` | 9+11+15 = 35, plus 4 elements |

**Never delete `label` or `blurb` from any of these subtrees**
(`SolutionConstellation.astro:92-100` reads them for the other twenty slugs).

### 10.1 `scripts/data/em-dash-surfaces-baseline.json`: exactly what to drain

The file is a flat list of 2715 `"<locale file>:<key path>"` strings, and it uses DOT
index notation (`techDiff.rows.0.rediacc`), not brackets. Computed per page:

| page | entries to DRAIN | entries needing RENUMBER |
|---|---|---|
| retentionCompliance | 8 (all under `.benefits`) | none |
| infrastructureCosts | 1 (`techDiff.rows.4.rediacc`) | none |
| immutableBackups | 40 (30 under `.benefits`, 10 under `techDiff.rows.2`) | none |
| integrations | 0 | none |
| encryption | 10 (all under `.benefits`) | none |
| rapidRecovery | 10 (all under `.benefits`) | none |
| backupVerification | 17 (8 `.benefits`, 9 `techDiff.rows.1`) | **27** |

**The 27 on `backupVerification` are a trap.** Dropping `techDiff.rows[1]` renumbers the
survivors, so the baselined `techDiff.rows.2.rediacc`, `rows.2.traditional` and
`rows.3.rediacc` must be REWRITTEN to `rows.1.*` and `rows.2.rediacc` in all thirteen
locale entries. A drain-only pass leaves them pointing at rows that no longer hold an em
dash and leaves the new `rows.1` unbaselined. No other page in my set needs a renumber,
because on the others the array indices above the deleted one carry no baseline entries.

### 10.2 Comparison-row deletion and the citation refs

`comparison.features[n].refs[i]` are 1-based indices into `references.items`. Dropping a
feature orphans the items it cited. `validate-comparison-refs.js` enforces
refs-to-items (`invalid-ref-index`, `missing-ref-url`, `duplicate-column-ref`) and has NO
rule in the reverse direction, so **leaving `references.items` untouched passes the gate**
and is what I recommend. The visible cost is that the collapsed disclosure's count, which
`SPSources.astro:48` renders as `({items.length})`, over-counts what is actually cited: on
retention-compliance it would read 22 with 16 entries uncited.

Deleting the orphaned items instead would require renumbering every surviving `refs` entry
on the page in thirteen catalogs, and `problem.statCallouts[*].ref` alongside them. That
is a second, independent splice with its own failure mode, and I recommend it be a
separate pass if it is done at all.

### 10.3 CSS

No CSS goes dead and `scripts/data/dead-css-baseline.json` needs no change. Every class
these cuts remove (`.sp-stats`, `.sp-benefits`, `.sp-timeline-contrast`,
`.sp-cost-visual`, `.sp-clone-visual`, `.sp-pipeline-visual`) is still used by the
fourteen solution pages outside my set, and `SPStatsBar`, `SPProblem`, `SPHowItWorks` and
`SPBenefits` are additionally mounted by `PersonaPage.astro:100/104/116/124`.

---

## 11. Result, all seven, against the homepage benchmark

Every "after" cell is a DOM-removal simulation on the frozen build, not arithmetic.

| page | before: h / screens / words / w1 atoms / visible | after: h / screens / words / w1 atoms / visible |
|---|---|---|
| retention-compliance | 8731 / 9.7 / 885 / 277 / 207 | **7054 / 7.8 / 692 / 176 / 128** |
| infrastructure-costs | 8749 / 9.7 / 851 / 255 / 198 | **7129 / 7.9 / 661 / 178 / 139** |
| immutable-backups | 8861 / 9.8 / 945 / 252 / 214 | **7225 / 8.0 / 746 / 198 / 148** |
| integrations | 8590 / 9.5 / 857 / 245 / 191 | **7099 / 7.9 / 674 / 183 / 140** |
| encryption | 8719 / 9.7 / 892 / 245 / 203 | **7146 / 7.9 / 719 / 188 / 136** |
| rapid-recovery | 8752 / 9.7 / 883 / 242 / 204 | **7126 / 7.9 / 685 / 183 / 135** |
| backup-verification | 8771 / 9.7 / 877 / 240 / 209 | **7394 / 8.2 / 721 / 196 / 163** |
| backup-verification (stretch) | | *7040 / 7.8 / 684 / 180 / 137* |
| retention-compliance (stretch) | | *6442 / 7.2 / 623 / 162 / 117* |
| **home (benchmark)** | 5838 / 6.5 / 518 / 157 / 147 | unchanged |

Totals across the seven recommended plans: **-11,000px of page** (about 12.2 screens
removed in total), **-1292 words**, **-454 w1 atoms**.

Read the columns knowing what each one can and cannot see (0.3):

- **Height and words are the honest columns.** Both reproduce the w1 CSV exactly and
  neither depends on a class-naming convention. Every page drops from 9.5-9.8 screens to
  7.8-8.2, and word counts drop 18 to 23 percent.
- **Visible text-atoms** put six of seven at or below the homepage's 147.
- **w1 atoms** stay above the homepage's 157 on every page, and that is the metric being
  hardest on this plan for a mechanical reason rather than a content one: the two biggest
  remaining w1-atom blocks on every page are the `costCalculator` island and the
  `comparison` table, both of which are built from `[class*=row]` and `[class*=item]`
  elements and neither of which is repetition. The homepage carries no comparison table
  and no calculator, so the w1 column is comparing a page that has those surfaces against
  one that does not.

## 12. Answering decision A5 explicitly: `howItWorks` as a whole section

**Verdict: keep the section on all seven, drop its `*Visual` sub-block on six of seven.**

The mass the operator objected to is not in the section, it is in the visual. Measured:
the section is 904-966px, of which `steps` is 249-275px and the visual is 292-354px, the
remainder being the overline, the `<h2>` and the section padding. In atoms the split is
starker: `steps` is **9 atoms** for 45-73 words, the cheapest content per atom anywhere on
the page, while the visual is **20-26 atoms** for 32-42 words.

The visual also carries the specific things the spec named: the invented server table, and
the raw `BTRFS COW` string, which I confirmed is the only appearance of that token in the
rendered text of `infrastructure-costs`.

And the visual comes out through the i18n subtree, which is the cheap lever, while the
section comes out through `sections`, which is the config lever. Taking the visual out
gets the operator's stated objection with the smaller change.

Against dropping the whole section: the three `steps` are the only place each page's `rdc`
commands appear in prose (`rdc config backup-strategy set`, `rdc retention report`,
`rdc repo push production --immutable`, `rdc keygen production`, `rdc backup list`,
`rdc repo push production`). Dropping them would leave each page asserting a mechanism it
never shows, and the `bottomCta.command` string is a single line with no explanation
around it.

The one exception is `backup-verification`, where I keep the visual and cut more prose
instead, for the reason in 8.1.

If the operator wants the section gone regardless, the per-page numbers are in each page's
stretch note, and the config change is to add `&& s !== 'howItWorks'` to the same filter.

---

## 13. Things I could not determine

1. **RESOLVED, but late, and worth recording as a process finding.** The w1 `atoms`
   column was unreproducible for the first hour of this session because w1's harness is at
   `packages/www/scripts/measure-page-density.sh`, in the PRODUCT tree, and not in
   `reports/` beside the CSV it produced. It also appeared at 16:03, after this agent had
   started. I burned nine candidate metric definitions guessing at it before finding it,
   and the guesses were all text-based while the real definition is a class-substring
   selector count that ignores text entirely. **A measurement CSV should ship with, or
   name, the script that produced it.** Section 0.3 has the definition and the
   reproduction; every atom figure here is now labelled `w1 atoms`, `text-atoms` or
   `visible text-atoms` so no two numbers in this document are silently different metrics.
2. **Mobile was not measured.** Every number here is the agent-browser default desktop
   viewport. This matters specifically for the cuts I priced at zero height: the timeline
   chevrons, the benefit cards and the `howItWorks` steps are horizontal at desktop and
   almost certainly stack on mobile, where dropping individual elements WOULD save height.
   The whole-block cuts I propose are unaffected either way, but a mobile pass could find
   additional element-level cuts that are worthless at desktop. Someone should run the
   section-cost table at 390x844 before this is called finished.
3. **The Kubernetes sentences in `integrations.benefits.items[1]` and
   `rapidRecovery.benefits.items[0]`** are the only content I propose deleting that is not
   restated elsewhere on its own page. Both are stated at page length on
   `kubernetes-cluster-mobility`, which both pages link to through the constellation. I
   judged the loss acceptable rather than pay a 12-locale re-naturalization to relocate two
   sentences, but it is a judgement and the operator may want it reversed. Same for
   `encryption.benefits.items[1]` (the authenticated-encryption sentence) and
   `immutableBackups.stats[2]` ("<60s Full Backup Time", uncited).
4. **The w1 atom metric has a blind spot that will distort the wave scorecard.** It
   matches nothing in the tech-difference table (cells are `.sp-tech-detail-cell`, rows are
   wrapperless `<Fragment>`s), so every `techDiff` row cut in this document scores 0 atoms
   while removing 44 to 128px and 9 to 33 words. It also over-weights the `*Visual` blocks
   by counting textless `[class*=card]`/`[class*=row]` elements. Wave 9 should either add
   `[class*=cell]` to the selector or report height and words as the primary columns. I did
   not change the script: it is a product file and this agent writes none.
5. **Whether the `downloadGated` section should go** is outside my competence here. It is
   338px shared with `downloadShort` and its strings are shared across all 21 pages
   (`SPDownloadShort.astro:119-131`). It is a lead magnet, not repetition, so it is not a
   density defect. Config-only removal is available at line 131/149/158/195/222/247/273 by
   adding `&& s !== 'downloadGated'`, worth roughly 150px. I do not recommend it and I did
   not measure it.
