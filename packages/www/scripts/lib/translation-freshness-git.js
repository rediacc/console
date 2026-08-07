/**
 * Git plumbing for the translation-freshness gate.
 *
 * Split out of validate-translation-freshness.js: which files changed, and what
 * a file looked like at a commit, are questions about the repository rather than
 * about translation staleness, and they are the whole of this module.
 */
import { execSync } from 'node:child_process';

function getEnvChangedFiles() {
  const raw = process.env.TRANSLATION_FRESHNESS_CHANGED_FILES;
  if (!raw) {
    return null;
  }

  return raw
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function git(args, cwd) {
  return execSync(`git ${args.join(' ')}`, {
    cwd,
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  })
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function tryFetchBaseRef(repoRoot, baseRef) {
  if (!baseRef) {
    return;
  }

  try {
    execSync(
      `git fetch --no-tags --depth=50 origin +refs/heads/${baseRef}:refs/remotes/origin/${baseRef}`,
      {
        cwd: repoRoot,
        stdio: ['ignore', 'ignore', 'ignore'],
      }
    );
  } catch {
    // Best effort only. Local/dev environments may not have network access.
  }
}

/** Branch diffed against when neither the argument nor the environment names one. */
const DEFAULT_BASE_REF = 'main';

/**
 * First argument that is neither absent nor empty.
 *
 * @param {...(string | undefined)} values
 * @returns {string}
 */
function firstNonEmpty(...values) {
  for (const value of values) {
    if (value !== undefined && value !== '') return value;
  }
  return '';
}

export function detectChangedFiles(repoRoot, baseRefArg) {
  const fromEnv = getEnvChangedFiles();
  if (fromEnv) {
    return fromEnv;
  }

  // NOT `??`: on a push event GitHub sets GITHUB_BASE_REF to the EMPTY STRING
  // rather than leaving it unset, and an empty base ref makes every git rev-parse
  // below fail. Empty has to fall through to the default exactly like absent.
  const baseRef = firstNonEmpty(baseRefArg, process.env.GITHUB_BASE_REF, DEFAULT_BASE_REF);
  tryFetchBaseRef(repoRoot, baseRef);
  const candidates = [`origin/${baseRef}`, baseRef];

  // Untracked files are always included so that new translation files
  // (not yet staged/committed) are recognized as "changed in this PR".
  let untracked = [];
  try {
    untracked = git(['ls-files', '--others', '--exclude-standard', '--full-name'], repoRoot);
  } catch {
    // best effort
  }

  for (const candidate of candidates) {
    try {
      git(['rev-parse', '--verify', candidate], repoRoot);
      const mergeBase = git(['merge-base', 'HEAD', candidate], repoRoot)[0];
      const committed = git(['diff', '--name-only', `${mergeBase}...HEAD`], repoRoot);
      const staged = git(['diff', '--name-only', '--cached'], repoRoot);
      const unstaged = git(['diff', '--name-only'], repoRoot);
      return Array.from(new Set([...committed, ...staged, ...unstaged, ...untracked]));
    } catch {
      // try next strategy
    }
  }

  try {
    const committed = git(['diff', '--name-only', 'HEAD^...HEAD'], repoRoot);
    const staged = git(['diff', '--name-only', '--cached'], repoRoot);
    const unstaged = git(['diff', '--name-only'], repoRoot);
    return Array.from(new Set([...committed, ...staged, ...unstaged, ...untracked]));
  } catch {
    // fallback below
  }

  try {
    const staged = git(['diff', '--name-only', '--cached'], repoRoot);
    const unstaged = git(['diff', '--name-only'], repoRoot);
    return Array.from(new Set([...staged, ...unstaged, ...untracked]));
  } catch {
    return untracked;
  }
}

// ─── Git-based diff helpers ─────────────────────────────────────────

/**
 * Get file content at a specific git commit.
 */
export function getFileAtCommit(repoRoot, commit, filePath) {
  try {
    return execSync(`git show ${commit}:${filePath}`, {
      cwd: repoRoot,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    // Try deepening clone
    try {
      execSync('git fetch --deepen=100', { cwd: repoRoot, stdio: 'ignore' });
      return execSync(`git show ${commit}:${filePath}`, {
        cwd: repoRoot,
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      });
    } catch {
      return null;
    }
  }
}

/**
 * Get the latest commit that touched a file.
 */
export function getLatestCommitForFile(repoRoot, filePath) {
  try {
    return execSync(`git log -1 --format=%H -- ${filePath}`, {
      cwd: repoRoot,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return null;
  }
}
