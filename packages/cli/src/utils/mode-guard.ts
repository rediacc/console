/**
 * Registry-driven command guard system.
 * Auto-tags help descriptions and applies domain grouping from the registry.
 */

import type { Command } from 'commander';
import { COMMAND_DOMAINS, getCommandDef } from '../config/command-registry.js';
import { t } from '../i18n/index.js';
import { isAgentEnvironment } from './agent-guard.js';

/** Whether to show extended (full) help descriptions instead of summaries. */
let _extendedHelp = false;

/** Format an argument for display (e.g. `<name>`, `[command]`, `<files...>`). */
function humanReadableArgName(arg: {
  name: () => string;
  required: boolean;
  variadic: boolean;
}): string {
  const nameOutput = arg.name() + (arg.variadic ? '...' : '');
  return arg.required ? `<${nameOutput}>` : `[${nameOutput}]`;
}

/** Shared help overrides for subcommand term/description rendering. */
const baseHelpConfig = {
  subcommandTerm(cmd: Command): string {
    // Pad command name so [options] and args align across siblings
    const siblings = cmd.parent?.commands ?? [];
    const maxNameLen = Math.max(...siblings.map((c) => c.name().length));
    const paddedName = cmd.name().padEnd(maxNameLen);
    const alias = cmd.aliases()[0];
    const aliasPart = alias ? `|${alias}` : '';
    const optionsPart = cmd.options.length > 0 ? ' [options]' : '';
    const argsPart = cmd.registeredArguments.map((a) => ` ${humanReadableArgName(a)}`).join('');
    return paddedName + aliasPart + optionsPart + argsPart;
  },
  commandDescription(cmd: Command): string {
    if (_extendedHelp) return cmd.description();
    return cmd.summary() || cmd.description();
  },
  subcommandDescription(cmd: Command): string {
    if (_extendedHelp) return `${cmd.description()}\n`;
    return cmd.summary() || cmd.description();
  },
};

/**
 * Build an optionTerm function that aligns short flags, long flags, and arguments
 * into consistent columns for the given set of options.
 */
function buildOptionTerm(options: { short?: string; long?: string; flags: string }[]) {
  const maxLongLen = Math.max(0, ...options.map((o) => (o.long ?? '').length));

  return (option: { short?: string; long?: string; flags: string }): string => {
    const shortPart = option.short ? `${option.short}, ` : '    ';
    const longFlag = option.long ?? '';
    const paddedLong = longFlag.padEnd(maxLongLen);
    // Extract argument portion (e.g. " <name>", " [value]") from the raw flags
    const argIdx = option.flags.search(/\s+[<[]/);
    const argPart = argIdx >= 0 ? option.flags.slice(argIdx) : '';
    return shortPart + paddedLong + argPart;
  };
}

/** Check if a command is hidden. */
function isHidden(cmd: Command): boolean {
  return (cmd as Command & { _hidden?: boolean })._hidden === true;
}

/** Render a leaf subcommand's details (name, description, options) into lines. */
function renderLeafCommand(lines: string[], fullName: string, sub: Command): void {
  const argsPart = sub.registeredArguments.map((a) => ` ${humanReadableArgName(a)}`).join('');
  lines.push(`  ${fullName}${argsPart}`);

  const desc = sub.description();
  if (desc) {
    lines.push(`    ${desc}`);
  }

  const ownOptions = sub.options.filter((o) => o.long !== '--help' && o.long !== '--team');
  if (ownOptions.length > 0) {
    lines.push('    Options:');
    for (const opt of ownOptions) {
      const req = opt.required ? ' (required)' : '';
      lines.push(`      ${opt.flags}${req}  ${opt.description}`);
    }
  }
  lines.push('');
}

/**
 * Build inline subcommand details for agent-mode help.
 * Recursively flattens all leaf commands so agents can construct
 * the exact command from a single --help invocation (2-hop discovery).
 */
function buildInlineSubcommandDetails(parentCmd: Command): string {
  const lines: string[] = ['\nSubcommand Details:\n'];

  function collectCommands(cmd: Command, prefix: string): void {
    const visibleSubs = cmd.commands.filter((c) => !isHidden(c) && c.name() !== 'help');

    for (const sub of visibleSubs) {
      const fullName = prefix ? `${prefix} ${sub.name()}` : sub.name();
      const childSubs = sub.commands.filter((c) => !isHidden(c) && c.name() !== 'help');
      if (childSubs.length > 0) {
        collectCommands(sub, fullName);
      } else {
        renderLeafCommand(lines, fullName, sub);
      }
    }
  }

  collectCommands(parentCmd, '');
  return lines.join('\n');
}

/** Recursively apply the help config to a command and all its descendants. */
function applyHelpConfig(cmd: Command): void {
  // Hide the legacy parent-scoping options (--team, --region) from help — they're
  // accepted for scripting compatibility but carry no meaning for the local adapter.
  for (const opt of cmd.options) {
    if (opt.long === '--team' || opt.long === '--region') {
      (opt as { hidden?: boolean }).hidden = true;
    }
  }

  cmd.configureHelp({
    ...baseHelpConfig,
    optionTerm: buildOptionTerm([...cmd.options]),
    helpWidth: process.stdout.columns || 80,
  });

  if (cmd.commands.length > 0) {
    if (_extendedHelp && cmd.parent) {
      // Agent mode on subcommands: inline all subcommand details (hop 2)
      // Skip root command — its long descriptions are enough for group selection (hop 1)
      cmd.addHelpText('after', buildInlineSubcommandDetails(cmd));
    } else if (!_extendedHelp) {
      // Human mode: hint about --help-all
      cmd.addHelpText('after', `\n  ${t('help.useHelpAll')}\n`);
    }
  }

  for (const sub of cmd.commands) {
    applyHelpConfig(sub);
  }
}

/** Apply registry definition to a single command. */
function applyCommandDef(cmd: Command, def: ReturnType<typeof getCommandDef> & object): void {
  // Domain grouping via Commander.js helpGroup()
  cmd.helpGroup(COMMAND_DOMAINS[def.domain]);
}

/**
 * Apply the command registry to the CLI instance.
 * Sets help group headings, mode guards, and a custom help formatter that
 * renders mode tags as a separate column.
 */
export function applyRegistry(cli: Command): void {
  // Detect --help-all: replace with --help so Commander's built-in help machinery fires
  const helpAllIdx = process.argv.indexOf('--help-all');
  if (helpAllIdx !== -1) {
    _extendedHelp = true;
    process.argv[helpAllIdx] = '--help';
  }

  // AI agents always get extended help
  if (isAgentEnvironment()) {
    _extendedHelp = true;
  }

  for (const cmd of cli.commands) {
    const def = getCommandDef(cmd.name());
    if (!def) continue;

    applyCommandDef(cmd, def);
  }

  // Apply custom help formatting to the entire command tree
  applyHelpConfig(cli);
}
