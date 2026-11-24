/**
 * Command Safety Coverage (CS2)
 *
 * The severity and preview table must cover exactly the live contract
 * commands, never declare an MCP-destructive command harmless, and classify
 * every command that takes --dry-run or --apply. The check functions take the
 * tables as arguments so a control fixture can turn each one red.
 */
import { describe, expect, it } from 'vitest';
import {
  createDescriptionResolver,
  loadLocale,
  walkContractCommands,
} from '../../../scripts/lib/command-tree-lib.js';
import { cli } from '../../cli.js';
import { COMMAND_METADATA } from '../command-metadata.js';
import {
  COMMAND_PREVIEW,
  COMMAND_SEVERITY,
  type CommandPreview,
  type CommandSeverity,
  NOT_PREVIEW,
} from '../command-safety.js';

interface Cmd {
  pathKey: string;
  longs: string[];
}

const resolver = createDescriptionResolver(loadLocale('en'));
const COMMANDS: Cmd[] = walkContractCommands(cli, resolver).map((c) => ({
  pathKey: c.pathKey,
  longs: c.options.flatMap((o) => (/--([a-z0-9-]+)/.exec(o.flags)?.[1] ?? []) as string[]),
}));
const MCP_DESTRUCTIVE = new Set(
  Object.entries(COMMAND_METADATA)
    .filter(([, m]) => m.mcp?.destructive)
    .map(([k]) => k)
);

type Sev = Readonly<Record<string, CommandSeverity>>;
type Prev = Readonly<Record<string, CommandPreview>>;
type NotPrev = Readonly<Record<string, string>>;

const missingSeverity = (cmds: Cmd[], sev: Sev): string[] =>
  cmds.filter((c) => !(c.pathKey in sev)).map((c) => c.pathKey);

const staleKeys = (cmds: Cmd[], table: Readonly<Record<string, unknown>>): string[] => {
  const live = new Set(cmds.map((c) => c.pathKey));
  return Object.keys(table).filter((k) => !live.has(k));
};

const destructiveAtNone = (mcp: Set<string>, sev: Sev): string[] =>
  [...mcp].filter((k) => sev[k] === 'none');

const unclassifiedPreview = (cmds: Cmd[], prev: Prev, notPrev: NotPrev): string[] =>
  cmds
    .filter((c) => c.longs.includes('dry-run') || c.longs.includes('apply'))
    .filter((c) => !(c.pathKey in prev) && !(c.pathKey in notPrev))
    .map((c) => c.pathKey);

const badPreviewFlags = (cmds: Cmd[], prev: Prev): string[] =>
  Object.entries(prev)
    .filter(([k, p]) => !cmds.find((c) => c.pathKey === k)?.longs.includes(p.flag))
    .map(([k]) => k);

describe('command safety table', () => {
  it('walks 230 commands', () => {
    expect(COMMANDS.length).toBe(230);
  });

  it('has a severity for every command, and the check names a missing one', () => {
    expect(missingSeverity(COMMANDS, COMMAND_SEVERITY)).toEqual([]);
    const { 'repo list': _drop, ...without } = COMMAND_SEVERITY;
    expect(missingSeverity(COMMANDS, without)).toEqual(['repo list']);
  });

  it('has no stale key in any table, and the check names one', () => {
    expect(staleKeys(COMMANDS, COMMAND_SEVERITY)).toEqual([]);
    expect(staleKeys(COMMANDS, COMMAND_PREVIEW)).toEqual([]);
    expect(staleKeys(COMMANDS, NOT_PREVIEW)).toEqual([]);
    expect(staleKeys(COMMANDS, { ...COMMAND_SEVERITY, 'no such cmd': 'none' })).toEqual([
      'no such cmd',
    ]);
  });

  it('declares no MCP-destructive command at none, and the check names one', () => {
    expect(MCP_DESTRUCTIVE.size).toBeGreaterThan(0);
    expect(destructiveAtNone(MCP_DESTRUCTIVE, COMMAND_SEVERITY)).toEqual([]);
    expect(
      destructiveAtNone(MCP_DESTRUCTIVE, { ...COMMAND_SEVERITY, 'repo delete': 'none' })
    ).toEqual(['repo delete']);
  });

  it('declares repo prune destructive with polarity default on --apply', () => {
    expect(COMMAND_SEVERITY['repo prune']).toBe('destructive');
    expect(COMMAND_PREVIEW['repo prune']).toEqual({ flag: 'apply', polarity: 'default' });
    expect(COMMAND_PREVIEW['repo gc']).toEqual({ flag: 'apply', polarity: 'default' });
  });

  it('previews every --dry-run command: 23 opt-in rows plus repo gc and repo prune', () => {
    expect(Object.keys(COMMAND_PREVIEW).length).toBe(25);
    const dry = COMMANDS.filter((c) => c.longs.includes('dry-run'));
    expect(dry.length).toBe(23);
    for (const c of dry) {
      expect(COMMAND_PREVIEW[c.pathKey]).toEqual({ flag: 'dry-run', polarity: 'opt-in' });
    }
  });

  it('classifies every --dry-run/--apply command, and the check names an unclassified one', () => {
    expect(unclassifiedPreview(COMMANDS, COMMAND_PREVIEW, NOT_PREVIEW)).toEqual([]);
    const { 'repo gc': _gc, ...withoutGc } = COMMAND_PREVIEW;
    expect(unclassifiedPreview(COMMANDS, withoutGc, NOT_PREVIEW)).toEqual(['repo gc']);
    expect(Object.keys(NOT_PREVIEW)).toEqual(['config edit']);
    expect(NOT_PREVIEW['config edit'].length).toBeGreaterThan(0);
  });

  it('names a real option as every preview flag, and the check names a bad one', () => {
    expect(badPreviewFlags(COMMANDS, COMMAND_PREVIEW)).toEqual([]);
    expect(
      badPreviewFlags(COMMANDS, {
        ...COMMAND_PREVIEW,
        'repo list': { flag: 'dry-run', polarity: 'opt-in' },
      })
    ).toEqual(['repo list']);
  });
});
