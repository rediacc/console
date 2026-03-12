#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.join(__dirname, '..');
const TEMPLATE_DIR = path.join(ROOT_DIR, 'private/account/src/email/templates');
const LOCALES_DIR = path.join(ROOT_DIR, 'private/account/src/i18n/locales');
const LANGUAGES = ['en', 'ar', 'de', 'es', 'fr', 'ja', 'ru', 'tr', 'zh'] as const;
const TEMPLATE_FILES = ['auth.ts', 'billing.ts', 'contact.ts', 'newsletter.ts', 'organization.ts', 'security.ts'];
function flattenKeys(input: unknown, prefix = ''): string[] {
  if (typeof input === 'string') {
    return [prefix];
  }
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return [];
  }
  return Object.entries(input).flatMap(([key, value]) =>
    flattenKeys(value, prefix ? `${prefix}.${key}` : key)
  );
}

function readJson(filePath: string): Record<string, unknown> {
  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as Record<string, unknown>;
}

function findUsedTranslationKeys(content: string): Set<string> {
  const keys = new Set<string>();
  for (const match of content.matchAll(/t\(\s*`([^`]+)`/g)) {
    keys.add(match[1]);
  }
  for (const match of content.matchAll(/t\(\s*'([^']+)'/g)) {
    keys.add(match[1]);
  }
  return keys;
}

function hasRenderedEmailContract(content: string): boolean {
  const normalized = content.replace(/\s+/g, ' ');
  return normalized.includes('subject:') && normalized.includes('html:') && normalized.includes('text:');
}

function main(): void {
  console.log('Account Email Template Validation');
  console.log('============================================================\n');

  const errors: string[] = [];
  const englishKeys = new Set(flattenKeys(readJson(path.join(LOCALES_DIR, 'en', 'emails.json'))));

  for (const lang of LANGUAGES) {
    const localePath = path.join(LOCALES_DIR, lang, 'emails.json');
    const localeKeys = new Set(flattenKeys(readJson(localePath)));

    for (const key of englishKeys) {
      if (!localeKeys.has(key)) {
        errors.push(`${lang}/emails.json: missing key "${key}"`);
      }
    }
  }

  for (const fileName of TEMPLATE_FILES) {
    const filePath = path.join(TEMPLATE_DIR, fileName);
    const content = fs.readFileSync(filePath, 'utf8');
    const usedKeys = findUsedTranslationKeys(content);

    if (!hasRenderedEmailContract(content)) {
      errors.push(`${fileName}: expected template renderer with subject/html/text output`);
    }

    if (usedKeys.size === 0) {
      errors.push(`${fileName}: no translation keys found; template files must render locale-backed content`);
    }

    if (/subject:\s*['"`]/.test(content)) {
      errors.push(`${fileName}: subject must come from locale keys, not a hardcoded literal`);
    }

    if (/text:\s*['"`]/.test(content)) {
      errors.push(`${fileName}: text body must come from locale-backed rendering, not a hardcoded literal`);
    }

    for (const key of usedKeys) {
      const concreteKey = key.includes('${') ? null : key;
      if (concreteKey && !englishKeys.has(concreteKey)) {
        errors.push(`${fileName}: references missing email locale key "${concreteKey}"`);
      }
    }
  }

  if (errors.length > 0) {
    console.log('\u001B[31mErrors:\u001B[0m');
    for (const error of errors) {
      console.log(`  \u001B[31m✗\u001B[0m ${error}`);
    }
    console.log('\n\u001B[31m✗ Account email template validation FAILED\u001B[0m');
    process.exit(1);
  }

  console.log('\u001B[32m✓\u001B[0m Account email templates and locales are valid\n');
}

main();
