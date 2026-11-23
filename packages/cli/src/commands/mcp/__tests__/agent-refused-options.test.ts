/**
 * An MCP tool must not advertise an option the CLI refuses to an agent.
 *
 * Every `isAgentEnvironment()` call site under src/commands is classified below as refusing named
 * options of named commands, or as refusing none with the reason. An unclassified site fails the
 * scan, and a refused option that a built tool schema still carries fails the schema check.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { buildAllTools } from '../tools.js';

const COMMANDS_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

interface Refusal {
  /** Command path whose MCP tool, if any, must not carry the option. */
  command: string;
  /** Long option name without dashes. */
  option: string;
}

interface Site {
  /** Number of `isAgentEnvironment` references in the file, import lines excluded. */
  sites: number;
  refuses: Refusal[];
  /** Required when `refuses` is empty. */
  none?: string;
}

const CLASSIFIED: Record<string, Site> = {
  'config.ts': { sites: 1, refuses: [{ command: 'config show', option: 'reveal' }] },
  'config/field.ts': { sites: 1, refuses: [{ command: 'config field get', option: 'reveal' }] },
  'config/edit.ts': {
    sites: 1,
    refuses: [
      { command: 'config edit', option: 'reveal' },
      { command: 'config edit', option: 'apply' },
    ],
  },
  'repo-permission.ts': {
    sites: 2,
    refuses: [
      { command: 'repo permission grant', option: 'root' },
      { command: 'repo permission grant', option: 'path' },
    ],
  },
  'repo-prune.ts': { sites: 1, refuses: [{ command: 'repo prune', option: 'offline' }] },
  'repo-policy.ts': {
    sites: 1,
    refuses: [],
    none: 'refuses a limits change on a grand repository by repo identity, not by an option',
  },
  'repo.ts': { sites: 1, refuses: [], none: 'hides the help tree from agents, no option' },
  'machine/index.ts': { sites: 1, refuses: [], none: 'hides the help tree from agents, no option' },
  'term.ts': {
    sites: 2,
    refuses: [],
    none: 'refuses command text (direct renet, file writes) given to term connect, no option',
  },
  'feedback.ts': {
    sites: 1,
    refuses: [],
    none: 'an agent without --yes gets a preview; --yes is a global the tools never expose',
  },
};

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (name === '__tests__' || name === 'node_modules') continue;
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (name.endsWith('.ts')) out.push(full);
  }
  return out;
}

/** References in code, with import lines and comment lines left out. */
function countSites(text: string): number {
  return text.split('\n').filter((line) => {
    const trimmed = line.trim();
    if (!trimmed.includes('isAgentEnvironment')) return false;
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) {
      return false;
    }
    if (/\bimport\b/.test(trimmed) || /^isAgentEnvironment,?$/.test(trimmed)) return false;
    return true;
  }).length;
}

function scan(): Record<string, number> {
  const found: Record<string, number> = {};
  for (const file of sourceFiles(COMMANDS_DIR)) {
    const n = countSites(readFileSync(file, 'utf8'));
    if (n > 0) found[relative(COMMANDS_DIR, file)] = n;
  }
  return found;
}

describe('agent-refused options', () => {
  it('classifies every isAgentEnvironment call site under src/commands', () => {
    const counts = Object.fromEntries(Object.entries(CLASSIFIED).map(([f, s]) => [f, s.sites]));
    expect(scan()).toEqual(counts);
  });

  it('gives every site that refuses no option a reason', () => {
    for (const [file, site] of Object.entries(CLASSIFIED)) {
      if (site.refuses.length === 0) expect(site.none, file).toBeTruthy();
    }
  });

  it('counts references the way the scan expects (control)', () => {
    expect(countSites("import { isAgentEnvironment } from 'x';\n// isAgentEnvironment\n")).toBe(0);
    expect(countSites('  if (isAgentEnvironment()) {\n  agent: isAgentEnvironment,\n')).toBe(2);
  });

  it('exposes no refused option in any MCP tool schema', () => {
    const tools = new Map(buildAllTools().map((tool) => [tool.name, tool]));
    for (const site of Object.values(CLASSIFIED)) {
      for (const { command, option } of site.refuses) {
        const tool = tools.get(command.replaceAll(' ', '_'));
        if (!tool) continue;
        expect(Object.keys(tool.schema), `${command} advertises --${option}`).not.toContain(option);
      }
    }
  });

  it('keeps config_show a tool without reveal (control: the check sees the tool)', () => {
    const tool = buildAllTools().find((t) => t.name === 'config_show');
    expect(tool).toBeDefined();
    expect(Object.keys(tool?.schema ?? {})).not.toContain('reveal');
  });
});
