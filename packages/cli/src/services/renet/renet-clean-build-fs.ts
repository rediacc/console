import * as fsSync from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

/** Marker written last into a finished clean build directory; first line the commit, second `keyed` or `keyless`. */
export const CLEAN_BUILD_MARKER = '.complete';
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

/** The marker body of a finished build: the commit, and whether the licence public key was compiled in. */
export function cleanBuildMarker(commit: string, keyed: boolean): string {
  return `${commit}\n${keyed ? 'keyed' : 'keyless'}\n`;
}

/**
 * True when `dir` holds a finished build of `commit`. A keyless build (no licence public key at build time) is not reused once the key is available (`keyAvailable`), or every upload at that commit would ship a binary that cannot verify licences.
 */
export function isCompleteCleanBuild(
  dir: string,
  commit: string,
  ext: string,
  keyAvailable = false
): boolean {
  try {
    const [markedCommit, markedKey] = fsSync
      .readFileSync(path.join(dir, CLEAN_BUILD_MARKER), 'utf-8')
      .trim()
      .split('\n');
    if (markedCommit !== commit) return false;
    if (keyAvailable && markedKey !== 'keyed') return false;
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
    // No cache: build.sh builds keyless, as it would in the working tree.
  }
  return env;
}

export function pruneOtherCleanBuilds(root: string, keep: string): void {
  for (const name of fsSync.readdirSync(root)) {
    if (name !== keep && /^[0-9a-f]{40}([0-9a-f]{24})?$/.test(name)) {
      fsSync.rmSync(path.join(root, name), { recursive: true, force: true });
    }
  }
}
