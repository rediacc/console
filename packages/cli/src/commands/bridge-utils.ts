import type { Command } from 'commander';

/**
 * Convert camelCase to kebab-case for CLI option names.
 * e.g. ownerUid → owner-uid, mountPoint → mount-point
 */
export function camelToKebab(str: string): string {
  return str
    .replaceAll(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replaceAll(/([A-Z])([A-Z][a-z])/g, '$1-$2')
    .toLowerCase();
}

/**
 * Convert kebab-case back to camelCase for reading parsed Commander options.
 * e.g. owner-uid → ownerUid, mount-point → mountPoint
 */
export function kebabToCamel(str: string): string {
  return str.replaceAll(/-([a-z])/g, (_, c) => c.toUpperCase());
}

/**
 * Find an existing child command by name, or create a new one.
 * Essential for sharing command groups between bridge and metadata commands.
 */
export function getOrCreateCommand(parent: Command, name: string, description?: string): Command {
  const existing = parent.commands.find((c) => c.name() === name);
  if (existing) return existing;
  const cmd = parent.command(name);
  if (description) cmd.description(description);
  return cmd;
}
