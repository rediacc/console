/**
 * The contract generator's refusals and outputs, driven as the real script into a scratch
 * directory. The generator is a top-level script, so the cases it can be driven into without
 * editing the command tree are tested here: the `--version` refusal, a clean run, and what the
 * clean run leaves out and puts in. The curation refusals (a missing summary, a stale safety key)
 * fire on bad tables, which need a changed tree; for those the run's outputs prove the same gates
 * passed: every command has a summary key, a bounded summary and a severity.
 */
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { SUMMARY_MAX_LENGTH } from '@rediacc/shared/cli-contract/validation';
import { isMcpLayerErrorCode } from '@rediacc/shared/mcp/errors';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { listErrorCodeOrigins } from '../types/error-origins.js';

const CLI_ROOT = path.resolve(import.meta.dirname, '..', '..');
const TSX = path.resolve(CLI_ROOT, '..', '..', 'node_modules', '.bin', 'tsx');
const SCRIPT = path.join(CLI_ROOT, 'scripts', 'generate-cli-contract.ts');

interface Contract {
  version: string;
  errorCodes: { code: string; origin: string }[];
  commands: { pathKey: string; summary: string; summaryKey: string | null; severity?: string }[];
}

function generate(args: string[]) {
  return spawnSync(TSX, [SCRIPT, ...args], { cwd: CLI_ROOT, encoding: 'utf-8', timeout: 120_000 });
}

describe('generate-cli-contract', () => {
  let out = '';
  let contract: Contract;
  let run: ReturnType<typeof generate>;

  beforeAll(() => {
    out = mkdtempSync(path.join(tmpdir(), 'cli-contract-'));
    run = generate(['--output', out]);
    contract = JSON.parse(readFileSync(path.join(out, 'contract.json'), 'utf-8')) as Contract;
  }, 120_000);

  afterAll(() => {
    if (out) rmSync(out, { recursive: true, force: true });
  });

  it('runs clean on the live command tree', () => {
    expect(run.status, run.stderr).toBe(0);
  });

  it('keeps the MCP-layer error codes out of the contract code list', () => {
    // Control: the origin list does carry such codes, so the filter has something to remove.
    const origins = listErrorCodeOrigins().map(({ code }) => code);
    const mcpLayer = origins.filter((code) => isMcpLayerErrorCode(code));
    expect(mcpLayer).toContain('POLICY_DENIED');
    const listed = new Set(contract.errorCodes.map(({ code }) => code));
    for (const code of mcpLayer) expect(listed.has(code), code).toBe(false);
    for (const code of origins.filter((c) => !isMcpLayerErrorCode(c))) {
      expect(listed.has(code), code).toBe(true);
    }
  });

  it('gives every command a summary key that resolves, a bounded summary and a severity', () => {
    expect(contract.commands.length).toBeGreaterThan(100);
    for (const command of contract.commands) {
      expect(command.summaryKey, `${command.pathKey} summaryKey`).not.toBeNull();
      expect(command.summary.trim(), `${command.pathKey} summary`).not.toBe('');
      expect([...command.summary].length, command.pathKey).toBeLessThanOrEqual(SUMMARY_MAX_LENGTH);
      expect(['none', 'caution', 'destructive'], command.pathKey).toContain(command.severity);
    }
  });

  it('versions the contract by a content hash, the same in every file it writes', () => {
    expect(contract.version).toMatch(/^[0-9a-f]{16}$/);
    for (const file of ['contract.generated.ts', 'contract-version.generated.ts']) {
      expect(readFileSync(path.join(out, file), 'utf-8')).toContain(
        `CLI_CONTRACT_VERSION = '${contract.version}'`
      );
    }
  });

  it('refuses the dropped --version flag with exit 1', () => {
    const refused = generate(['--version', '1.2.3', '--output', path.join(out, 'unused')]);
    expect(refused.status).toBe(1);
    expect(refused.stderr).toContain('--version was dropped');
  }, 120_000);
});
