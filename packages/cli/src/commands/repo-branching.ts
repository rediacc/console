import { randomUUID } from 'node:crypto';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { type LocalExecuteResult, localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { compositeKey, parseRepoRef } from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { handleForkAction } from './repo-fork.js';
import { assertMachineExists } from './_validate.js';

function tryParse<T>(s: string): T | undefined {
  try {
    return JSON.parse(s) as T;
  } catch {
    return undefined;
  }
}

/** Accumulate a renet command's indented JSON from captured stdout, skipping
 * interleaved bridge log lines (mirrors repo-diff's extractor). */
function parseRenetJson<T>(stdout: string): T | undefined {
  let buf = '';
  for (const rawLine of stdout.trim().split('\n')) {
    const line = rawLine.replace(/^\[[^\]]+\]\s?/, '');
    if (buf) {
      buf += `\n${line}`;
    } else {
      const brace = line.indexOf('{');
      if (brace < 0) continue;
      buf = line.slice(brace);
    }
    const parsed = tryParse<T>(buf);
    if (parsed !== undefined) return parsed;
  }
  return undefined;
}

/** repo commit --name <workingFork> --message <msg> [--author] -m <machine> */
async function handleCommit(options: {
  name: string;
  message: string;
  author?: string;
  machine: string;
  debug?: boolean;
}): Promise<void> {
  try {
    await assertCommandPolicy(CMD.REPO_COMMIT, options.name);
    await assertMachineExists(options.machine);

    const cfg = await configService.getRepository(options.name);
    if (!cfg) throw new ValidationError(`Repository "${options.name}" not found in context`);
    if (cfg.immutable) {
      throw new ValidationError(
        `"${options.name}" is an immutable commit, not a working fork. Check it out first: rdc repo checkout ${options.name} --tag <name> -m ${options.machine}`
      );
    }

    const parent = cfg.headCommit ?? '';
    const commitGuid = randomUUID();

    const result: LocalExecuteResult = await localExecutorService.execute({
      functionName: 'repository_commit',
      machineName: options.machine,
      params: {
        repository: options.name,
        tag: commitGuid,
        message: options.message,
        ...(options.author ? { author: options.author } : {}),
        ...(parent ? { commitParent: parent } : {}),
        network_id: cfg.networkId,
      },
      debug: options.debug,
    });

    if (!result.success) {
      renderLocalExecutionFailure(result, t('commands.repo.commit.failed'));
      return;
    }

    // Register the immutable commit object and advance the working fork's tip.
    await configService.addRepository(commitGuid, {
      repositoryGuid: commitGuid,
      networkId: cfg.networkId,
      credential: cfg.credential,
      grandGuid: cfg.grandGuid ?? cfg.repositoryGuid,
      parentGuid: cfg.repositoryGuid,
      immutable: true,
      commitMessage: options.message,
      commitAuthor: options.author,
      commitParent: parent || undefined,
    });
    const workingKey = (await configService.getRepositoryKey(options.name)) ?? options.name;
    await configService.addRepository(workingKey, { ...cfg, headCommit: commitGuid });

    outputService.success(
      t('commands.repo.commit.completed', {
        commit: commitGuid.slice(0, 12),
        message: options.message,
      })
    );
  } catch (error) {
    handleError(error);
  }
}

/** repo branch <branchName> --name <workingFork> */
async function handleBranch(branchName: string, options: { name: string }): Promise<void> {
  try {
    await assertCommandPolicy(CMD.REPO_BRANCH, options.name);
    const cfg = await configService.getRepository(options.name);
    if (!cfg) throw new ValidationError(`Repository "${options.name}" not found in context`);
    const tip = cfg.headCommit;
    if (!tip) {
      throw new ValidationError(
        `"${options.name}" has no commits yet — run 'rdc repo commit' before creating a branch`
      );
    }
    const branches = { ...(cfg.branches ?? {}), [branchName]: tip };
    const workingKey = (await configService.getRepositoryKey(options.name)) ?? options.name;
    await configService.addRepository(workingKey, { ...cfg, branches });
    outputService.success(
      t('commands.repo.branch.completed', { branch: branchName, commit: tip.slice(0, 12) })
    );
  } catch (error) {
    handleError(error);
  }
}

/** repo checkout <commit|branch> --tag <newWorking> -m <machine> */
async function handleCheckout(
  target: string,
  options: {
    tag: string;
    machine: string;
    from?: string;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  try {
    await assertCommandPolicy(CMD.REPO_CHECKOUT, target);
    await assertMachineExists(options.machine);

    // Resolve target to a commit GUID: a branch name on --from's working fork,
    // or a direct commit reference.
    let commitRef = target;
    if (options.from) {
      const fromCfg = await configService.getRepository(options.from);
      const tip = fromCfg?.branches?.[target];
      if (!tip) {
        throw new ValidationError(`branch "${target}" not found on "${options.from}"`);
      }
      commitRef = tip;
    }
    const commitCfg = await configService.getRepository(commitRef);
    if (!commitCfg) throw new ValidationError(`commit "${commitRef}" not found in context`);

    // Checkout == reflink-clone the immutable commit into a fresh writable
    // fork. The fork's config key uses a HUMAN base name when one is known:
    // the --from working fork's base. A direct commit-GUID checkout keeps
    // the commit's key as base (the caller addressed it by GUID anyway).
    const baseName = parseRepoRef(options.from ?? commitRef).name;
    await handleForkAction(commitRef, options.tag, {
      machine: options.machine,
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
      forkBaseName: baseName,
    });

    // Record the new working fork's tip = the checked-out commit.
    const newKey = compositeKey(baseName, options.tag);
    const newCfg = await configService.getRepository(newKey);
    if (newCfg) {
      await configService.addRepository(newKey, {
        ...newCfg,
        headCommit: commitCfg.repositoryGuid,
      });
    }
  } catch (error) {
    handleError(error);
  }
}

/** repo log --name <workingFork|commit> -m <machine> */
async function handleLog(options: {
  name: string;
  machine: string;
  json?: boolean;
  debug?: boolean;
}): Promise<void> {
  try {
    await assertMachineExists(options.machine);
    const cfg = await configService.getRepository(options.name);
    if (!cfg) throw new ValidationError(`Repository "${options.name}" not found in context`);
    const tip = cfg.headCommit ?? (cfg.immutable ? cfg.repositoryGuid : undefined);
    if (!tip) {
      throw new ValidationError(`"${options.name}" has no commits yet`);
    }

    const result: LocalExecuteResult = await localExecutorService.execute({
      functionName: 'repository_log',
      machineName: options.machine,
      params: { repository: tip },
      debug: options.debug,
    });
    if (!result.success) {
      renderLocalExecutionFailure(result, t('commands.repo.log.failed'));
      return;
    }

    const parsed = parseRenetJson<{ entries: Record<string, unknown>[] }>(result.stdout ?? '');
    if (options.json) {
      outputService.print(parsed ?? { entries: [] }, 'json');
      return;
    }
    for (const e of parsed?.entries ?? []) renderLogEntry(e);
  } catch (error) {
    handleError(error);
  }
}

/** Render one commit entry in `git log`-like form. */
function renderLogEntry(e: Record<string, unknown>): void {
  outputService.info(`commit ${String(e.guid ?? '')}`);
  if (e.author || e.committed_at) {
    outputService.info(`  Author: ${e.author ?? ''}  Date: ${e.committed_at ?? ''}`);
  }
  if (e.message) outputService.info(`  ${e.message}`);
}

/** Derive the common-ancestor GUID for a per-file three-way merge, or undefined for whole-image. */
function deriveMergeBase(
  resolve: string | undefined,
  sourceName: string,
  sourceCfg: { commitParent?: string },
  targetCfg: { headCommit?: string }
): string | undefined {
  if (!resolve) return undefined;
  const base = sourceCfg.commitParent ?? targetCfg.headCommit;
  if (!base) {
    throw new ValidationError(
      `--resolve needs a common ancestor; "${sourceName}" has no recorded commit parent`
    );
  }
  return base;
}

/** repo merge --name <target> --from <source> -m <machine> [--force] [--resolve ours|theirs] */
async function handleMerge(options: {
  name: string;
  from: string;
  machine: string;
  force?: boolean;
  resolve?: string;
  base?: string;
  debug?: boolean;
}): Promise<void> {
  try {
    await assertCommandPolicy(CMD.REPO_MERGE, options.name);
    await assertMachineExists(options.machine);

    const targetCfg = await configService.getRepository(options.name);
    if (!targetCfg) throw new ValidationError(`Repository "${options.name}" not found in context`);
    const sourceCfg = await configService.getRepository(options.from);
    if (!sourceCfg) throw new ValidationError(`Source "${options.from}" not found in context`);

    // For a per-file three-way merge, use the explicit --base if given, else
    // derive the common ancestor from the source commit's recorded parent (or the
    // target's headCommit). renet validates the --resolve value itself.
    const base = options.resolve
      ? (options.base ?? deriveMergeBase(options.resolve, options.from, sourceCfg, targetCfg))
      : undefined;

    const result: LocalExecuteResult = await localExecutorService.execute({
      functionName: 'repository_merge',
      machineName: options.machine,
      params: {
        repository: options.name,
        from: sourceCfg.repositoryGuid,
        ...(options.force ? { force: true } : {}),
        ...(options.resolve ? { resolve: options.resolve, base: base as string } : {}),
        network_id: targetCfg.networkId,
      },
      debug: options.debug,
    });
    if (!result.success) {
      renderLocalExecutionFailure(result, t('commands.repo.merge.failed'));
      return;
    }
    // The merged target now carries the source's commit; track its tip.
    const targetKey = (await configService.getRepositoryKey(options.name)) ?? options.name;
    await configService.addRepository(targetKey, {
      ...targetCfg,
      headCommit: sourceCfg.repositoryGuid,
    });
    outputService.success(
      t('commands.repo.merge.completed', { source: options.from, target: options.name })
    );
  } catch (error) {
    handleError(error);
  }
}

/** Register git-like branching commands (Phase 2 & 4 of issue #75). */
export function registerRepoBranchingCommands(repo: Command): void {
  repo
    .command('commit')
    .summary(t('commands.repo.commit.descriptionShort'))
    .description(t('commands.repo.commit.description'))
    .requiredOption('--name <name>', t('commands.repo.commit.nameOption'))
    .requiredOption('--message <msg>', t('commands.repo.commit.messageOption'))
    .option('--author <author>', t('commands.repo.commit.authorOption'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(handleCommit);

  repo
    .command('branch')
    .summary(t('commands.repo.branch.descriptionShort'))
    .description(t('commands.repo.branch.description'))
    .requiredOption('--branch <branch>', t('commands.repo.branch.branchOption'))
    .requiredOption('--name <name>', t('commands.repo.branch.workingOption'))
    .action((options: { branch: string; name: string }) => handleBranch(options.branch, options));

  repo
    .command('checkout')
    .summary(t('commands.repo.checkout.descriptionShort'))
    .description(t('commands.repo.checkout.description'))
    .requiredOption('--ref <commit|branch>', t('commands.repo.checkout.refOption'))
    .requiredOption('--tag <name>', t('commands.repo.checkout.tagOption'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--from <workingFork>', t('commands.repo.checkout.fromOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      (options: {
        ref: string;
        tag: string;
        machine: string;
        from?: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => handleCheckout(options.ref, options)
    );

  repo
    .command('log')
    .summary(t('commands.repo.log.descriptionShort'))
    .description(t('commands.repo.log.description'))
    .requiredOption('--name <name>', t('commands.repo.log.nameOption'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--json', t('commands.repo.log.jsonOption'))
    .option('--debug', t('options.debug'))
    .action(handleLog);

  repo
    .command('merge')
    .summary(t('commands.repo.merge.descriptionShort'))
    .description(t('commands.repo.merge.description'))
    .requiredOption('--name <name>', t('commands.repo.merge.nameOption'))
    .requiredOption('--from <source>', t('commands.repo.merge.fromOption'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--force', t('commands.repo.merge.forceOption'))
    .option('--resolve <ours|theirs>', t('commands.repo.merge.resolveOption'))
    .option('--base <guid>', t('commands.repo.merge.baseOption'))
    .option('--debug', t('options.debug'))
    .action(handleMerge);
}
