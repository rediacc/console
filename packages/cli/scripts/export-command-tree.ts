#!/usr/bin/env tsx
/**
 * Commander.js Command Tree Exporter
 *
 * Introspects the live Commander.js command tree and exports a JSON representation
 * containing all commands, their options, arguments, and i18n description keys.
 *
 * This JSON is consumed by generate-cli-docs.js to enrich the generated documentation
 * with options tables, argument syntax, and default values.
 *
 * Usage:
 *   npx tsx packages/cli/scripts/export-command-tree.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Command, Option, Argument } from 'commander';
import { cli } from '../src/cli.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const cliJsonPath = path.resolve(__dirname, '../src/i18n/locales/en/cli.json');
const cliJson: Record<string, unknown> = JSON.parse(fs.readFileSync(cliJsonPath, 'utf-8'));

// ---------- Types ----------

interface CommandNode {
  name: string;
  descriptionKey: string | null;
  options: OptionNode[];
  arguments: ArgumentNode[];
  subcommands: CommandNode[];
}

interface OptionNode {
  flags: string;
  descriptionKey: string | null;
  mandatory: boolean;
  defaultValue: string | null;
}

interface ArgumentNode {
  name: string;
  required: boolean;
  variadic: boolean;
  defaultValue: string | null;
}

// ---------- Reverse i18n lookup ----------

/**
 * Flatten a nested object into a Map of dot-separated keys to string values.
 */
function flattenObject(obj: Record<string, unknown>, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  const recurse = (currentObj: Record<string, unknown>, p: string): void => {
    for (const [key, value] of Object.entries(currentObj)) {
      const fullKey = p ? `${p}.${key}` : key;
      if (typeof value === 'string') {
        result.set(fullKey, value);
      } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        recurse(value as Record<string, unknown>, fullKey);
      }
    }
  };
  recurse(obj, prefix);
  return result;
}

interface InterpolatedEntry {
  pattern: RegExp;
  key: string;
}

/**
 * Build a reverse lookup from English description strings to their i18n key paths.
 * Handles both exact matches and interpolated templates (containing {{...}}).
 */
function buildReverseLookup(): { exact: Map<string, string>; interpolated: InterpolatedEntry[] } {
  const exact = new Map<string, string>();
  const interpolated: InterpolatedEntry[] = [];

  function collectNamespace(namespace: string): void {
    const nsData = (cliJson as Record<string, unknown>)[namespace];
    if (!nsData || typeof nsData !== 'object') return;
    const flat = flattenObject(nsData as Record<string, unknown>, namespace);
    for (const [key, value] of flat) {
      if (value.includes('{{')) {
        const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const pattern = new RegExp('^' + escaped.replace(/\\\{\\\{.*?\\\}\\\}/g, '.*') + '$');
        interpolated.push({ pattern, key });
      } else {
        if (!exact.has(value)) exact.set(value, key);
      }
    }
  }

  collectNamespace('options');
  collectNamespace('commands');
  return { exact, interpolated };
}

const reverseLookup = buildReverseLookup();

/**
 * Find the i18n key for a given English description string.
 */
function findDescriptionKey(description: string): string | null {
  const exactKey = reverseLookup.exact.get(description);
  if (exactKey) return exactKey;
  for (const { pattern, key } of reverseLookup.interpolated) {
    if (pattern.test(description)) return key;
  }
  return null;
}

// ---------- Extraction helpers ----------

function serialiseDefault(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value === 'function') return null;
  if (Array.isArray(value) && value.length === 0) return null;
  return String(value);
}

function extractOption(opt: Option): OptionNode {
  return {
    flags: opt.flags,
    descriptionKey: findDescriptionKey(opt.description),
    mandatory: opt.mandatory ?? false,
    defaultValue: serialiseDefault(opt.defaultValue),
  };
}

function extractArgument(arg: Argument): ArgumentNode {
  return {
    name: arg.name(),
    required: arg.required,
    variadic: arg.variadic,
    defaultValue: serialiseDefault(arg.defaultValue),
  };
}

// ---------- Tree walker ----------

/** Global options that appear on every command and should be excluded from per-command tables. */
const GLOBAL_OPTION_LONGS = new Set(['--output', '--context', '--lang', '--version', '--help']);

/** Top-level shortcut aliases that duplicate real commands — excluded from the tree. */
const EXCLUDED_TOP_LEVEL = new Set(['login', 'logout', 'run', 'trace', 'cancel', 'retry']);

function walkCommand(cmd: Command): CommandNode | null {
  const name = cmd.name();
  if (name === 'help') return null;

  const rawDesc = cmd.description();
  const descriptionKey = rawDesc ? findDescriptionKey(rawDesc) : null;

  const options: OptionNode[] = [];
  for (const opt of cmd.options) {
    if (GLOBAL_OPTION_LONGS.has(opt.long ?? '')) continue;
    options.push(extractOption(opt));
  }

  const args: ArgumentNode[] = cmd.registeredArguments.map(extractArgument);

  const subcommands: CommandNode[] = [];
  for (const sub of cmd.commands) {
    const node = walkCommand(sub);
    if (node) subcommands.push(node);
  }

  return { name, descriptionKey, options, arguments: args, subcommands };
}

// ---------- Main ----------

const tree = walkCommand(cli);
if (tree === null) {
  console.error('\x1b[31mError: Could not generate command tree.\x1b[0m');
  process.exit(1);
}

// Filter out top-level shortcut aliases
tree.subcommands = tree.subcommands.filter((sub) => !EXCLUDED_TOP_LEVEL.has(sub.name));

const outputPath = path.resolve(__dirname, 'command-tree.json');
fs.writeFileSync(outputPath, JSON.stringify(tree, null, 2) + '\n', 'utf-8');
console.log(`\x1b[32m✓\x1b[0m Wrote ${outputPath}`);
console.log(`  Commands: ${countCommands(tree)}`);
console.log(`  Options:  ${countOptions(tree)}`);

function countCommands(node: CommandNode): number {
  let count = node.subcommands.length;
  for (const sub of node.subcommands) count += countCommands(sub);
  return count;
}

function countOptions(node: CommandNode): number {
  let count = node.options.length;
  for (const sub of node.subcommands) count += countOptions(sub);
  return count;
}
