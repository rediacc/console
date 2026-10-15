/**
 * The WSL launcher used to export every connection variable, secrets included,
 * inside the command it hands to cmd.exe / wt.exe / wsl.exe as arguments. The
 * secrets now cross into WSL by name through WSLENV, with their values in the
 * spawned environment only. A fake spawn records what each launch would expose.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

interface Spawned {
  file: string;
  args: string[];
  env: NodeJS.ProcessEnv;
}

const spawned: Spawned[] = [];

vi.mock('node:child_process', () => ({
  spawn: (file: string, args: string[], options: { env: NodeJS.ProcessEnv }) => {
    spawned.push({ file, args, env: options.env });
    return { unref: () => undefined };
  },
}));

vi.mock('../../utils/platform.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/platform.js')>()),
  isWSL: () => true,
}));

const { buildBashExports, launchTerminal, withWslEnv } = await import('../launchers.js');

const SECRET = 'wsl-secret-value-3K';
const ENV = { REDIACC_REPOSITORY: 'app', REDIACC_SECRET_TOKEN: SECRET };

describe('WSL launcher secret delivery', () => {
  beforeEach(() => {
    spawned.length = 0;
  });

  it('exports only the non-secret variables', () => {
    const exports = buildBashExports(ENV);
    expect(exports).toBe("export REDIACC_REPOSITORY='app' && ");
    expect(exports).not.toContain(SECRET);
  });

  it('names the secrets in WSLENV, appending to an existing one', () => {
    expect(withWslEnv({ WSLENV: 'USERPROFILE/p' }, ENV).WSLENV).toBe(
      'USERPROFILE/p:REDIACC_SECRET_TOKEN'
    );
    expect(withWslEnv({}, { REDIACC_REPOSITORY: 'app' }).WSLENV).toBeUndefined();
  });

  it('keeps the secret out of every argument it spawns with', () => {
    const result = launchTerminal('wsl', {
      command: 'ssh -o SendEnv=REDIACC_SECRET_TOKEN repo@h',
      environmentVariables: ENV,
    });
    expect(result.success).toBe(true);
    expect(spawned).toHaveLength(1);
    const [{ args, env }] = spawned;
    for (const arg of args) expect(arg).not.toContain(SECRET);
    expect(env.REDIACC_SECRET_TOKEN).toBe(SECRET);
    expect(env.WSLENV).toContain('REDIACC_SECRET_TOKEN');
  });
});
