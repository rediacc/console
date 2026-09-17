// --------------------------------------------------------------------------- NODE TOOLING TREES AND THE DELIBERATE SUPPRESSIONS
//
// The tail of the config, and the two things that belong at a tail: rules that are switched off for a whole CLASS of file with the measurement that justified
// it, and the .ci / eslint-rules / package-scripts / .cjs trees that were once
// excluded outright and are now configured. ---------------------------------------------------------------------------
//
// ORDER IS THE CONTRACT. Flat config resolves by LAST MATCH WINS, so these
// blocks mean what they mean only in the position eslint.config.js splices them
// into. This module is a verbatim slice of the single 1,444-line file that came before it: the blocks, their order, their comments and their whitespace are unchanged. Anything else would be a rewrite wearing a refactor's clothes. ---------------------------------------------------------------------------

import tseslint from 'typescript-eslint';
import globals from 'globals';

export default [
  // ── prefer-const-arrays is a TYPESCRIPT rule; it cannot apply to plain JS ──
  // The rule is registered for '**/*.{js,jsx,ts,tsx}', but the only thing that satisfies
  // it is an `as const` assertion, which is a TSAsExpression — TypeScript-only syntax that is a hard SyntaxError in a .js file (verified: node rejects
  // `export const FOO = ['a'] as const;` in ESM .js). So on any plain-JS file the rule
  // demands something that cannot be written, and the only ways out are a blanket disable comment or converting the file to TypeScript.
  //
  // That is a defect in the rule's scope, not a property of any one file, so it is fixed here for the whole class rather than suppressed at the call site. Plain-JS files that want narrow literal types should ship a hand-written .d.ts, which is exactly what packages/locales does.
  {
    files: ['**/*.js', '**/*.jsx', '**/*.mjs', '**/*.cjs'],
    rules: {
      'custom/prefer-const-arrays': 'off',
    },
  },

  // ── P4 reshape: size/complexity debt, suppressed deliberately, scheduled for P5 ──
  {
    // BLOCKER: splitting a command-REGISTERING module is not cosmetic, and this is the failure mode, not a plea that we were busy. 1. check:ci-command-planes attributes every leaf to the module whose .action() REGISTERS it — it patches Command.prototype.command/.action and captures a stack at registration time. Split the file and leaves get re-attributed: if a split-out module's
    // import graph no longer reaches a machine seam, a machine-plane leaf becomes unattributable, or worse, silently changes plane. 2. command-tree.json is derived from registration ORDER, and a split can shift it.
    //      Four validators and two ESLint rules read that file as their model of the CLI.
    // 3. COMMAND_METADATA / COMMAND_PLANES / the policy globs are keyed by command-path STRING and have no stale-entry gate. A split that re-nests or renames a leaf ORPHANS its guard — and guards fail OPEN: a deny that stops denying (#55). command-metadata.ts (823 lines) is the authz table itself, so it is the most dangerous of the three and gets split LAST, under test.
    // datastore.ts (539) and machine/status.ts (548) are ordinary size drift from the reshape. Deferred to P5, where the split is done deliberately with the plane/tree/guard artifacts regenerated and diffed. A 512-line cap is not worth a silent authz gap. The command-tree freshness gate added in this wave (check:ci-command-tree) is what makes that split safe to attempt — do it
    // after that gate exists, never before.
    files: [
      'packages/cli/src/config/command-metadata.ts',
      'packages/cli/src/commands/datastore.ts',
      'packages/cli/src/commands/machine/status.ts',
    ],
    rules: {
      'max-lines': 'off',
    },
  },
  {
    // BLOCKER: eight functions in the P4 command layer sit between 11 and 17 cognitive complexity against a limit of 10. Every one is a command action whose branching IS the contract it implements (the placement union, the datastore attach/detach state machine, the repo verb dispatch). Extracting helpers to please a counter, inside an unmerged wave that four feature-breaking bugs
    // already survived, trades a real risk of behaviour change
    // for a cosmetic number. These are also the exact functions whose guards the type system
    // already lies about (noUncheckedIndexedAccess is off — see docs/design/spec/12-carried-debt), so a careless extraction can drop a load-bearing check while looking like a tidy-up. P5: extract deliberately, each with a red-first test.
    files: [
      'packages/cli/src/commands/datastore.ts',
      'packages/cli/src/commands/repo.ts',
      'packages/cli/src/commands/repo-create-delete.ts',
      'packages/cli/src/commands/repo-trim.ts',
      'packages/cli/src/commands/mcp/tool-factory.ts',
      'packages/cli/src/commands/mcp/__tests__/argv-acceptance.test.ts',
    ],
    rules: {
      'sonarjs/cognitive-complexity': 'off',
    },
  },


  // ---- Node tooling trees: .ci scripts, the repo's own eslint rules, GitHub
  // Actions glue --------------------------------------------------------------
  //
  // These were EXCLUDED rather than configured, and the two ignore comments said
  // why: "custom eslint rules (plain JS)" and "JS scripts are github-script
  // glue". The first was a PARSER workaround -- the repo-wide block is type-aware via projectService, and a file no tsconfig covers fails to PARSE there, which looks like 45 fatal errors rather than like a missing config. The second premise is stale: .ci/ holds 7247 lines of JS/TS including the live CI scope engine, which is not glue.
  //
  // Measured before writing this. Lifting the exclusions with NO config gave 385 errors, of which 290 were no-undef (console 108, process 91, module 36, require 27, setTimeout 8, __dirname 7) and 45 were "not found by the project service" -- 87% of the total was this block's absence, not defects. packages/*/scripts/** are the SAME KIND OF THING as scripts/**/*.ts, which already
  // has this exact relaxation twenty lines up: build and utility scripts whose stdout IS their interface. They were excluded rather than configured ("package-level scripts (plain JS utilities)"), and that exclusion was never a parser workaround -- these files ARE tsconfig-covered and parse fine, which is why lifting it yields 115 real findings and zero fatals.
  //
  // It also hid the gates from themselves: package.json implements TEN check:ci-* gates out of this tree, among them check:ci-command-planes, check:ci-tutorial-parity and check:ci-tutorial-casts.
  {
    files: ['packages/*/scripts/**/*.{js,cjs,mjs,ts}'],
    rules: {
      // stdout is the interface, exactly as for scripts/**/*.ts above.
      'no-console': 'off',
      'sonarjs/cognitive-complexity': 'off',
      'unicorn/prefer-number-properties': 'off',
      'unicorn/no-negated-condition': 'off',
      'no-nested-ternary': 'off',
      'prefer-template': 'off',
      'no-regex-spaces': 'off',
    },
  },
  {
    files: [
      '.ci/**/*.{js,cjs,mjs,ts}',
      // `.js` ALONE LEFT .mjs AND .cjs WITHOUT NODE GLOBALS, and the symptom is a `no-undef` on `process` for a reason that has nothing to do with the code.
      // Measured 2026-09-06: `eslint --print-config` on a .mjs here reports no
      // `process` global at all, on a .js it reports one. A test harness written in this directory was steered to .js to route around it. This matters beyond
      // eslint-rules: W7 relocates 7 .mjs and 11 .cjs into scripts/, so the same
      // extension gap is waiting in whatever lint block covers them.
      'eslint-rules/**/*.{js,cjs,mjs}',
      '.github/actions/**/*.js',
      // The bundler and this config itself: root tooling, outside every tsconfig, and previously ignored outright. The bundler produced only
      // no-undef on node globals; this file only a parse error. Both are
      // exactly the two classes the block above exists for.
      'packages/cli/bundle.mjs',
      'eslint.config.js',
      // Build-time plugin modules: plain ESM run by node (the search-index generator) and by Astro's markdown pipeline, deliberately outside every tsconfig. Same two classes as the bundler above: node globals and no
      // type information.
      'packages/www/src/plugins/*.mjs',
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      parser: tseslint.parser,
      // projectService is explicitly CLEARED. These files are deliberately
      // outside every tsconfig, so type-aware linting cannot apply to them;
      // leaving it inherited is what produced the parse errors.
      parserOptions: { projectService: false, project: false },
      globals: { ...globals.node, ...globals.es2021 },
    },
    rules: {
      // Type-aware rules cannot run without type information.
      ...tseslint.configs.disableTypeChecked.rules,
      // These ARE command-line tools and CI steps. stdout is their interface.
      'no-console': 'off',
    },
  },
  {
    // .cjs is CommonJS. require/module/exports are the module system here, not a legacy habit to lint away -- and the repo-wide block's glob
    // (**/*.{js,jsx,ts,tsx}) never matched .cjs at all, which is why these files
    // had no globals and every `process` read as undefined.
    files: ['**/*.cjs'],
    languageOptions: {
      sourceType: 'commonjs',
      globals: { ...globals.node, ...globals.es2021 },
    },
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
];
