/**
 * Completion over the real generated contract (D2 of
 * agent/plans/PLAN-console-command-line.md).
 */
import { describe, expect, it } from 'vitest';
import { CLI_CONTRACT } from '../../cli-contract/index.js';
import { complete, matchRank } from '../complete.js';
import { analyze, type CommandLineEnv, type ResourceSource } from '../state.js';

const names: ResourceSource = (kind, ctx) => {
  if (kind === 'repo') return ctx.machine === 'prod-1' ? ['shop'] : ['shop', 'shop:test', 'mail'];
  if (kind === 'machine') return ['prod-1', 'prod-2'];
  return [];
};
const locked: ResourceSource = () => 'locked';

function env(source: ResourceSource): CommandLineEnv {
  return { contract: CLI_CONTRACT, source };
}

/** Complete at the end of `line`, or at the `|` marker when the line carries one. */
function at(line: string, source: ResourceSource = names) {
  const cursor = line.includes('|') ? line.indexOf('|') : line.length;
  const text = line.replace('|', '');
  return complete(analyze(env(source), text), cursor);
}

const labels = (line: string, source?: ResourceSource): string[] =>
  at(line, source).map((s) => s.label);

describe('matchRank', () => {
  it('ranks prefix before subsequence and rejects a miss', () => {
    expect(matchRank('repo', 're')).toBe(0);
    expect(matchRank('preview', 're')).toBe(1);
    expect(matchRank('machine', 're')).toBe(-1);
    expect(matchRank('anything', '')).toBe(0);
    expect(matchRank('REPO', 're')).toBe(0);
  });
});

describe('complete: command path', () => {
  it('offers rdc on an empty line and for a prefix of it', () => {
    expect(labels('')).toEqual(['rdc']);
    expect(labels('rd')).toEqual(['rdc']);
    expect(labels('xyz')).toEqual([]);
  });

  it('offers domains after rdc, in contract order', () => {
    const rows = at('rdc ');
    expect(rows[0].label).toBe('backup');
    expect(rows.find((r) => r.label === 'repo')?.kind).toBe('domain');
    expect(rows.find((r) => r.label === 'doctor')?.kind).toBe('command');
  });

  it('`rdc re` suggests repo first, a prefix match ahead of a subsequence match', () => {
    const rows = at('rdc re');
    expect(rows[0].label).toBe('repo');
    expect(rows.map((r) => r.label)).toContain('preview');
    expect(rows.map((r) => r.label).indexOf('preview')).toBeGreaterThan(0);
    expect(rows[0]).toMatchObject({ insert: 'repo ', start: 4, end: 6 });
  });

  it('lists subcommands with their summary, severity and blocked reason', () => {
    const rows = at('rdc repo ');
    const fork = rows.find((r) => r.label === 'fork');
    expect(fork?.kind).toBe('command');
    expect(fork?.summary).toBeTruthy();
    expect(fork?.severity).toBeDefined();
    const group = rows.find((r) => r.label === 'admin');
    expect(group?.summary).toBeUndefined();
  });

  it('carries the blocked reason of a command the console cannot run', () => {
    const blocked = CLI_CONTRACT.commands.find((c) => !c.proxyCapable && c.path.length === 2);
    if (!blocked) throw new Error('contract has no two-word command that is not proxy-capable');
    const row = at(`rdc ${blocked.path[0]} `).find((r) => r.label === blocked.path[1]);
    expect(row?.blockedReason).toBe(blocked.proxyBlockedReason);
  });

  it('offers nothing after an unknown domain', () => {
    expect(at('rdc nonsense ')).toEqual([]);
  });

  it('replaces the whole token under the cursor', () => {
    const rows = at('rdc re|po fork');
    expect(rows[0]).toMatchObject({ label: 'repo', start: 4, end: 8 });
  });
});

describe('complete: command arguments', () => {
  it('`rdc repo fork ` lists the required positional ahead of the flags', () => {
    const rows = at('rdc repo fork ');
    const firstFlag = rows.findIndex((r) => r.kind === 'flag');
    expect(rows[0]).toMatchObject({ kind: 'value', label: 'shop', required: true });
    expect(rows.slice(0, firstFlag).every((r) => r.kind === 'value')).toBe(true);
    expect(firstFlag).toBeGreaterThan(0);
  });

  it('shows an inert placeholder for a required positional that names no resource', () => {
    const rows = at('rdc repo create ');
    expect(rows[0]).toMatchObject({ kind: 'positional', label: '<name>', inert: true });
    expect(rows[1].kind).toBe('flag');
  });

  it('lists mandatory and common flags before advanced ones', () => {
    const flags = at('rdc repo fork shop ').filter((r) => r.kind === 'flag');
    expect(flags[0]).toMatchObject({ label: '--tag', required: true });
    expect(flags.map((r) => r.label).indexOf('--checkpoint')).toBeGreaterThan(0);
  });

  it('omits a flag already given but keeps a variadic one', () => {
    const rows = labels('rdc repo fork shop --tag t1 ');
    expect(rows).not.toContain('--tag');
    expect(rows).toContain('--checkpoint');
  });

  it('filters flags by the typed prefix and offers every flag for `--`', () => {
    expect(labels('rdc repo fork shop --ch')).toEqual(['--checkpoint']);
    expect(labels('rdc repo fork shop --').length).toBe(
      CLI_CONTRACT.commands.find((c) => c.pathKey === 'repo fork')?.options.length
    );
  });

  it('offers no flag while a positional value is being typed', () => {
    expect(at('rdc repo fork sh').every((r) => r.kind !== 'flag')).toBe(true);
    expect(labels('rdc repo fork sh')).toEqual(['shop', 'shop:test']);
  });

  it('lists choices of a value-taking flag before resource names, from `--flag ` and `--flag=`', () => {
    expect(labels('rdc backup strategy set s --mode ')).toEqual(['hot', 'cold']);
    expect(labels('rdc backup strategy set s --mode c')).toEqual(['cold']);
    const eq = at('rdc backup strategy set s --mode=c');
    const line = 'rdc backup strategy set s --mode=c';
    expect(eq[0]).toMatchObject({ label: 'cold', start: line.indexOf('=') + 1, end: line.length });
    expect(eq[0].insert).toBe('cold ');
  });

  it('lists resource names for a flag bound to a kind', () => {
    expect(labels('rdc backup schedule --machine ')).toEqual(['prod-1', 'prod-2']);
  });

  it('narrows a source by what the line already names', () => {
    expect(labels('rdc repo down --machine prod-1 ').filter((l) => !l.startsWith('-'))).toEqual([
      'shop',
    ]);
    expect(labels('rdc repo down ')).toContain('mail');
  });

  it('quotes a value that needs it', () => {
    const rows = at('rdc repo fork ', () => ['my repo']);
    expect(rows[0].insert).toBe(`'my repo' `);
  });

  it('quotes a leading dash so an accepted row stays a value (review e20b39e7.1)', () => {
    const rows = at('rdc repo fork ', () => ['-x', 'plain']);
    expect(rows.find((r) => r.label === '-x')?.insert).toBe(`'-x' `);
    expect(rows.find((r) => r.label === 'plain')?.insert).toBe('plain ');
  });

  it('a locked source yields exactly the one inert unlock row for a value slot', () => {
    const rows = at('rdc repo fork ', locked);
    const unlock = rows.filter((r) => r.kind === 'unlock');
    expect(unlock).toHaveLength(1);
    expect(unlock[0]).toMatchObject({
      label: 'Unlock to suggest',
      labelKey: 'commandLine.unlock',
      inert: true,
      insert: '',
    });
    expect(rows[0]).toBe(unlock[0]);
    expect(rows.some((r) => r.kind === 'value')).toBe(false);
  });

  it('control: a locked source does not touch rows that need no resource', () => {
    expect(at('rdc repo ', locked).some((r) => r.kind === 'unlock')).toBe(false);
    expect(at('rdc backup strategy set s --mode ', locked).map((r) => r.label)).toEqual([
      'hot',
      'cold',
    ]);
  });

  it('offers nothing after a bare `--`', () => {
    expect(at('rdc repo exec shop -- ')).toEqual([]);
  });

  it('keeps offering the command flags after one it does not declare', () => {
    const rows = labels('rdc repo fork shop --bogus ');
    expect(rows).toContain('--tag');
    expect(rows).not.toContain('--bogus');
  });
});

describe('complete: cost', () => {
  it('stays under 1 ms per call on the real contract', () => {
    const lines = ['rdc ', 'rdc re', 'rdc repo fork ', 'rdc repo fork shop --', 'rdc backup sch'];
    const runs = 300;
    const start = performance.now();
    for (let i = 0; i < runs; i++) {
      for (const line of lines) complete(analyze(env(names), line), line.length);
    }
    const perCall = (performance.now() - start) / (runs * lines.length);
    expect(perCall).toBeLessThan(1);
  });
});
