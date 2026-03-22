#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CLOUD_GROUPS, parseRdcCommand, parseShellTokens } from './lib/cli-reference-catalog.js';
import {
  getAllLandingTerminalCommandsForLanguage,
  getAllLanguages,
  getTranslationTerminalCommands,
} from './lib/landing-terminal-catalog.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MAP_PATH = path.resolve(__dirname, './data/landing-cli-capability-map.json');

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

const MAP_STATUSES = new Set(['supported', 'partial', 'unsupported']);
const EXPERIMENTAL_ROOT_COMMANDS = new Set(CLOUD_GROUPS);

function loadCapabilityMap() {
  if (!fs.existsSync(MAP_PATH)) return { entries: [] };
  const raw = JSON.parse(fs.readFileSync(MAP_PATH, 'utf-8'));
  const entries = Array.isArray(raw.entries) ? raw.entries : [];
  return { entries };
}

function mapBySourceId(entries) {
  const map = new Map();
  for (const entry of entries) map.set(entry.sourceId, entry);
  return map;
}

function addError(errors, rule, file, message, details = null, suggestion = null) {
  errors.push({ rule, file, message, details, suggestion });
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function isNonEmptyStringArray(value) {
  return Array.isArray(value) && value.length > 0 && value.every((item) => isNonEmptyString(item));
}

function validateMapEntryShape(entry) {
  if (!entry || typeof entry !== 'object') return false;
  if (!isNonEmptyString(entry.sourceId)) return false;
  if (!isNonEmptyString(entry.simulatedCommand)) return false;
  if (!MAP_STATUSES.has(entry.status)) return false;
  if (!isNonEmptyStringArray(entry.closestMatches)) return false;
  if (!isNonEmptyStringArray(entry.referenceLinks)) return false;
  if (!isNonEmptyString(entry.capabilityNote)) return false;
  if (!isNonEmptyString(entry.implementationNote)) return false;
  return true;
}

function extractRootCommand(commandText, parsed) {
  if (parsed && typeof parsed.commandPath === 'string' && parsed.commandPath.length > 0) {
    return parsed.commandPath.split(' ')[0];
  }

  const tokens = parseShellTokens(String(commandText || ''));
  if (tokens[0] !== 'rdc') return null;
  for (let i = 1; i < tokens.length; i += 1) {
    const token = tokens[i];
    if (!token.startsWith('-')) return token;
  }
  return null;
}

function isExperimentalCommand(commandText, parsed) {
  const root = extractRootCommand(commandText, parsed);
  return typeof root === 'string' && EXPERIMENTAL_ROOT_COMMANDS.has(root);
}

function validateEnglishCommands(errors, capabilityMap, stats) {
  const commands = getAllLandingTerminalCommandsForLanguage('en');
  const seenSourceIds = new Set();

  for (const item of commands) {
    seenSourceIds.add(item.sourceId);

    if (!item.commandText) {
      addError(
        errors,
        'landing-terminal-command-shape-invalid',
        item.sourcePath,
        'Command line is missing both structured and text command fields',
        JSON.stringify(item.rawLine),
        'Provide cmd/flag/value or text for each command line'
      );
      continue;
    }

    if (!item.isRdcCommand) continue;

    const parsed = parseRdcCommand(item.commandText);
    if (isExperimentalCommand(item.commandText, parsed)) {
      stats.experimentalSkipped += 1;
      continue;
    }

    if (parsed.ok) continue;

    const mapEntry = capabilityMap.get(item.sourceId);
    if (!mapEntry) {
      addError(
        errors,
        'landing-rdc-invalid-unmapped',
        item.sourcePath,
        `Unsupported rdc command is not mapped: ${item.commandText}`,
        parsed.reason,
        'Add a capability map entry with closest match and gap notes'
      );
      continue;
    }

    if (mapEntry.simulatedCommand !== item.commandText) {
      addError(
        errors,
        'landing-rdc-invalid-stale-map',
        item.sourcePath,
        `Mapped command mismatch for ${item.sourceId}`,
        `map: ${mapEntry.simulatedCommand} | current: ${item.commandText}`,
        'Update mapping to the exact current terminal command'
      );
      continue;
    }

    if (!validateMapEntryShape(mapEntry)) {
      addError(
        errors,
        'landing-rdc-map-missing-reference',
        item.sourcePath,
        `Incomplete capability mapping for ${item.sourceId}`,
        JSON.stringify(mapEntry),
        'Fill status, closestMatches, referenceLinks, capabilityNote, implementationNote'
      );
    }
  }

  for (const [sourceId, entry] of capabilityMap.entries()) {
    if (isExperimentalCommand(entry.simulatedCommand, null)) {
      stats.experimentalMapEntries += 1;
      continue;
    }

    if (!seenSourceIds.has(sourceId)) {
      addError(
        errors,
        'landing-rdc-invalid-stale-map',
        sourceId,
        'Capability map entry points to a non-existing terminal command',
        entry.simulatedCommand,
        'Remove stale mapping or update sourceId'
      );
    }
  }
}

function buildTranslationCommandMap(lang) {
  const map = new Map();
  const commands = getTranslationTerminalCommands(lang);
  for (const entry of commands) {
    map.set(entry.sourceId, entry.commandText || '');
  }
  return map;
}

function validateLocaleParity(errors) {
  const baseMap = buildTranslationCommandMap('en');

  for (const lang of getAllLanguages()) {
    if (lang === 'en') continue;
    const langMap = buildTranslationCommandMap(lang);

    for (const [sourceId, enCommand] of baseMap.entries()) {
      if (!langMap.has(sourceId)) {
        addError(
          errors,
          'landing-command-parity-mismatch',
          `${lang}:${sourceId}`,
          'Missing command line in translated terminal content',
          `expected: ${enCommand}`,
          'Mirror English command line structure in this locale'
        );
        continue;
      }

      const other = langMap.get(sourceId);
      if (other !== enCommand) {
        addError(
          errors,
          'landing-command-parity-mismatch',
          `${lang}:${sourceId}`,
          'Translated terminal command differs from English source command',
          `en: ${enCommand} | ${lang}: ${other}`,
          'Keep terminal commands identical across locales'
        );
      }
    }
  }
}

function summarize(entries) {
  const summary = { supported: 0, partial: 0, unsupported: 0 };
  for (const entry of entries) {
    if (entry && MAP_STATUSES.has(entry.status)) summary[entry.status] += 1;
  }
  return summary;
}

function printMappings(mapEntries, includeExperimental = true) {
  if (!Array.isArray(mapEntries) || mapEntries.length === 0) return;

  const filtered = includeExperimental
    ? [...mapEntries]
    : mapEntries.filter((entry) => !isExperimentalCommand(entry.simulatedCommand, null));

  const sorted = filtered.sort((a, b) => {
    if (a.status === b.status) return a.sourceId.localeCompare(b.sourceId);
    const rank = { supported: 0, partial: 1, unsupported: 2 };
    return rank[a.status] - rank[b.status];
  });

  console.log('\n' + colors.bold('Capability Mappings'));
  console.log(colors.dim('-'.repeat(60)));
  for (const entry of sorted) {
    const lead = `[${entry.status}] ${entry.sourceId}`;
    const nearest = Array.isArray(entry.closestMatches) ? entry.closestMatches.join(' | ') : '';
    const exp = isExperimentalCommand(entry.simulatedCommand, null) ? ' (experimental)' : '';
    console.log(colors.cyan(`  ${lead}${exp}`));
    console.log(colors.dim(`    sim: ${entry.simulatedCommand}`));
    if (nearest) console.log(colors.dim(`    closest: ${nearest}`));
  }
}

function printSummary(errors, mapEntries, strictMode, stats) {
  console.log(colors.bold('Landing CLI Usage Validation'));
  console.log('='.repeat(60));

  const nonExperimentalEntries = mapEntries.filter(
    (entry) => !isExperimentalCommand(entry.simulatedCommand, null)
  );
  const s = summarize(nonExperimentalEntries);
  console.log(
    colors.dim(
      `Capability map summary (non-experimental): supported=${s.supported}, partial=${s.partial}, unsupported=${s.unsupported}`
    )
  );
  if (stats.experimentalMapEntries > 0 || stats.experimentalSkipped > 0) {
    console.log(
      colors.dim(
        `Experimental commands excluded from enforcement: mapEntries=${stats.experimentalMapEntries}, terminalRows=${stats.experimentalSkipped}`
      )
    );
  }
  printMappings(mapEntries, true);

  if (strictMode && (s.partial > 0 || s.unsupported > 0)) {
    errors.push({
      rule: 'landing-cli-strict-mode',
      file: 'capability-map',
      message:
        'Strict mode requires all terminal commands to be fully supported (no partial/unsupported mappings).',
      details: `partial=${s.partial}, unsupported=${s.unsupported}`,
      suggestion:
        'Replace simulated commands with real supported commands or implement missing CLI support',
    });
  }

  if (errors.length === 0) {
    console.log(colors.green('✓ Landing terminal command usage is valid.'));
    console.log('='.repeat(60));
    return 0;
  }

  const grouped = new Map();
  for (const error of errors) {
    if (!grouped.has(error.rule)) grouped.set(error.rule, []);
    grouped.get(error.rule).push(error);
  }

  for (const [rule, items] of grouped.entries()) {
    console.log(colors.red(`\n[${rule}] (${items.length} errors)`));
    console.log(colors.dim('-'.repeat(40)));
    for (const item of items) {
      console.log(colors.red(`  ✗ ${item.file}`));
      console.log(colors.dim(`    ${item.message}`));
      if (item.details) console.log(colors.cyan(`    → ${item.details}`));
      if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
    }
  }

  console.log('\n' + '='.repeat(60));
  console.log(colors.red(`✗ Validation failed (${errors.length} errors)`));
  console.log('='.repeat(60));
  return 1;
}

function main() {
  const errors = [];
  const { entries } = loadCapabilityMap();
  const capabilityMap = mapBySourceId(entries);
  const strictMode = true;
  const stats = {
    experimentalSkipped: 0,
    experimentalMapEntries: 0,
  };

  validateEnglishCommands(errors, capabilityMap, stats);
  validateLocaleParity(errors);

  process.exit(printSummary(errors, entries, strictMode, stats));
}

main();
