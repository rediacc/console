/**
 * The VS Code environment bootstrap hands setup-script.py a config whose env
 * block carries the repo's secret values. That config used to be an argument of
 * the local ssh and of the remote `python3`, readable in `ps` on both hosts.
 * It now goes on the ssh session's stdin. A fake ssh records both channels, and
 * the real setup script is run against the recorded stdin to prove the reader.
 */

import { execFileSync } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import { afterAll, describe, expect, it, vi } from 'vitest';

interface Recorded {
  file: string;
  args: string[];
  stdin: string;
}

const recorded: Recorded[] = [];

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: (file: string, args: string[]) => {
    const entry: Recorded = { file, args, stdin: '' };
    recorded.push(entry);
    const child = new EventEmitter() as EventEmitter & {
      stdin: PassThrough;
      stdout: PassThrough;
      stderr: PassThrough;
    };
    child.stdin = new PassThrough();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.stdin.on('data', (d: Buffer) => {
      entry.stdin += d.toString();
    });
    child.stdin.on('finish', () => setImmediate(() => child.emit('close', 0)));
    return child;
  },
}));

const SETUP_SCRIPT = readFileSync(new URL('../setup-script.py', import.meta.url), 'utf8');
vi.mock('../setup-script.py', () => ({ default: 'print(1)' }));

const { ensureVSCodeEnvSetup } = await import('../bootstrap.js');

const SECRET = 'vscode-secret-value-8W';
const dirs: string[] = [];

afterAll(() => {
  for (const d of dirs) rmSync(d, { recursive: true, force: true });
});

describe('ensureVSCodeEnvSetup secret delivery', () => {
  it('sends the config on stdin and no secret in the ssh argv', async () => {
    recorded.length = 0;
    const result = await ensureVSCodeEnvSetup({
      sshDestination: 'repo@h',
      sshOptions: ['-o', 'BatchMode=yes'],
      envVars: { REDIACC_REPOSITORY: 'app', REDIACC_SECRET_API_KEY: SECRET },
      universalUser: 'rediacc',
      sshUser: 'root',
      serverInstallPath: '/mnt/rediacc/mounts/x',
    });

    expect(result.success).toBe(true);
    expect(recorded).toHaveLength(1);
    const [{ file, args, stdin }] = recorded;
    expect(file).toBe('ssh');
    for (const arg of args) expect(arg).not.toContain(SECRET);
    expect(args.at(-1)).toMatch(/^sudo -u 'rediacc' python3 -c '.*'$/s);
    const config = JSON.parse(stdin) as { envBlock: string };
    expect(config.envBlock).toContain(`export REDIACC_SECRET_API_KEY='${SECRET}'`);
  });

  it('the real setup script reads that config from stdin', () => {
    const home = mkdtempSync(join(tmpdir(), 'vscode-bootstrap-'));
    dirs.push(home);
    const config = JSON.stringify({
      envBlock: '',
      bashFunctions: '',
      universalUser: 'x',
      serverInstallPath: '/nowhere',
      markerStart: '#s',
      markerEnd: '#e',
    });
    const probe = `${SETUP_SCRIPT.split('\ndef main')[0]}\nprint(UNIVERSAL_USER)\n`;
    const out = execFileSync('python3', ['-c', probe], {
      input: config,
      env: { ...process.env, HOME: home },
    }).toString();
    expect(out.trim()).toBe('x');
  });
});
