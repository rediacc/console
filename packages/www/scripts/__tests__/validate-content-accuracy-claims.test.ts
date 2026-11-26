import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  CLAIM_OVERSTATEMENT_ALLOWLIST,
  findClaimOverstatements,
  invokedDirectly,
  productHosts,
} from '../validate-content-accuracy.js';

type Hit = { arm: string; line: number };
const scan = (text: string, file = 'docs/en/x.md'): Hit[] => findClaimOverstatements(text, file);

describe('claim-overstatement rule', () => {
  it('refuses the "forensic trail" arm', () => {
    expect(scan('Every action leaves a forensic trail.').map((h) => h.arm)).toEqual([
      'forensic trail',
    ]);
  });

  it('refuses the "forensic-grade" arm', () => {
    expect(scan('A forensic-grade record of changes.').map((h) => h.arm)).toEqual([
      'forensic-grade',
    ]);
  });

  it('refuses hash-chained within one sentence of audit log when no scope is named', () => {
    const hits = scan('Line one.\nThe server keeps a hash-chained audit log for you.');
    expect(hits.map((h) => h.arm)).toEqual(['hash-chained audit log']);
    expect(hits[0].line).toBe(2);
  });

  it('passes hash-chained audit log when the sentence names per org or a day file', () => {
    expect(scan('The hash-chained audit log is chained per org and day.')).toEqual([]);
    expect(scan('The hash-chained audit log lives in one day file per org.')).toEqual([]);
  });

  it('passes hash-chained when audit log sits in a different sentence', () => {
    expect(scan('Batches are hash-chained. The audit log is separate.')).toEqual([]);
  });

  it('passes an allowlisted line that carries a reason', () => {
    const line = 'The local file is a hash-chained audit log.';
    const allow = [{ file: 'docs/en/x.md', includes: 'local file', reason: 'local CLI log' }];
    expect(findClaimOverstatements(line, 'docs/en/x.md', allow)).toEqual([]);
    expect(findClaimOverstatements(line, 'docs/en/x.md', [])).toHaveLength(1);
  });

  it('ignores an allowlist entry that has no reason', () => {
    const line = 'The local file is a hash-chained audit log.';
    const allow = [{ file: 'docs/en/x.md', includes: 'local file', reason: '' }];
    expect(findClaimOverstatements(line, 'docs/en/x.md', allow)).toHaveLength(1);
  });

  it('keeps a reason on every shipped allowlist entry', () => {
    for (const entry of CLAIM_OVERSTATEMENT_ALLOWLIST) {
      expect(entry.reason.length).toBeGreaterThan(10);
    }
  });
});

describe('claim-overstatement multi-line, allowlist and scope handling', () => {
  it('refuses a sentence wrapped across two physical lines', () => {
    const hits = scan('The server keeps a hash-chained\naudit log for you.');
    expect(hits.map((h) => h.arm)).toEqual(['hash-chained audit log']);
    expect(hits[0].line).toBe(1);
  });

  it('does not join sentences across a blank line', () => {
    expect(scan('Batches are hash-chained\n\naudit log is separate.')).toEqual([]);
  });

  it('keeps refusing a forensic claim on an allowlisted line', () => {
    const allow = [
      {
        file: 'docs/en/x.md',
        includes: 'workstation audit log',
        reason: 'scoped to the workstation',
      },
    ];
    const text = 'The workstation audit log is a forensic trail.';
    expect(findClaimOverstatements(text, 'docs/en/x.md', allow).map((h) => h.arm)).toEqual([
      'forensic trail',
    ]);
  });

  it('is not exempted by unrelated per organization wording', () => {
    expect(scan('Pricing is per organization and the audit log is hash-chained.')).toHaveLength(1);
  });
});

describe('productHosts', () => {
  const fixture = (regions: string, toml: string | null) => {
    const root = mkdtempSync(join(tmpdir(), 'hosts-'));
    writeFileSync(join(root, 'regions.json'), regions);
    mkdirSync(join(root, 'workers/mcp'), { recursive: true });
    if (toml !== null) writeFileSync(join(root, 'workers/mcp/wrangler.eu.toml'), toml);
    return root;
  };

  it('reads region domains and MCP route patterns', () => {
    const root = fixture(
      '{"regions":[{"domain":"eu.example.cloud"}]}',
      'routes = [{ pattern = "mcp.eu.example.cloud" }]'
    );
    try {
      expect(productHosts(root)).toEqual(['eu.example.cloud', 'mcp.eu.example.cloud']);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it('throws when the MCP patterns or the region domains vanish', () => {
    const noMcp = fixture('{"regions":[{"domain":"eu.example.cloud"}]}', 'name = "x"');
    const noRegions = fixture('{"regions":[]}', 'pattern = "a.example.cloud"');
    try {
      expect(() => productHosts(noMcp)).toThrow(/route patterns/);
      expect(() => productHosts(noRegions)).toThrow(/region domains/);
    } finally {
      rmSync(noMcp, { recursive: true, force: true });
      rmSync(noRegions, { recursive: true, force: true });
    }
  });

  it('resolves the tracked deploy config to non-empty hosts', () => {
    expect(productHosts().length).toBeGreaterThan(1);
  });
});

describe('invokedDirectly', () => {
  const script = fileURLToPath(new URL('../validate-content-accuracy.js', import.meta.url));

  it('is true for a symlinked start and false without argv[1]', () => {
    const dir = mkdtempSync(join(tmpdir(), 'vca-'));
    try {
      const link = join(dir, 'link.js');
      symlinkSync(script, link);
      expect(invokedDirectly(link)).toBe(true);
      expect(invokedDirectly('')).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it('throws on an unresolvable path instead of returning false', () => {
    expect(() => invokedDirectly('/nonexistent/vca.js')).toThrow();
  });

  it('runs main() through a symlink and exits non-zero on bad input path', () => {
    const dir = mkdtempSync(join(tmpdir(), 'vca-'));
    try {
      const link = join(dir, 'link.js');
      symlinkSync(script, link);
      const run = spawnSync(process.execPath, [link], { encoding: 'utf8' });
      expect(run.stdout + run.stderr).not.toBe('');
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
