# PROMPT: www round 5

Your mission is `agent/programs/www-round5/README.md`. Read it and follow its `## Read
order` before writing anything. Twelve operator observations about `packages/www`, planned
across four waves, measured live and not read off a file.

**Validate, do not believe.** Every `file:line` in that suite is a hypothesis until you
re-verify it against the tree, and the repo moved after the measurements were taken so line
numbers have drifted. Run the real thing, read stdout and stderr separately, and plant a
control before trusting any zero.

**Ask the decision points early, in one round.** `README.md` ends with two open ones, each
carrying a RECOMMENDED default that executes if unanswered. Four more are locked by the
operator and must not be relitigated. Do not block on the open two.

## Staffing

Opus is the default for coding sub-agents. **Fable for the challenging pieces and for all
planning agents.** Sonnet for translation and naturalization only.

Fable-tier in this program: the item-4 sentence-wrapping mechanism and its two gates; the
surface-colour ladder in wave A; the docs subcategory vocabulary in wave C.

At most **2 concurrent writers**, with disjoint file ownership stated verbatim in every
prompt and everything else explicitly forbidden. **`public/styles/main.css` belongs to wave
A alone**; it is 3,421 lines and two writers corrupt it. Forbid `git checkout`, `restore`,
`stash`, `clean` and any repo-wide sync or regenerate script in every writer prompt.
Investigation agents fan out freely. Spot-check every sub-agent report against the artifact
before building on it: they are accurate about intent and quietly wrong about placement.

## Program state

`~/.claude/projects/-home-muhammed-console/programs/www-round5/`

`MANIFEST.md` (update at every phase boundary), `reports/` (every writing or planning
sub-agent names its working report `reports/<phase>-<agent>.md`), `checkpoints/` (periodic
uncommitted-tree patches).

## Checklist and worklist

`agent/programs/www-round5/CHECKLIST.md` tracks four waves. Seed the shared worklist at
start, one item per wave, tagged with your 8-char session prefix and carrying the checklist
token. Path via `.claude/hooks/stop/worklist.py --path`:

```
worklist.py --add <me> 'cl:www-round5/w1 Wave A: chrome and surfaces'
worklist.py --add <me> 'cl:www-round5/w2 Wave B: marketing comprehension'
worklist.py --add <me> 'cl:www-round5/w3 Wave C: docs surface'
worklist.py --add <me> 'cl:www-round5/w4 Wave D: gates'
```

The Stop hook blocks any stopping session while a wave is neither ticked in the checklist
nor covered by such an item. Tick a `wN` only after the store item is ticked with probed
evidence; set `Status: done` when all four are ticked.

## Ground rules

**Everything stays local and uncommitted.** No commit, branch, push or PR unless the
operator asks in-task. The operator runs `/pr-babysit` at the end. Never
`git checkout/restore/stash/clean`: the tree carries other sessions' work. Repair forward.

**Testing and concurrency support are first-class deliverables.** Four gates are part of
the scope, not a wrap-up, and **a gate that cannot fail is a defect**: every one ships with
a control that mutates something real and is observed to go red.

**No em dashes in any authored text, in any language.**

Drive the real page with `agent-browser` before and after every change, with a distinct
`AGENT_BROWSER_SESSION` per agent. `/en` works; `/en/` 404s. Only one `npm run build:www`
at a time: it deletes 14 tracked `search-index*.json` from the shared tree while it runs.

## Definition of done

All twelve items addressed or explicitly named as not-done with a reason; before-and-after
browser measurements for items 1, 3, 5, 6, 8 and 9 at 1440 and 390, and for items 4 and 6
across locales including `/ar` and one CJK locale; axe on `/en` clears `.language-name`,
`.footer-version` and `.form-input` in both themes; four gates wired three-point with
`check:ci-parity` green and every control observed to fail; `CHECKLIST.md` fully ticked at
`Status: done`; the tree uncommitted.
