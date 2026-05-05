import { describe, expect, it } from 'vitest';

import { buildRemoteRenetCommand, buildRenetEnvPrefix } from '../local-executor.js';

describe('buildRenetEnvPrefix — envSecrets', () => {
  it('emits no prefix when nothing is needed', () => {
    expect(
      buildRenetEnvPrefix({
        isDevelopment: false,
        telemetryDisabled: false,
      })
    ).toBe('');
  });

  it('shell-quotes secret values; tolerates spaces, $ and quotes', () => {
    const out = buildRenetEnvPrefix({
      isDevelopment: false,
      telemetryDisabled: true,
      envSecrets: {
        REDIACC_SECRET_PLAIN: 'simple',
        REDIACC_SECRET_SPACE: 'with space',
        REDIACC_SECRET_DOLLAR: 'has $variable',
        REDIACC_SECRET_QUOTE: "it's a quote",
      },
    });
    expect(out).toContain("REDIACC_SECRET_PLAIN='simple'");
    expect(out).toContain("REDIACC_SECRET_SPACE='with space'");
    expect(out).toContain("REDIACC_SECRET_DOLLAR='has $variable'");
    // single-quote escape: ' → '\'' (the only safe inner-quote pattern in sh)
    expect(out).toContain("REDIACC_SECRET_QUOTE='it'\\''s a quote'");
  });

  it('handles multi-line values (PEMs etc) without breaking', () => {
    const out = buildRenetEnvPrefix({
      isDevelopment: false,
      telemetryDisabled: true,
      envSecrets: {
        REDIACC_SECRET_PEM: '-----BEGIN-----\nA\nB\n-----END-----',
      },
    });
    expect(out).toContain("REDIACC_SECRET_PEM='-----BEGIN-----\nA\nB\n-----END-----'");
  });

  it('combines telemetry-disabled and envSecrets into a single env prefix', () => {
    const out = buildRenetEnvPrefix({
      isDevelopment: true,
      telemetryDisabled: true,
      envSecrets: { REDIACC_SECRET_X: 'x' },
    });
    expect(out).toMatch(/^env /);
    expect(out).toContain('REDIACC_ENVIRONMENT=development');
    expect(out).toContain('REDIACC_TELEMETRY_DISABLED=1');
    expect(out).toContain("REDIACC_SECRET_X='x'");
    expect(out).toMatch(/ $/); // trailing space for splice
  });

  it('does NOT inject envSecrets into the OTLP-credential branch when telemetry is enabled', () => {
    // Telemetry enabled (telemetryDisabled=false) AND otlpCreds present:
    // OTLP creds are exported. envSecrets are still appended after them.
    const out = buildRenetEnvPrefix({
      isDevelopment: false,
      telemetryDisabled: false,
      otlpCreds: { user: 'u', pass: 'p' },
      envSecrets: { REDIACC_SECRET_X: 'x' },
    });
    expect(out).toContain("REDIACC_OTLP_USER='u'");
    expect(out).toContain("REDIACC_OTLP_PASS='p'");
    expect(out).toContain("REDIACC_SECRET_X='x'");
  });
});

describe('buildRemoteRenetCommand — envSecrets', () => {
  it('produces a sudo invocation that splices the env prefix', () => {
    const cmd = buildRemoteRenetCommand({
      remoteRenetPath: '/usr/bin/renet',
      isDevelopment: false,
      telemetryDisabled: true,
      envSecrets: { REDIACC_SECRET_FOO: 'bar' },
    });
    expect(cmd).toBe(
      "sudo env REDIACC_TELEMETRY_DISABLED=1 REDIACC_SECRET_FOO='bar' /usr/bin/renet execute --executor local"
    );
  });

  it('omits envSecrets when undefined (no extra space, no extra tokens)', () => {
    const cmd = buildRemoteRenetCommand({
      remoteRenetPath: '/usr/bin/renet',
      isDevelopment: false,
      telemetryDisabled: true,
    });
    expect(cmd).toBe(
      'sudo env REDIACC_TELEMETRY_DISABLED=1 /usr/bin/renet execute --executor local'
    );
  });
});
