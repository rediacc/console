/**
 * The clean-build path of a renet upload: the dirty-tree guard, the choice of binary to upload, and
 * the build of the committed HEAD in a scratch clone. Split from renet-execution.ts.
 */

import { execFileSync, spawn } from 'node:child_process';
import * as fsSync from 'node:fs';
import * as path from 'node:path';
import type { MachineConfig } from '../../types/index.js';
import { outputService } from '../core/output.js';
import {
  accountKeyId,
  bakedAccountKey,
  CLEAN_BUILD_MARKER,
  cleanBuildDirName,
  cleanBuildEnv,
  cleanBuildFiles,
  cleanBuildMarker,
  cleanBuildRoot,
  copyEmbeddedAssets,
  isCompleteCleanBuild,
  pinCommittedEbpfObjects,
  pruneOtherCleanBuilds,
  RENET_BUILD_DIR,
} from './renet-clean-build-fs.js';

/** Maximum dirty paths named in the refusal. */
const DIRTY_PATHS_SHOWN = 10;

/**
 * Refuse to upload a renet binary built from a dirty source tree, unless
 * REDIACC_ALLOW_DIRTY_RENET=1. A binary outside a git work tree (a release
 * binary on PATH) is allowed. Untracked files count: Go compiles untracked .go
 * files, and `bin/` is gitignored so the binary itself never shows up.
 *
 * A tree already dirty when provisioning starts never reaches this guard:
 * {@link selectRenetUploadBinary} swaps in a build of the committed HEAD. The guard
 * catches a tree that turned dirty after that choice, and binds callers that pass
 * the working-tree binary directly.
 */
export function assertRenetSourceClean(localBinaryPath: string, machine: MachineConfig): void {
  if (process.env.REDIACC_ALLOW_DIRTY_RENET === '1') return;
  const state = renetSourceState(localBinaryPath);
  if (state === null || state.dirty.length === 0) return;
  const { top, dirty } = state;
  const shown = dirty.slice(0, DIRTY_PATHS_SHOWN).map((line) => `  ${line}`);
  if (dirty.length > DIRTY_PATHS_SHOWN) {
    shown.push(`  ... and ${dirty.length - DIRTY_PATHS_SHOWN} more`);
  }
  throw new Error(
    `Refusing to upload renet to ${machine.ip}: the binary was built from a dirty tree at ${top}.\n` +
      `${shown.join('\n')}\n` +
      'Commit the renet change first, or set REDIACC_ALLOW_DIRTY_RENET=1 to upload it anyway.'
  );
}

/**
 * The git work tree a local renet binary sits in and its `status --porcelain` lines, or null for
 * a binary outside any git work tree (a release binary on PATH).
 */
export function renetSourceState(localBinaryPath: string): { top: string; dirty: string[] } | null {
  let top: string;
  try {
    top = gitOut(['rev-parse', '--show-toplevel'], path.dirname(localBinaryPath));
  } catch {
    return null;
  }
  if (!top) return null;
  const porcelain = gitOut(['status', '--porcelain'], top);
  return { top, dirty: porcelain.split('\n').filter((line) => line.trim() !== '') };
}

export function gitOut(args: string[], cwd: string): string {
  return execFileSync('git', ['-C', cwd, ...args], {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'ignore'],
  }).trim();
}

/** The renet binary a provisioning call hands to the provisioner. */
export interface RenetUploadSelection {
  /** Host binary; the provisioner picks `renet-linux-<arch>` beside it for a foreign arch. */
  localBinaryPath: string;
  /** The committed renet HEAD this binary was built from instead of a dirty tree; null otherwise. */
  cleanCommit: string | null;
  /** Uncommitted paths left out of that build. */
  excludedPaths: number;
  /** Whether the dirty-tree upload guard applies (only to the working-tree binary). */
  guarded: boolean;
}

/** Process seams of the clean build; tests replace them, production uses the real tools. */
export interface RenetCleanBuildDeps {
  git: (args: string[], cwd: string) => string;
  /** Run renet's own `./build.sh dev` in `cwd`; build output goes to stderr. */
  build: (cwd: string, env: NodeJS.ProcessEnv) => Promise<void>;
  /** `go version -m <binary>` output. */
  goVersionM: (binary: string) => string;
}

const realCleanBuildDeps: RenetCleanBuildDeps = {
  git: gitOut,
  build: (cwd, env) =>
    new Promise((resolve, reject) => {
      // stdout is the CLI command's; build progress goes to stderr.
      // build.sh resolves against the child's cwd: a cwd-joined path would be resolved against cwd a second time when cwd is relative.
      const child = spawn('bash', ['build.sh', 'dev'], {
        cwd,
        env,
        stdio: ['ignore', 2, 2],
      });
      child.on('error', reject);
      child.on('close', (code) =>
        code === 0 ? resolve() : reject(new Error(`bash build.sh dev exited ${code} in ${cwd}`))
      );
    }),
  goVersionM: (binary) =>
    execFileSync('go', ['version', '-m', binary], {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }),
};

/**
 * Pick the renet binary to upload. A dirty renet working tree no longer blocks the upload: the
 * binary is built from the committed HEAD in a scratch clone and THAT is uploaded, so another
 * session's uncommitted edits in private/renet cannot stop a production `rdc repo up` (2026-10-23,
 * the hostinger observability stack). REDIACC_ALLOW_DIRTY_RENET=1 still uploads the working-tree
 * build as it is.
 */
export async function selectRenetUploadBinary(
  localBinaryPath: string,
  deps: RenetCleanBuildDeps = realCleanBuildDeps
): Promise<RenetUploadSelection> {
  const asIs: RenetUploadSelection = {
    localBinaryPath,
    cleanCommit: null,
    excludedPaths: 0,
    guarded: true,
  };
  if (process.env.REDIACC_ALLOW_DIRTY_RENET === '1') return asIs;
  const state = renetSourceState(localBinaryPath);
  if (state === null || state.dirty.length === 0) return asIs;
  const commit = deps.git(['rev-parse', 'HEAD'], state.top);
  outputService.info(
    `renet working tree ${state.top} has ${state.dirty.length} uncommitted path(s); using a build of committed HEAD ${commit.slice(0, 12)} (local edits not included; REDIACC_ALLOW_DIRTY_RENET=1 uploads the working-tree build)`
  );
  const built = await buildRenetAtCommit(state.top, commit, deps);
  return {
    localBinaryPath: built,
    cleanCommit: commit,
    excludedPaths: state.dirty.length,
    guarded: false,
  };
}

interface StageInput {
  work: string;
  stage: string;
  ext: string;
  key: string;
  commit: string;
}

/** Check the clone is untouched and each built binary bakes the key and the commit, then move them into `stage` with the marker. */
function stageVerifiedBuild(input: StageInput, deps: RenetCleanBuildDeps): void {
  const { work, stage, ext, key, commit } = input;
  const keyId = accountKeyId(key);
  const left = deps.git(['status', '--porcelain'], work);
  if (left) {
    throw new Error(
      `The clean renet build of ${commit.slice(0, 12)} changed tracked files in its clone, so its stamp would be modified:\n${left}`
    );
  }
  fsSync.mkdirSync(stage);
  for (const name of cleanBuildFiles(ext)) {
    const built = path.join(work, RENET_BUILD_DIR, name);
    const info = deps.goVersionM(built);
    if (bakedAccountKey(info) !== key) {
      throw new Error(
        `The clean renet build ${built} does not bake the account public key it was built with (key id ${keyId})`
      );
    }
    if (!info.includes(`vcs.revision=${commit}`) || !info.includes('vcs.modified=false')) {
      throw new Error(
        `The clean renet build ${built} does not carry vcs.revision=${commit} with vcs.modified=false`
      );
    }
    fsSync.renameSync(built, path.join(stage, name));
  }
  fsSync.writeFileSync(path.join(stage, CLEAN_BUILD_MARKER), cleanBuildMarker(commit, keyId));
}

/** Publish the staged directory as the cached build of `commit`. */
function publishStage(
  stage: string,
  finalDir: string,
  build: { commit: string; ext: string; keyId: string }
): void {
  const { commit, ext, keyId } = build;
  // A leftover directory (a cached build missing a binary, or one baked with another key) would make the rename fail with ENOTEMPTY on every run; a rename only ever publishes a whole directory, so what is there is stale.
  if (!isCompleteCleanBuild(finalDir, commit, ext, keyId)) {
    fsSync.rmSync(finalDir, { recursive: true, force: true });
  }
  try {
    fsSync.renameSync(stage, finalDir);
  } catch (err) {
    // A concurrent process finished the same commit first; its build is as good as ours.
    if (!isCompleteCleanBuild(finalDir, commit, ext, keyId)) throw err;
  }
}

/**
 * Build renet at `commit` with renet's own `./build.sh dev`, in a `git clone --shared` of `top`
 * (no worktree, nothing written to the source checkout), and return the host binary of the result.
 * There is one licensed build, in the clone's `bin/`, and it must bake the licence public key the
 * working tree supplies ({@link cleanBuildEnv}); without one this refuses before build.sh runs.
 * Cached per commit and key under {@link cleanBuildRoot}; other commits' builds are pruned.
 *
 * The clone has its own `.git` directory, so Go stamps `vcs.revision=<commit>`; the stamp and a
 * clean clone are verified before the build is accepted. The gitignored embedded assets are copied
 * from the working tree; build.sh's receipt check restages them if HEAD's lockfile differs.
 */
export async function buildRenetAtCommit(
  top: string,
  commit: string,
  deps: RenetCleanBuildDeps = realCleanBuildDeps
): Promise<string> {
  const root = cleanBuildRoot(top, deps);
  const ext = process.platform === 'win32' ? '.exe' : '';
  const finalDir = path.join(root, cleanBuildDirName(commit));
  const hostBinary = path.join(finalDir, `renet${ext}`);
  const buildEnv = cleanBuildEnv(top);
  const key = buildEnv.ACCOUNT_ED25519_PUBLIC_KEY ?? '';
  if (!key) {
    throw new Error(
      'renet needs ACCOUNT_ED25519_PUBLIC_KEY (the production account public key) and none was found in the environment or the public-key cache. Run ./run.sh setup, then retry.'
    );
  }
  const keyId = accountKeyId(key);
  if (isCompleteCleanBuild(finalDir, commit, ext, keyId)) return hostBinary;

  fsSync.mkdirSync(root, { recursive: true });
  const work = path.join(root, `work-${commit.slice(0, 12)}-${process.pid}`);
  const stage = path.join(root, `stage-${commit.slice(0, 12)}-${process.pid}`);
  fsSync.rmSync(work, { recursive: true, force: true });
  fsSync.rmSync(stage, { recursive: true, force: true });
  try {
    deps.git(['clone', '--quiet', '--shared', '--no-checkout', top, work], root);
    deps.git(['-c', 'advice.detachedHead=false', 'switch', '--quiet', '--detach', commit], work);
    copyEmbeddedAssets(top, work);
    pinCommittedEbpfObjects(work);

    outputService.info(`Building renet ${commit.slice(0, 12)} from a clean clone...`);
    await deps.build(work, buildEnv);

    stageVerifiedBuild({ work, stage, ext, key, commit }, deps);
    publishStage(stage, finalDir, { commit, ext, keyId });
    pruneOtherCleanBuilds(root, commit);
  } finally {
    fsSync.rmSync(work, { recursive: true, force: true });
    fsSync.rmSync(stage, { recursive: true, force: true });
  }
  return hostBinary;
}
