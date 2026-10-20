import { describe, expect, it } from 'vitest';
import { shellQuote } from '../../utils/shell-quote.js';
import { buildRemoteRenetCommand, buildRenetEnv } from '../executor/local-executor.js';
import { STDIN_ENV_READER } from '../executor/renet-launch.js';

describe('buildRenetEnv: envSecrets', () => {
  it('emits no prefix and no secrets when nothing is needed', () => {
    expect(
      buildRenetEnv({
        isDevelopment: false,
        telemetryDisabled: false,
      })
    ).toEqual({ prefix: '', secrets: {} });
  });

  it('keeps secret values verbatim and out of the prefix; tolerates spaces, $ and quotes', () => {
    const out = buildRenetEnv({
      isDevelopment: false,
      telemetryDisabled: true,
      envSecrets: {
        REDIACC_SECRET_PLAIN: 'simple',
        REDIACC_SECRET_SPACE: 'with space',
        REDIACC_SECRET_DOLLAR: 'has $variable',
        REDIACC_SECRET_QUOTE: "it's a quote",
      },
    });
    expect(out.prefix).toBe('env REDIACC_TELEMETRY_DISABLED=1 ');
    expect(out.secrets).toEqual({
      REDIACC_SECRET_PLAIN: 'simple',
      REDIACC_SECRET_SPACE: 'with space',
      REDIACC_SECRET_DOLLAR: 'has $variable',
      REDIACC_SECRET_QUOTE: "it's a quote",
    });
  });

  it('preserves newlines (multiline PEM secrets)', () => {
    const out = buildRenetEnv({
      isDevelopment: false,
      telemetryDisabled: false,
      envSecrets: {
        REDIACC_SECRET_PEM: '-----BEGIN-----\nA\nB\n-----END-----',
      },
    });
    expect(out.secrets.REDIACC_SECRET_PEM).toBe('-----BEGIN-----\nA\nB\n-----END-----');
  });

  it('telemetry disabled still forwards secrets', () => {
    const out = buildRenetEnv({
      isDevelopment: false,
      telemetryDisabled: true,
      envSecrets: { REDIACC_SECRET_X: 'x' },
    });
    expect(out.prefix).toContain('REDIACC_TELEMETRY_DISABLED=1');
    expect(out.secrets).toEqual({ REDIACC_SECRET_X: 'x' });
  });

  it('OTLP creds and secrets travel together, off the prefix', () => {
    const out = buildRenetEnv({
      isDevelopment: false,
      telemetryDisabled: false,
      otlpCreds: { user: 'u', pass: 'p' },
      envSecrets: { REDIACC_SECRET_X: 'x' },
    });
    expect(out.prefix).toBe('');
    expect(out.secrets).toEqual({
      REDIACC_OTLP_USER: 'u',
      REDIACC_OTLP_PASS: 'p',
      REDIACC_SECRET_X: 'x',
    });
  });
});

describe('buildRemoteRenetCommand — envSecrets', () => {
  it('puts the secret on stdin and only the reader on the command', () => {
    const launch = buildRemoteRenetCommand({
      remoteRenetPath: '/usr/bin/renet',
      isDevelopment: false,
      telemetryDisabled: true,
      envSecrets: { REDIACC_SECRET_FOO: 'bar' },
    });
    expect(launch.command).toBe(
      `sudo bash -c ${shellQuote(`${STDIN_ENV_READER}env REDIACC_TELEMETRY_DISABLED=1 '/usr/bin/renet' execute --executor local`)}`
    );
    expect(launch.stdinPrefix).toBe('REDIACC_SECRET_FOO=bar\0\0');
    // The reader text itself is pinned here too (review 978aa3f1.2): the root shell exports only REDIACC_SECRET_*/REDIACC_OTLP_* names and refuses any other with exit 97.
    expect(STDIN_ENV_READER).toContain('REDIACC_SECRET_?*=*|REDIACC_OTLP_?*=*) ;;');
    expect(STDIN_ENV_READER).toContain("echo 'renet launch: refused secret name' >&2; exit 97");
  });

  it('omits envSecrets when undefined (no extra space, no extra tokens)', () => {
    const launch = buildRemoteRenetCommand({
      remoteRenetPath: '/usr/bin/renet',
      isDevelopment: false,
      telemetryDisabled: true,
    });
    expect(launch).toEqual({
      command: "sudo env REDIACC_TELEMETRY_DISABLED=1 '/usr/bin/renet' execute --executor local",
      stdinPrefix: '',
    });
  });

  it('refuses a name the remote reader could not export', () => {
    expect(() =>
      buildRemoteRenetCommand({
        remoteRenetPath: '/usr/bin/renet',
        isDevelopment: false,
        telemetryDisabled: true,
        envSecrets: { 'BAD NAME': 'x' },
      })
    ).toThrow(/Refused secret name/);
  });
});
