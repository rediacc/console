/**
 * ESLint rule to enforce E2E test file naming conventions
 *
 * Pattern: {NN}[{variant}]-{feature-name}[.negative].test.ts
 *
 * NN is the two-digit suite number and the optional single-letter variant
 * marks a split suite (12a / 12b / 12d). The previous {XX}-{YY} pattern and
 * its `packages/e2e` path both described the web-console suite that PR #513
 * deleted; neither matched a single file in the surviving `packages/e2e-tests`
 * suite (0 of 33), so both are updated here to the convention actually in use.
 */

import path from 'node:path';

/** @type {import('eslint').Rule.RuleModule} */
export const e2eTestNamingConvention = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Enforce E2E test file naming conventions',
      recommended: true,
    },
    messages: {
      invalidTestFileName:
        'E2E test file "{{filename}}" does not match pattern: {NN}[{variant}]-{feature-name}[.negative].test.ts',
    },
    schema: [
      {
        type: 'object',
        properties: {
          maxSection: { type: 'number', default: 11 },
          excludeDirs: {
            type: 'array',
            items: { type: 'string' },
            default: ['helpers', 'setup', 'electron'],
          },
        },
        additionalProperties: false,
      },
    ],
  },

  create(context) {
    const options = context.options[0] || {};
    const excludeDirs = new Set(options.excludeDirs || ['helpers', 'setup', 'electron']);

    // Pattern: NN[variant]-feature-name[.negative].test.ts
    // NN: 2-digit suite number; variant: optional single letter for split suites
    // feature-name: kebab-case (lowercase letters, numbers, hyphens)
    // .negative: optional suffix for negative test cases
    const VALID_PATTERN = /^(\d{2})([a-z])?-([a-z0-9]+(?:-[a-z0-9]+)*)(\.negative)?\.test\.ts$/;

    return {
      Program(node) {
        const filename = context.filename;

        // Only check .test.ts files
        if (!filename.endsWith('.test.ts')) return;

        // Only check files under packages/e2e-tests/tests
        const e2eTestsPath = path.join('packages', 'e2e-tests', 'tests');
        if (!filename.includes(e2eTestsPath)) return;

        // Check excluded directories
        const pathParts = filename.split(e2eTestsPath);
        if (pathParts.length < 2) return;

        const relativePath = pathParts[1].replace(/^[/\\]/, '');
        const pathSegments = relativePath.split(path.sep);

        // If first segment is an excluded directory, skip validation
        if (pathSegments.length > 0 && excludeDirs.has(pathSegments[0])) return;

        const basename = path.basename(filename);
        if (!VALID_PATTERN.test(basename)) {
          context.report({
            node,
            messageId: 'invalidTestFileName',
            data: { filename: basename },
          });
        }
      },
    };
  },
};

export default e2eTestNamingConvention;
