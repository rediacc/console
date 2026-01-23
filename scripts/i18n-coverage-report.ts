#!/usr/bin/env node
/**
 * i18n Coverage Report
 *
 * Non-blocking informational tool that generates a summary of translation key usage.
 * Shows which keys are used in web source, documentation, and which are orphaned.
 *
 * Usage:
 *   npx tsx scripts/i18n-coverage-report.ts
 *   npx tsx scripts/i18n-coverage-report.ts --json
 *
 * Exit codes:
 *   0 - Always (this is an informational report, not a validation gate)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LOCALES_DIR = path.join(__dirname, '../packages/web/src/i18n/locales/en');
const WEB_SRC_DIR = path.join(__dirname, '../packages/web/src');
const SHARED_SRC_DIR = path.join(__dirname, '../packages/shared/src');
const DOCS_DIR = path.join(__dirname, '../packages/www/src/content/docs');

interface NamespaceCoverage {
  namespace: string;
  totalKeys: number;
  webUsed: number;
  docsUsed: number;
  unused: number;
  webPercent: string;
  docsPercent: string;
  unusedPercent: string;
}

interface CoverageReport {
  namespaces: NamespaceCoverage[];
  summary: {
    totalKeys: number;
    webUsed: number;
    docsUsed: number;
    orphaned: number;
    webPercent: string;
    docsPercent: string;
    orphanedPercent: string;
  };
}

/**
 * Recursively get all keys from a nested object
 */
function getAllKeysFromObject(
  obj: Record<string, unknown>,
  prefix = ''
): string[] {
  const keys: string[] = [];

  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;

    if (typeof value === 'string') {
      keys.push(fullKey);
    } else if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...getAllKeysFromObject(value as Record<string, unknown>, fullKey));
    }
  }

  return keys;
}

/**
 * Get all locale keys grouped by namespace
 */
function getLocaleKeysByNamespace(): Map<string, string[]> {
  const namespaceKeys = new Map<string, string[]>();

  if (!fs.existsSync(LOCALES_DIR)) {
    return namespaceKeys;
  }

  const jsonFiles = globSync(`${LOCALES_DIR}/*.json`);

  for (const file of jsonFiles) {
    const namespace = path.basename(file, '.json');

    try {
      const content = JSON.parse(fs.readFileSync(file, 'utf-8')) as Record<string, unknown>;
      const keys = getAllKeysFromObject(content);
      namespaceKeys.set(namespace, keys);
    } catch {
      console.error(`Failed to parse ${file}`);
    }
  }

  return namespaceKeys;
}

/**
 * Extract translation keys used in web source files
 */
function extractWebKeys(): Set<string> {
  const keys = new Set<string>();

  const sourceFiles = [
    ...globSync(`${WEB_SRC_DIR}/**/*.{ts,tsx}`),
    ...globSync(`${SHARED_SRC_DIR}/**/*.{ts,tsx}`),
  ];

  const useTranslationPattern = /useTranslation\(\s*['"]([a-zA-Z]+)['"]/g;
  const tCallPattern = /\bt\(\s*['"`]([a-zA-Z][a-zA-Z0-9_.]*)['"` ]/g;
  const useTranslationArrayPattern = /useTranslation\(\s*\[([^\]]+)\]/g;
  const fullKeyPattern = /\bt\(\s*['"`]([a-zA-Z]+):([a-zA-Z0-9_.]+)['"` ]/g;

  for (const file of sourceFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    const namespaces = new Set<string>();
    let match: RegExpExecArray | null;

    const nsPattern = new RegExp(useTranslationPattern.source, 'g');
    while ((match = nsPattern.exec(content)) !== null) {
      namespaces.add(match[1]);
    }

    const nsArrayPattern = new RegExp(useTranslationArrayPattern.source, 'g');
    while ((match = nsArrayPattern.exec(content)) !== null) {
      const arrayContent = match[1];
      const nsMatches = arrayContent.match(/['"]([a-zA-Z]+)['"]/g);
      if (nsMatches) {
        for (const nsMatch of nsMatches) {
          namespaces.add(nsMatch.replace(/['"]/g, ''));
        }
      }
    }

    const tPattern = new RegExp(tCallPattern.source, 'g');
    while ((match = tPattern.exec(content)) !== null) {
      const key = match[1];

      if (key.includes(':')) {
        const [ns, keyPath] = key.split(':');
        keys.add(`${ns}.${keyPath}`);
      } else {
        for (const namespace of namespaces) {
          keys.add(`${namespace}.${key}`);
        }

        if (namespaces.size === 0) {
          for (const ns of ['common', 'auth', 'resources', 'functions', 'queue', 'system', 'machines', 'organization', 'settings', 'storageProviders', 'ceph']) {
            keys.add(`${ns}.${key}`);
          }
        }
      }
    }

    const fullPattern = new RegExp(fullKeyPattern.source, 'g');
    while ((match = fullPattern.exec(content)) !== null) {
      keys.add(`${match[1]}.${match[2]}`);
    }
  }

  return keys;
}

/**
 * Extract translation keys used in documentation files
 */
function extractDocsKeys(): Set<string> {
  const keys = new Set<string>();

  if (!fs.existsSync(DOCS_DIR)) {
    return keys;
  }

  const mdFiles = globSync(`${DOCS_DIR}/**/*.md`);
  const pattern = /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

  for (const file of mdFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    let match: RegExpExecArray | null;
    const re = new RegExp(pattern.source, 'g');

    while ((match = re.exec(content)) !== null) {
      keys.add(`${match[1]}.${match[2]}`);
    }
  }

  return keys;
}

/**
 * Generate coverage report
 */
function generateReport(): CoverageReport {
  const namespaceKeys = getLocaleKeysByNamespace();
  const webKeys = extractWebKeys();
  const docsKeys = extractDocsKeys();

  const namespaces: NamespaceCoverage[] = [];
  let totalKeys = 0;
  let totalWebUsed = 0;
  let totalDocsUsed = 0;
  let totalUnused = 0;

  const sortedNamespaces = [...namespaceKeys.entries()].sort((a, b) =>
    a[0].localeCompare(b[0])
  );

  for (const [namespace, keys] of sortedNamespaces) {
    let webUsed = 0;
    let docsUsed = 0;
    let unused = 0;

    for (const key of keys) {
      const fullKey = `${namespace}.${key}`;
      const usedInWeb = webKeys.has(fullKey);
      const usedInDocs = docsKeys.has(fullKey);

      if (usedInWeb) webUsed++;
      if (usedInDocs) docsUsed++;
      if (!usedInWeb && !usedInDocs) unused++;
    }

    const total = keys.length;
    namespaces.push({
      namespace,
      totalKeys: total,
      webUsed,
      docsUsed,
      unused,
      webPercent: total > 0 ? ((webUsed / total) * 100).toFixed(1) : '0.0',
      docsPercent: total > 0 ? ((docsUsed / total) * 100).toFixed(1) : '0.0',
      unusedPercent: total > 0 ? ((unused / total) * 100).toFixed(1) : '0.0',
    });

    totalKeys += total;
    totalWebUsed += webUsed;
    totalDocsUsed += docsUsed;
    totalUnused += unused;
  }

  return {
    namespaces,
    summary: {
      totalKeys,
      webUsed: totalWebUsed,
      docsUsed: totalDocsUsed,
      orphaned: totalUnused,
      webPercent: totalKeys > 0 ? ((totalWebUsed / totalKeys) * 100).toFixed(1) : '0.0',
      docsPercent: totalKeys > 0 ? ((totalDocsUsed / totalKeys) * 100).toFixed(1) : '0.0',
      orphanedPercent: totalKeys > 0 ? ((totalUnused / totalKeys) * 100).toFixed(1) : '0.0',
    },
  };
}

/**
 * Print human-readable report
 */
function printReport(report: CoverageReport): void {
  console.log('i18n Coverage Report');
  console.log('============================================================\n');

  for (const ns of report.namespaces) {
    console.log(`Namespace: ${ns.namespace} (${ns.totalKeys} keys)`);
    console.log(`  Web usage:  ${ns.webUsed}/${ns.totalKeys} (${ns.webPercent}%)`);
    console.log(`  Docs usage: ${ns.docsUsed}/${ns.totalKeys} (${ns.docsPercent}%)`);
    console.log(`  Unused:     ${ns.unused}/${ns.totalKeys} (${ns.unusedPercent}%)`);
    console.log();
  }

  console.log('SUMMARY');
  console.log('------------------------------------------------------------');
  console.log(`  Total keys:   ${report.summary.totalKeys.toLocaleString()}`);
  console.log(`  Used in web:  ${report.summary.webUsed.toLocaleString()} (${report.summary.webPercent}%)`);
  console.log(`  Used in docs: ${report.summary.docsUsed.toLocaleString()} (${report.summary.docsPercent}%)`);
  console.log(`  Orphaned:     ${report.summary.orphaned.toLocaleString()} (${report.summary.orphanedPercent}%)`);
  console.log();
}

function main(): void {
  const jsonMode = process.argv.includes('--json');
  const report = generateReport();

  if (jsonMode) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    printReport(report);
  }

  process.exit(0);
}

main();
