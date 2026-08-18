# PLAN: Lint-rule liveness as a config-derived probe matrix
Status: done
Owner: 97604f47
Updated: 2026-08-15

**2026-08-15 CLOSED, proven not asserted.** `npm run check:ci-lint-rule-liveness` exits 0
and reports: "30 enabled custom/i18n rule(s) each fired on a planted violation (35
registered, 5 off by documented decision, 0 enabled-but-unreachable and recorded); 3
negative controls stayed silent", plus JSX reachability across 30 directory
representatives. That is the matrix this plan asked for, doing the thing it was built to
do, with its own negative controls holding.

Replaces the single hard-coded probe in `.ci/scripts/quality/check_lint_rule_liveness.py`
with a matrix that derives its universe from `eslint.config.js` itself, so no enabled
custom rule can be outside the gate's view without the gate saying so.

Everything below marked VERIFIED was driven through the real ESLint API in this worktree
on 2026-08-15. Line anchors were each re-read before being written down; a few anchors
supplied by the investigation sub-agents were wrong and are corrected here.

---

## 1. What the gate proves today, and the exact size of its blind spot

`check_lint_rule_liveness.py` is a genuine control: it plants a violation and asserts the
rule reports it, so a rule that is structurally unable to fire cannot pass (the docstring
at `:1-24` records the five inert i18n rules that motivated it). The limits are three
constants:

- `SPECIMEN_DIR = "packages/www/src/i18n/translations"` (`:101`) and the single probe
  `packages/www/src/i18n/translations/tr.json` (`:138`).
- the namespace filter `key.startswith("i18n/")` (`:88`), which drops `custom/` and
  `i18n-source/` entirely.
- `SPECIMENS` (`:37-68`), 5 entries.

Measured at that probe: 5 rules resolved, 3 enabled. Repo-wide the real number is **30
enabled custom-namespace rules**, so the gate proves 3 of 30 and is silent about 27.

`check_lint_scope_coverage.py:28-31` names this gate as its backstop for "a file linted by
a config that happens to enable nothing", which means a dead `custom/*` rule is currently
invisible to both gates. There is no `RuleTester` anywhere in the repo
(`grep -rl RuleTester` outside `node_modules` returns nothing), so nothing else covers them.

---

## 2. The universe, derived rather than listed

The matrix must not be a hand-written probe list, because a hand-written list is exactly
what silently misses a config block. `eslint.config.js` default-exports a plain array of
40 resolved blocks (`tseslint.config(...)` returns one), so the gate imports it and walks
it. VERIFIED: `import('<root>/eslint.config.js')` yields `Array.isArray === true`,
`length === 40`, in 1027 ms.

From that walk:

- **REGISTERED** = every rule name under a `plugins:` entry named `custom`, `i18n`, or
  `i18n-source`. Measured: **36** (19 `custom/`, 16 `i18n/`, 1 `i18n-source/`). This equals
  the rule files on disk: 19 in `eslint-rules/` plus 17 in `eslint-rules/i18n/`, where
  `interpolation-match` is the one i18n file that lives in `i18nSourcePlugin`
  (`eslint-rules/i18n/index.js:51-55`). No orphan rule file exists.
- **ENABLED** = any rule assigned a severity other than `off`/`0` in at least one block.
  Measured: **30**.
- **NEVER ENABLED** = REGISTERED minus ENABLED. Measured: **6**.

Severity is last-block-wins per path, so "enabled in some block" is a candidate, not a
verdict. Each matrix entry therefore names a probe path, and the gate re-checks that path
with `ESLint#calculateConfigForFile` (the in-process equivalent of `--print-config`,
VERIFIED at 23 ms per call) before it believes the rule is on there.

### 2.1 The 30 enabled rules and their enabling globs (measured)

| Rule | Enabling `files` glob(s) |
|---|---|
| `custom/no-duplicate-translation-props` | `**/*.{js,jsx,ts,tsx}` |
| `custom/no-hardcoded-nullish-defaults` | `**/*.{js,jsx,ts,tsx}` |
| `custom/prefer-const-arrays` | `**/*.{js,jsx,ts,tsx}` |
| `custom/require-testid` | `**/*.{js,jsx,ts,tsx}` |
| `custom/no-direct-sftp-client` | `packages/cli/src/**/*.{js,ts}` |
| `custom/no-hardcoded-cli-text` | `packages/cli/src/**/*.{js,ts}` |
| `custom/require-command-summary` | `packages/cli/src/**/*.{js,ts}` |
| `custom/require-translation-key-arg` | `packages/cli/src/**/*.{js,ts}` |
| `custom/require-translation` | `packages/cli/src/**`, `private/account/web/src/**` |
| `i18n-source/interpolation-match` | `packages/cli/src/**`, `private/account/web/src/**` |
| `custom/no-positional-cli-syntax-source` | `packages/cli/src/**`, `private/account/web/src/**`, `packages/www/src/**` |
| `custom/no-hardcoded-text` | `private/account/web/src/**/*.{ts,tsx}` |
| `custom/no-unawaited-drizzle-terminator` | `private/account/src/**/*.ts` (minus `src/db/index.ts`) |
| `custom/e2e-test-naming-convention` | `packages/e2e-tests/**/*.ts`, `packages/{shared,cli}/src/**/__tests__/**` |
| `custom/require-data-track` | `packages/www/src/**/*.{ts,tsx}` |
| `custom/seo-no-vague-anchor-text` | `packages/www/src/**/*.{ts,tsx}` |
| `custom/seo-require-img-alt` | `packages/www/src/**/*.{ts,tsx}` |
| `custom/seo-no-hash-breadcrumb-url` | `packages/www/src/**/*.{ts,tsx}` |
| `custom/seo-no-trailing-slash-internal-link` | `packages/www/src/**/*.{ts,tsx}` |
| `i18n/seo-title-length` | `packages/www/src/i18n/translations/*.json` |
| `i18n/seo-description-length` | `packages/www/src/i18n/translations/*.json` |
| `i18n/seo-no-duplicate-h1-title` | `packages/www/src/i18n/translations/*.json` |
| `i18n/no-untranslated-tutorial-transcript-values` | `packages/www/src/data/tutorial-transcripts/*/*.json` |
| `i18n/cli-flag-consistency` | `packages/cli/src/i18n/locales/**/*.json` |
| `i18n/no-positional-cli-syntax` | `packages/cli/src/i18n/locales/**`, `private/account/web/src/i18n/locales/**` |
| `i18n/no-undefined-cli-flags` | `packages/cli/src/i18n/locales/en/**/*.json` |
| `i18n/cross-language-consistency` | `<localesDir>/en/**/*.json` for all three trees |
| `i18n/translation-coverage` | `<localesDir>/en/**/*.json` for all three trees |
| `i18n/no-untranslated-values` | the 12 non-English dirs of all three trees |
| `i18n/interpolation-consistency` | the 12 non-English dirs of all three trees |

The three `localesDir` trees are `packages/cli/src/i18n/locales`,
`private/account/web/src/i18n/locales`, `private/account/src/i18n/locales`, wired at
`eslint.config.js:667`, `:709`, `:808` through the generator `i18nLocaleConfigs`
(`eslint.config.js:83`).

---

## 3. The buckets, and what each one earns

### 3.1 Enabled and provable in-config: 27 rules

Specimen fires while the rule sits at its configured severity, with its configured
options, at a path inside its enabling block. No severity override, no options override.
This is the strongest available proof short of a real defect. All 27 VERIFIED firing
(section 5).

### 3.2 Enabled but structurally deaf to the linted text: 2 rules

`i18n/cross-language-consistency` and `i18n/translation-coverage` never read the file
being linted beyond a type check. `cross-language-consistency` uses the linted node only
at `:161` (`node.body?.type !== 'Object'`) and then reads English from
`path.join(absoluteLocalesDir, sourceLanguage, namespace + '.json')` (`:164`);
`translation-coverage` counts keys off disk the same way. VERIFIED: a stdin specimen of
`{"a":"x"}` at `packages/cli/src/i18n/locales/en/cli.json` produces **zero** messages from
both. A text-based liveness gate would score them "dead" while they work.

They are provable by keeping the real probe path and overriding only the rule's
`localesDir` option to point at a two-file fixture tree. VERIFIED, both fire:

- `cross-language-consistency` with `{en/cli.json: {"a":"x","b":"y"}, tr/cli.json: {"a":"x"}}`
  reports `Key "b" exists in en but is missing in tr`.
- `translation-coverage` with the same fixture reports `tr translation coverage is 50% (1/2 keys)`.

The fixture lives in an OS temp dir created with `mkdtemp`, outside the repo. Never under a
locales tree: these rules enumerate language subdirectories by listing `localesDir`
(`cross-language-consistency.js:19`), so a probe directory planted inside a real locales
tree becomes a fourteenth "language" for every rule in the tree, and the locale-set gates
that derive from `@rediacc/locales` would see it too.

### 3.3 Enabled but triggered by the filename alone: 1 rule

`custom/e2e-test-naming-convention` reports purely on the basename
(`eslint-rules/e2e-test-naming-convention.js:51` `VALID_PATTERN`, report at `:76`), and it
self-guards to paths containing `packages/e2e-tests/tests` (`:62`). So the specimen path
must be a name that violates the pattern, and no such file exists on disk. It cannot: the
repo's 26 files there all conform, which is the rule doing its job.

A virtual path does not work either. The typed-linting block sets `projectService`
(`eslint.config.js:314-325`) with `allowDefaultProject` limited to `scripts/*.ts`,
`scripts/utils/*.ts`, `packages/locales/*.js`. VERIFIED: linting text at
`packages/cli/src/commands/zzz-nope.ts` returns a **fatal** message
`Parsing error: ... was not found by the project service`, and zero rules run. Disabling
`projectService` for that one lint does not help either: VERIFIED, ESLint then throws out
of `@typescript-eslint/no-deprecated` because a type-aware rule is still enabled.

Resolution: prove this one in an isolated `ESLint` instance
(`overrideConfigFile: true`) that registers only this rule with the plain TS parser.
VERIFIED: fires on `packages/e2e-tests/tests/zz_Bad-Name.test.ts`, silent on
`packages/e2e-tests/tests/01-system-checks.test.ts`, 0.3 s. That proves the rule code can
report; `calculateConfigForFile` on a real e2e test proves it is switched on in the real
config. The two halves together are the same claim the other 27 get in one step, and the
matrix entry must carry that reason in prose so nobody "simplifies" it later.

### 3.4 Registered but enabled nowhere: 6 rules

Two different situations, and only one of them is documented:

**Off by an explicit, documented decision (5).** `i18n/sorted-keys`,
`i18n/no-empty-translations`, `i18n/key-naming-convention`, `i18n/no-unused-keys`,
`i18n/translation-staleness`. The banner at `eslint.config.js:104-137` records why (7245
findings on waking, a non-converging fixer). Treatment: the gate keeps a `KNOWN_OFF` map
whose keys must equal this set exactly, each with its reason string. Specimens for
`sorted-keys` and `no-empty-translations` already exist and stay, so the day one is turned
back on it is proven live in the same commit.

**Dead code, undocumented (1).** `custom/no-raw-api-calls` is imported at
`eslint.config.js:19`, registered into the plugin at `:290`, and then only ever assigned
`'off'`, at `:1056` and `:1135`. It is enabled by no block anywhere. Two `'off'` lines
switch off a rule that was never on. Treatment: this is not a missing specimen and not a
dead rule, it is dead wiring. **Recommendation: delete the import, the registration, the
two `off` lines, and `eslint-rules/no-raw-api-calls.js`.** If the operator wants it kept,
it goes in `KNOWN_OFF` with a written reason like the other five. Either way the gate then
fails on any FUTURE rule that becomes registered-but-never-enabled, which is the class
control.

### 3.5 Enabled, alive as code, with no file it can ever report on: 1 rule

`custom/require-testid` is `['error', {...}]` at `eslint.config.js:437` under
`**/*.{js,jsx,ts,tsx}`, and it only reports on JSX elements (report sites
`eslint-rules/require-testid.js:195`, `:206`, `:218`). Measured reach:

- Every `.tsx`/`.jsx` in the linted tree is under `packages/www/src` (28 files) or
  `private/account/web` (209 files); `private/growth` (18) is globally ignored at
  `eslint.config.js:183-215`. Both of the linted trees switch the rule **off**:
  `eslint.config.js:1134` (www) and `:1055` (account web). VERIFIED by
  `--print-config`: severity `0` at `packages/www/src/components/AccountCta.tsx` and at
  `private/account/web/src/pages/Activity.tsx`.
- JSX does not parse in a `.ts` file, so the rule cannot report at any `.ts` path where it
  is on. VERIFIED: `Parsing error: '>' expected`.
- It is on and JSX parses in `.js`/`.mjs`/`.cjs` (VERIFIED: fires at
  `eslint-rules/zz-probe.js` with no override), but **no `.js`/`.mjs`/`.cjs` file outside
  `node_modules` contains JSX** (measured: zero hits for `=> <Capital` / `return ( <Capital`).

So `custom/require-testid` is enabled at error severity across the whole repo and protects
zero files. This is a distinct failure from a dead rule and needs a distinct message. See
section 6.3 for the reachability check that detects the class, and section 10 for the
decision it forces.

### 3.6 Summary counts

| Bucket | Count | Rules |
|---|---|---|
| Enabled, provable in-config | 27 | section 5 table |
| Enabled, needs fixture-dir option override | 2 | `i18n/cross-language-consistency`, `i18n/translation-coverage` |
| Enabled, needs isolated instance | 1 | `custom/e2e-test-naming-convention` |
| Registered, off by documented decision | 5 | the five i18n rules of `eslint.config.js:104-137` |
| Registered, never enabled, undocumented (dead wiring) | 1 | `custom/no-raw-api-calls` |
| Enabled but unreachable (dead scope) | 1 | `custom/require-testid` (also counted in the 27) |

---

## 4. Mechanism: one Node process, ESLint's JS API

The current gate spawns `npx eslint` once per rule. Measured in this worktree:
`npx eslint --print-config <path>` is **1.03 s**, a single `npx eslint --stdin ...` lint is
**2.05 s** (5 sequential runs took 10.2 s). A 30-rule matrix built that way costs
30 x 2.05 s plus config resolution, over 90 s, which is how a gate gets disabled.

The whole matrix instead runs in ONE Node process against `node_modules/eslint`'s API:

```js
const eslint = new ESLint({});                       // real config, real severities
const res = await eslint.lintText(code, { filePath: probe, warnIgnored: false });
```

`lintText` writes nothing to disk and takes a virtual `filePath` that decides which config
block applies, so there is no fixture file, no cleanup path, and no `git status` noise for
29 of the 30 rules. The single-star-glob trap that forced `SPECIMEN_DIR` to be flat
(`check_lint_rule_liveness.py:94-100`) does not disappear, it just moves: the `filePath`
string must sit exactly where the enabling glob matches, and
`packages/www/src/i18n/translations/*.json` still does not cross a directory boundary. The
matrix records the probe path per rule for that reason, and the gate re-checks each one
with `calculateConfigForFile` rather than trusting it.

Measured cost of the whole matrix, one process: config import 1.03 s + 29 in-config lints
9.34 s + isolated instance 0.31 s. The per-lint cost is dominated by first touch of a
TypeScript project service (2.80 s for the first `packages/cli` file, 1.71 s for the first
account-web file, 1.90 s for the first www file); every subsequent lint in the same project
is 3 to 40 ms. **Projected total including controls and the reachability sweep: 11 to 13 s.**
No batching design is required; the single process IS the batching.

`process.cwd()` must be the repo root. Several rules resolve their `localesDir` against
`process.cwd()` (`eslint-rules/i18n/shared/require-path-option.js:24`) and
`require-command-summary.js:59` reads `en/cli.json` relative to `context.cwd`; a wrong cwd
makes some rules throw and others silently no-op.

### 4.1 Where the code lives, and why the entry point does not move

`.ci/scripts/quality/check_lint_rule_liveness.py` is referenced from four places:
`package.json:96`, `scripts/ci-runner/manifest.ts:145`,
`.github/workflows/ci-quality.yml:749`, and the anti-vacuity registry at
`.ci/scripts/test/gates/test-gate-anti-vacuity.sh:121`. Keep that path as the executable
entry point and move the logic to `.ci/scripts/quality/lint-rule-liveness.mjs`
(`.ci/scripts/**` already contains `.mjs` siblings, e.g. `.ci/scripts/build/sea-inject/*.mjs`).
The Python file shrinks to: check the two preconditions, spawn `node` once, relay stdout,
stderr and exit code.

Required edits beyond the two script files:
- `scripts/ci-runner/manifest.ts:145` `leaves:` must gain
  `.ci/scripts/quality/lint-rule-liveness.mjs`, or a change to the real logic will not
  reselect the gate.
- Nothing else changes: same npm script id, same workflow step, same anti-vacuity entry.

---

## 5. The specimens

Every row below was VERIFIED firing on 2026-08-15 through `lintText` **with no rule
override and no option override**, i.e. at the configured severity with the configured
options, except the three rows marked otherwise. Content is written as it would appear in
the matrix.

### 5.1 `packages/cli/src/commands/backup.ts` (7 rules)

| Rule | Specimen | Condition it targets |
|---|---|---|
| `custom/no-direct-sftp-client` | `export const c = new SFTPClient();` | `no-direct-sftp-client.js:46` (`NewExpression` callee named `SFTPClient`); the `allow` list is read at `:38` and set at `eslint.config.js:631`, so the probe must not be `src/services/machine/machine-connection.ts` |
| `custom/no-hardcoded-cli-text` | `outputService.success("Backup completed successfully");` | report at `no-hardcoded-cli-text.js:158`; the string must contain a space, or `shouldIgnore` treats it as an identifier |
| `custom/require-command-summary` | `cmd.description(t("commands.cluster.description"));` | report at `require-command-summary.js:174` (summary too long); depends on the real `en/cli.json` value being over the max, measured 198 chars |
| `custom/require-translation` | `t("cli:zz.nope");` | report path from `require-translation.js:109`; the `cli:` namespace prefix is load-bearing, an unprefixed key resolves no namespace and the rule returns silently |
| `custom/require-translation-key-arg` | `errorResult("zz.nope.absent");` | report at `require-translation-key-arg.js:97`; the function name `errorResult` and arg index 0 come from `eslint.config.js:616-621` |
| `custom/no-positional-cli-syntax-source` | `export const s = "rdc repo list <name>";` | report at `no-positional-cli-syntax-source.js:171`; the denylist is auto-derived from `packages/cli/scripts/command-tree.json`, so `repo list` must still be a zero-positional leaf |
| `i18n-source/interpolation-match` | `t("cli:timing.step.configLoaded");` | report at `i18n/interpolation-match.js:194` (missing `{{duration}}`); depends on the real en value `Config loaded ({{duration}})` |

### 5.2 `packages/shared/src/index.ts` (3 rules)

| Rule | Specimen | Condition |
|---|---|---|
| `custom/no-duplicate-translation-props` | `export interface P { t: TypedTFunction; tC: TypedTFunction; }` | report at `no-duplicate-translation-props.js:92` |
| `custom/prefer-const-arrays` | `export const A_B = ["x"];` | report at `prefer-const-arrays.js:95`; must be UPPER_SNAKE_CASE, all-literal, no `as const`, and in a `.ts` (the rule is off for `**/*.js` at `eslint.config.js:1265`) |
| `custom/no-hardcoded-nullish-defaults` | `export const f = (y?: number) => y ?? 22;` | report at `no-hardcoded-nullish-defaults.js:148`; `22` avoids the allowlist at `eslint.config.js:410-432` (`0`, `1`, `-1` and 13 strings are allowed) |

### 5.3 `eslint-rules/zz-probe.js` (1 rule, JSX in a `.js` path)

| Rule | Specimen | Condition |
|---|---|---|
| `custom/require-testid` | `export const A = () => <Modal />;` | report at `require-testid.js:195`; `Modal` is in `requiredElements` at `eslint.config.js:437`. Co-fires `react/jsx-no-undef` and `no-undef`, which is harmless because the assertion is per rule id. See 3.5: this is the ONLY shape that can fire, and no real file has it |

### 5.4 `private/account/web/src/pages/Activity.tsx` (1 rule)

| Rule | Specimen | Condition |
|---|---|---|
| `custom/no-hardcoded-text` | `export const A = () => <div>Hello world</div>;` | report at `no-hardcoded-text.js:156` (JSXText) |

### 5.5 `private/account/src/routes/configs.ts` (1 rule)

| Rule | Specimen | Condition |
|---|---|---|
| `custom/no-unawaited-drizzle-terminator` | `declare const db: any; declare const tbl: any;` + newline + `export function go() { db.select().from(tbl).all(); }` | report at `no-unawaited-drizzle-terminator.js:215`; purely syntactic, no type info needed |

### 5.6 `packages/www/src/components/AccountCta.tsx` (5 rules)

| Rule | Specimen | Condition |
|---|---|---|
| `custom/require-data-track` | `export const X = () => <a href="/en/docs">Docs</a>;` | report at `require-data-track.js:141`; `elements`/`exemptParents` set at `eslint.config.js:1159` |
| `custom/seo-no-vague-anchor-text` | `export const X = () => <a href="/en/docs" data-track="x">Click here</a>;` | report at `seo-no-vague-anchor-text.js:81`; the `data-track` attribute keeps `require-data-track` quiet; a dynamic child would silence the rule |
| `custom/seo-require-img-alt` | `export const X = () => <img src="/a.png" />;` | report at `seo-require-img-alt.js:94` |
| `custom/seo-no-hash-breadcrumb-url` | `const breadcrumbItems = [{ name: "S", url: "/en/#solutions" }];` + newline + `export default breadcrumbItems;` | report at `seo-no-hash-breadcrumb-url.js:55`. **The variable name is the trap**: the rule only looks inside an array whose declarator id matches `/breadcrumb/i` (guard described at `:30`), so the identical object under another name is silent |
| `custom/seo-no-trailing-slash-internal-link` | `export const X = () => <a href="/en/docs/" data-track="x">Docs</a>;` | report at `seo-no-trailing-slash-internal-link.js:123`; the path must not start with an exempt prefix (`/account/`, `/api/`, `/assets/`, `/admin/`, ...) |

### 5.7 `packages/www/src/i18n/translations/tr.json` (3 rules, carried over unchanged)

The three existing specimens in `check_lint_rule_liveness.py:44-61` stay as they are, key
shapes included: `pages.x.meta.title` for `i18n/seo-title-length` (key filter at
`i18n/seo-title-length.js:53`), `pages.x.meta.description` for
`i18n/seo-description-length` (`i18n/seo-description-length.js:51`), and the
`meta.title` + sibling `hero.title` pair for `i18n/seo-no-duplicate-h1-title`.

### 5.8 `packages/www/src/data/tutorial-transcripts/tr/tutorial-storage-management.json` (1 rule)

| Rule | Specimen | Condition |
|---|---|---|
| `i18n/no-untranslated-tutorial-transcript-values` | `{"events":[{"text":"Fill the repository most of the way and check: the filesystem is getting tight."}]}` | report at `no-untranslated-tutorial-transcript-values.js:127`; the value must be byte-identical to `events[0].text` of the English cast of the SAME basename, and the rule returns `{}` for `en/` (`:80`). Text taken from the shortest first event in the tree |

### 5.9 `packages/cli/src/i18n/locales/en/cli.json` (2 rules)

| Rule | Specimen | Condition |
|---|---|---|
| `i18n/no-positional-cli-syntax` | `{"cli":{"description":"rdc config current <name>"}}` | report at `no-positional-cli-syntax.js:250`; `config current` must remain a zero-positional leaf in `command-tree.json` |
| `i18n/no-undefined-cli-flags` | `{"cli":{"description":"Use --zzz-not-a-flag now"}}` | report at `no-undefined-cli-flags.js:148`; `exemptFlags`/`exemptKeyPrefixes` are both empty at `eslint.config.js:701-704` |

### 5.10 `packages/cli/src/i18n/locales/tr/cli.json` (3 rules)

| Rule | Specimen | Condition |
|---|---|---|
| `i18n/cli-flag-consistency` | `{"cli":{"description":"Makineleri --current-ita ile yonet"}}` | report at `cli-flag-consistency.js:138`; the key path must EXIST in the real `en/cli.json` (`cli.description` does) and the rule returns `{}` for `en/` (`:121`) |
| `i18n/no-untranslated-values` | `{"cli":{"description":"Manage machines, repositories, and deployments over SSH"}}` | report at `no-untranslated-values.js:176`; value must be byte-identical to en AND survive the allowlist at `eslint.config.js:46-81` plus `:670-687`, which exempts anything containing a dot, a colon, an at-sign or a placeholder. `cli.description` is one of the few en values that qualifies |
| `i18n/interpolation-consistency` | `{"timing":{"step":{"configLoaded":"Yapilandirma yuklendi"}}}` | report at `interpolation-consistency.js:137`; the nested key path must mirror en exactly, the same string at a flat key is silent. Rule returns `{}` for `en/` (`:109`) |

### 5.11 Option-override rows (2 rules)

Probe path stays `packages/cli/src/i18n/locales/en/cli.json`; only `localesDir` is
redirected at a temp fixture. VERIFIED firing.

| Rule | Fixture | Condition |
|---|---|---|
| `i18n/cross-language-consistency` | `<tmp>/en/cli.json = {"a":"x","b":"y"}`, `<tmp>/tr/cli.json = {"a":"x"}` | report at `cross-language-consistency.js:131`; English read at `:164` |
| `i18n/translation-coverage` | same fixture | report at `translation-coverage.js:184`/`:194`, threshold compared at `:192` |

### 5.12 Isolated row (1 rule)

`custom/e2e-test-naming-convention`, filePath `packages/e2e-tests/tests/zz_Bad-Name.test.ts`,
body `export const x = 1;`, isolated instance per 3.3. VERIFIED firing.

### 5.13 Specimens that depend on live repo data

Six specimens read a real value out of the tree and would go silent if that value changed:
`require-command-summary` and `i18n-source/interpolation-match` (keys in `en/cli.json`),
`no-positional-cli-syntax-source` and `i18n/no-positional-cli-syntax` (leaves in
`command-tree.json`), `i18n/cli-flag-consistency` and `i18n/no-untranslated-values`
(`cli.description`), plus the transcript text.

A stale specimen going silent reads EXACTLY like a dead rule, which is the false
accusation this whole gate is built to avoid. So each of those matrix entries carries a
`precondition` closure that the gate evaluates BEFORE the lint (does the key still exist,
is the value still over the limit, is the command still a zero-positional leaf), and a
failed precondition exits 1 with `SPECIMEN STALE: <rule>: <what changed>. Update the
specimen; this is not evidence the rule is dead.` A distinct message is the whole point.

---

## 6. Cleanup, stray files, and the checks that keep the harness honest

### 6.1 Nothing is written into the repo

29 of 30 specimens go through `lintText`, which never touches the filesystem. The two
option-override rows need a real directory, created with
`fs.mkdtemp(path.join(os.tmpdir(), 'lint-liveness-'))` and removed in a `finally` with
`fs.rm(dir, { recursive: true, force: true })`, so an exception cannot leak it. It is
outside the repo, so no locale-set gate, no `git status` entry, no `.gitignore` needed.
Forbidden explicitly, with the reason written next to the code: the fixture must never be
created inside a locales tree, because the cross-file rules enumerate language directories
by listing `localesDir` and would adopt it as a language.

### 6.2 Controls: every run must prove the harness can still say NO

The existing gate does this once, by pointing `sorted-keys` at already-sorted input
(`check_lint_rule_liveness.py:163-169`). The matrix has three distinct execution modes, so
it needs one negative control per mode, all inline on every run, none behind a flag:

1. **In-config mode**: `i18n/sorted-keys` on `{"a":"1","b":"2"}` (with severity override,
   as today, since the rule is off). VERIFIED silent.
2. **Option-override mode**: `i18n/cross-language-consistency` and
   `i18n/translation-coverage` pointed at a SYMMETRIC fixture (`en/cli.json = {"a":"x"}`,
   `tr/cli.json = {"a":"y"}`). VERIFIED silent for both.
3. **Isolated mode**: `custom/e2e-test-naming-convention` on the conforming name
   `packages/e2e-tests/tests/01-system-checks.test.ts`. VERIFIED silent.

Any control that fires means the harness cannot distinguish firing from not firing:
print `CONTROL FAILED` and refuse a verdict, exit 1, exactly as today.

A fourth, structural control: a **fatal-message guard**. If any lint result carries
`message.fatal`, the specimen did not parse and the run reports
`SPECIMEN DID NOT PARSE` for that rule rather than "dead". This is not decoration, it is
the exact failure mode that would otherwise have made every `.ts` specimen at a
nonexistent path look like 10 dead rules at once (3.3).

### 6.3 Reachability (the dead-scope check)

For rules that can only report on a particular file shape, "enabled somewhere" is not the
same as "can ever report". The matrix entry declares `requiresJsx: true` for the five
JSX-only rules (`require-testid`, `no-hardcoded-text`, `require-data-track`,
`seo-no-vague-anchor-text`, `seo-require-img-alt`), and the gate asserts that at least one
REAL `.tsx`/`.jsx` file in the tree resolves that rule at severity > 0.

Implementation note for cost: dedupe the candidate file list by parent directory before
calling `calculateConfigForFile` (config is path-scoped, so one file per directory
decides), which turns ~237 candidates into ~30 calls, about 0.7 s.

Measured outcome today: `no-hardcoded-text` reaches 209 files, the four www rules reach 28,
and `require-testid` reaches **zero**. The message for that case must be its own:
`ENABLED BUT UNREACHABLE: custom/require-testid is 'error' on **/*.{js,jsx,ts,tsx} but is
off on every .tsx/.jsx path in the tree and cannot parse JSX in a .ts. It protects no file.`

### 6.4 Vacuous-input refusal

`test-gate-anti-vacuity.sh:121` runs the gate against an empty-tree fixture that copies
only `scripts/` and `.ci/scripts/`, and asserts the string `VACUOUS INPUT` appears. So:

- The Python entry point checks for `eslint.config.js` and `node_modules/eslint` FIRST and
  prints `VACUOUS INPUT: <path> is missing, so no rule set can be resolved` when either is
  absent. It must not let Node crash with `ERR_MODULE_NOT_FOUND`, which would be a
  non-zero exit for an environment reason wearing a vacuity failure's exit code.
- Floors inside the driver, each with its own message: fewer than **30** REGISTERED rules,
  or fewer than **25** ENABLED, is `VACUOUS INPUT` (today: 36 and 30; the floors leave room
  for a deliberate removal but not for the config silently resolving to nothing).
- **Set equality both ways**, which is the actual class-level control and is stronger than
  any floor: `ENABLED` must equal the matrix key set. A rule enabled with no matrix entry
  fails as `unproven` (today's wording, kept). A matrix entry for a rule no longer enabled
  fails as `stale matrix entry`. And `REGISTERED \ ENABLED` must equal `KNOWN_OFF`, so a
  newly registered-but-never-enabled rule cannot slip in the way `custom/no-raw-api-calls`
  did.

---

## 7. Runtime

| Step | Measured |
|---|---|
| `import('eslint.config.js')` | 1.03 s |
| 29 in-config / override lints, one process | 9.34 s |
| isolated instance for the filename rule | 0.31 s |
| `calculateConfigForFile` | 23 ms each |
| controls (4) | ~0.3 s |
| reachability sweep (~30 config resolutions) | ~0.7 s |
| **projected total** | **11 to 13 s** |

For contrast, the same matrix built the current way, one `npx eslint` per rule: 2.05 s per
lint plus 1.03 s per `--print-config`, over 90 s. That is the difference between a gate
that stays on and a gate someone turns off.

---

## 8. Verifying the finished gate by mutation

A gate that has never been seen to fail has not been tested. Four mutations, one per
execution mode, each with `cp` and never `git`. The working tree is shared and uncommitted;
`git checkout`/`restore`/`stash` would destroy other sessions' work.

**Mutation 1 (in-config TS mode) - `custom/no-direct-sftp-client`.** Smallest possible
edit, one identifier.

```bash
cd /home/muhammed/monorepo/console
cp eslint-rules/no-direct-sftp-client.js /tmp/nds.bak.js
# edit line 46: 'SFTPClient' -> 'SFTPClientZZZ'
npm run check:ci-lint-rule-liveness   # MUST exit 1, naming ONLY custom/no-direct-sftp-client
cp /tmp/nds.bak.js eslint-rules/no-direct-sftp-client.js
npm run check:ci-lint-rule-liveness   # MUST exit 0
```

**Mutation 2 (in-config JSON mode) - `i18n/interpolation-consistency`.** Reproduce the
historical defect shape rather than a typo: make the rule walk an empty member list, the
same way the five inert rules did. Edit the object-member access it uses (via
`eslint-rules/i18n/shared/json-ast.js::objectMembers`) inside
`interpolation-consistency.js` only, so the rule reports nothing while staying enabled.
Expect exactly one dead rule named.

**Mutation 3 (option-override mode) - `i18n/translation-coverage`.** Flip the comparison at
`translation-coverage.js:192` from `<` to `> 1000`. Expect one dead rule, and expect the
symmetric-fixture control to stay silent (a control that starts firing here would mean the
mutation broke the harness, not the rule).

**Mutation 4 (isolated mode) - `custom/e2e-test-naming-convention`.** Replace
`VALID_PATTERN` at `:51` with `/.*/`. Expect one dead rule, and the conforming-name control
still silent.

Additionally, two harness mutations that must produce the OTHER messages, because those
messages are the whole reason the buckets exist:

- Delete one matrix entry: expect `unproven`, not a pass.
- Point one specimen at a path outside its enabling block (e.g. move the
  `no-direct-sftp-client` specimen to `packages/shared/src/index.ts`): expect
  `probe path does not enable this rule`, not `dead`. VERIFIED today that this case is
  silent rather than firing, which is precisely why it needs its own message.

---

## 9. Order of work

1. Write `.ci/scripts/quality/lint-rule-liveness.mjs`: config walk, matrix, four modes,
   controls, floors, set equality, reachability, preconditions.
2. Reduce `check_lint_rule_liveness.py` to the launcher plus the two vacuity preconditions.
   Keep its docstring history; it is the record of why this exists.
3. Add the `.mjs` to `scripts/ci-runner/manifest.ts:145` `leaves`.
4. Run the four mutations of section 8 plus the two harness mutations.
5. Run `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` and confirm the entry still
   passes against the empty fixture.
6. Resolve the two findings the gate will report on its first honest run:
   `custom/no-raw-api-calls` (delete the dead wiring) and `custom/require-testid` (decide
   between turning it on where JSX actually lives and turning it off).

---

## 10. Decisions the operator has to make, with defaults

- **`custom/require-testid`.** The gate as designed goes RED on day one for it. DEFAULT:
  report it and leave the rule as it is until the operator decides, i.e. ship the
  reachability check with `require-testid` listed in a `KNOWN_UNREACHABLE` map carrying
  this plan as its reason, so the gate is green and the finding is written down rather than
  hidden. Turning it on for `private/account/web` (209 tsx files) is a separate wave with a
  real finding count behind it.
- **`custom/no-raw-api-calls`.** DEFAULT: delete the import, the plugin registration and
  the two `off` lines, and delete `eslint-rules/no-raw-api-calls.js`. Clean break, no
  compatibility theater.

---

## 11. Hypotheses, explicitly not verified

- The mutation runs of section 8 are designed, not executed. Every mutation TARGET was
  verified to be the live report path, but no mutation has been applied.
- The reachability sweep's ~0.7 s figure is extrapolated from the measured 23 ms per
  `calculateConfigForFile`, not measured end to end.
- Mutation 2's exact edit inside `interpolation-consistency.js` is described by shape, not
  by a verified line, because the rule reads members through the shared helper rather than
  inline.
- The `.js` escape hatch that makes `custom/require-testid` provable at all
  (`eslint-rules/zz-probe.js`) stops working if a future config block extends
  `projectService` coverage to `eslint-rules/*.js`.

---

## 12. Adjacent findings, out of this plan's scope

1. **`check:lint` never passes `.ci/`, `workers/` or `.github/actions/` to eslint.**
   `package.json` runs `eslint packages scripts private/account`, and no workflow invokes
   eslint on anything else. `check_lint_scope_coverage.py` reports those files as covered
   because it asks whether the eslint CONFIG ignores them (`eslint_ignored`, `:104-121`),
   not whether any command ever hands them to eslint. Config-visible is not
   argument-visible. Its own docstring (`:11`) claims `.ci/` was among the 93 files brought
   into scope on 2026-08-06. Worth a separate probe.
2. **A fourth locale tree has no i18n gate at all.** `packages/shared/src/i18n/locales`
   holds the same 13 languages, and `i18nLocaleConfigs` is called for only three trees
   (`eslint.config.js:667`, `:709`, `:808`). None of the eleven enabled i18n rules see it.
3. **`i18n-source/interpolation-match` declares a `messageId` it never reports.**
   `unknownKey` is declared at `eslint-rules/i18n/interpolation-match.js:160` and has no
   `context.report` referencing it. Cosmetic, but it is the same species of thing this
   gate hunts: a declared capability with nothing behind it.
