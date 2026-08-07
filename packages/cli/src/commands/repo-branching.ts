import { randomUUID } from 'node:crypto';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { type ExecuteResult, getExecutor } from '../services/executor/executor-factory.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { compositeKey, parseRepoRef } from '../utils/config-schema.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoRefLocal } from '../utils/repo-target.js';
import { handleForkAction } from './repo-fork.js';

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

/** repo commit <ref> --message <msg> [--author] */
async function handleCommit(
  ref: string,
  options: {
    message: string;
    author?: string;
    debug?: boolean;
  }
): Promise<void> {
  try {
    // Mutating verb: derive the execution machine from the ref's placement
    // (spec/03 §2.3). No `-m`/`--cluster` any more.
    const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
    await assertCommandPolicy(CMD.REPO_COMMIT, repoKey);

    const cfg = await configService.getRepository(repoKey);
    if (!cfg) throw new ValidationError(`Repository "${name}" not found in context`);
    if (cfg.immutable) {
      throw new ValidationError(
        `"${name}" is an immutable commit, not a working fork. Check it out first: rdc repo checkout ${repoKey} --tag <name>`
      );
    }

    const parent = cfg.headCommit ?? '';
    const commitGuid = randomUUID();

    const result: ExecuteResult = await getExecutor().execute({
      functionName: 'repository_commit',
      machineName,
      ...(kubeCluster !== undefined && { kubeCluster }),
      // #74: renet resolves the image from the machine vault, so the datastore
      // the repo is RECORDED on has to be declared or the commit is written
      // against the machine's default.
      datastore: await recordedDatastoreMount(repoKey),
      params: {
        repository: repoKey,
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
    const workingKey = (await configService.getRepositoryKey(repoKey)) ?? repoKey;
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

/** repo branch <ref> --branch <name> */
async function handleBranch(ref: string, options: { branch: string }): Promise<void> {
  try {
    // Config-only ref op (spec §5.4): points a branch at a working fork in the
    // config; it never dispatches to a machine, so resolve the family locally.
    const { name, repoKey } = await resolveRepoRefLocal(ref);
    await assertCommandPolicy(CMD.REPO_BRANCH, repoKey);
    const cfg = await configService.getRepository(repoKey);
    if (!cfg) throw new ValidationError(`Repository "${name}" not found in context`);
    const tip = cfg.headCommit;
    if (!tip) {
      throw new ValidationError(
        `"${name}" has no commits yet; run 'rdc repo commit' before creating a branch`
      );
    }
    const branches = { ...(cfg.branches ?? {}), [options.branch]: tip };
    const workingKey = (await configService.getRepositoryKey(repoKey)) ?? repoKey;
    await configService.addRepository(workingKey, { ...cfg, branches });
    outputService.success(
      t('commands.repo.branch.completed', { branch: options.branch, commit: tip.slice(0, 12) })
    );
  } catch (error) {
    handleError(error);
  }
}

/** repo checkout <commit-or-branch-ref> --tag <newWorking> [--from <workingFork>] */
async function handleCheckout(
  target: string,
  options: {
    tag: string;
    from?: string;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  try {
    // Resolve target to a commit GUID: a branch name on --from's working fork,
    // or a direct commit reference. (The commit/branch ref is NOT a repo family,
    // so it cannot itself derive an execution machine.)
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

    // Mutating verb: derive the execution machine from the SOURCE family's
    // placement (spec/03 §2.3) — the working fork named by --from, else the base
    // repo the commit belongs to. The shared handleForkAction accepts an optional
    // kubeCluster, so a kubernetes-world source forks with KUBECONFIG threaded;
    // a docker source leaves it unset and forks against the machine's daemon.
    const { repoKey, machineName, kubeCluster } = await resolveRepoRef(options.from ?? baseName);
    await assertCommandPolicy(CMD.REPO_CHECKOUT, repoKey);

    await handleForkAction(commitRef, options.tag, {
      machine: machineName,
      ...(kubeCluster !== undefined && { kubeCluster }),
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

/** repo log <ref> */
async function handleLog(ref: string, options: { debug?: boolean }): Promise<void> {
  try {
    // Read-only verb: skip step 5's remote round-trip (spec/03 §2.3 tail).
    const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref, {
      readOnly: true,
    });
    const cfg = await configService.getRepository(repoKey);
    if (!cfg) throw new ValidationError(`Repository "${name}" not found in context`);
    const tip = cfg.headCommit ?? (cfg.immutable ? cfg.repositoryGuid : undefined);
    if (!tip) {
      throw new ValidationError(`"${name}" has no commits yet`);
    }

    const result: ExecuteResult = await getExecutor().execute({
      functionName: 'repository_log',
      machineName,
      ...(kubeCluster !== undefined && { kubeCluster }),
      // #74: `tip` is a commit GUID inside this repo's family, so the family's
      // recorded placement is where renet must look for it.
      datastore: await recordedDatastoreMount(repoKey),
      params: { repository: tip },
      debug: options.debug,
    });
    if (!result.success) {
      renderLocalExecutionFailure(result, t('commands.repo.log.failed'));
      return;
    }

    const parsed = parseRenetJson<{ entries: Record<string, unknown>[] }>(result.stdout ?? '');
    // Structured output rides the global `-o json` format now; the dedicated
    // `--json` flag is gone (spec/03 §5.4).
    if (getOutputFormat() === 'json') {
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

/** repo merge <ref> --from <source> [--force] [--resolve ours|theirs] [--base <guid>] */
async function handleMerge(
  ref: string,
  options: {
    from: string;
    force?: boolean;
    resolve?: string;
    base?: string;
    debug?: boolean;
  }
): Promise<void> {
  try {
    const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
    await assertCommandPolicy(CMD.REPO_MERGE, repoKey);

    const targetCfg = await configService.getRepository(repoKey);
    if (!targetCfg) throw new ValidationError(`Repository "${name}" not found in context`);
    const sourceCfg = await configService.getRepository(options.from);
    if (!sourceCfg) throw new ValidationError(`Source "${options.from}" not found in context`);

    // For a per-file three-way merge, use the explicit --base if given, else
    // derive the common ancestor from the source commit's recorded parent (or the
    // target's headCommit). renet validates the --resolve value itself.
    const base = options.resolve
      ? (options.base ?? deriveMergeBase(options.resolve, options.from, sourceCfg, targetCfg))
      : undefined;

    const result: ExecuteResult = await getExecutor().execute({
      functionName: 'repository_merge',
      machineName,
      ...(kubeCluster !== undefined && { kubeCluster }),
      // #74: merge reads BOTH sides from one datastore — `--from` names a GUID
      // in the same family, which is why the target's placement covers it.
      datastore: await recordedDatastoreMount(repoKey),
      params: {
        repository: repoKey,
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
    const targetKey = (await configService.getRepositoryKey(repoKey)) ?? repoKey;
    await configService.addRepository(targetKey, {
      ...targetCfg,
      headCommit: sourceCfg.repositoryGuid,
    });
    outputService.success(
      t('commands.repo.merge.completed', { source: options.from, target: name })
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
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--message <msg>', t('commands.repo.commit.messageOption'))
    .option('--author <author>', t('commands.repo.commit.authorOption'))
    .option('--debug', t('options.debug'))
    .action(handleCommit);

  repo
    .command('branch')
    .summary(t('commands.repo.branch.descriptionShort'))
    .description(t('commands.repo.branch.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--branch <branch>', t('commands.repo.branch.branchOption'))
    .action(handleBranch);

  repo
    .command('checkout')
    .summary(t('commands.repo.checkout.descriptionShort'))
    .description(t('commands.repo.checkout.description'))
    .argument('<commit-or-branch-ref>', t('options.repoRef'))
    .requiredOption('--tag <name>', t('commands.repo.checkout.tagOption'))
    .option('--from <workingFork>', t('commands.repo.checkout.fromOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(handleCheckout);

  repo
    .command('log')
    .summary(t('commands.repo.log.descriptionShort'))
    .description(t('commands.repo.log.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .action(handleLog);

  repo
    .command('merge')
    .summary(t('commands.repo.merge.descriptionShort'))
    .description(t('commands.repo.merge.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--from <source>', t('commands.repo.merge.fromOption'))
    .option('--force', t('commands.repo.merge.forceOption'))
    .addOption(
      new Option('--resolve <ours|theirs>', t('commands.repo.merge.resolveOption')).choices([
        'ours',
        'theirs',
      ])
    )
    .option('--base <guid>', t('commands.repo.merge.baseOption'))
    .option('--debug', t('options.debug'))
    .action(handleMerge);
}
