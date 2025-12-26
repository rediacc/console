/**
 * Procedure Default Values
 *
 * Centralized defaults for stored procedure parameters.
 * Applied automatically by createTypedApi when parameters are missing.
 */

import type { StoredProcedureName } from '../../types/api-schema.generated';

type ProcedureDefaults = Partial<Record<StoredProcedureName, Record<string, unknown>>>;

/**
 * Map of procedure names to their default parameter values.
 * These defaults are applied when calling procedures through TypedApi.
 *
 * User-provided values always take precedence over defaults.
 */
export const PROCEDURE_DEFAULTS: ProcedureDefaults = {
  // Resource creation with optional vault
  CreateBridge: { vaultContent: '{}' },
  CreateMachine: { vaultContent: '{}' },
  CreateRegion: { vaultContent: '{}' },
  CreateRepository: { vaultContent: '{}' },
  CreateStorage: { vaultContent: '{}' },
  CreateTeam: { vaultContent: '{}' },
  // Ceph resources
  CreateCephCluster: { vaultContent: '{}' },
  CreateCephPool: { vaultContent: '{}' },
  CreateCephRbdImage: { vaultContent: '{}' },
  CreateCephRbdSnapshot: { vaultContent: '{}' },
  CreateCephRbdClone: { vaultContent: '{}' },
} as const;

/**
 * Apply default values to procedure parameters.
 * User-provided values take precedence over defaults.
 * Undefined values in params do NOT override defaults.
 */
export function applyProcedureDefaults<P extends StoredProcedureName>(
  procedureName: P,
  params: Record<string, unknown> | undefined
): Record<string, unknown> {
  const defaults = PROCEDURE_DEFAULTS[procedureName];
  if (!defaults) return params ?? {};

  // Filter out undefined values from params so they don't override defaults
  const definedParams: Record<string, unknown> = {};
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        definedParams[key] = value;
      }
    }
  }

  return { ...defaults, ...definedParams };
}
