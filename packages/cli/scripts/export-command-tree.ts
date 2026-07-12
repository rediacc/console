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
 * The tree walk itself lives in lib/command-tree-lib.ts, shared with
 * generate-cli-contract.ts so both read the same tree.
 *
 * Usage:
 *   npx tsx packages/cli/scripts/export-command-tree.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { cli } from '../src/cli.js';
import {
  type CommandNode,
  createDescriptionResolver,
  EXCLUDED_TOP_LEVEL,
  loadLocale,
  walkCommand,
} from './lib/command-tree-lib.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const resolver = createDescriptionResolver(loadLocale('en'));

const tree = walkCommand(cli, resolver);
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
