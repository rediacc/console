#!/usr/bin/env node
/**
 * CLI Translation Key Usage Check (RUNTIME half)
 *
 * The static sibling (check-cli-i18n-key-usage.ts) resolves every t('literal')
 * against en/cli.json, but honestly skips keys built from template literals
 * (t(`help.${x}`)) or variables, because it cannot evaluate them. Those dynamically
 * built keys are exactly where the shipped bug lived: machine/index.ts renders
 * help.machine.containers into `rdc machine status --help` and it leaked as a
 * raw key.
 *
 * This gate renders --help for every node of the LIVE Commander tree (the same
 * tree the docs exporter walks: packages/cli/src/cli.ts) and fails on any
 * output that still looks like an unresolved i18n key. addHelpText('after')
 * content (where the bug lives) surfaces only through outputHelp(), never
 * helpInformation(), so each node is rendered via a captured outputHelp().
 *
 * Detecting a raw key without tripping on prose or URLs: a leaked i18next key
 * has a precise shape: its root segment is one of en/cli.json's top-level
 * namespaces, its parent path resolves to an OBJECT in the catalogue, and the
 * full path is a MISSING leaf. That is what "namespace exists, leaf typo'd or
 * computed wrong" looks like (help.machine exists, containers does not). A URL
 * like docs.rediacc.com fails the parent-is-object test; a real key like
 * options.output resolves to a leaf and is never flagged.
 *
 * Coverage limit (stated, per the check-lockfile.sh precedent): this catches
 * leaks whose namespace PATH is real but whose leaf is wrong. A key with a
 * bogus root namespace (t('helpx.foo')) is the static half's job. Agent-only /
 * --help-all help blocks are force-expanded below so they are covered too.
 *
 * Usage:
 *   npx tsx scripts/check-cli-i18n-help-render.ts
 *   npm run check:ci-i18n-cli-help-render
 *
 * Exit codes:
 *   0 - No raw i18n keys in any rendered help
 *   1 - At least one rendered help output contains a raw key
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Force every conditional help block to register so the render covers them:
// some addHelpText blocks gate on isAgentEnvironment() (REDIACC_AGENT=1) and
// others on --help-all. Both must be set BEFORE importing cli.ts, because the
// blocks are attached at module-registration time.
process.env.REDIACC_AGENT = '1';
if (!process.argv.includes('--help-all')) process.argv.push('--help-all');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// This gate lives beside export-command-tree.ts (packages/cli/scripts/), the
// established home for scripts that walk the live Commander tree via ../src.
const EN_CLI_JSON = path.resolve(__dirname, '../src/i18n/locales/en/cli.json');

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

// Last-segment extensions that make a namespace-rooted token a filename in
// prose (e.g. "common.js", "docs.md"), not a raw key. Kept deliberately small.
const FILE_EXT = new Set([
  'js',
  'ts',
  'mjs',
  'cjs',
  'jsx',
  'tsx',
  'json',
  'sh',
  'md',
  'go',
  'mod',
  'sum',
  'yml',
  'yaml',
  'toml',
  'env',
  'sock',
  'png',
  'jpg',
  'jpeg',
  'mp4',
  'txt',
  'lock',
  'html',
  'css',
  'conf',
  'ini',
  'log',
  'pem',
  'crt',
]);

function classify(root: Record<string, JsonValue>, dotPath: string): 'object' | 'leaf' | 'missing' {
  let current: JsonValue = root;
  for (const segment of dotPath.split('.')) {
    if (current && typeof current === 'object' && !Array.isArray(current) && segment in current) {
      current = (current as Record<string, JsonValue>)[segment];
    } else {
      return 'missing';
    }
  }
  return current !== null && typeof current === 'object' && !Array.isArray(current)
    ? 'object'
    : 'leaf';
}

interface Leak {
  commandPath: string;
  token: string;
  snippet: string;
}

interface CommanderCommand {
  name(): string;
  commands: CommanderCommand[];
  configureOutput(opts: {
    writeOut?: (s: string) => void;
    writeErr?: (s: string) => void;
  }): unknown;
  outputHelp(): void;
}

async function main(): Promise<void> {
  console.log('CLI Translation Key Usage Check (runtime help render)');
  console.log('============================================================\n');

  const enJson = JSON.parse(fs.readFileSync(EN_CLI_JSON, 'utf-8')) as Record<string, JsonValue>;
  const namespaces = Object.keys(enJson).filter((k) => {
    const v = enJson[k];
    return v !== null && typeof v === 'object' && !Array.isArray(v);
  });

  // A namespace-rooted, camelCase dotted token: <namespace>(.seg)+.
  const tokenRe = new RegExp(`\\b(?:${namespaces.join('|')})(?:\\.[A-Za-z][A-Za-z0-9]*)+`, 'g');

  const { cli } = (await import('../src/cli.js')) as { cli: CommanderCommand };

  const leaks: Leak[] = [];
  const renderErrors: { commandPath: string; error: string }[] = [];
  let nodesRendered = 0;

  const visit = (cmd: CommanderCommand, prefix: string[]): void => {
    const name = cmd.name();
    if (name === 'help') return;
    const commandPath = ['rdc', ...prefix, name].filter(Boolean).join(' ');

    let captured = '';
    cmd.configureOutput({ writeOut: (s: string) => (captured += s), writeErr: () => {} });
    try {
      cmd.outputHelp();
      nodesRendered++;
    } catch (err) {
      renderErrors.push({ commandPath, error: err instanceof Error ? err.message : String(err) });
    }

    const seen = new Set<string>();
    let m: RegExpExecArray | null;
    tokenRe.lastIndex = 0;
    while ((m = tokenRe.exec(captured)) !== null) {
      const token = m[0];
      if (seen.has(token)) continue;
      const segs = token.split('.');
      const last = segs[segs.length - 1].toLowerCase();
      if (FILE_EXT.has(last)) continue;
      const parent = segs.slice(0, -1).join('.');
      // Raw-key signature: the parent namespace path is a real object, the full
      // path is a missing leaf.
      if (classify(enJson, token) === 'missing' && classify(enJson, parent) === 'object') {
        seen.add(token);
        const idx = captured.indexOf(token);
        const snippet = captured
          .slice(Math.max(0, idx - 30), idx + token.length + 10)
          .replaceAll(/\s+/g, ' ')
          .trim();
        leaks.push({ commandPath, token, snippet });
      }
    }

    for (const sub of cmd.commands) visit(sub, [...prefix, name]);
  };

  // Walk each top-level command (skip the implicit root name "rdc" itself, but
  // do render the root's own help for its addHelpText blocks).
  let rootCaptured = '';
  cli.configureOutput({ writeOut: (s: string) => (rootCaptured += s), writeErr: () => {} });
  try {
    cli.outputHelp();
    nodesRendered++;
  } catch (err) {
    renderErrors.push({
      commandPath: 'rdc',
      error: err instanceof Error ? err.message : String(err),
    });
  }
  {
    const seen = new Set<string>();
    let m: RegExpExecArray | null;
    tokenRe.lastIndex = 0;
    while ((m = tokenRe.exec(rootCaptured)) !== null) {
      const token = m[0];
      if (seen.has(token)) continue;
      const segs = token.split('.');
      if (FILE_EXT.has(segs[segs.length - 1].toLowerCase())) continue;
      const parent = segs.slice(0, -1).join('.');
      if (classify(enJson, token) === 'missing' && classify(enJson, parent) === 'object') {
        seen.add(token);
        const idx = rootCaptured.indexOf(token);
        leaks.push({
          commandPath: 'rdc',
          token,
          snippet: rootCaptured
            .slice(Math.max(0, idx - 30), idx + token.length + 10)
            .replaceAll(/\s+/g, ' ')
            .trim(),
        });
      }
    }
  }
  for (const sub of cli.commands) visit(sub, []);

  const GREEN = '\x1b[32m';
  const RED = '\x1b[31m';
  const YELLOW = '\x1b[33m';
  const RESET = '\x1b[0m';

  console.log(
    `Rendered --help for ${nodesRendered} command node(s) across ${namespaces.length} namespaces.\n`
  );

  if (renderErrors.length > 0) {
    console.log(`${YELLOW}!${RESET} ${renderErrors.length} node(s) failed to render:`);
    for (const e of renderErrors) console.log(`    ${e.commandPath}: ${e.error}`);
    console.log('');
  }

  if (leaks.length === 0 && renderErrors.length === 0) {
    console.log(`${GREEN}✓${RESET} No raw i18n keys found in rendered help output`);
    process.exit(0);
  }

  if (leaks.length > 0) {
    console.log(`${RED}✗${RESET} Found ${leaks.length} raw i18n key(s) in rendered help:\n`);
    for (const leak of leaks) {
      console.log(`  ${leak.commandPath} --help`);
      console.log(`    raw key: ${leak.token}`);
      console.log(`    context: ...${leak.snippet}...`);
      console.log('');
    }
    console.log('Fix: add the key to packages/cli/src/i18n/locales/en/cli.json (English),');
    console.log('then run the 12-locale naturalization pass so the other locales carry it.\n');
  }

  process.exit(1);
}

void main();
