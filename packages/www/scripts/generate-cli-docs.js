#!/usr/bin/env node
/**
 * CLI Documentation Generator
 *
 * Generates cli-application.md for all supported languages from the CLI's
 * i18n source of truth (cli.json). Each language gets its own file with
 * translated frontmatter and {{t:cli.docs.*}} keys in the body that the
 * remark-resolve-translations plugin resolves at build time.
 *
 * Usage:
 *   node packages/www/scripts/generate-cli-docs.js
 *
 * The generated files use {{t:cli.xxx}} translation keys that the
 * remark-resolve-translations plugin resolves at build time.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { computeSourceHash } from './validate-translation-freshness.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// All supported languages
const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

// Path helpers
function getCliJsonPath(lang) {
  return path.resolve(__dirname, `../../cli/src/i18n/locales/${lang}/cli.json`);
}

function getOutputPath(lang) {
  return path.resolve(__dirname, `../src/content/docs/${lang}/cli-application.md`);
}

// Command groups in registration order (matches cli.ts)
const COMMAND_ORDER = [
  'auth',
  'context',
  'organization',
  'user',
  'team',
  'permission',
  'region',
  'bridge',
  'machine',
  'repository',
  'repo',
  'storage',
  'queue',
  'sync',
  'vscode',
  'term',
  'ceph',
  'audit',
  'protocol',
  'snapshot',
  'backup',
  'shortcuts',
  'update',
  'doctor',
  'ops',
];

// Validate COMMAND_ORDER against actual command groups in cli.json
function validateCommandOrder(commands) {
  const allGroups = new Set(Object.keys(commands));
  const orderedGroups = new Set(COMMAND_ORDER);

  for (const group of allGroups) {
    if (!orderedGroups.has(group)) {
      throw new Error(
        `Command group "${group}" exists in cli.json but is missing from COMMAND_ORDER in generate-cli-docs.js. ` +
          `Add it to COMMAND_ORDER to include it in the generated documentation.`
      );
    }
  }

  for (const group of orderedGroups) {
    if (!allGroups.has(group)) {
      console.warn(
        `Warning: Command group "${group}" is in COMMAND_ORDER but not found in cli.json commands.`
      );
    }
  }
}

// Convert camelCase to kebab-case for CLI command syntax
function toKebab(str) {
  return str.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
}

/**
 * Check if a node in cli.json represents a command (has a "description" key)
 */
function isCommand(node) {
  return node && typeof node === 'object' && typeof node.description === 'string';
}

/**
 * Check if a node has sub-commands (nested objects that themselves have descriptions)
 */
function hasSubCommands(node) {
  if (!node || typeof node !== 'object') return false;
  for (const [key, value] of Object.entries(node)) {
    if (key === 'description') continue;
    if (isCommand(value)) return true;
  }
  return false;
}

/**
 * Get the ordered sub-command keys for a node
 */
function getSubCommandKeys(node) {
  return Object.keys(node).filter((key) => {
    if (key === 'description') return false;
    return isCommand(node[key]);
  });
}

/**
 * Resolve a dotted path in an object
 */
function getNestedValue(obj, dotPath) {
  const parts = dotPath.split('.');
  let current = obj;
  for (const part of parts) {
    if (current === null || current === undefined || typeof current !== 'object') return undefined;
    current = current[part];
  }
  return current;
}

/**
 * Check if a supplement key exists in the English cli.json docs.supplements section.
 * Returns true if the path resolves to a non-undefined value.
 */
function hasSupplementKey(docsSupplements, supplementPath) {
  return getNestedValue(docsSupplements, supplementPath) !== undefined;
}

/**
 * Emit supplement content using {{t:}} keys for a given command path and type.
 * Only emits if the key exists in the English cli.json docs.supplements section.
 */
function emitSupplement(docsSupplements, commandPath, type) {
  // Build the supplement lookup path
  let lookupPath;
  if (type === 'afterDescription') {
    // e.g., commandPath="context", type="afterDescription" -> "context.afterDescription"
    // e.g., commandPath="context.createLocal", type="afterDescription" -> "context.createLocal.afterDescription"
    lookupPath = `${commandPath}.${type}`;
  } else {
    lookupPath = `${commandPath}.${type}`;
  }

  if (!hasSupplementKey(docsSupplements, lookupPath)) return '';

  const tKey = `{{t:cli.docs.supplements.${lookupPath}}}`;

  switch (type) {
    case 'tip':
      return `\n> **{{t:cli.docs.admonitions.tip}}**: ${tKey}\n`;
    case 'warning':
      return `\n> **{{t:cli.docs.admonitions.warning}}**: ${tKey}\n`;
    case 'note':
      return `\n> **{{t:cli.docs.admonitions.note}}**: ${tKey}\n`;
    case 'afterDescription':
      return `\n${tKey}\n`;
    default:
      return '';
  }
}

/**
 * Build CLI command syntax string from a command path
 * e.g., ['auth', 'token', 'list'] -> 'rdc auth token list'
 */
function buildCommandSyntax(group, ...subParts) {
  // Shortcuts special case: "rdc run" not "rdc shortcuts run"
  if (group === 'shortcuts') {
    return `rdc ${subParts.map(toKebab).join(' ')}`;
  }
  const parts = [group, ...subParts].map(toKebab);
  return `rdc ${parts.join(' ')}`;
}

// ---------- Command tree enrichment ----------

const COMMAND_TREE_PATH = path.resolve(__dirname, '../../cli/scripts/command-tree.json');
let commandTreeLookup = {};
try {
  const tree = JSON.parse(fs.readFileSync(COMMAND_TREE_PATH, 'utf-8'));
  commandTreeLookup = buildCommandLookup(tree);
} catch {
  /* graceful fallback — tables simply won't be emitted */
}

function buildCommandLookup(tree, prefix = '') {
  const lookup = {};
  const recurse = (node, p) => {
    for (const sub of node.subcommands || []) {
      const key = p ? `${p}.${sub.name}` : sub.name;
      lookup[key] = sub;
      recurse(sub, key);
    }
  };
  recurse(tree, prefix);
  return lookup;
}

function getCommandTreeKey(group, ...subKeys) {
  return [group, ...subKeys].map(toKebab).join('.');
}

function buildEnrichedSyntax(group, ...subParts) {
  const base = buildCommandSyntax(group, ...subParts);
  const key = getCommandTreeKey(group, ...subParts);
  const node = commandTreeLookup[key];
  if (!node) return base;
  let suffix = '';
  for (const arg of node.arguments || []) {
    if (arg.variadic) {
      suffix += arg.required ? ` <${arg.name}...>` : ` [${arg.name}...]`;
    } else {
      suffix += arg.required ? ` <${arg.name}>` : ` [${arg.name}]`;
    }
  }
  if (node.options && node.options.length > 0) suffix += ' [options]';
  return base + suffix;
}

function emitOptionsTable(group, ...subParts) {
  const key = getCommandTreeKey(group, ...subParts);
  const node = commandTreeLookup[key];
  if (!node || !node.options || node.options.length === 0) return [];
  const tableLines = [];
  tableLines.push('');
  tableLines.push(
    '| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} | {{t:cli.docs.tableHeaders.required}} | {{t:cli.docs.tableHeaders.default}} |'
  );
  tableLines.push('|------|-------------|----------|---------|');
  for (const opt of node.options) {
    const flags = `\`${opt.flags}\``;
    const desc = opt.descriptionKey ? `{{t:cli.${opt.descriptionKey}}}` : '\u2014';
    const req = opt.mandatory
      ? '{{t:cli.docs.optionLabels.yes}}'
      : '{{t:cli.docs.optionLabels.no}}';
    const def = opt.defaultValue != null ? `\`${opt.defaultValue}\`` : '-';
    tableLines.push(`| ${flags} | ${desc} | ${req} | ${def} |`);
  }
  tableLines.push('');
  return tableLines;
}

/**
 * YAML-safe quote: wraps value in double quotes, escaping inner double quotes
 */
function yamlQuote(value) {
  return `"${value.replace(/"/g, '\\"')}"`;
}

/**
 * Generate the markdown content for a given language.
 * Uses the English cli.json for structural discovery (command tree)
 * and the target language's cli.json for frontmatter values.
 * Body content is identical across all languages (uses {{t:}} keys).
 */
export function generate(lang, cliJsonEn, { sourceHash } = {}) {
  // Load the target language's cli.json for frontmatter
  const langCliJson = JSON.parse(fs.readFileSync(getCliJsonPath(lang), 'utf-8'));
  const docs = langCliJson.docs;

  const commands = cliJsonEn.commands;
  validateCommandOrder(commands);
  const errors = cliJsonEn.errors;
  const docsSupplements = cliJsonEn.docs.supplements;
  const lines = [];

  // --- Frontmatter (translated per language) ---
  lines.push('---');
  lines.push(`title: ${yamlQuote(docs.frontmatter.title)}`);
  lines.push(`description: ${yamlQuote(docs.frontmatter.description)}`);
  lines.push(`category: ${yamlQuote(docs.frontmatter.category)}`);
  lines.push('order: 2');
  lines.push(`language: ${lang}`);
  lines.push('generated: true');
  lines.push(`generatedFrom: packages/cli/src/i18n/locales/${lang}/cli.json`);
  if (sourceHash) {
    lines.push(`sourceHash: "${sourceHash}"`);
  }
  lines.push('---');
  lines.push('');

  // --- Auto-generated comment ---
  lines.push('<!-- THIS FILE IS AUTO-GENERATED. Do not edit manually. -->');
  lines.push('<!-- To regenerate: npm run generate:cli-docs -w @rediacc/www -->');
  lines.push('');

  // --- Title ---
  lines.push('# {{t:cli.docs.pageTitle}}');
  lines.push('');

  // --- Overview ---
  lines.push('## {{t:cli.docs.overview.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.overview.text}}');
  lines.push('');

  // --- Installation ---
  lines.push('### {{t:cli.docs.installation.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.installation.text}}');
  lines.push('');
  lines.push('```bash');
  lines.push('# macOS / Linux');
  lines.push('curl -fsSL https://get.rediacc.com | sh');
  lines.push('');
  lines.push('# Or use the packaged binary directly');
  lines.push('./rdc --help');
  lines.push('```');
  lines.push('');

  // --- Global options table ---
  lines.push('### {{t:cli.docs.globalOptions.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.globalOptions.intro}}');
  lines.push('');
  lines.push('| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} |');
  lines.push('|------|-------------|');
  lines.push('| `--output` | {{t:cli.options.output}} |');
  lines.push('| `--context` | {{t:cli.options.context}} |');
  lines.push('| `--lang` | {{t:cli.options.lang}} |');
  lines.push('| `--force` | {{t:cli.options.force}} |');
  lines.push('');
  lines.push('---');
  lines.push('');

  // --- Command sections ---
  let sectionNum = 0;

  for (const group of COMMAND_ORDER) {
    const groupData = commands[group];
    if (!groupData) continue;

    sectionNum++;

    // H2 for command group — use {{t:}} key for section title
    lines.push(`## ${sectionNum}. {{t:cli.docs.sectionTitles.${group}}}`);
    lines.push('');

    // Group description
    if (groupData.description) {
      lines.push(`{{t:cli.commands.${group}.description}}`);
      lines.push('');
    }

    // after_description supplement for group
    const groupAfter = emitSupplement(docsSupplements, group, 'afterDescription');
    if (groupAfter) {
      lines.push(groupAfter.trim());
      lines.push('');
    }

    // Process sub-commands
    const subKeys = getSubCommandKeys(groupData);
    let subNum = 0;

    // Standalone command (no sub-commands, e.g., update, doctor)
    if (subKeys.length === 0) {
      lines.push('```bash');
      lines.push(buildEnrichedSyntax(group));
      lines.push('```');
      lines.push(...emitOptionsTable(group));
      lines.push('');
    }

    for (const subKey of subKeys) {
      const subData = groupData[subKey];
      subNum++;

      if (hasSubCommands(subData)) {
        // This is a sub-group (e.g., auth.tfa, auth.token, team.member, permission.group, organization.vault)
        lines.push(`### ${sectionNum}.${subNum} ${toKebab(subKey)}`);
        lines.push('');
        lines.push(`{{t:cli.commands.${group}.${subKey}.description}}`);
        lines.push('');

        // after_description supplement
        const subGroupAfter = emitSupplement(
          docsSupplements,
          `${group}.${subKey}`,
          'afterDescription'
        );
        if (subGroupAfter) {
          lines.push(subGroupAfter.trim());
          lines.push('');
        }

        // Nested sub-commands
        const nestedKeys = getSubCommandKeys(subData);
        for (const nestedKey of nestedKeys) {
          const nestedData = subData[nestedKey];

          if (hasSubCommands(nestedData)) {
            // 3rd level nesting (e.g., ceph.cluster.vault.get)
            lines.push(`#### ${toKebab(nestedKey)}`);
            lines.push('');
            lines.push(`{{t:cli.commands.${group}.${subKey}.${nestedKey}.description}}`);
            lines.push('');

            const level3Keys = getSubCommandKeys(nestedData);
            for (const l3Key of level3Keys) {
              const commandPath = `${group}.${subKey}.${nestedKey}.${l3Key}`;
              lines.push(`**${toKebab(l3Key)}:**`);
              lines.push('');
              lines.push(`{{t:cli.commands.${commandPath}.description}}`);
              lines.push('');
              lines.push('```bash');
              lines.push(buildEnrichedSyntax(group, subKey, nestedKey, l3Key));
              lines.push('```');
              lines.push(...emitOptionsTable(group, subKey, nestedKey, l3Key));
              lines.push('');

              // Supplements for deeply nested
              const deepTip = emitSupplement(docsSupplements, commandPath, 'tip');
              if (deepTip) lines.push(deepTip.trim()), lines.push('');
              const deepWarning = emitSupplement(docsSupplements, commandPath, 'warning');
              if (deepWarning) lines.push(deepWarning.trim()), lines.push('');
              const deepNote = emitSupplement(docsSupplements, commandPath, 'note');
              if (deepNote) lines.push(deepNote.trim()), lines.push('');
            }
          } else {
            // Leaf command within a sub-group
            const commandPath = `${group}.${subKey}.${nestedKey}`;
            lines.push(`#### ${toKebab(nestedKey)}`);
            lines.push('');
            lines.push(`{{t:cli.commands.${commandPath}.description}}`);
            lines.push('');

            // after_description supplement
            const nestedAfter = emitSupplement(docsSupplements, commandPath, 'afterDescription');
            if (nestedAfter) {
              lines.push(nestedAfter.trim());
              lines.push('');
            }

            lines.push('```bash');
            lines.push(buildEnrichedSyntax(group, subKey, nestedKey));
            lines.push('```');
            lines.push(...emitOptionsTable(group, subKey, nestedKey));
            lines.push('');

            // Supplements
            const tipSup = emitSupplement(docsSupplements, commandPath, 'tip');
            if (tipSup) lines.push(tipSup.trim()), lines.push('');
            const warnSup = emitSupplement(docsSupplements, commandPath, 'warning');
            if (warnSup) lines.push(warnSup.trim()), lines.push('');
            const noteSup = emitSupplement(docsSupplements, commandPath, 'note');
            if (noteSup) lines.push(noteSup.trim()), lines.push('');
          }
        }
      } else {
        // Leaf command directly under group (e.g., auth.login, machine.list)
        const commandPath = `${group}.${subKey}`;
        lines.push(`### ${sectionNum}.${subNum} ${toKebab(subKey)}`);
        lines.push('');
        lines.push(`{{t:cli.commands.${commandPath}.description}}`);
        lines.push('');

        // after_description supplement
        const cmdAfter = emitSupplement(docsSupplements, commandPath, 'afterDescription');
        if (cmdAfter) {
          lines.push(cmdAfter.trim());
          lines.push('');
        }

        lines.push('```bash');
        lines.push(buildEnrichedSyntax(group, subKey));
        lines.push('```');
        lines.push(...emitOptionsTable(group, subKey));
        lines.push('');

        // Supplements
        const tipSup = emitSupplement(docsSupplements, commandPath, 'tip');
        if (tipSup) lines.push(tipSup.trim()), lines.push('');
        const warnSup = emitSupplement(docsSupplements, commandPath, 'warning');
        if (warnSup) lines.push(warnSup.trim()), lines.push('');
        const noteSup = emitSupplement(docsSupplements, commandPath, 'note');
        if (noteSup) lines.push(noteSup.trim()), lines.push('');
      }
    }

    // Group-level tip/warning supplements (applied after all sub-commands)
    const groupTip = emitSupplement(docsSupplements, group, 'tip');
    if (groupTip) lines.push(groupTip.trim()), lines.push('');
    const groupWarning = emitSupplement(docsSupplements, group, 'warning');
    if (groupWarning) lines.push(groupWarning.trim()), lines.push('');

    lines.push('---');
    lines.push('');
  }

  // --- Common Error Messages ---
  lines.push('## {{t:cli.docs.errors.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.errors.intro}}');
  lines.push('');
  lines.push('| {{t:cli.docs.tableHeaders.error}} | {{t:cli.docs.tableHeaders.meaning}} |');
  lines.push('|-------|---------|');

  // Pick the most important/common flat error keys
  const errorKeys = [
    'authRequired',
    'noActiveContext',
    'permissionDenied',
    'machineRequired',
    'teamRequired',
    'regionRequired',
  ];

  for (const key of errorKeys) {
    if (errors[key]) {
      lines.push(`| {{t:cli.errors.${key}}} | {{t:cli.docs.errors.meanings.${key}}} |`);
    }
  }

  lines.push('');
  lines.push('---');
  lines.push('');

  // --- Output Formats ---
  lines.push('## {{t:cli.docs.outputFormats.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.outputFormats.text}}');
  lines.push('');
  lines.push('```bash');
  lines.push('rdc machine list --output json');
  lines.push('rdc machine list --output yaml');
  lines.push('rdc machine list --output csv');
  lines.push('rdc machine list --output table   # default');
  lines.push('```');
  lines.push('');
  lines.push('{{t:cli.docs.outputFormats.closing}}');
  lines.push('');

  return lines.join('\n');
}

// When run as a script (not imported), write all languages to disk
const isMainModule =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isMainModule) {
  const cliJsonEn = JSON.parse(fs.readFileSync(getCliJsonPath('en'), 'utf-8'));

  // Generate English first (without sourceHash) to compute the hash
  const enContent = generate('en', cliJsonEn);
  const matter = await import('gray-matter');
  const parsed = matter.default(enContent);
  const hash = computeSourceHash(parsed.data, parsed.content);

  // Now generate all languages with sourceHash included
  for (const lang of LANGUAGES) {
    const content = generate(lang, cliJsonEn, { sourceHash: hash });
    fs.writeFileSync(getOutputPath(lang), content, 'utf-8');
    console.log(
      `\x1b[32m✓\x1b[0m Generated ${lang}/cli-application.md (${content.split('\n').length} lines, sourceHash: ${hash})`
    );
  }
}
