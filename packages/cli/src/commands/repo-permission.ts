import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { parseCapturedJson } from '../services/executor/renet-output.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { optStr } from '../services/jobs/steps-support.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { isRepoAllowedByGrandEnv } from '../utils/grand-env.js';
import { isOverrideLegitimate } from '../utils/process-ancestry.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { assertMachineExists } from './_validate.js';

interface PermissionOptions {
  root?: boolean;
  path?: string;
  debug?: boolean;
}

type PermissionVerb = 'grant' | 'revoke' | 'show';

/** The lifecycle half of the grant renet prints (`daemon grant --show`). */
interface LifecycleGrant {
  root: boolean;
  paths: string[];
}

/** The lifecycle grant in renet's output; none (the default tier) when it carries no `lifecycle` key. */
function lifecycleOf(stdout: string | undefined): LifecycleGrant | undefined {
  try {
    const grant = parseCapturedJson<{
      lifecycle?: { root?: boolean; paths?: { path: string; read_write?: boolean }[] | null };
    }>(stdout);
    const lifecycle = grant.lifecycle ?? {};
    return {
      root: lifecycle.root === true,
      paths: (lifecycle.paths ?? []).map((p) => (p.read_write ? `${p.path}:rw` : p.path)),
    };
  } catch {
    return undefined;
  }
}

/** A grand repository has no grand of its own to differ from; a fork's grandGuid is another repository's guid. A ref that resolves to nothing is treated as grand. */
async function isGrandRepository(repoKey: string): Promise<boolean> {
  const repo = await configService.getRepository(repoKey);
  return !(repo?.grandGuid && repo.grandGuid !== repo.repositoryGuid);
}

/**
 * Refuse `--root` to an agent unless the operator set REDIACC_ALLOW_GRAND_REPO before the agent
 * started: the same ancestry check the grand-repo guard makes. A root grant removes the privilege drop of
 * the repository's up() and down(), so an agent never confers it on itself.
 */
function assertRootGrantAllowed(name: string): void {
  if (!isAgentEnvironment()) return;
  if (!isRepoAllowedByGrandEnv(name)) {
    throw new ValidationError(t('errors.agent.rootGrantBlocked', { name }));
  }
  if (!isOverrideLegitimate()) {
    throw new ValidationError(t('errors.agent.rootGrantOverride', { name }));
  }
}

/**
 * Refuse `--path` on a grand repository to an agent under the same ancestry check as `--root`: a path grant widens
 * what the repository's up() and down() reach on the host. A fork stays free.
 */
async function assertPathGrantAllowed(name: string, repoKey: string): Promise<void> {
  if (!isAgentEnvironment()) return;
  if (!(await isGrandRepository(repoKey))) return;
  if (!isRepoAllowedByGrandEnv(name)) {
    throw new ValidationError(t('errors.agent.pathGrantBlocked', { name }));
  }
  if (!isOverrideLegitimate()) {
    throw new ValidationError(t('errors.agent.pathGrantOverride', { name }));
  }
}

/** Each verb's text, as literal keys so the orphan-key gate sees every one. */
const VERB_TEXT = {
  grant: {
    summary: () => t('commands.repo.permission.grant.descriptionShort'),
    description: () => t('commands.repo.permission.grant.description'),
    rootOption: () => t('commands.repo.permission.grant.rootOption'),
    pathOption: () => t('commands.repo.permission.grant.pathOption'),
    starting: (vars: Record<string, string>) => t('commands.repo.permission.grant.starting', vars),
    completed: (vars: Record<string, string>) =>
      t('commands.repo.permission.grant.completed', vars),
    failed: () => t('commands.repo.permission.grant.failed'),
  },
  revoke: {
    summary: () => t('commands.repo.permission.revoke.descriptionShort'),
    description: () => t('commands.repo.permission.revoke.description'),
    rootOption: () => t('commands.repo.permission.revoke.rootOption'),
    pathOption: () => t('commands.repo.permission.revoke.pathOption'),
    starting: (vars: Record<string, string>) => t('commands.repo.permission.revoke.starting', vars),
    completed: (vars: Record<string, string>) =>
      t('commands.repo.permission.revoke.completed', vars),
    failed: () => t('commands.repo.permission.revoke.failed'),
  },
  show: {
    summary: () => t('commands.repo.permission.show.descriptionShort'),
    description: () => t('commands.repo.permission.show.description'),
    starting: (vars: Record<string, string>) => t('commands.repo.permission.show.starting', vars),
    completed: (vars: Record<string, string>) => t('commands.repo.permission.show.completed', vars),
    failed: () => t('commands.repo.permission.show.failed'),
  },
} as const;

/** A grant or revoke names something to change, and an agent may change it on this repository. */
async function assertGrantChangeAllowed(
  verb: PermissionVerb,
  name: string,
  repoKey: string,
  options: PermissionOptions
): Promise<void> {
  if (!options.root && !options.path) {
    throw new ValidationError(t('commands.repo.permission.nothingToChange', { verb }));
  }
  if (options.root) assertRootGrantAllowed(name);
  if (options.path) await assertPathGrantAllowed(name, repoKey);
}

async function handlePermissionVerb(
  verb: PermissionVerb,
  ref: string,
  options: PermissionOptions
): Promise<void> {
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref, {
    readOnly: verb === 'show',
  });
  if (kubeCluster) {
    throw new ValidationError(t('errors.cluster.dockerOnlyVerb', { verb: `permission ${verb}` }));
  }
  if (verb !== 'show') await assertGrantChangeAllowed(verb, name, repoKey, options);
  await assertMachineExists(machineName);

  const params: Record<string, unknown> = {};
  if (options.root) params.root = true;
  if (options.path) params.path = options.path;

  const steps =
    verb === 'show'
      ? [planStep('renderPermissionShow', { repo: repoKey })]
      : [planStep('mirrorLifecycleGrants', { repo: repoKey })];
  await executeRepoFunction(
    `repository_permission_${verb}`,
    repoKey,
    machineName,
    params,
    {
      debug: options.debug,
      captureOutput: true,
      job: { verb: `repo permission ${verb}`, steps },
    },
    {
      starting: VERB_TEXT[verb].starting({ repository: name, machine: machineName }),
      completed: VERB_TEXT[verb].completed({ repository: name }),
      failed: VERB_TEXT[verb].failed(),
    }
  );
}

bindStepHandler('mirrorLifecycleGrants', async ({ output, params }) => {
  const repoKey = optStr(params, 'repo');
  if (!repoKey) throw new Error('step param "repo" is missing');
  const grant = lifecycleOf(output);
  // The machine's grant already changed; an output that cannot be read must not leave state.repos on the old lifecycle without saying so.
  if (!grant) throw new Error(t('commands.repo.permission.show.unreadable'));
  await configService.setRepositoryLifecycle(repoKey, grant);
});

bindStepHandler('renderPermissionShow', async ({ output, params }) => {
  const repoKey = optStr(params, 'repo');
  const grant = lifecycleOf(output);
  if (!grant) throw new Error(t('commands.repo.permission.show.unreadable'));
  if (repoKey) await configService.setRepositoryLifecycle(repoKey, grant);
  outputService.print(
    [{ root: grant.root ? 'Yes' : 'No', paths: grant.paths.join(', ') || '-' }],
    getOutputFormat()
  );
});

/** Register `repo permission grant|revoke|show`: what a repository's Rediaccfile up() and down() may reach (the machine's grant store enforces it). */
export function registerRepoPermissionCommands(repo: Command): void {
  const permission = repo
    .command('permission')
    .summary(t('commands.repo.permission.descriptionShort'))
    .description(t('commands.repo.permission.description'));

  for (const verb of ['grant', 'revoke'] as const) {
    permission
      .command(verb)
      .summary(VERB_TEXT[verb].summary())
      .description(VERB_TEXT[verb].description())
      .argument('<ref>', t('options.repoRef'))
      .option('--root', VERB_TEXT[verb].rootOption())
      .option('--path <path>', VERB_TEXT[verb].pathOption())
      .option('--debug', t('options.debug'))
      .action(async (ref: string, options: PermissionOptions) => {
        try {
          await handlePermissionVerb(verb, ref, options);
        } catch (error) {
          handleError(error);
        }
      });
  }

  permission
    .command('show')
    .summary(VERB_TEXT.show.summary())
    .description(VERB_TEXT.show.description())
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: PermissionOptions) => {
      try {
        await handlePermissionVerb('show', ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}
