import { Command } from 'commander';
import {
  parseGetRegionBridges,
  parseGetCompanyVaults,
  parseCreateBridge,
  extractPrimaryOrSecondary,
} from '@rediacc/shared/api';
import type {
  GetCompanyVaults_ResultSet1,
  CreateBridgeParams,
  DeleteBridgeParams,
  UpdateBridgeNameParams,
  UpdateBridgeVaultParams,
} from '@rediacc/shared/types';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { createResourceCommands } from '../utils/commandFactory.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

export function registerBridgeCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const bridge = createResourceCommands(program, {
    resourceName: 'bridge',
    resourceNamePlural: 'bridges',
    nameField: 'bridgeName',
    parentOption: 'region',
    operations: {
      list: async (params) => {
        const response = await typedApi.GetRegionBridges({
          regionName: params?.regionName as string,
        });
        return parseGetRegionBridges(response as never);
      },
      create: async (payload) => {
        const response = await typedApi.CreateBridge(payload as unknown as CreateBridgeParams);
        return parseCreateBridge(response as never);
      },
      rename: (payload) => typedApi.UpdateBridgeName(payload as unknown as UpdateBridgeNameParams),
      delete: (payload) => typedApi.DeleteBridge(payload as unknown as DeleteBridgeParams),
    },
    transformCreatePayload: (name, opts) => ({
      bridgeName: name,
      regionName: opts.region,
      vaultContent: '{}',
    }),
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetCompanyVaults({});
        const vaults = parseGetCompanyVaults(response as never);
        return vaults as unknown as (GetCompanyVaults_ResultSet1 & { vaultType?: string })[];
      },
      vaultType: 'Bridge',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        typedApi.UpdateBridgeVault(payload as unknown as UpdateBridgeVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add custom reset-auth command
  bridge
    .command('reset-auth <name>')
    .description('Reset bridge authorization token')
    .option('-r, --region <name>', 'Region name')
    .action(async (name: string, options: { region?: string }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.region) {
          throw new ValidationError('Region name required. Use --region or set context.');
        }

        const apiResponse = await withSpinner(
          `Resetting authorization for bridge "${name}"...`,
          () => typedApi.ResetBridgeAuthorization({ bridgeName: name, isCloudManaged: false }),
          'Authorization reset'
        );

        // Extract token from response
        const tokenData = extractPrimaryOrSecondary(apiResponse as never)[0] as
          | { authToken?: string }
          | undefined;
        const authToken = tokenData?.authToken ?? null;

        if (authToken) {
          outputService.success(`New token: ${authToken}`);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
