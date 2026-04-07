/**
 * Delegation Certificate Validity Policy
 *
 * Single source of truth for computing how long a newly issued (or renewed)
 * delegation certificate should be valid. Used by both the backend service
 * (admin + customer endpoints) and the frontend "live preview" in create
 * modals so the customer sees the effective validity before submitting.
 *
 * Inputs:
 *   - planCode                       — drives default + ceiling
 *   - subscriptionOverrideDays       — admin-set override that replaces both
 *                                      the default and the ceiling for that
 *                                      subscription (escape hatch)
 *   - subscriptionExpiresAt          — hard cap so a cert can never outlive
 *                                      the subscription by more than the
 *                                      configured grace period (3 days)
 *   - requestedDays                  — caller-supplied target. undefined ->
 *                                      use the effective default
 *
 * Output: { effectiveDays, validUntil, reason } where `reason` discriminates
 * the clamp path so the UI can explain "you asked for 90 but got 18 because
 * the subscription expires in 15 days".
 */

import {
  PLAN_DELEGATION_CERT_DEFAULT_DAYS,
  PLAN_DELEGATION_CERT_MAX_DAYS,
  SUBSCRIPTION_CONFIG,
} from './constants.js';
import type { PlanCode } from './types.js';

export interface ComputeValidityInput {
  planCode: PlanCode;
  /** Per-subscription override (column delegation_cert_default_days). null = use plan defaults. */
  subscriptionOverrideDays: number | null;
  /** Subscription expiresAt as ISO string. null = perpetual / no fixed end. */
  subscriptionExpiresAt: string | null;
  /** Caller-supplied request. undefined = use the effective default. */
  requestedDays: number | undefined;
  /** Test seam for "now". */
  now?: Date;
}

export type ValidityClampReason =
  /** No request, no override → plan default applied. */
  | 'plan_default'
  /** No request, override set → override applied as the default. */
  | 'subscription_override'
  /** Caller request honored as-is (within all caps). */
  | 'requested'
  /** Caller request exceeded the plan ceiling (no override) — clamped down. */
  | 'plan_max_clamp'
  /** Caller request exceeded an explicit per-sub override — clamped down. */
  | 'override_max_clamp'
  /** Otherwise-valid target would outlive subscriptionExpiresAt + grace. */
  | 'subscription_cap_clamp';

export interface ComputedValidity {
  effectiveDays: number;
  /** ISO string. */
  validUntil: string;
  reason: ValidityClampReason;
}

/**
 * Thrown by `computeDelegationCertValidity` when the subscription's
 * expiresAt + grace window is already in the past. Issuing a cert in this
 * state would silently mint a 1-day cert that outlives the documented
 * hard cap and bypasses the expiry contract. Callers must handle this
 * (the account service catches it and returns 403 SUBSCRIPTION_EXPIRED).
 */
export class SubscriptionExpiredForDelegationError extends Error {
  readonly code = 'SUBSCRIPTION_EXPIRED_FOR_DELEGATION';
  constructor(
    public readonly subscriptionExpiresAt: string,
    public readonly capExpiresAt: string
  ) {
    super(
      `Subscription expired beyond grace period. ` +
        `Subscription expiresAt=${subscriptionExpiresAt}, ` +
        `cap (expiresAt + ${SUBSCRIPTION_CONFIG.gracePeriodDays}d grace)=${capExpiresAt}. ` +
        `Cannot issue or renew a delegation cert.`
    );
  }
}

/**
 * Clamp a target validity (in days) to the subscription's expiry + grace
 * window. Returns the original target unchanged when no expiry is set or
 * when the target already fits inside the cap.
 *
 * Throws `SubscriptionExpiredForDelegationError` when the cap is already
 * in the past - silently clamping to 1 day in that case would let an
 * expired subscription mint a fresh cert and undermine the hard cap.
 */
function clampToSubscriptionExpiry(
  now: Date,
  target: number,
  subscriptionExpiresAt: string | null
): { target: number; clamped: boolean } {
  if (!subscriptionExpiresAt) return { target, clamped: false };
  const expiryMs = new Date(subscriptionExpiresAt).getTime();
  if (!Number.isFinite(expiryMs)) return { target, clamped: false };
  const capMs = expiryMs + SUBSCRIPTION_CONFIG.gracePeriodDays * 86_400_000;
  if (capMs <= now.getTime()) {
    throw new SubscriptionExpiredForDelegationError(
      subscriptionExpiresAt,
      new Date(capMs).toISOString()
    );
  }
  const targetEndMs = now.getTime() + target * 86_400_000;
  if (targetEndMs <= capMs) return { target, clamped: false };
  const clampedDays = Math.floor((capMs - now.getTime()) / 86_400_000);
  return { target: Math.max(1, clampedDays), clamped: true };
}

/**
 * Compute the effective validity for a delegation cert.
 * Pure function - safe to call from frontend and backend.
 */
export function computeDelegationCertValidity(input: ComputeValidityInput): ComputedValidity {
  const now = input.now ?? new Date();
  const planDefault = PLAN_DELEGATION_CERT_DEFAULT_DAYS[input.planCode];
  const planMax = PLAN_DELEGATION_CERT_MAX_DAYS[input.planCode];

  // An explicit override on the subscription replaces BOTH the default and
  // the ceiling for that subscription. This is the admin escape hatch.
  const hasOverride = input.subscriptionOverrideDays !== null;
  const effectiveDefault = input.subscriptionOverrideDays ?? planDefault;
  const effectiveMax = input.subscriptionOverrideDays ?? planMax;

  // Pick the target and initial reason.
  let target = input.requestedDays ?? effectiveDefault;
  let reason: ValidityClampReason;
  if (input.requestedDays !== undefined) {
    reason = 'requested';
  } else if (hasOverride) {
    reason = 'subscription_override';
  } else {
    reason = 'plan_default';
  }

  // Clamp to effective max.
  if (target > effectiveMax) {
    target = effectiveMax;
    reason = hasOverride ? 'override_max_clamp' : 'plan_max_clamp';
  }

  // Clamp to (subscriptionExpiresAt + gracePeriodDays).
  const expiryClamp = clampToSubscriptionExpiry(now, target, input.subscriptionExpiresAt);
  if (expiryClamp.clamped) {
    target = expiryClamp.target;
    reason = 'subscription_cap_clamp';
  }

  // Final floor.
  if (target < 1) target = 1;

  return {
    effectiveDays: target,
    validUntil: new Date(now.getTime() + target * 86_400_000).toISOString(),
    reason,
  };
}

/**
 * Compute the renewal threshold (days before expiry to start renewing).
 *
 * Industry best practice (Let's Encrypt: 90-day certs renewed at 60 days
 * remaining = 1/3 of validity). Adapted here so short-lived COMMUNITY certs
 * (15 days) renew at ~5 days remaining instead of immediately tripping a
 * fixed 14-day threshold.
 *
 * The `envCeiling` is the absolute max from the operator's config — never
 * try to renew sooner than this many days before expiry, even if 1/3 of
 * validity would suggest doing so.
 */
export function computeRenewalThresholdDays(validityDays: number, envCeiling: number): number {
  if (validityDays < 1) return 1;
  return Math.min(envCeiling, Math.ceil(validityDays / 3));
}
