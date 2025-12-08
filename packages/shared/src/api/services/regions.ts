import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  CreateRegionParams,
  DeleteRegionParams,
  GetCompanyRegions_ResultSet1,
  GetRegionBridges_ResultSet1,
  GetRegionBridgesParams,
  UpdateRegionNameParams,
  UpdateRegionVaultParams,
  WithOptionalVault,
} from '../../types';

export function createRegionsService(client: ApiClient) {
  return {
    list: async (): Promise<GetCompanyRegions_ResultSet1[]> => {
      const response = await client.get<GetCompanyRegions_ResultSet1>('/GetCompanyRegions');
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

    getBridges: async (params: GetRegionBridgesParams): Promise<GetRegionBridges_ResultSet1[]> => {
      const response = await client.get<GetRegionBridges_ResultSet1>('/GetRegionBridges', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetRegionBridges_ResultSet1>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },
  };
}
