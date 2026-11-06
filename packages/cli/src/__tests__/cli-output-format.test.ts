import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Command } from 'commander';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createCli } from '../cli.js';
import { registerAuditCommands } from '../commands/config/audit.js';
import { initI18n } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setOutputFormat } from '../utils/errors.js';

// `-o` is checked at parse time, and `config audit log` renders the requested format instead of always printing JSON.
class ExitCalled extends Error {
  constructor(readonly code: number) {
    super(`exit ${code}`);
  }
}

describe('global -o validation', () => {
  beforeEach(async () => {
    await initI18n();
    vi.spyOn(process, 'exit').mockImplementation(((code?: number) => {
      throw new ExitCalled(code ?? 0);
    }) as never);
    vi.spyOn(outputService, 'error').mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    setOutputFormat('table');
  });

  it.each(['yml', 'xml', 'JSON'])(
    'refuses -o %s with exit 2 before the command runs',
    async (bad) => {
      const cli = createCli();
      const ran = vi.fn();
      cli.command('probe').action(ran);
      await expect(cli.parseAsync(['node', 'rdc', '-o', bad, 'probe'])).rejects.toMatchObject({
        code: 2,
      });
      expect(ran).not.toHaveBeenCalled();
      const stderr = vi
        .mocked(outputService.error)
        .mock.calls.map((c) => String(c[0]))
        .join('');
      expect(stderr).toContain(bad);
      // The allowed formats are named, whatever separator the message joins them with.
      for (const allowed of ['table', 'json', 'yaml', 'csv']) expect(stderr).toContain(allowed);
    }
  );

  it.each(['table', 'json', 'yaml', 'csv'])('accepts -o %s', async (ok) => {
    const cli = createCli();
    const ran = vi.fn();
    cli.command('probe').action(ran);
    await cli.parseAsync(['node', 'rdc', '-o', ok, 'probe']);
    expect(ran).toHaveBeenCalled();
  });
});

describe('config audit log honours the output format', () => {
  const dir = mkdtempSync(join(tmpdir(), 'audit-fmt-'));
  const prev = process.env.XDG_CONFIG_HOME;
  afterAll(() => rmSync(dir, { recursive: true, force: true }));
  beforeEach(async () => {
    await initI18n();
    process.env.XDG_CONFIG_HOME = dir;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    setOutputFormat('table');
    if (prev === undefined) delete process.env.XDG_CONFIG_HOME;
    else process.env.XDG_CONFIG_HOME = prev;
  });

  it.each(['yaml', 'table'] as const)('renders %s, not JSON', async (fmt) => {
    mkdirSync(join(dir, 'rediacc'), { recursive: true });
    const entry = {
      ts: '2026-11-06T00:00:00Z',
      actor: { kind: 'human', agentSignals: [] },
      command: 'config audit probe',
      paths: [],
      outcome: 'ok',
      prevHash: '',
    };
    writeFileSync(join(dir, 'rediacc', 'audit.log.jsonl'), `${JSON.stringify(entry)}\n`);
    setOutputFormat(fmt);
    const write = vi.spyOn(process.stdout, 'write').mockReturnValue(true);
    const program = new Command();
    registerAuditCommands(program.command('config'), program);
    await program.parseAsync(['node', 'rdc', 'config', 'audit', 'log']);
    const text = write.mock.calls.map((c) => String(c[0])).join('');
    // The rendered bytes carry the entry (a table cell may be cut, so only its start is checked) but are not a JSON document.
    expect(text).toContain('config');
    expect(() => JSON.parse(text)).toThrow();
  });
});
