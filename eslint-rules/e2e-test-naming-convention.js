/**
 * ESLint rule to enforce E2E test file naming conventions
 *
 * Pattern: {XX}-{YY}[-{ZZ}]-{feature-name}[.negative].test.ts
 *
 * This rule ensures E2E test files follow a consistent naming pattern
 * that aligns with documentation structure (web-application.md).
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
        'E2E test file "{{filename}}" does not match pattern: {XX}-{YY}[-{ZZ}]-{feature-name}[.negative].test.ts',
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

    // Pattern: XX-YY[-ZZ]-feature-name[.negative].test.ts
    // XX, YY, ZZ: 2-digit numbers
    // feature-name: kebab-case (lowercase letters, numbers, hyphens)
    // .negative: optional suffix for negative test cases
    const VALID_PATTERN = /^(\d{2})-(\d{2})(?:-(\d{2}))?-([a-z0-9]+(?:-[a-z0-9]+)*)(\.negative)?\.test\.ts$/;

    return {
      Program(node) {
        const filename = context.filename;

        // Only check .test.ts files
        if (!filename.endsWith('.test.ts')) return;

        // Only check files under packages/e2e/tests
        const e2eTestsPath = path.join('packages', 'e2e', 'tests');
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
