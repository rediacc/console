/**
 * License Validation
 *
 * Functions for validating license data structure and status.
 */

import { LICENSE_CONFIG, PLAN_ORDER } from './constants';
import type {
  LicenseData,
  LicenseStatus,
  LicenseValidationResult,
  OrganizationLicense,
  PlanCode,
  ResourceLimits,
  SignedLicenseBlob,
} from './types';

/**
 * Validate that a license data object has all required fields.
 */
export function validateLicenseData(data: unknown): data is LicenseData {
  if (!data || typeof data !== 'object') {
    return false;
  }

  const license = data as Partial<LicenseData>;

  // Check required string fields
  const requiredStrings: (keyof LicenseData)[] = [
    'licenseId',
    'customerId',
    'planCode',
    'status',
    'issuedAt',
    'expiresAt',
    'lastCheckIn',
    'gracePeriodEnds',
  ];

  for (const field of requiredStrings) {
    if (typeof license[field] !== 'string') {
      return false;
    }
  }

  // Check required number fields
  if (
    typeof license.version !== 'number' ||
    typeof license.organizationId !== 'number' ||
    typeof license.maxActivations !== 'number' ||
    typeof license.activationCount !== 'number'
  ) {
    return false;
  }

  // Check plan code is valid
  if (!PLAN_ORDER.includes(license.planCode as PlanCode)) {
    return false;
  }

  // Check resources object
  if (!license.resources || typeof license.resources !== 'object') {
    return false;
  }

  // Check features object
  if (!license.features || typeof license.features !== 'object') {
    return false;
  }

  return true;
}

/**
 * Validate a signed license blob structure.
 */
export function validateSignedBlob(blob: unknown): blob is SignedLicenseBlob {
  if (!blob || typeof blob !== 'object') {
    return false;
  }

  const signed = blob as Partial<SignedLicenseBlob>;

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
 * Validate an organization license structure.
 */
export function validateOrganizationLicense(license: unknown): license is OrganizationLicense {
  if (!license || typeof license !== 'object') {
    return false;
  }

  const orgLicense = license as Partial<OrganizationLicense>;

  if (!validateSignedBlob(orgLicense.signedBlob)) {
    return false;
  }

  if (!orgLicense.cachedData || typeof orgLicense.cachedData !== 'object') {
    return false;
  }

  // Cast to Record for runtime validation of unknown input
  const cached = orgLicense.cachedData as Record<string, unknown>;
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
 * Check if a license is currently active.
 */
export function isLicenseActive(status: LicenseStatus): boolean {
  return status === 'ACTIVE' || status === 'GRACE';
}

/**
 * Check if a license has expired based on dates.
 */
export function isLicenseExpired(expiresAt: string | Date): boolean {
  const expiry = typeof expiresAt === 'string' ? new Date(expiresAt) : expiresAt;
  return expiry < new Date();
}

/**
 * Check if a license is in grace period.
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
  const checkInIntervalMs = LICENSE_CONFIG.checkInIntervalHours * 60 * 60 * 1000;

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
  grace.setDate(grace.getDate() + LICENSE_CONFIG.gracePeriodDays);
  return grace;
}

/**
 * Get the effective plan code considering grace period.
 * Returns degraded plan (COMMUNITY) if grace period has expired.
 */
export function getEffectivePlanCode(planCode: PlanCode, gracePeriodEnds: string | Date): PlanCode {
  if (isGracePeriodExpired(gracePeriodEnds)) {
    return LICENSE_CONFIG.degradedPlan;
  }
  return planCode;
}

/**
 * Validate license data and return detailed result.
 */
export function validateLicense(
  data: LicenseData,
  now: Date = new Date()
): LicenseValidationResult {
  // Check status
  if (data.status === 'SUSPENDED') {
    return { valid: false, error: 'License is suspended' };
  }

  if (data.status === 'INACTIVE') {
    return { valid: false, error: 'License is not activated' };
  }

  // Check expiration
  const expiresAt = new Date(data.expiresAt);
  if (now > expiresAt) {
    return { valid: false, error: 'License has expired' };
  }

  // Check grace period
  const gracePeriodEnds = new Date(data.gracePeriodEnds);
  const inGrace = isInGracePeriod(data.lastCheckIn, data.gracePeriodEnds);

  if (isGracePeriodExpired(gracePeriodEnds)) {
    return {
      valid: true,
      data: {
        ...data,
        planCode: LICENSE_CONFIG.degradedPlan,
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
 * Decode base64 payload to LicenseData.
 */
export function decodeLicensePayload(payload: string): LicenseData | null {
  try {
    const json = atob(payload);
    const data = JSON.parse(json);
    if (validateLicenseData(data)) {
      return data;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Encode LicenseData to base64 payload.
 */
export function encodeLicensePayload(data: LicenseData): string {
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
    'maxActiveJobs',
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
