#!/usr/bin/env node
/**
 * Validates the rdc commands the LANDING pages put in front of a reader.
 *
 * WHICH CORPUS, AND WHY NOT THE OTHER ONE. This gate was written for the animated
 * `terminal.lines` blocks in the locale catalogs plus `heroTerminalLines` in
 * index.astro. Both are gone: the homepage was rebuilt without its terminal demo and
 * the terminal blocks left the catalogs. The gate reported that truthfully and exited
 * 0, which read as coverage for weeks.
 *
 * The commands did not leave the site. They MOVED to `bottomCta.command` -- 23 of them,
 * one per solution/persona page, rendered by SPBottomCta.astro in a copy-me code block,
 * in 13 locales. That is now this gate's corpus.
 *
 * The tutorial STORYBOARDS were considered and deliberately not taken, even though they
 * are a real current source of on-camera commands. `scripts/check-tutorial-commands.ts`
 * already validates them with the same `parseRdcCommand`, field-aware so it reads
 * `commandFull`/`teardownCommand` and never the abbreviated `command` label (measured:
 * 18 storyboards, 101 runnable commands, green). Pointing a second gate at that surface
 * would add zero coverage and a second place to keep an excuse honest -- the exact
 * double-gating `validate-cli-examples.ts` refuses for the same surface.
 *
 * WHAT THIS GATE UNIQUELY OWNS:
 *   1. absolute validity of every landing rdc command against the live command tree;
 *   2. cross-locale parity of those commands across all 13 catalogs;
 *   3. the capability map, the channel for a deliberately-simulated command.
 *
 * (2) alone is not enough and must never be mistaken for coverage: command names are
 * never translated, so a dead flag sits identically in all 13 catalogs in perfect
 * parity. Only (1) can see that.
 *
 * NOT EVERY LANDING COMMAND IS COVERED ELSEWHERE, which is the reason this gate has to
 * exist rather than defer to validate-content-accuracy.js: that one skips any command
 * containing `*` or `?` as a glob, and `rdc config backup-strategy set --cron '0 2 * * *'`
 * -- live on a production page in 13 locales -- goes straight through the hole.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseRdcCommand } from './lib/cli-reference-catalog.js';
import {
  countLandingTerminalSources,
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

/**
 * BLOCKER: three landing CTA commands do not run against the current CLI, and fixing
 * them means editing `bottomCta.command` in all 13 naturalized locale catalogs, which
 * is not this gate's change to make. They are FROZEN here, with evidence, so the gate
 * can be switched on today instead of staying vacuous until someone has time.
 *
 * This is a RATCHET, not an allowlist, and it turns only one way:
 *   - a NEW failing command is RED (that is the whole point);
 *   - a frozen command whose TEXT changes is RED (the entry no longer describes it);
 *   - a frozen command that is FIXED is RED until its entry is deleted, because an
 *     entry that outlives its defect is a standing budget for the next one.
 *
 * Measured 2026-08-27 against packages/cli/scripts/command-tree.json. Each entry
 * carries the parser's own reason and the replacement a fixer should use.
 */
const KNOWN_UNRUNNABLE_CTA_COMMANDS = [
  {
    sourceId: 'solution:retentionCompliance:bottomCta',
    commandText: "rdc config backup-strategy set --cron '0 2 * * *'",
    reason: 'unknown-option',
    evidence:
      'parseRdcCommand resolves the path to `config` only: `backup-strategy set` are excess ' +
      'positionals and `--cron` is not an option of any of them. Note that ' +
      'validate-content-accuracy.js does NOT see this one: its wildcard guard ' +
      '(`/[*?]/.test(text)`) skips the whole command because the cron expression contains ' +
      '`*`, so this gate is the only thing standing over it.',
    fix: 'Replace with a real backup-schedule command, or drop the command block from this CTA.',
  },
  {
    sourceId: 'solution:vulnerabilityManagement:bottomCta',
    commandText: 'rdc term production cve-2026-1234-fix',
    reason: 'excess-positional-args',
    evidence:
      '`rdc term` is a command GROUP and takes 0 positionals; `term connect` is the command.',
    fix: 'rdc term connect production',
  },
  {
    sourceId: 'solution:kubernetesClusterMobility:bottomCta',
    commandText: 'rdc cluster fork prod --tag staging',
    reason: 'missing-mandatory-option',
    evidence: '`cluster fork` requires `--to <dest-cluster>`; the printed form cannot run.',
    fix: 'rdc cluster fork prod --tag staging --to <dest-cluster>',
  },
];

const frozenById = new Map(KNOWN_UNRUNNABLE_CTA_COMMANDS.map((e) => [e.sourceId, e]));

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
  const frozenHit = new Set();
  let rdcChecked = 0;

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
    rdcChecked += 1;

    const parsed = parseRdcCommand(item.commandText);
    const frozen = frozenById.get(item.sourceId);

    if (parsed.ok) {
      // A FIXED command whose freeze entry survives is RED. Without this branch the
      // ratchet only turns one way and a stale entry silently pre-authorises the next
      // breakage at the same source.
      if (frozen) {
        addError(
          errors,
          'landing-rdc-frozen-entry-stale',
          item.sourcePath,
          `KNOWN_UNRUNNABLE_CTA_COMMANDS still freezes ${item.sourceId}, but it now parses`,
          `current: ${item.commandText}`,
          'Delete that entry from validate-landing-cli-usage.js'
        );
      }
      continue;
    }

    if (frozen) {
      if (frozen.commandText !== item.commandText || frozen.reason !== parsed.reason) {
        addError(
          errors,
          'landing-rdc-frozen-entry-stale',
          item.sourcePath,
          `Frozen entry for ${item.sourceId} no longer describes this command`,
          `frozen: ${frozen.commandText} (${frozen.reason}) | current: ${item.commandText} (${parsed.reason})`,
          'Update the frozen entry, or fix the command and delete it'
        );
        continue;
      }
      frozenHit.add(item.sourceId);
      continue;
    }

    // NOTE ON WHAT IS NOT SKIPPED. This used to wave through `excess-positional-args`
    // and `missing-mandatory-option`, on the reasoning that "landing page demos use
    // simplified commands for visual appeal". That was true of the ANIMATED TERMINAL
    // this gate was written for, and it is not true of `bottomCta.command`, which the
    // page presents in a copy-me code block as the command to run. An abbreviated
    // decoration and an unrunnable instruction are different things.
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

  // A frozen entry whose SOURCE is gone is stale too (the CTA was deleted, or the key
  // renamed), and it would otherwise sit here forever describing nothing.
  for (const entry of KNOWN_UNRUNNABLE_CTA_COMMANDS) {
    if (!seenSourceIds.has(entry.sourceId)) {
      addError(
        errors,
        'landing-rdc-frozen-entry-stale',
        entry.sourceId,
        'Frozen entry points at a landing command that no longer exists',
        entry.commandText,
        'Delete that entry from validate-landing-cli-usage.js'
      );
    }
  }

  return { total: commands.length, rdcChecked, frozenHit: frozenHit.size };
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

function printSummary(errors, mapEntries, strictMode, counts) {
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
      `Collected ${counts.total} landing command block(s); ${counts.rdcChecked} are rdc ` +
        `commands and were parsed against the live CLI. Parity checked across ` +
        `${getAllLanguages().length} locales.`
    )
  );
  console.log(
    colors.dim(
      `Frozen unrunnable commands (BLOCKER, ratcheted): ` +
        `${counts.frozenHit}/${KNOWN_UNRUNNABLE_CTA_COMMANDS.length} still present.`
    )
  );
  for (const entry of KNOWN_UNRUNNABLE_CTA_COMMANDS) {
    console.log(colors.dim(`    ${entry.sourceId}: ${entry.commandText}  (${entry.reason})`));
    console.log(colors.dim(`      fix: ${entry.fix}`));
  }
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

  const counts = validateEnglishCommands(errors, capabilityMap);
  validateLocaleParity(errors);

  // ZERO commands has two causes that need opposite responses, and only one of them is
  // "nothing to do". If a landing command SOURCE exists and the collector yields nothing,
  // the collector is broken and reporting success is the empty-scan failure. If no source
  // exists at all, there is genuinely nothing to validate.
  //
  // THIS GATE HAS ALREADY BEEN ON BOTH SIDES OF THAT LINE, which is why the refusal is
  // worth its length. The `terminal.lines` blocks and index.astro's `heroTerminalLines`
  // both went away for real, so the honest answer became "no sources" and the gate exited 0
  // on an empty scan for weeks. It read as coverage. The commands had not left the site,
  // they had MOVED to `bottomCta.command`, which the collector did not know about. So the
  // count below spans EVERY known landing command shape, and adding a shape to the site
  // without adding it here reproduces exactly that failure.
  const sources = countLandingTerminalSources('en');
  const sourceCount =
    (sources.homepageArray ? 1 : 0) + sources.terminalBlocks + sources.ctaCommands;

  if (counts.total === 0) {
    if (sourceCount > 0) {
      console.error('✗ landing-cli-usage found NO commands to check, but a landing command');
      console.error(
        `  SOURCE EXISTS (heroTerminalLines: ${sources.homepageArray}, terminal blocks: ` +
          `${sources.terminalBlocks}, bottomCta commands: ${sources.ctaCommands}).`
      );
      console.error('  The collector is broken.');
      process.exit(1);
    }
    console.error('✗ landing-cli-usage found no landing command sources AT ALL.');
    console.error('  heroTerminalLines is absent from index.astro, the en catalog carries no');
    console.error('  terminal blocks, and no page has a bottomCta.command. That is possible,');
    console.error('  but it is not something to report as a pass: this gate would then be');
    console.error('  green because it has no subject. Retire it, or point it at whatever');
    console.error('  surface now carries the on-page commands.');
    process.exit(1);
  }

  if (counts.rdcChecked === 0) {
    console.error(
      `✗ landing-cli-usage collected ${counts.total} command block(s) and NONE of them is an`
    );
    console.error('  rdc command. Every check below is about rdc syntax, so this run proved');
    console.error('  nothing. Either the collector is reading the wrong field, or the CTA');
    console.error('  commands stopped being rdc commands.');
    process.exit(1);
  }

  process.exit(printSummary(errors, entries, strictMode, counts));
}

main();
