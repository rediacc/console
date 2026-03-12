import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { handleError, ValidationError } from '../utils/errors.js';
import {
  type CreateActionOptions,
  coerceCliParams,
  createAction,
  traceAction,
  validateFunctionParams,
} from './queue.js';

interface DatastoreRunOptions {
  machine?: string;
  debug?: boolean;
  watch?: boolean;
}

/** Resolve extra machines for fork operations. */
async function resolveExtraMachines(
  coerced: Record<string, unknown>
): Promise<Record<string, { ip: string; port?: number; user: string }> | undefined> {
  if (!coerced.to || typeof coerced.to !== 'string') return undefined;
  const toValue = coerced.to;
  const targetMachine = await configService.getLocalMachine(toValue);
  return {
    [toValue]: {
      ip: targetMachine.ip,
      port: targetMachine.port,
      user: targetMachine.user,
    },
  };
}

/** Execute a function locally via direct SSH. */
async function executeLocal(
  functionName: string,
  machineName: string,
  coerced: Record<string, unknown>,
  options: DatastoreRunOptions
): Promise<void> {
  outputService.info(
    t('commands.shortcuts.run.executingLocal', { function: functionName, machine: machineName })
  );

  const extraMachines = await resolveExtraMachines(coerced);
  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params: coerced,
    extraMachines,
    debug: options.debug,
  });

  if (result.success) {
    outputService.success(
      t('commands.shortcuts.run.completedLocal', { duration: result.durationMs })
    );
  } else {
    renderLocalExecutionFailure(
      result,
      t('commands.shortcuts.run.failedLocal', { error: result.error })
    );
  }
}

/** Execute a bridge function for datastore operations. */
async function executeFunction(
  functionName: string,
  params: Record<string, unknown>,
  options: DatastoreRunOptions,
  program?: Command
): Promise<void> {
  const provider = await getStateProvider();
  const machineName = options.machine ?? (await configService.getMachine());

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  const coerced = coerceCliParams(functionName, params as Record<string, string>);
  validateFunctionParams(functionName, coerced);

  if (provider.isCloud) {
    const createOptions: CreateActionOptions = {
      function: functionName,
      machine: machineName,
      priority: String(DEFAULTS.PRIORITY.QUEUE_PRIORITY),
      param: Object.entries(coerced).map(([k, v]) => `${k}=${v}`),
    };
    const result = await createAction(createOptions);
    if (options.watch && result.taskId && program) {
      outputService.info(t('commands.shortcuts.run.watching'));
      await traceAction(result.taskId, { watch: true, interval: '2000' }, program);
    }
  } else {
    await executeLocal(functionName, machineName, coerced, options);
  }
}

/** Resolve Ceph pool/image/cluster params from CLI options or machine config. */
async function resolveCephInitParams(
  params: Record<string, unknown>,
  options: { machine?: string; image?: string; pool: string; cluster: string }
): Promise<void> {
  let image = options.image;
  let pool = options.pool;
  if (!image) {
    const machineName = options.machine ?? (await configService.getMachine());
    if (machineName) {
      const machine = await configService.getLocalMachine(machineName);
      if (machine.ceph) {
        image = machine.ceph.image;
        pool = machine.ceph.pool;
      }
    }
  }
  if (!image) {
    throw new ValidationError(t('commands.datastore.init.imageRequired'));
  }
  params.pool = pool;
  params.image = image;
  params.cluster = options.cluster;
}

export function registerDatastoreCommands(program: Command): void {
  const datastore = program.command('datastore').description(t('commands.datastore.description'));

  // datastore init
  datastore
    .command('init')
    .description(t('commands.datastore.init.description'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.machineOption'))
    .requiredOption('--size <size>', t('commands.datastore.init.sizeOption'))
    .option('--backend <type>', t('commands.datastore.init.backendOption'), 'local')
    .option('--pool <name>', t('commands.datastore.init.poolOption'), 'rbd')
    .option('--image <name>', t('commands.datastore.init.imageOption'))
    .option('--cluster <name>', t('commands.datastore.init.clusterOption'), 'ceph')
    .option('--force', t('commands.datastore.init.forceOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        options: DatastoreRunOptions & {
          size: string;
          backend: string;
          pool: string;
          image?: string;
          cluster: string;
          force?: boolean;
        }
      ) => {
        try {
          const functionName =
            options.backend === 'ceph' ? 'datastore_ceph_init' : 'datastore_init';
          const params: Record<string, unknown> = {
            size: options.size,
          };

          if (options.backend === 'ceph') {
            await resolveCephInitParams(params, options);
          }

          if (options.force) {
            params.force = 'true';
          }

          outputService.info(t('commands.datastore.init.starting', { machine: options.machine }));
          await executeFunction(functionName, params, options);
        } catch (error) {
          handleError(error);
        }
      }
    );

  // datastore status
  datastore
    .command('status')
    .description(t('commands.datastore.status.description'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: DatastoreRunOptions) => {
      try {
        outputService.info(t('commands.datastore.status.starting', { machine: options.machine }));
        await executeFunction('datastore_status', {}, options);
      } catch (error) {
        handleError(error);
      }
    });

  // datastore fork
  datastore
    .command('fork')
    .description(t('commands.datastore.fork.description'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.machineOption'))
    .requiredOption('--to <name>', t('commands.datastore.fork.toOption'))
    .option('--cow-size <size>', t('commands.datastore.fork.cowSizeOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        options: DatastoreRunOptions & {
          to: string;
          cowSize?: string;
        }
      ) => {
        try {
          // Read source machine's ceph config
          const machineName = options.machine ?? (await configService.getMachine());
          if (!machineName) {
            throw new ValidationError(t('errors.machineRequiredLocal'));
          }

          const machine = await configService.getLocalMachine(machineName);
          if (!machine.ceph) {
            throw new ValidationError(
              `Machine "${machineName}" does not have Ceph configuration. Run: rdc config set ceph --pool <pool> --image <image> -m ${machineName}`
            );
          }

          const destImage = `${machine.ceph.image}-fork-${options.to}`;

          const params: Record<string, unknown> = {
            source: machine.ceph.image,
            dest: destImage,
            pool: machine.ceph.pool,
            cluster: machine.ceph.clusterName ?? DEFAULTS.CEPH.CLUSTER,
          };

          if (options.cowSize) {
            params.cow_size = options.cowSize;
          }

          outputService.info(
            t('commands.datastore.fork.starting', {
              source: machineName,
              target: options.to,
            })
          );
          await executeFunction('datastore_ceph_fork', params, options);
        } catch (error) {
          handleError(error);
        }
      }
    );

  // datastore unfork
  datastore
    .command('unfork')
    .description(t('commands.datastore.unfork.description'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.machineOption'))
    .requiredOption('--source <image>', t('commands.datastore.unfork.sourceOption'))
    .requiredOption('--snapshot <name>', t('commands.datastore.unfork.snapshotOption'))
    .requiredOption('--dest <image>', t('commands.datastore.unfork.destOption'))
    .option('--pool <name>', t('commands.datastore.unfork.poolOption'))
    .option('--mount-point <path>', t('commands.datastore.unfork.mountPointOption'))
    .option('--force', t('commands.datastore.unfork.forceOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        options: DatastoreRunOptions & {
          source: string;
          snapshot: string;
          dest?: string;
          pool?: string;
          mountPoint?: string;
          force?: boolean;
        }
      ) => {
        try {
          const machineName = options.machine ?? (await configService.getMachine());
          if (!machineName) {
            throw new ValidationError(t('errors.machineRequiredLocal'));
          }

          // Read machine's ceph config for defaults
          const machine = await configService.getLocalMachine(machineName);
          const pool = options.pool ?? machine.ceph?.pool ?? DEFAULTS.CEPH.POOL;

          const params: Record<string, unknown> = {
            source: options.source,
            dest: options.dest,
            snapshot: options.snapshot,
            pool,
          };

          if (options.mountPoint) {
            params.mount_point = options.mountPoint;
          }

          if (options.force) {
            params.force = 'true';
          }

          outputService.info(t('commands.datastore.unfork.starting', { machine: machineName }));
          await executeFunction('datastore_ceph_unfork', params, options);
        } catch (error) {
          handleError(error);
        }
      }
    );
}
