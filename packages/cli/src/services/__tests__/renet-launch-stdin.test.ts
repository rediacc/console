/**
 * Secrets reach a remote renet through stdin, never through its command line.
 *
 * Every renet launch the CLI sends over SSH (`execute`, detached `job start`,
 * `list all`) used to splice `REDIACC_OTLP_PASS` and each `REDIACC_SECRET_*`
 * into a `sudo env K='v' renet ...` command, readable in the local ssh argv
 * and in `ps` on the machine. The launch now carries them as NUL-terminated
 * records ahead of the vault, read by a root bash that exports them and execs
 * renet.
 *
 * The round-trip test runs the real launcher under bash (sudo stripped), with
 * a stand-in renet that records its argv, environment and stdin, so it proves
 * the reader end, not only the string.
 */

import { execFileSync } from 'node:child_process';
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildJobStartCommand } from '../executor/job-client.js';
import { buildRemoteRenetCommand, buildRenetEnv } from '../executor/local-executor.js';
import { buildListCommand } from '../machine/machine-status.js';

const PASS = 'otlp-pass-Zq9';
const SECRET = "multi\nline 'quoted' $HOME `x` value";
const PARAMS = {
  isDevelopment: true,
  telemetryDisabled: false,
  otlpCreds: { user: 'otlp-user', pass: PASS },
  envSecrets: { REDIACC_SECRET_DB: SECRET, REDIACC_SECRET_EMPTY: '' },
};

describe('every renet launch keeps secrets off the command', () => {
  const launches = {
    execute: () =>
      buildRemoteRenetCommand({ remoteRenetPath: '/usr/bin/renet', eventsMode: true, ...PARAMS }),
    'job start': () =>
      buildJobStartCommand({ remoteRenetPath: '/usr/bin/renet', env: buildRenetEnv(PARAMS) }),
    'list all': () =>
      buildListCommand({
        remoteRenetPath: '/usr/bin/renet',
        datastore: '/mnt/rediacc',
        env: buildRenetEnv(PARAMS),
      }),
  };

  for (const [name, build] of Object.entries(launches)) {
    it(`${name}: no secret value in the command, every one on stdin`, () => {
      const launch = build();
      expect(launch.command).not.toContain(PASS);
      expect(launch.command).not.toContain('multi');
      expect(launch.command).not.toContain('REDIACC_SECRET_DB');
      expect(launch.stdinPrefix).toContain(`REDIACC_OTLP_PASS=${PASS}\0`);
      expect(launch.stdinPrefix).toContain(`REDIACC_SECRET_DB=${SECRET}\0`);
      // The non-secret setting stays visible on the command.
      expect(launch.command).toContain('REDIACC_ENVIRONMENT=development');
    });
  }
});

describe('the stdin reader, run for real', () => {
  let dir: string;
  let fakeRenet: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'renet-launch-'));
    fakeRenet = join(dir, 'renet');
    // Records argv, the variables under test, and the stdin it inherits.
    writeFileSync(
      fakeRenet,
      [
        '#!/usr/bin/env bash',
        `out=${JSON.stringify(dir)}`,
        'printf "%s\\0" "$@" > "$out/argv"',
        'printf "%s" "$REDIACC_SECRET_DB" > "$out/secret"',
        'printf "%s" "${REDIACC_SECRET_EMPTY-unset}" > "$out/empty"',
        'printf "%s|%s" "$REDIACC_OTLP_USER" "$REDIACC_OTLP_PASS" > "$out/otlp"',
        'printf "%s" "$REDIACC_ENVIRONMENT" > "$out/environment"',
        'cat > "$out/stdin"',
      ].join('\n')
    );
    chmodSync(fakeRenet, 0o755);
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it('exports each record, then hands renet the vault byte-for-byte', () => {
    const launch = buildRemoteRenetCommand({ remoteRenetPath: fakeRenet, ...PARAMS });
    expect(launch.command.startsWith('sudo bash -c ')).toBe(true);
    const vault = '{"vault":"json","with":"\\n newline"}\n';

    execFileSync('sh', ['-c', launch.command.slice('sudo '.length)], {
      input: launch.stdinPrefix + vault,
    });

    expect(readFileSync(join(dir, 'secret'), 'utf8')).toBe(SECRET);
    expect(readFileSync(join(dir, 'empty'), 'utf8')).toBe('');
    expect(readFileSync(join(dir, 'otlp'), 'utf8')).toBe(`otlp-user|${PASS}`);
    expect(readFileSync(join(dir, 'environment'), 'utf8')).toBe('development');
    expect(readFileSync(join(dir, 'stdin'), 'utf8')).toBe(vault);
    expect(readFileSync(join(dir, 'argv'), 'utf8')).toBe('execute\0--executor\0local\0');
  });
});
