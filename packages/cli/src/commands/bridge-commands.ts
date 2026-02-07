import type { BridgeFunctionName } from '@rediacc/shared/queue-vault';
import {
  FUNCTION_DEFINITIONS,
  type FunctionDefinition,
} from '@rediacc/shared/queue-vault/data/definitions';
import { executeBridgeFunction } from './bridge-executor.js';
import { camelToKebab, getOrCreateCommand, kebabToCamel } from './bridge-utils.js';
import { t } from '../i18n/index.js';
import type { Command } from 'commander';

/** Collector for repeatable --option <value> flags (arrays). */
function collect(val: string, acc: string[]): string[] {
  acc.push(val);
  return acc;
}

/**
 * Determine if a repository_* function should use a positional <name> argument.
 * All repository_* functions with requirements.repository: true get a positional,
 * except repository_list (which doesn't target a specific repository).
 */
function usesRepositoryPositional(functionName: string, funcDef: FunctionDefinition): boolean {
  return (
    functionName.startsWith('repository_') &&
    functionName !== 'repository_list' &&
    !!funcDef.requirements.repository
  );
}

/**
 * Auto-generate Commander.js commands from FUNCTION_DEFINITIONS.
 * Must be called AFTER existing command registrations so getOrCreateCommand
 * can find and extend existing groups (machine, repository, ceph, etc.).
 */
export function registerBridgeFunctionCommands(program: Command): void {
  for (const [functionName, funcDef] of Object.entries(FUNCTION_DEFINITIONS)) {
    registerSingleFunction(program, functionName as BridgeFunctionName, funcDef);
  }
}

function registerSingleFunction(
  program: Command,
  functionName: BridgeFunctionName,
  funcDef: FunctionDefinition
): void {
  // Split function name into command path segments
  // e.g. ceph_image_create → ['ceph', 'image', 'create']
  // Special case: 'setup' → ['setup'] (single segment = leaf command on program)
  const segments = functionName.split('_');

  // For machine_ssh_test → ['machine', 'ssh', 'test'] we need intermediate groups
  // Navigate/create intermediate command groups, then create leaf
  let parent: Command = program;
  const leafName = segments[segments.length - 1];

  for (let i = 0; i < segments.length - 1; i++) {
    parent = getOrCreateCommand(parent, segments[i]);
  }

  // Check if this leaf command already exists (e.g. registered by metadata commands)
  const existing = parent.commands.find((c) => c.name() === leafName);
  if (existing) {
    // Skip — existing registration takes precedence (shouldn't happen for bridge-only commands)
    return;
  }

  const hasPositional = usesRepositoryPositional(functionName, funcDef);
  const cmdSignature = hasPositional ? `${leafName} <name>` : leafName;
  const description = getDescriptionFromName(functionName);

  const cmd = parent.command(cmdSignature).description(description);

  // Add context options derived from requirements
  addContextOptions(cmd, funcDef, functionName);

  // Add function parameter options
  addParamOptions(cmd, funcDef);

  // Add shared options
  cmd.option(
    '--extra-machine <name:ip:user>',
    t('options.extraMachine'),
    (val: string, acc: string[]) => {
      acc.push(val);
      return acc;
    },
    [] as string[]
  );
  cmd.option('--debug', t('options.debug'));
  cmd.option('-w, --watch', t('options.watch'));
  cmd.option('-p, --priority <1-5>', t('options.priority'), '3');

  // Wire action handler
  if (hasPositional) {
    cmd.action(async (name: string, opts: Record<string, unknown>) => {
      const bridgeOpts = buildBridgeOptions(functionName, funcDef, opts, name, program);
      await executeBridgeFunction(bridgeOpts, program);
    });
  } else {
    cmd.action(async (opts: Record<string, unknown>) => {
      const bridgeOpts = buildBridgeOptions(functionName, funcDef, opts, undefined, program);
      await executeBridgeFunction(bridgeOpts, program);
    });
  }
}

function addContextOptions(cmd: Command, funcDef: FunctionDefinition, functionName: string): void {
  const reqs = funcDef.requirements;

  if (reqs.machine) {
    cmd.option('-m, --machine <name>', t('options.machine'));
  }
  if (reqs.team) {
    cmd.option('-t, --team <name>', t('options.team'));
  }
  // For non-repository-group functions that require a repository, add --repository option
  if (reqs.repository && !functionName.startsWith('repository_')) {
    cmd.option('-r, --repository <name>', t('options.repository'));
  }
  if (reqs.bridge) {
    cmd.option('-b, --bridge <name>', t('options.bridge'));
  }
  if (reqs.network_id) {
    cmd.option('--network-id <id>', t('options.networkId'));
  }
}

function addParamOptions(cmd: Command, funcDef: FunctionDefinition): void {
  for (const [paramName, paramDef] of Object.entries(funcDef.params)) {
    const kebab = camelToKebab(paramName);

    switch (paramDef.type) {
      case 'bool':
        cmd.option(`--${kebab}`, paramDef.help ?? paramName);
        break;
      case 'int': {
        const flag = `--${kebab} <n>`;
        cmd.option(flag, paramDef.help ?? paramName, (v: string) => Number.parseInt(v, 10));
        break;
      }
      case 'array':
        cmd.option(`--${kebab} <value>`, paramDef.help ?? paramName, collect, [] as string[]);
        break;
      case 'string':
      default: {
        const flag = `--${kebab} <value>`;
        cmd.option(flag, paramDef.help ?? paramName);
        break;
      }
    }
  }
}

function buildBridgeOptions(
  functionName: BridgeFunctionName,
  funcDef: FunctionDefinition,
  opts: Record<string, unknown>,
  positionalName: string | undefined,
  _program: Command
): import('./bridge-executor.js').BridgeExecuteOptions {
  // Extract context values
  const machine = opts.machine as string | undefined;
  const team = opts.team as string | undefined;
  const bridge = opts.bridge as string | undefined;
  const extraMachine = opts.extraMachine as string[] | undefined;
  const debug = opts.debug as boolean | undefined;
  const watch = opts.watch as boolean | undefined;
  const priority = opts.priority as string | undefined;

  // Build params from Commander options
  const params: Record<string, unknown> = {};

  // Inject positional repository name for repository_* functions
  if (positionalName && usesRepositoryPositional(functionName, funcDef)) {
    params.repository = positionalName;
  }

  // Inject repository from --repository for non-repository-group functions
  if (opts.repository && !functionName.startsWith('repository_')) {
    params.repository = opts.repository;
  }

  // Inject network_id from --network-id
  if (opts.networkId !== undefined) {
    params.network_id = opts.networkId;
  }

  // Map function param options (kebab → camelCase param names)
  for (const paramName of Object.keys(funcDef.params)) {
    const kebab = camelToKebab(paramName);
    // Commander converts --kebab-name to camelCase property
    const commanderKey = kebabToCamel(kebab);
    if (opts[commanderKey] !== undefined) {
      params[paramName] = opts[commanderKey];
    }
  }

  return {
    functionName,
    machine,
    team,
    bridge,
    params,
    extraMachine: extraMachine?.length ? extraMachine : undefined,
    debug,
    watch,
    priority,
  };
}

/** Generate a human-readable description from the function name. */
function getDescriptionFromName(functionName: string): string {
  const nameMap: Record<string, string> = {
    setup: 'Install and configure renet',
    machine_ping: 'Test SSH connectivity',
    machine_ssh_test: 'Test SSH connectivity',
    machine_version: 'Get renet version',
    machine_uninstall: 'Uninstall renet',
    repository_create: 'Create a new repository',
    repository_delete: 'Remove a repository',
    repository_list: 'List repositories on machine',
    repository_up: 'Start repository services',
    repository_down: 'Stop repository services',
    repository_mount: 'Mount a repository',
    repository_unmount: 'Unmount a repository',
    repository_info: 'Get repository information',
    repository_status: 'Get repository status',
    repository_resize: 'Resize a repository',
    repository_expand: 'Expand a repository',
    repository_fork: 'Create a CoW fork of a repository',
    repository_ownership: 'Change repository ownership',
    repository_validate: 'Validate repository configuration',
    repository_template_apply: 'Apply template to repository',
    backup_pull: 'Pull repository from remote source',
    backup_push: 'Push repository to remote destination',
    ceph_client_mount: 'Mount RBD image on client',
    ceph_client_unmount: 'Unmount RBD image from client',
    ceph_image_create: 'Create RBD image',
    ceph_image_delete: 'Delete RBD image',
    ceph_image_format: 'Format RBD image with filesystem',
    ceph_image_info: 'Get image info',
    ceph_image_list: 'List RBD images',
    ceph_image_map: 'Map RBD image to local device',
    ceph_image_resize: 'Resize RBD image',
    ceph_image_unmap: 'Unmap RBD image from local device',
    ceph_snapshot_create: 'Create image snapshot',
    ceph_snapshot_delete: 'Delete image snapshot',
    ceph_snapshot_list: 'List image snapshots',
    ceph_snapshot_protect: 'Protect snapshot from deletion',
    ceph_snapshot_rollback: 'Rollback image to snapshot',
    ceph_snapshot_unprotect: 'Unprotect snapshot for deletion',
    ceph_clone_delete: 'Delete a clone image',
    ceph_clone_flatten: 'Flatten clone to remove parent dependency',
    ceph_clone_image: 'Clone image from snapshot',
    ceph_clone_list: 'List snapshot clones',
    ceph_clone_mount: 'Mount clone with COW overlay',
    ceph_clone_unmount: 'Unmount clone and cleanup COW resources',
    container_exec: 'Execute command in container',
    container_inspect: 'Inspect container details',
    container_kill: 'Kill a container',
    container_list: 'List all containers',
    container_logs: 'Get container logs',
    container_pause: 'Pause a container',
    container_remove: 'Remove a container',
    container_restart: 'Restart a container',
    container_start: 'Start a container',
    container_stats: 'Get container statistics',
    container_stop: 'Stop a container',
    container_unpause: 'Unpause a container',
  };
  return nameMap[functionName] ?? functionName.replaceAll('_', ' ');
}
