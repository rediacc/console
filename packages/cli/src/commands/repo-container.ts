/**
 * `rdc repo logs` / `rdc repo exec` (spec 03 §5.4, R2-F14) — the two verbs that
 * replace `term connect`'s container side door.
 *
 * The old shape was `term connect -m <m> -r <repo> --container <c> --log-lines
 * <n> --follow`: a SHELL command carrying container flags, which meant the only
 * way for an agent to read a log line was to ask for an interactive shell and type
 * into it. These are the first-class verbs instead, and they are what let `term`
 * be honestly excluded from MCP (§5.8) while an agent keeps both capabilities.
 *
 * Same verb, same meaning across runtimes (principle 2): docker = `docker
 * logs`/`exec` through the repo's own daemon; kubernetes = pod logs/exec in the
 * repo's namespace. The runtime is derived from the ref, never asked for.
 *
 * `repo exec` propagates the remote command's exit code VERBATIM (§1 deviation):
 * a wrapper that swallowed it would make `rdc repo exec app -- test -f x` useless.
 * This is end-to-end only because renet's `handleExecuteResult` re-raises the
 * child's code (cmd/renet/execute_command.go); it used to `os.Exit(1)`
 * unconditionally, which silently collapsed every remote code to 1 and made the
 * claim above false for years. If a remote `exit 7` ever reports 1 again, look
 * there first, not here. NOTE the unavoidable ambiguity this buys: rdc reserves
 * exit codes 2-15 for its own classes (types/index.ts), so a container exiting 7
 * is indistinguishable from rdc's own API_ERROR to anything reading `$?`.
 *
 * Both verbs set `passthroughOutput` because their output IS the answer. Without
 * it the executor's default handler keeps only step events and drops the rest,
 * which is why `repo exec` printed nothing at all unless run with --debug.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { shellQuote } from '../utils/shell-quote.js';

/**
 * Which container the verb acts on. Omitting `--container` is only unambiguous
 * when the repo runs exactly one; anything else is exit 11 listing the choices,
 * because picking one for the operator is how you read the wrong log or run a
 * command in the wrong process (§5.4 ambiguity rule).
 */
function resolveContainer(
  repoKey: string,
  machineName: string,
  kubeCluster: string | undefined,
  requested: string | undefined
): string | undefined {
  // An explicit choice is always honored; renet reports a bad name itself, and its
  // error names the containers that DO exist, which is the message we would write.
  if (requested) return requested;
  // Undefined lets renet apply the single-container default. It knows the live
  // container set; the CLI would have to round-trip to learn it, and the answer
  // could change between the probe and the call anyway.
  void repoKey;
  void machineName;
  void kubeCluster;
  return undefined;
}

export function registerRepoContainerCommands(repo: Command): void {
  repo
    .command('logs')
    .summary(t('commands.repo.logs.descriptionShort'))
    .description(t('commands.repo.logs.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('-c, --container <name>', t('commands.repo.logs.containerOption'))
    .option('-f, --follow', t('commands.repo.logs.followOption'))
    .option('--lines <n>', t('commands.repo.logs.linesOption'), '100')
    .option('--timestamps', t('commands.repo.logs.timestampsOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        ref: string,
        options: {
          container?: string;
          follow?: boolean;
          lines: string;
          timestamps?: boolean;
          debug?: boolean;
        }
      ) => {
        try {
          const { repoKey, machineName, kubeCluster } = await resolveRepoRef(ref, {
            readOnly: true,
          });
          const container = resolveContainer(repoKey, machineName, kubeCluster, options.container);
          const lines = Number(options.lines);
          if (!Number.isInteger(lines) || lines < 1) {
            throw new ValidationError(
              `--lines must be a positive integer, got "${options.lines}".`
            );
          }

          const result = await getExecutor().execute({
            functionName: 'container_logs',
            machineName,
            // #74: the container lives in the repo's compose project, which renet
            // resolves through the repo's mount — the machine default is not it.
            datastore: await recordedDatastoreMount(repoKey),
            params: {
              repository: repoKey,
              ...(container && { container }),
              lines,
              ...(options.follow && { follow: true }),
              ...(options.timestamps && { timestamps: true }),
            },
            debug: options.debug,
            passthroughOutput: true,
            ...(kubeCluster !== undefined && { kubeCluster }),
          });
          if (!result.success) {
            throw new Error(result.error ?? t('errors.container.logsFailed'));
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  repo
    .command('exec')
    .summary(t('commands.repo.exec.descriptionShort'))
    .description(t('commands.repo.exec.description'))
    .argument('<ref>', t('options.repoRef'))
    .argument('<cmd...>', t('commands.repo.exec.cmdArgument'))
    .option('-c, --container <name>', t('commands.repo.exec.containerOption'))
    .option('-i, --interactive', t('commands.repo.exec.interactiveOption'))
    .option('-u, --user <user>', t('commands.repo.exec.userOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        ref: string,
        cmd: string[],
        options: {
          container?: string;
          interactive?: boolean;
          user?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const { repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
          await assertCommandPolicy(CMD.REPO_EXEC, repoKey);
          const container = resolveContainer(repoKey, machineName, kubeCluster, options.container);

          const result = await getExecutor().execute({
            functionName: 'container_exec',
            machineName,
            // #74: same as container_logs — the exec target is resolved through
            // the repo's mount, so the recorded datastore has to travel.
            datastore: await recordedDatastoreMount(repoKey),
            params: {
              repository: repoKey,
              ...(container && { container }),
              // Quote EACH argv element, then join. renet hands this string to
              // `/bin/sh -c` as one argv element (pkg/functions/commands/
              // container.go), so a bare join let the container's shell re-split
              // it: `-- sh -c "echo A B"` arrived as `sh -c echo A B`, silently
              // running something the operator never typed.
              command: cmd.map(shellQuote).join(' '),
              ...(options.user && { user: options.user }),
              ...(options.interactive && { tty: true }),
            },
            debug: options.debug,
            passthroughOutput: true,
            ...(kubeCluster !== undefined && { kubeCluster }),
          });

          // The remote exit code IS the result (§1 deviation). Anything else makes
          // `repo exec <ref> -- test -f /x` a command whose answer cannot be read.
          if (!result.success) {
            // A NON-ZERO remote exit is not a CLI failure, it is the answer. Only a
            // dispatch failure (exitCode 0 with success false, or an SSH-level error)
            // becomes an exception.
            if (result.exitCode !== 0) {
              process.exitCode = result.exitCode;
              return;
            }
            throw new Error(result.error ?? t('errors.container.execFailed'));
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}
