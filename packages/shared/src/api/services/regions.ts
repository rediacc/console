import { endpoints } from '../../endpoints';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Bridge, Region } from '../../types';
import type {
  WithOptionalVault,
  CreateRegionParams,
  UpdateRegionNameParams,
  DeleteRegionParams,
  UpdateRegionVaultParams,
  GetRegionBridgesParams,
} from '../../types';

export function createRegionsService(client: ApiClient) {
  return {
    list: async (): Promise<Region[]> => {
      const response = await client.get<Region>(endpoints.company.getCompanyRegions);
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (region) => Boolean(region.regionName),
      });
    },

    create: (params: WithOptionalVault<CreateRegionParams>) =>
      client.post(endpoints.regions.createRegion, {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateRegionNameParams) =>
      client.post(endpoints.regions.updateRegionName, params),

    delete: (params: DeleteRegionParams) =>
      client.post(endpoints.regions.deleteRegion, params),

    updateVault: (params: UpdateRegionVaultParams) =>
      client.post(endpoints.regions.updateRegionVault, params),

    getBridges: async (params: GetRegionBridgesParams): Promise<Bridge[]> => {
      const response = await client.get<Bridge>(endpoints.regions.getRegionBridges, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Bridge>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },
  };
}
