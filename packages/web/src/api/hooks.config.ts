/**
 * Hook configuration for auto-generated TanStack Query hooks.
 *
 * This file re-exports the JSON configuration with proper TypeScript types.
 * The JSON is read by the C# generator (ReactHooksGeneratorService.cs) to produce
 * api-hooks.generated.ts, and also used at runtime for invalidation lookups.
 */

import config from './hooks.config.json';

export const HOOK_CONFIG = config;
export type HookConfig = typeof HOOK_CONFIG;

// Type-safe helpers for accessing config
export type ProcedureName = keyof typeof config.invalidations;
export type InvalidationKeys = (typeof config.invalidations)[ProcedureName];

/**
 * Get invalidation keys for a procedure.
 */
export function getInvalidationKeys(procedure: string): readonly string[] {
  if (procedure in config.invalidations) {
    return config.invalidations[procedure as ProcedureName];
  }
  return [];
}

/**
 * Get message configuration for a procedure.
 */
export function getMessages(procedure: string): { success?: string; error?: string } | undefined {
  return config.messages[procedure as keyof typeof config.messages];
}

/**
 * Get query options for a procedure.
 */
export function getQueryOptions(
  procedure: string
): { staleTime?: number; refetchInterval?: number } | undefined {
  return config.queryOptions[procedure as keyof typeof config.queryOptions];
}

/**
 * Check if a procedure should be skipped during generation.
 */
export function shouldSkip(procedure: string): boolean {
  return config.skip.includes(procedure);
}
