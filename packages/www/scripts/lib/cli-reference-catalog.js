import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const LOCAL_GROUPS = [
  'agent',
  'config',
  'datastore',
  'store',
  'machine',
  'mcp',
  'repo',
  'storage',
  'vscode',
  'term',
  'protocol',
  'shortcuts',
  'subscription',
  'update',
  'doctor',
  'ops',
];

const CLOUD_GROUPS = [
  'auth',
  'organization',
  'user',
  'team',
  'permission',
  'region',
  'bridge',
  'repository',
  'queue',
  'ceph',
  'audit',
];

const TARGET_DOC_CATEGORIES = new Set([
  'Guides',
  'Tutorials',
  'Concepts',
  'Reference',
  'Use Cases',
]);
const SHELL_FENCE_LANGS = new Set(['bash', 'sh', 'shell', 'zsh', 'powershell', 'ps1']);
// Flags always valid on any command. Includes options not exported in command-tree.json
// but registered globally by the CLI framework (output formatting, confirmations, etc.)
const GLOBAL_ALWAYS_VALID = new Set([
  '--help',
  '-h',
  '--version',
  '-V',
  '--output',
  '-o',
  '--yes',
  '-y',
  '--quiet',
  '-q',
  '--dry-run',
  '--fields',
  '--no-color',
]);

const COMMAND_TREE_PATH = path.resolve(__dirname, '../../../cli/scripts/command-tree.json');
const CLI_JSON_PATH = path.resolve(__dirname, '../../../cli/src/i18n/locales/en/cli.json');

let cachedTree = null;
let cachedCatalog = null;
let cachedDocumentedPaths = null;

export function getCommandTree() {
  if (cachedTree) return cachedTree;
  cachedTree = JSON.parse(fs.readFileSync(COMMAND_TREE_PATH, 'utf-8'));
  return cachedTree;
}

function toKebab(str) {
  return String(str)
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .toLowerCase();
}

function isCommandNode(node) {
  return node && typeof node === 'object' && typeof node.description === 'string';
}

function collectDocumentedPaths(node, parts, out) {
  for (const [key, value] of Object.entries(node || {})) {
    if (key === 'description') continue;
    if (!isCommandNode(value)) continue;
    const next = [...parts, toKebab(key)];
    out.add(next.join(' '));
    collectDocumentedPaths(value, next, out);
  }
}

function getDocumentedReferencePaths() {
  if (cachedDocumentedPaths) return cachedDocumentedPaths;
  const cliJson = JSON.parse(fs.readFileSync(CLI_JSON_PATH, 'utf-8'));
  const documented = new Set();

  for (const group of [...LOCAL_GROUPS, ...CLOUD_GROUPS]) {
    documented.add(group);
    collectDocumentedPaths(cliJson?.commands?.[group], [group], documented);
  }

  cachedDocumentedPaths = documented;
  return documented;
}

export function getGroupScope(group) {
  if (LOCAL_GROUPS.includes(group)) return 'local';
  if (CLOUD_GROUPS.includes(group)) return 'cloud';
  return 'local';
}

export function getReferenceSlug(scope) {
  return scope === 'cloud' ? 'cli-application-cloud' : 'cli-application';
}

export function toAnchorId(scope, commandPath) {
  return `cli-${scope}-${commandPath.replaceAll(' ', '-').replaceAll('.', '-')}`;
}

export function toGroupAnchorId(scope, group) {
  return `cli-${scope}-group-${group}`;
}

function extractFlagNames(flags) {
  return String(flags)
    .split(',')
    .map((part) => part.trim().split(/\s+/)[0])
    .filter(Boolean);
}

function optionExpectsValue(flag, optionDefs) {
  for (const option of optionDefs || []) {
    const names = extractFlagNames(option.flags);
    if (!names.includes(flag)) continue;
    return /<.+?>/.test(option.flags) || /\[.+?\]/.test(option.flags);
  }
  return false;
}

function walkCommands(node, pathParts, out) {
  const commandPath = pathParts.join(' ');
  if (commandPath) {
    const group = pathParts[0];
    const scope = getGroupScope(group);
    const rootOptionDefs = getCommandTree().options || [];
    const commandOptionDefs = node.options || [];
    const allowedFlags = new Set([...GLOBAL_ALWAYS_VALID]);

    for (const option of rootOptionDefs) {
      for (const name of extractFlagNames(option.flags)) allowedFlags.add(name);
    }
    for (const option of commandOptionDefs) {
      for (const name of extractFlagNames(option.flags)) allowedFlags.add(name);
    }

    out.set(commandPath, {
      commandPath,
      group,
      scope,
      slug: getReferenceSlug(scope),
      anchorId: toAnchorId(scope, commandPath),
      node,
      rootOptionDefs,
      commandOptionDefs,
      allowedFlags,
      args: node.arguments || [],
    });
  }

  for (const sub of node.subcommands || []) {
    walkCommands(sub, [...pathParts, sub.name], out);
  }
}

export function getCliReferenceCatalog() {
  if (cachedCatalog) return cachedCatalog;
  const map = new Map();
  const documentedPaths = getDocumentedReferencePaths();
  const tree = getCommandTree();
  for (const sub of tree.subcommands || []) {
    walkCommands(sub, [sub.name], map);
  }
  for (const [key, entry] of map.entries()) {
    entry.documented = documentedPaths.has(key);
  }
  cachedCatalog = map;
  return map;
}

function findCommand(tokensAfterRoot) {
  const tree = getCommandTree();
  let node = { subcommands: tree.subcommands || [] };
  const matched = [];

  for (const token of tokensAfterRoot) {
    const next = (node.subcommands || []).find((sub) => sub.name === token);
    if (!next) break;
    matched.push(token);
    node = next;
  }

  return {
    node: matched.length > 0 ? node : null,
    consumed: matched.length,
    commandPath: matched.join(' '),
  };
}

export function parseShellTokens(text) {
  const tokens = [];
  let current = '';
  let quote = null;
  let escape = false;

  for (const char of text) {
    if (escape) {
      current += char;
      escape = false;
      continue;
    }

    if (char === '\\') {
      escape = true;
      continue;
    }

    if (quote) {
      if (char === quote) {
        quote = null;
      } else {
        current += char;
      }
      continue;
    }

    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }

    if (/\s/.test(char)) {
      if (current) {
        tokens.push(current);
        current = '';
      }
      continue;
    }

    current += char;
  }

  if (current) tokens.push(current);
  return tokens;
}

export function parseRdcCommand(commandText) {
  const tokens = parseShellTokens(commandText.trim());
  if (tokens[0] !== 'rdc') {
    return { ok: false, reason: 'not-rdc' };
  }

  const tree = getCommandTree();
  const rootOptionDefs = tree.options || [];
  const rootFlags = new Set([...GLOBAL_ALWAYS_VALID]);
  for (const option of rootOptionDefs) {
    for (const name of extractFlagNames(option.flags)) rootFlags.add(name);
  }

  let index = 1;
  while (index < tokens.length && tokens[index].startsWith('-')) {
    const token = tokens[index];
    const flag = token.includes('=') ? token.split('=')[0] : token;

    if (!rootFlags.has(flag)) {
      return { ok: false, reason: 'unknown-global-option', flag, commandText };
    }

    if (!token.includes('=') && optionExpectsValue(flag, rootOptionDefs)) {
      index += 1;
    }

    index += 1;
  }

  if (index >= tokens.length) {
    return { ok: true, rootOnly: true, commandText };
  }

  const tokensAfterRoot = tokens.slice(index);
  const found = findCommand(tokensAfterRoot);
  if (!found.node) {
    return {
      ok: false,
      reason: 'unknown-command',
      near: tokensAfterRoot[0] || '',
      commandText,
    };
  }

  const commandOptionDefs = found.node.options || [];
  const validFlags = new Set([...GLOBAL_ALWAYS_VALID]);
  for (const option of rootOptionDefs) {
    for (const name of extractFlagNames(option.flags)) validFlags.add(name);
  }
  for (const option of commandOptionDefs) {
    for (const name of extractFlagNames(option.flags)) validFlags.add(name);
  }

  const args = found.node.arguments || [];
  const variadicIndex = args.findIndex((arg) => arg.variadic);

  let positionals = 0;
  let i = index + found.consumed;
  while (i < tokens.length) {
    const token = tokens[i];
    const canConsumeVariadic = variadicIndex !== -1 && positionals >= variadicIndex;

    if (token.startsWith('-') && !canConsumeVariadic) {
      const flag = token.includes('=') ? token.split('=')[0] : token;
      if (!validFlags.has(flag)) {
        return {
          ok: false,
          reason: 'unknown-option',
          flag,
          commandPath: found.commandPath,
          commandText,
        };
      }

      if (
        !token.includes('=') &&
        (optionExpectsValue(flag, rootOptionDefs) || optionExpectsValue(flag, commandOptionDefs))
      ) {
        i += 1;
      }
    } else {
      positionals += 1;
    }

    i += 1;
  }

  const requiredArgs = args.filter((arg) => arg.required).length;
  if (positionals < requiredArgs) {
    return {
      ok: false,
      reason: 'missing-required-args',
      commandPath: found.commandPath,
      requiredArgs,
      positionals,
      commandText,
    };
  }

  const catalog = getCliReferenceCatalog();
  const entry = catalog.get(found.commandPath);
  if (!entry) {
    return {
      ok: false,
      reason: 'missing-reference-entry',
      commandPath: found.commandPath,
      commandText,
    };
  }
  if (!entry.documented) {
    return {
      ok: false,
      reason: 'missing-reference-entry',
      commandPath: found.commandPath,
      commandText,
    };
  }

  return {
    ok: true,
    rootOnly: false,
    commandPath: found.commandPath,
    entry,
    commandText,
  };
}

export function mergeContinuationLines(lines, startIndex) {
  let command = lines[startIndex].trim();
  let endIndex = startIndex;
  while (command.endsWith('\\') && endIndex + 1 < lines.length) {
    command = `${command.slice(0, -1).trimEnd()} ${lines[endIndex + 1].trim()}`;
    endIndex += 1;
  }
  return { command, endIndex };
}

export {
  CLOUD_GROUPS,
  GLOBAL_ALWAYS_VALID,
  LOCAL_GROUPS,
  SHELL_FENCE_LANGS,
  TARGET_DOC_CATEGORIES,
};
