#!/usr/bin/env tsx
/**
 * check-pricing-consistency — blocking gate tying packages/www's displayed
 * plan-limit numbers to packages/shared's canonical PLAN_LIMITS/PLAN_MAX_MACHINES.
 *
 * Before this script existed, nothing caught drift between the canonical
 * subscription constants and the marketing site's copy — the numbers were
 * hand-copied into three places inside en.json plus two documentation pages,
 * and they silently disagreed with each other and with the canonical source.
 *
 * Scope: this only checks the ENGLISH source (en.json + docs/en/*.md). The 12
 * translated locale files carry the same digits embedded in translated prose,
 * which can't be generically parsed across 12 languages. Coverage for those
 * relies on the existing i18n staleness gate (check-i18n-naturalization)
 * forcing a re-naturalization pass whenever the English source changes — that
 * is a process control, not a numeric one.
 *
 * Fix a failure: update packages/shared/src/subscription/constants.ts (if the
 * canonical value should change) or the www content (if it drifted from the
 * canonical value) so both sides agree again.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { type PlanCode, PLAN_LIMITS, PLAN_MAX_MACHINES, PLAN_ORDER } from '@rediacc/shared/subscription';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..');
const WWW_TRANSLATIONS_DIR = path.join(REPO_ROOT, 'packages/www/src/i18n/translations');
const WWW_DOCS_EN_DIR = path.join(REPO_ROOT, 'packages/www/src/content/docs/en');

const PLAN_ID_BY_CODE: Record<string, string> = {
  COMMUNITY: 'community',
  PROFESSIONAL: 'professional',
  BUSINESS: 'business',
  ENTERPRISE: 'enterprise',
};

// Paid tiers display their monthly cap with a "+" suffix (room to grow /
// contact for more); Community is a fixed free-tier cap, no suffix.
const PAID_PLAN_CODES = PLAN_ORDER.filter((code) => code !== 'COMMUNITY');

let failures = 0;

function fail(message: string): void {
  console.error(`  ✗ ${message}`);
  failures++;
}

/** "2,000+" -> 2000; "10" -> 10; strips thousands separators and a trailing "+". */
function parseCount(raw: string): number | null {
  const cleaned = raw.replace(/,/g, '').replace(/\+$/, '').trim();
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function hasPlusSuffix(raw: string): boolean {
  return raw.trim().endsWith('+');
}

/**
 * Machine/floating-license counts must match PLAN_MAX_MACHINES numerically,
 * except ENTERPRISE: it is sold through partners with negotiated terms, so
 * customer-facing surfaces display "Custom" while PLAN_MAX_MACHINES.ENTERPRISE
 * stays the internal partner-deal default (see the PLAN_MAX_MACHINES comment
 * in packages/shared/src/subscription/constants.ts).
 */
function machinesDisplayMatches(code: (typeof PLAN_ORDER)[number], raw: string): boolean {
  if (code === 'ENTERPRISE' && raw.trim().toLowerCase() === 'custom') {
    return true;
  }
  return parseCount(raw) === PLAN_MAX_MACHINES[code];
}

function checkEnJson(): void {
  const en = JSON.parse(fs.readFileSync(path.join(WWW_TRANSLATIONS_DIR, 'en.json'), 'utf8'));
  const pricing = en.pages?.pricing;
  if (!pricing) {
    fail('en.json: pages.pricing not found');
    return;
  }

  // 1. technicalSummary.values[plan].jobsPerMonth / floatingLicenses
  const tsValues = pricing.technicalSummary?.values ?? {};
  for (const code of PLAN_ORDER) {
    const planId = PLAN_ID_BY_CODE[code];
    const entry = tsValues[planId];
    if (!entry) {
      fail(`en.json technicalSummary.values.${planId} missing`);
      continue;
    }
    const jobsPerMonth = parseCount(entry.jobsPerMonth ?? '');
    const canonicalIssuances = PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth;
    if (jobsPerMonth !== canonicalIssuances) {
      fail(
        `en.json technicalSummary.values.${planId}.jobsPerMonth = "${entry.jobsPerMonth}" ` +
          `(parsed ${jobsPerMonth}) does not match PLAN_LIMITS.${code}.maxRepoLicenseIssuancesPerMonth = ${canonicalIssuances}`
      );
    }
    // Widened for the membership test only: PAID_PLAN_CODES is the three paid
    // tiers, `code` is a PlanCode and may be COMMUNITY. At runtime .includes
    // simply returns false for it, which is the intended answer; the cast just
    // stops the narrow tuple type from rejecting the question.
    if ((PAID_PLAN_CODES as readonly PlanCode[]).includes(code) && !hasPlusSuffix(entry.jobsPerMonth ?? '')) {
      fail(
        `en.json technicalSummary.values.${planId}.jobsPerMonth = "${entry.jobsPerMonth}" ` +
          'is missing the "+" display convention for a paid tier'
      );
    }

    if (!machinesDisplayMatches(code, entry.floatingLicenses ?? '')) {
      fail(
        `en.json technicalSummary.values.${planId}.floatingLicenses = "${entry.floatingLicenses}" ` +
          `does not match PLAN_MAX_MACHINES.${code} = ${PLAN_MAX_MACHINES[code]} (or "Custom" for ENTERPRISE)`
      );
    }
  }

  // 2. comparison.categories.infrastructure.rows — duplicate of the same two metrics
  const rows = pricing.comparison?.categories?.infrastructure?.rows ?? [];
  const machinesRow = rows.find((r: { label?: string }) => /floating licenses/i.test(r.label ?? ''));
  const issuancesRow = rows.find((r: { label?: string }) => /server setups per month/i.test(r.label ?? ''));
  if (!machinesRow) fail('en.json comparison.categories.infrastructure.rows: Floating Licenses row not found');
  if (!issuancesRow) fail('en.json comparison.categories.infrastructure.rows: server-setups row not found');
  for (const code of PLAN_ORDER) {
    const planId = PLAN_ID_BY_CODE[code];
    if (machinesRow) {
      if (!machinesDisplayMatches(code, machinesRow[planId] ?? '')) {
        fail(
          `en.json comparison Floating-Licenses row.${planId} = "${machinesRow[planId]}" ` +
            `does not match PLAN_MAX_MACHINES.${code} = ${PLAN_MAX_MACHINES[code]} (or "Custom" for ENTERPRISE)`
        );
      }
    }
    if (issuancesRow) {
      const parsed = parseCount(issuancesRow[planId] ?? '');
      if (parsed !== PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth) {
        fail(
          `en.json comparison server-setups row.${planId} = "${issuancesRow[planId]}" ` +
            `does not match PLAN_LIMITS.${code}.maxRepoLicenseIssuancesPerMonth = ${PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth}`
        );
      }
    }
  }

  // 3. plans.*.features prose — extract the digit run from the "N server setups per month" bullet
  const plans = pricing.plans ?? {};
  for (const code of PLAN_ORDER) {
    const planId = PLAN_ID_BY_CODE[code];
    const features: string[] = plans[planId]?.features ?? [];
    const bullet = features.find((f) => /server setups per month/i.test(f));
    if (!bullet) {
      fail(`en.json pages.pricing.plans.${planId}.features: no "server setups per month" bullet found`);
      continue;
    }
    const match = /([\d,]+\+?)\s*server setups per month/i.exec(bullet);
    const parsed = match ? parseCount(match[1]) : null;
    if (parsed !== PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth) {
      fail(
        `en.json pages.pricing.plans.${planId}.features bullet "${bullet}" ` +
          `does not match PLAN_LIMITS.${code}.maxRepoLicenseIssuancesPerMonth = ${PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth}`
      );
    }
  }
}

interface MarkdownTableSpec {
  /** Row labels are ALL CAPS (account-management.md) vs Title Case (subscription-licensing.md). */
  rowLabelStyle: 'upper' | 'title';
  machinesCol: number;
  issuancesCol: number;
}

function checkMarkdownTable(fileName: string, spec: MarkdownTableSpec): void {
  const filePath = path.join(WWW_DOCS_EN_DIR, fileName);
  const content = fs.readFileSync(filePath, 'utf8');
  for (const code of PLAN_ORDER) {
    const rowLabel = spec.rowLabelStyle === 'upper' ? code : code[0] + code.slice(1).toLowerCase();
    const rowRegex = new RegExp(`\\|\\s*${rowLabel}\\s*\\|([^\\n]+)\\|`, 'i');
    const rowMatch = rowRegex.exec(content);
    if (!rowMatch) {
      fail(`${fileName}: table row for ${rowLabel} not found`);
      continue;
    }
    const cells = rowMatch[1].split('|').map((c) => c.trim());
    const issuances = parseCount(cells[spec.issuancesCol]);
    if (!machinesDisplayMatches(code, cells[spec.machinesCol])) {
      fail(
        `${fileName} row ${rowLabel}: machines column "${cells[spec.machinesCol]}" does not match ` +
          `PLAN_MAX_MACHINES.${code} = ${PLAN_MAX_MACHINES[code]} (or "Custom" for ENTERPRISE)`
      );
    }
    if (issuances !== PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth) {
      fail(
        `${fileName} row ${rowLabel}: issuances column "${cells[spec.issuancesCol]}" does not match ` +
          `PLAN_LIMITS.${code}.maxRepoLicenseIssuancesPerMonth = ${PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth}`
      );
    }
  }
}

function main(): number {
  console.log('Pricing Consistency Check');
  console.log('='.repeat(60));
  console.log('Checking en.json against @rediacc/shared/subscription...\n');

  checkEnJson();
  // | Plan | Floating Licenses | Repository Size | Monthly repo license issuances | ... |
  checkMarkdownTable('subscription-licensing.md', {
    rowLabelStyle: 'title',
    machinesCol: 0,
    issuancesCol: 2,
  });
  // | Plan | Machines | Repo Licenses/mo | Delegation cert default / max | Features |
  checkMarkdownTable('account-management.md', {
    rowLabelStyle: 'upper',
    machinesCol: 0,
    issuancesCol: 1,
  });

  if (failures > 0) {
    console.error(`\n${failures} pricing inconsistency(ies) found.`);
    return 1;
  }
  console.log('✓ All checked pricing numbers match @rediacc/shared/subscription');
  return 0;
}

process.exit(main());
