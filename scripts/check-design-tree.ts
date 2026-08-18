#!/usr/bin/env tsx
/**
 * docs/design/06-cli-reshape.md §1 must be a TRANSCRIPT of the shipped CLI, not a
 * memory of what someone meant to build.
 *
 * A design doc that describes a tree the code no longer has is worse than no doc:
 * the next reader trusts it, and every one of the five per-leaf classification
 * systems (plane, MCP, guardrails, policy globs, ref bindings) is keyed by the
 * exact command path it gets wrong. The whole P4 phase found bug after bug hiding
 * behind a claim nothing could falsify, so this claim gets a check.
 *
 * Both directions:
 *   - every leaf the doc draws must exist in the CLI (no phantoms);
 *   - every leaf the CLI has must appear in the doc (no omissions — that is how
 *     `machine infra *` sat unlisted for a whole phase).
 *
 * Usage:
 *   npx tsx scripts/check-design-tree.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DOC = path.join(ROOT, 'docs/design/06-cli-reshape.md');
const TREE = path.join(ROOT, 'packages/cli/scripts/command-tree.json');

/** Commands deliberately held out of the contract, and out of the doc's tree. */
const HELD_OUT = new Set(['run']);

interface TreeNode {
  name?: string;
  arguments?: unknown[];
  subcommands?: TreeNode[];
}

// ---------- The CLI's leaves ----------

function cliLeaves(): Set<string> {
  const tree: TreeNode = JSON.parse(fs.readFileSync(TREE, 'utf-8'));
  const leaves = new Set<string>();

  const walk = (node: TreeNode, parts: string[]): void => {
    const subs = (node.subcommands ?? []).filter((s) => s.name && s.name !== 'help');
    if (parts.length > 0 && subs.length === 0) {
      leaves.add(parts.join(' '));
      return;
    }
    for (const sub of subs) walk(sub, [...parts, sub.name as string]);
  };

  walk(tree, []);
  return new Set([...leaves].filter((leaf) => !HELD_OUT.has(leaf.split(' ')[0])));
}

// ---------- The doc's leaves ----------

/**
 * Expand the §1 notation into leaves.
 *
 * The grammar, which nests:
 *   items  := item*
 *   item   := WORD group?          // a WORD with no group is a leaf
 *   group  := '{' items '}'        // the WORD before it is a prefix for every item
 *
 * So `admin {validate autostart {enable disable}}` yields `admin validate`,
 * `admin autostart enable`, `admin autostart disable`. A `<positional>` is skipped:
 * it names an argument, not a subcommand.
 */
function expand(tokens: string[], at: number, prefix: string[], out: Set<string>): number {
  let i = at;

  while (i < tokens.length) {
    const token = tokens[i];

    if (token === '}') return i + 1;

    if (token === '{') {
      // A brace with no word before it (a continuation line began with one).
      i = expand(tokens, i + 1, prefix, out);
      continue;
    }

    i++;

    if (token.startsWith('<') || token.startsWith('[')) continue;

    if (tokens[i] === '{') {
      i = expand(tokens, i + 1, [...prefix, token], out);
      continue;
    }

    out.add([...prefix, token].join(' '));
  }

  return i;
}

/** Parse the §1 fenced block into the set of leaves it draws. */
function docLeaves(): Set<string> {
  const md = fs.readFileSync(DOC, 'utf-8');
  const section = md.slice(md.indexOf('## 1. The tree'));
  const fence = section.slice(section.indexOf('```') + 3);
  const block = fence.slice(0, fence.indexOf('```'));

  const leaves = new Set<string>();
  let domain = '';
  let body: string[] = [];

  const flush = (): void => {
    if (domain && body.length > 0) expand(body, 0, [domain], leaves);
    body = [];
  };

  for (const rawLine of block.split('\n')) {
    // Strip parenthetical asides like "(see §9)" and "(hidden)".
    const line = rawLine.replace(/\([^)]*\)/g, '');
    if (!line.trim()) continue;

    // `rdc doctor | credits | update | serve | mcp serve` — whole commands, one row.
    if (line.includes('|')) {
      flush();
      domain = '';
      for (const alt of line.replace(/^rdc\s+/, '').split('|')) {
        const parts = alt.trim().split(/\s+/).filter(Boolean);
        if (parts.length > 0 && !HELD_OUT.has(parts[0])) leaves.add(parts.join(' '));
      }
      continue;
    }

    const tokenize = (text: string): string[] =>
      text
        .replace(/([{}])/g, ' $1 ')
        .split(/\s+/)
        .filter(Boolean);

    // The noun may carry a trailing colon (`rdc ops:  up down …`). It is a table
    // separator, not part of the name: without it the row parses as the invocation
    // `rdc ops up` and the positional-syntax detector reds on the design doc.
    const header = line.match(/^rdc\s+([^\s:]+):?\s*(.*)$/);
    if (header) {
      flush();
      domain = header[1];
      body = tokenize(header[2]);
    } else if (/^\s/.test(rawLine) && domain) {
      body.push(...tokenize(line));
    }
  }
  flush();

  return leaves;
}

// ---------- Check ----------

const cli = cliLeaves();
const doc = docLeaves();

// A leaf the doc draws is satisfied if the CLI has it, OR if it is an actionable
// parent the CLI models as a group (the doc writes `repo replicate <ref>` for a
// parent that also runs), OR if it is a group whose children the CLI has.
const cliPrefixes = new Set<string>();
for (const leaf of cli) {
  const parts = leaf.split(' ');
  for (let i = 1; i <= parts.length; i++) cliPrefixes.add(parts.slice(0, i).join(' '));
}

const phantom = [...doc].filter((leaf) => !cliPrefixes.has(leaf)).sort();
const omitted = [...cli].filter((leaf) => !doc.has(leaf)).sort();

if (phantom.length > 0 || omitted.length > 0) {
  console.error(
    '\x1b[31m✗ docs/design/06-cli-reshape.md §1 does not match the shipped CLI\x1b[0m\n'
  );
  if (phantom.length > 0) {
    console.error('  The doc draws commands the CLI does not have:');
    for (const leaf of phantom) console.error(`    rdc ${leaf}`);
    console.error('');
  }
  if (omitted.length > 0) {
    console.error('  The CLI has commands the doc never lists:');
    for (const leaf of omitted) console.error(`    rdc ${leaf}`);
    console.error('');
  }
  console.error('  §1 is an as-built transcript. Update it, and record the reason in §1.1.');
  process.exit(1);
}

console.log(
  `\x1b[32m✓\x1b[0m docs/design/06-cli-reshape.md §1 matches the shipped CLI ` +
    `(${cli.size} leaves, both directions)`
);
