/**
 * A renet launch carrying secrets runs a root bash that exports each stdin
 * record before it execs renet. A name such as LD_PRELOAD, PATH, BASH_ENV or
 * IFS would change what that root bash and renet load, so only the names
 * buildRenetEnv emits (REDIACC_SECRET_*, REDIACC_OTLP_*) are admitted: the
 * builder refuses any other, and the reader refuses a forged record before it
 * exports it.
 */

import { execFileSync, spawnSync } from 'node:child_process';
import { chmodSync, existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { sudoRenet } from '../executor/renet-launch.js';

describe('sudoRenet secret names', () => {
  for (const name of [
    'LD_PRELOAD',
    'PATH',
    'BASH_ENV',
    'IFS',
    'REDIACC_SECRET_',
    'REDIACC_TOKEN',
  ]) {
    it(`refuses ${name || '(empty)'}`, () => {
      expect(() =>
        sudoRenet(
          { prefix: '', secrets: { REDIACC_SECRET_OK: 'v', [name]: '/tmp/x.so' } },
          'renet x'
        )
      ).toThrow(name);
    });
  }

  it('admits the names buildRenetEnv emits', () => {
    const launch = sudoRenet(
      {
        prefix: '',
        secrets: { REDIACC_OTLP_USER: 'u', REDIACC_OTLP_PASS: 'p', REDIACC_SECRET_DB_PASS: 's' },
      },
      'renet x'
    );
    expect(launch.stdinPrefix).toContain('REDIACC_SECRET_DB_PASS=s\0');
  });
});

describe('the stdin reader refuses a forged name, run for real', () => {
  let dir: string;
  let fakeRenet: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), 'renet-names-'));
    fakeRenet = join(dir, 'renet');
    writeFileSync(fakeRenet, `#!/usr/bin/env bash\ntouch ${JSON.stringify(join(dir, 'ran'))}\n`);
    chmodSync(fakeRenet, 0o755);
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  for (const forged of ['LD_PRELOAD=/tmp/evil.so', 'PATH=/tmp/evil', 'REDIACC_SECRET_X;y=1']) {
    it(`stops before exporting ${forged.split('=')[0]}`, () => {
      const launch = sudoRenet({ prefix: '', secrets: { REDIACC_SECRET_OK: 'v' } }, fakeRenet);
      const input = `REDIACC_SECRET_OK=v\0${forged}\0\0`;
      const result = spawnSync('bash', ['-c', launch.command.slice('sudo '.length)], { input });
      expect(result.status).toBe(97);
      expect(existsSync(join(dir, 'ran'))).toBe(false);
    });
  }

  it('still runs renet for admitted names', () => {
    const launch = sudoRenet({ prefix: '', secrets: { REDIACC_SECRET_OK: 'v' } }, fakeRenet);
    execFileSync('bash', ['-c', launch.command.slice('sudo '.length)], {
      input: launch.stdinPrefix,
    });
    expect(existsSync(join(dir, 'ran'))).toBe(true);
    rmSync(join(dir, 'ran'));
  });
});
