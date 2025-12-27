/**
 * Resource Parsers (Bridges, Regions, Storage)
 */

import { extractPrimaryOrSecondary, extractRowsByIndex, extractFirstByIndex } from './base';
import type {
  GetCompanyRegions_ResultSet1,
  GetRegionBridges_ResultSet1,
  GetTeamStorages_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';

// Regions
export function parseGetCompanyRegions(
  response: ApiResponse<GetCompanyRegions_ResultSet1>
): GetCompanyRegions_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((region) => Boolean(region.regionName));
}

// Bridges
export function parseGetRegionBridges(
  response: ApiResponse<GetRegionBridges_ResultSet1>
): GetRegionBridges_ResultSet1[] {
  return extractRowsByIndex<GetRegionBridges_ResultSet1>(response, 1);
}

export function parseCreateBridge(
  response: ApiResponse<GetRegionBridges_ResultSet1>
): GetRegionBridges_ResultSet1 | null {
  return (
    extractFirstByIndex<GetRegionBridges_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetRegionBridges_ResultSet1>(response, 0)
  );
}

// Storage
export function parseGetTeamStorages(
  response: ApiResponse<GetTeamStorages_ResultSet1>
): GetTeamStorages_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((storage) => Boolean(storage.storageName));
}

export function parseCreateStorage(
  response: ApiResponse<GetTeamStorages_ResultSet1>
): GetTeamStorages_ResultSet1 | null {
  return (
    extractFirstByIndex<GetTeamStorages_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetTeamStorages_ResultSet1>(response, 0)
  );
}

export const parseRegionList = parseGetCompanyRegions;
export const parseBridgeList = parseGetRegionBridges;
export const parseStorageList = parseGetTeamStorages;
