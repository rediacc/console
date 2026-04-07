import { describe, expect, it } from 'vitest';
import {
  computeDelegationCertValidity,
  computeRenewalThresholdDays,
  PLAN_DELEGATION_CERT_DEFAULT_DAYS,
  PLAN_DELEGATION_CERT_MAX_DAYS,
  SubscriptionExpiredForDelegationError,
} from '../index';

const NOW = new Date('2026-04-07T00:00:00.000Z');
const daysFromNow = (days: number): string =>
  new Date(NOW.getTime() + days * 86_400_000).toISOString();

describe('computeDelegationCertValidity', () => {
  describe('plan defaults (no override, no expiry)', () => {
    it.each([
      'COMMUNITY',
      'PROFESSIONAL',
      'BUSINESS',
      'ENTERPRISE',
    ] as const)('returns the per-plan default for %s', (planCode) => {
      const result = computeDelegationCertValidity({
        planCode,
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: null,
        requestedDays: undefined,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(PLAN_DELEGATION_CERT_DEFAULT_DAYS[planCode]);
      expect(result.reason).toBe('plan_default');
    });
  });

  describe('subscription override (no plan ceiling applies)', () => {
    it('uses the override as both default and ceiling', () => {
      const result = computeDelegationCertValidity({
        planCode: 'COMMUNITY',
        subscriptionOverrideDays: 200,
        subscriptionExpiresAt: null,
        requestedDays: undefined,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(200);
      expect(result.reason).toBe('subscription_override');
    });

    it('clamps a request that exceeds the override to the override (override_max_clamp)', () => {
      const result = computeDelegationCertValidity({
        planCode: 'COMMUNITY',
        subscriptionOverrideDays: 50,
        subscriptionExpiresAt: null,
        requestedDays: 200,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(50);
      expect(result.reason).toBe('override_max_clamp');
    });

    it('honors a request below the override (requested)', () => {
      const result = computeDelegationCertValidity({
        planCode: 'COMMUNITY',
        subscriptionOverrideDays: 200,
        subscriptionExpiresAt: null,
        requestedDays: 30,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(30);
      expect(result.reason).toBe('requested');
    });
  });

  describe('caller request honored vs clamped', () => {
    it('honors a request within plan max', () => {
      const result = computeDelegationCertValidity({
        planCode: 'PROFESSIONAL',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: null,
        requestedDays: 90,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(90);
      expect(result.reason).toBe('requested');
    });

    it('clamps a request above plan max (plan_max_clamp)', () => {
      const result = computeDelegationCertValidity({
        planCode: 'COMMUNITY',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: null,
        requestedDays: 365,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(PLAN_DELEGATION_CERT_MAX_DAYS.COMMUNITY); // 30
      expect(result.reason).toBe('plan_max_clamp');
    });
  });

  describe('subscription expiry cap', () => {
    it('clamps a 90-day request when subscription expires in 5 days', () => {
      const result = computeDelegationCertValidity({
        planCode: 'BUSINESS',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: daysFromNow(5),
        requestedDays: 90,
        now: NOW,
      });
      // Cap = 5 + 3 grace = 8 days from now
      expect(result.effectiveDays).toBe(8);
      expect(result.reason).toBe('subscription_cap_clamp');
    });

    it('clamps the plan default when expiry is closer than the default', () => {
      const result = computeDelegationCertValidity({
        planCode: 'BUSINESS', // default 90
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: daysFromNow(10),
        requestedDays: undefined,
        now: NOW,
      });
      // Cap = 10 + 3 grace = 13
      expect(result.effectiveDays).toBe(13);
      expect(result.reason).toBe('subscription_cap_clamp');
    });

    it('does not cap when subscription expiry is far in the future', () => {
      const result = computeDelegationCertValidity({
        planCode: 'PROFESSIONAL',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: daysFromNow(180),
        requestedDays: undefined,
        now: NOW,
      });
      expect(result.effectiveDays).toBe(PLAN_DELEGATION_CERT_DEFAULT_DAYS.PROFESSIONAL); // 60
      expect(result.reason).toBe('plan_default');
    });

    it('floors at 1 day when subscription has already expired (within grace)', () => {
      const result = computeDelegationCertValidity({
        planCode: 'PROFESSIONAL',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: daysFromNow(-1), // expired 1 day ago, within 3-day grace
        requestedDays: undefined,
        now: NOW,
      });
      // Cap = -1 + 3 = +2 days
      expect(result.effectiveDays).toBe(2);
      expect(result.reason).toBe('subscription_cap_clamp');
    });

    it('throws SubscriptionExpiredForDelegationError when grace has also expired', () => {
      // Subscription expired 30 days ago, grace period is 3 days, so the cap
      // is 27 days in the past. Issuing a fresh 1-day cert here would let an
      // expired subscription mint a cert that outlives the documented hard
      // cap. The policy must reject outright.
      expect(() =>
        computeDelegationCertValidity({
          planCode: 'PROFESSIONAL',
          subscriptionOverrideDays: null,
          subscriptionExpiresAt: daysFromNow(-30),
          requestedDays: undefined,
          now: NOW,
        })
      ).toThrow(SubscriptionExpiredForDelegationError);
    });

    it('throws when expiresAt + grace == now (boundary)', () => {
      expect(() =>
        computeDelegationCertValidity({
          planCode: 'PROFESSIONAL',
          subscriptionOverrideDays: null,
          subscriptionExpiresAt: daysFromNow(-3), // exactly grace-period away
          requestedDays: undefined,
          now: NOW,
        })
      ).toThrow(SubscriptionExpiredForDelegationError);
    });
  });

  describe('monthly subscription example', () => {
    it('caps a 365-day request to ~31 days when expires next month', () => {
      const result = computeDelegationCertValidity({
        planCode: 'PROFESSIONAL',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: daysFromNow(28), // monthly billing
        requestedDays: 365,
        now: NOW,
      });
      // Cap = 28 + 3 = 31. Plan max = 120, so subscription cap wins.
      expect(result.effectiveDays).toBe(31);
      expect(result.reason).toBe('subscription_cap_clamp');
    });
  });

  describe('validUntil computation', () => {
    it('returns an ISO string offset by effectiveDays from now', () => {
      const result = computeDelegationCertValidity({
        planCode: 'BUSINESS',
        subscriptionOverrideDays: null,
        subscriptionExpiresAt: null,
        requestedDays: undefined,
        now: NOW,
      });
      const expected = new Date(NOW.getTime() + 90 * 86_400_000).toISOString();
      expect(result.validUntil).toBe(expected);
    });
  });
});

describe('computeRenewalThresholdDays', () => {
  it('returns the env ceiling when 1/3 of validity exceeds it', () => {
    expect(computeRenewalThresholdDays(90, 14)).toBe(14);
    expect(computeRenewalThresholdDays(120, 14)).toBe(14);
    expect(computeRenewalThresholdDays(60, 14)).toBe(14);
  });

  it('returns ceil(validity / 3) when smaller than the env ceiling', () => {
    expect(computeRenewalThresholdDays(15, 14)).toBe(5);
    expect(computeRenewalThresholdDays(30, 14)).toBe(10);
    expect(computeRenewalThresholdDays(7, 14)).toBe(3);
  });

  it('floors at 1 for tiny validity', () => {
    expect(computeRenewalThresholdDays(0, 14)).toBe(1);
    expect(computeRenewalThresholdDays(-5, 14)).toBe(1);
    expect(computeRenewalThresholdDays(1, 14)).toBe(1);
  });
});
