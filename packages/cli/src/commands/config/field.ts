/**
 * `rdc config field` — canonical pointer-addressed access to any config leaf.
 *
 * Subcommands:
 *   get <pointer>                          read a value (respects --reveal)
 *   set <pointer> --new <v> [--current]    mutate a value (gate-checked)
 *   unset <pointer> [--current]            delete a value (gate-checked)
 *   rotate <pointer> --new <v>             rotate a sensitive value without --current
 *   list [--sensitive] [--output json]     enumerate every registered pointer
 *
 * The gate check uses MutationGate (services/mutation-gate.ts). Every typed
 * command (`config machine add`, `config storage add`, etc.) is encouraged to
 * delegate here so they inherit `--current` enforcement automatically.
 */

import { createHash } from 'node:crypto';
import { isatty } from 'node:tty';
import type { Command } from 'commander';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { configService } from '../../services/config-resources.js';
import { auditLog, type AuditEventDraft } from '../../services/audit-log.js';
import { t } from '../../i18n/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import {
  evaluateMutations,
  PreconditionMismatchError,
  type MutationEntry,
} from '../../services/mutation-gate.js';
import { outputService } from '../../services/output.js';
import {
  canonicalJson,
  digestForPointer,
  getByPointer,
  metaForPointer,
  redactClone,
  shortFingerprint,
} from '../../schema/walker.js';
import {
  listSensitivityTemplates,
  SENSITIVITY_REGISTRY,
} from '../../schema/sensitivity.js';
import { handleError, ValidationError } from '../../utils/errors.js';

function configDir(): string {
  // configFileStorage exposes the directory via a private method indirectly —
  // for audit log placement we use $XDG_CONFIG_HOME/rediacc (same convention).
  const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
  return `${xdg}/rediacc`;
}

function emit(draft: AuditEventDraft): void {
  try {
    auditLog(configDir(), draft);
  } catch {
    /* audit-log failure must never block the user */
  }
}

/**
 * Apply a JSON-Pointer mutation to the in-memory config, returning the new
 * config. Operates on the v2 shape via getByPointer/setByPointer semantics.
 *
 * Set/unset are persisted by the caller via configFileStorage.update —
 * MutationGate validates first.
 */
function applyMutation(
  config: unknown,
  pointer: string,
  newValue: unknown
): unknown {
  if (pointer === '') return newValue;
  const segments = pointer
    .split('/')
    .slice(1)
    .map((s) => s.replace(/~1/g, '/').replace(/~0/g, '~'));
  const clone = JSON.parse(JSON.stringify(config)) as Record<string, unknown>;
  let cursor: Record<string, unknown> = clone;
  for (let i = 0; i < segments.length - 1; i++) {
    const segment = segments[i];
    if (cursor[segment] === undefined || cursor[segment] === null) {
      cursor[segment] = {};
    }
    cursor = cursor[segment] as Record<string, unknown>;
  }
  const last = segments[segments.length - 1];
  if (newValue === undefined) delete cursor[last];
  else cursor[last] = newValue;
  return clone;
}

export function registerFieldCommands(parent: Command, _program: Command): void {
  const field = parent.command('field').description(t('commands.config.field.description'));

  field
    .command('get <pointer>')
    .description(t('commands.config.field.get.description'))
    .option('--reveal', t('commands.config.field.get.optionReveal'))
    .option('--digest', t('commands.config.field.get.optionDigest'))
    .action(async (pointer: string, options: { reveal?: boolean; digest?: boolean }) => {
      try {
        const config = await configService.getCurrent();
        if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

        if (options.digest) {
          const digest = digestForPointer(config, pointer);
          if (digest === undefined)
            throw new ValidationError(t('errors.config.pointerNotFound', { pointer }));
          outputService.print({ pointer, digest }, 'json');
          emit({ command: 'config field get', paths: [pointer], outcome: 'ok' });
          return;
        }

        const value = getByPointer(config, pointer);
        if (value === undefined)
          throw new ValidationError(t('errors.config.pointerNotFound', { pointer }));

        const meta = metaForPointer(pointer);
        const isSensitive = meta && meta.kind !== 'public';

        if (isSensitive && !options.reveal) {
          const stub = `${meta.redactAs ?? `<redacted:${meta.kind}>`}:${shortFingerprint(value)}`;
          outputService.print({ pointer, value: stub }, 'json');
          emit({ command: 'config field get', paths: [pointer], outcome: 'ok' });
          return;
        }

        if (isSensitive && options.reveal) {
          if (isAgentEnvironment()) {
            emit({
              command: 'config field get --reveal',
              paths: [pointer],
              outcome: 'refused',
              reason: 'agent environment — use --digest for a safe fingerprint',
            });
            throw new ValidationError(t('errors.agent.fieldReveal', { pointer }));
          }
          if (!isatty(process.stdout.fd)) {
            throw new ValidationError(t('errors.agent.revealRequiresTty'));
          }
          emit({ command: 'config field get', paths: [pointer], outcome: 'reveal_granted' });
        }

        outputService.print({ pointer, value }, 'json');
      } catch (error) {
        handleError(error);
      }
    });

  field
    .command('set <pointer>')
    .description(t('commands.config.field.set.description'))
    .requiredOption('--new <value>', t('commands.config.field.set.optionNew'))
    .option('--current <value>', t('commands.config.field.set.optionCurrent'))
    .action(async (pointer: string, options: { new: string; current?: string }) => {
      try {
        const config = await configService.getCurrent();
        if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

        const newValue = parseValue(options.new);
        const previousValue = getByPointer(config, pointer);

        const knowledge: Record<string, string> = {};
        if (options.current !== undefined) {
          const claim = parseValue(options.current);
          knowledge[pointer] = createHash('sha256')
            .update(canonicalJson(claim))
            .digest('hex');
        }

        try {
          evaluateMutations(
            [{ pointer, previousValue, newValue }] as MutationEntry[],
            { previousConfig: config, knowledge }
          );
        } catch (err) {
          if (err instanceof PreconditionMismatchError) {
            emit({
              command: 'config field set',
              paths: [pointer],
              outcome: 'precondition_failed',
              reason: err.failures.map((f) => f.reason).join('; '),
            });
            throw new ValidationError(err.message);
          }
          throw err;
        }

        const configName = configService.getCurrentName();
        await configFileStorage.update(configName, (cfg) => applyMutation(cfg, pointer, newValue) as typeof cfg);

        emit({
          command: 'config field set',
          paths: [pointer],
          outcome: 'ok',
          configId: config.id,
          configVersion: config.version,
        });

        outputService.success(t('commands.config.field.set.success', { pointer }));
      } catch (error) {
        handleError(error);
      }
    });

  field
    .command('unset <pointer>')
    .description(t('commands.config.field.unset.description'))
    .option('--current <value>', t('commands.config.field.unset.optionCurrent'))
    .action(async (pointer: string, options: { current?: string }) => {
      try {
        const config = await configService.getCurrent();
        if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

        const previousValue = getByPointer(config, pointer);
        if (previousValue === undefined) {
          throw new ValidationError(t('errors.config.pointerNotFound', { pointer }));
        }

        const knowledge: Record<string, string> = {};
        if (options.current !== undefined) {
          const claim = parseValue(options.current);
          knowledge[pointer] = createHash('sha256')
            .update(canonicalJson(claim))
            .digest('hex');
        }

        try {
          evaluateMutations(
            [{ pointer, previousValue, newValue: undefined }] as MutationEntry[],
            { previousConfig: config, knowledge }
          );
        } catch (err) {
          if (err instanceof PreconditionMismatchError) {
            emit({
              command: 'config field unset',
              paths: [pointer],
              outcome: 'precondition_failed',
              reason: err.failures.map((f) => f.reason).join('; '),
            });
            throw new ValidationError(err.message);
          }
          throw err;
        }

        const configName = configService.getCurrentName();
        await configFileStorage.update(configName, (cfg) => applyMutation(cfg, pointer, undefined) as typeof cfg);

        emit({
          command: 'config field unset',
          paths: [pointer],
          outcome: 'ok',
          configId: config.id,
          configVersion: config.version,
        });

        outputService.success(t('commands.config.field.unset.success', { pointer }));
      } catch (error) {
        handleError(error);
      }
    });

  field
    .command('rotate <pointer>')
    .description(t('commands.config.field.rotate.description'))
    .requiredOption('--new <value>', t('commands.config.field.rotate.optionNew'))
    .action(async (pointer: string, options: { new: string }) => {
      try {
        const config = await configService.getCurrent();
        if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));

        if (!isatty(process.stdin.fd)) {
          throw new ValidationError(t('errors.agent.rotateRequiresTty'));
        }

        const meta = metaForPointer(pointer);
        if (!meta || meta.kind === 'public') {
          throw new ValidationError(t('errors.agent.rotateNotSensitive', { pointer }));
        }

        const newValue = parseValue(options.new);
        const previousValue = getByPointer(config, pointer);

        evaluateMutations(
          [{ pointer, previousValue, newValue }] as MutationEntry[],
          {
            previousConfig: config,
            rotateAcknowledged: new Set([pointer]),
          }
        );

        const configName = configService.getCurrentName();
        await configFileStorage.update(configName, (cfg) => applyMutation(cfg, pointer, newValue) as typeof cfg);

        emit({
          command: 'config field rotate',
          paths: [pointer],
          outcome: 'rotate_no_knowledge',
          configId: config.id,
          configVersion: config.version,
        });

        outputService.success(t('commands.config.field.rotate.success', { pointer }));
      } catch (error) {
        handleError(error);
      }
    });

  field
    .command('list')
    .description(t('commands.config.field.list.description'))
    .option('--sensitive', t('commands.config.field.list.optionSensitive'))
    .option('--output <format>', t('commands.config.field.list.optionOutput'), 'table')
    .action((options: { sensitive?: boolean; output?: string }) => {
      try {
        const templates = listSensitivityTemplates();
        const rows = templates
          .map((pointer) => ({ pointer, ...SENSITIVITY_REGISTRY.get(pointer)! }))
          .filter((row) => !options.sensitive || row.kind !== 'public')
          .sort((a, b) => (a.pointer < b.pointer ? -1 : 1));
        outputService.print(rows, (options.output ?? 'table') as 'json' | 'table');
      } catch (error) {
        handleError(error);
      }
    });
}

/** Parse a CLI argument as JSON if it looks like JSON; otherwise treat as string. */
function parseValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (
    trimmed === 'null' ||
    trimmed === 'true' ||
    trimmed === 'false' ||
    /^-?\d+(\.\d+)?$/.test(trimmed) ||
    trimmed.startsWith('{') ||
    trimmed.startsWith('[') ||
    trimmed.startsWith('"')
  ) {
    try {
      return JSON.parse(trimmed);
    } catch {
      // fallthrough to string
    }
  }
  return raw;
}

// `redactClone` import is intentional for the eventual `config show --reveal=false` rework.
void redactClone;
