/**
 * Local-first media URLs for the videos this repo does NOT commit.
 *
 * Solution and tutorial videos live on Cloudflare R2 (media.rediacc.com) and their
 * bucket keys are tracked in `src/data/video-manifest.json`. `public/assets/videos/`
 * and `public/assets/tutorials/video/` are gitignored, so a fresh checkout has none of
 * them, while a developer who just ran the pipeline (or `sync-media-from-r2.sh`) has
 * some. The rule here serves both without a switch:
 *
 *   1. the file exists under `packages/www/public`  -> emit the local path
 *   2. otherwise                                     -> emit `${cdnBase}/${cdnKey}`
 *
 * This replaced an env-var gate (`PUBLIC_VIDEO_CDN_BASE_URL` set = CDN, unset = local
 * path). Unset was the local-dev default, and it emitted `/assets/...` paths that 404ed,
 * so every hero and tutorial player showed a blank poster and a "Format error".
 *
 * Everything here is Node-only and runs at build/render time: Astro (Vite SSR) and the
 * plain-tsx gate scripts both import the callers. Hence `process.env`, `import.meta.url`
 * and `node:fs`, never `process.cwd()`. The one `import.meta.env` read (the memo switch
 * below) is optional-chained, because under tsx and native Node it is undefined.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

/** `packages/www/public`, resolved from this file so it holds under Astro and under tsx. */
export const WWW_PUBLIC_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../public'
);

/**
 * The CDN base to fall back to. `PUBLIC_VIDEO_CDN_BASE_URL` still overrides it (CI and
 * staging set it; see .github/workflows/cd-deploy-worker.yml), otherwise the manifest's
 * own `baseUrl` applies, so a plain checkout points at media.rediacc.com with no setup.
 */
export function cdnBaseUrl(manifestBaseUrl: string): string {
  const base = process.env.PUBLIC_VIDEO_CDN_BASE_URL || manifestBaseUrl;
  return base.replace(/\/+$/, '');
}

/**
 * Existence memo for production builds ONLY. `astro build` resolves a few thousand
 * paths (21 solutions x 13 locales x 3 fields, plus 5 fields per tutorial embed across
 * ~234 pages), and the public tree does not change mid-build. In dev the check stays
 * live, so a file the pipeline just wrote is picked up on the next request without a
 * dev-server restart.
 *
 * The switch is Vite's own `import.meta.env.PROD`, not NODE_ENV, which this repo keeps
 * out of product code (`check:ci-env-manifest`). Where `import.meta.env` is undefined (tsx
 * gate scripts, and `astro.config.mjs` when Node imports it natively for the remark
 * plugin) the check stays live, which costs a stat per lookup and is never wrong.
 */
const existsMemo = import.meta.env?.PROD === true ? new Map<string, boolean>() : null;

/** Does `/assets/...` (a site-root path) exist as a file under `publicDir`? */
export function publicFileExists(publicPath: string, publicDir: string = WWW_PUBLIC_DIR): boolean {
  const abs = path.join(publicDir, publicPath);
  const hit = existsMemo?.get(abs);
  if (hit !== undefined) return hit;
  let exists = false;
  try {
    exists = fs.statSync(abs).isFile();
  } catch {
    exists = false;
  }
  existsMemo?.set(abs, exists);
  return exists;
}

export interface ResolveMediaUrlOptions {
  /** Site-root path, e.g. `/assets/videos/solutions/en/home.mp4`. */
  localPath: string;
  /** Bucket key, e.g. `videos/solutions/en/home.mp4`. */
  cdnKey: string;
  /** Already normalised by `cdnBaseUrl()`. */
  cdnBase: string;
  /** Test seam; defaults to `packages/www/public`. */
  publicDir?: string;
}

/** Local path when the file is checked out, CDN URL otherwise. */
export function resolveMediaUrl({
  localPath,
  cdnKey,
  cdnBase,
  publicDir,
}: ResolveMediaUrlOptions): string {
  if (publicFileExists(localPath, publicDir)) return localPath;
  return `${cdnBase}/${cdnKey.replace(/^\/+/, '')}`;
}
