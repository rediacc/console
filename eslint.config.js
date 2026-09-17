// ---------------------------------------------------------------------------
// FLAT CONFIG ROOT. The blocks live in ./eslint.config/, six modules deep.
//
// This file was 1,444 lines of one array, which made it unreadable in the one way that matters for flat config: you could not see the ORDER. Flat config resolves LAST MATCH WINS, so the position of a block is as load-bearing as its contents, and a reader scrolling a thousand lines to find out whether the account overrides come before or after the test overrides was reading the
// wrong artifact. Six named imports put that order on one screen.
//
// THE SPLIT IS A PURE MOVE, AND THAT WAS PROVED RATHER THAN ASSERTED.
// eslint-rules/__tests__/config-resolution-differential.mjs asks ESLint itself,
// via calculateConfigForFile, what the fully resolved config is for every tracked lintable path in the repository, and records the answers deterministically. The snapshot taken from the single-file config and the snapshot taken from this one are byte-identical across 2,762 paths. The same harness was checked in both directions: perturbing one rule in one module reds it, restoring
// the rule greens it, so a pass means something.
//
// WHAT EACH MODULE OWNS, in the order they are spliced: ignores global ignores, and reportUnusedDisableDirectives
//   typescript  js/tseslint recommended, scripts/, the repo-wide type-aware
//               block, and the `custom` plugin that wires up eslint-rules/
// i18n the locale-config generator and every i18n enforcement block tests playwright, __tests__, stub exemptions, the no-skip policy packages private/account, packages/www, packages/json, scripts/
//   tooling     class-wide suppressions and the .ci / eslint-rules / .cjs trees
//
// ADDING A BLOCK: put it in the module whose slice it belongs to, at the position it needs, and re-run the differential if the change was meant to be invisible. Do not add a seventh spread here to dodge the order question. ---------------------------------------------------------------------------

import tseslint from 'typescript-eslint';

import ignores from './eslint.config/ignores.js';
import typescript from './eslint.config/typescript.js';
import i18n from './eslint.config/i18n.js';
import tests from './eslint.config/tests.js';
import packageOverrides from './eslint.config/packages.js';
import tooling from './eslint.config/tooling.js';

export default tseslint.config(
  ...ignores,
  ...typescript,
  ...i18n,
  ...tests,
  ...packageOverrides,
  ...tooling,
);
