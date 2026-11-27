/**
 * Pins every number of PLAN-pricing-plan-model.md rulings R3-R8. These constants are the oracle the rest of the pricing program (seat and repository caps, CPU ceilings, free Professional, billing, the calculator) reads, so a changed value here must be a changed ruling.
 */
import { describe, expect, it } from 'vitest';
import {
  ENTERPRISE_MIN_FLOATING_LICENCES,
  FREE_PROFESSIONAL_LIMITS,
  getPerLicenceDimensions,
  getPlanBaseLimits,
  getPlanPricing,
  LARGE_MACHINE_PASS,
  MONTHLY_BILLING_MARKUP,
  PLAN_CAPS,
  PLAN_EDITION_RATE_USD_PER_YEAR,
  PLAN_FLOATING_LICENCES,
  PLAN_LIMITS,
  PLAN_PER_LICENCE_DIMENSIONS,
  PLAN_PRICING,
} from '../constants.js';

const GIB = 1024 ** 3;

describe('controls: unknown inputs fall back to COMMUNITY', () => {
  it('resolves an unknown plan code to the COMMUNITY base', () => {
    expect(getPlanBaseLimits('INVALID')).toEqual({
      ...PLAN_LIMITS.COMMUNITY,
      ...PLAN_CAPS.COMMUNITY,
    });
    expect(getPlanBaseLimits('INVALID').maxCpusPerMachine).toBe(16);
    expect(getPlanBaseLimits('INVALID').maxUsers).toBe(1);
    expect(getPerLicenceDimensions('INVALID')).toEqual([]);
    expect(getPlanPricing('INVALID')).toEqual(PLAN_PRICING.COMMUNITY);
  });

  it('never grants a paid plan for free: free-eligible on a code other than PROFESSIONAL is COMMUNITY', () => {
    const community = { ...PLAN_LIMITS.COMMUNITY, ...PLAN_CAPS.COMMUNITY };
    expect(getPlanBaseLimits('BUSINESS', 'free-eligible')).toEqual(community);
    expect(getPlanBaseLimits('ENTERPRISE', 'free-eligible')).toEqual(community);
    expect(getPlanBaseLimits('INVALID', 'free-eligible')).toEqual(community);
  });
});

describe('R3: per-floating-licence prices from the catalog edition rates', () => {
  it('states the catalog edition rates per licence per year', () => {
    expect(PLAN_EDITION_RATE_USD_PER_YEAR).toEqual({
      PROFESSIONAL: 550,
      BUSINESS: 700,
      ENTERPRISE: 900,
    });
    expect(MONTHLY_BILLING_MARKUP).toBe(1.15);
  });

  it('prices annual at the rate and monthly at round(rate x 1.15 / 12) dollars', () => {
    expect(PLAN_PRICING.PROFESSIONAL).toEqual({
      monthlyPriceCents: 5_300,
      annualPriceCents: 55_000,
      currency: 'usd',
    });
    expect(PLAN_PRICING.BUSINESS).toEqual({
      monthlyPriceCents: 6_700,
      annualPriceCents: 70_000,
      currency: 'usd',
    });
    expect(PLAN_PRICING.ENTERPRISE).toEqual({
      monthlyPriceCents: 8_600,
      annualPriceCents: 90_000,
      currency: 'usd',
    });
  });

  it('keeps FREE and COMMUNITY at zero', () => {
    for (const code of ['FREE', 'COMMUNITY'] as const) {
      expect(PLAN_PRICING[code].monthlyPriceCents).toBe(0);
      expect(PLAN_PRICING[code].annualPriceCents).toBe(0);
    }
  });
});

describe('R4: CPU ceiling per machine in logical CPUs', () => {
  it('states the ceiling for every tier', () => {
    expect(getPlanBaseLimits('FREE').maxCpusPerMachine).toBe(16);
    expect(getPlanBaseLimits('COMMUNITY').maxCpusPerMachine).toBe(16);
    expect(getPlanBaseLimits('PROFESSIONAL', 'free-eligible').maxCpusPerMachine).toBe(16);
    expect(getPlanBaseLimits('PROFESSIONAL').maxCpusPerMachine).toBe(32);
    expect(getPlanBaseLimits('BUSINESS').maxCpusPerMachine).toBe(64);
    expect(getPlanBaseLimits('ENTERPRISE').maxCpusPerMachine).toBeNull();
  });
});

describe('R5: users and original repositories', () => {
  it('states the user caps (FREE and COMMUNITY 1 per seat-repo-caps R1)', () => {
    expect(getPlanBaseLimits('FREE').maxUsers).toBe(1);
    expect(getPlanBaseLimits('COMMUNITY').maxUsers).toBe(1);
    expect(getPlanBaseLimits('PROFESSIONAL', 'free-eligible').maxUsers).toBe(10);
    expect(getPlanBaseLimits('PROFESSIONAL').maxUsers).toBe(25);
    expect(getPlanBaseLimits('BUSINESS').maxUsers).toBeNull();
    expect(getPlanBaseLimits('ENTERPRISE').maxUsers).toBeNull();
  });

  it('states the repository caps, Professional and Business per licence, Enterprise per quote', () => {
    expect(getPlanBaseLimits('PROFESSIONAL', 'free-eligible').maxRepositories).toBe(25);
    expect(getPlanBaseLimits('PROFESSIONAL').maxRepositories).toBe(100);
    expect(getPlanBaseLimits('BUSINESS').maxRepositories).toBe(250);
    expect(getPlanBaseLimits('ENTERPRISE').maxRepositories).toBeNull();
    expect(getPerLicenceDimensions('PROFESSIONAL')).toContain('maxRepositories');
    expect(getPerLicenceDimensions('BUSINESS')).toContain('maxRepositories');
  });

  it('never scales users per licence', () => {
    for (const dims of Object.values(PLAN_PER_LICENCE_DIMENSIONS)) {
      expect(dims).not.toContain('maxUsers');
    }
  });
});

describe('R6: setups and hosted R2', () => {
  it('gives free Professional 500 setups a month and 25 GiB, PROFESSIONAL for everything else', () => {
    const free = getPlanBaseLimits('PROFESSIONAL', 'free-eligible');
    expect(free.maxRepoLicenseIssuancesPerMonth).toBe(500);
    expect(free.storageQuotaBytes).toBe(25 * GIB);
    expect(FREE_PROFESSIONAL_LIMITS.storageQuotaBytes).toBe(25 * GIB);
    expect(free.maxRepositorySizeGb).toBe(PLAN_LIMITS.PROFESSIONAL.maxRepositorySizeGb);
    expect(getPerLicenceDimensions('PROFESSIONAL', 'free-eligible')).toEqual([]);
  });

  it('keeps paid Professional at 2,000 setups and 100 GiB per licence, Business at 5,000 and 500 GiB', () => {
    expect(getPlanBaseLimits('PROFESSIONAL').maxRepoLicenseIssuancesPerMonth).toBe(2000);
    expect(getPlanBaseLimits('PROFESSIONAL').storageQuotaBytes).toBe(100 * GIB);
    expect(getPlanBaseLimits('BUSINESS').maxRepoLicenseIssuancesPerMonth).toBe(5000);
    expect(getPlanBaseLimits('BUSINESS').storageQuotaBytes).toBe(500 * GIB);
    for (const code of ['PROFESSIONAL', 'BUSINESS'] as const) {
      expect(getPerLicenceDimensions(code)).toEqual([
        'maxRepositories',
        'maxRepoLicenseIssuancesPerMonth',
        'storageQuotaBytes',
      ]);
    }
    expect(getPerLicenceDimensions('ENTERPRISE')).toEqual([]);
  });
});

describe('R7: floating licences per subscription', () => {
  it('sells Professional 1-5 and Business 1-39 self-serve, Enterprise from the catalog minimum of 40', () => {
    expect(PLAN_FLOATING_LICENCES.PROFESSIONAL).toEqual({ min: 1, max: 5 });
    expect(PLAN_FLOATING_LICENCES.BUSINESS).toEqual({ min: 1, max: 39 });
    expect(PLAN_FLOATING_LICENCES.ENTERPRISE).toEqual({ min: 40, max: null });
    expect(ENTERPRISE_MIN_FLOATING_LICENCES).toBe(40);
  });
});

describe('R8: the large-machine add-on', () => {
  it('states the pass size, prices and limits', () => {
    expect(LARGE_MACHINE_PASS).toEqual({
      cpusPerPass: 8,
      monthlyPriceCents: 5_000,
      annualPriceCents: 20_000,
      currency: 'usd',
      maxPassesPerMachine: 4,
      maxMachinesWithPassesPerSubscription: 3,
    });
  });

  it('lifts a Business machine to at most 96 CPUs before Enterprise', () => {
    const top =
      (PLAN_CAPS.BUSINESS.maxCpusPerMachine ?? 0) +
      LARGE_MACHINE_PASS.cpusPerPass * LARGE_MACHINE_PASS.maxPassesPerMachine;
    expect(top).toBe(96);
  });
});
