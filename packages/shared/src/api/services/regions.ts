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
      const response = await client.get<Region>('/GetCompanyRegions');
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (region) => Boolean(region.regionName),
      });
    },

    create: (params: WithOptionalVault<CreateRegionParams>) =>
      client.post('/CreateRegion', {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateRegionNameParams) => client.post('/UpdateRegionName', params),

    delete: (params: DeleteRegionParams) => client.post('/DeleteRegion', params),

    updateVault: (params: UpdateRegionVaultParams) => client.post('/UpdateRegionVault', params),

    getBridges: async (params: GetRegionBridgesParams): Promise<Bridge[]> => {
      const response = await client.get<Bridge>('/GetRegionBridges', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Bridge>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },
  };
}
