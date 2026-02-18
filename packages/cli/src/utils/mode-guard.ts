/**
 * Mode-aware command guard system.
 * Blocks commands from running in unsupported modes and auto-tags help descriptions.
 * Hides experimental (cloud) commands unless --experimental or REDIACC_EXPERIMENTAL=1.
 */
import { DEFAULTS } from '@rediacc/shared/config';
import {
  ALL_MODES,
  COMMAND_DOMAINS,
  formatModeTag,
  getCommandDef,
  isExperimentalEnabled,
  type ModeSet,
  type SubcommandDef,
} from '../config/command-registry.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import type { Command } from 'commander';

// Fixed column width for the mode tag (longest tag is "[cloud|local|s3]" = 16 chars + padding)
const TAG_COL_WIDTH = 19;

/**
 * Add a preAction hook that blocks the command in unsupported modes.
 */
export function addModeGuard(command: Command, supportedModes: ModeSet): void {
  // All-modes commands don't need a guard
  if (supportedModes.length >= ALL_MODES.length) return;

  command.hook('preAction', async () => {
    const context = await contextService.getCurrent();
    const mode = context?.mode ?? DEFAULTS.CONTEXT.MODE;

    if (!supportedModes.includes(mode)) {
      const tag = formatModeTag(supportedModes);
      outputService.error(
        `"${command.name()}" is only available in ${supportedModes.join(' or ')} mode ${tag}. Current mode: ${mode}`
      );
      process.exit(1);
    }
  });
}

/**
 * Add a preAction hook that blocks the command when experimental mode is not enabled.
 */
function addExperimentalGuard(command: Command): void {
  command.hook('preAction', () => {
    if (!isExperimentalEnabled()) {
      outputService.error(
        `"${command.name()}" is an experimental command. Enable with --experimental flag or REDIACC_EXPERIMENTAL=1 environment variable.`
      );
      process.exit(1);
    }
  });
}

/**
 * Resolve the mode tag for a command by checking the registry.
 * Handles both top-level commands and subcommands (via parent lookup).
 */
function resolveTag(cmd: Command): string {
  // Top-level command?
  const def = getCommandDef(cmd.name());
  if (def) return formatModeTag(def.modes);

  // Subcommand — check parent's subcommand overrides, then inherit parent modes
  const parentDef = cmd.parent ? getCommandDef(cmd.parent.name()) : undefined;
  if (parentDef?.subcommands?.[cmd.name()]) {
    return formatModeTag(parentDef.subcommands[cmd.name()].modes);
  }
  if (parentDef) {
    return formatModeTag(parentDef.modes);
  }

  return '';
}

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
  subcommandDescription(cmd: Command): string {
    const tag = resolveTag(cmd);
    const desc = cmd.description();
    const tagCol = (tag || '').padEnd(TAG_COL_WIDTH);
    return `${tagCol}${desc}`;
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

/** Recursively apply the help config to a command and all its descendants. */
function applyHelpConfig(cmd: Command): void {
  cmd.configureHelp({
    ...baseHelpConfig,
    optionTerm: buildOptionTerm([...cmd.options]),
  });
  for (const sub of cmd.commands) {
    applyHelpConfig(sub);
  }
}

/** Apply subcommand-level mode guards for override entries. */
function applySubcommandGuards(cmd: Command, subcommands: Record<string, SubcommandDef>): void {
  for (const sub of cmd.commands) {
    const subDef = subcommands[sub.name()] as SubcommandDef | undefined;
    if (!subDef) continue;
    addModeGuard(sub, subDef.modes);

    if (subDef.experimental) {
      addExperimentalGuard(sub);
    }
  }
}

/** Hide experimental subcommands from help output. */
function applyExperimentalHiding(cmd: Command, subcommands: Record<string, SubcommandDef>): void {
  for (const sub of cmd.commands) {
    const subDef = subcommands[sub.name()] as SubcommandDef | undefined;
    if (subDef?.experimental) {
      (sub as Command & { _hidden: boolean })._hidden = true;
    }
  }
}

/** Apply registry definition to a single command. */
function applyCommandDef(
  cmd: Command,
  def: ReturnType<typeof getCommandDef> & object,
  experimental: boolean
): void {
  // Domain grouping via Commander.js helpGroup()
  cmd.helpGroup(COMMAND_DOMAINS[def.domain]);

  // Hide and guard experimental commands
  if (def.experimental) {
    addExperimentalGuard(cmd);
    if (!experimental) {
      (cmd as Command & { _hidden: boolean })._hidden = true;
    }
  }

  // Top-level mode guard
  addModeGuard(cmd, def.modes);

  // Subcommand-level mode and experimental guards
  if (def.subcommands) {
    applySubcommandGuards(cmd, def.subcommands);
    if (!experimental) {
      applyExperimentalHiding(cmd, def.subcommands);
    }
  }
}

/**
 * Apply the command registry to the CLI instance.
 * Sets help group headings, mode guards, experimental guards, and a custom
 * help formatter that renders mode tags as a separate column.
 */
export function applyRegistry(cli: Command): void {
  const experimental = isExperimentalEnabled();

  for (const cmd of cli.commands) {
    const def = getCommandDef(cmd.name());
    if (!def) continue;

    applyCommandDef(cmd, def, experimental);
  }

  // Apply custom help formatting to the entire command tree
  applyHelpConfig(cli);
}
