import { Command } from 'commander';
import type { CompanyVaultRecord } from '@rediacc/shared/types';
import { handleError } from './errors.js';
import { withSpinner } from './spinner.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';

/**
 * Configuration for a standard resource CRUD command set
 */
interface ParentContextOptions extends Record<string, unknown> {
  team?: string;
  region?: string;
}

export interface ResourceCommandConfig {
  /** Resource name in singular form (e.g., 'machine', 'team', 'bridge') */
  resourceName: string;
  /** Resource name in plural form (e.g., 'machines', 'teams', 'bridges') */
  resourceNamePlural: string;
  /** Field name used to identify the resource (e.g., 'machineName', 'teamName') */
  nameField: string;
  /** Parent context option - 'team', 'region', or 'none' for top-level resources */
  parentOption: 'team' | 'region' | 'none';
  /** API operations */
  operations: {
    list: (params?: Record<string, unknown>) => Promise<unknown>;
    create: (payload: Record<string, unknown>) => Promise<unknown>;
    rename: (payload: Record<string, unknown>) => Promise<unknown>;
    delete: (payload: Record<string, unknown>) => Promise<unknown>;
  };
  /** Optional: Additional options for create command */
  createOptions?: {
    flags: string;
    description: string;
    required?: boolean;
  }[];
  /** Optional: Transform create payload before sending */
  transformCreatePayload?: (
    name: string,
    opts: ParentContextOptions & Record<string, unknown>
  ) => Record<string, unknown>;
  /** Optional: Vault command configuration */
  vaultConfig?: {
    fetch: (
      params: Record<string, unknown>
    ) => Promise<{ vaults: (CompanyVaultRecord & { vaultType?: string })[] }>;
    vaultType: string;
  };
  /** Optional: Vault update command configuration */
  vaultUpdateConfig?: {
    update: (payload: Record<string, unknown>) => Promise<unknown>;
    vaultFieldName: string;
  };
}

/**
 * Create a parent context validation check
 */
function createParentCheck(parentOption: 'team' | 'region' | 'none') {
  return (opts: ParentContextOptions): boolean => {
    if (parentOption === 'none') {
      return true;
    }
    if (parentOption === 'team' && !opts.team) {
      outputService.error('Team name required. Use --team or set context.');
      return false;
    }
    if (parentOption === 'region' && !opts.region) {
      outputService.error('Region name required. Use --region or set context.');
      return false;
    }
    return true;
  };
}

/**
 * Factory function to create standard CRUD commands for a resource
 *
 * @example
 * ```typescript
 * createResourceCommands(program, {
 *   resourceName: 'machine',
 *   resourceNamePlural: 'machines',
 *   nameField: 'machineName',
 *   parentOption: 'team',
 *   endpoints: {
 *     list: endpoints.machines.getTeamMachines,
 *     create: endpoints.machines.createMachine,
 *     rename: endpoints.machines.updateMachineName,
 *     delete: endpoints.machines.deleteMachine
 *   },
 *   createOptions: [
 *     { flags: '-b, --bridge <name>', description: 'Bridge name', required: true }
 *   ],
 *   transformCreatePayload: (name, opts) => ({
 *     machineName: name,
 *     teamName: opts.team,
 *     bridgeName: opts.bridge
 *   })
 * })
 * ```
 */
export function createResourceCommands(program: Command, config: ResourceCommandConfig): Command {
  const {
    resourceName,
    resourceNamePlural,
    nameField,
    parentOption,
    operations,
    createOptions = [],
    transformCreatePayload,
    vaultConfig,
  } = config;

  const hasParent = parentOption !== 'none';
  const parentFlag =
    parentOption === 'team'
      ? '-t, --team <name>'
      : parentOption === 'region'
        ? '-r, --region <name>'
        : '';
  const parentDesc =
    parentOption === 'team' ? 'Team name' : parentOption === 'region' ? 'Region name' : '';
  const checkParent = createParentCheck(parentOption);

  const resource = program
    .command(resourceName)
    .description(
      `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} management commands`
    );

  // LIST command
  const listCmd = resource.command('list').description(`List ${resourceNamePlural}`);

  if (hasParent) {
    listCmd.option(parentFlag, parentDesc);
  }

  listCmd.action(async (options) => {
    try {
      await authService.requireAuth();
      const opts = hasParent ? await contextService.applyDefaults(options) : options;

      if (!checkParent(opts)) {
        process.exit(1);
      }

      const params = hasParent
        ? parentOption === 'team'
          ? { teamName: opts.team }
          : { regionName: opts.region }
        : {};

      const response = await withSpinner(
        `Fetching ${resourceNamePlural}...`,
        () => operations.list(params),
        `${resourceNamePlural.charAt(0).toUpperCase() + resourceNamePlural.slice(1)} fetched`
      );

      const items = Array.isArray(response)
        ? response
        : Array.isArray((response as { items?: unknown[] }).items)
          ? (response as { items: unknown[] }).items
          : [];
      const format = program.opts().output as OutputFormat;

      outputService.print(items, format);
    } catch (error) {
      handleError(error);
    }
  });

  // CREATE command
  const createCmd = resource.command(`create <name>`).description(`Create a new ${resourceName}`);

  if (hasParent) {
    createCmd.option(parentFlag, parentDesc);
  }

  // Add additional options
  createOptions.forEach((opt) => {
    createCmd.option(opt.flags, opt.description);
  });

  createCmd.action(async (name, options) => {
    try {
      await authService.requireAuth();
      const opts = hasParent ? await contextService.applyDefaults(options) : options;

      if (!checkParent(opts)) {
        process.exit(1);
      }

      // Check required options
      for (const opt of createOptions) {
        if (opt.required) {
          const optName = opt.flags.match(/--(\w+)/)?.[1];
          if (optName && !opts[optName]) {
            outputService.error(
              `${optName.charAt(0).toUpperCase() + optName.slice(1)} name required. Use --${optName}.`
            );
            process.exit(1);
          }
        }
      }

      let payload: Record<string, unknown>;
      if (transformCreatePayload) {
        payload = transformCreatePayload(name, opts);
      } else if (hasParent) {
        payload = {
          [nameField]: name,
          [parentOption === 'team' ? 'teamName' : 'regionName']:
            parentOption === 'team' ? opts.team : opts.region,
        };
      } else {
        payload = { [nameField]: name };
      }

      await withSpinner(
        `Creating ${resourceName} "${name}"...`,
        () => operations.create(payload),
        `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} "${name}" created`
      );
    } catch (error) {
      handleError(error);
    }
  });

  // RENAME command
  const renameCmd = resource
    .command('rename <oldName> <newName>')
    .description(`Rename a ${resourceName}`);

  if (hasParent) {
    renameCmd.option(parentFlag, parentDesc);
  }

  renameCmd.action(async (oldName, newName, options) => {
    try {
      await authService.requireAuth();
      const opts = hasParent ? await contextService.applyDefaults(options) : options;

      if (!checkParent(opts)) {
        process.exit(1);
      }

      const currentField = `current${nameField.charAt(0).toUpperCase() + nameField.slice(1)}`;
      const newField = `new${nameField.charAt(0).toUpperCase() + nameField.slice(1)}`;

      const payload: Record<string, unknown> = {
        [currentField]: oldName,
        [newField]: newName,
      };

      if (hasParent) {
        payload[parentOption === 'team' ? 'teamName' : 'regionName'] =
          parentOption === 'team' ? opts.team : opts.region;
      }

      await withSpinner(
        `Renaming ${resourceName} "${oldName}" to "${newName}"...`,
        () => operations.rename(payload),
        `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} renamed to "${newName}"`
      );
    } catch (error) {
      handleError(error);
    }
  });

  // DELETE command
  const deleteCmd = resource.command('delete <name>').description(`Delete a ${resourceName}`);

  if (hasParent) {
    deleteCmd.option(parentFlag, parentDesc);
  }

  deleteCmd.option('-f, --force', 'Skip confirmation').action(async (name, options) => {
    try {
      await authService.requireAuth();
      const opts = hasParent ? await contextService.applyDefaults(options) : options;

      if (!checkParent(opts)) {
        process.exit(1);
      }

      if (!options.force) {
        const { askConfirm } = await import('./prompt.js');
        const confirm = await askConfirm(
          `Delete ${resourceName} "${name}"? This cannot be undone.`
        );
        if (!confirm) {
          outputService.info('Cancelled');
          return;
        }
      }

      const payload: Record<string, unknown> = { [nameField]: name };

      if (hasParent) {
        payload[parentOption === 'team' ? 'teamName' : 'regionName'] =
          parentOption === 'team' ? opts.team : opts.region;
      }

      await withSpinner(
        `Deleting ${resourceName} "${name}"...`,
        () => operations.delete(payload),
        `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} "${name}" deleted`
      );
    } catch (error) {
      handleError(error);
    }
  });

  // VAULT command (if configured)
  if (vaultConfig || config.vaultUpdateConfig) {
    const vault = resource
      .command('vault')
      .description(
        `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} vault management`
      );

    // Vault GET command
    if (vaultConfig) {
      const getCmd = vault
        .command(`get <${resourceName}Name>`)
        .description(`Get ${resourceName} vault data`);

      if (hasParent) {
        getCmd.option(parentFlag, parentDesc);
      }

      getCmd.action(async (resourceItemName, options) => {
        try {
          await authService.requireAuth();
          const opts = hasParent ? await contextService.applyDefaults(options) : options;

          if (!checkParent(opts)) {
            process.exit(1);
          }

          const params: Record<string, unknown> = {
            [nameField]: resourceItemName,
          };

          if (hasParent) {
            params[parentOption === 'team' ? 'teamName' : 'regionName'] =
              parentOption === 'team' ? opts.team : opts.region;
          }

          const response = await withSpinner(
            `Fetching ${resourceName} vault...`,
            () => vaultConfig.fetch(params),
            'Vault fetched'
          );

          const vaultsArray: (CompanyVaultRecord & { vaultType?: string })[] = Array.isArray(
            response
          )
            ? (response as (CompanyVaultRecord & { vaultType?: string })[])
            : Array.isArray(
                  (response as { vaults?: (CompanyVaultRecord & { vaultType?: string })[] }).vaults
                )
              ? (response as { vaults: (CompanyVaultRecord & { vaultType?: string })[] }).vaults
              : [];
          const targetVault = vaultsArray.find((v) => v.vaultType === vaultConfig.vaultType);
          const format = program.opts().output as OutputFormat;

          if (targetVault) {
            outputService.print(targetVault, format);
          } else {
            outputService.info(`No ${resourceName} vault found`);
          }
        } catch (error) {
          handleError(error);
        }
      });
    }

    // Vault UPDATE command
    if (config.vaultUpdateConfig) {
      const updateCmd = vault
        .command(`update <${resourceName}Name>`)
        .description(`Update ${resourceName} vault data`)
        .option('--vault <json>', 'Vault data as JSON string')
        .option(
          '--vault-version <n>',
          'Current vault version (required for optimistic concurrency)',
          parseInt
        );

      if (hasParent) {
        updateCmd.option(parentFlag, parentDesc);
      }

      updateCmd.action(async (resourceItemName, options) => {
        try {
          await authService.requireAuth();
          const opts = hasParent ? await contextService.applyDefaults(options) : options;

          if (!checkParent(opts)) {
            process.exit(1);
          }

          // Get vault data from --vault flag or stdin
          let vaultData: string = options.vault;
          if (!vaultData && !process.stdin.isTTY) {
            // Read from stdin if not a TTY (piped input)
            const chunks: Buffer[] = [];
            for await (const chunk of process.stdin) {
              chunks.push(chunk);
            }
            vaultData = Buffer.concat(chunks).toString('utf-8').trim();
          }

          if (!vaultData) {
            outputService.error('Vault data required. Use --vault <json> or pipe JSON via stdin.');
            process.exit(1);
          }

          if (options.vaultVersion === undefined || options.vaultVersion === null) {
            outputService.error('Vault version required. Use --vault-version <n>.');
            process.exit(1);
          }

          // Validate JSON
          try {
            JSON.parse(vaultData);
          } catch {
            outputService.error('Invalid JSON vault data.');
            process.exit(1);
          }

          const payload: Record<string, unknown> = {
            [nameField]: resourceItemName,
            [config.vaultUpdateConfig!.vaultFieldName]: vaultData,
            vaultVersion: options.vaultVersion,
          };

          if (hasParent) {
            payload[parentOption === 'team' ? 'teamName' : 'regionName'] =
              parentOption === 'team' ? opts.team : opts.region;
          }

          await withSpinner(
            `Updating ${resourceName} vault...`,
            () => config.vaultUpdateConfig!.update(payload),
            `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} vault updated`
          );
        } catch (error) {
          handleError(error);
        }
      });
    }
  }

  return resource;
}

/**
 * Add a status command to an existing resource command
 */
export function addStatusCommand(
  resourceCommand: Command,
  config: {
    resourceName: string;
    nameField: string;
    parentOption: 'team' | 'region';
    fetch: (params: Record<string, unknown>) => Promise<unknown>;
  }
): void {
  const { resourceName, nameField, parentOption, fetch } = config;
  const parentFlag = parentOption === 'team' ? '-t, --team <name>' : '-r, --region <name>';
  const parentDesc = parentOption === 'team' ? 'Team name' : 'Region name';
  const checkParent = createParentCheck(parentOption);

  resourceCommand
    .command('status <name>')
    .description(`Get ${resourceName} status`)
    .option(parentFlag, parentDesc)
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!checkParent(opts)) {
          process.exit(1);
        }

        const params =
          parentOption === 'team' ? { teamName: opts.team } : { regionName: opts.region };

        const response = await withSpinner(
          `Fetching ${resourceName} status...`,
          () => fetch(params),
          'Status fetched'
        );

        const items: Record<string, unknown>[] = Array.isArray(response)
          ? (response as Record<string, unknown>[])
          : Array.isArray((response as { items?: Record<string, unknown>[] }).items)
            ? (response as { items: Record<string, unknown>[] }).items
            : [];
        const item = items.find((i) => i[nameField] === name);
        const format = resourceCommand.parent?.opts().output as OutputFormat;

        if (item) {
          outputService.print(item, format);
        } else {
          outputService.error(
            `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} "${name}" not found`
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * Add an assign command (e.g., assign-bridge for machines)
 */
export function addAssignCommand(
  resourceCommand: Command,
  config: {
    resourceName: string;
    nameField: string;
    targetName: string;
    targetField: string;
    parentOption: 'team' | 'region';
    perform: (payload: Record<string, unknown>) => Promise<unknown>;
  }
): void {
  const { resourceName, nameField, targetName, targetField, parentOption, perform } = config;
  const parentFlag = parentOption === 'team' ? '-t, --team <name>' : '-r, --region <name>';
  const parentDesc = parentOption === 'team' ? 'Team name' : 'Region name';
  const checkParent = createParentCheck(parentOption);

  resourceCommand
    .command(`assign-${targetName} <${resourceName}Name> <${targetName}Name>`)
    .description(`Assign ${resourceName} to a ${targetName}`)
    .option(parentFlag, parentDesc)
    .action(async (resourceItemName, targetItemName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!checkParent(opts)) {
          process.exit(1);
        }

        await withSpinner(
          `Assigning ${resourceName} "${resourceItemName}" to ${targetName} "${targetItemName}"...`,
          () =>
            perform({
              [nameField]: resourceItemName,
              [targetField]: targetItemName,
              [parentOption === 'team' ? 'teamName' : 'regionName']:
                parentOption === 'team' ? opts.team : opts.region,
            }),
          `${resourceName.charAt(0).toUpperCase() + resourceName.slice(1)} assigned to ${targetName} "${targetItemName}"`
        );
      } catch (error) {
        handleError(error);
      }
    });
}
