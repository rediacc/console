import { readFileSync } from 'node:fs';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';
import { registerRepoPolicyCommand } from './repo-policy.js';
import { registerRepoPromoteCommand } from './repo-promote.js';
import { registerRepoTrimCommand } from './repo-trim.js';

/**
 * Autostart is a DOCKER-only verb: it installs a systemd unit that mounts the repo
 * and runs its compose on boot. A kubernetes repo's workload is the cluster's job,
 * not systemd's, so refuse a cluster-placed ref with the reason. This inlines what
 * `assertDockerOnly` used to do from the (now dead) `--cluster` flag; the ref tells
 * us the placement, so the refusal is now based on what the repo IS rather than on
 * what the operator typed.
 */
async function resolveAutostartRef(
  ref: string
): Promise<{ name: string; repoKey: string; machineName: string }> {
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  if (kubeCluster) {
    throw new ValidationError(t('errors.cluster.dockerOnlyVerb', { verb: 'autostart' }));
  }
  return { name, repoKey, machineName };
}

/** The all-repos form has no ref to derive from, so -m is how it names its target. */
function requireMachine(machine: string | undefined): string {
  if (!machine) {
    throw new ValidationError(t('errors.machineRequiredLocal'));
  }
  return machine;
}

/** Execute a machine-level function (no repository context needed). */
async function executeMachineFunction(
  functionName: string,
  options: { machine: string; debug?: boolean; skipRouterRestart?: boolean },
  messages: { starting: string; completed: string; failed: string }
): Promise<void> {
  await assertMachineExists(options.machine);
  outputService.info(messages.starting);

  const result = await getExecutor().execute({
    functionName,
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(messages.completed);
  } else {
    renderLocalExecutionFailure(result, result.error ?? messages.failed);
  }
}

interface AutostartListPayload {
  service_installed?: boolean;
  service_enabled?: boolean;
  repositories?: { name: string; enabled: boolean; on_disk: boolean }[] | null;
}

interface AutostartListOptions {
  machine: string;
  cluster?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

/** `repo autostart list` — fetch the renet payload and render it. */
async function handleAutostartList(options: AutostartListOptions): Promise<void> {
  await assertMachineExists(options.machine);
  outputService.info(
    t('commands.repo.admin.autostart.list.starting', { machine: options.machine })
  );

  const result = await getExecutor().execute({
    functionName: 'repository_autostart_list',
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(
      result,
      result.error ?? t('commands.repo.admin.autostart.list.failed')
    );
    return;
  }

  // renet relays a single JSON object with `[repository_autostart_list]`
  // line prefixes — same shape the prune parser extracts.
  const payload = parseDatastorePruneOutput(result.stdout ?? '') as AutostartListPayload;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(payload, format);
    return;
  }

  const resolve = createGuidResolver(await loadGuidMap());
  const rows = (payload.repositories ?? []).map((r) => ({
    repository: resolve(r.name),
    guid: r.name,
    enabled: r.enabled ? 'yes' : 'no',
    onDisk: r.on_disk ? 'yes' : 'no',
  }));

  if (rows.length === 0) {
    outputService.info(t('commands.repo.admin.autostart.list.empty', { machine: options.machine }));
  } else {
    outputService.print(rows, 'table');
  }
  outputService.info(
    t('commands.repo.admin.autostart.list.service', {
      installed: payload.service_installed ? 'yes' : 'no',
      enabled: payload.service_enabled ? 'yes' : 'no',
    })
  );
}

/**
 * Register extended repo commands: fork, resize, expand, validate,
 * autostart, ownership, and template.
 */
export function registerExtendedRepoCommands(repo: Command, admin: Command): void {
  // `repo fork <parent-ref>` is registered by registerRepoForkCommand (repo-fork.ts),
  // wired in repo.ts alongside the other register* calls after the §2.3 reshape.
  registerRepoPromoteCommand(repo);

  // repo resize <ref> — offline grow/shrink. Stays on the DAILY surface (§5.4):
  // it is a volume-geometry verb an operator reaches for, not admin plumbing.
  repo
    .command('resize')
    .summary(t('commands.repo.resize.descriptionShort'))
    .description(t('commands.repo.resize.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--size <size>', t('commands.repo.resize.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          size: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
          await assertCommandPolicy(CMD.REPO_RESIZE, repoKey);
          await executeRepoFunction(
            'repository_resize',
            repoKey,
            machineName,
            { size: options.size },
            { ...options, ...(kubeCluster !== undefined && { kubeCluster }) },
            {
              starting: t('commands.repo.resize.starting', {
                repository: name,
                size: options.size,
                machine: machineName,
              }),
              completed: t('commands.repo.resize.completed'),
              failed: t('commands.repo.resize.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo expand <ref> — online grow-only (the deliberate counterpart to resize).
  repo
    .command('expand')
    .summary(t('commands.repo.expand.descriptionShort'))
    .description(t('commands.repo.expand.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--size <size>', t('commands.repo.expand.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          size: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
          await assertCommandPolicy(CMD.REPO_EXPAND, repoKey);
          await executeRepoFunction(
            'repository_expand',
            repoKey,
            machineName,
            { size: options.size },
            { ...options, ...(kubeCluster !== undefined && { kubeCluster }) },
            {
              starting: t('commands.repo.expand.starting', {
                repository: name,
                size: options.size,
                machine: machineName,
              }),
              completed: t('commands.repo.expand.completed'),
              failed: t('commands.repo.expand.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo trim [ref] (no ref = machine-wide, on -m)
  registerRepoTrimCommand(repo);

  // repo policy set|get [ref] (no ref = machine-wide default, on -m)
  registerRepoPolicyCommand(repo);

  // ── repo admin subtree (§5.4): the niche plumbing verbs move OFF the daily
  // surface. Same behavior, addressed by ref, one level down.

  // repo admin validate <ref>
  admin
    .command('validate')
    .summary(t('commands.repo.admin.validate.descriptionShort'))
    .description(t('commands.repo.admin.validate.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
          await assertCommandPolicy(CMD.REPO_ADMIN_VALIDATE, repoKey);
          await executeRepoFunction(
            'repository_validate',
            repoKey,
            machineName,
            {},
            { ...options, ...(kubeCluster !== undefined && { kubeCluster }) },
            {
              starting: t('commands.repo.admin.validate.starting', {
                repository: name,
                machine: machineName,
              }),
              completed: t('commands.repo.admin.validate.completed'),
              failed: t('commands.repo.admin.validate.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo admin autostart enable|disable|list
  const autostart = admin
    .command('autostart')
    .description(t('commands.repo.admin.autostart.description'));

  // repo autostart enable [--name <name>] — per-repo if name given, all repos if omitted
  // A ref targets ONE repo; -m with no ref targets every repo on the machine.
  // Autostart is docker-only by nature (it installs a systemd unit that mounts the
  // repo and runs its compose on boot); a kubernetes repo's workload is the
  // cluster's job, not systemd's, so a cluster-placed ref is refused with the
  // reason rather than silently doing nothing.
  autostart
    .command('enable')
    .description(t('commands.repo.admin.autostart.enable.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string | undefined,
        options: {
          machine?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          if (ref) {
            const { name, repoKey, machineName } = await resolveAutostartRef(ref);
            await assertCommandPolicy(CMD.REPO_ADMIN_AUTOSTART_ENABLE, repoKey);
            await executeRepoFunction(
              'repository_autostart_enable',
              repoKey,
              machineName,
              {},
              options,
              {
                starting: t('commands.repo.admin.autostart.enable.starting', {
                  repository: name,
                  machine: machineName,
                }),
                completed: t('commands.repo.admin.autostart.enable.completed'),
                failed: t('commands.repo.admin.autostart.enable.failed'),
              }
            );
          } else {
            const machine = requireMachine(options.machine);
            await executeMachineFunction(
              'repository_autostart_enable_all',
              { ...options, machine },
              {
                starting: t('commands.repo.admin.autostart.enable.startingAll', {
                  machine,
                }),
                completed: t('commands.repo.admin.autostart.enable.completedAll'),
                failed: t('commands.repo.admin.autostart.enable.failedAll'),
              }
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  autostart
    .command('disable')
    .description(t('commands.repo.admin.autostart.disable.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string | undefined,
        options: {
          machine?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          if (ref) {
            const { name, repoKey, machineName } = await resolveAutostartRef(ref);
            await assertCommandPolicy(CMD.REPO_ADMIN_AUTOSTART_DISABLE, repoKey);
            await executeRepoFunction(
              'repository_autostart_disable',
              repoKey,
              machineName,
              {},
              options,
              {
                starting: t('commands.repo.admin.autostart.disable.starting', {
                  repository: name,
                  machine: machineName,
                }),
                completed: t('commands.repo.admin.autostart.disable.completed'),
                failed: t('commands.repo.admin.autostart.disable.failed'),
              }
            );
          } else {
            const machine = requireMachine(options.machine);
            await executeMachineFunction(
              'repository_autostart_disable_all',
              { ...options, machine },
              {
                starting: t('commands.repo.admin.autostart.disable.startingAll', {
                  machine,
                }),
                completed: t('commands.repo.admin.autostart.disable.completedAll'),
                failed: t('commands.repo.admin.autostart.disable.failedAll'),
              }
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  autostart
    .command('list')
    .description(t('commands.repo.admin.autostart.list.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: AutostartListOptions) => {
      try {
        await handleAutostartList(options);
      } catch (error) {
        handleError(error);
      }
    });

  // repo admin ownership <ref>
  admin
    .command('ownership')
    .summary(t('commands.repo.admin.ownership.descriptionShort'))
    .description(t('commands.repo.admin.ownership.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--uid <uid>', t('commands.repo.admin.ownership.uidOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          uid?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
          await assertCommandPolicy(CMD.REPO_ADMIN_OWNERSHIP, repoKey);
          const params: Record<string, unknown> = {};
          if (options.uid) params.owner_uid = options.uid;

          await executeRepoFunction(
            'repository_ownership',
            repoKey,
            machineName,
            params,
            { ...options, ...(kubeCluster !== undefined && { kubeCluster }) },
            {
              starting: t('commands.repo.admin.ownership.starting', {
                repository: name,
                machine: machineName,
              }),
              completed: t('commands.repo.admin.ownership.completed'),
              failed: t('commands.repo.admin.ownership.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo admin template list|apply
  const template = admin
    .command('template')
    .summary(t('commands.repo.admin.template.descriptionShort'))
    .description(t('commands.repo.admin.template.description'));

  // repo template list
  template
    .command('list')
    .summary(t('commands.repo.admin.template.list.descriptionShort'))
    .description(t('commands.repo.admin.template.list.description'))
    .action(async () => {
      try {
        const { TEMPLATES } = await import('../templates/embedded.generated.js');
        const entries = Object.values(TEMPLATES);
        if (entries.length === 0) {
          outputService.info(t('commands.repo.admin.template.list.empty'));
          return;
        }
        for (const tmpl of entries) {
          outputService.info(`  ${tmpl.name.padEnd(20)} ${tmpl.description}`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo admin template apply <ref> --template <name>. The old `-r/--repository`
  // collapses into the positional ref, and the old `--name` (which meant the
  // TEMPLATE, not the repo, on a tree where --name means the repo everywhere else)
  // becomes the honest `--template`.
  template
    .command('apply')
    .summary(t('commands.repo.admin.template.apply.descriptionShort'))
    .description(t('commands.repo.admin.template.apply.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--template <name>', t('commands.repo.admin.template.apply.templateOption'))
    .option('--file <path>', t('commands.repo.admin.template.fileOption'))
    .option('--grand <name>', t('commands.repo.admin.template.grandOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (
        ref: string,
        options: {
          template: string;
          file?: string;
          grand?: string;
          debug?: boolean;
          skipRouterRestart?: boolean;
        }
      ) => {
        try {
          const templateName = options.template;
          const resolved = await resolveRepoRef(ref);
          await assertCommandPolicy(CMD.REPO_ADMIN_TEMPLATE, resolved.repoKey);

          let tmplBase64: string;

          if (options.file) {
            // File mode (backward compat): read local JSON file
            let fileContent: string;
            try {
              fileContent = readFileSync(options.file, 'utf-8');
            } catch {
              throw new Error(
                t('commands.repo.admin.template.fileNotFound', { path: options.file })
              );
            }
            tmplBase64 = Buffer.from(fileContent).toString('base64');
          } else {
            // Embedded mode: look up template by name
            const { TEMPLATES } = await import('../templates/embedded.generated.js');
            const embedded = TEMPLATES[templateName] as (typeof TEMPLATES)[string] | undefined;
            if (!embedded) {
              const available = Object.keys(TEMPLATES).join(', ');
              throw new Error(
                t('commands.repo.admin.template.apply.notFound', {
                  name: templateName,
                  available,
                })
              );
            }
            const templateJSON = { version: '2', files: embedded.files };
            tmplBase64 = Buffer.from(JSON.stringify(templateJSON)).toString('base64');
          }

          const params: Record<string, unknown> = { tmpl: tmplBase64 };

          // Resolve grand repo friendly name -> GUID
          if (options.grand) {
            const grandRepo = await configService.getRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction(
            'repository_template_apply',
            resolved.repoKey,
            resolved.machineName,
            params,
            {
              ...options,
              ...(resolved.kubeCluster !== undefined && { kubeCluster: resolved.kubeCluster }),
            },
            {
              starting: t('commands.repo.admin.template.starting', {
                repository: resolved.name,
                machine: resolved.machineName,
              }),
              completed: t('commands.repo.admin.template.completed'),
              failed: t('commands.repo.admin.template.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}
