import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import {
  addParentToPayload,
  applySearchFilter,
  applySorting,
  buildCreatePayload,
  buildListParams,
  capitalizeFirst,
  checkRequiredCreateOptions,
  extractItemsFromResponse,
  extractVaultsArray,
  getParentDesc,
  getParentFlag,
  type ParentContextOptions,
  type ParentOptionType,
  type VaultItem,
} from './commandFactory-helpers.js';
import { getOutputFormat, handleError } from './errors.js';
import { withSpinner } from './spinner.js';

/**
 * Hide the parent option (--team / --region) from help output.
 * These options are accepted for scripting compatibility but clutter help.
 */
function hideParentOption(cmd: Command, parentFlag: string): void {
  const longFlag = /--([\w-]+)/.exec(parentFlag)?.[0];
  if (!longFlag) return;
  const opt = cmd.options.find((o) => o.long === longFlag);
  if (opt) opt.hidden = true;
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
    fetch: (params: Record<string, unknown>) => Promise<VaultItem[] | { vaults: VaultItem[] }>;
    vaultType: string;
  };
}

interface CommandContext {
  hasParent: boolean;
  parentOption: ParentOptionType;
  parentFlag: string;
  parentDesc: string;
  nameField: string;
  resourceName: string;
  resourceNamePlural: string;
}

function setupListCommand(
  resource: Command,
  program: Command,
  ctx: CommandContext,
  operations: ResourceCommandConfig['operations']
): void {
  const listCmd = resource.command('list').description(`List ${ctx.resourceNamePlural}`);
  if (ctx.hasParent) {
    listCmd.option(ctx.parentFlag, ctx.parentDesc);
    hideParentOption(listCmd, ctx.parentFlag);
  }
  listCmd
    .option('--search <text>', t('options.searchInField', { field: ctx.nameField }))
    .option('--sort <field>', t('options.sortByField'))
    .option('--desc', t('options.sortDescending'));
  listCmd.action(async (options) => {
    try {
      const opts = ctx.hasParent ? await configService.applyDefaults(options) : options;
      const params = buildListParams(ctx.hasParent, ctx.parentOption, opts);
      const response = await withSpinner(
        `Fetching ${ctx.resourceNamePlural}...`,
        () => operations.list(params),
        `${capitalizeFirst(ctx.resourceNamePlural)} fetched`
      );

      let items = extractItemsFromResponse(response);
      items = applySearchFilter(items, options.search, ctx.nameField);
      items = applySorting(items, options.sort, options.desc);

      const format = program.opts().output as OutputFormat;
      outputService.print(items, format);
    } catch (error) {
      handleError(error);
    }
  });
}

function setupCreateCommand(
  resource: Command,
  ctx: CommandContext,
  operations: ResourceCommandConfig['operations'],
  createOptions: ResourceCommandConfig['createOptions'],
  transformCreatePayload?: ResourceCommandConfig['transformCreatePayload']
): void {
  const createCmd = resource
    .command('create')
    .description(`Create a new ${ctx.resourceName}`)
    .requiredOption('--name <name>', t('options.name'));
  if (ctx.hasParent) {
    createCmd.option(ctx.parentFlag, ctx.parentDesc);
    hideParentOption(createCmd, ctx.parentFlag);
  }
  createOptions?.forEach((opt) => createCmd.option(opt.flags, opt.description));
  createCmd.action(async (options) => {
    try {
      const name = options.name;
      const opts = ctx.hasParent ? await configService.applyDefaults(options) : options;

      const createCheck = checkRequiredCreateOptions(createOptions, opts);
      if (!createCheck.valid) {
        outputService.error(createCheck.errorMessage!);
        process.exit(1);
      }

      const payload = buildCreatePayload(
        name,
        ctx.nameField,
        ctx.parentOption,
        opts,
        ctx.hasParent,
        transformCreatePayload
      );

      await withSpinner(
        `Creating ${ctx.resourceName} "${name}"...`,
        () => operations.create(payload),
        `${capitalizeFirst(ctx.resourceName)} "${name}" created`
      );
    } catch (error) {
      handleError(error);
    }
  });
}

function setupRenameCommand(
  resource: Command,
  ctx: CommandContext,
  operations: ResourceCommandConfig['operations']
): void {
  const renameCmd = resource
    .command('rename')
    .description(`Rename a ${ctx.resourceName}`)
    .requiredOption('--current-name <name>', t('options.currentName'))
    .requiredOption('--new-name <name>', t('options.newName'));
  if (ctx.hasParent) {
    renameCmd.option(ctx.parentFlag, ctx.parentDesc);
    hideParentOption(renameCmd, ctx.parentFlag);
  }
  renameCmd.action(async (options) => {
    try {
      const oldName = options.currentName;
      const newName = options.newName;
      const opts = ctx.hasParent ? await configService.applyDefaults(options) : options;

      const currentField = `current${capitalizeFirst(ctx.nameField)}`;
      const newField = `new${capitalizeFirst(ctx.nameField)}`;

      const payload: Record<string, unknown> = {
        [currentField]: oldName,
        [newField]: newName,
      };
      addParentToPayload(payload, ctx.hasParent, ctx.parentOption, opts);

      await withSpinner(
        `Renaming ${ctx.resourceName} "${oldName}" to "${newName}"...`,
        () => operations.rename(payload),
        `${capitalizeFirst(ctx.resourceName)} renamed to "${newName}"`
      );
    } catch (error) {
      handleError(error);
    }
  });
}

function setupDeleteCommand(
  resource: Command,
  ctx: CommandContext,
  operations: ResourceCommandConfig['operations']
): void {
  const deleteCmd = resource
    .command('delete')
    .description(`Delete a ${ctx.resourceName}`)
    .requiredOption('--name <name>', t('options.name'));
  if (ctx.hasParent) {
    deleteCmd.option(ctx.parentFlag, ctx.parentDesc);
    hideParentOption(deleteCmd, ctx.parentFlag);
  }
  deleteCmd
    .option('-f, --force', t('options.force'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (options) => {
      try {
        const name = options.name;
        const opts = ctx.hasParent ? await configService.applyDefaults(options) : options;

        const payload: Record<string, unknown> = { [ctx.nameField]: name };
        addParentToPayload(payload, ctx.hasParent, ctx.parentOption, opts);

        if (options.dryRun) {
          outputService.print(
            { dryRun: true, resource: ctx.resourceName, ...payload },
            getOutputFormat()
          );
          return;
        }

        if (!options.force) {
          const { askConfirm } = await import('./prompt.js');
          const confirm = await askConfirm(
            `Delete ${ctx.resourceName} "${name}"? This cannot be undone.`
          );
          if (!confirm) {
            outputService.info(t('status.cancelled'));
            return;
          }
        }

        await withSpinner(
          `Deleting ${ctx.resourceName} "${name}"...`,
          () => operations.delete(payload),
          `${capitalizeFirst(ctx.resourceName)} "${name}" deleted`
        );
      } catch (error) {
        handleError(error);
      }
    });
}

function setupVaultGetCommand(
  vault: Command,
  program: Command,
  ctx: CommandContext,
  vaultConfig: NonNullable<ResourceCommandConfig['vaultConfig']>
): void {
  const getCmd = vault
    .command('get')
    .description(`Get ${ctx.resourceName} vault data`)
    .requiredOption('--name <name>', t('options.name'));
  if (ctx.hasParent) {
    getCmd.option(ctx.parentFlag, ctx.parentDesc);
    hideParentOption(getCmd, ctx.parentFlag);
  }
  getCmd.action(async (options) => {
    const resourceItemName = options.name;
    try {
      const opts = ctx.hasParent ? await configService.applyDefaults(options) : options;
      const params: Record<string, unknown> = { [ctx.nameField]: resourceItemName };
      addParentToPayload(params, ctx.hasParent, ctx.parentOption, opts);

      const response = await withSpinner(
        `Fetching ${ctx.resourceName} vault...`,
        () => vaultConfig.fetch(params),
        'Vault fetched'
      );

      const vaultsArray = extractVaultsArray(response);
      const targetVault = vaultsArray.find((v) => v.vaultType === vaultConfig.vaultType);
      const format = program.opts().output as OutputFormat;

      if (targetVault) {
        outputService.print(targetVault, format);
      } else {
        outputService.info(`No ${ctx.resourceName} vault found`);
      }
    } catch (error) {
      handleError(error);
    }
  });
}

function setupVaultCommands(
  resource: Command,
  program: Command,
  ctx: CommandContext,
  config: ResourceCommandConfig
): void {
  const { vaultConfig } = config;
  if (!vaultConfig) {
    return;
  }

  const vault = resource
    .command('vault')
    .description(`${capitalizeFirst(ctx.resourceName)} vault management`);

  setupVaultGetCommand(vault, program, ctx, vaultConfig);
}

export function createResourceCommands(program: Command, config: ResourceCommandConfig): Command {
  const {
    resourceName,
    resourceNamePlural,
    nameField,
    parentOption,
    operations,
    createOptions = [],
    transformCreatePayload,
  } = config;

  const ctx: CommandContext = {
    hasParent: parentOption !== 'none',
    parentOption,
    parentFlag: getParentFlag(parentOption),
    parentDesc: getParentDesc(parentOption),
    nameField,
    resourceName,
    resourceNamePlural,
  };

  const resource = program
    .command(resourceName)
    .description(t(`commands.${resourceName}.description`));

  setupListCommand(resource, program, ctx, operations);
  setupCreateCommand(resource, ctx, operations, createOptions, transformCreatePayload);
  setupRenameCommand(resource, ctx, operations);
  setupDeleteCommand(resource, ctx, operations);
  setupVaultCommands(resource, program, ctx, config);

  return resource;
}
