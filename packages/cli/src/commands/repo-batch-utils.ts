import readline from 'node:readline';
import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployAllRepoKeys } from '../services/repo-key-deployment.js';
import { getOutputFormat } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';

/** Prompt the user for batch confirmation. Returns true if confirmed. */
export async function confirmBatch(
  action: string,
  count: number,
  machine: string
): Promise<boolean> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(`${t('commands.repo.batchConfirm', { action, count, machine })} `, (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === 'y');
    });
  });
}

export async function postRepoUpTasks(repoName: string, machineName: string): Promise<void> {
  try {
    const machineConfig = await configService.getLocalMachine(machineName);
    if (machineConfig.infra?.baseDomain) {
      const localConfig = await configService.getLocalConfig();
      const { ensureRepoDnsRecords } = await import('../services/infra-provision.js');
      await ensureRepoDnsRecords(machineName, repoName, machineConfig.infra, localConfig);
    }
  } catch {
    // Non-fatal: DNS record creation failure should not block repo up
  }

  try {
    const { downloadCertCache } = await import('../services/cert-cache.js');
    await downloadCertCache(machineName, { silent: true });
  } catch {
    // Non-fatal: cert cache failure should not block repo up
  }
}

export async function handleUpAll(options: {
  machine: string;
  includeForks?: boolean;
  mountOnly?: boolean;
  parallel?: boolean;
  concurrency?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
  dryRun?: boolean;
}): Promise<void> {
  await deployAllRepoKeys(options.machine);

  const params: Record<string, unknown> = {};
  if (options.includeForks) params.include_forks = true;
  if (options.mountOnly) params.mount_only = true;
  if (options.dryRun) params.dry_run = true;
  if (options.parallel) params.parallel = true;
  if (options.parallel && options.concurrency) {
    params.concurrency = Number.parseInt(options.concurrency, 10);
  }

  outputService.info(t('commands.repo.upAll.starting', { machine: options.machine }));

  const result = await localExecutorService.execute({
    functionName: 'repository_up_all',
    machineName: options.machine,
    params,
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(t('commands.repo.upAll.completed'));
  } else {
    renderLocalExecutionFailure(result, t('commands.repo.upAll.failed'));
  }
}

class Semaphore {
  private readonly queue: (() => void)[] = [];
  private running = 0;

  constructor(private readonly max: number) {}

  async acquire(): Promise<void> {
    if (this.running < this.max) {
      this.running++;
      return;
    }
    return new Promise<void>((resolve) => {
      this.queue.push(resolve);
    });
  }

  release(): void {
    this.running--;
    const next = this.queue.shift();
    if (next) {
      this.running++;
      next();
    }
  }
}

export async function runBatchParallel(
  repos: { name: string }[],
  concurrency: number,
  action: string,
  taskFn: (repoName: string) => Promise<void>
): Promise<void> {
  const sem = new Semaphore(concurrency);
  let succeeded = 0;

  await Promise.allSettled(
    repos.map(async ({ name }) => {
      await sem.acquire();
      try {
        outputService.info(t('commands.repo.batchStarting', { action, repo: name }));
        await taskFn(name);
        succeeded++;
      } catch (error) {
        outputService.warn(
          t('commands.repo.batchFailed', {
            action,
            repo: name,
            error: error instanceof Error ? error.message : String(error),
          })
        );
      } finally {
        sem.release();
      }
    })
  );

  outputService.info(t('commands.repo.batchResult', { action, succeeded, total: repos.length }));
}

export async function runBatchOperation(
  action: string,
  machine: string,
  skipConfirm: boolean,
  fn: (repoName: string) => Promise<void>,
  options?: { parallel?: boolean; concurrency?: string }
): Promise<void> {
  const repos = await configService.listRepositories();
  if (!skipConfirm && !(await confirmBatch(action, repos.length, machine))) {
    return;
  }

  if (options?.parallel) {
    const concurrency = Number.parseInt(
      options.concurrency ?? String(DEFAULTS.BATCH.CONCURRENCY),
      10
    );
    await runBatchParallel(repos, concurrency, action, fn);
    return;
  }

  let succeeded = 0;
  for (let i = 0; i < repos.length; i++) {
    const { name } = repos[i];
    outputService.info(
      t('commands.repo.batchIterating', { action, current: i + 1, total: repos.length, repo: name })
    );
    try {
      await fn(name);
      succeeded++;
    } catch (error) {
      outputService.warn(
        t('commands.repo.batchFailed', {
          action,
          repo: name,
          error: error instanceof Error ? error.message : String(error),
        })
      );
    }
  }
  outputService.info(t('commands.repo.batchResult', { action, succeeded, total: repos.length }));
}

export async function handleDownAll(options: {
  machine: string;
  yes?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
  dryRun?: boolean;
}): Promise<void> {
  if (options.dryRun) {
    outputService.print(
      { dryRun: true, action: 'down-all', machine: options.machine },
      getOutputFormat()
    );
    return;
  }

  const repos = await configService.listRepositories();
  if (!options.yes && !(await confirmBatch('Down', repos.length, options.machine))) {
    return;
  }

  outputService.info(t('commands.repo.down.allStarting', { machine: options.machine }));

  const result = await localExecutorService.execute({
    functionName: 'repository_down_all',
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(t('commands.repo.down.allCompleted'));
  } else {
    renderLocalExecutionFailure(result, t('commands.repo.down.allFailed'));
  }
}
