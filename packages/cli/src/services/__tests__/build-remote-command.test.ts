/**
 * Tests for `buildRemoteRenetCommand`, the function that builds the SSH
 * command (and its stdin prefix) for spawning `renet execute` on a target
 * machine.
 *
 * The goal is to verify every combination of inputs produces the exact
 * expected launch. Any regression that changes env var ordering, puts a
 * credential on the command line, or leaks OTLP credentials when telemetry is
 * disabled will fail this test.
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
import { buildRemoteRenetCommand } from '../executor/local-executor.js';
import { STDIN_ENV_READER } from '../executor/renet-launch.js';

const RENET = '/usr/bin/renet';
const CREDS = { user: 'otlp-eu-abc123', pass: 'base64url-pass_-_' };
const CREDS_STDIN = 'REDIACC_OTLP_USER=otlp-eu-abc123\0REDIACC_OTLP_PASS=base64url-pass_-_\0\0';

/** The secret-carrying form: root bash reads the stdin records, then execs renet. */
function stdinLaunch(invocation: string): string {
  const script = `${STDIN_ENV_READER}${invocation}`;
  return `sudo bash -c '${script.replaceAll("'", "'\\''")}'`;
}

describe('buildRemoteRenetCommand', () => {
  describe('telemetry enabled', () => {
    it('with creds: REDIACC_OTLP_USER/PASS ride stdin, never the command', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: CREDS,
      });
      expect(launch.command).toBe(stdinLaunch(`'/usr/bin/renet' execute --executor local`));
      expect(launch.stdinPrefix).toBe(CREDS_STDIN);
      expect(launch.command).not.toContain('otlp-eu-abc123');
      expect(launch.command).not.toContain('base64url-pass');
    });

    it('without creds: no OTLP env vars, no REDIACC_TELEMETRY_DISABLED', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: null,
      });
      expect(launch.command).toBe(`sudo '/usr/bin/renet' execute --executor local`);
      expect(launch.stdinPrefix).toBe('');
      expect(launch.command).not.toContain('REDIACC_TELEMETRY_DISABLED');
    });

    it('with creds + dev mode: REDIACC_ENVIRONMENT on the command, creds on stdin', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: true,
        telemetryDisabled: false,
        otlpCreds: CREDS,
      });
      expect(launch.command).toBe(
        stdinLaunch(`env REDIACC_ENVIRONMENT=development '/usr/bin/renet' execute --executor local`)
      );
      expect(launch.stdinPrefix).toBe(CREDS_STDIN);
    });
  });

  describe('telemetry disabled', () => {
    it('with creds: injects REDIACC_TELEMETRY_DISABLED=1 and IGNORES creds', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: true,
        otlpCreds: CREDS,
      });
      expect(launch.command).toBe(
        `sudo env REDIACC_TELEMETRY_DISABLED=1 '/usr/bin/renet' execute --executor local`
      );
      // Critical: no OTLP credentials leak into the remote env, by either channel
      expect(launch.stdinPrefix).toBe('');
      expect(launch.command).not.toContain('REDIACC_OTLP');
      expect(launch.command).not.toContain('otlp-eu-abc123');
      expect(launch.command).not.toContain('base64url-pass');
    });

    it('without creds: injects REDIACC_TELEMETRY_DISABLED=1', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: true,
        otlpCreds: null,
      });
      expect(launch.command).toBe(
        `sudo env REDIACC_TELEMETRY_DISABLED=1 '/usr/bin/renet' execute --executor local`
      );
    });

    it('dev mode: REDIACC_ENVIRONMENT stays, telemetry disabled still wins', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: true,
        telemetryDisabled: true,
        otlpCreds: CREDS,
      });
      expect(launch.command).toBe(
        `sudo env REDIACC_ENVIRONMENT=development REDIACC_TELEMETRY_DISABLED=1 '/usr/bin/renet' execute --executor local`
      );
      expect(launch.stdinPrefix).toBe('');
    });
  });

  describe('events mode', () => {
    it('appends --events flag after executor local', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        eventsMode: true,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: null,
      });
      expect(launch.command).toBe(`sudo '/usr/bin/renet' execute --executor local --events`);
    });

    it('combines with other flags correctly', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        eventsMode: true,
        isDevelopment: true,
        telemetryDisabled: true,
        otlpCreds: CREDS,
      });
      expect(launch.command).toBe(
        `sudo env REDIACC_ENVIRONMENT=development REDIACC_TELEMETRY_DISABLED=1 '/usr/bin/renet' execute --executor local --events`
      );
    });
  });

  describe('credential bytes', () => {
    it('carries quotes and shell metacharacters verbatim on stdin, none on the command', () => {
      const launch = buildRemoteRenetCommand({
        remoteRenetPath: RENET,
        isDevelopment: false,
        telemetryDisabled: false,
        otlpCreds: { user: "has'quote", pass: 'p$ss&word;rm -rf' },
      });
      expect(launch.stdinPrefix).toBe(
        "REDIACC_OTLP_USER=has'quote\0REDIACC_OTLP_PASS=p$ss&word;rm -rf\0\0"
      );
      expect(launch.command).not.toContain('quote');
      expect(launch.command).not.toContain('p$ss');
    });
  });
});
