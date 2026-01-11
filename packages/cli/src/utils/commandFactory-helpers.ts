/**
 * Helper utilities for the command factory
 * Extracted to reduce file size of commandFactory.ts
 */

import type { GetOrganizationVaults_ResultSet1 } from '@rediacc/shared/types';
import { searchInFields, compareValues } from '@rediacc/shared/utils';

/**
 * Parent context options for commands
 */
export interface ParentContextOptions extends Record<string, unknown> {
  team?: string;
  region?: string;
}

export type ParentOptionType = 'team' | 'region' | 'none';

export function getParentFlag(parentOption: ParentOptionType): string {
  if (parentOption === 'team') return '-t, --team <name>';
  if (parentOption === 'region') return '-r, --region <name>';
  return '';
}

export function getParentDesc(parentOption: ParentOptionType): string {
  if (parentOption === 'team') return 'Team name';
  if (parentOption === 'region') return 'Region name';
  return '';
}

export function getParentKey(parentOption: ParentOptionType): string {
  return parentOption === 'team' ? 'teamName' : 'regionName';
}

export function getParentValue(
  opts: ParentContextOptions,
  parentOption: ParentOptionType
): unknown {
  return parentOption === 'team' ? opts.team : opts.region;
}

export function capitalizeFirst(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

export function extractItemsFromResponse(response: unknown): Record<string, unknown>[] {
  if (Array.isArray(response)) {
    return response as Record<string, unknown>[];
  }
  if (Array.isArray((response as { items?: unknown[] }).items)) {
    return (response as { items: unknown[] }).items as Record<string, unknown>[];
  }
  return [];
}

export function applySearchFilter(
  items: Record<string, unknown>[],
  searchText: string | undefined,
  nameField: string
): Record<string, unknown>[] {
  if (!searchText) return items;
  return items.filter((item) => searchInFields(item, searchText, [nameField]));
}

export function applySorting(
  items: Record<string, unknown>[],
  sortField: string | undefined,
  descending: boolean
): Record<string, unknown>[] {
  if (!sortField) return items;
  return [...items].sort((a, b) => {
    const result = compareValues(a[sortField], b[sortField]);
    return descending ? -result : result;
  });
}

export async function readVaultFromStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf-8').trim();
}

export function validateJsonVault(vaultData: string): boolean {
  try {
    JSON.parse(vaultData);
    return true;
  } catch {
    return false;
  }
}

export function buildListParams(
  hasParent: boolean,
  parentOption: ParentOptionType,
  opts: ParentContextOptions
): Record<string, unknown> {
  if (!hasParent) return {};
  return { [getParentKey(parentOption)]: getParentValue(opts, parentOption) };
}

export function buildCreatePayload(
  name: string,
  nameField: string,
  parentOption: ParentOptionType,
  opts: ParentContextOptions,
  hasParent: boolean,
  transformFn?: (name: string, opts: ParentContextOptions) => Record<string, unknown>
): Record<string, unknown> {
  if (transformFn) {
    return transformFn(name, opts);
  }
  if (hasParent) {
    return {
      [nameField]: name,
      [getParentKey(parentOption)]: getParentValue(opts, parentOption),
    };
  }
  return { [nameField]: name };
}

export function addParentToPayload(
  payload: Record<string, unknown>,
  hasParent: boolean,
  parentOption: ParentOptionType,
  opts: ParentContextOptions
): void {
  if (hasParent) {
    payload[getParentKey(parentOption)] = getParentValue(opts, parentOption);
  }
}

export type VaultItem = GetOrganizationVaults_ResultSet1 & { vaultType?: string };

export function extractVaultsArray(response: unknown): VaultItem[] {
  if (Array.isArray(response)) {
    return response as VaultItem[];
  }
  if (Array.isArray((response as { vaults?: VaultItem[] }).vaults)) {
    return (response as { vaults: VaultItem[] }).vaults;
  }
  return [];
}

export interface CreateOption {
  flags: string;
  description: string;
  required?: boolean;
}

export function checkRequiredCreateOptions(
  createOptions: CreateOption[] | undefined,
  opts: ParentContextOptions
): { valid: boolean; errorMessage?: string } {
  if (!createOptions) return { valid: true };
  for (const opt of createOptions) {
    if (opt.required) {
      const optName = /--(\w+)/.exec(opt.flags)?.[1];
      if (optName && !opts[optName]) {
        return {
          valid: false,
          errorMessage: `${capitalizeFirst(optName)} name required. Use --${optName}.`,
        };
      }
    }
  }
  return { valid: true };
}
