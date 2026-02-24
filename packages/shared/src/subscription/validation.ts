/**
 * Subscription Validation
 *
 * Functions for validating subscription data structure and status.
 */

import { SUBSCRIPTION_CONFIG, PLAN_ORDER } from './constants';
import type {
  SubscriptionData,
  SubscriptionStatus,
  SubscriptionValidationResult,
  OrganizationSubscription,
  PlanCode,
  ResourceLimits,
  SignedSubscriptionBlob,
} from './types';

/**
 * Validate that a subscription data object has all required fields.
 */
export function validateSubscriptionData(data: unknown): data is SubscriptionData {
  if (!data || typeof data !== 'object') {
    return false;
  }

  const subscription = data as Partial<SubscriptionData>;

  // Check required string fields
  const requiredStrings: (keyof SubscriptionData)[] = [
    'subscriptionId',
    'customerId',
    'planCode',
    'status',
    'issuedAt',
    'expiresAt',
    'lastCheckIn',
    'gracePeriodEnds',
  ];

  for (const field of requiredStrings) {
    if (typeof subscription[field] !== 'string') {
      return false;
    }
  }

  // Check required number fields
  if (
    typeof subscription.version !== 'number' ||
    typeof subscription.organizationId !== 'number' ||
    typeof subscription.maxActivations !== 'number' ||
    typeof subscription.activationCount !== 'number'
  ) {
    return false;
  }

  // Check plan code is valid
  if (!PLAN_ORDER.includes(subscription.planCode as PlanCode)) {
    return false;
  }

  // Check resources object
  if (!subscription.resources || typeof subscription.resources !== 'object') {
    return false;
  }

  // Check features object
  if (!subscription.features || typeof subscription.features !== 'object') {
    return false;
  }

  return true;
}

/**
 * Validate a signed subscription blob structure.
 */
export function validateSignedBlob(blob: unknown): blob is SignedSubscriptionBlob {
  if (!blob || typeof blob !== 'object') {
    return false;
  }

  const signed = blob as Partial<SignedSubscriptionBlob>;

  return (
    typeof signed.payload === 'string' &&
    typeof signed.signature === 'string' &&
    typeof signed.publicKeyId === 'string' &&
    signed.payload.length > 0 &&
    signed.signature.length > 0 &&
    signed.publicKeyId.length > 0
  );
}

/**
 * Validate an organization subscription structure.
 */
export function validateOrganizationSubscription(
  subscription: unknown
): subscription is OrganizationSubscription {
  if (!subscription || typeof subscription !== 'object') {
    return false;
  }

  const orgSubscription = subscription as Partial<OrganizationSubscription>;

  if (!validateSignedBlob(orgSubscription.signedBlob)) {
    return false;
  }

  if (!orgSubscription.cachedData || typeof orgSubscription.cachedData !== 'object') {
    return false;
  }

  // Cast to Record for runtime validation of unknown input
  const cached = orgSubscription.cachedData as Record<string, unknown>;
  return (
    typeof cached.planCode === 'string' &&
    typeof cached.status === 'string' &&
    typeof cached.expiresAt === 'string' &&
    typeof cached.gracePeriodEnds === 'string' &&
    cached.resources !== null &&
    typeof cached.resources === 'object' &&
    cached.features !== null &&
    typeof cached.features === 'object'
  );
}

/**
 * Check if a subscription is currently active.
 */
export function isSubscriptionActive(status: SubscriptionStatus): boolean {
  return status === 'ACTIVE' || status === 'GRACE';
}

/**
 * Check if a subscription has expired based on dates.
 */
export function isSubscriptionExpired(expiresAt: string | Date): boolean {
  const expiry = typeof expiresAt === 'string' ? new Date(expiresAt) : expiresAt;
  return expiry < new Date();
}

/**
 * Check if a subscription is in grace period.
 */
export function isInGracePeriod(
  lastCheckIn: string | Date,
  gracePeriodEnds: string | Date
): boolean {
  const now = new Date();
  const grace = typeof gracePeriodEnds === 'string' ? new Date(gracePeriodEnds) : gracePeriodEnds;
  const checkIn = typeof lastCheckIn === 'string' ? new Date(lastCheckIn) : lastCheckIn;

  // Grace period is active if:
  // 1. Current time is past the check-in interval
  // 2. Current time is before grace period ends
  const checkInAge = now.getTime() - checkIn.getTime();
  const checkInIntervalMs = SUBSCRIPTION_CONFIG.checkInIntervalHours * 60 * 60 * 1000;

  return checkInAge > checkInIntervalMs && now < grace;
}

/**
 * Check if grace period has expired (should degrade to COMMUNITY).
 */
export function isGracePeriodExpired(gracePeriodEnds: string | Date): boolean {
  const grace = typeof gracePeriodEnds === 'string' ? new Date(gracePeriodEnds) : gracePeriodEnds;
  return new Date() >= grace;
}

/**
 * Calculate grace period end date from last check-in.
 */
export function calculateGracePeriodEnd(lastCheckIn: string | Date): Date {
  const checkIn = typeof lastCheckIn === 'string' ? new Date(lastCheckIn) : lastCheckIn;
  const grace = new Date(checkIn);
  grace.setDate(grace.getDate() + SUBSCRIPTION_CONFIG.gracePeriodDays);
  return grace;
}

/**
 * Get the effective plan code considering grace period.
 * Returns degraded plan (COMMUNITY) if grace period has expired.
 */
export function getEffectivePlanCode(planCode: PlanCode, gracePeriodEnds: string | Date): PlanCode {
  if (isGracePeriodExpired(gracePeriodEnds)) {
    return SUBSCRIPTION_CONFIG.degradedPlan;
  }
  return planCode;
}

/**
 * Validate subscription data and return detailed result.
 */
export function validateSubscription(
  data: SubscriptionData,
  now: Date = new Date()
): SubscriptionValidationResult {
  // Check status
  if (data.status === 'SUSPENDED') {
    return { valid: false, error: 'Subscription is suspended' };
  }

  if (data.status === 'INACTIVE') {
    return { valid: false, error: 'Subscription is not activated' };
  }

  // Check expiration
  const expiresAt = new Date(data.expiresAt);
  if (now > expiresAt) {
    return { valid: false, error: 'Subscription has expired' };
  }

  // Check grace period
  const gracePeriodEnds = new Date(data.gracePeriodEnds);
  const inGrace = isInGracePeriod(data.lastCheckIn, data.gracePeriodEnds);

  if (isGracePeriodExpired(gracePeriodEnds)) {
    return {
      valid: true,
      data: {
        ...data,
        planCode: SUBSCRIPTION_CONFIG.degradedPlan,
        status: 'GRACE',
      },
      inGracePeriod: true,
      error: 'Grace period expired, degraded to COMMUNITY',
    };
  }

  return {
    valid: true,
    data,
    inGracePeriod: inGrace,
  };
}

/**
 * Decode base64 payload to SubscriptionData.
 */
export function decodeSubscriptionPayload(payload: string): SubscriptionData | null {
  try {
    const json = atob(payload);
    const data = JSON.parse(json);
    if (validateSubscriptionData(data)) {
      return data;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Encode SubscriptionData to base64 payload.
 */
export function encodeSubscriptionPayload(data: SubscriptionData): string {
  return btoa(JSON.stringify(data));
}

/**
 * Validate resource limits object has all required fields.
 */
export function validateResourceLimits(limits: unknown): limits is ResourceLimits {
  if (!limits || typeof limits !== 'object') {
    return false;
  }

  const l = limits as Partial<ResourceLimits>;
  const requiredKeys: (keyof ResourceLimits)[] = [
    'bridges',
    'maxReservedJobs',
    'jobTimeoutHours',
    'maxRepositorySizeGb',
    'maxJobsPerMonth',
    'maxPendingPerUser',
    'maxTasksPerMachine',
    'cephPoolsPerTeam',
  ];

  for (const key of requiredKeys) {
    if (typeof l[key] !== 'number') {
      return false;
    }
  }

  return true;
}
