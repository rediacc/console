#!/usr/bin/env node
/**
 * CLI Documentation Generator
 *
 * Generates cli-application.md per language from the CLI's i18n source of
 * truth (cli.json).
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
import { LOCAL_GROUPS, toAnchorId, toGroupAnchorId } from './lib/cli-reference-catalog.js';
import { computeSourceHash } from './validate-translation-freshness.js';

import { SITE_LOCALES } from '@rediacc/locales';
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// All supported languages
const LANGUAGES = SITE_LOCALES;

// Path helpers
function getCliJsonPath(lang) {
  return path.resolve(__dirname, `../../cli/src/i18n/locales/${lang}/cli.json`);
}

function getOutputPath(lang) {
  return path.resolve(__dirname, `../src/content/docs/${lang}/cli-application.md`);
}

// Command ordering: groups appear in the generated reference in this order.
const COMMAND_ORDER = [...LOCAL_GROUPS];

// i18n-only groups: keys that exist in cli.json commands but are NOT standalone
// top-level commands. They provide translations used by subcommands of other groups
// (e.g. "sync" translations are used by "repo sync", "backup" by "repo push/pull").
const I18N_ONLY_GROUPS = new Set(['sync', 'backup', 'snapshot']);

// Validate COMMAND_ORDER against actual command groups in cli.json
function validateCommandOrder(commands) {
  const allGroups = new Set(Object.keys(commands));
  const orderedGroups = new Set(COMMAND_ORDER);

  for (const group of allGroups) {
    if (I18N_ONLY_GROUPS.has(group)) continue;
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
  return str.replaceAll(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
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
 * Append one supplement block, plus the blank line that separates it, when the
 * English cli.json actually carries that key. No-op otherwise.
 */
function pushSupplement(lines, docsSupplements, commandPath, type) {
  const supplement = emitSupplement(docsSupplements, commandPath, type);
  if (supplement) {
    lines.push(supplement.trim());
    lines.push('');
  }
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
    for (const sub of node.subcommands ?? []) {
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
  for (const arg of node.arguments ?? []) {
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
  if (!node?.options || node.options.length === 0) return [];
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
  return `"${value.replaceAll('"', '\\"')}"`;
}

/**
 * Generate the markdown content for a given language.
 * Uses the English cli.json for structural discovery (command tree)
 * and the target language's cli.json for frontmatter values.
 * Body content is identical across all languages (uses {{t:}} keys).
 */
export function generate(lang, cliJsonEn, { sourceHash } = {}) {
  const scope = 'local';

  // Load the target language's cli.json for frontmatter
  const langCliJson = JSON.parse(fs.readFileSync(getCliJsonPath(lang), 'utf-8'));
  const docs = langCliJson.docs;

  const commands = cliJsonEn.commands;
  validateCommandOrder(commands);
  const errors = cliJsonEn.errors;
  const docsSupplements = cliJsonEn.docs.supplements;
  const lines = [];

  const fm = docs.frontmatter;

  // --- Frontmatter (translated per language, EXCEPT category) ---
  //
  // `category` is a SCHEMA ENUM, not display text. `src/content/config.ts` declares
  // z.enum(['Tutorials','Guides','Concepts','Reference','Use Cases','Legal']), so emitting
  // the localized value fails the content collection at build time with
  // "Invalid enum value ... received 'مرجع'" and takes the whole site build down, not just
  // that page.
  //
  // This is why the generated docs and the files on disk had drifted apart: the on-disk
  // copies carried the English enum, the generator produced the translated one, and
  // cli-doc-freshness reported the difference every run. Regenerating to satisfy that gate
  // then broke the build, which is the loop this comment exists to stop. The localized
  // string stays in the catalogs for display use; the frontmatter takes the enum from
  // English.
  const categoryEnum = cliJsonEn.docs.frontmatter.category;
  // `subcategory` is a CONSTANT here, and deliberately NOT sourced from cli.json.
  //
  // It is a schema enum that content/config.ts superRefines per category, so a localized
  // value fails the collection exactly as a localized `category` does. Putting it in
  // cli.json would therefore create an obligation to translate a string that must never
  // be translated: check-translation-hashes requires every new cli.json key to appear in
  // all 12 non-English locales, and it flagged this immediately when the first attempt
  // did exactly that.
  //
  // `category` can live in cli.json because its localized value has a real display use
  // elsewhere and the generator simply ignores it. `subcategory` has no such use, so
  // there is nothing for the other locales to legitimately hold.
  //
  // It is emitted at all because www-round5 puts every doc on a shelf: without it this
  // generated page is the one blank card in the Reference browse list, in all 13 locales.
  const subcategoryEnum = 'commands';
  lines.push('---');
  lines.push(`title: ${yamlQuote(fm.title)}`);
  lines.push(`description: ${yamlQuote(fm.description)}`);
  lines.push(`category: ${yamlQuote(categoryEnum)}`);
  if (subcategoryEnum) lines.push(`subcategory: ${subcategoryEnum}`);
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

  // --- Installation & Global Options ---
  lines.push('### {{t:cli.docs.installation.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.installation.text}}');
  lines.push('');
  lines.push('```bash');
  lines.push('# macOS / Linux');
  lines.push('curl -fsSL https://www.rediacc.com | sh');
  lines.push('');
  lines.push('# Or use the packaged binary directly');
  lines.push('./rdc --help');
  lines.push('```');
  lines.push('');

  lines.push('### {{t:cli.docs.globalOptions.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.globalOptions.intro}}');
  lines.push('');
  lines.push('| {{t:cli.docs.tableHeaders.flag}} | {{t:cli.docs.tableHeaders.description}} |');
  lines.push('|------|-------------|');
  lines.push('| `--output` | {{t:cli.options.output}} |');
  lines.push('| `--config` | {{t:cli.options.config}} |');
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
    lines.push(`<a id="${toGroupAnchorId(scope, group)}"></a>`);
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
      lines.push(`<a id="${toAnchorId(scope, group)}"></a>`);
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
        lines.push(`<a id="${toAnchorId(scope, `${group} ${toKebab(subKey)}`)}"></a>`);
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
              lines.push(
                `<a id="${toAnchorId(scope, `${group} ${toKebab(subKey)} ${toKebab(nestedKey)} ${toKebab(l3Key)}`)}"></a>`
              );
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
              pushSupplement(lines, docsSupplements, commandPath, 'tip');
              pushSupplement(lines, docsSupplements, commandPath, 'warning');
              pushSupplement(lines, docsSupplements, commandPath, 'note');
            }
          } else {
            // Leaf command within a sub-group
            const commandPath = `${group}.${subKey}.${nestedKey}`;
            lines.push(
              `<a id="${toAnchorId(scope, `${group} ${toKebab(subKey)} ${toKebab(nestedKey)}`)}"></a>`
            );
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
            pushSupplement(lines, docsSupplements, commandPath, 'tip');
            pushSupplement(lines, docsSupplements, commandPath, 'warning');
            pushSupplement(lines, docsSupplements, commandPath, 'note');
          }
        }
      } else {
        // Leaf command directly under group (e.g., auth.login, machine.list)
        const commandPath = `${group}.${subKey}`;
        lines.push(`<a id="${toAnchorId(scope, `${group} ${toKebab(subKey)}`)}"></a>`);
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
        pushSupplement(lines, docsSupplements, commandPath, 'tip');
        pushSupplement(lines, docsSupplements, commandPath, 'warning');
        pushSupplement(lines, docsSupplements, commandPath, 'note');
      }
    }

    // Group-level tip/warning supplements (applied after all sub-commands)
    pushSupplement(lines, docsSupplements, group, 'tip');
    pushSupplement(lines, docsSupplements, group, 'warning');

    lines.push('---');
    lines.push('');
  }

  // --- Common Error Messages & Output Formats ---
  lines.push('## {{t:cli.docs.errors.heading}}');
  lines.push('');
  lines.push('{{t:cli.docs.errors.intro}}');
  lines.push('');
  lines.push('| {{t:cli.docs.tableHeaders.error}} | {{t:cli.docs.tableHeaders.meaning}} |');
  lines.push('|-------|---------|');

  // Pick the most important/common flat error keys
  const errorKeys = [
    'authRequired',
    'noActiveConfig',
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
  const matter = await import('gray-matter');

  // Generate English first (without sourceHash) to compute the hash
  const enContent = generate('en', cliJsonEn);
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
