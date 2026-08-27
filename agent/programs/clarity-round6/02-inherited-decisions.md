# 02. Inherited decisions

Status: **Locked elsewhere. Do not relitigate.** Each item below was decided by the
operator or ratified in a prior program. Re-opening one wastes the session that settled it.

## From `agent/programs/www-simplification/02-locked-decisions.md`

**I1. Illustrations carry NO TEXT AT ALL** (L4, operator, 2026-08-18). 573 SVGs collapsed
to about 21, one per slug. Their words: *"illustrations should not have texts like in
other example websites that we target to look like for simplicity. So, that can also
reduce the cost of maintenance."* Where a label is genuinely load-bearing it moves into
the SURROUNDING HTML as a caption or heading, "and keep it rare".

**This binds Wave 4 directly.** Replacing the `costVisual` table and the `techDiff` table
with pictures is in scope; baking their text into the SVG is not. It also sidesteps the
whole resvg font trap, because a textless SVG needs no font.

**I2. No "defer"** (L2). Their words: *"Keep in mind 'defer' like words are not liked
here."* Ordering inside one change is legitimate and must be WRITTEN as ordering.
Postponement is not. If a piece genuinely cannot be done, say which piece and why, out loud.

**I3. Big-bang, gates RED-first** (L1). A gate that encodes a bug existing today goes in
red, so the fix and the gate prove each other.

**I4. The fake terminal is deleted from the homepage hero** (L5), because "neither
reference site puts a simulated artifact in its hero". Cutting the terminal scenes from
the videos is the VIDEO-SIDE CONTINUATION of a ruling already made on the site side.
Extend it, do not re-argue it.

**I5. Agent knowledge files must be self-contained** (L15). Their words: *"make agents
general! They should not depend on external md files!"* If this program writes or edits an
agent definition, inline the knowledge; never point at this suite.

**I6. No published Artifact** (L16). Markdown in the repo is the deliverable.

**I7. Sonnet for translations is deliberate** (L13). Do not "fix" the i18n ledger back.

## From `agent/programs/www-round5/`

**I8. `public/styles/main.css` is single-writer by decree** (`03-chrome-and-surfaces.md:8-13`).
3421 lines; two concurrent writers corrupt it. Wave 5 lives almost entirely in this file,
so Wave 5 has exactly ONE owner and never overlaps Wave 4.

**I9. The footer dark band is already diagnosed** (`03-chrome-and-surfaces.md:20-27`).
`main.css:2797-2806` re-points five custom properties on `.footer` but omits
`--color-bg-alt`, which `language-switcher.css:15` paints from. The decided fix adds
`--color-bg-alt` and `--color-hover` to that block, pointing at `main.css:471` and `:477`.
Wave 5 STARTS here rather than from scratch.

**I10. The section-surface browser gate was deliberately not shipped**
(`CHECKLIST.md:29-33`). It is unclaimed, and it is exactly the gate shape Wave 5 needs.

## From `agent/programs/www-simplification/research/`

**I11. The ROI calculator already has measured a11y defects.** `.sp-roi-size-btn` has no
`aria-pressed` (`RESEARCH-primitives.md:277`); three unlabelled range inputs on
`/en/solutions/encryption` (`:338`); `roi-calculator.astro:8` does not load
`pricing-page.css` (`RESEARCH-pricing.md:632-633`); open question O2 asks whether the
calculator belongs inline at all (`:646-651`). Demoting it into a modal must CARRY these
fixes, not recreate the defects behind a button.

## From the plan documents

**I12. Media goes to R2, never into a commit**
(`PLAN-git-history-media-rewrite.md:30-31, :190-191`). A re-render committed to git
invalidates that plan's measured blob census. Select media by DIRECTORY PREFIX, never by
`*.mp4`: the 11 `assets/tutorials/browser-segments/*.mp4` are tracked build inputs (`:184-186`,
`:313-318`).

**I13. `/tmp` is non-durable, by written decision** (`PLAN-git-history-media-rewrite.md:214`).
Wave 1's guard pushes agent-browser output OUT of the repo, and must therefore be scoped
to DISPOSABLE artifacts. Evidence that has to survive a reboot belongs in the program
`checkpoints/` directory, not in `/tmp`.

**I14. New hook rules belong in `.claude/hooks/trapguard/`, not in a 19th `block-*.sh`**
(`PLAN-trap-enforcement.md:280-286`). Every Bash call already spawns about 200 processes,
18 `bash` plus roughly 10 forks per hook that sources `command-scan.sh`, with NO
PreToolUse timeout (`:270-278`). trapguard is registered exactly twice
(`dispatch.py --pre-bash` / `--post-bash`) and already exists on disk. Do not migrate the
existing 18 hooks (`:299-300`). **This is a decision point, not a settled fact: the plan is
a draft and unowned, and a trapguard rule is invisible to `check-hook-integrity.sh`, whose
globs are `block-*.sh` across `pre-bash|pre-edit|pre-ask` only. See README decision 3.**

**I15. `private/growth` is deliberately outside console CI**
(`PLAN-testing-surface-audit.md:632-635`): *"separate repos, not submodules... those
pipelines carry their own risk."* Do NOT wire video_pipeline, Remotion or the Docker GPU
images into console CI on this program's own authority.

**I16. The www content, SEO, tutorial and video gates are suspected vacuous**
(`PLAN-testing-surface-audit.md:626-630`), about 20 `check:ci-*` left unaudited and
suspected of skipping when a build artifact or media manifest is absent. Assume the video
changes may pass gates that cannot fail, and plant a control before believing any green.

**I17. Do not add a seventh island that reads locale from `window`**
(`PLAN-ssr-nav-locale.md`). `BaseLayout.astro:364` mounts islands with no `lang` prop and
six are already affected; the decided direction is to pass `lang` explicitly. A calculator
modal must follow that.

**I18. Sentence wrapping is decided and partly shipped**
(`PLAN-sentence-aware-wrapping.md:51-53, :145-152, :157`). The mechanism is a build-time
`<span class="sentence">`; the component set is fixed; `Sentences.tsx` takes `lang` as a
PROP. The rehype pass SKIPS any subtree under `svg`, so new illustrations are outside it
by prior decision. `check:ci-sentence-wrapping` has shipped and fires on copy edits.

## From the ci-overhaul program

**I19. Blocking versus warning is an OPERATOR ruling, not the implementer's**
(`06-progress.md:4394-4397`). A blocking guard that "would be wrong most times it fires
teaches people to route around it". Wave 1 must ask, not assume.

**I20. Do not narrow a guard to kill a false positive** (`06-progress.md:5241-5247`,
operator, 2026-08-25). Four options were scored and the false positive was KEPT, because
"it fails LOUDLY while every narrowing fails SILENTLY". Six narrowings were reverted.
Exempting heredoc bodies was named "the most tempting option and the worst".

**I21. Registry and static gates are never path-filtered** (`02-v1-economics.md:245-248`,
`gate-author.md:104-106`). Do not add `paths:` to a manifest entry to make it cheaper.

**I22. Control-first, always.** "A gate you have not seen fail is not a gate"
(`gate-author.md:12-16`). Plant the violation on the real tree, watch it go red, remove it,
confirm green. A control that does not fire is a claim about your control first
(`:32-37`). Register every new gate in `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`
with a PINNED DIAGNOSTIC SUBSTRING, not merely an exit code.

**I23. For every command a hook suite asserts is BLOCKED, assert that
`echo '<that command>'` is ALLOWED** (`06-progress.md:5227-5232`). A guard refusing an echo
is matching on mention, not execution. A 2026-08-27 sweep found 17 of 48 cases doing this.
