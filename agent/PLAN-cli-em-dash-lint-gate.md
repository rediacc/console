# PLAN: Bring packages/cli under the em dash gate
Status: done
Owner: e6500e92
Updated: 2026-08-19 (closed)

Scope: extend `scripts/check-em-dash-surfaces.ts` to cover `packages/cli`, drain the
reader-facing half to zero, baseline the rest, and close one hole in the existing gate that
this extension would otherwise inherit.

## 1. The verdict, and the tree evidence for it

**Extend the existing gate's surface table. Do not write a second gate.** Four reasons, all
checkable:

1. **A second gate cannot reach CI without a fourth wiring point, and the manifest already
   documents why that is hard.** `scripts/ci-runner/manifest.ts:2029-2035` records that
   `em-dash-surfaces` was first pointed at the AI-slop step, and `check:ci-parity` refused
   it because that step invokes its script **by path, not through npm**, so the chain would
   never have run in CI. The gate today rides `check:i18n`
   (`package.json:163`, which chains `npm run check:ci-em-dash-surfaces` defined at
   `package.json:215`), declared at `scripts/ci-runner/manifest.ts:2072-2081` as
   `kind: 'step'` on `.github/workflows/ci-quality.yml` job `quality-i18n` (line 984)
   step `i18n` (line 1043, `run: npm run check:i18n` at line 1045). Adding a surface needs
   **no new wiring at all**. A second gate needs three new points, and its only sensible
   host step is the same `i18n` step, which would put two scripts doing the same scan into
   one step.
2. **The load-bearing machinery is per-gate, not per-surface.** The id scheme (key path for
   catalogs, hash of the trimmed line for source), the shrink-only baseline, the per-surface
   floor, and the inline selftest are all one implementation. A second file duplicates all
   four and doubles the number of places the id scheme can drift. A baseline whose entries
   are minted by two different hashers is not drainable.
3. **The gate's founding defect was a split surface table.** Its header
   (`scripts/check-em-dash-surfaces.ts:5-14`) says the ban existed in
   `.ci/scripts/quality/check-content-quality.sh` and covered only
   `packages/www/src/content/{docs,blog}`, so the largest surfaces were invisible while the
   output stayed green. A second gate for `packages/cli` recreates exactly that shape: two
   tables, each true about its own files and silent about the other's.
4. **The CLI's own i18n gates are about key resolution, not prose.**
   `scripts/check-cli-i18n-key-usage.ts` resolves every `t('literal')` against
   `packages/cli/src/i18n/locales/en/cli.json` and reports orphan leaves;
   `packages/cli/scripts/check-cli-i18n-help-render.ts` renders `--help` for every Commander
   node and fails on a leaked raw key. Neither one reads a VALUE as prose. Em dash is a
   prose concern shared with `packages/www`, and the www half already lives in this gate.
   Subject match points at the em dash gate, not at the CLI i18n pair.

## 2. What is actually there, measured today

All counts below are in the gate's own units, produced by importing its exported
`scanSurface` and running it against the real tree, not by `grep`. The gate counts one
finding per catalog KEY and one per source LINE, so they are smaller than a raw character
count: `grep -roP '\x{2014}' packages/cli/src | wc -l` reports **1381 characters**, which is
**1263 gate findings (1260 distinct ids)**.

| candidate surface | kind | exts | files | findings | distinct ids |
| --- | --- | --- | --- | --- | --- |
| `packages/cli/src/i18n/locales` | catalog | `.json` | 13 | 264 | 264 |
| `packages/cli/scripts` | source | `.ts` | 11 | 50 | 50 |
| `packages/cli/src` | source | `.ts` | 476 | 999 | 996 |

Existing surfaces, for calibration (same probe, same run): www catalogs 13 files / 1887,
www src 136 / 37, `.claude/commands` 4 / 0, `.claude/hooks` 50 / 0. Total 203 files, 1924
findings, which is exactly the size of `scripts/data/em-dash-surfaces-baseline.json`. The
gate is green today; its twelve selftest checks pass and it prints
`No new em dashes across 203 file(s) in 4 surface(s)`.

The tree is live while this plan is being written. A second run twenty minutes later reported
202 files, because a concurrent session deleted one file under `packages/www/src` (135 rather
than 136); the finding counts did not move. Re-measure before acting on any figure here; the
counts are evidence for the shape of the decision, not values to assert in a test.

### 2a. The source half is 93 percent comments, and that changes the plan

Of the 719 findings in `packages/cli/src` outside `__tests__`, **669 are on lines whose
trimmed text starts with `*`, `//` or `/*`**. Only 50 lines are not comment-shaped, and
those 50 split further:

* **26 lines** are `mcpExcludeReason` values in `packages/cli/src/config/command-metadata.ts`
  (line 512 through line 1069). Two of them, lines 1014 and 1018, are byte identical
  (`mcpExcludeReason: 'Cluster membership mutation <dash> not an agent operation',`), so they
  produce **one** id, not two. Correction to the brief: `mcpExcludeReason` is **not printed
  anywhere**. The only readers outside the table are
  `packages/cli/src/commands/mcp/__tests__/mcp-coverage.test.ts` and
  `packages/cli/src/utils/command-policy.ts`, and nothing renders the string. It is an
  internal annotation, so `command-metadata.ts:848` is a weaker example than the brief
  assumed. It still drains at zero, because it is 26 hand-written lines and the cost is
  minutes.
* **20 lines** are genuinely shipped text: thrown error messages and `outputService` output.
  Verified examples, opened and read:
  `packages/cli/src/services/config/config-resources-resolve.ts:33,156,181` (ambiguous ref,
  fork restore refusal, did-you-mean), `packages/cli/src/services/cluster/cluster-fork.ts:305,422,685`,
  `packages/cli/src/services/cluster/cluster-kube.ts:151,152`,
  `packages/cli/src/services/cluster/cluster-membership.ts:217`,
  `packages/cli/src/services/cluster/repo-replicate-ops.ts:110,339,340`,
  `packages/cli/src/services/repo/prune.ts:247,254`,
  `packages/cli/src/commands/update.ts:220`,
  `packages/cli/src/services/update/background-updater.ts:240`,
  `packages/cli/src/commands/doctor.ts:198`,
  `packages/cli/src/utils/timeline.ts:328`,
  `packages/cli/src/commands/config/field.ts:88`, and
  `packages/cli/src/remote/repository/bashFunctions.ts:115`, which is a `#` comment inside a
  bash snippet that is written to the remote machine, so it ships too.
* The remaining **4 lines** are trailing comments after code
  (`packages/cli/src/utils/repo-context-guard.ts:101`,
  `packages/cli/src/utils/process-ancestry.ts:147`,
  `packages/cli/src/services/core/embedded-assets.ts:273`,
  `packages/cli/src/commands/mcp/tools.ts:76`), which the comment regex missed because code
  precedes them.

So the shipped-text backlog inside `packages/cli/src/**/*.ts` is **46 lines, 45 distinct
ids**. That is drainable in one editing pass, and it must be drained BEFORE the baseline is
written so those ids never enter it. This is the `.claude/skills` lesson from the gate's own
header (`scripts/check-em-dash-surfaces.ts:92-100`): fix the thing first, then baseline the
residue, or the baseline records the defect permanently.

### 2b. The CLI locale catalogs are translations, not generated copies

The brief asked whether the trap at `GENERATED_CATALOG_DIRS`
(`scripts/check-em-dash-surfaces.ts:114-132`) recurs here. **It does not, in that form.**
`packages/cli/src/i18n/locales/<lang>/cli.json` is not generated from `en/cli.json`. There is
no generator under `packages/cli/scripts` that writes them, and the one script that touches
them, `scripts/sync-translations.ts:23-26`, only fills **missing** keys with the English
value as a placeholder. Measured consequence: of the 233 em dash findings in the twelve
non-English catalogs, **zero** are English placeholders. Every one is real translated text.
So fixing `en/cli.json` does not clear the copies, and all 13 files belong in the surface.

Key-level overlap, measured:

* 31 keys carry a dash in `en/cli.json`.
* 233 findings across the 12 other locales, on 59 distinct keys.
* 192 of those 233 sit on keys English also dashes (the translator kept the dash).
* 41 are translator introduced, on keys English does not dash.
* 5 English dashed keys have no dashed translation at all.

`packages/cli/src/i18n/locales/.translation-hashes.json` is skipped automatically: `walk()`
at `scripts/check-em-dash-surfaces.ts:145-156` refuses any entry whose name starts with `.`.
That is why the probe reports 13 files where `find` reports 14.

### 2c. The trap that DOES recur, in a worse form

The double counting hazard here is not a sibling directory, it is the package root.
`packages/cli/dist`, `packages/cli/node_modules` and `packages/cli/test-results` all exist on
disk right now and all carry em dashes (`packages/cli/dist/services/audit.js`,
`node_modules/zod/v4/locales/he.js`, and so on). They are gitignored
(`.gitignore:7`, `.gitignore:2`, `.gitignore:107`), but **`walk()` does not consult
`.gitignore`**. A surface declared as `packages/cli` instead of `packages/cli/src` would
scan a build output that is a verbatim copy of the source, count every finding twice, and
then `--write-baseline` would bake the duplicates in, where shrink-only draining can never
clear them. This is the same failure the existing `GENERATED_CATALOG_DIRS` comment describes,
and it gets the same treatment: an assertion, not a comment.

A second instance: `packages/cli/scripts/command-tree.json` is written by
`packages/cli/scripts/export-command-tree.ts:48` from the live Commander tree, so its content
is a copy of the CLI descriptions. It carries zero em dashes today, and it must stay out of
the surface (the scripts surface is `.ts` only) so that a future regression in a description
is reported once, at its source, and not twice.

A third, outside this gate: CLI option descriptions also flow into
`.claude/skills/rdc/reference.md` through
`packages/cli/scripts/generate-skill-reference.ts`. `.claude/skills` is deliberately NOT a
surface (see the gate header). When it eventually joins, the residue must be measured
**after** this plan lands, or the same sentence is counted at its source and at its copy.

## 3. Surface table after this plan

Three entries added to `SURFACES` at `scripts/check-em-dash-surfaces.ts:69-77`:

```ts
{ dir: 'packages/cli/src/i18n/locales', kind: 'catalog', exts: ['.json'], minFiles: 10 },
{ dir: 'packages/cli/scripts',          kind: 'source',  exts: ['.ts'],   minFiles: 8  },
{ dir: 'packages/cli/src',              kind: 'source',  exts: ['.ts'],   minFiles: 300 },
```

**The first is nested inside the third.** `packages/cli/src/i18n/locales` sits under
`packages/cli/src`, and they are disjoint only because their extension sets do not intersect.
That is a one-character edit away from breaking: adding `'.json'` to the source surface makes
every catalog finding count twice, exactly the widening trap the gate already guards for www.
It gets a new structural invariant and a control that fires (section 5, test T3).

Floors, and why each number:

* **Catalog 10** matches the www catalog floor. 13 locales live; the floor catches a
  collapsed glob, not a deliberate locale change.
* **Scripts 8** against 11 live files.
* **Source 300** against 476 live files, of which 295 are outside `__tests__`. The number is
  chosen to sit **above** 295 deliberately: this plan decides that test files are in the
  surface, and a future edit that quietly excludes `__tests__` should trip a red floor and
  have to argue, rather than shrink the surface by 181 files in silence. A floor whose only
  job is to catch an empty glob is weaker than one that also catches a narrowing.

**Tests are in the surface.** 280 findings live under `packages/cli/src/**/__tests__/**`
(for example `packages/cli/src/commands/__tests__/repo-fork.test.ts`, 13). Two reasons.
First, the gate has no exclusion mechanism today, and adding one creates a second suppression
surface inside a gate whose whole design avoids that (the header at lines 16-22 says as
much about the bash gate's two existing hatches). Second, the standing repo rule is that the
em dash is an AI tell to be avoided everywhere, and test text is no less hand written than a
JSDoc block, which is already in scope for `.claude/hooks`. They ride the baseline, they cost
nothing to keep there, and no new machinery is invented to hide them.

## 4. What joins at zero, what rides the baseline

| surface | findings today | disposition | who drains it |
| --- | --- | --- | --- |
| `packages/cli/src/i18n/locales` | 264 (en 31, other 233) | **ZERO** | one Opus pass for `en`, two Sonnet sub-agents for the 12 locales |
| `packages/cli/scripts` | 50 | **ZERO** | one Opus pass, all 50 are JSDoc prose in 8 files |
| `packages/cli/src` shipped text | 46 lines / 45 ids | **ZERO**, drained before the baseline is written | one Opus pass |
| `packages/cli/src` residue | about 951 ids | **BASELINE** | nobody now, shrink only |

Why the catalogs join at zero rather than riding a baseline, given that www's 1887 catalog
findings are baselined: `packages/cli/src/i18n/locales/*/cli.json` is what `rdc --help`
prints, it is 264 findings rather than 1887, and the whole drain including the translation
cascade is a bounded job that fits in the session that adds the surface. That is the same
test the gate applied to `.claude/commands` and `.claude/hooks`, which drained 77 findings
rather than record "these instructions may break the rule" forever.

Why the `packages/cli/src` residue is baselined: 951 ids across 476 files, 93 percent of them
prose inside JSDoc where the dash is often doing real syntactic work in a technical
explanation. Rewriting that is not a mechanical edit, and a bad pass changes documented
meaning. It shrinks over time under the existing shrink-only rule.

## 4b. A SECOND hole, found 2026-08-19 while the gate was green

Steps 1 to 4 are committed. Before step 6 runs, one thing changed in the gate this plan
edits, and it changes how the new surfaces must be tested.

`test-gate-paths-exist.sh` failed the Security lane on this gate:

```
TIER-B scripts/check-em-dash-surfaces.ts:432: packages/www/src/x.tsx
```

That literal was a fixture inside the zero-surface selftest. `inZeroSurface` is pure string
comparison and never touches the filesystem, so the fixture names nothing on disk ON
PURPOSE, and the dead-path detector cannot tell that apart from a real constant pointing at
a file somebody deleted. The detector is right to be strict: it exists because gates
silently produced empty globs and empty file lists when their paths moved underneath them.

Fixed by deriving both fixtures from `ZERO_SURFACES` and `SURFACES` at runtime, which is
the form that detector documents as ignored, and is also the better test: a derived fixture
keeps exercising the real configuration instead of drifting the moment either list is
edited. The assertion was re-proved with a planted control (`startsWith(dir)` without the
trailing slash), which makes it fail as it should, and the file was restored byte-identical
afterwards.

**Consequence for steps 6 to 8, and the reason this is recorded here rather than in a
commit message.** The three surfaces this plan adds name REAL directories, so they are not
affected. But section 7's new selftest controls must NOT introduce synthetic path literals
for the `packages/cli` surfaces the way the www fixture did. Any fixture path that does not
exist on disk has to be assembled at runtime, or the Security lane goes red on a gate that
is otherwise correct, and the failure will look like it belongs to this plan's change
rather than to its test fixtures.

## 5. The hole this plan must close first

**`--write-baseline` has no idea which surfaces joined at zero.** `main()` at
`scripts/check-em-dash-surfaces.ts:445-451` writes every finding from every surface. The
zero-join of `.claude/commands` and `.claude/hooks` is recorded **only in a comment** at
lines 80-101. So today, if a session reintroduced an em dash into `.claude/commands` and then
ran `--write-baseline` for an unrelated reason, the finding would be baselined silently and
the comment would still claim the surface is at zero. Adding the CLI catalogs at zero would
inherit that hole and make it bigger, because the CLI catalogs are the surface most likely to
churn (thirteen files, every locale delta touches them).

**Fix, riding this change:**

```ts
/** Surfaces that joined at ZERO. No id from one of these may ever enter the baseline. */
const ZERO_SURFACES = [
  '.claude/commands',
  '.claude/hooks',
  'packages/cli/src/i18n/locales',
  'packages/cli/scripts',
];
```

Enforced in two places: `--write-baseline` refuses to write an id whose file sits under a
zero surface and names it, and a normal run fails if the baseline file already contains one.
Both are proved to fire in T6 below.

## 6. Execution order

The order is forced by `scripts/check-translation-hashes.ts`, which covers the CLI locales
(`LOCALE_CONFIGS` at line 49, entry at line 52) and runs inside the same `check:i18n` chain.
Changing an English value invalidates its crc32 in
`packages/cli/src/i18n/locales/.translation-hashes.json` (keyCount 1763, sourceLanguage en),
and that gate's own remediation text at lines 307-323 is explicit that re-hashing first
stamps the stale translations as current, which is the drift it exists to catch. It also
states, at line 321, that `private/growth/i18n_pipeline` **cannot** do this directory:
`config.py` targets `packages/www`, and pointing it here silently does nothing. So the twelve
locales are hand translated, by a Sonnet sub-agent, per repo model policy.

1. **Drain `packages/cli/scripts`** (50 findings, 8 files, all JSDoc). Opus, inline.
2. **Drain the 46 shipped-text lines in `packages/cli/src`** (section 2a). Opus, inline.
   Restructure with a comma, colon, period or parentheses. Do not substitute a spaced hyphen.
3. **Drain `en/cli.json`** (31 keys). Opus, inline.
4. **Drain the twelve locales.** Two Sonnet sub-agents, six locale directories each, disjoint
   file ownership, per the max-two-writers rule. Agent A owns `ar de es et fr it`, agent B
   owns `ja ko pt ru tr zh`. Each agent's job is both halves at once:
   * re-translate the 31 keys whose English changed in step 3, because their hash is now
     stale, and
   * remove the dash from the findings its locales already carry (41 of the 233 are
     translator introduced on keys English never dashed, so they do not come along for free).
   Per-locale finding counts to hand each agent: ar 23, de 24, es 17, et 8, fr 19, it 7,
   ja 18, ko 3, pt 10, ru 57, tr 23, zh 24.
   **Punctuation advice does not transfer.** English "replace the dash with a colon" is wrong
   guidance for ja and zh, which have their own full-width punctuation and often want a
   clause break or a particle rather than any mark, and for ar, where the text runs
   right to left and a dash surrounded by Latin-script product names is a bidi hazard.
   Instruct each agent to produce idiomatic native punctuation for the language, not a
   transliteration of the English fix, and forbid it from touching keys, key order, ordering
   (these files are alphabetically sorted), placeholders, or any file outside its six
   directories.
5. **Re-hash**: `npm run i18n:generate-hashes`. Only after step 4, never before.
6. **Add the three surfaces and `ZERO_SURFACES`** to `scripts/check-em-dash-surfaces.ts`, plus
   the new selftest checks in section 7.
7. **Regenerate the baseline**: `npx tsx scripts/check-em-dash-surfaces.ts --write-baseline`.
8. **Verify the baseline delta by shape, not by size** (section 8).

## 7. Tests, each with the defect it is planted against

Every check below runs inline on every invocation, in `selftest()`, in the same temp-root
style the file already uses. A check that cannot fail is worse than no check, so each one is
listed with the exact plant that makes it go red.

**T1. A CLI catalog finding is reported by key path.**
Plant: write `<root>/packages/cli/src/i18n/locales/de/cli.json` containing
`{"commands":{"repo":{"fork":{"description":"Forkt ein Repository <dash> sofort"}}}}`.
Expect exactly one finding with `where === 'commands.repo.fork.description'`.
Control half: `<root>/packages/cli/src/i18n/locales/en/cli.json` with the same shape and no
dash reports nothing. Fires if the catalog surface is misdeclared as `source`, in which case
`where` is a line hash instead of a key path and the assertion on the key path fails.

**T2. A CLI source finding is reported, and its id survives a line move.**
Plant: `<root>/packages/cli/src/services/foo.ts` containing
`throw new Error('Repository not found <dash> did you mean "web"?');`. Expect one finding.
Then rewrite the file with two unrelated lines prepended and require `idOf` to be unchanged.
Fires if anyone swaps the hash id for a line number, which would make a 951-entry baseline
churn on every unrelated edit and get regenerated wholesale.

**T3. No surface may be nested inside another with an overlapping extension set.**
This is the new structural invariant, and it is the one most likely to be broken by a
plausible edit. Implement as an exported predicate over any surface table:

```ts
export function overlappingSurfaces(surfaces: readonly Surface[]): string[]
```

returning a message for every pair where one `dir` is a path prefix of the other AND their
`exts` intersect.
Assert it returns empty for the real `SURFACES`.
Plant, and this is the part that makes it a control rather than a comment: call it with the
synthetic table
`[{dir:'packages/cli/src', exts:['.ts','.json'], ...}, {dir:'packages/cli/src/i18n/locales', exts:['.json'], ...}]`
and require exactly one violation. That synthetic table is the literal result of someone
adding `'.json'` to the CLI source surface.

**T4. The CLI source surface is `packages/cli/src`, never `packages/cli`.**
Two halves, because a string equality assertion alone does not prove the narrowing matters.
Half one: assert the declared dir equals `packages/cli/src`.
Half two, the behavioural plant: build a temp root containing BOTH
`<root>/packages/cli/dist/audit.js` and `<root>/packages/cli/src/audit.ts` carrying the same
dashed line, scan with `dir: 'packages/cli'` and require 2 findings, then scan with
`dir: 'packages/cli/src'` and require 1. That demonstrates the duplicate the wider surface
would create, using the real build-output path that exists in the working tree today.

**T5. The floors.** The existing generic floor checks already cover an empty glob and a
satisfied floor. Add: assert every CLI surface's `minFiles` is greater than zero (the
existing check already sweeps `SURFACES`, so this comes free once they are added), and add a
targeted plant for the narrowing case: a temp root with 5 `.ts` files under
`packages/cli/src` scanned against `minFiles: 300` must produce exactly one floor violation.

**T6. A zero surface can never be baselined.** Two directions, both planted.
Direction one: `--write-baseline` over a tree whose `.claude/commands/x.md` prose carries a
dash must REFUSE and name `.claude/commands`, rather than writing the id.
Direction two: a normal run against a baseline file that already contains
`packages/cli/src/i18n/locales/ru/cli.json:commands.repo.fork.description` must fail and say
the surface joined at zero.
Control for both: with a clean tree and a baseline holding only `packages/www` ids, neither
path fires. Without direction two, the guard is satisfied by a gate that simply never writes,
and a hand-edited baseline slips through.

**T7. Placeholders and structure are untouched by the drain.** Not a new check: after step 4,
run the existing chain, which already owns this. `npm run check:ci-i18n-placeholders`
catches a lost `{{placeholder}}`, `npm run check:ci-i18n-cli-key-usage` catches a key that
moved or vanished, `npm run check:ci-i18n-cli-help-render` catches a leaked raw key in
rendered help, and `npx tsx scripts/check-translation-hashes.ts` catches a locale left stale.
Naming them here because the drain touches 13 catalogs and the Sonnet agents are the most
likely source of an accidental structural edit.

**T8. The whole gate still refuses on a broken glob.** Existing behaviour, re-verified after
the surface table grows: temporarily point one CLI surface at a nonexistent directory and
confirm the run exits 1 with the per-surface floor message rather than reporting a clean
scan. Revert immediately; this is a manual probe during implementation, not a committed test.

Run the gate directly and read the streams separately when verifying:

```
npx tsx scripts/check-em-dash-surfaces.ts --selftest >out 2>err; echo $?
npx tsx scripts/check-em-dash-surfaces.ts           >out 2>err; echo $?
```

Note that stderr carries an unrelated `npm warn Unknown project config "minimum-release-age"`
line under `npx`, so an empty stderr is not the success signal; the exit code is.

## 8. Verifying the baseline delta

Do not accept the new baseline on its size. After step 7, compare old and new by shape:

* Every **added** id must match `^packages/cli/src/.+\.ts:` . Any added id under
  `packages/cli/src/i18n/locales`, `packages/cli/scripts`, `.claude/`, or `packages/www`
  means either a zero surface leaked (T6 should have caught it, so investigate the gate, not
  the baseline) or an unrelated regression rode along.
* **Nothing may be removed.** A removal means an existing www or `.claude` finding stopped
  being reported, which this change cannot legitimately cause, and would indicate the file
  was regenerated over a broken scan.
* Expected size is about 2875 entries (1924 existing plus roughly 951). Treat that as a
  sanity range, not an assertion; the exact number is whatever the shape check certifies.

Use `grep -P`, never `grep -E`, when checking these by hand. `grep` on this machine is ugrep,
and it returns silent false zeros for `-E` patterns that alternate `^` with a negated class,
which is precisely the shape a "lines not starting with packages/cli" check wants.

## 9. CI wiring

Three points, all already satisfied, listed because `check:ci-parity` and
`check:ci-gate-reachability-coverage` enforce them and a reviewer will ask:

1. **npm script**: `package.json:215`,
   `"check:ci-em-dash-surfaces": "tsx scripts/check-em-dash-surfaces.ts"`, chained into
   `check:i18n` at `package.json:163`.
2. **ci-runner manifest**: `scripts/ci-runner/manifest.ts:2072-2081`, id
   `check:ci-em-dash-surfaces`, `gate: true`, `leaves: ['scripts/check-em-dash-surfaces.ts']`,
   `ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-i18n',
   step: 'i18n' }`. The same script is also listed in the `leaves` of the chained `check:i18n`
   entry at line 199.
3. **workflow step**: `.github/workflows/ci-quality.yml:1043-1045`, job `quality-i18n`
   (line 984), step named `i18n`, `run: npm run check:i18n`.

**No fourth point is needed, and that is the argument in section 1 restated in wiring terms.**
Extending the surface table changes zero of these three. A second gate would add three new
entries and would have to be chained into a step that invokes it through npm, which is the
constraint that already rejected one placement of this gate.

## 10. Risks

* **The translation cascade is the largest single piece of work here**, roughly 31 keys times
  12 locales for the hash-driven re-translation, plus 41 translator-introduced findings, and
  it must complete before `i18n:generate-hashes` runs or the gate that would have caught
  stale translations is disarmed by the fix.
* **A Sonnet agent editing a sorted catalog can reorder or drop keys.** Constrain each agent
  to values only, to its six directories, and re-run the i18n chain in T7 afterwards.
* **`--write-baseline` is a loaded gun near a 951-entry baseline.** Run it exactly once, at
  step 7, after the drains, and certify the result by the shape check in section 8.
* **`command-metadata.ts` findings are cheap to drain and were mis-attributed as user facing.**
  Draining them is still correct, but do not cite them as shipped text in the commit message.


## 11. Outcome, 2026-08-19 (this plan is CLOSED)

All eight steps in section 6 are done and committed. Verified at close rather than
assumed:

* Steps 1 to 4, the drains, landed earlier in the session. Re-measured at close:
  `packages/cli/scripts` and `packages/cli/src/i18n/locales` both carry ZERO em dashes.
* Step 5: `check-translation-hashes.ts` reports "Translation hashes are up-to-date",
  and `check:i18n:completeness` passes, so the twelve locales were re-translated
  before the re-hash rather than stamped current over stale text, which was the
  ordering hazard this section existed to force.
* Steps 6 to 8 landed in `82def0b11`. Three surfaces added; the two clean ones are
  also in `ZERO_SURFACES`, so the zero-join is enforced rather than merely true on
  the day. Baseline 1923 to 2876 (+953), delta verified BY SHAPE: no entry in the
  baseline belongs to any zero surface.

Two things this plan did not predict, both recorded above rather than left to be
rediscovered:

* Section 4b, a dead path constant inside the very gate being extended, found only
  because `test-gate-paths-exist.sh` failed the Security lane while everything else
  was green. It constrained how the new surfaces' own fixtures had to be written.
* `nestedSurfaceOverlap()` was added beyond section 7's test list. Section 3 called
  the nesting "one character away from breaking" and left it as prose; a comment is
  not a control, so it became a check with a case in both directions.

Live proof the zero-join holds, run at close: planting an em dash in
`packages/cli/scripts` made `--write-baseline` exit 1 naming the file and the reason,
with the baseline unchanged at 2876. Removing it returned the gate to exit 0 over 718
files in 8 surfaces.

The residue in `packages/cli/src` (about 950 ids, JSDoc prose) stays baselined and
shrinks under the existing shrink-only rule. Nobody is assigned to drain it, by
design.
