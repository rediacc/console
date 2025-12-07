import { Command } from 'commander';
import { api } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { createResourceCommands } from '../utils/commandFactory.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type {
  GetRegionBridgesParams,
  CreateBridgeParams,
  UpdateBridgeNameParams,
  DeleteBridgeParams,
  UpdateBridgeVaultParams,
  ResetBridgeAuthorizationParams,
} from '@rediacc/shared/types';

export function registerBridgeCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const bridge = createResourceCommands(program, {
    resourceName: 'bridge',
    resourceNamePlural: 'bridges',
    nameField: 'bridgeName',
    parentOption: 'region',
    operations: {
      list: (params) => api.bridges.list({ regionName: params?.regionName as string }),
      create: (payload) => api.bridges.create(payload as unknown as CreateBridgeParams),
      rename: (payload) => api.bridges.rename(payload as unknown as UpdateBridgeNameParams),
      delete: (payload) => api.bridges.delete(payload as unknown as DeleteBridgeParams),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Bridge',
    },
    vaultUpdateConfig: {
      update: (payload) => api.bridges.updateVault(payload as unknown as UpdateBridgeVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add custom reset-auth command
  bridge
    .command('reset-auth <name>')
    .description('Reset bridge authorization token')
    .option('-r, --region <name>', 'Region name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.region) {
          outputService.error('Region name required. Use --region or set context.');
          process.exit(1);
        }

        const authToken = await withSpinner(
          `Resetting authorization for bridge "${name}"...`,
          () => api.bridges.resetAuthorization({ bridgeName: name, isCloudManaged: false }),
          'Authorization reset'
        );

        if (authToken) {
          outputService.success(`New token: ${authToken}`);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
