import { endpoints } from '../../endpoints';
import type { Bridge, Region } from '../../types';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';

export function createRegionsService(client: ApiClient) {
  return {
    list: async (): Promise<Region[]> => {
      const response = await client.get<Region>(endpoints.company.getCompanyRegions);
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (region) => Boolean(region.regionName),
      });
    },

    create: (regionName: string) => client.post(endpoints.regions.createRegion, { regionName }),

    rename: (currentName: string, newName: string) =>
      client.post(endpoints.regions.updateRegionName, {
        currentRegionName: currentName,
        newRegionName: newName,
      }),

    delete: (regionName: string) => client.post(endpoints.regions.deleteRegion, { regionName }),

    updateVault: (regionName: string, vault: string, vaultVersion: number) =>
      client.post(endpoints.regions.updateRegionVault, {
        regionName,
        vaultContent: vault,
        vaultVersion,
      }),

    getBridges: async (regionName: string): Promise<Bridge[]> => {
      const response = await client.get<Bridge>(endpoints.regions.getRegionBridges, { regionName });
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Bridge>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },
  };
}
