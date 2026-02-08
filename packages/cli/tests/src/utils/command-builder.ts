/**
 * Command builder for unified CLI test infrastructure.
 *
 * Constructs CLI argument arrays from a base command, a TestContext,
 * and optional flag overrides — so shared scenarios don't need to know
 * whether they're running in cloud or local mode.
 */
import type { TestContext } from './TestContext';

/**
 * Build a CLI argument array by appending context-derived flags and
 * user-supplied overrides to a base command.
 *
 * Context flags (--team, --machine) are only added when the context
 * provides them. Flags with `undefined` values are silently skipped.
 *
 * @param base    Base command tokens, e.g. ['repository', 'create', name]
 * @param ctx     TestContext providing team/machine defaults
 * @param flags   Optional key-value overrides (--key value)
 * @returns Complete argument array ready for runner.run()
 *
 * @example
 * buildCommand(['repository', 'create', 'myrepo'], ctx, { size: '4G' })
 * // → ['repository', 'create', 'myrepo', '--team', 'default', '--machine', 'vm1', '--size', '4G']
 */
export function buildCommand(
  base: string[],
  ctx: TestContext,
  flags?: Record<string, string | undefined>
): string[] {
  const args = [...base];

  if (ctx.teamName) {
    args.push('--team', ctx.teamName);
  }

  if (ctx.machineName) {
    args.push('--machine', ctx.machineName);
  }

  if (flags) {
    for (const [key, value] of Object.entries(flags)) {
      if (value !== undefined) {
        args.push(`--${key}`, value);
      }
    }
  }

  return args;
}

/**
 * Build a CLI argument array for delete operations.
 *
 * Note: bridge-generated commands do NOT support `--force`.
 * Callers must ensure resources are stopped/unmounted before deletion.
 */
export function buildDeleteCommand(
  base: string[],
  ctx: TestContext,
  flags?: Record<string, string | undefined>
): string[] {
  return buildCommand(base, ctx, flags);
}
