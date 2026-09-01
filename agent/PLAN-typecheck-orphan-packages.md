# PLAN: four packages nothing typechecks

Status: ready to run, AFTER #583 merges
Origin: session f88f9be7, 2026-09-01. Found by sweeping the class behind `6ba6a0c4c`,
which wired `packages/cli`'s 185 test files into a typecheck project and fixed the 111
errors hiding there. These four are the siblings. All counts below were MEASURED on the
tree at `6ba6a0c4c`, not estimated.

## The two shapes, which need different fixes

`packages/cli` and `packages/shared` are covered. The rest split in two:

| package | tests | in a tsconfig | anything RUNS it | errors |
|---|---|---|---|---|
| `packages/provisioning` | 1 | **no** — `exclude: ['src/**/*.test.ts']` | — | **2** |
| `packages/e2e-tests` | 41 | yes | **nothing** | **0** |
| `workers/www` | 3 | yes | **nothing** | **18** |
| `packages/www` | 5 | yes | **nothing** | **32** |

- `provisioning` is the exact shape `6ba6a0c4c` fixed: the config deliberately excludes
  its own tests.
- The other three have configs that DO include their tests, but no `typecheck` script and
  nothing in CI that runs one. That is the orphan-config shape `scripts/tsconfig.json` had
  until 2026-08-05: coverage that looks real and never executes.

## What the errors actually are, per package

Read this before assuming the counts imply the work. They do not.

**`packages/e2e-tests` — 0 errors.** Type-clean the whole time and never once checked.
Pure wiring, no fixes. Do this one first; it is free and it proves the harness.

**`packages/provisioning` — 2 errors.** Drop `src/**/*.test.ts` from `exclude`, or add a
`tsconfig.test.json` beside it the way `packages/cli` and `packages/shared` now have. Two
errors to read.

**`packages/www` — 32 errors, and ZERO of them are in test files.** All 32 are `TS2339`,
and they are one missing ambient declaration repeated:

    AccountCta.tsx(48,12): Property 'openRegionPicker' does not exist on type 'Window & typeof globalThis'
    ContactForm.tsx(103,14): Property 'plausible' does not exist on type 'Window & typeof globalThis'

So www is not a "tests excluded" case at all: it is a package nothing typechecks, whose
production code reads two undeclared globals. The likely fix is ONE `.d.ts` declaring
`Window.plausible` and `Window.openRegionPicker`, not 32 edits. Verify that before
budgeting for more. Note `packages/www/tsconfig.json` includes `**/*`, so turning this on
covers the whole site, which is a bigger win than the count suggests.

**`workers/www` — 18 errors, but only ~5 are the worker's.** 13 are `TS2823` in
`../../private/account/src/i18n/index.ts`, pulled in transitively:

    Import attributes are only supported when the '--module' option is set to 'esnext'…

That is a module-setting mismatch, not a defect. Fix the config first and re-measure; the
worker's own errors are `src/smart-redirect.ts` (2), `src/index.ts` (1) and one test.

Also: `workers/mta-sts` and `workers/proxy` have NO tsconfig at all. `workers/account` and
`workers/www` have one plus a `"typecheck": "tsc --noEmit"` script that nothing invokes.

## How to wire it, once each package is clean

Mirror what `6ba6a0c4c` did, which is itself a mirror of `packages/shared`:

1. a `tsconfig.test.json` (or a dropped exclude) so the tests are in a project;
2. chain `tsc --noEmit -p <project>` into BOTH `check:types` and `typecheck` in the root
   `package.json` — they are separate strings and both must be edited;
3. `npm run check:ci-parity` and `npm run check:ci-gate-manifest` must both agree
   afterwards.

## Traps this cost the session that found it

- **A green `ci:quick` is NOT a claim about types.** `check:types` is `slow: true` and the
  quick lane defers it, and `check:lint`/`check:format` are biome, which does not
  typecheck. Two type errors reached CI that way. Run
  `npx tsc --noEmit -p <project>` before every push.
- **`check:lint` is eslint, not biome.** Sub-agents reported "biome clean" and left 10
  eslint errors, 7 of them `@typescript-eslint/require-await` from making a sync mock body
  `async` to satisfy a `Promise<T>` signature. The repo's adaptation pattern is at
  `remote/sync/__tests__/sftp-fallback.test.ts:31`: keep the body sync, wrap at the
  boundary.
- **`as unknown as X` hides everything and TS cannot flag it.** Replacing one with
  `satisfies` exposed 8 missing required fields and a fixture expressing "unmounted" by
  OMITTING a required field. Grep for `as unknown as` in the package before starting.
- Fix the TYPE. No `@ts-expect-error`, no `as any`, no widening to `unknown`.
