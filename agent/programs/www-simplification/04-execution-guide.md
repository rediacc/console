# 04. Execution guide

Status: **forward-looking.** Nothing here has been run.

## Before anything

1. **Cut a fresh `MMDD-N` branch.** The tree is parked on `main` and the modified
   tracked files cannot be committed there. Do this before editing any tracked file.
2. **Read `01-verified-context.md` and re-verify the claims you are about to
   depend on.** They were true on `main` at 2026-08-18T05:13Z.
3. **Ask the four decision points in `README.md` in ONE round**, not one at a time.
4. **Take over the wave items; do NOT re-add them.** All eleven are already in the
   store, tagged to the handoff session `e6500e92`, each carrying its token
   `cl:www-simplification/<wN>`:

       worklist.py --reassign <me> e6500e92

   The token links the store item to `CHECKLIST.md`. They were seeded at handoff
   rather than left for you because the Stop hook blocks ANY stopping session
   while a wave is uncovered, including peers with no stake in this program.
5. **Check for a neighbour.** A second `astro dev` ran on port 4802 for over a day
   during research, owned by another session. If one is live, the rig assumes a
   neighbour rather than the tree to itself.

## Spikes, before the waves they gate

- **S1, gates G11 then G1 (half a day).** Land `paths:` scoping and one RED gate,
  and prove the RED gate fails on today's tree and the mutation flips it. If a
  gate cannot be made to fail, that is a headline finding, not a footnote.
- **S2, the frozen-snapshot rig.** Build the 112 MB payload (an rsync plus a
  `node_modules` symlink, **not** a worktree; this checkout is itself a submodule
  worktree). Serve it on 4331. Prove a measurement taken against it does not move
  when the shared tree is edited.
- **S3 is CANCELLED.** It existed to prove an SVG-to-pipeline translation
  importer. Operator decision L4 removed the need: the illustrations carry no text
  at all, so there is nothing to import.

## Waves and ordering

Sequential. Two writers may run **inside** a wave only where their file sets are
disjoint, stated verbatim in each prompt.

| Wave | Work | Hard constraint |
|---|---|---|
| w1 | Gate scaffolding, RED-first gates | G11 first or every later run costs 95 min |
| w2 | Locale chunking, the 6.7 MB bundle | **Removes the TS-build backstop.** Keep an equivalent hard failure, or deleting a locale file becomes invisible |
| w3 | Collapse the token layer to one `:root` | Owns `public/styles/main.css`. **Cannot run with w4** |
| w4 | One primitive vocabulary | Also `main.css`. **Strictly after w3**, never beside it |
| w5 | Anchors F1 and F2 | Fable-tier. F2 rewrites fragment identity across 936 files |
| w6 | Homepage hero and below-fold | **One file, `[lang]/index.astro`. Never two writers** |
| w7 | Pricing and docs | Disjoint; may run as two writers |
| w8 | Illustrations become textless, 573 to about 21 | Fable-tier. No importer needed; S3 cancelled |
| w9 | Constellation | Fable-tier. Re-taxonomy, then label harvest, then build |
| w10 | Motion | **After w4**, which owns the `no-preference` and `html.js-anim` guard. Land it first or a no-JS visitor gets a blank homepage |
| w11 | Verification | Re-run the recorded instruments, not new ones |

Zero-pixel-change waves (w1, w2) are the cleanest gates in the program: assert the
rendered output is byte-identical before and after.

## Two-writer discipline, learned the hard way on 2026-08-18

The cap is 2 concurrent writers with disjoint files. Both halves failed once and
neither failure was the writers' fault:

1. **A wave is done when YOU have verified it stopped, not when it says so.**
   `w3-tokens` filed "done, w4 can start", then kept writing `public/styles/main.css`
   for another 24 minutes and produced a better census 15 minutes after that. Check
   the file mtimes and whether a build or agent process is still running before you
   release the next writer.

2. **Extending an agent's scope RESTARTS its clock.** The lead answered a scope
   question by giving `w3` two more stylesheets, then released `w4` on `w3`'s earlier
   completion message. Both then wrote `main.css` between roughly 09:29 and 09:53.
   Nothing was lost, but `w3` was doing whole-file rewrites, so a read-modify-write
   race would have silently eaten one of them.

3. **Overlap is invisible in the artifact.** The file looked fine afterwards, with
   both sets of work present. The collision was only detectable because one agent
   compared its own checkpoint patch against the file's mtime. If two writers must
   ever share a file, they need a marker convention, not good intentions.

**And the citation lesson that came out of the same incident:** matching numbers are
not evidence that the provenance is sound. The lead recorded a correct set of figures
against a census produced during the contaminated window, one paragraph after warning
about that exact error. Cite the artifact AND its timestamp, then check the artifact
was produced under conditions that make it attributable.


## Token forcing is SEMANTIC, not syntactic

A scripted pass that swaps a literal for the nearest token will silently break things
that happen to share a syntax. Two real regressions from this programme, both caught
only because another agent re-read a whole file after a pass:

- **A radius token is not scale-free.** `--radius-full` (9999px) applied to a 3px by
  14px tick mark turns a crisp tick into a capsule. Never force a radius onto an
  element narrower or shorter than roughly 8px without looking at it.
- **An absolutely positioned pseudo-element of an inline anchor sits at its static
  position, past the viewport edge on a long line, and STILL counts toward
  `scrollWidth`.** This single rule was the entire mobile overflow on 21 solution pages
  in 13 locales. Bisected properly: `white-space: normal` on it changed nothing (442),
  `position: static` fixed it outright (375). The relayed diagnosis had blamed
  `white-space: nowrap` and was wrong.
- **`box-shadow` with zero blur and non-zero spread is an OUTLINE, not an elevation.**
  `0 0 0 1px rgba(0,0,0,0.4)` keeps a white mark visible on bright video; replacing it
  with `var(--shadow)` = `0 1px 3px rgba(0,0,0,0.08)` outlines nothing. A `0 2px 8px`
  in the same file WAS a real shadow and swapped correctly, which is what makes the
  rule usable: judge the value's job, not its property name.

**AMENDMENT to this programme's own thesis, and it is the sharpest finding here.** The
guidance is "before adding a component, grep for the one that already exists". A
comparison table followed exactly that, found `.metric-label`, and inherited the metrics
bar's `text-transform: uppercase` and `letter-spacing`, shipping shouted row headers
that scrolled the page. **Following the guidance is what caused the bug.**

The reason it survived is that the name looked like it belonged to them: **a shared name
in a global stylesheet is an implicit export with no import to review.** The amendment is
"grep for it, THEN READ WHAT IT DOES", and prefer a component-scoped name over a
plausible shared one, because a duplicate rule costs a bounded amount and an accidental
inheritance does not.

**Do not reason from the spec. Render both and compare the bytes.** `w3` was about to
argue two suspect radii were "near identical after CSS clamping", which is reasoning
from the specification rather than measuring. It rendered each real geometry twice, at
4x device scale, once with the original value and once with the token, and diffed the
PNGs. Five were byte-IDENTICAL and safe; three were different and were real defects.

**Publish the passes as well as the failures.** That is what found the third defect.
`.sp-terminal-cursor` at 8x15px fell exactly through a small-box filter that cut off at
8px; it surfaced only because the same instrument that confirmed five findings was run
over everything and its passes were listed too. A sweep that reports only hits cannot
show you the case it never examined.

**So: after any scripted pass, re-verify the WHOLE file, not the declarations you
aimed at.** And prefer a named exception with a reason over a silent forced value.
Five named exceptions beat five silent regressions.

## Two rules born from wave 3, both non-obvious

**A chrome override must live AFTER the primitive layer in `main.css`, not with its
subject.** The primitive layer sits ~400 lines below the navigation section, and
`.nav-cta-btn` / `.hamburger-btn` share `(0,1,0)` specificity with `.btn`, so the
primitive silently beat the nav's `display: none`: the hamburger reappeared at desktop
and pushed the nav-right cluster onto a second grid row over the dark hero. The first
fix attempt put the sizing back in the nav section and changed nothing, for the same
reason. **axe caught it as a 4.90:1 -> 3.51:1 contrast change; no screenshot did.**

**`.cssRules` exists on EVERY rule since Chrome 112.** CSS nesting gave every
`CSSStyleRule` a usually-empty `.cssRules`, so the idiomatic
`if (rule.cssRules) { recurse; continue; }` **skips every style rule on the page**. A
focus-ring census reported `0 distinct focus declarations out of 1,248 rules` on a page
with 70 focus rules, and the zero looked entirely plausible. **Prefer `getComputedStyle`
over painted elements to any CSSOM walk.** Checked across this programme: `w3`'s census
is `getComputedStyle`-based and unaffected; only two of `w4`'s own instruments had it.

## Never use a live writer's file as a test fixture

The lead did this and is recording it against its own name. Fixing a gate, it needed a
real `.astro` file to run a control against, picked one `w6` was actively editing, and
did `cp` backup -> mutate -> restore twice over about two minutes. **The restore would
have silently reverted any write the owner made in that window.** It probably did not
happen; probably is not a standard. Use a file no wave owns, or a scratch copy outside
the tree.

Two smaller lessons from the same episode:

- **`printf >> path` on a file another wave DELETED silently recreates it.** A control
  targeting `MetricsBar.astro` resurrected a component `w6` had just removed.
- **A blanket `python` replace can insert a helper's own call inside the helper.**
  Wiring a comment-mask into "every line loop" put the call inside the mask function
  itself, and the gate died with `RangeError: Maximum call stack size exceeded`. Re-read
  the whole file after any scripted edit, including your own.

## A census whose SERVER died reported the best result in the programme

`w4` nearly published a fiction. Its static server died halfway through a census and
**the census did not raise**: it recorded the 404 body as a valid page, censused `/en`
mobile at **5 painted elements**, and produced a summary reading `font-size 17 -> 3,
radius 8 -> 0, scrollWidth 629 -> 390`. That is the most impressive row anyone has
produced here, and it is entirely false.

Two countermeasures, both now required of `w11`:

- **Floor the element count.** The census throws if any surface returns fewer than 50
  painted elements; the lowest genuine figure across 36 surfaces was 264.
- **A server backgrounded in one Bash call does NOT survive into the next one here.**
  The server and the census must share a single call, and liveness must be asserted
  before AND after.

Related, from `w7`: **`serve` silently rebinds when its port is taken**, announcing the
new port only in its own log, which turned one BEFORE census into a second reading of
the AFTER build. Put a marker only one side has into the served tree and assert it.

## Check a deletion RANGE before you run it, not after

Two agents converged on a `main.css` deletion range through three rounds of
artifact-level verification, and the range was still **off by four lines**: the metrics
block was handed over as `2091-2154` but ends at `2150`, and `2154` sat mid-rule inside
`.integrations-strip` - the live component `logo-wall` had just been deleted in favour
of. Deleting to it would have corrupted exactly the thing the sweep existed to protect.

It survived that much verification because everyone was answering **"which classes are
dead"**, and nobody asked **"where does this block end"**. Different question, and the
first does not imply the second.

**Before deleting any line range from a stylesheet, check the segment's brace balance:**

    python3 -c "l=open('f.css').read().split(chr(10)); s=chr(10).join(l[A-1:B]); print(s.count('{')-s.count('}'))"

Zero means the range is a whole number of blocks. The bad range gave `+1`; the correct
one gave `0`. Delete BOTTOM-UP so earlier indices stay valid, and re-check the whole
file afterwards, not just the ranges you aimed at.

**The outcome is gated even if the range is not.** `check:format` (`biome format`,
`package.json:155`, manifest `:98`) fails on a corrupted stylesheet with a parse error
naming file and line: a planted mid-rule deletion gave brace delta -1 and
`packages/www/public/styles/main.css:1805:18 parse × expected , but instead found (`.
That catches it AFTER the edit; the brace check above catches it before.

## `\b` IS THE WRONG TOOL FOR A CSS CLASS NAME

**A hyphen is a word boundary.** `\bmetric\b` matches `technical-metric`, so a sweeper
asking "is `.metric` still used?" gets a confident yes and keeps a fully dead rule.
Reproduced here: the naive grep names two consumers, exact class-token matching names
none.

**This fooled three instruments in a row, and every failure pointed the same way.** One
agent's `\b` grep matched `technical-metric`. A peer's delimiter-safe SOURCE search
matched `metric.key` in JavaScript and, better still, matched the words "metrics-bar"
inside the doc comment explaining why the component had been deleted. Then the
replacement instrument still used `\b` and reported 13 pages. **Both failure modes
land in the comfortable direction: keep the rule, believe you checked.**

Settle it on the BUILT HTML with exact class-token matching, where a JS identifier and a
comment cannot appear and `technical-metric` is simply a different string.
`<scratchpad>/w6-classemit-dist.py` does that and refuses three ways: stale dist, zero
HTML files scanned, and any control class returning zero. Its refusal message is the
right one: *"The scan is not seeing the site; its zeros mean nothing."*

**A stale dist nearly produced the opposite answer here**, not hypothetically: one rig
built at 11:52 still emitted the class a rename removed at 12:05. That tool now refuses
to run if any source file is newer than the dist.

## A metric that reaches ZERO can still sit on an unexamined cause

Stronger than the improvement version below, and it cost three passes on one defect.
Each stopping point produced a green measurement:

1. The nav attribution was inherited from a research document without measuring.
2. Bisection found a `nowrap` the wave had itself added. Fixed. Overflow fell.
3. A peer's passing remark revealed the table had ALSO borrowed a global class whose
   `text-transform: uppercase` was making the labels wide in the first place, upstream
   of the fix. Measured separately: 557px -> 502px from the rename, 502px -> 383px from
   the wrap. **Both load-bearing.**

## An improving metric is not a clean metric

`w7` reported 141px of residual overflow on `/en/pricing` as "the header", taking the
attribution from a research document instead of measuring. It was actually
`white-space: nowrap` on a table cell **in code that wave had just added**. It survived
four builds and a full before/after census, because the number fell from 228 and the
residue read as somebody else's known bug.

Two rules fall out, and they cost two waves between them:

- **"The rest is the known issue" is an attribution, not a measurement.** If you did not
  bisect it, you do not know whose it is.
- **An overflow a wave INTRODUCES is indistinguishable from one it inherited**, because
  both look like a smaller number than before. Sweep every surface your wave adds:
  `w6` had shipped a new route in 13 locales and never overflow-checked it, and only
  found that after reading `w7`'s correction.

**And the instrument that finds a defect is often built FOR that defect.** `w6`'s
overflow probe required `position: absolute` AND `white-space: nowrap` on a
pseudo-element; it found the tooltip it was written for and would have missed `w7`'s
plain table cell entirely. Prefer bisection, which assumes nothing about the shape of
the offending box: hide a subtree, re-read `scrollWidth`, restore, verify the restore.
It also distinguishes geometry that merely sticks out (the nav's 15px) from geometry
that actually makes the page scroll.

## Do not infer a TIME from a STATE

The lead and `w6` reached opposite conclusions about when a catalog deletion happened,
from the same evidence, and both were reasoning the same way. The lead saw the keys
absent and concluded the deletion had "just landed"; `w6` saw no change since its own
09:11Z baseline and concluded the deletion was "still pending". The deletion had in fact
landed BEFORE that baseline, so neither reading was right.

**A state tells you what is true now. It does not tell you when it became true.** If the
timing matters, get it from a timestamped artifact (a snapshot, a build log, a git
object), not from the presence or absence of a value. The same error in a different
costume produced a "second writer" story from a truncated `ls` timestamp earlier in this
programme.

## Dead blocks in `public/styles/main.css`, with ONE landmine

Left by `w6` for whoever sweeps that file. Coordinates as of 2026-08-18:

- `1272-1300` the logo-wall block
- `1651` the `.logo-wall-badge` NAME inside the chip primitive's selector list. **Remove
  the name, not the rule**: it still serves `.chip` and `.integrations-strip-badge`.
- `1956-2089` `.difference-row*` and `.difference-zoom*`
- `2091-2154` the metrics bar

**SETTLED at the artifact level, 2026-08-18.** Three source greps disagreed about this
block and all three erred toward keeping dead code. Resolved by exact class-token
matching on 1,842 built HTML pages, with live controls returning non-zero
(`comparison-row-label` 78, `home-difference` 13, `sp-home-hero` 13,
`technical-metric` 117) so the zeros mean something:

| lines | what | action |
|---|---|---|
| `1272-1300` | logo-wall block | **delete** |
| `1651` | the `.logo-wall-badge` NAME inside a selector list | **drop the name, KEEP the rule** - it still serves `.chip` and `.integrations-strip-badge` |
| `1956-2089` | `.difference-row*` / `.difference-zoom*` | **delete** |
| `2091-2154` | metrics bar, ALL FIVE selectors including `.metric` and `.metric-label` | **delete whole, no exception** |

**`.home-difference` and `.home-difference-container` at `1945-1954` must STAY**; the
rewritten section emits both on 13 pages.

The earlier "`.metric-label` must survive" exception is VOID: its last consumer was
renamed to `.comparison-row-label`. `.metric` at `2106` is dead too, which no source
grep established, because `\bmetric\b` matches `technical-metric`.

## Instrument traps that read like real failures

Each of these produces output indistinguishable from a genuine defect. All were hit
for real during this programme.

- **`npm run check:types` must be run from the repo ROOT.** From `packages/www` it
  exits 1 with `Missing script: "check:types"`, which reads exactly like a type error.
- **Reading an exit code through a pipe gives you `grep`'s status, not the command's.**
  Done three times in one wave, once making a mutant look like a fired control when it
  had never run.
- **`querySelectorAll('*')` returns no pseudo-elements.** Two independent overflow
  sweeps blamed the nav; the whole 442->375px overflow was one `::after`.
- **`getComputedStyle` mid-transition returns interpolated values that are STABLE
  across runs**, so they look like real data. Wait for finite animations, and prove it
  by taking two consecutive runs with byte-identical value sets.
- **`astro check` EXITS 0 WITHOUT CHECKING ANYTHING here.** `@astrojs/check` is not
  installed, so the command prints an interactive install prompt and returns success.
  Run non-interactively it BLOCKS on stdin forever: a 124-minute run in this programme
  burned zero CPU ticks and was reported as "slow" for two hours. Either way you get
  nothing. **`.astro` files are covered ONLY by a real `astro build` in this repo.**
- **The harness can report `exit code 0` for a rig build that actually exited 1.**
  Observed on a build that died with `Could not resolve regions.json`; only an explicit
  `echo ASTRO_EXIT=$?` revealed it. Echo the code yourself; do not read it off the
  harness. (The rig also needs `regions.json` at its root.)
- **`serve` silently rebinds when its port is taken**, announcing the new port only in
  its own log. One wave's BEFORE census was therefore a second measurement of its AFTER
  build. Put a marker only one side has into the served tree and assert it before
  trusting any census.
- **`tsc` does not typecheck `.astro` files.** A null dereference passed a green
  `tsc` and was only caught by `astro check`.
- **A dist older than its sources answers yesterday's question.** `check-anchor-integrity`
  now warns; nothing else does.
- **`ls --time-style=+%H:%M:%S` DROPS THE DATE.** A file last touched two months ago
  reads as this morning, and a plausible story gets built on it. Use
  `--time-style=full-iso`, and settle "did anyone edit this?" with `git diff --quiet`,
  which is one command and cannot be misread.
- **Untracked files are invisible to several gates.** `git diff` shows nothing for a
  new file, and `shellcheck.sh` enumerated only tracked `.sh` until it was widened.

## Staffing

**Opus** default for coding sub-agents. **Fable for w5, w8, w9 and for every
planning agent.** **Sonnet for all translation and naturalization**, via
sub-agents, which is the operator's cost policy.

At most **2 concurrent writers**, disjoint files named verbatim in the prompt.
Investigation agents fan out freely. Every sub-agent report is spot-checked
against the artifact before anything builds on it; reports are accurate about
intent and quietly wrong about placement.

Every writing or planning sub-agent prompt names its working report
`reports/<phase>-<agent>.md` under the program-state dir, and its brief
`reports/<phase>-<agent>-brief.md` when one is used. The team lead reads reports
and artifacts, never bare summaries.

## Gates between waves

A wave is done when, in this order:

1. Its worklist item is ticked **with probed evidence**, not a summary.
2. Its blast radius was declared in advance and the pixel gate asserts zero change
   **outside** it. The gate must print the **count** of surfaces compared; zero
   compared is a failure, not a pass. w3 and w4 have an empty outside-set and are
   labelled vacuous by declaration, so nobody reads their silence as success.
3. `MANIFEST.md` is updated at the boundary.
4. An uncommitted-tree patch lands in `checkpoints/`. A host reboot once destroyed
   a `/tmp` scratchpad; that is why durable state exists.
5. Only then tick the `wN` box in `CHECKLIST.md`. When every wave is ticked, set
   `Status: done`.

Decision points are asked in one early round and parked as `- [?]` **with a
DEFAULT that executes** if unanswered. Background delegation is held as
`- [>] (prefix) until:<ISO>Z worker:<id>` with leases renewed on wake. `- [x]`
only after probing the artifact.

## Definition of done

- Every wave ticked in `CHECKLIST.md`, `Status: done`.
- All 12 gates green, and **each one demonstrated to fail** on its planted
  mutation. A gate that cannot fail is not done.
- The scorecard re-run with the **recorded** instruments: homepage decoded JS
  under 500,000 B, distinct painted font sizes at 8 or fewer, distinct painted
  colours at 16 or fewer, mobile page height at 7,000 px or less.
- `anchor-integrity` reports **zero** dead in-page fragments across all 1,107
  pages and zero duplicate TOC fragments.
- Zero horizontal overflow at 1440 and 390, in every locale including Arabic.
- No em dash in any authored text, in any language.
- The four metrics we already beat are **unchanged**, not "improved": unused-CSS
  percentage, DOM node count and depth, above-fold density, a11y violations.

## Trap: a dev server old enough to be lying, and the tools that hid it

Added 2026-08-18 by the lead, after losing about twenty minutes to it.

The symptom was clean and specific. `/en/install#homebrew` rendered the page but
the platform picker was GONE: four tabs on a bare load, zero with the anchor. That
is a perfect hydration-mismatch story, the component did read
`window.location.hash` inside a `useState` initializer, and the fix wrote itself.

It was not the component. The dev server on port 4802 had been running since
**Aug 16**, two days of this programme deleting and rewriting components underneath
it, and its module graph had gone stale. Every React island on every page was dead
with `TypeError: jsxDEV is not a function` and `Failed to fetch dynamically imported
module` for `Navigation.tsx`, `Footer.tsx` and `LeadMagnetModal.tsx`. The homepage
was equally broken, which is the check that settled it in one command.

**The control that mattered:** on a clean server, revert the fix and load the page
again. The original code produced ZERO errors and ZERO hydration warnings. Without
that step the session would have recorded a confident repair of a bug that was never
there, and the real defect, an unusable dev server every later wave was about to
measure against, would have gone on standing.

Three instrument failures stacked to make this hard to see, and each is worth
knowing on its own:

- **`agent-browser errors` prints one blank line per error.** The message text is
  only in `errors --json`. Six blank markers told me nothing; the JSON named the
  exact TypeError and the module that failed. Never read the plain form.
- **`AGENT_BROWSER_SESSION=foo-$$` is a NEW session on every Bash call**, because
  `$$` is the shell's pid and each call is a new shell. The query ran against a
  browser where nothing had been opened, and reported an empty DOM. It looks
  exactly like a page that failed to render. Use a fixed literal.
- **In dev, a React hydration mismatch is a console WARNING, not a page error**, so
  `errors` cannot see it at all and `console --json` is the right instrument. A
  production preview throws it as a real error (minified #418), which is why the
  stale build on 4874 showed one while dev showed none. Two servers, two React
  builds, two different truths about the same source.

**The rule:** before believing any browser measurement, confirm the server is
serving today's code. `ps -o lstart` on the dev server and a load of one unrelated
page are enough. A long-lived dev server in a tree this active is not a convenience,
it is a stale instrument, and it will hand a wave a number that describes a site
nobody is running.

## A shrink-only baseline can still GROW, and the gate will say nothing

Added 2026-08-18 by the lead.

The em-dash gate holds a shrink-only baseline: it fails when a finding it has frozen
turns out to be FIXED, so the set can only ever get smaller. After the consolidated
catalog pass, draining it printed a reassuring line: `2,189 -> 2,160`, and the gate went
green. The number went down, the gate was happy, and the story looked finished.

Diffing the two baselines as SETS rather than comparing their sizes showed 30 entries
removed and **one added**: `ru.json:pages.solutionPages.cloudOutageProtection.blurb`, a
key that did not exist before the pass because the pass created it. A harvested value
carried a dash into a brand new key. The total still shrank, so nothing could have
flagged it, and `--write-baseline` would have quietly enshrined a fresh violation in the
very instrument that exists to prevent them.

The value was fixed rather than baselined, since the key was created in this session and
the standing rule is no dashes in any language. Russian тире is conventional in that
sentence, which is exactly why a translator would leave it and why the frozen set is the
wrong place to settle it.

**The rule: after any `--write-baseline`, diff the old and new sets and assert that the
ADDED side is empty.** A shrink-only baseline guarantees the total cannot grow. It
guarantees nothing about composition, and "the number went down" is not the same claim as
"nothing new got in".

## Trap: `grep -E` in this environment returns silent FALSE ZEROS

Reported by `w10-motion`, and reproduced before recording it.

`grep` here is ugrep 7.5.0. When `^` is alternated with a negated character class under
`-E`, it drops matches and reports a confident zero:

```
grep -cE '(^|[^a-z-])ease' packages/www/public/styles/main.css   ->  0
grep -cP '(^|[^a-z-])ease' packages/www/public/styles/main.css   ->  26
grep -cE '[^a-z-]ease'     packages/www/public/styles/main.css   ->  26
```

Same pattern, same file, three different answers. It nearly cost that wave its entire
easing inventory, and a zero from this shape is indistinguishable from a clean sweep.

**Use `-P` for anything with an alternated anchor**, and treat any sweep that reported
"no findings" with such a pattern as unrun. This belongs beside the other instrument
failures in this programme: the type-checker that exited 0 with nothing installed, the
census that recorded 404 bodies as pages, and the include pattern matching zero files
while 99 sat unlinted. The common shape is an instrument that answers rather than
refuses.

## Trap: a build rewrites `.astro/` under every running dev server in the tree

Also from `w10-motion`, and it explains the stale-server class this programme kept
tripping over.

`packages/www/.astro/` is derived from `config.root` with no override, so ANY build
rewrites the cache that every running dev server in the same checkout is reading. The
timeline that wave recorded: port 4802 was verifiably healthy at 12:44, two builds ran at
12:49 and 12:55, and by 13:00 that server was serving 384 DOM nodes with
`jsxDEV is not a function` on every island.

**A stale dev server does not fail loudly, it serves a SMALLER page.** That is the whole
danger: a census against it returns plausible numbers that are simply describing less
site. The cheap liveness assertion that wave suggested is worth adopting: on `/en` the
painted duration `0.08s` belongs to `.nav-translate`, which exists only if the Navigation
island rendered, so a census showing no `0.08s` and no nav is measuring a stale server,
not an improved site.

Corollary for anyone coordinating waves: do not run a build while another agent is
measuring against a dev server in the same tree, and say so before you start one.

## Trap: `git show HEAD` is not "before this wave" in a tree with uncommitted rounds

Added 2026-08-18 by the lead, after accusing a wave of deleting a feature it never touched.

Everything in this programme stays UNCOMMITTED by operator instruction. By round 2 the
working tree therefore carried **two** rounds of uncommitted work, and `HEAD` predated
both. `git show HEAD:<file>` is the state before ROUND 1, not the state before the wave
you are auditing.

What that cost: `grep -ci share` on `DocsLayout.astro` gave **64 at HEAD and 4 in the
tree**, and I attributed the whole 60-line delta to the wave then editing that file. The
removal was round 1's, deliberate, and a good one: a 336-line script that injected a 141px
split button into every h2 and h3 and shipped an HTML-to-Markdown converter to the browser
to serve one menu item, whose side effect was heading accessible names reading
`"IntroductionCopy sectionvCopy section linkCopy direct URL to"`.

The wave answered with a preserved pre-edit read of the file showing the count was already
4 before its first edit, the self-documenting replacement comment, and the earlier wave's
report citation. It was right.

**The rule: to audit what one wave changed, compare against that wave's own starting
state, not against `HEAD`.** Options that actually mean what you want:

- the writer's own preserved pre-edit read of the file,
- a checkpoint patch taken before the wave started,
- or, when neither exists, ask the writer for its baseline before drawing a conclusion.

And the confirming check that does not depend on any baseline: for a suspected orphaned
key, look at the CATALOGS. If the key is already absent from all thirteen, no pass has
anything to do, whoever removed it. That single query settled this in one command after
two rounds of inference had pointed the wrong way.
