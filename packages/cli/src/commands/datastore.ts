import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { assertMachineExists } from './_validate.js';
import { coerceCliParams, validateFunctionParams } from './function-params.js';

interface DatastoreRunOptions {
  machine?: string;
  debug?: boolean;
  watch?: boolean;
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

  const result = await getExecutor().execute({
    functionName,
    machineName,
    params: coerced,
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
  options: DatastoreRunOptions
): Promise<void> {
  const machineName = options.machine;

  if (!machineName) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }

  await assertMachineExists(machineName);

  const coerced = coerceCliParams(functionName, params as Record<string, string>);
  validateFunctionParams(functionName, coerced);

  await executeLocal(functionName, machineName, coerced, options);
}

/** Resolve Ceph pool/image params from CLI options. */
function resolveCephInitParams(
  params: Record<string, unknown>,
  options: { machine?: string; image?: string; pool: string; cluster: string }
): void {
  const image = options.image;
  const pool = options.pool;
  // The per-machine ceph pointer was retired in config v3 (Ceph is a datastore
  // backend now). Explicit --image/--pool are required until the datastore
  // registry supplies them (P4).
  if (!image) {
    throw new ValidationError(t('commands.datastore.init.imageRequired'));
  }
  params.pool = pool;
  params.image = image;
  params.cluster = options.cluster;
}

export function registerDatastoreCommands(program: Command): void {
  const datastore = program
    .command('datastore')
    .summary(t('commands.datastore.descriptionShort'))
    .description(t('commands.datastore.description'));

  // datastore init
  datastore
    .command('init')
    .description(t('commands.datastore.init.description'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.machineOption'))
    .requiredOption('--size <size>', t('commands.datastore.init.sizeOption'))
    .addOption(
      new Option('--backend <type>', t('commands.datastore.init.backendOption'))
        .choices(['local', 'ceph'])
        .default('local')
    )
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
            resolveCephInitParams(params, options);
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

  // datastore resize (offline grow/shrink of the loop-backed pool)
  datastore
    .command('resize')
    .description(t('commands.datastore.resize.description'))
    .requiredOption('-m, --machine <name>', t('commands.datastore.machineOption'))
    .requiredOption('--size <size>', t('commands.datastore.resize.sizeOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: DatastoreRunOptions & { size: string }) => {
      try {
        outputService.info(
          t('commands.datastore.resize.starting', { machine: options.machine, size: options.size })
        );
        await executeFunction('datastore_resize', { size: options.size }, options);
      } catch (error) {
        handleError(error);
      }
    });

  // datastore fork
  datastore
    .command('fork')
    .summary(t('commands.datastore.fork.descriptionShort'))
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
          const machineName = options.machine;
          if (!machineName) {
            throw new ValidationError(t('errors.machineRequiredLocal'));
          }

          await configService.getLocalMachine(machineName);
          // The per-machine ceph pointer was retired in config v3. This legacy
          // fork path is superseded by the datastore registry (`rdc datastore
          // fork`, P1/P4); it no longer has a machine-side Ceph image to read.
          throw new ValidationError(
            `Ceph fork on "${machineName}" is retired: Ceph is now a datastore backend. Fork the named datastore instead (rdc datastore --help).`
          );
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
          const machineName = options.machine;
          if (!machineName) {
            throw new ValidationError(t('errors.machineRequiredLocal'));
          }

          await configService.getLocalMachine(machineName);
          // datastore_ceph_unfork was deleted with the ceph-below-the-repo
          // redesign (delete ledger, 02 §6): unforking a datastore is now
          // `datastore detach --discard`, which tears the fork's clone + owned
          // snapshot down through the registry's ordered hygiene sequence.
          throw new ValidationError(
            `Ceph unfork on "${machineName}" is retired: discard a datastore fork with ` +
              `\`rdc datastore detach <name>:<tag> --discard\` (P4 porcelain).`
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}
