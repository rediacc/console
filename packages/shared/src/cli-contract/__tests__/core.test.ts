/**
 * The lazy contract entry (D6 of agent/plans/PLAN-console-contract-semantics.md):
 * `./core` indexes a contract it is handed and never imports the data, `./load`
 * reaches the data only through a dynamic import, and the root entry keeps its
 * synchronous lookups over the bundled contract.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { indexContract } from '../core.js';
import { CLI_CONTRACT } from '../data/contract.generated.js';
import {
  commandsByDomain,
  commandsForContext,
  getCommand,
  proxyCapableCommands,
} from '../index.js';
import { loadCliContract } from '../load.js';
import type { CliContract, ContractCommand } from '../types.js';

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf-8');
}

/** Every module specifier a source file names, static or dynamic, with how it is named. */
function specifiers(text: string): { spec: string; dynamic: boolean }[] {
  const found: { spec: string; dynamic: boolean }[] = [];
  for (const m of text.matchAll(/^\s*(?:import|export)\b[^;]*?\bfrom\s+['"]([^'"]+)['"]/gms)) {
    found.push({ spec: m[1], dynamic: false });
  }
  for (const m of text.matchAll(/^\s*import\s+['"]([^'"]+)['"]/gm)) {
    found.push({ spec: m[1], dynamic: false });
  }
  for (const m of text.matchAll(/\bimport\(\s*['"]([^'"]+)['"]\s*\)/g)) {
    found.push({ spec: m[1], dynamic: true });
  }
  return found;
}

const DATA = /(^|\/)data\/contract\.generated(\.js)?$/;

function entry(pathKey: string, extra: Partial<ContractCommand> = {}): ContractCommand {
  const path = pathKey.split(' ');
  return {
    path,
    pathKey,
    domain: path[0],
    group: null,
    plane: 'machine',
    descriptionKey: null,
    label: pathKey,
    summaryKey: null,
    summary: pathKey,
    severity: 'none',
    options: [],
    positionals: [],
    hasSubcommands: false,
    interactive: false,
    proxyCapable: false,
    proxyBlockedReason: 'test',
    detachable: false,
    machineOption: null,
    repoOption: null,
    machinePositional: null,
    repoPositional: null,
    ...extra,
  };
}

const FIXTURE: CliContract = {
  version: 'test',
  languages: ['en'],
  errorCodes: [],
  commands: [
    entry('repo up', {
      repoPositional: 'ref',
      machineOption: 'machine',
      proxyCapable: true,
      proxyBlockedReason: undefined,
      detachable: true,
    }),
    entry('repo list', { machineOption: 'machine' }),
    entry('machine info', { machinePositional: 'machine' }),
    entry('config show'),
  ],
};

describe('specifier scan (control)', () => {
  it('sees static, re-export, side-effect and dynamic imports of the data', () => {
    const planted = [
      "import { CLI_CONTRACT } from './data/contract.generated.js';",
      "export { CLI_CONTRACT_VERSION } from './data/contract.generated.js';",
      "import './data/contract.generated.js';",
      "const m = await import('./data/contract.generated.js');",
    ].join('\n');
    const hits = specifiers(planted).filter((s) => DATA.test(s.spec));
    expect(hits.map((h) => h.dynamic)).toEqual([false, false, false, true]);
  });

  it('sees the data import in the root entry', () => {
    expect(specifiers(source('../index.ts')).some((s) => DATA.test(s.spec))).toBe(true);
  });
});

describe('core.ts', () => {
  it('imports nothing from data/contract.generated', () => {
    const text = source('../core.ts');
    expect(specifiers(text).length).toBeGreaterThan(0);
    expect(specifiers(text).filter((s) => DATA.test(s.spec))).toEqual([]);
  });

  it('imports only types, so a bundle pulls no other module through it', () => {
    const lines = source('../core.ts')
      .split('\n')
      .filter((l) => /^\s*import\b/.test(l));
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.filter((l) => !/^\s*import\s+type\b/.test(l))).toEqual([]);
  });

  it('looks a command up by path key', () => {
    const index = indexContract(FIXTURE);
    expect(index.getCommand('repo up')?.pathKey).toBe('repo up');
    expect(index.getCommand('repo down')).toBeUndefined();
  });

  it('groups by domain in contract order', () => {
    const grouped = indexContract(FIXTURE).commandsByDomain();
    expect([...grouped.keys()]).toEqual(['repo', 'machine', 'config']);
    expect(grouped.get('repo')?.map((c) => c.pathKey)).toEqual(['repo up', 'repo list']);
  });

  it('filters by a flag or positional binding, and returns all with no context', () => {
    const index = indexContract(FIXTURE);
    expect(index.commandsForContext({}).length).toBe(4);
    expect(index.commandsForContext({ machine: true }).map((c) => c.pathKey)).toEqual([
      'repo up',
      'repo list',
      'machine info',
    ]);
    expect(index.commandsForContext({ repo: true }).map((c) => c.pathKey)).toEqual(['repo up']);
    expect(index.commandsForContext({ machine: true, repo: true }).map((c) => c.pathKey)).toEqual([
      'repo up',
    ]);
  });

  it('lists the proxyable commands', () => {
    expect(
      indexContract(FIXTURE)
        .proxyCapableCommands()
        .map((c) => c.pathKey)
    ).toEqual(['repo up']);
  });
});

describe('load.ts', () => {
  it('reaches the data only through a dynamic import', () => {
    const hits = specifiers(source('../load.ts')).filter((s) => DATA.test(s.spec));
    expect(hits).toEqual([{ spec: './data/contract.generated.js', dynamic: true }]);
  });

  it('resolves to the bundled contract, the same object on every call', async () => {
    const first = await loadCliContract();
    expect(first).toBe(CLI_CONTRACT);
    expect(await loadCliContract()).toBe(first);
  });
});

describe('root entry', () => {
  it('answers like an index over the bundled contract', () => {
    const index = indexContract(CLI_CONTRACT);
    const key = CLI_CONTRACT.commands[0].pathKey;
    expect(getCommand(key)).toBe(index.getCommand(key));
    expect([...commandsByDomain().keys()]).toEqual([...index.commandsByDomain().keys()]);
    expect(commandsForContext({ repo: true })).toEqual(index.commandsForContext({ repo: true }));
    expect(proxyCapableCommands()).toEqual(index.proxyCapableCommands());
  });
});
