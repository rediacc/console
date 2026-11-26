/**
 * Review 1121-1 2b807c97.2: an `excludeOptions` entry that names no option of its command is dead
 * configuration that reads as a refusal. Every entry must name a long option the command's
 * Commander registration carries (hidden options included, which the contract leaves out), and
 * the check reports one that does not.
 */
import type { Command } from 'commander';
import { describe, expect, it } from 'vitest';
import { createCli } from '../../cli.js';
import { COMMAND_METADATA } from '../command-metadata.js';

interface Entry {
  command: string;
  option: string;
}

/** Every `excludeOptions` entry whose option the command's contract entry does not carry. */
function deadExclusions(
  metadata: Record<string, { mcp?: { excludeOptions?: readonly string[] } }>,
  longOptionsOf: (command: string) => ReadonlySet<string> | undefined
): Entry[] {
  const dead: Entry[] = [];
  for (const [command, meta] of Object.entries(metadata)) {
    for (const option of meta.mcp?.excludeOptions ?? []) {
      if (!longOptionsOf(command)?.has(option)) dead.push({ command, option });
    }
  }
  return dead;
}

/** The long option names of every registered command, by space-joined path. */
function registeredOptions(): Map<string, ReadonlySet<string>> {
  const found = new Map<string, ReadonlySet<string>>();
  const walk = (command: Command, path: string[]) => {
    if (path.length > 0) {
      const longs = command.options.flatMap((o) => (o.long ? [o.long.replace(/^--/, '')] : []));
      found.set(path.join(' '), new Set(longs));
    }
    for (const child of command.commands) walk(child, [...path, child.name()]);
  };
  walk(createCli(), []);
  return found;
}

const LIVE = registeredOptions();

describe('excludeOptions in the command metadata', () => {
  it('names only options its command carries', () => {
    expect(deadExclusions(COMMAND_METADATA, (command) => LIVE.get(command))).toEqual([]);
  });

  it('control: the check reports an exclusion the command does not carry', () => {
    const metadata = { 'config current': { mcp: { excludeOptions: ['reveal'] } } };
    expect(deadExclusions(metadata, (command) => LIVE.get(command))).toEqual([
      { command: 'config current', option: 'reveal' },
    ]);
  });

  it('control: a real exclusion passes', () => {
    const metadata = { 'config show': { mcp: { excludeOptions: ['reveal'] } } };
    expect(deadExclusions(metadata, (command) => LIVE.get(command))).toEqual([]);
  });
});
