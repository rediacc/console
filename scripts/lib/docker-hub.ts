/**
 * Docker Hub's repository and tag addressing, and the one place a tag's digest is read.
 *
 * Two readers share it: the `docker` driver of `npm run pins` (scripts/lib/pins/drivers/
 * docker.ts), which resolves the digest a bump writes beside the tag, and check:ci-docker-
 * image-freshness, which proves every `<image>:<tag>@sha256:<digest>` line in the tree still
 * agrees with what Docker Hub serves for that tag. Each keeps its own transport (the driver's
 * `Deps.json` seam, the gate's token-then-anonymous fetch); neither keeps its own parser.
 *
 * WHICH DIGEST. `GET /v2/repositories/<repo>/tags/<tag>` answers a top-level `digest`, the
 * multi-arch INDEX digest, the same value `docker buildx imagetools inspect <image>:<tag>`
 * prints as `Manifest.Digest` and the one a `FROM <image>:<tag>@sha256:...` line must carry.
 * The per-architecture digests under `images[]` are NOT it: pinning one of those makes every
 * other architecture fail to pull. So only the top-level field is read, and anything else
 * (absent, malformed, an `images[]`-only answer) is null, which every caller treats as a
 * refusal, never as agreement.
 */

/** The Docker Hub API host a caller uses when no stub base is set. */
export const HUB_DEFAULT_BASE = 'https://hub.docker.com';

const DIGEST = /^sha256:[0-9a-f]{64}$/;

/**
 * The Docker Hub repository path of an image reference (`node` -> `library/node`,
 * `docker.io/foo/bar` -> `foo/bar`), or null for an image served by another registry
 * (a first path component carrying a dot, `mcr.microsoft.com/...`, `ghcr.io/...`). Pure.
 */
export function hubRepo(image: string): string | null {
  if (image.includes('.') && !image.startsWith('docker.io/')) return null;
  const bare = image.replace(/^docker\.io\//, '');
  return bare.includes('/') ? bare : `library/${bare}`;
}

/** The per-tag endpoint, whose answer carries the tag's index `digest`. Pure. */
export function hubTagUrl(base: string, repo: string, tag: string): string {
  return `${base.replace(/\/+$/, '')}/v2/repositories/${repo}/tags/${encodeURIComponent(tag)}`;
}

/**
 * The index digest of a per-tag answer: its top-level `digest` when that is exactly
 * `sha256:<64 hex>`, else null. `images[]` is never consulted (see WHICH DIGEST). Pure.
 */
export function parseTagDigest(json: unknown): string | null {
  if (typeof json !== 'object' || json === null || Array.isArray(json)) return null;
  const d = (json as { digest?: unknown }).digest;
  return typeof d === 'string' && DIGEST.test(d) ? d : null;
}
