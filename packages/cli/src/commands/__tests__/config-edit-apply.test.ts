/**
 * `rdc config edit --apply` keeps the sensitive values the edit sets.
 *
 * Two paths used to put the CURRENT value back over the edited one: a changed sensitive value
 * with its old value supplied through `--current-secrets`, and a sensitive value that did not
 * exist before. Both applied "successfully" and silently kept the old document.
 */

import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const configHome = mkdtempSync(join(tmpdir(), 'rdc-edit-apply-'));
process.env.XDG_CONFIG_HOME = configHome;
const NAME = 'edt';

vi.mock('../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  isAgentEnvironment: () => false,
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { success: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));

const { configFileStorage } = await import('../../adapters/config-file-storage.js');
const { configService } = await import('../../services/config/config-resources.js');
const { redactClone } = await import('../../schema/fingerprint.js');
const { registerEditCommands } = await import('../config/edit.js');

async function apply(edited: unknown, knowledge?: Record<string, unknown>): Promise<void> {
  const file = join(configHome, 'edited.json');
  writeFileSync(file, JSON.stringify(edited));
  const args = ['config', 'edit', '--apply', file];
  if (knowledge) {
    const knowledgeFile = join(configHome, 'knowledge.json');
    writeFileSync(knowledgeFile, JSON.stringify(knowledge));
    args.push('--current-secrets', knowledgeFile);
  }
  const program = new Command();
  program.exitOverride();
  registerEditCommands(program.command('config'), program);
  await program.parseAsync(args, { from: 'user' });
}

beforeEach(async () => {
  vi.spyOn(process, 'exit').mockImplementation((code) => {
    throw new Error(`rdc exited with code ${String(code)}`);
  });
  await configFileStorage.delete(NAME).catch(() => undefined);
  await configFileStorage.init(NAME);
  await configFileStorage.update(NAME, (cfg) => ({
    ...cfg,
    infra: { certEmail: 'old@example.com' },
  }));
  configService.setRuntimeConfig(NAME);
});

afterAll(() => {
  rmSync(configHome, { recursive: true, force: true });
});

describe('config edit --apply', () => {
  it('a changed sensitive value with its old value supplied is applied', async () => {
    const edited = redactClone((await configService.getCurrent())!);
    edited.infra = { certEmail: 'new@example.com' };
    await apply(edited, { '/infra/certEmail': 'old@example.com' });
    expect((await configFileStorage.load(NAME)).infra?.certEmail).toBe('new@example.com');
  });

  it('a wrong old value is refused and nothing changes', async () => {
    const edited = redactClone((await configService.getCurrent())!);
    edited.infra = { certEmail: 'new@example.com' };
    await expect(apply(edited, { '/infra/certEmail': 'guess@example.com' })).rejects.toThrow(
      /exited with code/
    );
    expect((await configFileStorage.load(NAME)).infra?.certEmail).toBe('old@example.com');
  });

  it('a sensitive value that did not exist before is added', async () => {
    const edited = redactClone((await configService.getCurrent())!);
    edited.defaults = { universalUser: 'deploy' };
    await apply(edited);
    expect((await configFileStorage.load(NAME)).defaults?.universalUser).toBe('deploy');
  });

  it('control: a changed sensitive value without its old value is refused', async () => {
    const edited = redactClone((await configService.getCurrent())!);
    edited.infra = { certEmail: 'new@example.com' };
    await expect(apply(edited)).rejects.toThrow(/exited with code/);
    expect((await configFileStorage.load(NAME)).infra?.certEmail).toBe('old@example.com');
  });
});
