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
 * PLAN-pricing-plan-model.md Design 5 adds four rules on top of the limit checks:
 * prices (docs table and the pricing page copy) against PLAN_PRICING, the user /
 * repository / CPU / hosted-R2 dimensions against PLAN_CAPS, PLAN_LIMITS and
 * FREE_PROFESSIONAL_LIMITS, floating-licence ranges against PLAN_FLOATING_LICENCES,
 * and every locale's technicalSummary.values against PLAN_LIMITS. Every run first
 * proves each rule can fail: the planted controls below mutate an in-memory copy of
 * the sources and each must produce a finding, or the gate itself fails.
 *
 * Fix a failure: update packages/shared/src/subscription/constants.ts (if the
 * canonical value should change) or the www content (if it drifted from the
 * canonical value) so both sides agree again.
 *
 * ---- gate ----
 * step: Pricing consistency
 * needs: node
 * lane: quality-content
 * ---- end gate ----
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
// The PM1 dimensions are not re-exported by the subscription index (packages/shared/src/subscription/index.ts, outside PM4's Owns, reported to the lead), so they come from the constants module directly.
import {
  FREE_PROFESSIONAL_LIMITS,
  LARGE_MACHINE_PASS,
  PLAN_CAPS,
  PLAN_FLOATING_LICENCES,
  PLAN_LIMITS,
  PLAN_MAX_MACHINES,
  PLAN_ORDER,
  PLAN_PER_LICENCE_DIMENSIONS,
  PLAN_PRICING,
} from '@rediacc/shared/subscription/constants';
import type { PlanCode } from '@rediacc/shared/subscription';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '..', '..');
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

// FREE is a plan code but not a priced card: it has no technicalSummary column and no row in either docs table, so a loop over PLAN_ORDER would report its absence as drift. Its limits are judged where they are defined, in packages/shared; this gate ties the DISPLAYED numbers of the priced plans to them.
const PRICED_PLAN_CODES = PLAN_ORDER.filter((code) => code !== 'FREE');

const GIB = 1024 ** 3;

/** The slice of a translation catalog this gate reads. */
interface TechnicalSummaryCell {
  jobsPerMonth?: string;
  floatingLicenses?: string;
  usersTeams?: string;
  repositories?: string;
}
interface PricingCopy {
  technicalSummary?: {
    metrics?: { key: string; label: string; tooltip?: string }[];
    values?: Record<string, TechnicalSummaryCell>;
  };
  [section: string]: unknown;
}
interface Catalog {
  pages?: { pricing?: PricingCopy };
}

/** The pricing copy of a catalog, for the planted controls that mutate it. */
function pricingCopy(
  catalog: Catalog
): PricingCopy & {
  technicalSummary: {
    metrics: { tooltip?: string }[];
    values: Record<string, TechnicalSummaryCell>;
  };
} {
  const ts = catalog.pages?.pricing?.technicalSummary;
  if (!catalog.pages?.pricing || !ts?.metrics || !ts.values) {
    throw new Error('catalog has no pages.pricing.technicalSummary to plant into');
  }
  return catalog.pages.pricing as ReturnType<typeof pricingCopy>;
}

/** Every file the gate reads, loaded once so the planted controls can mutate a copy. */
interface Sources {
  /** Parsed en.json. */
  en: Catalog;
  /** Parsed locale catalogs by file name, English excluded. */
  locales: Record<string, Catalog>;
  /** English docs by file name. */
  docs: Record<string, string>;
}

type Findings = string[];

function loadSources(): Sources {
  const locales: Record<string, Catalog> = {};
  let en: Catalog | undefined;
  for (const name of fs
    .readdirSync(WWW_TRANSLATIONS_DIR)
    .filter((f) => /^[a-z]{2}\.json$/.test(f))) {
    const parsed = JSON.parse(fs.readFileSync(path.join(WWW_TRANSLATIONS_DIR, name), 'utf8'));
    if (name === 'en.json') en = parsed;
    else locales[name] = parsed;
  }
  const docs: Record<string, string> = {};
  for (const name of ['subscription-licensing.md', 'account-management.md']) {
    docs[name] = fs.readFileSync(path.join(WWW_DOCS_EN_DIR, name), 'utf8');
  }
  if (!en) throw new Error('en.json not found');
  return { en, locales, docs };
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
function machinesDisplayMatches(code: PlanCode, raw: string): boolean {
  if (code === 'ENTERPRISE' && raw.trim().toLowerCase() === 'custom') {
    return true;
  }
  return parseCount(raw) === PLAN_MAX_MACHINES[code];
}

/**
 * pages.pricing.technicalSummary.values cells that still print the pre-R5 "Unlimited" for a dimension PLAN_CAPS now bounds. The English pricing copy is rewritten by PLAN-pricing-public-calculator.md PC5 (www per Design 5), which owns en.json and the 12 locales; until it lands these four cells are waived so the gate is green on the tree, and each waiver FAILS the moment its cell is corrected, so PC5 deletes the entry rather than leaving a dead suppression.
 * BLOCKER: PC5 has not landed; the cells are en.json technicalSummary.values.{community.usersTeams, professional.usersTeams, professional.repositories, business.repositories}.
 */
const OWED_UNLIMITED_CELLS: ReadonlySet<string> = new Set([
  'community.usersTeams',
  'professional.usersTeams',
  'professional.repositories',
  'business.repositories',
]);

function isUnlimitedText(raw: string): boolean {
  return /^(unlimited|per quote|custom)$/i.test(raw.trim());
}

/** A displayed cap cell against a PLAN_CAPS value: null is "Unlimited" / "Per quote", a number is that number. */
function capCellMatches(cap: number | null, raw: string): boolean {
  if (cap === null) return isUnlimitedText(raw);
  return parseCount(raw.replace(/\s*per licen[cs]e\s*$/i, '')) === cap;
}

function checkEnJson(src: Sources): Findings {
  const out: Findings = [];
  const fail = (m: string) => out.push(m);
  const pricing = src.en.pages?.pricing;
  if (!pricing) {
    fail('en.json: pages.pricing not found');
    return out;
  }

  // 1. technicalSummary.values[plan].jobsPerMonth / floatingLicenses
  const tsValues = pricing.technicalSummary?.values ?? {};
  for (const code of PRICED_PLAN_CODES) {
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
    // Widened for the membership test only: PAID_PLAN_CODES is the three paid tiers, `code` is a PlanCode and may be COMMUNITY. At runtime .includes
    // simply returns false for it, which is the intended answer; the cast just
    // stops the narrow tuple type from rejecting the question.
    if (
      (PAID_PLAN_CODES as readonly PlanCode[]).includes(code) &&
      !hasPlusSuffix(entry.jobsPerMonth ?? '')
    ) {
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

    // 2. The user and repository caps (R5), PLAN_CAPS.
    for (const [key, cap] of [
      ['usersTeams', PLAN_CAPS[code].maxUsers],
      ['repositories', PLAN_CAPS[code].maxRepositories],
    ] as const) {
      const cell = String(entry[key] ?? '');
      const waived = OWED_UNLIMITED_CELLS.has(`${planId}.${key}`);
      const matches = capCellMatches(cap, cell);
      if (waived && matches) {
        fail(
          `en.json technicalSummary.values.${planId}.${key} = "${cell}" now matches PLAN_CAPS; ` +
            `delete "${planId}.${key}" from OWED_UNLIMITED_CELLS in scripts/gates/check-pricing-consistency.ts`
        );
      } else if (!waived && !matches) {
        fail(
          `en.json technicalSummary.values.${planId}.${key} = "${cell}" does not match ` +
            `PLAN_CAPS.${code}.${key === 'usersTeams' ? 'maxUsers' : 'maxRepositories'} = ${cap ?? 'unlimited'}`
        );
      }
    }
  }

  // 3. Prices. A plan price printed on the pricing page must be one PLAN_PRICING or the large-machine add-on carries. Scoped to pages.pricing minus professionalServices (a different product), so the refund-policy copy that still prints the old prices is PC5's, not this gate's.
  const allowed = allowedPriceDollars();
  const scoped: Record<string, unknown> = { ...pricing };
  delete scoped.professionalServices;
  for (const { where, text } of stringsOf(scoped, 'pages.pricing')) {
    for (const amount of recurringDollarAmounts(text)) {
      if (!allowed.has(amount)) {
        fail(
          `en.json ${where}: price $${amount} per period is not in PLAN_PRICING ` +
            `(allowed: ${[...allowed].map((n) => `$${n}`).join(', ')})`
        );
      }
    }
  }
  return out;
}

function allowedPriceDollars(): Set<number> {
  const out = new Set<number>();
  for (const code of PRICED_PLAN_CODES) {
    for (const cents of [
      PLAN_PRICING[code].monthlyPriceCents,
      PLAN_PRICING[code].annualPriceCents,
    ]) {
      if (cents > 0) out.add(cents / 100);
    }
  }
  out.add(LARGE_MACHINE_PASS.monthlyPriceCents / 100);
  out.add(LARGE_MACHINE_PASS.annualPriceCents / 100);
  return out;
}

/** Dollar amounts followed by a billing period ("$49/month", "$599 per year", "$67 a month", "$550/yr"). */
function recurringDollarAmounts(text: string): number[] {
  const out: number[] = [];
  const re = /\$\s?(\d[\d,]*(?:\.\d+)?)\s*(?:\/|per\s+|a\s+|each\s+)(?:month|mo|year|yr|annum)\b/gi;
  for (const m of text.matchAll(re)) out.push(Number(m[1].replace(/,/g, '')));
  return out;
}

function* stringsOf(node: unknown, where: string): Generator<{ where: string; text: string }> {
  if (typeof node === 'string') yield { where, text: node };
  else if (Array.isArray(node)) {
    for (const [i, v] of node.entries()) yield* stringsOf(v, `${where}[${i}]`);
  } else if (node && typeof node === 'object') {
    for (const [k, v] of Object.entries(node)) yield* stringsOf(v, `${where}.${k}`);
  }
}

/**
 * technicalSummary cells the 12 translated catalogs still print with pre-redesign numbers (measured 2026-11-27: 6 cells in each locale, 7 in it and ko). The 12 locales are derived from English by the naturalization pipeline, which PLAN-pricing-public-calculator.md PC5 runs after the English copy changes, so these are owed to it, not to this box. The list is shrink-only: a cell that now agrees must be deleted from it (the gate fails until it is), and a contradiction not on it fails at once.
 * BLOCKER: PC5's locale pass has not landed; the 12 catalogs are ar de es et fr it ja ko pt ru tr zh.
 */
const OWED_LOCALE_CELLS_COMMON: readonly string[] = [
  'community.floatingLicenses',
  'professional.jobsPerMonth',
  'professional.floatingLicenses',
  'business.jobsPerMonth',
  'business.floatingLicenses',
  'enterprise.jobsPerMonth',
];
const OWED_LOCALE_CELLS_EXTRA: Record<string, readonly string[]> = {
  'it.json': ['community.jobsPerMonth'],
  'ko.json': ['community.jobsPerMonth'],
};

/**
 * Every locale's technicalSummary.values must agree with PLAN_LIMITS. The prose around the
 * digits is translated and not parseable, but the digits are not: strip everything but them
 * and compare. A cell with no digits ("Custom" in some script) says nothing and is skipped.
 */
function checkLocales(src: Sources): Findings {
  const out: Findings = [];
  for (const [name, catalog] of Object.entries(src.locales)) {
    const values = catalog.pages?.pricing?.technicalSummary?.values;
    if (!values) {
      out.push(`${name}: pages.pricing.technicalSummary.values not found`);
      continue;
    }
    const owed = new Set([...OWED_LOCALE_CELLS_COMMON, ...(OWED_LOCALE_CELLS_EXTRA[name] ?? [])]);
    const contradicted = new Set<string>();
    const note = (planId: string, field: string, message: string) => {
      const key = `${planId}.${field}`;
      contradicted.add(key);
      if (!owed.has(key)) out.push(message);
    };
    for (const code of PRICED_PLAN_CODES) {
      const planId = PLAN_ID_BY_CODE[code];
      const entry = values[planId];
      if (!entry) {
        out.push(`${name}: technicalSummary.values.${planId} missing`);
        continue;
      }
      const jobsDigits = String(entry.jobsPerMonth ?? '').replace(/\D/g, '');
      if (jobsDigits !== String(PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth)) {
        note(
          planId,
          'jobsPerMonth',
          `${name}: technicalSummary.values.${planId}.jobsPerMonth = "${entry.jobsPerMonth}" ` +
            `contradicts PLAN_LIMITS.${code}.maxRepoLicenseIssuancesPerMonth = ${PLAN_LIMITS[code].maxRepoLicenseIssuancesPerMonth}`
        );
      }
      const licDigits = String(entry.floatingLicenses ?? '').replace(/\D/g, '');
      if (
        licDigits !== '' &&
        code !== 'ENTERPRISE' &&
        licDigits !== String(PLAN_MAX_MACHINES[code])
      ) {
        note(
          planId,
          'floatingLicenses',
          `${name}: technicalSummary.values.${planId}.floatingLicenses = "${entry.floatingLicenses}" ` +
            `contradicts PLAN_MAX_MACHINES.${code} = ${PLAN_MAX_MACHINES[code]}`
        );
      }
    }
    for (const key of owed) {
      if (!contradicted.has(key)) {
        out.push(
          `${name}: technicalSummary.values.${key} now agrees with shared; delete it from the owed-locale-cells list in scripts/gates/check-pricing-consistency.ts`
        );
      }
    }
  }
  return out;
}

interface MarkdownTableSpec {
  /** Row labels are ALL CAPS (account-management.md) vs Title Case (subscription-licensing.md). */
  rowLabelStyle: 'upper' | 'title';
  /** null: the file's machines column is a range judged by checkPlanModelTable, not a count. */
  machinesCol: number | null;
  /** Row label by plan code when it is not the code itself. */
  labels?: Record<string, string>;
  issuancesCol: number;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function checkMarkdownTable(src: Sources, fileName: string, spec: MarkdownTableSpec): Findings {
  const out: Findings = [];
  const fail = (m: string) => out.push(m);
  const content = src.docs[fileName];
  for (const code of PRICED_PLAN_CODES) {
    const rowLabel =
      spec.labels?.[code] ??
      (spec.rowLabelStyle === 'upper' ? code : code[0] + code.slice(1).toLowerCase());
    const rowRegex = new RegExp(`\\|\\s*${escapeRegExp(rowLabel)}\\s*\\|([^\\n]+)\\|`, 'i');
    const rowMatch = rowRegex.exec(content);
    if (!rowMatch) {
      fail(`${fileName}: table row for ${rowLabel} not found`);
      continue;
    }
    const cells = rowMatch[1].split('|').map((c) => c.trim());
    const issuances = parseCount(cells[spec.issuancesCol]);
    if (spec.machinesCol !== null && !machinesDisplayMatches(code, cells[spec.machinesCol])) {
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
  return out;
}

/** Row label in the docs plan-model table by plan code (R1: COMMUNITY is shown as "Registered (free)"). */
const DOC_PLAN_ROW_LABEL: Record<string, string> = {
  COMMUNITY: 'Registered (free)',
  PROFESSIONAL: 'Professional',
  BUSINESS: 'Business',
  ENTERPRISE: 'Enterprise',
};
const DOC_FREE_PROFESSIONAL_LABEL = 'Free Professional';

function parseTable(
  content: string,
  headerCell: string
): Map<string, Record<string, string>> | null {
  const lines = content.split('\n');
  const start = lines.findIndex(
    (l) => l.trim().startsWith('|') && l.includes(headerCell) && l.includes('Floating Licenses')
  );
  if (start === -1) return null;
  const split = (l: string) =>
    l
      .trim()
      .replace(/^\||\|$/g, '')
      .split('|')
      .map((c) => c.trim());
  const headers = split(lines[start]);
  const rows = new Map<string, Record<string, string>>();
  for (let i = start + 2; i < lines.length && lines[i].trim().startsWith('|'); i++) {
    const cells = split(lines[i]);
    rows.set(cells[0], Object.fromEntries(headers.map((h, j) => [h, cells[j] ?? ''])));
  }
  return rows;
}

function dollars(cents: number): string {
  return `$${cents / 100}`;
}

/**
 * The plan-model table in subscription-licensing.md (R1-R8): floating-licence ranges, issuances,
 * users, repositories, CPUs, hosted R2 and the per-licence price, each against shared.
 */
function checkPlanModelTable(src: Sources): Findings {
  const out: Findings = [];
  const fileName = 'subscription-licensing.md';
  const rows = parseTable(src.docs[fileName], 'Plan');
  if (!rows) {
    out.push(
      `${fileName}: plan-model table (header with "Plan" and "Floating Licenses") not found`
    );
    return out;
  }
  const cell = (label: string, header: string): string | null => {
    const row = rows.get(label);
    if (!row) {
      out.push(`${fileName}: plan-model table row "${label}" not found`);
      return null;
    }
    if (!(header in row)) {
      out.push(`${fileName}: plan-model table column "${header}" not found`);
      return null;
    }
    return row[header];
  };
  const expectCap = (label: string, header: string, cap: number | null, what: string) => {
    const raw = cell(label, header);
    if (raw !== null && !capCellMatches(cap, raw)) {
      out.push(
        `${fileName} row ${label}: "${header}" = "${raw}" does not match ${what} = ${cap ?? 'unlimited'}`
      );
    }
  };

  const freeProfessional = {
    ...PLAN_LIMITS.PROFESSIONAL,
    ...PLAN_CAPS.PROFESSIONAL,
    ...FREE_PROFESSIONAL_LIMITS,
  };
  const specs: {
    label: string;
    code: PlanCode;
    base: typeof freeProfessional | ((typeof PLAN_LIMITS)[PlanCode] & (typeof PLAN_CAPS)[PlanCode]);
    free: boolean;
  }[] = [
    ...PRICED_PLAN_CODES.map((code) => ({
      label: DOC_PLAN_ROW_LABEL[code],
      code,
      base: { ...PLAN_LIMITS[code], ...PLAN_CAPS[code] },
      free: false,
    })),
    {
      label: DOC_FREE_PROFESSIONAL_LABEL,
      code: 'PROFESSIONAL',
      base: freeProfessional,
      free: true,
    },
  ];

  for (const { label, code, base, free } of specs) {
    const where = free ? 'FREE_PROFESSIONAL_LIMITS' : `PLAN_*.${code}`;
    expectCap(label, 'Users', base.maxUsers, `${where}.maxUsers`);
    expectCap(label, 'Repositories', base.maxRepositories, `${where}.maxRepositories`);
    expectCap(label, 'CPUs per machine', base.maxCpusPerMachine, `${where}.maxCpusPerMachine`);

    const issuances = cell(label, 'Monthly repo license issuances');
    if (issuances !== null && parseCount(issuances) !== base.maxRepoLicenseIssuancesPerMonth) {
      out.push(
        `${fileName} row ${label}: issuances "${issuances}" does not match ` +
          `${where}.maxRepoLicenseIssuancesPerMonth = ${base.maxRepoLicenseIssuancesPerMonth}`
      );
    }

    // Per-licence dimensions say so in the cell; the others must not.
    const perLicence = !free && PLAN_PER_LICENCE_DIMENSIONS[code].includes('maxRepositories');
    const repos = cell(label, 'Repositories');
    if (
      repos !== null &&
      base.maxRepositories !== null &&
      /per licen[cs]e/i.test(repos) !== perLicence
    ) {
      out.push(
        `${fileName} row ${label}: Repositories "${repos}" ${perLicence ? 'must' : 'must not'} say "per licence" ` +
          `(PLAN_PER_LICENCE_DIMENSIONS.${code})`
      );
    }

    // Hosted R2, in GiB. COMMUNITY is skipped: R2 gives it none but constants.ts still carries the old 10 GiB, a PM-box-external value owed to the lead (see the report).
    if (code !== 'COMMUNITY') {
      const r2 = cell(label, 'Hosted R2');
      const expectGib = base.storageQuotaBytes / GIB;
      if (r2 !== null && parseCount(r2.replace(/\s*(GiB|GB)\b.*$/i, '')) !== expectGib) {
        out.push(
          `${fileName} row ${label}: Hosted R2 "${r2}" does not match ${where}.storageQuotaBytes = ${expectGib} GiB`
        );
      }
    }

    // Floating licences (R7): the self-serve range for the paid tiers, 1 elsewhere.
    const licences = cell(label, 'Floating Licenses');
    if (licences !== null) {
      const range =
        !free && code in PLAN_FLOATING_LICENCES
          ? PLAN_FLOATING_LICENCES[code as keyof typeof PLAN_FLOATING_LICENCES]
          : null;
      const expected = range
        ? range.max === null
          ? `${range.min}+`
          : `${range.min}-${range.max}`
        : '1';
      if (licences.replace(/\s/g, '') !== expected) {
        out.push(
          `${fileName} row ${label}: Floating Licenses "${licences}" does not match ${where} range "${expected}"`
        );
      }
    }

    // Price per licence: "$monthly / $annual", or "Free".
    const price = cell(label, 'Price per licence');
    if (price !== null) {
      const pricing = free ? PLAN_PRICING.FREE : PLAN_PRICING[code];
      const expected =
        pricing.annualPriceCents === 0
          ? 'Free'
          : `${dollars(pricing.monthlyPriceCents)} / ${dollars(pricing.annualPriceCents)}`;
      if (price.replace(/\s+/g, ' ') !== expected) {
        out.push(
          `${fileName} row ${label}: Price per licence "${price}" does not match PLAN_PRICING.${free ? 'FREE' : code} = "${expected}"`
        );
      }
    }
  }
  return out;
}

function runChecks(src: Sources): Findings {
  return [
    ...new Set([
      ...checkEnJson(src),
      ...checkLocales(src),
      // | Plan | Floating Licenses | Repository Size | Monthly repo license issuances | ... |
      ...checkMarkdownTable(src, 'subscription-licensing.md', {
        rowLabelStyle: 'title',
        machinesCol: null,
        issuancesCol: 2,
        labels: DOC_PLAN_ROW_LABEL,
      }),
      // | Plan | Machines | Repo Licenses/mo | Delegation cert default / max | Features |
      ...checkMarkdownTable(src, 'account-management.md', {
        rowLabelStyle: 'upper',
        machinesCol: 0,
        issuancesCol: 1,
      }),
      ...checkPlanModelTable(src),
    ]),
  ];
}

/**
 * The planted controls: each mutates a deep copy of the real sources the way one drift would, and the rule it names must then report a finding. A rule that stays quiet is a gate that cannot fail.
 */
const CONTROLS: { rule: string; plant: (src: Sources) => void }[] = [
  {
    rule: 'docs price column',
    plant: (s) => {
      s.docs['subscription-licensing.md'] = s.docs['subscription-licensing.md'].replace(
        '$53 / $550',
        '$49 / $499'
      );
    },
  },
  {
    rule: 'docs users column',
    plant: (s) => {
      s.docs['subscription-licensing.md'] = s.docs['subscription-licensing.md'].replace(
        /(\| Professional \|[^\n]*)/,
        (row) => row.replace('| 25 |', '| 26 |')
      );
    },
  },
  {
    rule: 'docs CPU column',
    plant: (s) => {
      s.docs['subscription-licensing.md'] = s.docs['subscription-licensing.md'].replace(
        /(\| Business \|[^\n]*)/,
        (row) => row.replace('| 64 |', '| 128 |')
      );
    },
  },
  {
    rule: 'docs free Professional row',
    plant: (s) => {
      s.docs['subscription-licensing.md'] = s.docs['subscription-licensing.md'].replace(
        /(\| Free Professional \|[^\n]*)/,
        (row) => row.replace('| 500 |', '| 2,000 |')
      );
    },
  },
  {
    rule: 'docs floating-licence range',
    plant: (s) => {
      s.docs['subscription-licensing.md'] = s.docs['subscription-licensing.md'].replace(
        '1-39',
        '1-40'
      );
    },
  },
  {
    rule: 'docs hosted R2 column',
    plant: (s) => {
      s.docs['subscription-licensing.md'] = s.docs['subscription-licensing.md'].replace(
        /(\| Professional \|[^\n]*)/,
        (row) => row.replace('| 100 GiB', '| 99 GiB')
      );
    },
  },
  {
    rule: 'pricing page price copy',
    plant: (s) => {
      pricingCopy(s.en).technicalSummary.metrics[0].tooltip = 'Professional is $49/month.';
    },
  },
  {
    rule: 'pricing page user cap',
    plant: (s) => {
      pricingCopy(s.en).technicalSummary.values.business.usersTeams = '50';
    },
  },
  {
    rule: 'pricing page owed-cell waiver goes stale',
    plant: (s) => {
      pricingCopy(s.en).technicalSummary.values.professional.repositories = '100';
    },
  },
  {
    rule: 'locale technicalSummary',
    plant: (s) => {
      pricingCopy(s.locales['de.json']).technicalSummary.values.community.jobsPerMonth = '1.234';
    },
  },
  {
    rule: 'issuances (existing)',
    plant: (s) => {
      pricingCopy(s.en).technicalSummary.values.business.jobsPerMonth = '4,000+';
    },
  },
];

/** Runs every planted control against the real sources; returns the rules that stayed quiet. */
function selfTest(real: Sources): string[] {
  const quiet: string[] = [];
  const baseline = runChecks(real).length;
  for (const { rule, plant } of CONTROLS) {
    const copy: Sources = structuredClone(real);
    plant(copy);
    const planted = runChecks(copy);
    if (planted.length <= baseline) quiet.push(rule);
  }
  return quiet;
}

function main(): number {
  console.log('Pricing Consistency Check');
  console.log('='.repeat(60));
  console.log(
    'Checking en.json, the locales and the docs against @rediacc/shared/subscription...\n'
  );

  const src = loadSources();
  // `--plant <rule>` applies one planted control to the sources and reports what the gate then says: rc 1 for every rule.
  const plantAt = process.argv.indexOf('--plant');
  if (plantAt !== -1) {
    const wanted = process.argv[plantAt + 1];
    const control = CONTROLS.find((c) => c.rule === wanted);
    if (!control) {
      console.error(
        `unknown control "${wanted}"; known: ${CONTROLS.map((c) => c.rule).join(' | ')}`
      );
      return 2;
    }
    control.plant(src);
    const planted = runChecks(src);
    for (const f of planted) console.error(`  ✗ ${f}`);
    console.error(`\nplanted control "${wanted}": ${planted.length} finding(s)`);
    return planted.length > 0 ? 1 : 0;
  }
  const findings = runChecks(src);
  for (const f of findings) console.error(`  ✗ ${f}`);

  const quiet = selfTest(src);
  for (const rule of quiet) {
    console.error(`  ✗ planted control "${rule}" produced no finding: that rule cannot fail`);
  }

  const total = findings.length + quiet.length;
  if (total > 0) {
    console.error(`\n${total} pricing inconsistency(ies) found.`);
    return 1;
  }
  console.log(
    `✓ All checked pricing numbers match @rediacc/shared/subscription (${CONTROLS.length} planted controls fire)`
  );
  return 0;
}

process.exit(main());
