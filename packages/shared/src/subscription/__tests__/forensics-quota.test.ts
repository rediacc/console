import { describe, expect, it } from 'vitest';
import {
  getForensicsQuotaBytesForPlan,
  getPlanMetadata,
  getStorageQuotaBytesForPlan,
  PLAN_LIMITS,
  PLAN_METADATA,
  PLAN_ORDER,
  PROGRESSIVE_LIMIT_KEYS,
} from '../constants.js';

const GiB = 1024 ** 3;

describe('forensicsQuotaBytes', () => {
  it('carries the per-plan quotas of the shipping plan', () => {
    expect(PLAN_LIMITS.FREE.forensicsQuotaBytes).toBe(0);
    expect(PLAN_LIMITS.COMMUNITY.forensicsQuotaBytes).toBe(0);
    expect(PLAN_LIMITS.PROFESSIONAL.forensicsQuotaBytes).toBe(25 * GiB);
    expect(PLAN_LIMITS.BUSINESS.forensicsQuotaBytes).toBe(125 * GiB);
    expect(PLAN_LIMITS.ENTERPRISE.forensicsQuotaBytes).toBe(512 * GiB);
  });

  it('is a quarter of the storage quota on every plan that ships forensics', () => {
    for (const code of PLAN_ORDER) {
      const { forensicsQuotaBytes, storageQuotaBytes } = PLAN_LIMITS[code];
      if (forensicsQuotaBytes === 0) continue;
      expect(forensicsQuotaBytes, code).toBe(storageQuotaBytes / 4);
    }
  });

  it('is tracked as a progressive limit', () => {
    expect(PROGRESSIVE_LIMIT_KEYS).toContain('forensicsQuotaBytes');
  });

  it('reads the plan value and falls back to COMMUNITY for an unknown plan', () => {
    expect(getForensicsQuotaBytesForPlan('BUSINESS')).toBe(125 * GiB);
    expect(getForensicsQuotaBytesForPlan('NOPE')).toBe(PLAN_LIMITS.COMMUNITY.forensicsQuotaBytes);
  });

  it('treats an inherited object key as an unknown plan (review 68e1565f.2)', () => {
    for (const code of ['toString', 'constructor', '__proto__']) {
      expect(getForensicsQuotaBytesForPlan(code), code).toBe(
        PLAN_LIMITS.COMMUNITY.forensicsQuotaBytes
      );
      expect(getStorageQuotaBytesForPlan(code), code).toBe(PLAN_LIMITS.COMMUNITY.storageQuotaBytes);
      expect(getPlanMetadata(code).displayName, code).toBe(PLAN_METADATA.COMMUNITY.displayName);
    }
  });

  it('pins selfServe per plan (review 68e1565f.1)', () => {
    expect(PLAN_ORDER.filter((code) => PLAN_METADATA[code].selfServe)).toEqual([]);
  });
});

describe('rediaccAiCredits plan flag', () => {
  it('is true for ENTERPRISE alone', () => {
    for (const code of PLAN_ORDER) {
      expect(PLAN_METADATA[code].rediaccAiCredits, code).toBe(code === 'ENTERPRISE');
    }
  });

  it('reads false for an unknown plan through the COMMUNITY fallback', () => {
    expect(getPlanMetadata('NOPE').rediaccAiCredits).toBe(false);
  });
});
