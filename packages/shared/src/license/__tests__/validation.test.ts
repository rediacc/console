import { describe, expect, it } from 'vitest';
import { PLAN_FEATURES, PLAN_RESOURCES } from '../constants.js';
import {
  calculateGracePeriodEnd,
  decodeLicensePayload,
  encodeLicensePayload,
  getEffectivePlanCode,
  isGracePeriodExpired,
  isInGracePeriod,
  isLicenseActive,
  isLicenseExpired,
  validateLicense,
  validateLicenseData,
  validateOrganizationLicense,
  validateResourceLimits,
  validateSignedBlob,
} from '../validation.js';
import type { LicenseData, OrganizationLicense, SignedLicenseBlob } from '../types.js';

const createValidLicenseData = (overrides: Partial<LicenseData> = {}): LicenseData => ({
  version: 1,
  licenseId: 'test-license-id',
  organizationId: 1,
  customerId: 'test-customer',
  planCode: 'PROFESSIONAL',
  status: 'ACTIVE',
  issuedAt: '2026-01-01T00:00:00Z',
  expiresAt: '2027-01-01T00:00:00Z',
  lastCheckIn: new Date().toISOString(),
  gracePeriodEnds: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
  resources: PLAN_RESOURCES.PROFESSIONAL,
  features: PLAN_FEATURES.PROFESSIONAL,
  maxActivations: 5,
  activationCount: 1,
  ...overrides,
});

describe('License Validation', () => {
  describe('validateLicenseData', () => {
    it('should return true for valid license data', () => {
      const data = createValidLicenseData();
      expect(validateLicenseData(data)).toBe(true);
    });

    it('should return false for null', () => {
      expect(validateLicenseData(null)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(validateLicenseData(undefined)).toBe(false);
    });

    it('should return false for non-object', () => {
      expect(validateLicenseData('string')).toBe(false);
      expect(validateLicenseData(123)).toBe(false);
    });

    it('should return false for missing required fields', () => {
      const data = createValidLicenseData();
      delete (data as unknown as Record<string, unknown>).licenseId;
      expect(validateLicenseData(data)).toBe(false);
    });

    it('should return false for invalid plan code', () => {
      const data = createValidLicenseData({ planCode: 'INVALID' as 'PROFESSIONAL' });
      expect(validateLicenseData(data)).toBe(false);
    });

    it('should return false for missing resources', () => {
      const data = createValidLicenseData();
      delete (data as unknown as Record<string, unknown>).resources;
      expect(validateLicenseData(data)).toBe(false);
    });

    it('should return false for missing features', () => {
      const data = createValidLicenseData();
      delete (data as unknown as Record<string, unknown>).features;
      expect(validateLicenseData(data)).toBe(false);
    });
  });

  describe('validateSignedBlob', () => {
    it('should return true for valid signed blob', () => {
      const blob: SignedLicenseBlob = {
        payload: 'dGVzdA==',
        signature: 'c2lnbmF0dXJl',
        publicKeyId: 'key-2026-01',
      };
      expect(validateSignedBlob(blob)).toBe(true);
    });

    it('should return false for empty payload', () => {
      const blob = {
        payload: '',
        signature: 'c2lnbmF0dXJl',
        publicKeyId: 'key-2026-01',
      };
      expect(validateSignedBlob(blob)).toBe(false);
    });

    it('should return false for missing fields', () => {
      expect(validateSignedBlob({ payload: 'test' })).toBe(false);
      expect(validateSignedBlob({})).toBe(false);
      expect(validateSignedBlob(null)).toBe(false);
    });
  });

  describe('validateOrganizationLicense', () => {
    it('should return true for valid organization license', () => {
      const license: OrganizationLicense = {
        signedBlob: {
          payload: 'dGVzdA==',
          signature: 'c2lnbmF0dXJl',
          publicKeyId: 'key-2026-01',
        },
        cachedData: {
          planCode: 'PROFESSIONAL',
          status: 'ACTIVE',
          resources: PLAN_RESOURCES.PROFESSIONAL,
          features: PLAN_FEATURES.PROFESSIONAL,
          expiresAt: '2027-01-01T00:00:00Z',
          gracePeriodEnds: '2026-01-04T00:00:00Z',
        },
      };
      expect(validateOrganizationLicense(license)).toBe(true);
    });

    it('should return false for invalid signed blob', () => {
      const license = {
        signedBlob: {},
        cachedData: {
          planCode: 'PROFESSIONAL',
          status: 'ACTIVE',
          resources: {},
          features: {},
          expiresAt: '2027-01-01T00:00:00Z',
          gracePeriodEnds: '2026-01-04T00:00:00Z',
        },
      };
      expect(validateOrganizationLicense(license)).toBe(false);
    });
  });

  describe('validateResourceLimits', () => {
    it('should return true for valid resource limits', () => {
      expect(validateResourceLimits(PLAN_RESOURCES.COMMUNITY)).toBe(true);
      expect(validateResourceLimits(PLAN_RESOURCES.ENTERPRISE)).toBe(true);
    });

    it('should return false for missing fields', () => {
      expect(validateResourceLimits({ bridges: 0 })).toBe(false);
    });

    it('should return false for non-numeric values', () => {
      const invalid = { ...PLAN_RESOURCES.COMMUNITY, bridges: 'zero' };
      expect(validateResourceLimits(invalid)).toBe(false);
    });
  });
});

describe('License Status Functions', () => {
  describe('isLicenseActive', () => {
    it('should return true for ACTIVE status', () => {
      expect(isLicenseActive('ACTIVE')).toBe(true);
    });

    it('should return true for GRACE status', () => {
      expect(isLicenseActive('GRACE')).toBe(true);
    });

    it('should return false for other statuses', () => {
      expect(isLicenseActive('INACTIVE')).toBe(false);
      expect(isLicenseActive('EXPIRED')).toBe(false);
      expect(isLicenseActive('SUSPENDED')).toBe(false);
    });
  });

  describe('isLicenseExpired', () => {
    it('should return true for past date', () => {
      expect(isLicenseExpired('2020-01-01T00:00:00Z')).toBe(true);
      expect(isLicenseExpired(new Date('2020-01-01'))).toBe(true);
    });

    it('should return false for future date', () => {
      expect(isLicenseExpired('2099-01-01T00:00:00Z')).toBe(false);
      expect(isLicenseExpired(new Date('2099-01-01'))).toBe(false);
    });

    it('should return false for expiry just barely in the future', () => {
      const future = new Date(Date.now() + 10_000).toISOString();
      expect(isLicenseExpired(future)).toBe(false);
    });
  });

  describe('isGracePeriodExpired', () => {
    it('should return true when grace period has passed', () => {
      const past = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      expect(isGracePeriodExpired(past)).toBe(true);
    });

    it('should return false when grace period is in future', () => {
      const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
      expect(isGracePeriodExpired(future)).toBe(false);
    });
  });

  describe('isInGracePeriod', () => {
    it('should return false when within check-in interval', () => {
      const now = Date.now();
      const lastCheckIn = new Date(now - 1000).toISOString(); // 1 second ago
      const gracePeriodEnds = new Date(now + 3 * 24 * 60 * 60 * 1000).toISOString();
      expect(isInGracePeriod(lastCheckIn, gracePeriodEnds)).toBe(false);
    });

    it('should return true when past check-in interval but before grace expires', () => {
      const now = Date.now();
      const lastCheckIn = new Date(now - 48 * 60 * 60 * 1000).toISOString(); // 2 days ago
      const gracePeriodEnds = new Date(now + 24 * 60 * 60 * 1000).toISOString(); // 1 day from now
      expect(isInGracePeriod(lastCheckIn, gracePeriodEnds)).toBe(true);
    });

    it('should return false when check-in is just under the 24h interval', () => {
      const now = Date.now();
      const lastCheckIn = new Date(now - 23 * 60 * 60 * 1000 - 59 * 60 * 1000).toISOString(); // 23h59m ago
      const gracePeriodEnds = new Date(now + 3 * 24 * 60 * 60 * 1000).toISOString();
      expect(isInGracePeriod(lastCheckIn, gracePeriodEnds)).toBe(false);
    });

    it('should return false when grace period end is in the past', () => {
      const now = Date.now();
      const lastCheckIn = new Date(now - 48 * 60 * 60 * 1000).toISOString(); // 2 days ago
      const gracePeriodEnds = new Date(now - 1 * 60 * 60 * 1000).toISOString(); // 1 hour ago
      expect(isInGracePeriod(lastCheckIn, gracePeriodEnds)).toBe(false);
    });
  });

  describe('calculateGracePeriodEnd', () => {
    it('should add grace period days to last check-in', () => {
      const checkIn = new Date('2026-01-01T00:00:00Z');
      const graceEnd = calculateGracePeriodEnd(checkIn);
      expect(graceEnd.toISOString()).toBe('2026-01-04T00:00:00.000Z');
    });
  });

  describe('getEffectivePlanCode', () => {
    it('should return original plan if grace period not expired', () => {
      const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
      expect(getEffectivePlanCode('ENTERPRISE', future)).toBe('ENTERPRISE');
    });

    it('should return COMMUNITY if grace period expired', () => {
      const past = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      expect(getEffectivePlanCode('ENTERPRISE', past)).toBe('COMMUNITY');
    });
  });
});

describe('License Validation Function', () => {
  describe('validateLicense', () => {
    it('should return valid for active license', () => {
      const data = createValidLicenseData();
      const result = validateLicense(data);
      expect(result.valid).toBe(true);
      expect(result.data).toBeDefined();
    });

    it('should return invalid for suspended license', () => {
      const data = createValidLicenseData({ status: 'SUSPENDED' });
      const result = validateLicense(data);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('suspended');
    });

    it('should return invalid for inactive license', () => {
      const data = createValidLicenseData({ status: 'INACTIVE' });
      const result = validateLicense(data);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('not activated');
    });

    it('should return invalid for expired license', () => {
      const data = createValidLicenseData({
        expiresAt: '2020-01-01T00:00:00Z',
      });
      const result = validateLicense(data);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('expired');
    });

    it('should indicate grace period when active', () => {
      const now = Date.now();
      const data = createValidLicenseData({
        lastCheckIn: new Date(now - 48 * 60 * 60 * 1000).toISOString(),
        gracePeriodEnds: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateLicense(data);
      expect(result.valid).toBe(true);
      expect(result.inGracePeriod).toBe(true);
    });

    it('should degrade to COMMUNITY when grace period expired', () => {
      const data = createValidLicenseData({
        planCode: 'ENTERPRISE',
        gracePeriodEnds: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateLicense(data);
      expect(result.valid).toBe(true);
      expect(result.data?.planCode).toBe('COMMUNITY');
      expect(result.inGracePeriod).toBe(true);
    });

    it('should return valid when now equals expiresAt exactly', () => {
      const expiresAt = '2027-06-15T12:00:00.000Z';
      const now = new Date(expiresAt);
      const data = createValidLicenseData({ expiresAt });
      const result = validateLicense(data, now);
      expect(result.valid).toBe(true);
    });

    it('should return invalid when now is 1ms after expiresAt', () => {
      const expiresAt = '2027-06-15T12:00:00.000Z';
      const now = new Date(new Date(expiresAt).getTime() + 1);
      const data = createValidLicenseData({ expiresAt });
      const result = validateLicense(data, now);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('expired');
    });

    it('should detect grace period when check-in is just past 24h interval', () => {
      const now = Date.now();
      const data = createValidLicenseData({
        lastCheckIn: new Date(now - 24 * 60 * 60 * 1000 - 60 * 1000).toISOString(), // 24h + 1min ago
        gracePeriodEnds: new Date(now + 2 * 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateLicense(data);
      expect(result.valid).toBe(true);
      expect(result.inGracePeriod).toBe(true);
    });

    it('should NOT detect grace period when check-in is just under 24h interval', () => {
      const now = Date.now();
      const data = createValidLicenseData({
        lastCheckIn: new Date(now - 23 * 60 * 60 * 1000 - 59 * 60 * 1000).toISOString(), // 23h59m ago
        gracePeriodEnds: new Date(now + 2 * 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateLicense(data);
      expect(result.valid).toBe(true);
      expect(result.inGracePeriod).toBe(false);
    });
  });
});

describe('License Payload Encoding/Decoding', () => {
  describe('encodeLicensePayload', () => {
    it('should encode license data to base64', () => {
      const data = createValidLicenseData();
      const encoded = encodeLicensePayload(data);
      expect(typeof encoded).toBe('string');
      expect(encoded.length).toBeGreaterThan(0);
    });
  });

  describe('decodeLicensePayload', () => {
    it('should decode valid base64 payload', () => {
      const data = createValidLicenseData();
      const encoded = encodeLicensePayload(data);
      const decoded = decodeLicensePayload(encoded);
      expect(decoded).not.toBeNull();
      expect(decoded?.licenseId).toBe(data.licenseId);
    });

    it('should return null for invalid base64', () => {
      expect(decodeLicensePayload('not-valid-base64!!!')).toBeNull();
    });

    it('should return null for valid base64 with invalid JSON', () => {
      const invalidJson = btoa('not json');
      expect(decodeLicensePayload(invalidJson)).toBeNull();
    });

    it('should return null for valid JSON but invalid license data', () => {
      const invalidData = btoa(JSON.stringify({ foo: 'bar' }));
      expect(decodeLicensePayload(invalidData)).toBeNull();
    });
  });
});
