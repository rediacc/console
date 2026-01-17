/**
 * Type-safe parameter interfaces for function handlers.
 * These types define what parameters each handler expects from the FunctionSelectionModal.
 */

import type { QueueFunction } from '@rediacc/shared/types';

// ============================================
// Base types
// ============================================

/**
 * Common parameters that appear in most function handlers.
 */
interface BaseHandlerParams {
  /** Repository GUID */
  repository?: string;
  /** Grand repository GUID for forked repos */
  grand?: string;
  /** Option flags (comma-separated or single value) */
  option?: string;
}

// ============================================
// Per-handler typed params
// ============================================

/**
 * Unified parameters for push function handler.
 * Used when pushing a repository to machines or storage systems.
 */
export interface PushFunctionParams extends BaseHandlerParams {
  /** Destination type: machine (SSH) or storage (rclone) */
  destinationType: 'machine' | 'storage';
  /** Single destination (machine name or storage name) */
  to?: string;
  /** Target machines for parallel deployment (array from multi-select) */
  machines?: string[] | string;
  /** Target storage systems for parallel backup (array from multi-select) */
  storages?: string[] | string;
  /** Push destination filename */
  dest?: string;
  /** Deployment/version tag */
  tag?: string;
  /** Repository state: online (mounted) or offline */
  state?: 'online' | 'offline';
  /** CRIU hot backup (zero-downtime) */
  checkpoint?: 'true' | 'false' | boolean;
  /** Overwrite existing backup */
  override?: boolean;
}

/**
 * Parameters for the fork function handler.
 * Used when creating a local copy of a repository.
 * Note: Internally uses the 'backup_push' function.
 */
export interface ForkFunctionParams extends BaseHandlerParams {
  /** Fork tag (required) */
  tag: string;
  /** Repository state: online (mounted) or offline */
  state?: 'online' | 'offline';
}

/**
 * Parameters for the pull function handler.
 * Used when pulling a repository from a storage or machine.
 */
export interface PullFunctionParams extends BaseHandlerParams {
  /** Source type: machine or storage */
  sourceType: 'machine' | 'storage';
  /** Source identifier (machine name or storage name) */
  from: string;
}

/**
 * Parameters for custom/generic function handlers.
 * Allows any parameters to pass through.
 */
export interface CustomFunctionParams {
  [key: string]: unknown;
}

// ============================================
// Typed FunctionData variants
// ============================================

/**
 * Base FunctionData structure (matches existing FunctionData).
 */
export interface BaseFunctionData {
  function: QueueFunction;
  priority: number;
  description: string;
}

/**
 * FunctionData with typed push params.
 * Unified handler for both machine and storage destinations.
 */
export interface PushFunctionData extends BaseFunctionData {
  function: QueueFunction & { name: 'backup_push' };
  params: PushFunctionParams;
}

/**
 * FunctionData with typed fork params.
 * Note: Fork internally uses 'backup_push' function.
 */
export interface ForkFunctionData extends BaseFunctionData {
  function: QueueFunction & { name: 'fork' };
  params: ForkFunctionParams;
}

/**
 * FunctionData with typed pull params.
 */
export interface PullFunctionData extends BaseFunctionData {
  function: QueueFunction & { name: 'backup_pull' };
  params: PullFunctionParams;
}

/**
 * FunctionData with custom/generic params.
 */
export interface CustomFunctionData extends BaseFunctionData {
  params: CustomFunctionParams;
}

// ============================================
// Type guards
// ============================================

/**
 * Check if params contain push-specific fields.
 * @internal Used only by isPushFunctionData
 */
function isPushParams(params: unknown): params is PushFunctionParams {
  return typeof params === 'object' && params !== null && 'destinationType' in params;
}

/**
 * Check if params contain fork-specific fields.
 * @internal Used only by isForkFunctionData
 */
function isForkParams(params: unknown): params is ForkFunctionParams {
  return (
    typeof params === 'object' &&
    params !== null &&
    'tag' in params &&
    !('machines' in params) &&
    !('storages' in params) &&
    !('destinationType' in params)
  );
}

/**
 * Check if params contain pull-specific fields.
 * @internal Used only by isPullFunctionData
 */
function isPullParams(params: unknown): params is PullFunctionParams {
  return (
    typeof params === 'object' && params !== null && 'sourceType' in params && 'from' in params
  );
}

/**
 * Check if function data is for push.
 */
export function isPushFunctionData(
  data: BaseFunctionData & { params: unknown }
): data is PushFunctionData {
  return data.function.name === 'backup_push' && isPushParams(data.params);
}

/**
 * Check if function data is for fork.
 */
export function isForkFunctionData(
  data: BaseFunctionData & { params: unknown }
): data is ForkFunctionData {
  return data.function.name === 'fork' && isForkParams(data.params);
}

/**
 * Check if function data is for pull.
 */
export function isPullFunctionData(
  data: BaseFunctionData & { params: unknown }
): data is PullFunctionData {
  return data.function.name === 'backup_pull' && isPullParams(data.params);
}
