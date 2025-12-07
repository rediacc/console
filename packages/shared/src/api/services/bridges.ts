import { endpoints } from '../../endpoints';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Bridge, BridgeAuthorizationToken } from '../../types';

export function createBridgesService(client: ApiClient) {
  return {
    list: async (regionName: string): Promise<Bridge[]> => {
      const response = await client.get<Bridge>(endpoints.regions.getRegionBridges, { regionName });
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Bridge>(1),
        filter: (bridge) => Boolean(bridge.bridgeName),
      });
    },

    create: (regionName: string, bridgeName: string, vaultContent?: string) =>
      client.post(endpoints.bridges.createBridge, {
        regionName,
        bridgeName,
        vaultContent: vaultContent ?? '{}',
      }),

    rename: (regionName: string, currentName: string, newName: string) =>
      client.post(endpoints.bridges.updateBridgeName, {
        regionName,
        currentBridgeName: currentName,
        newBridgeName: newName,
      }),

    delete: (regionName: string, bridgeName: string) =>
      client.post(endpoints.bridges.deleteBridge, { regionName, bridgeName }),

    updateVault: (regionName: string, bridgeName: string, vault: string, vaultVersion: number) =>
      client.post(endpoints.bridges.updateBridgeVault, {
        regionName,
        bridgeName,
        vaultContent: vault,
        vaultVersion,
      }),

    resetAuthorization: async (regionName: string, bridgeName: string): Promise<string | null> => {
      const response = await client.post<BridgeAuthorizationToken>(
        endpoints.bridges.resetBridgeAuthorization,
        {
          regionName,
          bridgeName,
        }
      );

      const token = parseFirst<BridgeAuthorizationToken>(response, {
        extractor: responseExtractors.primaryOrSecondary,
      });

      return token?.authToken ?? null;
    },
  };
}
