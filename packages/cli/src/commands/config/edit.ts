/**
 * `rdc config edit` — open the active config in $EDITOR for hand-edit.
 *
 * Flow:
 *   1. Refuse for AI agents unless REDIACC_ALLOW_CONFIG_EDIT scope grants access.
 *   2. Render the config as redacted JSONC (or full JSONC with --reveal + audit).
 *   3. Spawn $EDITOR; wait for the user to close it.
 *   4. Re-parse the saved file; reject any modified `<redacted:…>` stub
 *      whose new value is still a stub (round-trip: untouched stubs map back
 *      to current values).
 *   5. Validate via the v2 Zod schema; on failure, reopen with an error banner.
 *      Abort after 3 consecutive failures and preserve the user's draft as `.orig`.
 *   6. Apply via `configFileStorage.update` (atomic temp+rename + .bak).
 *
 * Subcommand: `rdc config edit --dump [--redacted] [--apply <file>]`
 *   --dump            print the current config as JSONC to stdout
 *   --apply <file>    read an edited JSONC from a file and apply it
 *
 * Audit:
 *   edit_open / edit_apply / edit_abort / reveal_granted are all logged.
 */

import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  statSync,
  existsSync,
  copyFileSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { isatty } from 'node:tty';
import type { Command } from 'commander';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { configService } from '../../services/config-resources.js';
import { auditLog } from '../../services/audit-log.js';
import { t } from '../../i18n/index.js';
import { configEditOverrideScope, isAgentEnvironment } from '../../utils/agent-guard.js';
import { openEditor, EditorError } from '../../utils/editor-launcher.js';
import { outputService } from '../../services/output.js';
import { redactClone, shortFingerprint, walkSensitive, getByPointer } from '../../schema/walker.js';
import {
  parseConfig,
  RdcConfigSchema,
  stringifyConfig,
  type RdcConfig,
} from '../../schema/schemas.js';
import { handleError, ValidationError } from '../../utils/errors.js';

const REDACT_PATTERN = /^<redacted:[^>]+>:[0-9a-f]{8}$/;
const MAX_RETRIES = 3;

function configDir(): string {
  const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
  return `${xdg}/rediacc`;
}

function refuseAgentEdit(): never {
  const key = process.env.REDIACC_ALLOW_CONFIG_EDIT
    ? 'errors.agent.configEditAncestry'
    : 'errors.agent.configEdit';
  throw new ValidationError(t(key));
}

interface RenderOptions {
  reveal: boolean;
}

/**
 * Render an RdcConfig as JSONC suitable for $EDITOR. Untouched stubs round-trip
 * back to current values via SHA-256 short-fingerprint comparison.
 */
function renderJsonc(config: RdcConfig, options: RenderOptions): string {
  const view = options.reveal ? config : redactClone(config);
  const banner = [
    `// ${t('commands.config.edit.bannerTitle', { name: configService.getCurrentName(), version: config.version })}`,
    `// ${t('commands.config.edit.bannerStrip')}`,
    options.reveal
      ? `// ${t('commands.config.edit.bannerReveal')}`
      : `// ${t('commands.config.edit.bannerRedacted')}`,
    `// ${t('commands.config.edit.bannerRotateLine1')}`,
    `// ${t('commands.config.edit.bannerRotateLine2')}`,
    '',
  ].join('\n');
  return `${banner + stringifyConfig(view)}\n`;
}

/**
 * Prompt the user to confirm a list of sensitive-field rotations.
 * Returns true only when the user types 'rotate' (case-insensitive).
 */
async function promptRotationConfirmation(paths: string[]): Promise<boolean> {
  const lines = [
    '',
    t('commands.config.edit.rotatePromptHeader', { count: paths.length }),
    ...paths.map((p) => t('commands.config.edit.rotatePromptBullet', { pointer: p })),
    '',
    t('commands.config.edit.rotatePromptFooter'),
  ];
  process.stdout.write(lines.join('\n'));
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question('', (answer) => {
      rl.close();
      resolve(answer.trim().toLowerCase() === 'rotate');
    });
  });
}

/**
 * Strip JSONC comment lines (lines starting with `//` after optional whitespace).
 * Block comments and inline `//` are NOT supported — the renderer only emits
 * line comments before the JSON body, so the stripper handles only that form.
 */
function stripComments(jsonc: string): string {
  return jsonc
    .split('\n')
    .filter((line) => !/^\s*\/\//.test(line))
    .join('\n');
}

/**
 * Detect modified `<redacted:...>` stubs by comparing each sensitive path's
 * value in the edited config against the current config's stub.
 *
 * Rules:
 *   - Unchanged stub  (stub matches current digest)  → substitute real value back.
 *   - Stub replaced with a DIFFERENT stub             → hard failure (meaningless edit).
 *   - Stub replaced with real plaintext               → rotation intent.
 *     - If knowledge[pointer] supplied (via --current-secrets): silent accept.
 *     - Otherwise: surface on `rotations` so the caller can prompt or reject.
 *
 * Returning `rotations` (instead of immediately failing) lets interactive mode
 * show a single confirmation prompt for all rotations; non-interactive `--apply`
 * keeps strict behavior by converting `rotations` to `failures` at the call site.
 */
type StubOutcome =
  | { kind: 'untouched'; currentValue: unknown }
  | { kind: 'bad-stub' }
  | { kind: 'rotation' }
  | { kind: 'public' };

function classifyStub(
  pointer: string,
  editedValue: unknown,
  currentConfig: RdcConfig,
  meta: { kind: string; redactAs?: string },
  knowledge: Record<string, unknown> | undefined
): StubOutcome {
  if (meta.kind === 'public') return { kind: 'public' };

  const currentValue = getByPointer(currentConfig, pointer);
  const currentStub =
    currentValue === null || currentValue === undefined
      ? null
      : `${meta.redactAs ?? `<redacted:${meta.kind}>`}:${shortFingerprint(currentValue)}`;

  if (typeof editedValue === 'string' && currentStub && editedValue === currentStub) {
    return { kind: 'untouched', currentValue };
  }

  if (typeof editedValue === 'string' && REDACT_PATTERN.test(editedValue)) {
    return { kind: 'bad-stub' };
  }

  if (currentValue !== undefined && knowledge?.[pointer] === undefined) {
    return { kind: 'rotation' };
  }

  return { kind: 'untouched', currentValue };
}

function reconcileStubs(
  edited: unknown,
  currentConfig: RdcConfig,
  knowledge: Record<string, unknown> | undefined
): { result: unknown; failures: string[]; rotations: string[] } {
  const failures: string[] = [];
  const rotations: string[] = [];
  const view = JSON.parse(JSON.stringify(edited));

  for (const { pointer, value: editedValue, meta } of walkSensitive(view as RdcConfig)) {
    const outcome = classifyStub(pointer, editedValue, currentConfig, meta, knowledge);
    if (outcome.kind === 'public') continue;
    if (outcome.kind === 'untouched') {
      assignAtPointer(view, pointer, outcome.currentValue);
    } else if (outcome.kind === 'bad-stub') {
      failures.push(
        `${pointer}: edited value still looks like a redaction stub but does not match the current digest`
      );
    } else {
      rotations.push(pointer);
    }
  }

  return { result: view, failures, rotations };
}

function assignAtPointer(root: unknown, pointer: string, value: unknown): void {
  if (pointer === '') return;
  const segments = pointer
    .split('/')
    .slice(1)
    .map((s) => s.replaceAll('~1', '/').replaceAll('~0', '~'));
  let cursor: Record<string, unknown> | undefined = root as Record<string, unknown>;
  for (let i = 0; i < segments.length - 1; i++) {
    cursor = cursor[segments[i]] as Record<string, unknown> | undefined;
    if (!cursor) return;
  }
  cursor[segments[segments.length - 1]] = value;
}

function loadKnowledgeFile(path: string): Record<string, unknown> {
  const text = readFileSync(path, 'utf8');
  const raw: unknown = JSON.parse(text);
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new ValidationError(`--current-secrets must be a JSON object: ${path}`);
  }
  return raw as Record<string, unknown>;
}

async function applyEdit(
  parsed: RdcConfig,
  reconciled: unknown,
  configName: string,
  configIdForAudit: string,
  configVersionForAudit: number
): Promise<void> {
  // Replace the entire config with the reconciled v2-validated value.
  const validated = parseConfig(RdcConfigSchema, reconciled, 'rdc config edit');
  await configFileStorage.update(configName, () => validated);
  auditLog(configDir(), {
    command: 'config edit',
    paths: [],
    outcome: 'edit_apply',
    configId: configIdForAudit,
    configVersion: configVersionForAudit,
  });
  void parsed;
}

/** Handle `--apply <file>` mode: parse, reconcile, and apply without interaction. */
async function handleApplyMode(
  applyPath: string,
  config: RdcConfig,
  configName: string,
  knowledge: Record<string, unknown> | undefined
): Promise<void> {
  const text = readFileSync(applyPath, 'utf8');
  const stripped = stripComments(text);
  let edited: unknown;
  try {
    edited = JSON.parse(stripped);
  } catch (err) {
    throw new ValidationError(`Invalid JSON in ${applyPath}: ${(err as Error).message}`);
  }
  const { result, failures, rotations } = reconcileStubs(edited, config, knowledge);
  const allFailures = [
    ...failures,
    ...rotations.map(
      (p) =>
        `${p}: sensitive field changed without --current; supply --current-secrets <file> mapping pointer→old-value`
    ),
  ];
  if (allFailures.length > 0) {
    throw new ValidationError(
      `Reconciliation failed:\n${allFailures.map((f) => `  ${f}`).join('\n')}`
    );
  }
  await applyEdit(config, result, configName, config.id, config.version);
  outputService.success(t('commands.config.edit.applied', { path: applyPath }));
}

/** Write error banner + content to the tmp file and return a failed-iteration result. */
function writeErrorToTmp(
  tmpFile: string,
  banner: string,
  errorBlock: string,
  content: string,
  nextAttempt: number
): { done: boolean; failed: boolean; nextAttempt: number } {
  writeFileSync(tmpFile, `${banner}${errorBlock}${content}`, { mode: 0o600 });
  return { done: false, failed: true, nextAttempt };
}

/**
 * Confirm pending rotations with the user. Returns null if the iteration
 * should continue normally, or a done/failed result if it should stop.
 */
async function confirmRotations(
  rotations: string[],
  edited: unknown,
  tmpFile: string,
  config: RdcConfig,
  attempt: number,
  tmp: string
): Promise<{ done: boolean; failed: boolean; nextAttempt: number } | null> {
  if (!isatty(process.stdin.fd) || !isatty(process.stdout.fd)) {
    const errs = rotations.map(
      (p) => `${p}: rotation confirmation requires an interactive TTY (or use --current-secrets)`
    );
    const banner = `// ─── ${rotations.length} UNCONFIRMED ROTATION(S) ───\n`;
    return writeErrorToTmp(
      tmpFile,
      banner,
      `${errs.map((f) => `// ${f}`).join('\n')}\n`,
      `${JSON.stringify(edited, null, 2)}\n`,
      attempt + 1
    );
  }
  const confirmed = await promptRotationConfirmation(rotations);
  if (!confirmed) {
    outputService.info(t('commands.config.edit.rotateDeclined'));
    auditLog(configDir(), {
      command: 'config edit',
      paths: rotations,
      outcome: 'edit_abort',
      configId: config.id,
      configVersion: config.version,
      reason: 'user declined rotation confirmation',
    });
    rmSync(tmp, { recursive: true, force: true });
    return { done: true, failed: false, nextAttempt: attempt };
  }
  auditLog(configDir(), {
    command: 'config edit',
    paths: rotations,
    outcome: 'rotate_no_knowledge',
    configId: config.id,
    configVersion: config.version,
    reason: 'interactive editor confirmation',
  });
  return null;
}

/** Parse JSONC from the tmp file; returns the parsed value or an error result. */
function parseTmpFile(
  tmpFile: string,
  attempt: number
): { edited: unknown } | { done: boolean; failed: boolean; nextAttempt: number } {
  const text = readFileSync(tmpFile, 'utf8');
  const stripped = stripComments(text);
  try {
    return { edited: JSON.parse(stripped) };
  } catch (err) {
    const errs = [`JSON parse error: ${(err as Error).message}`];
    const banner = `// ─── ${errs.length} ERROR(S) on attempt ${attempt + 1}/${MAX_RETRIES} ───\n`;
    return writeErrorToTmp(
      tmpFile,
      banner,
      `${errs.map((f) => `// ${f}`).join('\n')}\n`,
      stripped,
      attempt + 1
    );
  }
}

/** Reconcile, confirm rotations, and apply. Returns iteration result. */
async function reconcileAndApply(
  edited: unknown,
  config: RdcConfig,
  configName: string,
  knowledge: Record<string, unknown> | undefined,
  tmpFile: string,
  attempt: number,
  tmp: string
): Promise<{ done: boolean; failed: boolean; nextAttempt: number }> {
  const { result, failures, rotations } = reconcileStubs(edited, config, knowledge);
  if (failures.length > 0) {
    const banner = `// ─── ${failures.length} RECONCILIATION ERROR(S) on attempt ${attempt + 1}/${MAX_RETRIES} ───\n`;
    const errorBlock = `${failures.map((f) => `// ${f}`).join('\n')}\n`;
    return writeErrorToTmp(
      tmpFile,
      banner,
      errorBlock,
      `${JSON.stringify(edited, null, 2)}\n`,
      attempt + 1
    );
  }
  if (rotations.length > 0) {
    const rotResult = await confirmRotations(rotations, edited, tmpFile, config, attempt, tmp);
    if (rotResult) return rotResult;
  }
  try {
    await applyEdit(config, result, configName, config.id, config.version);
    outputService.success(t('commands.config.edit.saved', { name: configName }));
    rmSync(tmp, { recursive: true, force: true });
    return { done: true, failed: false, nextAttempt: attempt };
  } catch (err) {
    const banner = `// ─── VALIDATION ERROR on attempt ${attempt + 1}/${MAX_RETRIES} ───\n`;
    const errorBlock = `// ${(err as Error).message.replaceAll('\n', '\n// ')}\n`;
    return writeErrorToTmp(
      tmpFile,
      banner,
      errorBlock,
      `${JSON.stringify(edited, null, 2)}\n`,
      attempt + 1
    );
  }
}

/** Handle one retry iteration of the interactive editor loop. */
async function runEditorIteration(
  tmpFile: string,
  config: RdcConfig,
  configName: string,
  editorCmd: string | undefined,
  knowledge: Record<string, unknown> | undefined,
  beforeMtimeMs: number,
  attempt: number,
  tmp: string
): Promise<{ done: boolean; failed: boolean; nextAttempt: number }> {
  try {
    await openEditor(tmpFile, editorCmd);
  } catch (err) {
    if (err instanceof EditorError) throw new ValidationError(err.message);
    throw err;
  }

  const afterStat = statSync(tmpFile);
  if (afterStat.mtimeMs === beforeMtimeMs && attempt === 0) {
    outputService.info(t('commands.config.edit.noChanges'));
    auditLog(configDir(), {
      command: 'config edit',
      paths: [],
      outcome: 'edit_abort',
      configId: config.id,
      configVersion: config.version,
      reason: 'no changes',
    });
    rmSync(tmp, { recursive: true, force: true });
    return { done: true, failed: false, nextAttempt: attempt };
  }

  const parseResult = parseTmpFile(tmpFile, attempt);
  if (!('edited' in parseResult)) return parseResult;

  return reconcileAndApply(
    parseResult.edited,
    config,
    configName,
    knowledge,
    tmpFile,
    attempt,
    tmp
  );
}

/** Handle interactive editor flow with retry loop. */
async function handleInteractiveMode(
  config: RdcConfig,
  configName: string,
  reveal: boolean,
  editorCmd: string | undefined,
  knowledge: Record<string, unknown> | undefined
): Promise<void> {
  const tmp = mkdtempSync(join(tmpdir(), 'rdc-edit-'));
  const tmpFile = join(tmp, `${configName}.jsonc`);
  writeFileSync(tmpFile, renderJsonc(config, { reveal }), { mode: 0o600 });
  const beforeMtimeMs = statSync(tmpFile).mtimeMs;

  auditLog(configDir(), {
    command: 'config edit',
    paths: [],
    outcome: 'edit_open',
    configId: config.id,
    configVersion: config.version,
  });

  let attempt = 0;
  while (attempt < MAX_RETRIES) {
    const { done, nextAttempt } = await runEditorIteration(
      tmpFile,
      config,
      configName,
      editorCmd,
      knowledge,
      beforeMtimeMs,
      attempt,
      tmp
    );
    attempt = nextAttempt;
    if (done) return;
  }

  // Out of retries — preserve draft and abort.
  const orig = `${configDir()}/${configName}.edit-${Date.now()}.orig`;
  if (existsSync(tmpFile)) copyFileSync(tmpFile, orig);
  rmSync(tmp, { recursive: true, force: true });
  auditLog(configDir(), {
    command: 'config edit',
    paths: [],
    outcome: 'edit_abort',
    configId: config.id,
    configVersion: config.version,
    reason: `${MAX_RETRIES} consecutive failures; draft saved to ${orig}`,
  });
  throw new ValidationError(
    t('commands.config.edit.abortAfterRetries', { count: MAX_RETRIES, path: orig })
  );
}

/** Check agent gate and reveal gate; throws if access should be refused. */
function checkEditGates(
  config: RdcConfig,
  agent: boolean,
  needsAgentGate: boolean,
  reveal: boolean
): void {
  if (agent && needsAgentGate) {
    const scope = configEditOverrideScope();
    if (!scope || scope !== '*') {
      auditLog(configDir(), {
        command: 'config edit',
        paths: [],
        outcome: 'refused',
        configId: config.id,
        configVersion: config.version,
        reason: 'agent without REDIACC_ALLOW_CONFIG_EDIT=*',
      });
      refuseAgentEdit();
    }
  }
  if (reveal) {
    if (!isatty(process.stdout.fd))
      throw new ValidationError(t('errors.agent.showRevealRequiresTty'));
    auditLog(configDir(), {
      command: 'config edit --reveal',
      paths: [],
      outcome: 'reveal_granted',
      configId: config.id,
      configVersion: config.version,
    });
  }
}

export function registerEditCommands(parent: Command, _program: Command): void {
  parent
    .command('edit')
    .description(t('commands.config.edit.description'))
    .option('--reveal', t('commands.config.edit.optionReveal'))
    .option('--dump', t('commands.config.edit.optionDump'))
    .option('--apply <file>', t('commands.config.edit.optionApply'))
    .option('--current-secrets <file>', t('commands.config.edit.optionCurrentSecrets'))
    .option('--editor <cmd>', t('commands.config.edit.optionEditor'))
    .action(
      async (options: {
        reveal?: boolean;
        dump?: boolean;
        apply?: string;
        currentSecrets?: string;
        editor?: string;
      }) => {
        try {
          const config = await configService.getCurrent();
          if (!config) throw new ValidationError(t('errors.config.noActiveConfig'));
          const configName = configService.getCurrentName();

          const agent = isAgentEnvironment();
          const reveal = options.reveal === true;

          // Agent gate: block interactive editor + --apply + --reveal.
          // --dump without --reveal is read-only redacted output — safe for agents.
          const interactive = !options.dump && !options.apply;
          const needsAgentGate = interactive || Boolean(options.apply) || reveal;
          checkEditGates(config, agent, needsAgentGate, reveal);

          const knowledge: Record<string, unknown> | undefined = options.currentSecrets
            ? loadKnowledgeFile(options.currentSecrets)
            : undefined;

          if (options.dump) {
            process.stdout.write(renderJsonc(config, { reveal }));
            return;
          }

          if (options.apply) {
            await handleApplyMode(options.apply, config, configName, knowledge);
            return;
          }

          await handleInteractiveMode(config, configName, reveal, options.editor, knowledge);
        } catch (error) {
          handleError(error);
        }
      }
    );
}
