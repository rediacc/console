import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { type LocalExecuteResult, localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';

/** Surface renet's specific error reason from a failed repository_cat result. */
function renderCatFailure(result: LocalExecuteResult): void {
  const detail = (result.stderr ?? '')
    .split('\n')
    .map((l) => l.replace(/^\[[a-z0-9_]+\]\s?/i, '').trim())
    .filter((l) => /^(Error:|error:)/.test(l))
    .map((l) => l.replace(/^(Error|error):\s*/, ''))
    .at(-1);
  renderLocalExecutionFailure(result, detail ?? result.error ?? t('commands.repo.cat.failed'));
  process.exitCode = 1;
}

/**
 * Decode the `RDC_CAT_B64:<base64>` marker from repository_cat stdout and
 * write raw bytes to process.stdout. Uses indexOf to avoid O(n) line splits
 * on up-to-50 MiB output.
 */
function decodeCatPayload(stdout: string): void {
  const marker = 'RDC_CAT_B64:';
  const markerIdx = stdout.indexOf(marker);
  if (markerIdx === -1) {
    outputService.error(t('commands.repo.cat.failed'));
    process.exitCode = 1;
    return;
  }
  const valueStart = markerIdx + marker.length;
  const newlineIdx = stdout.indexOf('\n', valueStart);
  const b64Value = (
    newlineIdx === -1 ? stdout.slice(valueStart) : stdout.slice(valueStart, newlineIdx)
  ).trim();
  process.stdout.write(Buffer.from(b64Value, 'base64'));
}

/**
 * repo cat — bounded, pipeable single-file read inside the repo mount
 * (rediacc/console#490). Stdout = file bytes only; progress/diagnostics go to
 * stderr, so `rdc repo cat … | jq` / `| grep` / `> out` stay clean.
 */
export function registerRepoCatCommand(repo: Command): void {
  repo
    .command('cat')
    .description(t('commands.repo.cat.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--remote-file <path>', t('commands.repo.cat.remoteFileOption'))
    .option('--max-bytes <n>', t('commands.repo.cat.maxBytesOption'))
    .option('--offset <n>', t('commands.repo.cat.offsetOption'))
    .option('--head <lines>', t('commands.repo.cat.headOption'))
    .option('--tail <lines>', t('commands.repo.cat.tailOption'))
    .option('--stat', t('commands.repo.cat.statOption'))
    .option('--force-binary', t('commands.repo.cat.forceBinaryOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        remoteFile: string;
        maxBytes?: string;
        offset?: string;
        head?: string;
        tail?: string;
        stat?: boolean;
        forceBinary?: boolean;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          const repoEntry = await configService.getRepository(name);
          if (!repoEntry) {
            throw new Error(`Repository "${name}" not found in context`);
          }
          await configService.ensureRepositoryNetworkId(name);

          const params: Record<string, unknown> = { path: options.remoteFile };
          if (options.maxBytes) params.max_bytes = Number.parseInt(options.maxBytes, 10);
          if (options.offset) params.offset = Number.parseInt(options.offset, 10);
          if (options.head) params.head = Number.parseInt(options.head, 10);
          if (options.tail) params.tail = Number.parseInt(options.tail, 10);
          if (options.stat) params.stat = true;
          if (options.forceBinary) params.force_binary = true;

          // Progress goes to stderr (outputService.info), keeping stdout pure.
          outputService.info(
            t('commands.repo.cat.starting', {
              repository: name,
              machine: options.machine,
              path: options.remoteFile,
            })
          );

          const result = await localExecutorService.execute({
            functionName: 'repository_cat',
            machineName: options.machine,
            params: { repository: name, ...params },
            debug: options.debug,
            skipRouterRestart: options.skipRouterRestart,
            captureOutput: true,
          });

          if (!result.success) {
            renderCatFailure(result);
            return;
          }
          decodeCatPayload(result.stdout ?? '');
        } catch (error) {
          handleError(error);
        }
      }
    );
}
