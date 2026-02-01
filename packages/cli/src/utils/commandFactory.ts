import { Command } from 'commander';
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
  getParentKey,
  getParentValue,
  type ParentContextOptions,
  type ParentOptionType,
  readVaultFromStdin,
  type VaultItem,
  validateJsonVault,
} from './commandFactory-helpers.js';
import { handleError } from './errors.js';
import { withSpinner } from './spinner.js';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';

/**
 * Mode-aware authentication helper.
 * Only requires cloud auth for cloud mode. S3/local modes authenticate differently.
 */
async function requireAuthForMode(): Promise<void> {
  const provider = await getStateProvider();
  if (provider.mode === 'cloud') {
    await authService.requireAuth();
  }
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
  /** Optional: Vault update command configuration */
  vaultUpdateConfig?: {
    update: (payload: Record<string, unknown>) => Promise<unknown>;
    vaultFieldName: string;
  };
}

function createParentCheck(parentOption: 'team' | 'region' | 'none') {
  return (opts: ParentContextOptions): boolean => {
    if (parentOption === 'none') return true;
    if (parentOption === 'team' && !opts.team) {
      outputService.error(t('errors.teamRequired'));
      return false;
    }
    if (parentOption === 'region' && !opts.region) {
      outputService.error(t('errors.regionRequired'));
      return false;
    }
    return true;
  };
}

interface CommandContext {
  hasParent: boolean;
  parentOption: ParentOptionType;
  parentFlag: string;
  parentDesc: string;
  checkParent: (opts: ParentContextOptions) => boolean;
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
  if (ctx.hasParent) listCmd.option(ctx.parentFlag, ctx.parentDesc);
  listCmd
    .option('--search <text>', t('options.searchInField', { field: ctx.nameField }))
    .option('--sort <field>', t('options.sortByField'))
    .option('--desc', t('options.sortDescending'));
  listCmd.action(async (options) => {
    try {
      await requireAuthForMode();
      const opts = ctx.hasParent ? await contextService.applyDefaults(options) : options;
      if (!ctx.checkParent(opts)) process.exit(1);
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
    .command('create <name>')
    .description(`Create a new ${ctx.resourceName}`);
  if (ctx.hasParent) createCmd.option(ctx.parentFlag, ctx.parentDesc);
  createOptions?.forEach((opt) => createCmd.option(opt.flags, opt.description));
  createCmd.action(async (name, options) => {
    try {
      await requireAuthForMode();
      const opts = ctx.hasParent ? await contextService.applyDefaults(options) : options;

      if (!ctx.checkParent(opts)) process.exit(1);

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
    .command('rename <oldName> <newName>')
    .description(`Rename a ${ctx.resourceName}`);
  if (ctx.hasParent) renameCmd.option(ctx.parentFlag, ctx.parentDesc);
  renameCmd.action(async (oldName, newName, options) => {
    try {
      await requireAuthForMode();
      const opts = ctx.hasParent ? await contextService.applyDefaults(options) : options;
      if (!ctx.checkParent(opts)) process.exit(1);

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
  const deleteCmd = resource.command('delete <name>').description(`Delete a ${ctx.resourceName}`);
  if (ctx.hasParent) deleteCmd.option(ctx.parentFlag, ctx.parentDesc);
  deleteCmd.option('-f, --force', t('options.force')).action(async (name, options) => {
    try {
      await requireAuthForMode();
      const opts = ctx.hasParent ? await contextService.applyDefaults(options) : options;
      if (!ctx.checkParent(opts)) process.exit(1);
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

      const payload: Record<string, unknown> = { [ctx.nameField]: name };
      addParentToPayload(payload, ctx.hasParent, ctx.parentOption, opts);

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
    .command(`get <${ctx.resourceName}Name>`)
    .description(`Get ${ctx.resourceName} vault data`);
  if (ctx.hasParent) getCmd.option(ctx.parentFlag, ctx.parentDesc);
  getCmd.action(async (resourceItemName, options) => {
    try {
      await requireAuthForMode();
      const opts = ctx.hasParent ? await contextService.applyDefaults(options) : options;
      if (!ctx.checkParent(opts)) process.exit(1);
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

function setupVaultUpdateCommand(
  vault: Command,
  ctx: CommandContext,
  vaultUpdateConfig: NonNullable<ResourceCommandConfig['vaultUpdateConfig']>
): void {
  const updateCmd = vault
    .command(`update <${ctx.resourceName}Name>`)
    .description(`Update ${ctx.resourceName} vault data`)
    .option('--vault <json>', t('options.vaultJson'))
    .option('--vault-version <n>', t('options.vaultVersion'), Number.parseInt);

  if (ctx.hasParent) {
    updateCmd.option(ctx.parentFlag, ctx.parentDesc);
  }

  updateCmd.action(async (resourceItemName, options) => {
    try {
      await requireAuthForMode();
      const opts = ctx.hasParent ? await contextService.applyDefaults(options) : options;

      if (!ctx.checkParent(opts)) {
        process.exit(1);
      }

      let vaultData: string = options.vault;
      if (!vaultData && !process.stdin.isTTY) {
        vaultData = await readVaultFromStdin();
      }

      if (!vaultData) {
        outputService.error(t('errors.vaultDataRequired'));
        process.exit(1);
      }

      if (options.vaultVersion === undefined || options.vaultVersion === null) {
        outputService.error(t('errors.vaultVersionRequired'));
        process.exit(1);
      }

      if (!validateJsonVault(vaultData)) {
        outputService.error(t('errors.invalidJsonVault'));
        process.exit(1);
      }

      const payload: Record<string, unknown> = {
        [ctx.nameField]: resourceItemName,
        [vaultUpdateConfig.vaultFieldName]: vaultData,
        vaultVersion: options.vaultVersion,
      };
      addParentToPayload(payload, ctx.hasParent, ctx.parentOption, opts);

      await withSpinner(
        `Updating ${ctx.resourceName} vault...`,
        () => vaultUpdateConfig.update(payload),
        `${capitalizeFirst(ctx.resourceName)} vault updated`
      );
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
  const { vaultConfig, vaultUpdateConfig } = config;
  if (!vaultConfig && !vaultUpdateConfig) {
    return;
  }

  const vault = resource
    .command('vault')
    .description(`${capitalizeFirst(ctx.resourceName)} vault management`);

  if (vaultConfig) {
    setupVaultGetCommand(vault, program, ctx, vaultConfig);
  }

  if (vaultUpdateConfig) {
    setupVaultUpdateCommand(vault, ctx, vaultUpdateConfig);
  }
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
    checkParent: createParentCheck(parentOption),
    nameField,
    resourceName,
    resourceNamePlural,
  };

  const resource = program
    .command(resourceName)
    .description(`${capitalizeFirst(resourceName)} management commands`);

  setupListCommand(resource, program, ctx, operations);
  setupCreateCommand(resource, ctx, operations, createOptions, transformCreatePayload);
  setupRenameCommand(resource, ctx, operations);
  setupDeleteCommand(resource, ctx, operations);
  setupVaultCommands(resource, program, ctx, config);

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
  const parentFlag = getParentFlag(parentOption);
  const parentDesc = getParentDesc(parentOption);
  const checkParent = createParentCheck(parentOption);

  resourceCommand
    .command('status <name>')
    .description(`Get ${resourceName} status`)
    .option(parentFlag, parentDesc)
    .action(async (name, options) => {
      try {
        await requireAuthForMode();
        const opts = await contextService.applyDefaults(options);

        if (!checkParent(opts)) {
          process.exit(1);
        }

        const params = { [getParentKey(parentOption)]: getParentValue(opts, parentOption) };

        const response = await withSpinner(
          `Fetching ${resourceName} status...`,
          () => fetch(params),
          'Status fetched'
        );

        const items = extractItemsFromResponse(response);
        const item = items.find((i) => i[nameField] === name);
        const format = resourceCommand.parent?.opts().output as OutputFormat;

        if (item) {
          outputService.print(item, format);
        } else {
          outputService.error(`${capitalizeFirst(resourceName)} "${name}" not found`);
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
  const parentFlag = getParentFlag(parentOption);
  const parentDesc = getParentDesc(parentOption);
  const checkParent = createParentCheck(parentOption);

  resourceCommand
    .command(`assign-${targetName} <${resourceName}Name> <${targetName}Name>`)
    .description(`Assign ${resourceName} to a ${targetName}`)
    .option(parentFlag, parentDesc)
    .action(async (resourceItemName, targetItemName, options) => {
      try {
        await requireAuthForMode();
        const opts = await contextService.applyDefaults(options);

        if (!checkParent(opts)) {
          process.exit(1);
        }

        const payload: Record<string, unknown> = {
          [nameField]: resourceItemName,
          [targetField]: targetItemName,
          [getParentKey(parentOption)]: getParentValue(opts, parentOption),
        };

        await withSpinner(
          `Assigning ${resourceName} "${resourceItemName}" to ${targetName} "${targetItemName}"...`,
          () => perform(payload),
          `${capitalizeFirst(resourceName)} assigned to ${targetName} "${targetItemName}"`
        );
      } catch (error) {
        handleError(error);
      }
    });
}
