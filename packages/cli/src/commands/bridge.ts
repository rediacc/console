import { Command } from 'commander';
import { authService } from '../services/auth.js';
import { api } from '../services/api.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { withSpinner } from '../utils/spinner.js';
import { handleError } from '../utils/errors.js';
import { createResourceCommands } from '../utils/commandFactory.js';
export function registerBridgeCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const bridge = createResourceCommands(program, {
    resourceName: 'bridge',
    resourceNamePlural: 'bridges',
    nameField: 'bridgeName',
    parentOption: 'region',
    operations: {
      list: (params) => api.bridges.list(params?.regionName as string),
      create: (payload) =>
        api.bridges.create(payload.regionName as string, payload.bridgeName as string),
      rename: (payload) =>
        api.bridges.rename(
          payload.regionName as string,
          payload.currentBridgeName as string,
          payload.newBridgeName as string
        ),
      delete: (payload) =>
        api.bridges.delete(payload.regionName as string, payload.bridgeName as string),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Bridge',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        api.bridges.updateVault(
          payload.regionName as string,
          payload.bridgeName as string,
          payload.bridgeVault as string,
          payload.vaultVersion as number
        ),
      vaultFieldName: 'bridgeVault',
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
          () => api.bridges.resetAuthorization(opts.region as string, name),
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
