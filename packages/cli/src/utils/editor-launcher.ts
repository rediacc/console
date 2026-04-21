/**
 * Cross-platform editor launcher for `rdc config edit`.
 *
 * Resolution order mirrors git's own precedence so the CLI honors whatever
 * the user has already configured for `git commit`:
 *   1. explicit `--editor <cmd>` flag
 *   2. `$GIT_EDITOR`
 *   3. `git config --get core.editor` (skipped if git is missing / not a repo)
 *   4. `$VISUAL`
 *   5. `$EDITOR`
 *   6. platform default (`notepad.exe` on Windows, `nano` elsewhere)
 *
 * Known editors get `--wait`-equivalents auto-injected so the CLI blocks until
 * the user closes the editor rather than returning immediately (which is the
 * default for `code`, `cursor`, `subl`, etc.).
 *
 * Headless invocations (e.g., `nvim --headless`) refuse — they would block
 * forever or return without the user editing anything.
 */

import { execFileSync, spawn } from 'node:child_process';
import { t } from '../i18n/index.js';

/** Known GUI editors that need a --wait flag to block. */
const KNOWN_WAIT_FLAGS: Record<string, string[]> = {
  code: ['--wait'],
  'code-insiders': ['--wait'],
  codium: ['--wait'],
  cursor: ['--wait'],
  windsurf: ['--wait'],
  subl: ['--wait'],
  sublime_text: ['--wait'],
  mate: ['-w'],
  atom: ['--wait'],
  'notepad.exe': ['/W'],
};

/** Platform default fallbacks (in priority order). */
function platformDefaults(): string[] {
  if (process.platform === 'win32') return ['notepad.exe'];
  return ['nano', 'vim'];
}

/**
 * Read `core.editor` from git config. Returns `null` if git is missing, the
 * key is unset, or any error occurs — the caller falls through to $VISUAL /
 * $EDITOR. Runs with a short timeout so a misconfigured git (slow ssh signing
 * helper, etc.) can't hang the CLI.
 */
function readGitCoreEditor(): string | null {
  try {
    const out = execFileSync('git', ['config', '--get', 'core.editor'], {
      encoding: 'utf8',
      timeout: 2_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    return out.length > 0 ? out : null;
  } catch {
    return null;
  }
}

export class EditorError extends Error {
  readonly code: 'not_found' | 'headless_refused' | 'nonzero_exit' | 'spawn_failed';
  constructor(code: EditorError['code'], message: string) {
    super(message);
    this.name = 'EditorError';
    this.code = code;
  }
}

export interface ResolvedEditor {
  command: string;
  args: string[];
}

/**
 * Pick an editor from the caller's preference, git config, the environment,
 * and fall back to platform defaults. Returns the base command and any
 * auto-injected flags (not including the file path — that's appended at
 * launch time).
 *
 * Rejects invocations that already specify `--headless` / similar blocking-
 * forever flags, since the CLI would hang.
 */
export function resolveEditor(explicit?: string): ResolvedEditor {
  const raw =
    explicit ??
    process.env.GIT_EDITOR ??
    readGitCoreEditor() ??
    process.env.VISUAL ??
    process.env.EDITOR ??
    platformDefaults()[0];
  if (!raw) {
    throw new EditorError('not_found', t('errors.editor.notFound'));
  }
  const parts = raw.split(/\s+/).filter(Boolean);
  const command = parts[0]!;
  const callerArgs = parts.slice(1);

  // Reject headless invocations.
  if (callerArgs.some((a) => /^--headless$|^--batch$/.test(a))) {
    throw new EditorError('headless_refused', t('errors.editor.headlessRefused', { command: raw }));
  }

  // Inject known --wait-equivalents unless already present.
  const base = command.split(/[\\/]/).pop() ?? command;
  const waitFlag = KNOWN_WAIT_FLAGS[base];
  const args = [...callerArgs];
  if (waitFlag) {
    const already = args.some((a) => waitFlag.includes(a));
    if (!already) args.push(...waitFlag);
  }

  return { command, args };
}

/**
 * Spawn the editor on the given file path, inherit stdio, and resolve when
 * the user exits the editor. Rejects with EditorError on non-zero exit.
 */
export async function openEditor(filePath: string, explicit?: string): Promise<void> {
  const { command, args } = resolveEditor(explicit);
  return new Promise((resolve, reject) => {
    const child = spawn(command, [...args, filePath], {
      stdio: 'inherit',
      shell: false,
    });
    child.on('error', (err) => {
      reject(
        new EditorError('spawn_failed', t('errors.editor.spawnFailed', { command, reason: err.message }))
      );
    });
    child.on('exit', (code) => {
      if (code === 0 || code === null) resolve();
      else
        reject(
          new EditorError('nonzero_exit', t('errors.editor.nonzeroExit', { command, code: String(code) }))
        );
    });
  });
}
