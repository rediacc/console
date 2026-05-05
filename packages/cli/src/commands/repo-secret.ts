/**
 * Per-repo secrets CLI surface (`rdc repo secret …`).
 *
 * **Write-only model (V2).** Mirrors GitHub Actions secrets:
 *   - `set` / `unset` write or delete.
 *   - `list` returns names + modes (never values, never digests).
 *   - `get` returns `{ key, mode, digest }` only — the plaintext value is
 *     never returned to anyone (human or agent). Use `--current` to verify
 *     a value you already know via passwd-style precondition.
 *
 * **Symmetric mutation gate.** Humans and agents both need `--current`
 * matching the previous value to overwrite or unset. Either can use
 * `--rotate-secret` to skip the precondition (audited as a rotation).
 *
 * **No `grandGuard`.** With write-only there's no plaintext read attack to
 * gate. Mutation-gate is the actual safety property; the fork-isolation
 * invariant from V1 (registerFork doesn't copy `secrets`) is unchanged.
 */

import { createHash } from 'node:crypto';
import type { Command } from 'commander';
import { auditLog, type AuditEventDraft } from '../services/audit-log.js';
import { configService } from '../services/config-resources.js';
import {
  evaluateMutations,
  PreconditionMismatchError,
  type MutationEntry,
} from '../services/mutation-gate.js';
import {
  deleteRepositorySecret,
  listRepositorySecretKeyModes,
  readRepositorySecret,
  writeRepositorySecret,
} from '../services/repo-secrets-store.js';
import { canonicalJson, shortFingerprint } from '../schema/walker.js';
import { handleError, PreconditionValidationError, ValidationError } from '../utils/errors.js';
import { outputService } from '../services/output.js';
import { t } from '../i18n/index.js';
import type { NextAction } from '../types/errors.js';
import type { SecretMode } from '../types/index.js';

function emit(draft: AuditEventDraft): void {
  try {
    const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
    auditLog(`${xdg}/rediacc`, draft);
  } catch {
    /* audit-log failure must never block the user */
  }
}

interface SecretGetOptions {
  name: string;
  key: string;
}

interface SecretListOptions {
  name: string;
}

interface SecretSetOptions {
  name: string;
  key: string;
  value: string;
  mode?: SecretMode;
  current?: string;
  rotateSecret?: boolean;
}

interface SecretUnsetOptions {
  name: string;
  key: string;
  current?: string;
  rotateSecret?: boolean;
}

async function readValueFromStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk as Buffer);
  }
  // Strip a single trailing newline (common from `echo`/`cat`); preserve
  // intentional internal newlines (multi-line PEMs etc.).
  return Buffer.concat(chunks).toString('utf-8').replace(/\n$/, '');
}

function hashValue(s: string): string {
  return createHash('sha256').update(canonicalJson(s)).digest('hex');
}

function buildSecretPointer(repoKey: string, secretKey: string): string {
  // RFC 6901: escape `~` → `~0`, `/` → `~1` in segment values
  const escapedRepo = repoKey.replaceAll('~', '~0').replaceAll('/', '~1');
  const escapedSecret = secretKey.replaceAll('~', '~0').replaceAll('/', '~1');
  return `/resources/repositories/${escapedRepo}/secrets/${escapedSecret}/value`;
}

/**
 * Build the structured next-action hint for a precondition failure.
 * Two options: re-read the digest and retry with --current, or skip the
 * precondition via --rotate-secret. The original argv is reconstructed
 * so the agent can relay the exact retry command verbatim.
 */
function buildPreconditionNext(repoKey: string, key: string, originalArgs: string[]): NextAction {
  const rotateCmd = [...originalArgs.filter((a) => a !== '--rotate-secret'), '--rotate-secret'];
  return {
    summary: t('errors.precondition.next.summary'),
    options: [
      {
        description: t('errors.precondition.next.options.confirm.description'),
        run: t('errors.precondition.next.options.confirm.run', { repository: repoKey, key }),
      },
      {
        description: t('errors.precondition.next.options.rotate.description'),
        run: rotateCmd.join(' '),
      },
    ],
  };
}

async function handleSecretGet(options: SecretGetOptions): Promise<void> {
  const repoKey = await configService.getRepositoryKey(options.name);
  if (!repoKey) {
    throw new ValidationError(
      t('commands.repo.secret.get.repoNotFound', { repository: options.name })
    );
  }

  const entry = readRepositorySecret(await configService.getRepository(repoKey), options.key);
  if (!entry) {
    throw new ValidationError(
      t('commands.repo.secret.get.notFound', { key: options.key, repository: options.name })
    );
  }

  // Write-only model: NEVER return the plaintext value, regardless of caller.
  // Digest lets the user verify "is this still the value I think it is" via
  // the --current ceremony on a subsequent `set`.
  const pointer = buildSecretPointer(repoKey, options.key);
  const digest = shortFingerprint(entry.value);
  outputService.print({ key: options.key, mode: entry.mode, digest }, 'json');
  emit({ command: 'repo secret get', paths: [pointer], outcome: 'ok' });
}

async function handleSecretList(options: SecretListOptions): Promise<void> {
  const repoKey = await configService.getRepositoryKey(options.name);
  if (!repoKey) {
    throw new ValidationError(
      t('commands.repo.secret.get.repoNotFound', { repository: options.name })
    );
  }

  const entries = listRepositorySecretKeyModes(await configService.getRepository(repoKey));
  if (entries.length === 0) {
    outputService.print({ repository: repoKey, secrets: [] }, 'json');
    return;
  }
  outputService.print({ repository: repoKey, secrets: entries }, 'json');
}

async function resolveRepoKeyOrThrow(name: string): Promise<string> {
  const repoKey = await configService.getRepositoryKey(name);
  if (!repoKey) {
    throw new ValidationError(t('commands.repo.secret.get.repoNotFound', { repository: name }));
  }
  return repoKey;
}

function runMutationGate(
  command: string,
  entry: MutationEntry,
  options: { current?: string; rotateSecret?: boolean; name: string; key: string },
  repoKey: string,
  config: NonNullable<Awaited<ReturnType<typeof configService.getCurrent>>>,
  originalArgs: string[]
): void {
  const knowledge: Record<string, string> = {};
  if (options.current !== undefined) {
    knowledge[entry.pointer] = hashValue(options.current);
  }
  const rotateAcknowledged = options.rotateSecret ? new Set<string>([entry.pointer]) : undefined;

  try {
    evaluateMutations([entry], {
      previousConfig: config,
      knowledge,
      rotateAcknowledged,
    });
  } catch (err) {
    if (err instanceof PreconditionMismatchError) {
      emit({
        command,
        paths: [entry.pointer],
        outcome: 'precondition_failed',
        reason: err.failures.map((f) => f.reason).join('; '),
      });
      throw new PreconditionValidationError(
        err.message,
        buildPreconditionNext(repoKey, options.key, originalArgs)
      );
    }
    throw err;
  }
}

async function handleSecretSet(options: SecretSetOptions): Promise<void> {
  if (options.current !== undefined && options.rotateSecret) {
    throw new ValidationError(t('errors.repo.secret.mutuallyExclusive'));
  }

  const repoKey = await resolveRepoKeyOrThrow(options.name);
  const value = options.value === '-' ? await readValueFromStdin() : options.value;
  if (value.length === 0) {
    throw new ValidationError(t('errors.repo.secret.emptyValue'));
  }

  const mode: SecretMode = options.mode as SecretMode;
  const pointer = buildSecretPointer(repoKey, options.key);
  const previousEntry = readRepositorySecret(
    await configService.getRepository(repoKey),
    options.key
  );
  const config = await configService.getCurrent();
  if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

  runMutationGate(
    'repo secret set',
    { pointer, previousValue: previousEntry?.value, newValue: value },
    options,
    repoKey,
    config,
    [
      'rdc repo secret set',
      `--name ${options.name}`,
      `--key ${options.key}`,
      `--value <new-value>`,
      `--mode ${mode}`,
    ]
  );

  await writeRepositorySecret(await configService.getResourceState(), repoKey, options.key, {
    mode,
    value,
  });

  emit({
    command: 'repo secret set',
    paths: [pointer],
    outcome: options.rotateSecret ? 'rotate_no_knowledge' : 'ok',
    configId: config.id,
    configVersion: config.version,
  });

  outputService.success(
    t('commands.repo.secret.set.success', { key: options.key, mode, repository: repoKey })
  );
}

async function handleSecretUnset(options: SecretUnsetOptions): Promise<void> {
  if (options.current !== undefined && options.rotateSecret) {
    throw new ValidationError(t('errors.repo.secret.mutuallyExclusive'));
  }

  const repoKey = await resolveRepoKeyOrThrow(options.name);
  const previousEntry = readRepositorySecret(
    await configService.getRepository(repoKey),
    options.key
  );
  if (!previousEntry) {
    throw new ValidationError(
      t('commands.repo.secret.get.notFound', { key: options.key, repository: options.name })
    );
  }

  const pointer = buildSecretPointer(repoKey, options.key);
  const config = await configService.getCurrent();
  if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

  runMutationGate(
    'repo secret unset',
    { pointer, previousValue: previousEntry.value, newValue: undefined },
    options,
    repoKey,
    config,
    ['rdc repo secret unset', `--name ${options.name}`, `--key ${options.key}`]
  );

  await deleteRepositorySecret(
    await configService.getResourceState(),
    options.name,
    repoKey,
    options.key
  );

  emit({
    command: 'repo secret unset',
    paths: [pointer],
    outcome: options.rotateSecret ? 'rotate_no_knowledge' : 'ok',
    configId: config.id,
    configVersion: config.version,
  });

  outputService.success(
    t('commands.repo.secret.unset.success', { key: options.key, repository: repoKey })
  );
}

export function registerRepoSecretCommands(repoCommand: Command): void {
  const secret = repoCommand
    .command('secret')
    .summary(t('commands.repo.secret.descriptionShort'))
    .description(t('commands.repo.secret.description'));

  secret
    .command('get')
    .summary(t('commands.repo.secret.get.descriptionShort'))
    .description(t('commands.repo.secret.get.description'))
    .requiredOption('--name <repository>', t('commands.repo.secret.nameOption'))
    .requiredOption('--key <KEY>', t('commands.repo.secret.keyOption'))
    .action(async (options: SecretGetOptions) => {
      try {
        await handleSecretGet(options);
      } catch (error) {
        handleError(error);
      }
    });

  secret
    .command('list')
    .summary(t('commands.repo.secret.list.descriptionShort'))
    .description(t('commands.repo.secret.list.description'))
    .requiredOption('--name <repository>', t('commands.repo.secret.nameOption'))
    .action(async (options: SecretListOptions) => {
      try {
        await handleSecretList(options);
      } catch (error) {
        handleError(error);
      }
    });

  secret
    .command('set')
    .summary(t('commands.repo.secret.set.descriptionShort'))
    .description(t('commands.repo.secret.set.description'))
    .requiredOption('--name <repository>', t('commands.repo.secret.nameOption'))
    .requiredOption('--key <KEY>', t('commands.repo.secret.keyOption'))
    .requiredOption('--value <value>', t('commands.repo.secret.valueOption'))
    .option('--mode <mode>', t('commands.repo.secret.modeOption'), 'file')
    .option('--current <value>', t('commands.repo.secret.currentOption'))
    .option('--rotate-secret', t('commands.repo.secret.rotateOption'))
    .action(async (options: SecretSetOptions) => {
      try {
        const m = options.mode as string;
        if (m !== 'env' && m !== 'file') {
          throw new ValidationError(t('errors.repo.secret.badMode', { mode: m }));
        }
        await handleSecretSet(options);
      } catch (error) {
        handleError(error);
      }
    });

  secret
    .command('unset')
    .summary(t('commands.repo.secret.unset.descriptionShort'))
    .description(t('commands.repo.secret.unset.description'))
    .requiredOption('--name <repository>', t('commands.repo.secret.nameOption'))
    .requiredOption('--key <KEY>', t('commands.repo.secret.keyOption'))
    .option('--current <value>', t('commands.repo.secret.currentOption'))
    .option('--rotate-secret', t('commands.repo.secret.rotateOption'))
    .action(async (options: SecretUnsetOptions) => {
      try {
        await handleSecretUnset(options);
      } catch (error) {
        handleError(error);
      }
    });
}
