import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const GENERATOR = fileURLToPath(
  new URL('../../scripts/generate-skill-reference.ts', import.meta.url)
);
const CLI_DIR = fileURLToPath(new URL('../..', import.meta.url));

describe('generate-skill-reference option defaults', () => {
  it('omits the default suffix for an empty-array default', () => {
    const out = execFileSync('npx', ['tsx', GENERATOR], {
      cwd: CLI_DIR,
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    });
    expect(out).not.toContain('(default: )');
    expect(out).toContain('(default: ');
  }, 120_000);

  it('gives a command with subcommands and its own action a section beside its subcommands', () => {
    const out = execFileSync('npx', ['tsx', GENERATOR], {
      cwd: CLI_DIR,
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    });
    const headings = out.split('\n').filter((line) => line.startsWith('### rdc '));
    // `server licence <domain>` is invocable beside `server licence mint`: dropping the parent would hide its flags.
    expect(headings).toContain('### rdc server licence <domain>');
    expect(headings).toContain('### rdc server licence mint');
    // Control: a group with no action of its own (`server`, `config`) still has no section.
    expect(headings).not.toContain('### rdc server');
    expect(headings).not.toContain('### rdc config');
  }, 120_000);

  it('labels a grand-guarded command with its REDIACC_ALLOW_GRAND_REPO and ops VM exits, never the bare fork-only', () => {
    const out = execFileSync('npx', ['tsx', GENERATOR], {
      cwd: CLI_DIR,
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    });
    const lines = out.split('\n');
    const at = lines.indexOf('### rdc repo admin orphan delete <ref>');
    expect(at).toBeGreaterThan(-1);
    const label = lines.slice(at).find((line) => line.startsWith('> '));
    expect(label).toContain('REDIACC_ALLOW_GRAND_REPO');
    expect(label).toContain('ops VMs exempt');
    // Control: no annotation line is the bare label that understated what an agent can do.
    expect(lines).not.toContain('> agent: fork-only');
  }, 120_000);

  it('the committed .claude/skills/rdc/reference.md is current', () => {
    // --check exits 3 when the committed reference differs from the render, so execFileSync throws and the test fails.
    execFileSync('npx', ['tsx', GENERATOR, '--check'], {
      cwd: CLI_DIR,
      encoding: 'utf8',
      stdio: 'pipe',
    });
  }, 120_000);
});
