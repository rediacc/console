import { describe, expect, it } from 'vitest';
import { PLAN_FEATURES, PLAN_RESOURCES } from '../constants.js';
import {
  calculateGracePeriodEnd,
  decodeSubscriptionPayload,
  encodeSubscriptionPayload,
  getEffectivePlanCode,
  isGracePeriodExpired,
  isInGracePeriod,
  isSubscriptionActive,
  isSubscriptionExpired,
  validateSubscription,
  validateSubscriptionData,
  validateOrganizationSubscription,
  validateResourceLimits,
  validateSignedBlob,
} from '../validation.js';
import type {
  SubscriptionData,
  OrganizationSubscription,
  SignedSubscriptionBlob,
} from '../types.js';

const createValidSubscriptionData = (
  overrides: Partial<SubscriptionData> = {}
): SubscriptionData => ({
  version: 1,
  subscriptionId: 'test-subscription-id',
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

describe('Subscription Validation', () => {
  describe('validateSubscriptionData', () => {
    it('should return true for valid subscription data', () => {
      const data = createValidSubscriptionData();
      expect(validateSubscriptionData(data)).toBe(true);
    });

    it('should return false for null', () => {
      expect(validateSubscriptionData(null)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(validateSubscriptionData(undefined)).toBe(false);
    });

    it('should return false for non-object', () => {
      expect(validateSubscriptionData('string')).toBe(false);
      expect(validateSubscriptionData(123)).toBe(false);
    });

    it('should return false for missing required fields', () => {
      const data = createValidSubscriptionData();
      delete (data as unknown as Record<string, unknown>).subscriptionId;
      expect(validateSubscriptionData(data)).toBe(false);
    });

    it('should return false for invalid plan code', () => {
      const data = createValidSubscriptionData({ planCode: 'INVALID' as 'PROFESSIONAL' });
      expect(validateSubscriptionData(data)).toBe(false);
    });

    it('should return false for missing resources', () => {
      const data = createValidSubscriptionData();
      delete (data as unknown as Record<string, unknown>).resources;
      expect(validateSubscriptionData(data)).toBe(false);
    });

    it('should return false for missing features', () => {
      const data = createValidSubscriptionData();
      delete (data as unknown as Record<string, unknown>).features;
      expect(validateSubscriptionData(data)).toBe(false);
    });
  });

  describe('validateSignedBlob', () => {
    it('should return true for valid signed blob', () => {
      const blob: SignedSubscriptionBlob = {
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

  describe('validateOrganizationSubscription', () => {
    it('should return true for valid organization subscription', () => {
      const subscription: OrganizationSubscription = {
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
      expect(validateOrganizationSubscription(subscription)).toBe(true);
    });

    it('should return false for invalid signed blob', () => {
      const subscription = {
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
      expect(validateOrganizationSubscription(subscription)).toBe(false);
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

describe('Subscription Status Functions', () => {
  describe('isSubscriptionActive', () => {
    it('should return true for ACTIVE status', () => {
      expect(isSubscriptionActive('ACTIVE')).toBe(true);
    });

    it('should return true for GRACE status', () => {
      expect(isSubscriptionActive('GRACE')).toBe(true);
    });

    it('should return false for other statuses', () => {
      expect(isSubscriptionActive('INACTIVE')).toBe(false);
      expect(isSubscriptionActive('EXPIRED')).toBe(false);
      expect(isSubscriptionActive('SUSPENDED')).toBe(false);
    });
  });

  describe('isSubscriptionExpired', () => {
    it('should return true for past date', () => {
      expect(isSubscriptionExpired('2020-01-01T00:00:00Z')).toBe(true);
      expect(isSubscriptionExpired(new Date('2020-01-01'))).toBe(true);
    });

    it('should return false for future date', () => {
      expect(isSubscriptionExpired('2099-01-01T00:00:00Z')).toBe(false);
      expect(isSubscriptionExpired(new Date('2099-01-01'))).toBe(false);
    });

    it('should return false for expiry just barely in the future', () => {
      const future = new Date(Date.now() + 10_000).toISOString();
      expect(isSubscriptionExpired(future)).toBe(false);
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

describe('Subscription Validation Function', () => {
  describe('validateSubscription', () => {
    it('should return valid for active subscription', () => {
      const data = createValidSubscriptionData();
      const result = validateSubscription(data);
      expect(result.valid).toBe(true);
      expect(result.data).toBeDefined();
    });

    it('should return invalid for suspended subscription', () => {
      const data = createValidSubscriptionData({ status: 'SUSPENDED' });
      const result = validateSubscription(data);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('suspended');
    });

    it('should return invalid for inactive subscription', () => {
      const data = createValidSubscriptionData({ status: 'INACTIVE' });
      const result = validateSubscription(data);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('not activated');
    });

    it('should return invalid for expired subscription', () => {
      const data = createValidSubscriptionData({
        expiresAt: '2020-01-01T00:00:00Z',
      });
      const result = validateSubscription(data);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('expired');
    });

    it('should indicate grace period when active', () => {
      const now = Date.now();
      const data = createValidSubscriptionData({
        lastCheckIn: new Date(now - 48 * 60 * 60 * 1000).toISOString(),
        gracePeriodEnds: new Date(now + 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateSubscription(data);
      expect(result.valid).toBe(true);
      expect(result.inGracePeriod).toBe(true);
    });

    it('should degrade to COMMUNITY when grace period expired', () => {
      const data = createValidSubscriptionData({
        planCode: 'ENTERPRISE',
        gracePeriodEnds: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateSubscription(data);
      expect(result.valid).toBe(true);
      expect(result.data?.planCode).toBe('COMMUNITY');
      expect(result.inGracePeriod).toBe(true);
    });

    it('should return valid when now equals expiresAt exactly', () => {
      const expiresAt = '2027-06-15T12:00:00.000Z';
      const now = new Date(expiresAt);
      const data = createValidSubscriptionData({ expiresAt });
      const result = validateSubscription(data, now);
      expect(result.valid).toBe(true);
    });

    it('should return invalid when now is 1ms after expiresAt', () => {
      const expiresAt = '2027-06-15T12:00:00.000Z';
      const now = new Date(new Date(expiresAt).getTime() + 1);
      const data = createValidSubscriptionData({ expiresAt });
      const result = validateSubscription(data, now);
      expect(result.valid).toBe(false);
      expect(result.error).toContain('expired');
    });

    it('should detect grace period when check-in is just past 24h interval', () => {
      const now = Date.now();
      const data = createValidSubscriptionData({
        lastCheckIn: new Date(now - 24 * 60 * 60 * 1000 - 60 * 1000).toISOString(), // 24h + 1min ago
        gracePeriodEnds: new Date(now + 2 * 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateSubscription(data);
      expect(result.valid).toBe(true);
      expect(result.inGracePeriod).toBe(true);
    });

    it('should NOT detect grace period when check-in is just under 24h interval', () => {
      const now = Date.now();
      const data = createValidSubscriptionData({
        lastCheckIn: new Date(now - 23 * 60 * 60 * 1000 - 59 * 60 * 1000).toISOString(), // 23h59m ago
        gracePeriodEnds: new Date(now + 2 * 24 * 60 * 60 * 1000).toISOString(),
      });
      const result = validateSubscription(data);
      expect(result.valid).toBe(true);
      expect(result.inGracePeriod).toBe(false);
    });
  });
});

describe('Subscription Payload Encoding/Decoding', () => {
  describe('encodeSubscriptionPayload', () => {
    it('should encode subscription data to base64', () => {
      const data = createValidSubscriptionData();
      const encoded = encodeSubscriptionPayload(data);
      expect(typeof encoded).toBe('string');
      expect(encoded.length).toBeGreaterThan(0);
    });
  });

  describe('decodeSubscriptionPayload', () => {
    it('should decode valid base64 payload', () => {
      const data = createValidSubscriptionData();
      const encoded = encodeSubscriptionPayload(data);
      const decoded = decodeSubscriptionPayload(encoded);
      expect(decoded).not.toBeNull();
      expect(decoded?.subscriptionId).toBe(data.subscriptionId);
    });

    it('should return null for invalid base64', () => {
      expect(decodeSubscriptionPayload('not-valid-base64!!!')).toBeNull();
    });

    it('should return null for valid base64 with invalid JSON', () => {
      const invalidJson = btoa('not json');
      expect(decodeSubscriptionPayload(invalidJson)).toBeNull();
    });

    it('should return null for valid JSON but invalid subscription data', () => {
      const invalidData = btoa(JSON.stringify({ foo: 'bar' }));
      expect(decodeSubscriptionPayload(invalidData)).toBeNull();
    });
  });
});
