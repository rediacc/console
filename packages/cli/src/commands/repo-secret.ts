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
 *
 * **Addressing (reshape P4).** Every verb takes a positional `<ref>` and
 * resolves the repo through `resolveRepoRefLocal`. Secret ops are config-local
 * (no remote round-trip, no machine dispatch), so they resolve the family/tag
 * WITHOUT deriving a placement machine — that keeps them working on a repo whose
 * datastore is detached or whose placement is not yet reconciled. The composite
 * `name:tag` key the flat-view store indexes by is rebuilt from the resolved
 * `name` + `tag` (the flattened repositories map is always keyed that way).
 */

import { createHash } from 'node:crypto';
import { canonicalJson } from '@rediacc/shared/config-schema';
import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { shortFingerprint } from '../schema/fingerprint.js';
import { configService } from '../services/config/config-resources.js';
import { type AuditEventDraft, auditLog } from '../services/core/audit-log.js';
import {
  evaluateMutations,
  type MutationEntry,
  PreconditionMismatchError,
} from '../services/core/mutation-gate.js';
import { outputService } from '../services/core/output.js';
import {
  deleteRepositorySecret,
  listRepositorySecretKeyModes,
  readRepositorySecret,
  writeRepositorySecret,
} from '../services/repo/repo-secrets-store.js';
import type { NextAction } from '../types/errors.js';
import type { SecretMode } from '../types/index.js';
import {
  getOutputFormat,
  handleError,
  PreconditionValidationError,
  ValidationError,
} from '../utils/errors.js';
import { resolveRepoRefLocal } from '../utils/repo-target.js';

function emit(draft: AuditEventDraft): void {
  try {
    const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
    auditLog(`${xdg}/rediacc`, draft);
  } catch {
    /* audit-log failure must never block the user */
  }
}

interface SecretGetOptions {
  key: string;
}

interface SecretSetOptions {
  key: string;
  value: string;
  mode?: SecretMode;
  current?: string;
  rotateSecret?: boolean;
}

interface SecretUnsetOptions {
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
  // RFC 6901: escape `~` → `~0`, `/` → `~1` in segment values. v3 keys
  // repositories by name into families of structural tags, so the composite
  // `name:tag` key splits into the `<name>/tags/<tag>` path.
  const escape = (s: string) => s.replaceAll('~', '~0').replaceAll('/', '~1');
  const colon = repoKey.indexOf(':');
  const base = colon === -1 ? repoKey : repoKey.slice(0, colon);
  const tag = colon === -1 ? 'latest' : repoKey.slice(colon + 1);
  return `/resources/repositories/${escape(base)}/tags/${escape(tag)}/secrets/${escape(secretKey)}/value`;
}

/**
 * The flat-view store key (`name:tag`) for a resolved ref. The flattened
 * repositories map is always composite-keyed (`${base}:${tag}`), and the
 * store helpers index it directly, so a bare ref must be rebuilt with its
 * resolved tag before it can touch the map.
 */
async function resolveSecretRepoKey(ref: string): Promise<{ name: string; repoKey: string }> {
  // Config-local: secret ops read/write the config only (secrets are injected at
  // up() time, never set on a machine), so resolve the family/tag WITHOUT deriving
  // a placement machine. This keeps secret get/list/set/unset working on a repo
  // whose datastore is detached or whose placement is not yet reconciled.
  const { name, tag } = await resolveRepoRefLocal(ref);
  return { name, repoKey: `${name}:${tag}` };
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

async function handleSecretGet(ref: string, options: SecretGetOptions): Promise<void> {
  // Read-only: derive the machine, skip step 5's remote round-trip.
  const { name, repoKey } = await resolveSecretRepoKey(ref);

  const entry = readRepositorySecret(await configService.getRepository(repoKey), options.key);
  if (!entry) {
    throw new ValidationError(
      t('commands.repo.secret.get.notFound', { key: options.key, repository: name })
    );
  }

  // Write-only model: NEVER return the plaintext value, regardless of caller.
  // Digest lets the user verify "is this still the value I think it is" via
  // the --current ceremony on a subsequent `set`.
  const pointer = buildSecretPointer(repoKey, options.key);
  const digest = shortFingerprint(entry.value);
  const format = getOutputFormat();
  if (format === 'table') {
    outputService.print([{ key: options.key, mode: entry.mode, digest }], 'table');
  } else {
    outputService.print({ key: options.key, mode: entry.mode, digest }, format);
  }
  emit({ command: 'repo secret get', paths: [pointer], outcome: 'ok' });
}

async function handleSecretList(ref: string): Promise<void> {
  // Read-only + config-local: derive the key, no remote round-trip.
  const { repoKey } = await resolveSecretRepoKey(ref);

  const entries = listRepositorySecretKeyModes(await configService.getRepository(repoKey));
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print({ repository: repoKey, secrets: entries }, format);
    return;
  }
  if (entries.length === 0) {
    outputService.info(t('commands.repo.secret.list.empty', { repository: repoKey }));
    return;
  }
  outputService.print(entries, 'table');
}

function runMutationGate(
  command: string,
  entry: MutationEntry,
  options: { current?: string; rotateSecret?: boolean; key: string },
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

async function handleSecretSet(ref: string, options: SecretSetOptions): Promise<void> {
  if (options.current !== undefined && options.rotateSecret) {
    throw new ValidationError(t('errors.repo.secret.mutuallyExclusive'));
  }

  // Mutating verb: resolve through the addressing model without readOnly.
  const { repoKey } = await resolveSecretRepoKey(ref);
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
  // Secret values are encrypted at rest (v3); the precondition gate needs the
  // decrypted config so digestForPointer sees the real stored value.
  const config = await configService.getDecryptedConfig();
  if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

  runMutationGate(
    'repo secret set',
    { pointer, previousValue: previousEntry?.value, newValue: value },
    options,
    repoKey,
    config,
    [
      'rdc repo secret set',
      repoKey,
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

async function handleSecretUnset(ref: string, options: SecretUnsetOptions): Promise<void> {
  if (options.current !== undefined && options.rotateSecret) {
    throw new ValidationError(t('errors.repo.secret.mutuallyExclusive'));
  }

  // Mutating verb: resolve through the addressing model without readOnly.
  const { name, repoKey } = await resolveSecretRepoKey(ref);
  const previousEntry = readRepositorySecret(
    await configService.getRepository(repoKey),
    options.key
  );
  if (!previousEntry) {
    throw new ValidationError(
      t('commands.repo.secret.get.notFound', { key: options.key, repository: name })
    );
  }

  const pointer = buildSecretPointer(repoKey, options.key);
  const config = await configService.getDecryptedConfig();
  if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

  runMutationGate(
    'repo secret unset',
    { pointer, previousValue: previousEntry.value, newValue: undefined },
    options,
    repoKey,
    config,
    ['rdc repo secret unset', repoKey, `--key ${options.key}`]
  );

  await deleteRepositorySecret(await configService.getResourceState(), name, repoKey, options.key);

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
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--key <KEY>', t('commands.repo.secret.keyOption'))
    .action(async (ref: string, options: SecretGetOptions) => {
      try {
        await handleSecretGet(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  secret
    .command('list')
    .summary(t('commands.repo.secret.list.descriptionShort'))
    .description(t('commands.repo.secret.list.description'))
    .argument('<ref>', t('options.repoRef'))
    .action(async (ref: string) => {
      try {
        await handleSecretList(ref);
      } catch (error) {
        handleError(error);
      }
    });

  secret
    .command('set')
    .summary(t('commands.repo.secret.set.descriptionShort'))
    .description(t('commands.repo.secret.set.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--key <KEY>', t('commands.repo.secret.keyOption'))
    .requiredOption('--value <value>', t('commands.repo.secret.valueOption'))
    .addOption(
      new Option('--mode <mode>', t('commands.repo.secret.modeOption'))
        .choices(['env', 'file'])
        .default('file')
    )
    .option('--current <value>', t('commands.repo.secret.currentOption'))
    .option('--rotate-secret', t('commands.repo.secret.rotateOption'))
    .action(async (ref: string, options: SecretSetOptions) => {
      try {
        const m = options.mode as string;
        if (m !== 'env' && m !== 'file') {
          throw new ValidationError(t('errors.repo.secret.badMode', { mode: m }));
        }
        await handleSecretSet(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  secret
    .command('unset')
    .summary(t('commands.repo.secret.unset.descriptionShort'))
    .description(t('commands.repo.secret.unset.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--key <KEY>', t('commands.repo.secret.keyOption'))
    .option('--current <value>', t('commands.repo.secret.currentOption'))
    .option('--rotate-secret', t('commands.repo.secret.rotateOption'))
    .action(async (ref: string, options: SecretUnsetOptions) => {
      try {
        await handleSecretUnset(ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}
