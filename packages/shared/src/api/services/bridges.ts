import { endpoints } from '../../endpoints';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Bridge, BridgeAuthorizationToken } from '../../types';
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
    list: async (params: GetRegionBridgesParams): Promise<Bridge[]> => {
      const response = await client.get<Bridge>(endpoints.regions.getRegionBridges, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Bridge>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },

    create: (params: WithOptionalVault<CreateBridgeParams>) =>
      client.post(endpoints.bridges.createBridge, {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      }),

    rename: (params: UpdateBridgeNameParams) =>
      client.post(endpoints.bridges.updateBridgeName, params),

    delete: (params: DeleteBridgeParams) =>
      client.post(endpoints.bridges.deleteBridge, params),

    updateVault: (params: UpdateBridgeVaultParams) =>
      client.post(endpoints.bridges.updateBridgeVault, params),

    resetAuthorization: async (params: ResetBridgeAuthorizationParams): Promise<string | null> => {
      const response = await client.post<BridgeAuthorizationToken>(
        endpoints.bridges.resetBridgeAuthorization,
        params
      );

      const token = parseFirst<BridgeAuthorizationToken>(response, {
        extractor: responseExtractors.primaryOrSecondary,
      });

      return token?.authToken ?? null;
    },
  };
}
