# w-fixes-pipeline — writer report (clarity-round6)

Five assigned defects, all fixed. One sibling defect found and fixed in the same class
(rule: sweep the class, not the instance). Every check below was proven by planting a
violation and watching it go red, then removing it and watching it go green.

---

## D1. `step1000_source.py` never invalidated its cache

**Fix.** `steps/step1000_source.py` now computes a `cache_key` over every INPUT it reads
and re-derives when any of them moves:

| input | hashed as |
|---|---|
| page copy | `SolutionRecord.content_hash()` |
| `.cast` recordings | sha256 of the bytes of every file `cast_paths_for_category()` opens |
| positioning / pains docs | sha256 of each resolved doc |
| extraction shape | `SCHEMA_VERSION` (bump to invalidate the fleet) |

A missing input hashes as the literal `"missing"`, so a deleted cast is a DIFFERENT key
rather than the same key with less in it. `cache_inputs` is stored alongside so a miss can
name what moved: `Moved: casts:tutorial-backup-restore.cast`.

`cast_terminal.cast_paths_for_category()` was extracted so the key hashes exactly the files
the extractor opens, including the `_DEFAULT_CAST_FILES` fallback. `extract_for_category`
now calls it, so the two cannot drift.

**Evidence the defect was real, measured before the fix.** All 21 cached briefs were stale,
and every one still carried pre-positional-refs syntax:

```
dev-env    cached: rdc repo fork --parent my-app --machine machine-11 --tag experiment --up
           fresh : rdc repo fork my-app --tag experiment --up
           cached: rdc repo delete --name my-app:experiment --machine machine-11
           fresh : rdc repo delete my-app:experiment --yes
encryption cached: rdc repo secret set --name my-app --key DB_HOST ...
           fresh : rdc repo secret set my-app --key DB_HOST ...
```

**Fleet refreshed.** Snapshot taken first
(`scratchpad/snapshot-1000/`, 21 files), then all 21 `1000_source.json` re-derived. Now
21/21 HIT. The 37 unique `rdc` commands in the refreshed `facts.terminal_real` parse
37/37 clean against `packages/www/scripts/lib/cli-reference-catalog.js`, matching the
coordinator's independent measurement.

**Controls planted (7/7 fired correctly)**, in an isolated `PROCESSING_DIR`:

| control | expected | result |
|---|---|---|
| unchanged inputs | HIT | HIT |
| page content changed | MISS "page content" | fired |
| cast file mutated | MISS naming the cast | fired |
| cast restored byte-for-byte | MISS, key returns to its ORIGINAL value | fired, key `173350881ded5602` both times |
| unchanged again | HIT | HIT |
| `SCHEMA_VERSION` bumped | MISS "schema 2->99" | fired |
| legacy payload with no `cache_key` | MISS "pre-invalidation cache" | fired |

The mutated `.cast` was restored and verified byte-identical; `git status` on
`packages/www/public/assets/tutorials/` is clean.

---

## D2. The script writer invented CLI commands

Two halves: the prompt, and a deterministic post-check.

**Prompt (`prompts/script.py`, `prompts/storyboard.py`, `prompts/social_post.py`).**
`script.py` gains an absolute section, "NO rdc COMMAND ANYWHERE IN THIS FILE", covering
`narration`, `on_screen_text` and `visual_note` (the previous rule only forbade NARRATING
a command, which is why the inventions migrated into `on_screen_text`), plus self-check
item 7b, plus the sentence the empty case needed stated plainly:

> AN EMPTY facts.terminal_real MEANS THERE IS NO COMMAND YOU MAY WRITE.
> It does not mean "no grounding was supplied, so use your knowledge of the CLI".

`storyboard.py` extends "never put a command on screen" to EVERY field and adds the
drop-it-do-not-copy-it instruction for a command arriving from `2000_script.json`.

**Post-check (`postcheck.py` + `scripts/rdc_parse.mjs`, new).** Validity is NOT
re-implemented: `rdc_parse.mjs` imports `parseRdcCommand`/`rdcCommandPath` from
`packages/www/scripts/lib/cli-reference-catalog.js`, the same instrument every CLI gate in
the console repo uses. Three verdicts:

- **WRONG** — the command does not exist (`unknown-command`/`unknown-option`).
- **INCOMPLETE** — the verb exists, the invocation is not runnable.
- **UNGROUNDED** — absent from `facts.terminal_real`. This is the ONLY check that can fire
  when `terminal_real` is empty, which is where two of the five inventions came from.

Extraction has two modes, and that split is what keeps precision:

- **STRICT** — the string IS a command. Full parse + grounding.
- **PROSE** — a sentence that OPENS with one ("rdc repo pull production. Rediacc clones the
  full environment ..."). Only the VERB is judged. Without this the checker reports fourteen
  bogus positional args on ordinary copy, and a checker that cries wolf gets switched off.
  A shell break (`| ; > &`) stays STRICT: what follows a pipe is another command, not prose.

Wired into steps **2000**, **3600** and **5000**, on the CACHED path as well as the fresh
one — a cached artifact that was never checked is not a checked artifact. Fails closed via
`raise_on`, listing every violation.

**What it finds on the fleet today: 36 violations across 8 slugs.** These are LIVE, in
`on_screen_text` and in `visual.params.lines[].text`, i.e. burned into shipped video in 13
languages: `rdc security-scan`, `rdc audit`, `rdc clone`, `rdc retention report`,
`rdc config backup-strategy set`, `rdc cluster fork prod` (missing `--tag`),
`rdc cluster migrate prod` (missing `--to`), `rdc repo fork` (no args),
`rdc term production cve-fix`. The terminalType TEMPLATE was removed; the invented commands
simply moved into the on-screen text.

Locale drift was checked separately and is **0**: translations preserve commands verbatim,
so the English check covers all 13. (This is why parity alone is not enough — a dead command
sits identically in every locale in perfect parity. Only the absolute CLI check sees it.)

**Controls planted (14/14 fired correctly).** Baseline clean storyboard silent; invented
nonexistent command → WRONG+UNGROUNDED; valid-but-unrecorded command → UNGROUNDED only;
grounded verbatim command → silent; empty `terminal_real` → UNGROUNDED with the
empty-specific message; **prose merely mentioning `rdc` → silent (false-positive control)**;
backticked command in prose → fires; missing checker → **RAISES rather than reporting clean**
(instrument control); `raise_on` raises on non-empty and is silent on empty. Plus 7
strict/prose classifier cases, all correct. End-to-end through the real `run()` on the cached
path: `environment-cloning` passes, `ai-pentesting` raises, `audit-trail` (3600) raises.

---

## D2b. SIBLING FOUND AND FIXED — LinkedIn social copy carries dead commands

Not in the brief. Found by pointing the new extractor at every other stage artifact.
`3600_social.json` quotes commands that have never existed:

- `audit-trail`: `rdc audit --from 2026-02-01 --to 2026-02-27`
- `retention-compliance`: `rdc retention report --framework soc2`
- `vendor-lock-in`: `rdc repo sync push-all` (twice: carousel slide and text post)

A post is arguably worse than a frame, because a reader can copy it. Step 3600 is now wired
to the same post-check with the same grounding rule, and `prompts/social_post.py` gains the
matching prohibition. Measured: 6 violations, 0 false positives.

---

## D3. `validate:landing-cli-usage` was vacuous

**Chose: give it real inputs. Did NOT retire it.** (Consistent with the coordinator's
mid-task correction, which arrived after the work was done in that direction.)

**Which empty it was, established by running it, not reading it.** The prior N5 retraction
is correct that an empty capability map is the STRICTEST setting. This was a different
emptiness: the collector scanned `terminal.lines` and `heroTerminalLines`, both of which
genuinely left the site. The commands did not leave — they **MOVED** to
`bottomCta.command`: 23 of them, one per solution/persona page, rendered in a copy-me code
block by `SPBottomCta.astro:30-33`, in 13 locales.

`scripts/lib/landing-terminal-catalog.js` now collects that surface (the extinct collectors
are kept: they cost nothing and would catch a re-introduction).
`scripts/validate-landing-cli-usage.js`:

- checks **21 rdc commands** absolutely against the live CLI, and **parity across 13
  locales** (299 command strings);
- **removed the blanket skip** of `excess-positional-args` / `missing-mandatory-option`. That
  rationale ("landing demos are simplified for visual appeal") described the animated
  terminal; `bottomCta.command` is presented as THE command to run;
- refuses on an empty scan, in two distinct ways: sources exist but nothing collected →
  "the collector is broken"; and, new, **no source at all is now also RED**, because a gate
  with no subject is not a passing gate;
- refuses if commands were collected but NONE is an rdc command.

**Three genuinely-broken production commands were exposed and could not be fixed here**
(i18n catalogs are out of my ownership), so they are FROZEN in
`KNOWN_UNRUNNABLE_CTA_COMMANDS` with evidence, the parser's own reason, and the exact
replacement. It is a ratchet, not an allowlist: a NEW failure is red, a frozen command whose
text or reason changes is red, and a frozen command that gets FIXED is red until its entry
is deleted.

| sourceId | command | reason |
|---|---|---|
| `solution:retentionCompliance:bottomCta` | `rdc config backup-strategy set --cron '0 2 * * *'` | `unknown-option` |
| `solution:vulnerabilityManagement:bottomCta` | `rdc term production cve-2026-1234-fix` | `excess-positional-args` |
| `solution:kubernetesClusterMobility:bottomCta` | `rdc cluster fork prod --tag staging` | `missing-mandatory-option --to` |

**Why the storyboards were NOT taken, despite the coordinator's suggestion.**
`scripts/check-tutorial-commands.ts` already validates them with the same
`parseRdcCommand`, field-aware (`commandFull`/`teardownCommand`, never the abbreviated
`command` label). Verified by running it: **18 storyboards, 101 runnable commands, green**.
A second gate there adds zero coverage and a second excuse surface to keep honest — exactly
what `validate-cli-examples.ts` refuses for that surface. Reasoning recorded in the
validator's header so it is not re-litigated.

**Controls planted (6/6 fired correctly):**

| control | result |
|---|---|
| A: invalid `rdc cluster fork --name prod` planted in `en.json` `bottomCta.command` | **RED**, `landing-rdc-invalid-unmapped`, exit 1 |
| B: `de.json` command changed to differ from en | **RED**, `landing-command-parity-mismatch`, exit 1 |
| C: a frozen command replaced with a valid one | **RED**, "still freezes ..., but it now parses" |
| D: a frozen command changed but still broken | **RED**, "no longer describes this command" |
| F: collector stubbed to return `[]` while sources exist | **RED**, "The collector is broken" (reports 23 sources) |
| G: `isRdcCommand` forced false | **RED**, "NONE of them is an rdc command" |
| E: everything restored | **GREEN**, exit 0 |

`en.json` and `de.json` were restored and verified **byte-identical by sha256**;
`git status packages/www/src/i18n/` is empty. The catalog file was likewise restored and
sha-verified.

---

## D4. `HOMEPAGE_GROUPS` stale by six entries

Measured against `en.json`: 10 of 16 present. Absent: `problem`, `featureShowcase`,
`metrics`, `integrations`, `testimonials`, `logoWall`.

Both tuples updated **identically** (`www_pipeline/surfaces.py`,
`video_pipeline/persona_source.py`), and the silence that let it live is closed three ways:

1. `surfaces.assert_groups_exist()` — raises if any name is not a top-level key of
   `en.json`. Called from `_all_items()`, deliberately NOT at import (i18n_pipeline imports
   the tuple and never touches the homepage).
2. `persona_source._homepage_record` — the old check only fired when EVERY group was gone, so
   six dead names read as success. It now fails on ANY missing group in `en` (a gap in
   another locale stays tolerated, since English is the source of truth).
3. `persona_source.assert_ported_tuple_matches()` — turns the "PORTED VERBATIM" comment into
   an assertion by importing the upstream tuple and comparing. `ImportError` is not an error.

`pain_gate=group in ("hero", "problem")` reduced to `("hero",)`. Behaviourally identical
(`problem` matched nothing), so this is a clarity fix only.

**Controls planted (3/3 fired).** Adding `logoWall` back → both drift checks fire by name.
Diverging the two tuples → the identity check fires. Baseline: 10 groups, green.

---

## D5. Two slugs with zero `stockVideo` scenes — one defect, one not

`prompts/storyboard.py` rule 9: "stockVideo is REQUIRED on 1 to 2 scenes (at least one,
never more than two, never 2 consecutive)". Every other slug has exactly 1.

- **`infrastructure-costs` — a REAL defect.** 21 scenes, zero stockVideo ever authored;
  `5500_stockvideo.json` records `"scenes": []`, so nothing fell back. The rule's only
  reader was the agent that skipped it.
- **`vulnerability-management` — NOT a stockVideo finding.** It is the stale pre-v3 4-scene
  artifact `config.py` already names as "a stale pre-v3 5-scene script that must never be
  used as a baseline": 11 scenes under `MIN_SCENE_COUNT`, a fabricated testimonial ("A
  European fintech"), the word "btrfs" in narration, and over-specific numbers — everything
  the current prompt bans. Its whole tree needs regenerating, not a stockVideo beat.

**Fix:** `postcheck.check_storyboard_templates` counts all three clauses of rule 9 and runs
in **step 5000**, not after 5500. That placement is load-bearing: 5500 legitimately rewrites
a stockVideo scene to `kineticText` when Pexels returns nothing, so checking downstream would
confuse "the author never wrote one" with "the search found none" — different defects,
different fixes. The predicate is byte-identical to step5500's own
(`(scene.get("visual") or {}).get("template")`); verified across 5,252 scenes that no scene
carries `template` only under `params`.

Documented in `CONTRACT.md` (§5500) with both slugs named and distinguished.

**Controls planted (4/4 fired).** Zero stockVideo → fires. Three (and consecutive) → both
clauses fire. Exactly two but adjacent → the consecutive clause fires alone. Empty scenes
array → fires.

---

## Files changed

Owned and edited:

- `/home/developer/console/private/growth/video_pipeline/postcheck.py` (new)
- `/home/developer/console/private/growth/video_pipeline/scripts/rdc_parse.mjs` (new)
- `/home/developer/console/private/growth/video_pipeline/steps/step1000_source.py`
- `/home/developer/console/private/growth/video_pipeline/steps/step2000_script.py`
- `/home/developer/console/private/growth/video_pipeline/steps/step3600_social.py`
- `/home/developer/console/private/growth/video_pipeline/steps/step5000_storyboard.py`
- `/home/developer/console/private/growth/video_pipeline/cast_terminal.py`
- `/home/developer/console/private/growth/video_pipeline/persona_source.py`
- `/home/developer/console/private/growth/video_pipeline/prompts/script.py`
- `/home/developer/console/private/growth/video_pipeline/prompts/storyboard.py`
- `/home/developer/console/private/growth/video_pipeline/prompts/social_post.py`
- `/home/developer/console/private/growth/video_pipeline/CONTRACT.md`
- `/home/developer/console/private/growth/video_pipeline/processing/*/1000_source.json` (21, re-derived)
- `/home/developer/console/private/growth/www_pipeline/surfaces.py`
- `/home/developer/console/packages/www/scripts/validate-landing-cli-usage.js`
- `/home/developer/console/packages/www/scripts/lib/landing-terminal-catalog.js`

Snapshot of the pre-refresh briefs:
`/tmp/claude-1000/-home-developer-console/e580532b-53bf-4b76-92d8-b15b242c96d5/scratchpad/snapshot-1000/`

## Gates run (all green)

`validate-landing-cli-usage` 0 · `validate-content-accuracy --strict` 0 ·
`validate-docs-cli-usage` 0 · `check-tutorial-commands` 0 ·
`eslint` on both JS files 0 · `compileall` on every edited `.py` ·
`git status packages/www/src/i18n/` empty · `git status packages/www/public/assets/tutorials/` empty.

Not run: `npm run build` and `npm run ci` in full (forbidden / out of scope), and no render,
narration or publish. `ruff` is not installed in this environment; the repo's python-lint
gate excludes gitignored trees, which is where all the Python I touched lives.

## Found but NOT owned — for the operator / another writer

1. **36 live invalid-CLI strings in shipped video across 8 slugs** (list above). The video
   artifacts are mine, but fixing them means re-running the script/storyboard agents and
   re-rendering + re-narrating 8 slugs in 13 languages. The gate now refuses those slugs, so
   the next run cannot proceed without fixing them.
2. **3 unrunnable `bottomCta.command` values in `en.json` and 12 locale mirrors** (frozen
   above, with exact fixes). i18n catalogs are outside my ownership.
   `packages/www/src/i18n/translations/*.json`.
3. **`validate-content-accuracy.js:139` has a hole.** Its glob guard
   `if (/[*?]/.test(text)) continue;` skips ANY command containing `*` or `?`, so
   `rdc config backup-strategy set --cron '0 2 * * *'` is invisible to it purely because the
   cron expression has asterisks. That is why the landing gate is the only thing standing
   over that one. `packages/www/scripts/validate-content-accuracy.js`.
4. **`vulnerability-management` is a stale pre-v3 artifact still on disk** with 13 localized
   voiceovers and renders derived from it (4 scenes, fabricated testimonial, "btrfs" in
   narration). It should be regenerated or deleted, not patched.
