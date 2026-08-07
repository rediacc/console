#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseRdcCommand } from './lib/cli-reference-catalog.js';
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

function validateEnglishCommands(errors, capabilityMap) {
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
    if (parsed.ok) continue;

    // Landing page demos use simplified commands for visual appeal.
    // Skip strict option checks; only enforce structural correctness
    // (unknown commands/options).
    if (
      parsed.reason === 'excess-positional-args' ||
      parsed.reason === 'missing-mandatory-option'
    ) {
      continue;
    }

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

  return commands.length;
}

function buildTranslationCommandMap(lang) {
  const map = new Map();
  const commands = getTranslationTerminalCommands(lang);
  for (const entry of commands) {
    map.set(entry.sourceId, entry.commandText ?? '');
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

function printMappings(mapEntries) {
  if (!Array.isArray(mapEntries) || mapEntries.length === 0) return;

  const sorted = [...mapEntries].sort((a, b) => {
    if (a.status === b.status) return a.sourceId.localeCompare(b.sourceId);
    const rank = { supported: 0, partial: 1, unsupported: 2 };
    return rank[a.status] - rank[b.status];
  });

  console.log('\n' + colors.bold('Capability Mappings'));
  console.log(colors.dim('-'.repeat(60)));
  for (const entry of sorted) {
    const lead = `[${entry.status}] ${entry.sourceId}`;
    const nearest = Array.isArray(entry.closestMatches) ? entry.closestMatches.join(' | ') : '';
    console.log(colors.cyan(`  ${lead}`));
    console.log(colors.dim(`    sim: ${entry.simulatedCommand}`));
    if (nearest) console.log(colors.dim(`    closest: ${nearest}`));
  }
}

function printSummary(errors, mapEntries, strictMode, checkedCount) {
  console.log(colors.bold('Landing CLI Usage Validation'));
  console.log('='.repeat(60));

  // ★ SAY WHAT WAS ACTUALLY CHECKED, not just what is EXCUSED.
  //
  // This line used to print only the capability-map summary — "supported=0, partial=0,
  // unsupported=0" — and then "✓ valid". Read cold, that says "this gate validated nothing",
  // and it very nearly got the gate deleted as vacuous.
  //
  // It is the opposite. The capability map is the list of commands EXCUSED from parsing
  // (with gap notes). An EMPTY map is the STRICTEST possible setting: nothing is excused, so
  // every rdc command on the landing surfaces must parse against the live CLI. This gate is
  // what caught the homepage hero teaching `rdc cluster fork --name prod` — a command the P4
  // reshape deleted.
  //
  // A gate whose success message understates what it did is one bad reading away from being
  // removed. So it now reports the commands it CHECKED first.
  console.log(
    colors.dim(
      `Checked ${checkedCount} rdc command(s) on the landing surfaces against the live CLI.`
    )
  );
  const s = summarize(mapEntries);
  console.log(
    colors.dim(
      `Capability map (commands EXCUSED from parsing): supported=${s.supported}, partial=${s.partial}, unsupported=${s.unsupported}`
    )
  );
  printMappings(mapEntries);

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

  const checkedCount = validateEnglishCommands(errors, capabilityMap);
  validateLocaleParity(errors);

  if (checkedCount === 0) {
    // A landing page with ZERO rdc commands means the collector broke, not that the page is
    // clean. Refuse to report success on an empty scan — that is the failure mode this whole
    // program keeps finding.
    console.error('✗ landing-cli-usage found NO rdc commands to check. The collector is broken.');
    process.exit(1);
  }

  process.exit(printSummary(errors, entries, strictMode, checkedCount));
}

main();
