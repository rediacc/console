# www simplification — shared brief

**Status:** research phase, 2026-08-17. Read this before doing anything.

The operator's words: *"the web site is super complex. I need simplification.
https://claude.com/ is a good example to have a simple design."* They are also a
fan of **https://www.anthropic.com/**, "especially the hero section of the home
page. There is a special component there."

You are one of a fleet of domain specialists. You research your domain now; you
will be asked to **implement** the simplification in your domain later, in this
same conversation, with the knowledge you are building right now. Write for that
future self: a fact you do not record is a fact you will re-derive.

## The one hard rule right now

**DO NOT MODIFY ANYTHING.** The operator said so explicitly. Zero edits to
`packages/www` — no `.astro`, `.tsx`, `.css`, `.json`, no config, no content.

The **only** file you may write is your own research document:

    agent/programs/www-simplification/research/RESEARCH-<your-domain>.md

Also forbidden, always: `git checkout`, `git restore`, `git stash`, `git clean`,
`git commit`, and any `sync`/`regenerate`/`generate` script. This tree is shared
with other sessions and holds uncommitted work that is not yours. There is no
safety net.

## The subject

`packages/www` — an **Astro 5.18** marketing + docs site. No Tailwind; all CSS is
hand-written. Relevant scale, measured 2026-08-17:

| Thing | Count |
|---|---|
| Components (`src/components/*.{astro,tsx}`) | 43 |
| Pages (`src/pages/**/*.astro`) | 61 |
| Layouts | 3 (`BaseLayout`, `ContentLayout`, `DocsLayout`) |
| CSS in `src/styles/` | 8,806 lines across 20 files |
| CSS in `public/styles/` | 4,697 lines across 5 files |
| Astro components carrying an inline `<style>` block | 14 |
| Locales | 13 (en + 12) |

**Where the styling actually lives — this trips people up.** The main stylesheet
is *not* in `src/`. `src/layouts/BaseLayout.astro:237-242` links
`/styles/main.css` (3,421 lines) and `/styles/responsive.css` (248) from
`public/styles/`, plus three more loaded via the `media="print"` onload trick
(`search-modal.css`, `contact-modal.css`, `region-picker.css`). On top of that,
`BaseLayout.astro:279-414` holds an inline `<style>` block that defines the
`:root` custom properties (`--font-family`, `--font-size-*`, …). So tokens are
split between an inline block in a layout, `public/styles/main.css`, and several
files under `src/styles/` that declare their own `:root`
(`lead-magnet-modal.css`, `sidebar-shared.css`, `solution-pages.css`,
`AnnouncementBar.astro`). Establish the real cascade before you claim anything
about it.

Fonts: **Inter** (Regular/Medium/SemiBold/Bold) and **JetBrains Mono**
(Regular/Bold), self-hosted under `public/fonts/`. Only Inter-Regular and
Inter-SemiBold are preloaded (`BaseLayout.astro:131-133`).

## Running instance

An Astro dev server is already up — **do not start another one**, and do not kill
it:

    http://localhost:4321/        ->  redirects to /en
    http://localhost:4321/en
    http://localhost:4321/en/pricing

It is background task `b3o18fv5k`. First-boot content sync takes ~56s; it is
already past that. If a route 404s or the server is gone, say so in your report
rather than starting a second one.

## Reference sites

- **https://claude.com/** — the operator's stated model for simple design.
- **https://www.anthropic.com/** — especially the **homepage hero**, which the
  operator says contains "a special component".
- Their docs surfaces exist too (`https://docs.claude.com/`) if your domain
  covers documentation.

Study them **through the lens of your own domain**, not exhaustively. The point
is a specific, portable answer to "what do they do that makes it feel simple, and
what is the equivalent move for us."

## Your browser

`agent-browser` 0.34.0 is installed and working. Full command reference:

    /tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/agent-browser-help.txt
    /tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/agent-browser-skill-core.md

Read the core skill before your first command; it is written for agents.

**Session isolation is mandatory.** Every other specialist is driving a browser
at the same time. Export these before your first `agent-browser` call and keep
them set for the whole session, substituting your own domain slug:

    export AGENT_BROWSER_SESSION=sx-<your-domain>
    export AGENT_BROWSER_SCREENSHOT_DIR=/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-<your-domain>

Then `mkdir -p "$AGENT_BROWSER_SCREENSHOT_DIR"`.

**`AGENT_BROWSER_SCREENSHOT_DIR` DOES NOT WORK — always pass an absolute path.**
This brief originally told you to rely on that variable. That was wrong, and it
already put three untracked `.png` files into `packages/www/`. Proven:

    cd /tmp
    export AGENT_BROWSER_SCREENSHOT_DIR=/tmp/.../shots/leadcheck   # dir exists
    agent-browser screenshot envdir-probe.png
    -> "Screenshot saved to envdir-probe.png"
    -> $AGENT_BROWSER_SCREENSHOT_DIR is EMPTY; the file is at /tmp/envdir-probe.png

`agent-browser --help` documents the variable as "Default screenshot output
directory", so this is a defect in agent-browser 0.34.0, not a misreading. A bare
filename resolves against the working directory instead. Set the variable anyway
(harmless, and the session name still isolates you), but **write every screenshot
path out in full**:

    agent-browser screenshot "$AGENT_BROWSER_SCREENSHOT_DIR/whatever.png"

Never pass a bare filename. Your working directory is the repo.

**`diff screenshot --output <path>` writes NOTHING.** Second defect in the same
family, found by `sx-process` and verified twice: the command prints
`Diff image: <path>` and the file is absent afterwards. The **verdict** it prints
(pass/fail plus pixel counts) IS trustworthy — a control was run and fired both
ways — but the diff **image** is never produced. If you need to look at the
difference, use ImageMagick, which is installed and does write a real file:

    compare before.png after.png diff.png

Trust the verdict, do not trust the path.

**The page is 133px wider than the viewport even at desktop.** At 1440x900 on
`/en`, `documentElement.scrollWidth` is **1573** against `clientWidth` 1440,
while **zero visible element's right edge exceeds the viewport** — the cause is
the off-canvas `aside.sidebar` (width 1425 at left -1425). Consequence for your
work: **a full-page screenshot comes out 1573px wide at a 1440 viewport.** If you
are comparing images across sessions or against a baseline, that extra 133px is
in the frame and will move if anyone touches the sidebar.

**Never run `agent-browser close --all`.** It closes every peer's browser. Plain
`agent-browser close` (yours only) at the end is fine and polite.

### Quirks already paid for — do not rediscover these

- `title`, `url` and `viewport` are **not** top-level commands. Viewport is
  `agent-browser set viewport <w> <h>`. Get url/title via `eval`.
- `eval` shares **one scope across invocations**, so a bare `const x = …` throws
  `Identifier 'x' has already been declared` on the second call. Wrap every
  snippet in an IIFE: `agent-browser eval "(()=>{ … })()"`.
- Playwright-style `text=Foo` selectors are **rejected** by `click`. Use a CSS
  selector, or a `@ref` from `agent-browser snapshot`.
- `scroll down <px>` under-scrolls on these pages. Use
  `eval "(()=>{window.scrollTo(0,N);return 'ok'})()"`, and let it settle (~1s)
  before measuring — reads issued immediately after a scroll return pre-scroll
  geometry because of smooth scrolling.
- Useful beyond screenshots: `snapshot` (accessibility tree with refs), `eval`
  for computed styles, `set viewport` for responsive checks, `console`,
  `network requests`. There is an accessibility/WCAG audit and a `diff
  screenshot --baseline`; check the help before assuming a command's name.

Take screenshots at **1440x900** as the standard desktop frame, and at
**390x844** for mobile. Actually *look* at them — a claim about visual weight
that you did not see is a guess.

## What a good research document looks like

Write to `agent/programs/www-simplification/research/RESEARCH-<your-domain>.md`. Structure:

1. **Verdict** — 5 sentences max. What is over-complex in your domain, and what
   is the single highest-leverage simplification.
2. **What we have** — the inventory, with `file:line` evidence for every claim.
   Counts, not adjectives: "9 button variants across 5 files" beats "many".
3. **What claude.com / anthropic.com do** — the same measurements on their side,
   with the URL and the measured value (computed styles, counts, px). Do not
   describe their vibe; measure their system.
4. **The delta** — a table. Ours vs theirs vs the gap.
5. **Proposed simplification** — ordered by leverage, each item with: the change,
   the exact files it touches, the risk, and how you would prove it worked.
   Include what you would **delete**. Deletion is the point.
6. **Cross-domain consequences** — anything that lands in another specialist's
   files. Name it; do not fix it.
7. **Open questions for the operator** — only genuine judgement calls.

## Evidence standards

- Every claim about **our** code carries `file:line`.
- Every claim about a **reference site** carries the URL and a measured value you
  read out of the live page (`eval` + `getComputedStyle`), not an impression.
- If you assert a count, show the command that produced it.
- Distinguish what you **measured** from what you **infer**. Both are welcome;
  conflating them is not.
- Screenshots are evidence: reference them by path in your document.

## Boundaries

Your domain and its file ownership are in your task prompt. Other specialists own
the rest. When you find something real outside your files — and you will —
record it under *Cross-domain consequences* and move on. Do not touch it, and do
not silently drop it.
