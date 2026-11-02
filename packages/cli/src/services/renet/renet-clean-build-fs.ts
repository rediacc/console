import { createHash } from 'node:crypto';
import * as fsSync from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

/** Marker written last into a finished clean build directory; first line the commit, second the {@link accountKeyId} of the licence public key baked in. */
export const CLEAN_BUILD_MARKER = '.complete';

/** Where `build.sh dev` writes its binaries, relative to the renet checkout: one licensed build, always in `bin/`. */
export const RENET_BUILD_DIR = 'bin';

/** The linker symbol build.sh bakes the licence public key into, as `go version -m` prints it. */
const BAKED_KEY_RE = /\/pkg\/license\/keys\.ProductionPublicKey=([A-Za-z0-9+/=]*)/g;

/** The licence public key `go version -m` output says the binary bakes; the last one wins, as with the linker. Empty when there is none. */
export function bakedAccountKey(goVersionM: string): string {
  const found = [...goVersionM.matchAll(BAKED_KEY_RE)];
  return found.length > 0 ? found[found.length - 1][1] : '';
}

/** A short digest of a licence public key, for the cache marker: the key itself is public, but there is no reason to copy it around. */
export function accountKeyId(key: string): string {
  return createHash('sha256').update(key).digest('hex').slice(0, 16);
}

/** The cached build directory name of a commit. */
export function cleanBuildDirName(commit: string): string {
  return commit;
}
const LINUX_ARCHES = ['amd64', 'arm64'] as const;

/** Where clean builds live: the console's gitignored .ci/cache, or the temp dir for a standalone renet. */
export function cleanBuildRoot(
  top: string,
  deps: { git: (args: string[], cwd: string) => string }
): string {
  let superproject = '';
  try {
    superproject = deps.git(['rev-parse', '--show-superproject-working-tree'], top);
  } catch {
    // Not a submodule.
  }
  return superproject
    ? path.join(superproject, '.ci', 'cache', 'renet-head')
    : path.join(os.tmpdir(), 'rediacc-renet-head');
}

export function cleanBuildFiles(ext: string): string[] {
  return [`renet${ext}`, ...LINUX_ARCHES.map((arch) => `renet-linux-${arch}`)];
}

/** The marker body of a finished build: the commit and the {@link accountKeyId} of the key it bakes. */
export function cleanBuildMarker(commit: string, keyId: string): string {
  return `${commit}\n${keyId}\n`;
}

/**
 * True when `dir` holds a finished build of `commit` baking the key `keyId` names. A build baked with another key (a rotation, or a cache written before the one-keypair store) is rebuilt, or every upload at that commit would ship a binary that cannot verify licences.
 */
export function isCompleteCleanBuild(
  dir: string,
  commit: string,
  ext: string,
  keyId: string
): boolean {
  try {
    const [markedCommit, markedKey] = fsSync
      .readFileSync(path.join(dir, CLEAN_BUILD_MARKER), 'utf-8')
      .trim()
      .split('\n');
    if (markedCommit !== commit || markedKey !== keyId) return false;
    return cleanBuildFiles(ext).every((name) => fsSync.existsSync(path.join(dir, name)));
  } catch {
    return false;
  }
}

/** The gitignored staged assets (311 MB): copy-on-write where the filesystem supports it. */
export function copyEmbeddedAssets(top: string, work: string): void {
  const src = path.join(top, 'pkg', 'embed', 'assets');
  if (!fsSync.existsSync(src)) return;
  fsSync.cpSync(src, path.join(work, 'pkg', 'embed', 'assets'), {
    recursive: true,
    force: true,
    mode: fsSync.constants.COPYFILE_FICLONE,
  });
}

/**
 * A fresh clone gives the committed BPF objects and their C source the same mtime, so build.sh's
 * `-nt` check would regenerate the objects with the local clang and could change tracked files.
 * Dating the source back keeps the committed objects, which is what HEAD means.
 */
export function pinCommittedEbpfObjects(work: string): void {
  const dir = path.join(work, 'pkg', 'ebpf');
  if (!fsSync.existsSync(dir)) return;
  const past = new Date('2000-01-01T00:00:00Z');
  for (const name of fsSync.readdirSync(dir)) {
    if (name.endsWith('.c') || name.endsWith('.h')) {
      fsSync.utimesSync(path.join(dir, name), past, past);
    }
  }
}

/**
 * build.sh reads the licence public key from `<renet>/../account/.cache/public-keys.env`, which
 * does not exist beside the clone, so the working tree's key is handed over in the environment,
 * exactly as the working-tree build would have read it. A public key; never printed.
 */
export function cleanBuildEnv(top: string): NodeJS.ProcessEnv {
  const env = { ...process.env };
  if (env.ACCOUNT_ED25519_PUBLIC_KEY) return env;
  try {
    const cache = fsSync.readFileSync(
      path.join(top, '..', 'account', '.cache', 'public-keys.env'),
      'utf-8'
    );
    const line = cache.split('\n').find((l) => l.startsWith('ACCOUNT_ED25519_PUBLIC_KEY='));
    const key = line?.slice('ACCOUNT_ED25519_PUBLIC_KEY='.length).trim();
    if (key) env.ACCOUNT_ED25519_PUBLIC_KEY = key;
  } catch {
    // No cache: the caller refuses before build.sh, which fails closed without a key.
  }
  return env;
}

/** Removes every build but `keep`'s, including the per-flavor `<commit>-<flavor>` directories older CLIs wrote. */
export function pruneOtherCleanBuilds(root: string, keep: string): void {
  for (const name of fsSync.readdirSync(root)) {
    if (name !== keep && /^[0-9a-f]{40}([0-9a-f]{24})?(-[a-z]+)?$/.test(name)) {
      fsSync.rmSync(path.join(root, name), { recursive: true, force: true });
    }
  }
}
