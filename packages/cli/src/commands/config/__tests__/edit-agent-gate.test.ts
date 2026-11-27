/**
 * `rdc config edit` has no agent override (PLAN-rmcp-config-edit-removal.md, box R1).
 *
 * Every agent is refused for the interactive editor, `--apply` and `--reveal`, even with the old
 * override var set to `*` and the ancestry check reporting it legitimate; `--dump --redacted`
 * stays open to agents; and `--apply` needs a TTY on stdin even for a human, so a script an agent
 * drives outside the ancestry check cannot reach it.
 */

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const configHome = mkdtempSync(join(tmpdir(), 'rdc-edit-agent-gate-'));
process.env.XDG_CONFIG_HOME = configHome;
const NAME = 'gate';
const OLD_VAR = ['REDIACC', 'ALLOW', 'CONFIG', 'EDIT'].join('_');

const state = vi.hoisted(() => ({ agent: false, stdinTty: true, stdoutTty: true, stderr: '' }));

vi.mock('node:tty', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:tty')>();
  return {
    ...actual,
    isatty: (fd: number) => {
      if (fd === 0) return state.stdinTty;
      return fd === 1 && state.stdoutTty;
    },
  };
});
vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  isAgentEnvironment: () => state.agent,
}));
vi.mock('../../../utils/process-ancestry.js', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  // The ancestry proof the old override needed: report it verified, so a refusal cannot be blamed on it.
  isOverrideLegitimate: () => true,
}));
vi.mock('../../../utils/editor-launcher.js', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  openEditor: vi.fn(),
}));
vi.mock('../../../services/core/output.js', () => ({
  outputService: {
    success: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    // handleError prints the refusal through outputService.error, the stderr channel.
    error: vi.fn((line: string) => {
      state.stderr += `${line}\n`;
    }),
    print: vi.fn(),
  },
}));

const { configFileStorage } = await import('../../../adapters/config-file-storage.js');
const { configService } = await import('../../../services/config/config-resources.js');
const { redactClone } = await import('../../../schema/fingerprint.js');
const { openEditor } = await import('../../../utils/editor-launcher.js');
const { t } = await import('../../../i18n/index.js');
const { registerEditCommands } = await import('../edit.js');

let stdout = '';
const stderrText = (): string => state.stderr;

function configPath(): string {
  return join(configHome, 'rediacc', `${NAME}.json`);
}

async function run(args: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  program.configureOutput({
    writeErr: (s) => {
      state.stderr += s;
    },
    writeOut: (s) => {
      stdout += s;
    },
  });
  const config = program.command('config').exitOverride();
  registerEditCommands(config, program);
  for (const sub of config.commands) sub.exitOverride();
  await program.parseAsync(['config', 'edit', ...args], { from: 'user' });
}

async function editedFile(): Promise<string> {
  const edited = redactClone((await configService.getCurrent())!);
  edited.defaults = { ...edited.defaults, pruneGraceDays: 9 };
  const file = join(configHome, 'edited.json');
  writeFileSync(file, JSON.stringify(edited));
  return file;
}

beforeEach(async () => {
  state.agent = false;
  state.stdinTty = true;
  state.stdoutTty = true;
  state.stderr = '';
  stdout = '';
  process.env[OLD_VAR] = '*';
  vi.mocked(openEditor).mockReset();
  vi.spyOn(process, 'exit').mockImplementation((code) => {
    throw new Error(`rdc exited with code ${String(code)}`);
  });
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk) => {
    stdout += String(chunk);
    return true;
  });
  await configFileStorage.delete(NAME).catch(() => undefined);
  await configFileStorage.init(NAME);
  await configFileStorage.update(NAME, (cfg) => ({
    ...cfg,
    infra: { certEmail: 'old@example.com' },
  }));
  configService.setRuntimeConfig(NAME);
});

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env[OLD_VAR];
});

afterAll(() => {
  rmSync(configHome, { recursive: true, force: true });
});

const refusal = (): string => t('errors.agent.configEdit').split('\n')[0];

describe('config edit agent gate (no override)', () => {
  it('refuses an agent the interactive editor with the old var set to * and verified ancestry', async () => {
    state.agent = true;
    const before = readFileSync(configPath());
    await expect(run([])).rejects.toThrow(/exited with code/);
    expect(stderrText()).toContain(refusal());
    expect(openEditor).not.toHaveBeenCalled();
    expect(readFileSync(configPath()).equals(before)).toBe(true);
  });

  it('refuses an agent --apply with the old var set to *, the config byte-identical', async () => {
    state.agent = true;
    const file = await editedFile();
    const before = readFileSync(configPath());
    await expect(run(['--apply', file])).rejects.toThrow(/exited with code/);
    expect(stderrText()).toContain(refusal());
    expect(readFileSync(configPath()).equals(before)).toBe(true);
  });

  it('refuses an agent --reveal, even with --dump', async () => {
    state.agent = true;
    await expect(run(['--dump', '--reveal'])).rejects.toThrow(/exited with code/);
    expect(stderrText()).toContain(refusal());
    expect(stdout).toBe('');
  });

  it('lets an agent run --dump --redacted, and the dump carries no plaintext', async () => {
    state.agent = true;
    await run(['--dump', '--redacted']);
    expect(stdout).toContain('<redacted:');
    expect(stdout).not.toContain('old@example.com');
  });

  it('the refusal names no override and suggests no --apply path', () => {
    const text = t('errors.agent.configEdit');
    expect(text).not.toContain(OLD_VAR);
    expect(text).not.toContain('edit --apply');
    expect(text).toContain('--dump --redacted');
  });

  it('refuses a human --apply without a TTY on stdin, the config byte-identical', async () => {
    state.stdinTty = false;
    const file = await editedFile();
    const before = readFileSync(configPath());
    await expect(run(['--apply', file])).rejects.toThrow(/exited with code/);
    expect(stderrText()).toContain(t('errors.agent.applyRequiresTty'));
    expect(readFileSync(configPath()).equals(before)).toBe(true);
  });

  it('control: a human --apply at a TTY is applied', async () => {
    const file = await editedFile();
    await run(['--apply', file]);
    expect((await configFileStorage.load(NAME)).defaults?.pruneGraceDays).toBe(9);
  });

  it('--redacted conflicts with --reveal', async () => {
    await expect(run(['--dump', '--redacted', '--reveal'])).rejects.toThrow(/cannot be used/);
  });
});
