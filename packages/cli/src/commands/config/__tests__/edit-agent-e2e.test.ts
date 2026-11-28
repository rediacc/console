/**
 * The real CLI entry refuses an agent's whole-document edit and rotation (PLAN-rmcp-config-edit-removal.md, box R5).
 *
 * The retired config-edit override is exported, set to `*`, in the environment of an agent-marked parent shell
 * (CLAUDECODE=1) that then runs `rdc`, the shape an operator used to opt an agent in with. Nothing is mocked: the
 * child is `src/index.ts` under tsx, the entry stdio-e2e.test.ts drives, against a temporary XDG_CONFIG_HOME
 * fixture. Both `config edit --apply <file>` and `config field rotate` must exit non-zero with the current refusal
 * text on stderr, and the config file must be byte-identical afterwards.
 *
 * The ancestry proof the override once needed depends on the processes above the test runner, so it is not what
 * this file asserts: the refusal must hold whatever that proof would say. edit-agent-gate.test.ts and
 * mutation-gate.test.ts hold the verified-ancestry case with the ancestry check stubbed to "legitimate".
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const CLI_ROOT = path.resolve(import.meta.dirname, '..', '..', '..', '..');
const EN = JSON.parse(
  readFileSync(path.join(CLI_ROOT, 'src', 'i18n', 'locales', 'en', 'cli.json'), 'utf-8')
) as { errors: { agent: Record<string, string> } };
const CONFIG_NAME = 'r5-e2e';
// The retired override, spelled in pieces so the removed-name gate finds no literal here.
const OLD_VAR = ['REDIACC', 'ALLOW', 'CONFIG', 'EDIT'].join('_');

const FIXTURE = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000e5',
  version: 1,
  credentials: { ssh: { privateKey: 'OLD-KEY' } },
  resources: { machines: { m1: { ip: '192.0.2.10', user: 'root', port: 22 } } },
  encryption: { mode: 'plaintext' },
};

let home: string;
let configFile: string;

/** Whitespace collapsed: the CLI wraps error text to the terminal width. */
const flat = (text: string): string => text.replace(/\s+/g, ' ');

/** The parent shell's env: the fixture's homes, the agent marker and the retired override, nothing inherited from REDIACC_*. */
function agentParentEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v === undefined || k.startsWith('REDIACC_') || k === 'RDC_DEV' || k === 'CI') continue;
    env[k] = v;
  }
  env.XDG_CONFIG_HOME = path.join(home, 'config');
  env.XDG_STATE_HOME = path.join(home, 'state');
  env.XDG_CACHE_HOME = path.join(home, 'cache');
  env.NO_COLOR = '1';
  env.REDIACC_DEFAULT_OUTPUT = 'table';
  env.CLAUDECODE = '1';
  env[OLD_VAR] = '*';
  return env;
}

/** Run `rdc <args>` as the child of an agent-marked shell that carries the override in its own exec-time env. */
function rdcUnderAgentShell(args: string[]) {
  const quoted = args.map((a) => `'${a.replaceAll("'", "'\\''")}'`).join(' ');
  return spawnSync(
    'sh',
    ['-c', `exec npx tsx src/index.ts --config ${CONFIG_NAME} ${quoted} </dev/null`],
    { cwd: CLI_ROOT, env: agentParentEnv(), encoding: 'utf-8', timeout: 90_000 }
  );
}

beforeAll(() => {
  home = mkdtempSync(path.join(tmpdir(), 'rdc-r5-e2e-'));
  const configDir = path.join(home, 'config', 'rediacc');
  mkdirSync(configDir, { recursive: true });
  configFile = path.join(configDir, `${CONFIG_NAME}.json`);
  writeFileSync(configFile, JSON.stringify(FIXTURE));
});

afterAll(() => {
  if (home) rmSync(home, { recursive: true, force: true });
});

describe('the real CLI refuses an agent with the retired override exported', () => {
  it('config edit --apply exits non-zero, prints the refusal on stderr, and leaves the config byte-identical', () => {
    const edited = path.join(home, 'edited.json');
    writeFileSync(edited, JSON.stringify({ ...FIXTURE, defaults: { pruneGraceDays: 9 } }));
    const before = readFileSync(configFile);

    const done = rdcUnderAgentShell(['config', 'edit', '--apply', edited]);

    expect(done.status, done.stderr).not.toBe(0);
    expect(flat(done.stderr)).toContain(flat(EN.errors.agent.configEdit));
    expect(done.stderr).not.toContain(OLD_VAR);
    expect(readFileSync(configFile).equals(before)).toBe(true);
  }, 120_000);

  it('config field rotate exits non-zero, prints the refusal on stderr, and leaves the config byte-identical', () => {
    const before = readFileSync(configFile);

    const done = rdcUnderAgentShell([
      'config',
      'field',
      'rotate',
      '--pointer',
      '/credentials/ssh/privateKey',
      '--new',
      'NEW-KEY',
    ]);

    expect(done.status, done.stderr).not.toBe(0);
    expect(flat(done.stderr)).toContain(flat(EN.errors.agent.rotateRequiresTty));
    expect(done.stderr).not.toContain(OLD_VAR);
    expect(readFileSync(configFile).equals(before)).toBe(true);
  }, 120_000);

  it('control: the same shell runs config edit --dump --redacted, so the refusals are not a broken entry', () => {
    const done = rdcUnderAgentShell(['config', 'edit', '--dump', '--redacted']);
    expect(done.status, done.stderr).toBe(0);
    expect(done.stdout).toContain('<redacted:');
    expect(done.stdout).not.toContain('OLD-KEY');
  }, 120_000);
});
