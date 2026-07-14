# P4 gate review — independent verdict

**Reviewer:** independent gate (task #10), cold shell, read-only w.r.t. the product.
**Tree:** `/home/muhammed/monorepo/console-gate`, pinned to console `88002b188`, renet `ea650bc`, account `909159f`.
**Environment:** own `npm install && npm run install:natives` at root, plus `private/account` and `private/account/web` (their own lockfiles — Note E).
**Date:** 2026-07-13.

---

## VERDICT: **FAIL**

**Read this part first, because the headline is misleading on its own.**

**The architecture of this wave is sound, and in places it is the best work in the program.**
Five of the six judgments only a gate can make came back clean, including every one that is
hard to fake: the mapping holds in both directions, the guardrails orphaned nothing, the
policy layer is correct *and* its new gate can genuinely fail for the right reason. I went
looking for a rotten foundation and did not find one. Nothing below is a design defect.

**It fails on execution, and it fails hard enough that it cannot be recorded as done.** The
wave's authors all reported success. In a cold shell, on their own snapshot:

- **`npm run ci` cannot pass.** Three independent gates are red — `lint`/`check:lint` (**59
  errors**), `check:cli-examples` (**88 errors**), `check:cli-docs` (**2 errors**). That is
  **149 errors**, and I attributed every failing file to the P4 commit itself. This is not
  inherited debt and it is not the sanctioned deferral.
- **The reshaped CLI's front door is broken.** All **five** examples printed by `rdc --help`
  are pre-P4 syntax. Not one of them runs. The first thing a user or an agent sees from this
  wave is five commands that error.
- **The renet i18n baseline was breached**, and 41 user-facing strings were laundered out of
  translation — past a gate that is green *because* they were laundered.
- **Four of the five carried-debt items exist nowhere but the gate brief**, which is a session
  scratch file. They would be lost when this session ends.

Every one of these is mechanical. There is no rework, no redesign, no rollback. I would expect
a competent day to clear the lot. But "a day of work remains" and "done" are different claims,
and the wave is currently making the second one.

---

## Findings, ranked by severity

### F1 — HIGH — `rdc --help` advertises five commands and none of them run

`packages/cli/src/cli.ts:352-356`

```
$ rdc machine query --name server-1             Show machine status
$ rdc term connect -m server-1 -r my-app        SSH into repository
$ rdc repo up --name my-app -m server-1          Deploy repository services
$ rdc repo sync upload -m server-1 -r my-app     Upload files to repository
$ rdc repo sync download -m server-1 -r my-app   Download files from repository
```

Verified live against **this tree's own build** (`./rdc.sh`, not an installed binary — the
oracle must be the version being shipped):

| the CLI's own example | what the CLI does with it |
|---|---|
| `rdc machine query --name server-1` | `error: unknown command 'query'` — exit 1 |
| `rdc repo up --name my-app -m server-1` | `error: unknown option '--name'` — exit 1 |
| `rdc term connect -m server-1 -r my-app` | `error: unknown option '-m'` — exit 1 |

`machine query` became `machine status` (§6.1). `--name`/`-m`/`-r` became positional refs
(§2.2). And `git diff cc5329316..88002b188 -- packages/cli/src/cli.ts` shows **the examples
block was never touched by the P4 commit**: the commands were renamed out from under their own
help text.

**Blast radius:** every user and every agent, on first contact — and it propagates, because the
`.claude/skills/rdc/` reference and the marp cheat sheet teach the same dead syntax (F3).

**Exact fix:** rewrite the five lines to the shipped contract — `rdc machine status server-1`,
`rdc term connect my-app`, `rdc repo up my-app`, `rdc repo sync upload my-app --local ./src`,
`rdc repo sync download my-app --local ./out`. `check:cli-examples` already flags exactly these
five lines, so the gate will confirm the fix.

**Why no gate caught it:** one did. `check:cli-examples` has been red the whole time (F3).

---

### F2 — HIGH — `lint` / `check:lint` red: 59 errors, every failing file P4's own

`npm run lint` → **exit 1, 59 problems (59 errors, 0 warnings)**.
`npm run check:lint` → **exit 1** (same 59; it is `eslint --max-warnings 0`).

This alone blocks `npm run ci`. I cross-referenced every failing file against
`git diff --name-only cc5329316..88002b188` (270 files): **all of them are P4-touched.** Not
one is inherited.

By rule:

| rule | count |
|---|---|
| `@typescript-eslint/no-unnecessary-condition` | 14 |
| `@typescript-eslint/no-unused-vars` | 11 |
| `sonarjs/cognitive-complexity` | 8 |
| `@typescript-eslint/consistent-type-assertions` | 8 |
| `custom/no-hardcoded-nullish-defaults` | 4 |
| `unicorn/prefer-string-replace-all` | 3 |
| `@typescript-eslint/require-await` | 3 |
| `custom/require-command-summary` | 2 |
| `max-lines`, `n/no-positional-cli-syntax`, others | rest |

The concentration is diagnostic — these are the reshape's own seams:

- **`packages/cli/src/commands/machine/status.ts:606` — `max-lines`: 548 > 512.** This is the
  command that *absorbed* `machine containers`/`services`/`repos` (§6.1 merged-into). The merge
  blew the file budget.
- **`packages/cli/src/commands/datastore.ts:572` — `max-lines`: 523 > 512**, plus 15 further
  errors in that one file (8 × unnecessary optional chain, 3 × unused `record`, 2 ×
  cognitive-complexity, 2 × hardcoded `"rbd"` in nullish coalescing).
- **`packages/cli/src/commands/backup.ts:259` — `custom/require-command-summary`:** *"Top-level
  command description (62 chars) is below 100 characters. Write a detailed description for AI
  agent discovery and add `.summary()`."* `backup` is the **new top-level noun this wave
  created** (w2a), and it does not satisfy the repo's own rule for new nouns.
- **`packages/cli/src/commands/repo-batch-utils.ts:339` — `runBatchParallel` defined but never
  used**, and `DEFAULTS` imported but never used: dead code left behind by the reshape.
- `mcp/custom-tools.ts:9` — `WRITE_TIMEOUT` unused. `mcp/tool-factory.ts:232` — complexity.
  `repo-create-placement.test.ts` — 8 × type-assertion style (a new test file).

**Exact fix:** `npm run lint` and work the list; 4 are `--fix`-able. The two `max-lines`
violations need a split, which is a real (small) refactor — `machine/status.ts` is the natural
one to split by section flag.

---

### F3 — HIGH — `check:cli-examples` red: 88 errors, and the deferral does not cover it

`npm run check:cli-examples` → **exit 1, 88 errors across 11 files.**

| file | errors | inside the deferred `packages/www/src/content/**`? |
|---|---|---|
| `packages/www/src/marp/rdc-cheat-sheet.marp.md` | 58 | **No** — `src/marp/` |
| `packages/json/templates/monitoring/heartbeat/README.md` | 6 | **No** — shipped template |
| `packages/cli/src/cli.ts` | 5 | **No** — the CLI itself (= F1) |
| `.claude/skills/rdc/backup.md` | 4 | **No** — agent-facing skill reference |
| `packages/www/src/components/PricingTrustSection.astro` | 4 | **No** — component |
| `.claude/skills/rdc/SKILL.md` | 3 | **No** — agent-facing skill reference |
| `docs/design/06-cli-reshape.md` | 3 | false positive (F10) |
| `private/renet/cmd/renet/dev.go` | 2 | **No** |
| `docs/design/spec/03-cli-contracts.md` | 1 | false positive (F10) |
| `packages/cli/src/i18n/locales/de/cli.json` | 1 | false positive (F10) |
| `private/account/web/src/i18n/locales/en/machines.json` | 1 | **No** |

**83 of the 88 are outside `src/content/**` entirely.** The sanctioned deferral names
`validate-docs-cli-usage` on `packages/www/src/content/**`; this is a *different gate* over a
*wider tree*. It cannot be waved onto the P7 docs ticket.

**Attribution — this is not inherited debt.** Every error is `Unknown option --name / -m / --up`
— flags that were **valid before P4**. These files were *correct* until the reshape deleted the
flags. P4 broke this gate; it did not find it broken.

The worst class is agent-facing: `.claude/skills/rdc/` teaches
`rdc repo push <repo> --to-machine <target> --up`, and `--up` **died on `push`** (§6.5, U3).
Those files are what *this program's own agents* read to drive the CLI.

**Exact fix:** regenerate the skill reference (`generate-skill-reference.ts`); rewrite the cheat
sheet, heartbeat README, `PricingTrustSection.astro`, `dev.go` and the account locale to
positional refs.

---

### F4 — MEDIUM-HIGH — renet i18n baseline breached, with user-facing strings laundered

Brief's judgment 5: *baseline still 2970; growth only via the sanctioned internal-error-wrap class.*

- `private/renet/pkg/i18n/baseline.json` at the P3 gate commit `c7e187a`: **2726** raw entries.
- At the P4 snapshot `ea650bc`: **2818** raw entries (**+106 added**, −14 removed).
- Raw→tool offset is a constant ~+226 (established in the P3 gate review), so 2818 raw ⇒
  tool-count **≈3044**, against the grandfathered **2970**. `docs/design/09-implementation-phases.md:497`
  still asserts 2970.

The 106 additions, by extractor pattern:

| pattern | count | class |
|---|---|---|
| `fmt.Errorf` | 65 | sanctioned (internal error wrap) |
| `fmt.Printf` | 18 | **user-facing stdout** |
| `cobra.Short` | 11 | **user-facing command help** |
| `fmt.Fprintf` | 4 | **user-facing** |
| `fmt.Sprintf` | 3 | **user-facing** |
| `errors.New` | 2 | **user-facing** |
| `log.Info` | 2 | **user-facing** |
| `fmt.Println` | 1 | **user-facing** |

**41 of 106 are outside the sanctioned class** — the `renet job *` and `renet datastore *`
surfaces. Examples: `cobra.Short` *"Cancel a running job"*, *"List jobs in the spool, newest
first"*, *"Open and mount a repo's per-volume LUKS images on an attached datastore"*;
`fmt.Printf` *"Opened %d volume(s) of repo %q on %q"*, *"Adopted %q (image %s/%s) [detached]"*.
That is command help and program output — precisely what i18n exists for — and putting them in
the baseline excludes them from translation **permanently**. renet commit `00dd0b0` is titled,
in as many words, *"chore(i18n): add new datastore command strings to the baseline."*

**Why the gate is green:** the baseline mechanism only fails on findings *beyond* the baseline.
`check:ci-renet` passes **because** the violations were added to it. The gate cannot fail for
this reason by construction — and renet's own `pkg/i18n/extract_internal_test.go:13` names this
exact failure mode in a comment ("launder them into the baseline permanently", issue #54).

**Exact fix:** remove the 41 non-`fmt.Errorf` entries from `baseline.json` and put those strings
in the i18n catalogue. If the operator would rather accept them, that is a ruling to take
*explicitly*, and the 2970 figure must be re-baselined to ~3044 with the reason recorded — not
left contradicting the tree.

---

### F5 — MEDIUM — four of the five carried-debt items are recorded nowhere durable

The brief says: *do not re-litigate the carried debt, but DO verify each is actually recorded
somewhere durable.* It is not.

| item | recorded? |
|---|---|
| **#68** adoption path | **Yes** — `docs/design/spec/03-cli-contracts.md:3369` |
| **#30** metrics-server APIService | **Yes** — `docs/design/README.md:36`, `spec/10-p3-gate-review.md:169` |
| **#82** adoption path | **No** — absent from `docs/` entirely |
| **#79** agent-node CSI | **No** — absent from `docs/` entirely |
| the 16 datastore-declaration bypass sites | **No** — absent from `docs/` entirely |
| kube size-license semantics | **No** — absent from `docs/` entirely |

Searching the whole repo for bug numbers 67–85 in `docs/` returns exactly **`#68` and `#76`**.
The four missing items appear in **no design doc, no spec, no committed ledger** — only in
`reports/p4-gate-brief.md`, a session scratch file outside the repo. When this session ends,
they are gone.

**Blast radius:** these are the items P5 is supposed to *start from*. A carry-in list that lives
only in the previous session's briefing is not a carry-in list.

**Exact fix:** add a "P5 carry-in" table to `docs/design/09-implementation-phases.md` (which
already carries the bug ledger at :466) with all five, or open GitHub issues and reference them.
One commit.

---

### F6 — MEDIUM (structural) — `command-tree.json` has no freshness gate, and nine validators trust it

`packages/cli/scripts/command-tree.json` is a **committed** artifact consumed by at least nine
checkers: `check-design-tree.ts`, `check-cli-docs.ts`, `check-i18n-untranslated.ts`,
`validate-cli-examples.ts`, `scripts/lib/positional-cli-detector.ts`, the two ESLint rules
(`no-positional-cli-syntax`, `no-undefined-cli-flags`), and www's `validate-docs-cli-usage.js` /
`generate-cli-docs.js` / `cli-reference-catalog.js`.

**Nothing regenerates it and diffs it.** `export:command-tree` exists only as a package script
(`packages/cli/package.json:12`); no `.ci/` script and no workflow invokes it. Contrast
`contract.json`, which **is** regenerate-and-diffed by `.ci/scripts/quality/check-cli-contract.sh`.

**I verified it is currently fresh** — I regenerated it from the live Commander tree and diffed
byte-identical — so today's greens from those nine are meaningful. But the *gate* is absent. An
author who changes the tree, is forced by `check:ci-cli-contract` to regenerate `contract.json`,
and forgets `export:command-tree`, leaves all nine validators grading **the previous CLI** —
silently, and greenly. That is exactly the shape this program has been bitten by seven times: a
validator's blind spot is indistinguishable from a passing check.

**Exact fix:** a `check:ci-command-tree` that regenerates to a temp dir and diffs (~15 lines,
copy `check-cli-contract.sh`), wired into the `ci` chain.

---

### F7 — LOW-MEDIUM — three stale `COMMAND_REGISTRY` entries

`packages/cli/src/config/command-registry.ts:36-38`

```ts
containers: { experimental: true },
services:   { experimental: true },
repos:      { experimental: true },
```

All three were **merged into `machine status`** (§6.1). Verified against the live Commander
tree: `machine containers` / `machine services` / `machine repos` → **do not exist**. The
registry still declares them.

They fail *inert* — there is no command left to mis-gate — which is why nothing noticed. But
`COMMAND_REGISTRY` is one of the name-keyed lists P4 was required to re-key in lockstep, and
**no gate checks it for staleness** (`mcp-coverage.test.ts` reads it only for top-level
`experimental` prefixes).

**Credit where it is due:** the *other* half of this hole is genuinely fixed. Spec §4.10
recorded *"COMMAND_REGISTRY holds 13 domains while the live tree has 16 — `job`, `cluster`,
`credits`, `serve` are in no registry entry, so they are not MCP-checked at all."* That is now
**closed**: 18 registry domains, 0 live domains missing. Verified against the live tree.

**Exact fix:** delete the three entries; optionally assert registry-vs-tree in
`mcp-coverage.test.ts`, which already has the live-tree walk to do it.

---

### F8 — MEDIUM — `check:cli-docs` red (2 violations), turning `check:i18n` red

- `packages/www/src/content/docs/en/troubleshooting.md:142` — `rdc vscode connect -m <machine> -r <repo>` — unknown short flag `-m`
- `packages/www/src/content/docs/en/troubleshooting.md:182` — `rdc term connect -m server-1 -c "ls -la"` — unknown short flag `-m`

These two *are* in the deferred directory, so they are the same **class** as the sanctioned
deferral — but they are caught by a **different gate**, and `check:cli-docs` is a member of the
`check:i18n` chain, which is a member of `npm run ci`. The deferral as written does not keep
`npm run ci` green.

**Exact fix:** it is two lines — fix them (`rdc vscode connect <repo>`, `rdc term connect
server-1 -c "ls -la"`). If the team prefers to defer, the deferral note must name
`check:cli-docs` explicitly and carry this count, or it reads as an unexplained red forever.

---

### F9 — LOW — one leaf carries no MCP classification

`machine health` is the only leaf with neither an `mcp` block nor an `mcpExcludeReason` (its own
or an ancestor's). It is `experimental: true`, therefore registered hidden, therefore skipped by
`mcp-coverage.test.ts`'s tree walk and **not exposed** — it fails closed. Harmless in practice;
formally it is the brief's *"an unmapped leaf is an open question, not a default."*

**Exact fix:** one line — give it an `mcpExcludeReason` so the classification is a decision
rather than a side effect of being hidden.

---

### F10 — INFO — `validate-cli-examples` false positives (do **not** "fix" these documents)

Five of F3's 88 errors are the validator misreading things that are not examples. Recorded so
nobody edits a correct document to appease it:

- `docs/design/06-cli-reshape.md:63-65` — the §1 **tree drawing**
  (`rdc ops   up down status ssh setup check`) parsed as `rdc ops up` with positional junk.
- `docs/design/spec/03-cli-contracts.md:329` — `rdc storage browse s3-main` in a table cell; the
  trailing `` ` |`` is swallowed into the args.
- `packages/cli/src/i18n/locales/de/cli.json:967` — German prose (*"… führt `rdc config
  reconcile` **aus**."*) parsed as a positional argument.

The de/cli.json case is the instructive one: the validator scans **translated prose** for command
examples and cannot tell a German separable-verb particle from an argument. It will keep firing
as locales change.

---

## Gate results — per-check evidence, cold shell

| check | exit | evidence |
|---|---|---|
| `check:types` | **0** | `tsc -b` shared+provisioning+cli, + account `--noEmit` |
| `check:test-cli` | **0** | **132 files, 1867 tests passed** |
| `check:ci-console-coverage` | **0** | 194 tests passed (after installing account/web deps — Note E) |
| `check:ci-renet` (full) | **0** | …but green *because* of the baseline — **F4** |
| `go vet -tags "root ebpf_e2e" ./...` | **0** | tag-gated files compile |
| `gofmt -l` | clean | — |
| `check:ci-cli-contract` | **0** | contract regenerated from the live tree, byte-identical |
| `check:ci-command-planes` | **0** | 17 domains, 164 commands: 93 machine / 51 config / 20 other |
| `check:ci-design-tree` | **0** | **163 leaves, both directions** |
| `check:ci-i18n-placeholders` | **0** | 12 locales, 1838 keys, 22 056 comparisons |
| `check:ci-i18n-untranslated` | **0** | 12 locales, 1838 keys, min length 30 |
| `check:ci-i18n-command-parity` | **0** | English absolute + 12 locales |
| `check:ci-knip-blockers` | **0** | 50 suppression entries validated |
| `lint:unused` (knip) | **0** | — |
| `check:format` | **0** | — |
| `check:version` | **0** | — |
| **`lint`** | **1** | **59 errors — F2** |
| **`check:lint`** | **1** | **59 errors — F2** |
| **`check:cli-examples`** | **1** | **88 errors — F3** |
| **`check:cli-docs`** | **1** | **2 errors — F8** |

---

## The six judgments only a gate can make

**1. Mechanical mapping, both directions — PASS.**
Live tree (163 leaves, **regenerated from the live Commander tree**, not read from the committed
JSON) against `spec/03 §6`:

- **0** §6 target rows with no shipped command — every row resolves.
- **0** shipped leaves missing from §6 — all 163 dispositioned. (My parser first flagged 36; all
  36 are slash-notation rows — `config field get/set/unset/rotate/list`, `doctor / update /
  credits`, `ops` prose — each confirmed present by hand.)
- **0 zombies** — not one command dispositioned `deleted` or `merged-into` is still shipped. The
  deletions actually happened, which is the half nobody checks.

Flag-level deltas spot-checked against §5, all honored: `repo push` `--tag`/`--up` gone;
`repo fork` `--cluster`/`--to-cluster`/`--provider` gone; `repo log` and `repo diff` `--json`
gone; `repo sync upload` `-t` gone; `datastore status` `-m` gone; `term connect` container flags
gone; `doctor`/`credits`/`update` `--output` gone. (`repo up` **keeps** `-m` — this is *correct*:
§5 contracts it as the `--all --machine <m>` batch form. Not drift. I checked before filing.)

**2. Guardrail audit — PASS.** §4.10 says this is the list with **no stale-entry gate**, which
fails *silent*, so I checked every key against the live tree by hand: **0 stale
`COMMAND_METADATA` keys (of 141), 0 stale `COMMAND_PLANES` keys (of 51).** All **47** guarded
commands (`grandGuard`/`forkBlocked`/`agentBlocked`) resolve to live commands. The rename wave
orphaned nothing — the single most likely way this wave could have quietly disarmed itself, and
it didn't.

**3. Policy-glob audit — PASS, and the gate is real.** I extracted all **92 authored globs across
16 files** and matched each against the live contract: **0 stale globs in any authored policy
document.** Every apparent hit is the gate's own *negative fixture* or doc prose explaining the
hazard. (`vite.config.ts` is my own regex catching Vite's `fs.allow` — not policy.)

The gate itself survives the doctrine test — it can fail for the right reason:

- `services/serve/policy.ts:73` checks globs against
  `LIVE_COMMANDS = CLI_CONTRACT.commands.map(c => c.pathKey)` — the **generated contract**, which
  is itself regenerate-and-diffed against the live Commander tree. It asks the thing that decides.
- `policy-stale-deny.test.ts` drives the **real `authorize()`** with `deny: ['repo takeover']` —
  the *actual pre-P4 name* of `repo promote`, i.e. the rename that would really have fired — and
  asserts the executor refuses. It carries a negative control ("the detector must not cry wolf")
  and asserts the asymmetry: stale *allow* tolerated (fails closed), stale *deny* fatal.

This is the strongest engineering in the wave, and it closes the one classification system that
fails **open**.

**4. MCP exposure — PASS-WITH-NOTE.** Of 163 leaves: **68** `mcp`-exposed, **94** excluded (by an
`mcpExcludeReason` on the leaf or an ancestor), **1** unclassified (`machine health` — F9). **0**
carry both. `mcp-coverage.test.ts` was rewritten this wave to walk the **live Commander tree**
instead of the domain-granular `COMMAND_REGISTRY`, and — the part that matters — to treat an
**actionable parent** as runnable via `_actionHandler`, closing a real hole where `repo replicate`
*"carried an `mcp` block that produced no tool at all: the gate was satisfied by a declaration
that did nothing."* Exactly the right instinct.

**5. renet i18n baseline — FAIL.** See **F4**: 2818 raw / ≈3044 tool-count against 2970, and 41 of
106 additions outside the sanctioned internal-error-wrap class.

**6. Design-suite as-built — PASS.** `check:ci-design-tree` confirms `06-cli-reshape.md §1` is a
transcript of the shipped CLI in **both** directions (163 leaves; no phantoms, no omissions), and
it reads the tree rather than a prose summary. §6's completeness claim holds (judgment 1). The
only design-doc "errors" are F10 false positives. **The design docs are not stale** — which,
given how much of this wave's truth depends on them, is worth stating plainly.

---

## Sanctioned deferrals — recorded so they cannot be quietly forgotten

**D1. `validate-docs-cli-usage` on `packages/www/src/content/**` — 379 violations** (+ ~30
inherited em dashes). Deliberately deferred to **P7's docs rewrite**: fixing now means editing 60
English + 772 locale files twice. **Not counted as a failure in this verdict.** It must appear on
the P7 ticket carrying this count.

> **The deferral does not cover F3 or F8.** Those are *different gates* (`check:cli-examples`,
> `check:cli-docs`). 83 of F3's 88 errors are outside `src/content/**` entirely, and F8 is two
> lines. Do not let D1 absorb them.

**D2. Local-environmental only — not run, not counted:** `validate:tutorial-audio` (no R2
credentials), `check:actions`, `check:ci-release-state`.

---

## What "fixing this" looks like (recommended order)

1. **F2** — `npm run lint`; work the 59. Two `max-lines` splits (`machine/status.ts`,
   `datastore.ts`) are the only non-trivial ones.
2. **F1** — five lines in `cli.ts`. Highest user impact per character in the whole list.
3. **F3** — regenerate the skill reference; rewrite the cheat sheet, heartbeat README, `dev.go`,
   `PricingTrustSection.astro`, account locale.
4. **F8** — two lines in `troubleshooting.md`.
5. **F4** — a decision, not a keystroke: un-launder the 41 strings, or re-baseline 2970→3044 on
   the record.
6. **F5** — one commit: put the five carry-ins in `09-implementation-phases.md`.
7. **F6/F7/F9** — the three cheap durability fixes (freshness gate; three registry lines; one
   `mcpExcludeReason`).

Re-run: `lint`, `check:lint`, `check:cli-examples`, `check:cli-docs`, `check:ci-renet`. When
those five are green, this verdict flips to PASS.

---

## Notes on method

**Note E — `check:ci-console-coverage`'s first red was my environment, not the code.** It failed
with `Cannot find dependency 'jsdom'`: `private/account` and `private/account/web` carry their
own lockfiles and are not installed by the root `npm install`. After installing both, it is green
(194 tests). I record it because a fresh CI runner has the same trap — and when it springs, the
gate prints `Test Files no tests` with `Errors 1`, which a careless reader will not distinguish
from a pass. That is itself a small instance of the doctrine.

**Note F — on not filing false findings.** Two candidate findings did not survive contact:
`repo up` keeping `-m` (correct per §5's batch form), and 42 leaves apparently lacking MCP
classification (my exact-key check was stricter than the enforcement, which inherits
`mcpExcludeReason` from ancestors — the true number is 1). I checked both against the code that
decides before writing them down. The doctrine cuts both ways: an assertion that *cannot fail*
predicts nothing, but an assertion that fires for the *wrong* reason is just noise.

**On what I did not take on trust:** I regenerated `command-tree.json` from the live Commander
tree rather than reading the committed copy (F6 is why that mattered); I ran the CLI's own help
through this tree's `./rdc.sh` rather than any installed binary; I re-derived the MCP, plane,
guardrail and policy classifications from the live tree rather than from the counts in the design
docs; and I attributed every lint and example failure to a specific commit range before calling
it P4's. For every green above, I asked what would make it go red, and confirmed that thing was
reachable — which is how F4 (a gate that is green *because* the violations were absorbed into its
baseline) and F6 (a gate that would grade the wrong CLI and never know) were found.
