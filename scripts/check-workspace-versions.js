#!/usr/bin/env node
/**
 * Check that all workspace packages have the same version.
 *
 * This script validates that the "version" field in all package.json files
 * matches the root package.json version.
 *
 * Usage:
 *   node scripts/check-workspace-versions.js
 *
 * Exit codes:
 *   0 - All versions match
 *   1 - Version mismatch detected
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');

const PACKAGES = [
  { path: '', name: 'rediacc-console (root)' },
  { path: 'packages/shared', name: '@rediacc/shared' },
  { path: 'packages/shared-desktop', name: '@rediacc/shared-desktop' },
  { path: 'packages/cli', name: '@rediacc/cli' },
  { path: 'packages/web', name: '@rediacc/web' },
  { path: 'packages/desktop', name: '@rediacc/desktop' },
  { path: 'packages/e2e', name: '@rediacc/e2e' },
];

function readPackageJson(packagePath) {
  const fullPath = path.join(CONSOLE_ROOT, packagePath, 'package.json');
  try {
    const content = fs.readFileSync(fullPath, 'utf-8');
    return JSON.parse(content);
  } catch {
    return null;
  }
}

function checkVersionConsistency() {
  const errors = [];
  const versions = new Map();

  for (const pkg of PACKAGES) {
    const packageJson = readPackageJson(pkg.path);
    if (!packageJson) {
      errors.push(`Could not read package.json for ${pkg.name}`);
      continue;
    }
    versions.set(pkg.name, {
      version: packageJson.version,
      path: pkg.path || '.',
    });
  }

  if (errors.length > 0) {
    return { success: false, errors };
  }

  const rootVersion = versions.get('rediacc-console (root)')?.version;
  if (!rootVersion) {
    errors.push('Could not determine root package version');
    return { success: false, errors };
  }

  const mismatches = [];
  for (const [name, info] of versions) {
    if (info.version !== rootVersion) {
      mismatches.push({
        name,
        path: info.path,
        actual: info.version,
        expected: rootVersion,
      });
    }
  }

  if (mismatches.length > 0) {
    errors.push(`Version mismatch detected. Expected: ${rootVersion}`);
    errors.push('');
    errors.push('Mismatched packages:');
    for (const m of mismatches) {
      errors.push(`  ${m.name}: ${m.actual} (in ${m.path}/package.json)`);
    }
    errors.push('');
    errors.push('To fix, run from monorepo root:');
    errors.push(`  python _scripts/update-bridge-version.py ${rootVersion}`);
    return { success: false, errors };
  }

  return { success: true, version: rootVersion };
}

const result = checkVersionConsistency();

if (!result.success) {
  console.error('Workspace version check FAILED:\n');
  result.errors.forEach((e) => console.error(e));
  process.exit(1);
}

console.log(`All ${PACKAGES.length} packages have version: ${result.version}`);
process.exit(0);
