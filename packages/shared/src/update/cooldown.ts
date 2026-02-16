import { UPDATE_STATE_DEFAULTS } from './constants';
import type { UpdateStateBase } from './types';

/**
 * Check if cooldown has expired. Base cooldown is 1 hour, with exponential
 * backoff on failures: min(1 * 2^failures, 24) hours.
 * Configurable via RDC_UPDATE_INTERVAL_HOURS.
 */
export function isCooldownExpired(state: UpdateStateBase): boolean {
  if (!state.lastAttemptAt) return true;

  const envHours = process.env.RDC_UPDATE_INTERVAL_HOURS;
  const baseHours = envHours ? Number(envHours) : UPDATE_STATE_DEFAULTS.DEFAULT_COOLDOWN_HOURS;
  const cooldownHours = Math.min(
    baseHours * 2 ** state.consecutiveFailures,
    UPDATE_STATE_DEFAULTS.MAX_COOLDOWN_HOURS
  );
  const cooldownMs = cooldownHours * 60 * 60 * 1000;

  const elapsed = Date.now() - new Date(state.lastAttemptAt).getTime();
  return elapsed >= cooldownMs;
}
