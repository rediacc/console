/**
 * Tests for `buildRemoteRenetCommand` — the function that builds the SSH
 * command string for spawning `renet execute` on a target machine.
 *
 * The goal is to verify every combination of inputs produces the exact
 * expected command string. Any regression that changes env var ordering,
 * quoting, or leaks OTLP credentials when telemetry is disabled will
 * fail this test.
 *
 * Covers the two bug classes from renet#51 follow-up:
 *   1. Credential-leak-despite-disable: when the user sets
 *      `REDIACC_TELEMETRY_DISABLED=1`, we must NOT inject
 *      `REDIACC_OTLP_USER`/`REDIACC_OTLP_PASS` into the remote env, even
 *      if the caller provides credentials.
 *   2. Disable-not-propagated: when telemetry is disabled, we must
 *      inject `REDIACC_TELEMETRY_DISABLED=1` so the remote renet also
 *      takes its default-deny branch.
 */

import { describe, expect, it } from 'vitest';
import { buildRemoteRenetCommand } from '../local-executor.js';

const RENET = '/usr/bin/renet';
const CREDS = { user: 'otlp-eu-abc123', pass: 'base64url-pass_-_' };

describe('buildRemoteRenetCommand', () => {
  describe('telemetry enabled', () => {
    it('with creds: injects REDIACC_OTLP_USER/PASS', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: CREDS,
      });
      expect(cmd).toBe(
        `sudo env REDIACC_OTLP_USER='otlp-eu-abc123' REDIACC_OTLP_PASS='base64url-pass_-_' /usr/bin/renet execute --executor local`
      );
    });

    it('without creds: no OTLP env vars, no REDIACC_TELEMETRY_DISABLED', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: null,
      });
      expect(cmd).toBe(`sudo /usr/bin/renet execute --executor local`);
      expect(cmd).not.toContain('REDIACC_OTLP');
      expect(cmd).not.toContain('REDIACC_TELEMETRY_DISABLED');
    });

    it('with creds + dev mode: both REDIACC_ENVIRONMENT and OTLP vars', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: true,
        telemetryDisabled: false,
        otlpCreds: CREDS,
      });
      expect(cmd).toBe(
        `sudo env REDIACC_ENVIRONMENT=development REDIACC_OTLP_USER='otlp-eu-abc123' REDIACC_OTLP_PASS='base64url-pass_-_' /usr/bin/renet execute --executor local`
      );
    });
  });

  describe('telemetry disabled', () => {
    it('with creds: injects REDIACC_TELEMETRY_DISABLED=1 and IGNORES creds', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: true,
        otlpCreds: CREDS,
      });
      expect(cmd).toBe(
        `sudo env REDIACC_TELEMETRY_DISABLED=1 /usr/bin/renet execute --executor local`
      );
      // Critical: no OTLP credentials leak into the remote env
      expect(cmd).not.toContain('REDIACC_OTLP_USER');
      expect(cmd).not.toContain('REDIACC_OTLP_PASS');
      expect(cmd).not.toContain('otlp-eu-abc123');
      expect(cmd).not.toContain('base64url-pass');
    });

    it('without creds: injects REDIACC_TELEMETRY_DISABLED=1', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: true,
        otlpCreds: null,
      });
      expect(cmd).toBe(
        `sudo env REDIACC_TELEMETRY_DISABLED=1 /usr/bin/renet execute --executor local`
      );
    });

    it('dev mode: REDIACC_ENVIRONMENT stays, telemetry disabled still wins', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: true,
        telemetryDisabled: true,
        otlpCreds: CREDS,
      });
      expect(cmd).toBe(
        `sudo env REDIACC_ENVIRONMENT=development REDIACC_TELEMETRY_DISABLED=1 /usr/bin/renet execute --executor local`
      );
      expect(cmd).not.toContain('REDIACC_OTLP');
    });
  });

  describe('events mode', () => {
    it('appends --events flag after executor local', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        eventsMode: true,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: null,
      });
      expect(cmd).toBe(`sudo /usr/bin/renet execute --executor local --events`);
    });

    it('combines with other flags correctly', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        eventsMode: true,
        isDevelopment: true,
        telemetryDisabled: true,
        otlpCreds: CREDS,
      });
      expect(cmd).toBe(
        `sudo env REDIACC_ENVIRONMENT=development REDIACC_TELEMETRY_DISABLED=1 /usr/bin/renet execute --executor local --events`
      );
    });
  });

  describe('shell escaping', () => {
    it('escapes single quotes in user/pass', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: { user: "has'quote", pass: "also'quote" },
      });
      // POSIX-safe: `'has'\''quote'`
      expect(cmd).toContain(`REDIACC_OTLP_USER='has'\\''quote'`);
      expect(cmd).toContain(`REDIACC_OTLP_PASS='also'\\''quote'`);
    });

    it('handles passwords with shell metacharacters', () => {
      const cmd = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: { user: 'u', pass: 'p$ss&word;rm -rf' },
      });
      // The single quotes protect all shell metacharacters except '
      expect(cmd).toContain(`REDIACC_OTLP_PASS='p$ss&word;rm -rf'`);
    });
  });
});
