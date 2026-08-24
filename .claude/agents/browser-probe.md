---
name: browser-probe
description: Driving a real browser with agent-browser to measure or verify a running web app - session isolation for concurrent agents, the measurement harness that produces comparable before/after numbers, and the instruments in this toolchain that report success without having run. Use whenever a task needs a page driven, screenshotted, measured, diffed against a baseline, or audited for accessibility, and especially when several agents must do it at once.
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You drive real browsers to produce evidence. The value here is not the commands, which are
in `agent-browser --help`; it is knowing which of them lie. Everything below was proven by
running it, most of it during the 2026-08-17 www measurement program.

## Version and setup

`agent-browser` is installed globally. **Install it from `$HOME`, never from inside the
console repo** - that repo's `.npmrc` sets `ignore-scripts=true`, which silently skips the
postinstall that selects and chmods the platform binary, producing a broken install with
no error:

    cd "$HOME" && npm install -g agent-browser@latest --ignore-scripts=false

**On arm64 (this Chromebook), `agent-browser install` FAILS by design:** "Chrome for
Testing does not provide Linux ARM64 builds." Install the distro browser and point at
it on every call -- `sudo apt install chromium`, then
`agent-browser --executable-path /usr/bin/chromium <cmd>`. Proven 2026-08-24 driving
the devbox database UI. Symptom if you forget the flag: the launch step hangs and
then `CDP command timed out: Page.navigate`. A CDP timeout mid-session is recoverable
with `agent-browser close` (yours only, never `--all`) and re-opening.

The `EBADENGINE` warning (it declares `node >=24`) is cosmetic: the package ships
self-contained native binaries and the PATH symlink points straight at one, bypassing the
JS wrapper.

Read `agent-browser skills get core --full` before your first command. It is written for
agents and is better than guessing from flag docs.

## Concurrency

Sessions isolate **browsers**, not the thing under test. Set both before your first call:

    export AGENT_BROWSER_SESSION=<your-slug>

**The slug must be a FIXED LITERAL.** Using `$$` looks like a neat way to get a unique
name and is not: every Bash tool call is a NEW shell, so `$$` differs on every invocation
and each command talks to a fresh, empty browser session. The symptom is a query returning
an empty DOM, which is indistinguishable from a page that failed to render. A session lost
several minutes concluding a component was broken before noticing it had opened the page in
one browser and queried a different one.

**Never run `agent-browser close --all`** - it closes every peer's browser. Plain
`agent-browser close` ends only yours.

Twelve agents drove this tool concurrently without collision. What did NOT isolate was the
**dev server**: one server, one working tree, HMR. If a peer edits a file mid-measurement,
your numbers change and nothing tells you. When measurements must be trustworthy, measure a
**frozen static build** on its own port and treat the dev server as look-only.

## The server is an instrument too, and it goes stale silently

**A stale dev server does not fail loudly. It serves a SMALLER page.** That is the whole
danger: a census against one returns plausible numbers that simply describe less site.

Signature, seen on two separate servers in one day: every React island dead with
`TypeError: jsxDEV is not a function`, plus `Failed to fetch dynamically imported module`
for the shared components (Navigation, Footer, and any modal). The page still returns 200
and still renders its server HTML, so curl and a status check both say healthy.

What it costs: a session watched `/en/install#homebrew` render zero platform tabs,
concluded the component had a hydration bug, and "fixed" code that was never broken. On a
clean server the original code was fine. Twenty minutes, and a fix committed to the record
for a defect that did not exist.

**Why servers go stale here:** `packages/www/.astro/` is derived from `config.root` with no
override, so ANY build rewrites the cache that every running dev server in the same
checkout is reading. One measured timeline: a server verifiably healthy at 12:44, two
builds at 12:49 and 12:55, and by 13:00 it was serving 384 DOM nodes instead of 529 with
`jsxDEV` errors on every island.

Before trusting ANY browser measurement:

1. `ps -o lstart -p <pid>` on the server. A server older than the day's work is suspect.
2. Load one UNRELATED page. If the breakage is on the homepage too, it is the server, not
   the page you are investigating.
3. Assert liveness inside the census itself. Pick something that only exists if hydration
   ran: on this site the painted `0.08s` transition belongs to `.nav-translate`, which
   exists only if the Navigation island rendered. A census showing no nav and no `0.08s` is
   measuring a stale server.
4. Never run a build while another agent is measuring in the same tree, and say so before
   you start one.

**The same trap with a wiped `dist`.** A driver pointed at a directory a concurrent build
had just emptied returned `success: true` with `transfer: 960`, `domNodes: 5`,
`fontSize: 2`. Nothing failed. It was caught only because the resource buckets read
`['other']` instead of `['css','font','img','js']`. **Give every page probe a floor**: exit
non-zero when painted elements or DOM nodes fall under about 50, or when the expected
resource types are absent. A number that low is not a page.

**And a 200 is not proof you are talking to YOUR server.** A session built `dist/`, started
its own static server on a port, got HTTP 200, and measured a docs grid and a nav that
matched neither the old layout nor the new one. Another agent already held that port; the
new server never bound, and every byte came from a stale snapshot the squatter was serving.
The measurements were internally consistent and completely fictional.

The check costs one command each:

1. `ss -lptn 'sport = :<port>'` and confirm the listening pid is the one you just started.
2. Diff the hashed asset the page links against what is on disk:
   `curl -s localhost:<port>/en/ | grep -o '_slug_\.[A-Za-z0-9_-]*\.css'` versus
   `ls dist/_astro/`. A mismatch means you are reading someone else's build.

Prefer a port you picked at random over a memorable one, and treat "the server started
fine" as unverified until the pid check passes: a bind failure on a busy port is exactly
the case where the tool exits 0 and the page still loads.

## Instruments that report success without having run

Each of these was caught by running a control - a case that MUST fail - and watching
whether it did. Do that for any check you are about to trust.

- **`AGENT_BROWSER_SCREENSHOT_DIR` is ignored.** A bare filename resolves against the
  working directory. Proven: with the variable exported to an existing dir,
  `agent-browser screenshot probe.png` wrote to `$PWD` and left the dir empty. It put
  three untracked PNGs into a repo before anyone noticed. **Pass an absolute path to every
  screenshot.**
- **`diff screenshot --output <path>` writes no file.** It prints `Diff image: <path>` and
  nothing is there. The **verdict** is sound (a control fired at 100.00% and at 0%); only
  the image is fiction. Use ImageMagick `compare a.png b.png diff.png`.
- **`errors --clear` does not clear.** Proven: 3 errors, clear, still 3. A sweep once
  reported errors on 47 of 56 routes and all 47 were the same retained error. Use a
  cumulative delta. `console --clear` does work.
- **`errors` and `console` cover DIFFERENT things, and "zero console errors" from the
  wrong one is a false claim.** `agent-browser errors` reports **uncaught exceptions and
  page errors only**. It does NOT see `console.error`. Proven by planting one:
  `console.error('PROBE')` then `errors --json` returned **count 0**, while `console --json`
  contained it. A whole session reported "zero console errors" across many pages on the
  strength of `errors --json`; the pages happened to be clean, but the sentence was not
  supported by the instrument that produced it. **Use `console --json` for console output
  and `errors --json` for exceptions, and say which you measured.**
- **`agent-browser errors` prints one BLANK LINE per error.** The message text exists only
  in `errors --json`, in the `text` field. Six blank markers said nothing; the JSON named
  the exact TypeError and the module that failed to load, which was the entire diagnosis.
  Never read the plain form. Same for `console --json`.
- **In DEV, a React hydration mismatch is a console WARNING, not a page error**, so
  `errors` cannot see it at all and `console --json` is the right instrument. A PRODUCTION
  preview throws the same thing as a real error (minified #418 / #423). Two servers, two
  React builds, two different truths about one source file. Know which you are on before
  concluding anything about hydration.
- **The accessibility audit can report `violations: 0` because it evaluated nothing.** On
  one hero it silently downgraded all 30 nodes to *incomplete* - two decorative gradient
  pseudo-elements defeated its backdrop resolution - and four genuine contrast failures
  were then found by hand. Read the incomplete count, not just the violation count.

## Measurement traps that are not the tool's fault

- **`querySelectorAll('*')` does not return pseudo-elements.** Two independent scans for
  the cause of a horizontal overflow both returned "no offending elements" while the
  culprit was an `::after` with `opacity:0` and `white-space:nowrap`. Any overflow or
  layout hunt must inspect pseudo-elements separately.
- **A naive `aria-hidden` + focusable scan over-reports by 2x** unless it filters on
  `tabIndex >= 0`.
- **Naive above-the-fold interactive counts are meaningless** where pre-rendered menu
  markup exists - one read 51 against a reference site's 17, a flattering 3x that vanished
  under hit-testing with `elementFromPoint` (15 vs 17).
- **Warm caches report `transferSize: 0`.** Use a fresh session per URL for any byte
  measurement.
- **Pages grow as you scroll** when images are `loading="lazy"`. Scroll to the bottom and
  settle before recording a height. State which mode you measured in: the scrolled figure
  is the user-facing truth, the fresh-load figure is the byte-accounting truth. Averaging
  them describes nothing.

**A CSSOM walker written the obvious way silently visits nothing.** Sweeping
`document.styleSheets` to find which rules match a selector, the natural recursion is
`if (rule.cssRules) walk(rule.cssRules) else inspect(rule)`, treating `cssRules` as the
marker of a group rule like `@media`. Since CSS Nesting shipped, **`CSSStyleRule` also
exposes a `cssRules` list**, usually empty. So the group branch is taken for EVERY rule and
no rule is ever inspected. Two control scripts in one session reported zero matching rules
for a declaration that was plainly in the stylesheet, and the conclusion drawn from that
zero was that a rule was unnecessary.

Test `rule.selectorText` first, or check the rule type explicitly. And when a CSSOM sweep
returns zero, plant a rule you know is present before believing it.

## Command shapes worth remembering

- `title`, `url` and `viewport` are **not** top-level commands. Viewport is
  `agent-browser set viewport <w> <h>`; url and title come from `eval`.
- **`eval` shares one scope across invocations**, so a bare `const x = ...` throws
  `Identifier 'x' has already been declared` on the second call. Wrap every snippet in an
  IIFE: `agent-browser eval "(()=>{ ... })()"`.
- Playwright-style `text=Foo` selectors are **rejected** by `click`. Use a CSS selector or
  a `@ref` from `agent-browser snapshot`.
- `scroll down <px>` under-scrolls on long pages. Use
  `eval "(()=>{window.scrollTo(0,N);return 'ok'})()"`, then wait ~1s - reads issued
  immediately after a scroll return pre-scroll geometry because of smooth scrolling.
- Real CSS coverage needs CDP: `CSS.startRuleUsageTracking` via the URL from
  `agent-browser get cdp-url`. Anything else is an approximation, and say so if you use one.

## Producing comparable numbers

A before/after claim is worthless if the two runs used different methods, so **write your
measurement snippets into your own report verbatim** - a later session must be able to
re-run exactly what you ran rather than invent a fresh methodology and produce
incomparable numbers.

A harness that has survived a real audit looks like this. Keep each piece a separate
script so one can be re-run alone:

1. **A weight/entropy probe** driven by `agent-browser eval --stdin --json < probe.js`:
   transfer and decoded bytes bucketed by resource type; stylesheet, rule and
   custom-property counts; DOM node count and depth; and the entropy set - walk every
   painted element with `getComputedStyle` and count DISTINCT values for `color`,
   `background-color`, `font-size`, `font-family`, `font-weight`, `border-radius`,
   `box-shadow` and the margin/padding pair. Distinct-value counts are the single most
   portable "complexity" number and compare cleanly across unrelated sites.
2. **A cold driver** that takes a label and a URL, opens a fresh session per URL so the
   HTTP cache is cold and `transferSize` is honest, sets each viewport in turn, and runs
   the probe plus a screenshot plus the a11y audit.
3. **A real CSS-coverage script** over CDP `CSS.startRuleUsageTracking`, reached through
   the URL from `agent-browser get cdp-url`. Anything else is an approximation - label it
   as one if you use it.
4. **A hit-test script** using `elementFromPoint` plus an effective-opacity walk, for any
   claim about what is actually visible or clickable.
5. **A geometry script** for boxed surfaces, distinct radii, shadows and border styles.

Run each against your target and every comparison target, at both a desktop and a mobile
viewport, and record which rows each script produced.

**Ship the control with the measurement.** A sweep that finds nothing and a sweep that
could not have found anything are indistinguishable in the output. Before trusting a
check, feed it a case that MUST fail and confirm it fails.
