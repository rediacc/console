import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { ForensicsClient } from '../services/forensics/client.js';
import { type RowKind, type RowsRead, readRepoRows, rowLines } from '../services/forensics/rows.js';
import { parseWindow } from '../services/forensics/window.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { resolveRepoRefLocal } from '../utils/repo-ref-local.js';

interface WindowOptions {
  since?: string;
  until?: string;
}

export interface RepoRowsDeps {
  client: ForensicsClient;
  /** The repository GUID the account store keys its evidence by. */
  repoGuid: (ref: string) => Promise<string>;
  now: () => Date;
}

async function configRepoGuid(ref: string): Promise<string> {
  const { name, repoKey } = await resolveRepoRefLocal(ref);
  const repo = await configService.getRepository(repoKey);
  if (!repo?.repositoryGuid) {
    throw new CliExitError(ERROR_CODES.NOT_FOUND, t('forensics.noRepoGuid', { name }));
  }
  return repo.repositoryGuid;
}

const defaultDeps = (): RepoRowsDeps => ({
  client: new ForensicsClient(),
  repoGuid: configRepoGuid,
  now: () => new Date(),
});

/** `rdc repo flows|opens <ref>`: the repo's network flows or file opens in the window, gaps included. */
export async function runRepoRows(
  kind: RowKind,
  ref: string,
  options: WindowOptions,
  deps: RepoRowsDeps = defaultDeps()
): Promise<RowsRead> {
  const window = parseWindow(options, deps.now());
  const read = await readRepoRows(deps.client, await deps.repoGuid(ref), window, kind);
  if (getOutputFormat() === 'json') outputService.print(read, 'json');
  else outputService.print(rowLines(read));
  return read;
}

function register(repo: Command, kind: RowKind): void {
  const keys =
    kind === 'flow'
      ? {
          summary: t('commands.repo.flows.descriptionShort'),
          description: t('commands.repo.flows.description'),
        }
      : {
          summary: t('commands.repo.opens.descriptionShort'),
          description: t('commands.repo.opens.description'),
        };
  repo
    .command(kind === 'flow' ? 'flows' : 'opens')
    .summary(keys.summary)
    .description(keys.description)
    .argument('<ref>', t('options.repoRef'))
    .option('--since <when>', t('commands.repo.rowsSinceOption'))
    .option('--until <when>', t('commands.repo.rowsUntilOption'))
    .action(async (ref: string, options: WindowOptions) => {
      try {
        await runRepoRows(kind, ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerRepoFlowsCommands(repo: Command): void {
  register(repo, 'flow');
  register(repo, 'open');
}
