# PLAN: Make @rediacc/shared loadable as the ESM package it declares itself to be
Status: draft
Owner: 97604f47
Updated: 2026-08-14

Scope: `packages/shared` emits an ESM package that Node cannot load. Fix the source so
the emit is correct, switch the compiler to the mode that enforces it, and add a gate that
loads the real build the way Node would.

Everything below was measured against the tree at `/home/muhammed/monorepo/console` on
2026-08-14. Commands are reproducible. Where a number differs from the brief, the
methodology is stated so the difference can be adjudicated rather than argued.

---

## 1. The defect, reproduced

`packages/shared/package.json:5` declares `"type": "module"`, `:221` points `main` at
`./dist/index.js`, and `:24-217` declares a 48-key `exports` map. The build is plain
`tsc -p tsconfig.json` (`packages/shared/package.json:7`), and `tsc` emits relative
specifiers verbatim.

```
$ node --input-type=module -e "import { getStorageQuotaBytesForPlan } from './packages/shared/dist/index.js'; console.log(getStorageQuotaBytesForPlan('COMMUNITY'));"
Error [ERR_MODULE_NOT_FOUND]: Cannot find module
  '/home/muhammed/monorepo/console/packages/shared/dist/config/defaults'
  imported from /home/muhammed/monorepo/console/packages/shared/dist/config/index.js
  url: 'file:///home/muhammed/monorepo/console/packages/shared/dist/config/defaults'
```

Source of the emitted line: `packages/shared/src/config/index.ts:1` (`export * from './defaults';`).
Another, reachable only through a subpath export: `packages/shared/src/services/machine/index.ts:6`.

### How wide

A scan of every `import` / `export ... from` / dynamic `import()` specifier beginning with
`.` and lacking a `.js` / `.mjs` / `.cjs` / `.json` suffix, over `.ts` and `.tsx`,
excluding `.d.ts`:

| Tree | relative specifiers | extensionless | files |
|---|---|---|---|
| `packages/shared/src` | 375 | **131** | 49 |
| `packages/shared/dist/**/*.js` | 308 | **106** | 43 |
| `packages/shared/dist/**/*.d.ts` | - | **102** | - |

The brief quotes 145 and 120. The 14-specifier delta in both columns is the type-only
imports (`import type ... from './x'`), which I counted in the 131 and which vanish from
the `.js` emit but survive in the `.d.ts`. If the brief's counter included `.d.ts` files
in the source pass, or counted a multi-line import once per specifier rather than once per
statement, the numbers reconcile. Nothing about the plan depends on which figure is
canonical; the codemod in section 5 reports its own count and must rewrite every one it
finds, with zero unresolved.

The runtime blast radius, measured by importing every module in `dist` in a child Node
process:

```
current dist:  modules=174  imported=85  failed=89   (61 of them ERR_MODULE_NOT_FOUND)
```

The package is not marginally broken. Roughly half of it cannot be loaded at all.

---

## 2. Why it survived every gate, and this is three separate reasons

This matters because the gate in section 7 has to survive all three.

1. **`private/account`, `private/account/web`, `private/account/e2e`, `packages/www`** all
   typecheck under `moduleResolution: bundler`
   (`private/account/tsconfig.json:5`, `private/account/web/tsconfig.json:5`,
   `private/account/e2e/tsconfig.json:5`, and `node_modules/astro/tsconfigs/base.json`
   for www). Bundler resolution permits extensionless relative specifiers, so their
   typecheck sees a correct package. At runtime they are bundled by wrangler/esbuild,
   vite and astro, none of which use Node's resolver.

2. **`packages/cli`** is `module: NodeNext, moduleResolution: NodeNext`
   (`packages/cli/tsconfig.json:5-6`), which should reject every one of these specifiers.
   It does not, because of `"references": [{ "path": "../shared" }]`
   (`packages/cli/tsconfig.json:22`). `--traceResolution` shows what that buys:

   ```
   ======== Resolving module './defaults' from '.../packages/shared/dist/config/index.d.ts'. ========
   Using compiler options of project reference redirect '.../packages/shared/tsconfig.json'.
   Explicitly specified module resolution kind: 'Bundler'.
   ======== Module name './defaults' was successfully resolved to '.../dist/config/defaults.d.ts'. ========
   ```

   The project reference makes TypeScript resolve the shared `.d.ts` internals with
   **shared's own** `moduleResolution: bundler`, not the CLI's NodeNext. `--listFiles`
   confirms the CLI program pulls in 134 files from `packages/shared/dist` and zero from
   `packages/shared/src`, so the redirect is doing the resolving, not a `paths` fallback.
   The reference is a lie-amplifier: it makes the consumer agree with the producer's
   wrong setting instead of checking it.

3. **`packages/e2e-tests`** is NodeNext but `"type": "commonjs"`
   (`packages/e2e-tests/package.json:5`), and CJS resolution allows extensionless
   specifiers. It also has no project reference to shared.

Remove any one of those and the defect is still invisible. That is why "add a stricter
tsconfig" is a fix but not a gate.

### What a consumer without the redirect actually gets

A NodeNext probe resolving through `node_modules` and the `exports` map, `skipLibCheck: true`,
exactly as an out-of-repo consumer would:

```ts
import { DEFAULTS } from '@rediacc/shared/config';
import { getStorageQuotaBytesForPlan } from '@rediacc/shared';
export const a: string = getStorageQuotaBytesForPlan('COMMUNITY'); // deliberate error
export const b: number = DEFAULTS;                                  // deliberate error
```

| Package under test | Result |
|---|---|
| current build | `TS2305: Module '"@rediacc/shared/config"' has no exported member 'DEFAULTS'`. The **root** import is silently widened, and the deliberate `TS2322` on line 3 is **not reported at all**. |
| fixed build | both deliberate errors reported: `TS2322` on line 3 and `TS2322` on line 4. |

So the failure mode is not uniform. Subpath entry points hard-fail; the root entry point
silently degrades to `any` and swallows real type errors. Only the fix restores both.

---

## 3. What the same root cause is hiding behind it

Found while proving the fix, and the fix is incomplete without them.

### 3a. JSON imports have no import attributes (14 specifiers)

After adding `.js` extensions and rebuilding, the import-all sweep drops from 89 failures
to 42, and exactly **two non-test modules still fail**:

```
FAIL i18n/index.js    | ERR_IMPORT_ATTRIBUTE_MISSING | Module ".../dist/i18n/locales/ar/common.json" needs an import attribute of "type: json"
FAIL regions/index.js | ERR_IMPORT_ATTRIBUTE_MISSING | Module ".../dist/regions/data.json"          needs an import attribute of "type: json"
```

Sources: `packages/shared/src/regions/index.ts:15` and `packages/shared/src/i18n/index.ts:15-27`
(13 locale imports). This is the same class of defect: a source form that is legal under
`bundler` and illegal under Node ESM. `@rediacc/shared/regions` is consumed by
`packages/cli/src/services/provision/region-discovery.ts:9`, so it is on a live path.
Adding `with { type: 'json' }` is verified below to be accepted by tsc under both
resolution modes, by vite/vitest, and by esbuild.

### 3b. `dist` ships 40 compiled test modules, reachable through the wildcard exports

`packages/shared/tsconfig.json:12` includes `src/**/*.ts`, so `src/**/__tests__/**` is
compiled into `dist`, and the wildcard `exports` keys (21 of the 48 keys contain `*`)
make them importable as public subpaths. They are also unloadable outside vitest: 40 of
the 42 remaining failures above are test modules erroring on absent vitest globals.

This is not cosmetic for this plan. If the tests stay in `dist`, the new gate needs a
`**/__tests__/**` exclusion, and an exclusion is a hole a future regression can hide in.
Excluding them from the build removes the hole:

```
extensions + attributes, tests still built:  modules=174 imported=134 failed=40  (all under __tests__)
extensions + attributes, tests excluded:     modules=134 imported=134 failed=0   (0.33s)
```

Nothing outside `packages/shared` imports `@rediacc/shared/**/__tests__` (grep over
`packages`, `private`, `scripts`), and `knip.jsonc:22-26` scopes the shared project to
`src/**/*.ts`, not `dist`, so knip is unaffected. Cost and mitigation in section 5, part 3.

### 3c. Two findings outside this plan's fix (reported, not fixed here)

- `.claude/hooks/pre-bash/block-cli-bundle.sh:4` matches `node .*packages/cli/` anywhere
  in a command line. It blocked a read-only analysis invocation
  (`node scan.mjs packages/cli/src ...`) that never ran the CLI bundle. The guard should
  anchor on the executed script, not on any mention of the path. Reported to the lead for
  routing; it is not in this plan's file set.
- `@rediacc/shared/i18n` has no importer anywhere outside `packages/shared` itself. It may
  be dead. Not touched here.

---

## 4. Strategy scoring

Read: `packages/shared/tsconfig.json` (extends `../../tsconfig.json`, overrides only
`composite`, `rootDir`, `outDir`, `declaration`, `declarationMap`, `stripInternal`, `lib`)
and root `tsconfig.json:4-6` (`module: ESNext`, `moduleResolution: bundler`). Shared
therefore compiles ESM output under bundler resolution, which is precisely the
combination that permits an emit Node rejects.

### (a) Add `.js` extensions across the source

**Necessary in every scenario.** It is the only change that makes the emitted `.js` and
the emitted `.d.ts` correct at the same time, and the `.d.ts` half is what un-degrades
consumer types (section 2). Measured: 131 rewrites across 49 files, **0 unresolved**, of
which 12 are directory-index specifiers that become `<dir>/index.js`. After the rewrite,
`tsc` under the **existing** bundler settings is clean, so (a) alone is non-breaking.

Blast radius on the seven consumers: **none**, checked. `.js` specifiers resolve to `.ts`
/ `.d.ts` under `bundler` (probe: identical error set before and after, section 6),
under NodeNext ESM, and under NodeNext CJS.

Weakness: it is a one-time cleanup. Nothing stops specifier number 132.

### (b) Also switch shared to `module: NodeNext, moduleResolution: NodeNext`

The brief's worry was that nodenext "may cascade into type errors across the package and
its consumers". Measured, it does not.

Run against a pristine copy of `packages/shared/src` under NodeNext, error histogram:

```
102 TS2835   relative import needs explicit file extension (with a ./x.js suggestion)
  7 TS2834   same class, no suggestion available
 14 TS1543   JSON import needs a 'type: "json"' attribute
 63 TS2307   cannot find module (the './x.generated' specifiers, where the resolver
             mistakes '.generated' for an extension and cannot suggest a fix)
 43 TS7006 / 3 TS7031 / 2 TS2339   downstream implicit-any from the unresolved modules
```

Run against the **fixed** copy (extensions + JSON attributes) under NodeNext:

```
(no output)
```

Zero errors. And the emit is unchanged: compiling the fixed source with
`moduleResolution: bundler` and with `NodeNext` produces **byte-identical output**
(`diff -rq` over both `dist` trees, 134 modules plus maps and declarations, no
differences).

So (b) costs the 14 JSON attributes from 3a, which have to be fixed anyway because they
are a real runtime break, and buys permanent enforcement. It also propagates: because of
the project-reference redirect (section 2, reason 2), `packages/cli` will start resolving
shared's `.d.ts` internals under NodeNext instead of bundler, which turns the redirect
from a lie-amplifier into a second enforcement point.

Blast radius on consumers, checked in section 6. The one thing (b) breaks is `tsc`'s
coverage of shared's own tests if 3b is adopted; mitigation in section 5, part 3.

### (c) Bundler or post-build rewrite step

Rejected on evidence, not taste. A rewrite step would fix the emitted `.js` and `.d.ts`,
so it is not useless, but: it leaves the source stating something false, so specifier 132
still lands and is silently repaired; it adds a build stage between `tsc` and the
artifact, which every consumer's `build:packages` must now be trusted to run; and it
cannot be verified by reading the source, only by reading the artifact. Given that (a)+(b)
is 145 mechanical edits with a byte-identical emit and zero consumer impact, paying for a
build stage to avoid them is a worse trade. House rule also applies: one operator, no
external consumers, fix the root cause.

### (d) Declare the package bundler-only and drop the ESM claims

Rejected on evidence. It does not fix the defect that actually costs something today.
Dropping `"type": "module"` or the `exports` map does not change what the `.d.ts` files
say, so a NodeNext consumer without a project reference still gets `TS2305` on every
subpath and silently-`any` types on the root entry (section 2). It would also have to
delete a 48-key `exports` map that the CLI uses across roughly 20 distinct subpaths. It
costs more than (a) and fixes less.

### Recommendation

**(a) + (b) together, plus the JSON attributes and the test-exclusion from section 3.**
(a) is mandatory; (b) is 14 extra edits and an emit that does not move; together they turn
a latent defect into an invariant the compiler holds. The gate in section 7 is what keeps
it true when someone reverts the tsconfig.

---

## 5. The change

Six parts. Parts 1 and 2 are the fix, part 3 is the enforcement, parts 4 to 6 are the gate
wiring.

### Part 1: extensions (131 rewrites, 49 files, `packages/shared/src/**`)

Mechanical, and the codemod is written and proven (it produced every measurement in this
plan). Resolution order per specifier, relative to the importing file's directory:

1. `<spec>.ts` or `<spec>.tsx` exists -> append `.js`
2. `<spec>/index.ts` or `<spec>/index.tsx` exists -> append `/index.js` (12 cases)
3. `<spec>.json` exists -> append `.json`
4. otherwise: report as UNRESOLVED and change nothing

It must report `rewrites=131 files=49 unresolved=0`. A non-zero `unresolved` is a stop,
not a warning. Per the shared-checkout rule, run it on `packages/shared/src` only, then
re-read the whole diff, not just the specifiers it claims to have touched.

### Part 2: JSON import attributes (14 specifiers, 2 files)

`packages/shared/src/regions/index.ts:15` and `packages/shared/src/i18n/index.ts:15-27`:

```ts
import regionsData from './data.json' with { type: 'json' };
import ar from './locales/ar/common.json' with { type: 'json' };
```

Emit check (verified): tsc preserves the attribute verbatim into `dist/i18n/index.js`.
Toolchain check (verified): `esbuild --bundle --format=esm --platform=node` accepts it
(exit 0), and shared's own vitest suite is unchanged by it (section 6).

### Part 3: enforce it, and keep test typechecking

`packages/shared/tsconfig.json`, add to `compilerOptions`:

```json
"module": "NodeNext",
"moduleResolution": "NodeNext",
```

and add `"src/**/__tests__/**"` to `exclude` (currently `["node_modules", "dist"]` at line 13).

The exclusion has one real cost: `check:types` and `typecheck`
(`package.json:147` and `package.json:178`, currently byte-identical strings) run
`tsc -b packages/shared ...`, which is what typechecks shared's tests today. Restore that
with a sibling project and append it to both scripts, keeping them identical:

`packages/shared/tsconfig.test.json`
```json
{
  "extends": "./tsconfig.json",
  "compilerOptions": { "composite": false, "noEmit": true, "declaration": false, "declarationMap": false },
  "include": ["src/**/*.ts", "src/**/*.tsx", "src/**/*.json"],
  "exclude": ["node_modules", "dist"]
}
```

appended to both scripts as `&& tsc --noEmit -p packages/shared/tsconfig.test.json`.

**Fallback if part 3's exclusion is judged out of scope:** keep the tests in `dist` and
give the gate a `**/__tests__/**` skip list. This is strictly weaker, and the plan says so
out loud: a gate with an exclusion list has a place for the next regression to live. The
40 test modules are the only thing in `dist` that cannot be imported, so excluding them
from the build is what lets the gate assert `imported === total` with no carve-out.

### Part 4: the gate script

`scripts/check-shared-esm-resolvable.ts`. Design in section 7.

### Part 5: npm key

`package.json`, beside `check:ci-shared-constant-duplication` (`package.json:56`):

```json
"check:ci-shared-esm-resolvable": "tsx scripts/check-shared-esm-resolvable.ts",
```

### Part 6: manifest and workflow

`scripts/ci-runner/manifest.ts`, after the entry at line 174, matching the `GateSpec`
shape at lines 26-58:

```ts
{ id: 'check:ci-shared-esm-resolvable', run: 'npm run check:ci-shared-esm-resolvable', gate: true, needs: ['build:packages'], mutex: ['build-artifacts'], paths: ['packages/shared/src/**', 'packages/shared/package.json', 'packages/shared/tsconfig.json'], leaves: ['scripts/check-shared-esm-resolvable.ts'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-packages', step: "Shared package native ESM resolvability" } },
```

`needs: ['build:packages']` points at the existing prerequisite node
(`scripts/ci-runner/manifest.ts:258`); `mutex: ['build-artifacts']` matches the two gates
that already depend on it (lines 156-157).

`.github/workflows/ci-quality.yml`, a step in **`quality-packages`** (job at line 765),
after the setup block at lines 787-792:

```yaml
      - name: Shared package native ESM resolvability
        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
        run: npm run check:ci-shared-esm-resolvable
```

**The job choice is forced, not preferred.** The gate needs `packages/shared/dist`, which
is gitignored (`.gitignore:7`, `packages/*/dist`) and only exists where
`setup-workspace` is called with `build-packages: 'true'`. `quality-code` (line 429),
where the sibling `check:ci-shared-constant-duplication` step lives (lines 536-538), does
**not** set it, so the gate would fail there on a missing `dist`. `quality-packages` does
(line 792). The step name string must match exactly: `scripts/check-ci-parity.ts` verifies
the manifest's declared `step` against the parsed workflow, and all three of the npm key,
the manifest entry and the workflow step are required for the K/C/W triangle it asserts.

---

## 6. Blast radius on the seven consumers, checked

The seven `package.json` files declaring `@rediacc/shared`: `packages/shared`,
`packages/cli`, `packages/www`, `packages/e2e-tests`, `private/account`,
`private/account/web`, `private/account/e2e`.

| Consumer | Resolution | Measured effect of the fix |
|---|---|---|
| `packages/shared` (self) | bundler now, NodeNext after | tsc clean under **both**. Its own vitest suite: 40 files / 685 passed before, 40 files / 681 passed + 4 skipped in the scratch copy. The 4 are `describe.skipIf(!existsSync(FIXTURES_PATH))` at `packages/shared/src/subscription/__tests__/crypto.test.ts:396`, whose fixture path reaches into `private/account/tests/`; they skip because the copy sits outside the repo, not because of the change. |
| `packages/cli` | NodeNext, but resolves shared's internals through the project-reference redirect (`packages/cli/tsconfig.json:22`) | Green today and predicted green after: the redirect will hand it NodeNext instead of bundler, and the `.d.ts` will carry extensions. This is the one prediction that must be confirmed by running the real `npm run typecheck`; it is step 5 of section 8. Runtime is esbuild-bundled and unaffected; esbuild accepts the JSON attributes (verified). |
| `packages/www` | astro `Bundler` (`node_modules/astro/tsconfigs/base.json`) | none |
| `packages/e2e-tests` | NodeNext but `"type": "commonjs"` (`packages/e2e-tests/package.json:5`) | none; CJS resolution accepts both forms |
| `private/account` | bundler (`tsconfig.json:5`) | none |
| `private/account/web` | bundler (`tsconfig.json:5`) | none |
| `private/account/e2e` | bundler (`tsconfig.json:5`) | none |

The bundler arm was measured, not assumed: an identical probe compiled against the current
package and against the fixed package produced **identical error sets** (`diff` empty).

One caveat stated plainly. My out-of-repo probe of `packages/cli/src` against the fixed
package reported 82 errors against the current package and 0 against the fixed one, which
looks like a dramatic improvement. That probe reached the package through explicit `paths`
mappings, which bypasses the project-reference redirect the real build uses, so it
measures what an **external** consumer would see, not what `npm run typecheck` will print.
I am not claiming the fix removes 82 real errors from CI. The real number is whatever
step 5 of section 8 prints, and the honest prediction is zero-to-zero.

---

## 7. The gate

The class survived because nothing ever loaded the built package the way Node would. The
gate does exactly that and nothing cleverer: it is not a scanner for extensionless
specifiers, because a scanner is a proxy that a novel failure mode (the JSON attributes,
for instance) walks straight past. It imports the artifact.

`scripts/check-shared-esm-resolvable.ts`, following the house pattern at
`scripts/check-shared-constant-duplication.ts` (control at lines 73-85, zero-scan guard at
lines 91-99, failure report and exit at 102-111).

### Phase 0: control, three arms, before anything real runs

Built in a temp directory, torn down after. The detector is the same function used on the
real package.

| Arm | Fixture | Must report |
|---|---|---|
| bad-extension | `{"type":"module"}`, `index.js` = `export * from './leaf'`, `leaf.js` present | `ERR_MODULE_NOT_FOUND` |
| bad-json | `index.js` = `import d from './d.json'`, no attribute | `ERR_IMPORT_ATTRIBUTE_MISSING` |
| good | same package with `'./leaf.js'` and `with { type: 'json' }` | imports cleanly |

Two directions on purpose. The bad arms catch a detector that has gone blind; the good arm
catches a detector that has collapsed into reporting everything, which would make a green
run on the real package impossible to distinguish from a broken instrument. Any arm
disagreeing is `exit 1` with "instrument control did not fire", before the real scan
result is even computed.

### Phase 1: zero-scan guard

- `packages/shared/dist` must exist. Absent means "run `npm run build:packages`", exit 1.
  A missing build is an unrun check, never a pass.
- module count must clear a floor (assert `>= 100`; actual 134 after part 3, 174 before).
- the `exports` map must yield a non-trivial set of concrete targets (48 keys, 21 of them
  wildcards; assert `>= 20` non-wildcard targets, actual 27). Every non-wildcard target
  must exist on disk and must appear in the imported set, which additionally catches an
  `exports` entry pointing at a file the build stopped emitting.

### Phase 2: the real run, in a child process

A child `node` process imports every `.js` under `dist` via `pathToFileURL`, collects
`{ module, code, url }` for each failure, and prints a completion sentinel carrying the
count of modules attempted.

The child process is not a stylistic choice. In-process, a single `dist` module calling
`process.exit(0)` at import time would end the gate with a success code and no output, and
that reads as a pass. The parent therefore requires **both** the sentinel and
`attempted === expected`; a child that exits 0 without finishing is a failure. (Checked:
no current `dist` module calls `process.exit`, which is exactly the kind of fact that
stops being true without anyone noticing.)

Failures print the module path, the error code, and `err.url`, because `err.url` names the
exact unresolvable specifier and is what makes the fix obvious.

Cost: 0.33s for 134 modules. The gate's real cost is the `build:packages` it depends on,
which `quality-packages` already pays.

### Proving it fires, with an over-eager mutation

The blind mutation to avoid is breaking `dist/index.js`: the root entry point is what a
smoke test would already catch, so its red proves nothing about coverage of the 47 other
export subpaths.

**Mutation 1 (the load-bearing one).** In a copy of the tree, revert
`packages/shared/src/services/machine/index.ts:6` to `export * from './parsing';`.
That module is reachable only through `./services/machine` and the `./services/*`
wildcard, never from the root index. Rebuild, run the gate.

- Expected RED, naming `services/machine/index.js`, code `ERR_MODULE_NOT_FOUND`, url
  ending `/dist/services/machine/parsing`.
- Restore, rebuild, run: expected GREEN.

Both directions are required. A case that is red on the untouched tree is red under every
mutation and demonstrates nothing; that is the failure
`.ci/scripts/test/mutate-check.sh` exists to prevent (see its header, lines 7-14), and its
rule about mutating a **copy** rather than the live tree applies here with extra force
because this checkout is shared with other sessions.

**Mutation 2 (the JSON arm).** Drop ` with { type: 'json' }` from
`packages/shared/src/regions/index.ts:15`. Rebuild. Expected RED on `regions/index.js`
with `ERR_IMPORT_ATTRIBUTE_MISSING`. Restore, expected GREEN. This proves the gate covers
a class that no extension-scanner would see, which is the argument for importing the
artifact instead of reading it.

**Mutation 3 (the control is not the only thing working).** Neuter the phase-0 control,
then run mutation 1. The gate must still go red. If it does not, the control is carrying
the gate and the real scan is decorative.

Record the three verdicts in the PR body. `.ci/scripts/test/gates/` is not required here:
that harness is for the 57 `qualityGateTest` entries, and this gate declares
`ci: { kind: 'step', ... }`, which `scripts/check-ci-parity.ts` verifies directly against
the workflow.

---

## 8. Verification sequence

Run in order. Steps 1 to 3 are the defect closing; 4 to 9 are the existing surface staying
green.

**1. The raw Node import, before and after.**
```
$ node --input-type=module -e "import { getStorageQuotaBytesForPlan } from './packages/shared/dist/index.js'; console.log(getStorageQuotaBytesForPlan('COMMUNITY'));"
```
before: `ERR_MODULE_NOT_FOUND ... url: file://.../dist/config/defaults`
after (requires `npm run build:packages` first): `10737418240`

**2. Every module in the artifact loads.** The new gate, run directly:
```
$ npm run check:ci-shared-esm-resolvable
```
Expected: `✓ ... 134/134 modules imported, 27 exports targets resolved; controls fired`.
Before the fix the same command must print 89 failures including 61 `ERR_MODULE_NOT_FOUND`;
confirm that once, so the gate is known to have had something to catch.

**3. The three mutations of section 7,** each with both directions.

**4. Shared's own suite and typecheck.**
```
$ cd packages/shared && npx vitest run
$ npx tsc --noEmit -p packages/shared/tsconfig.json
$ npx tsc --noEmit -p packages/shared/tsconfig.test.json     # new in part 3
```
Baseline measured today: `Test Files 40 passed (40) / Tests 685 passed (685)`, and both
typechecks silent. Expect the same after.

**5. The whole typecheck chain, which is where the cli prediction is settled.**
```
$ npm run typecheck
```
(`tsc -b packages/shared packages/provisioning packages/cli && tsc --noEmit -p private/account/tsconfig.json && tsc --noEmit -p scripts/tsconfig.json`,
`package.json:178`.) Baseline today: exit 0, no output. Expect the same. If NodeNext in
shared changes what the project-reference redirect imposes on `packages/cli`, this is the
step that says so, and any errors it prints are in scope for this change, not a follow-up.

**6. The CLI suite.**
```
$ cd packages/cli && npm test
```
Brief's baseline: 175 files / 2301 tests. Re-measure before changing anything; do not
trust the quoted figure across a day of other sessions' work.

**7. The account suite.**
```
$ cd private/account && npm test
```
Brief's baseline: 86 files / 1549 tests. **Re-baseline this one immediately before and
after**, because `private/account/tests/**` is owned by a live writer agent right now
(section 9). A delta there is far more likely to be theirs than this change's; shared is
not even in that suite's resolution path except through bundler mode, which section 6
measured as unaffected.

**8. Gate wiring parity.**
```
$ npm run check:ci-parity
$ npm run ci:list | grep shared-esm
```
Parity must pass with the new key present in all three of package.json, the manifest and
`ci-quality.yml`; `ci:list` must show the new gate with its `build:packages` prerequisite.

**9. The full local runner.**
```
$ npm run ci
```
(`tsx scripts/ci-runner/run.ts --selftest && tsx scripts/ci-runner/run.ts`, `package.json:172`.)

---

## 9. Collision check with the live writer agents

Files this plan writes:

- `packages/shared/src/**` (49 files, plus 2 for the JSON attributes)
- `packages/shared/tsconfig.json`, new `packages/shared/tsconfig.test.json`
- `package.json` (root): two script strings at lines 147 and 178, one new key near line 56
- `scripts/check-shared-esm-resolvable.ts` (new)
- `scripts/ci-runner/manifest.ts` (one entry after line 174)
- `.github/workflows/ci-quality.yml` (one step in `quality-packages`)

Reserved for the live writers: `scripts/drills/**`, `private/account/tests/**`,
`packages/e2e-tests/**`, `private/renet/pkg/chunkstore/*_test.go`. **No overlap.**

Two sequencing notes for the lead:

1. `private/account/tests/**` is read twice by this work: as step 7's baseline, and by
   `packages/shared/src/subscription/__tests__/crypto.test.ts:392-396`, which reads
   `private/account/tests/integration/cross-language/fixtures.json` and skips its four
   cases when the file is absent. If the account writer moves or rewrites that fixture,
   those four shared tests change state for reasons unrelated to this change. Read-only
   from my side, but it makes step 7's numbers noisy, so re-baseline rather than compare
   against the brief.
2. Nothing here needs `packages/e2e-tests`, and `packages/e2e-tests` needs nothing here
   (CJS, section 6), so the two can land in either order.

---

## 10. Open items

- **The one unverified prediction** is step 5: `npm run typecheck` staying green once
  `packages/shared` is NodeNext and `packages/cli` inherits that through the project
  reference. Everything upstream of it was measured; this one could not be, without
  writing to the tree. If it comes back red, the errors are real type errors the redirect
  was hiding, and they are in scope.
- **The `.generated` specifiers** (`packages/shared/src/renet-contract/index.ts:13` and
  siblings) resolve today and will carry `.js` like the rest, but note for whoever runs
  the codemod that TypeScript reports them as `TS2307` rather than `TS2835` because the
  resolver reads `.generated` as an extension and cannot suggest a fix. They are not a
  separate case for the codemod, which resolves against the filesystem, not against the
  suggestion.
- **Part 3's test exclusion** is the one judgment call worth a second opinion, because it
  trades a small amount of build-config surface for a gate with no exclusion list. The
  fallback is written down in section 5 so the choice can be reversed without redesigning
  the gate.
