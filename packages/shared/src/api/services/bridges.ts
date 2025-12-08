import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { GetRegionBridges_ResultSet1, BridgeAuthorizationToken } from '../../types';
import type {
  WithOptionalVault,
  CreateBridgeParams,
  GetRegionBridgesParams,
  UpdateBridgeNameParams,
  DeleteBridgeParams,
  UpdateBridgeVaultParams,
  ResetBridgeAuthorizationParams,
} from '../../types';

export function createBridgesService(client: ApiClient) {
  return {
    list: async (params: GetRegionBridgesParams): Promise<GetRegionBridges_ResultSet1[]> => {
      const response = await client.get<GetRegionBridges_ResultSet1>('/GetRegionBridges', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetRegionBridges_ResultSet1>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },

    create: (params: WithOptionalVault<CreateBridgeParams>) =>
      client.post('/CreateBridge', {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateBridgeNameParams) => client.post('/UpdateBridgeName', params),

    delete: (params: DeleteBridgeParams) => client.post('/DeleteBridge', params),

    updateVault: (params: UpdateBridgeVaultParams) => client.post('/UpdateBridgeVault', params),

    resetAuthorization: async (params: ResetBridgeAuthorizationParams): Promise<string | null> => {
      const response = await client.post<BridgeAuthorizationToken>(
        '/ResetBridgeAuthorization',
        params
      );

      const token = parseFirst<BridgeAuthorizationToken>(response, {
        extractor: responseExtractors.primaryOrSecondary,
      });

      return token?.authToken ?? null;
    },
  };
}
