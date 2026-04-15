/**
 * Tests for the `isTelemetryDisabled()` env-var check.
 *
 * This pure function is the single source of truth for CLI telemetry
 * opt-out. It's consulted from:
 *   - `cli.ts` preAction hook (gates the OTLP credential fetch)
 *   - `local-executor.ts:runRemoteExecution` (gates the fetch)
 *   - `local-executor.ts:buildRemoteCommand` (injects the disable flag
 *     into the remote renet env)
 *   - `telemetry.ts:shouldDisable` (gates the OTel SDK construction)
 *
 * Any regression here breaks telemetry opt-out in all four places, so
 * the behavior is worth locking down explicitly.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { isTelemetryDisabled } from '../telemetry.js';

describe('isTelemetryDisabled', () => {
  const savedCI = process.env.CI;
  const savedFlag = process.env.REDIACC_TELEMETRY_DISABLED;

  beforeEach(() => {
    delete process.env.CI;
    delete process.env.REDIACC_TELEMETRY_DISABLED;
  });

  afterEach(() => {
    if (savedCI === undefined) delete process.env.CI;
    else process.env.CI = savedCI;
    if (savedFlag === undefined) delete process.env.REDIACC_TELEMETRY_DISABLED;
    else process.env.REDIACC_TELEMETRY_DISABLED = savedFlag;
  });

  it('returns false when no env vars are set', () => {
    expect(isTelemetryDisabled()).toBe(false);
  });

  it('returns true when REDIACC_TELEMETRY_DISABLED=1', () => {
    process.env.REDIACC_TELEMETRY_DISABLED = '1';
    expect(isTelemetryDisabled()).toBe(true);
  });

  it('returns false when REDIACC_TELEMETRY_DISABLED=0 (not "1")', () => {
    process.env.REDIACC_TELEMETRY_DISABLED = '0';
    expect(isTelemetryDisabled()).toBe(false);
  });

  it('returns false when REDIACC_TELEMETRY_DISABLED=true (not "1")', () => {
    // Only exactly "1" disables — anything else is a no-op. This is
    // consistent with how the existing shouldDisable() check reads the
    // variable and matches the documented opt-out UX.
    process.env.REDIACC_TELEMETRY_DISABLED = 'true';
    expect(isTelemetryDisabled()).toBe(false);
  });

  it('returns true when CI=true', () => {
    process.env.CI = 'true';
    expect(isTelemetryDisabled()).toBe(true);
  });

  it('returns true when CI=1', () => {
    process.env.CI = '1';
    expect(isTelemetryDisabled()).toBe(true);
  });

  it('returns true when CI is set to any non-empty string', () => {
    process.env.CI = 'github-actions';
    expect(isTelemetryDisabled()).toBe(true);
  });

  it('returns false when CI is explicitly empty', () => {
    process.env.CI = '';
    expect(isTelemetryDisabled()).toBe(false);
  });

  it('returns true when both CI and REDIACC_TELEMETRY_DISABLED are set', () => {
    process.env.CI = 'true';
    process.env.REDIACC_TELEMETRY_DISABLED = '1';
    expect(isTelemetryDisabled()).toBe(true);
  });
});
