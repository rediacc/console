import { Command } from 'commander';
import {
  parseGetRegionBridges,
  parseGetOrganizationVaults,
  parseCreateBridge,
  extractPrimaryOrSecondary,
} from '@rediacc/shared/api';
import type {
  GetOrganizationVaults_ResultSet1,
  CreateBridgeParams,
  DeleteBridgeParams,
  UpdateBridgeNameParams,
  UpdateBridgeVaultParams,
} from '@rediacc/shared/types';
import { t } from '../i18n/index.js';
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
    }),
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetOrganizationVaults({});
        const vaults = parseGetOrganizationVaults(response as never);
        return vaults as unknown as (GetOrganizationVaults_ResultSet1 & { vaultType?: string })[];
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
    .description(t('commands.bridge.resetAuth.description'))
    .option('-r, --region <name>', t('options.region'))
    .action(async (name: string, options: { region?: string }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.region) {
          throw new ValidationError(t('errors.regionRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.bridge.resetAuth.resetting', { name }),
          () => typedApi.ResetBridgeAuthorization({ bridgeName: name, isCloudManaged: false }),
          t('commands.bridge.resetAuth.success')
        );

        // Extract token from response
        const tokenData = extractPrimaryOrSecondary(apiResponse as never)[0] as
          | { authToken?: string }
          | undefined;
        const authToken = tokenData?.authToken ?? null;

        if (authToken) {
          outputService.success(t('commands.bridge.resetAuth.newToken', { token: authToken }));
        }
      } catch (error) {
        handleError(error);
      }
    });
}
