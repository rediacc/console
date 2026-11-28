/**
 * The bundle's records: `manifest.json` (what it holds and which CLI built it), `SHA256SUMS`
 * (every file, `sha256sum` format) and `images/manifest.txt` (the `<tar> <ref>` lines the elite
 * template's `up()` loads; the proxy image is not in it, since it loads into the machine's Docker).
 */

import { createHash } from 'node:crypto';
import { t } from '../../../i18n/index.js';
import { ServerError } from '../box.js';
import { builtinTemplateVersion, TEMPLATE_NAME, templateFiles } from '../common.js';
import { BUNDLE_ARCHES, type BundleArch } from '../types.js';

export const BUNDLE_SCHEMA = 1;
export const MANIFEST_FILE = 'manifest.json';
export const SUMS_FILE = 'SHA256SUMS';
export const IMAGE_LIST_FILE = 'images/manifest.txt';

export class BundleError extends ServerError {}

export interface ManifestImage {
  ref: string;
  /** The image id (`docker image inspect --format '{{.Id}}'`) of what was saved. */
  digest: string;
  file: string;
  sha256: string;
}

/** One CLI binary shipped for installing on the machines that have none (`--with-cli`). */
export interface ManifestCli {
  platform: string;
  file: string;
  sha256: string;
}

/** One file the bundle carries beside the images: its path under the bundle and its sha256. */
export interface ManifestFile {
  file: string;
  sha256: string;
}

export interface BundleManifest {
  schema: number;
  cliVersion: string;
  template: { name: string; version: number; sha256: string };
  renet: { version: string; arch: BundleArch; file: string; sha256: string };
  images: ManifestImage[];
  /** Present only when the bundle was built with `--with-cli`. */
  cli?: ManifestCli[];
  /** Every file under `models/`; absent when the bundle was built with `--no-models`. */
  models?: ManifestFile[];
  /** sha256 of `images/manifest.txt`, which the signed manifest binds like the images. */
  imageList: string;
  createdAt: string;
}

/** sha256 over the built-in elite template's files, in path order. */
function templateSha256(): string {
  const files = templateFiles();
  const hash = createHash('sha256');
  for (const path of Object.keys(files).sort((a, b) => Number(a > b) - Number(a < b))) {
    hash.update(`${path}\0${files[path]}\0`);
  }
  return hash.digest('hex');
}

export function templateInfo(): BundleManifest['template'] {
  return { name: TEMPLATE_NAME, version: builtinTemplateVersion(), sha256: templateSha256() };
}

export interface SumEntry {
  file: string;
  sha256: string;
}

/** `sha256sum` format: `<hash>  <path>` per line, in path order. */
export function sumsText(entries: SumEntry[]): string {
  const sorted = [...entries].sort((a, b) => Number(a.file > b.file) - Number(a.file < b.file));
  return `${sorted.map((e) => `${e.sha256}  ${e.file}`).join('\n')}\n`;
}

export function parseSums(text: string): SumEntry[] {
  const entries: SumEntry[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    const match = /^([0-9a-f]{64}) [ *](.+)$/.exec(line);
    if (!match) throw new BundleError(t('commands.server.bundle.errors.sumsLine', { line }));
    entries.push({ sha256: match[1], file: match[2] });
  }
  return entries;
}

/** The `images/manifest.txt` the template reads: the server and RustFS tars, never the proxy's. */
export function imageListText(images: ManifestImage[]): string {
  return `${images
    .filter((i) => i.file !== 'images/traefik.tar')
    .map((i) => `${i.file.replace(/^images\//, '')} ${i.ref}`)
    .join('\n')}\n`;
}

function bad(what: string): BundleError {
  return new BundleError(t('commands.server.bundle.errors.manifestShape', { what }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function str(value: unknown, what: string): string {
  if (typeof value !== 'string' || !value) throw bad(what);
  return value;
}

function image(raw: unknown): ManifestImage {
  if (!isRecord(raw)) throw bad('images[]');
  return {
    ref: str(raw.ref, 'images[].ref'),
    digest: str(raw.digest, 'images[].digest'),
    file: str(raw.file, 'images[].file'),
    sha256: str(raw.sha256, 'images[].sha256'),
  };
}

function fileEntry(raw: unknown): ManifestFile {
  if (!isRecord(raw)) throw bad('models[]');
  return { file: str(raw.file, 'models[].file'), sha256: str(raw.sha256, 'models[].sha256') };
}

function cliEntry(raw: unknown): ManifestCli {
  if (!isRecord(raw)) throw bad('cli[]');
  return {
    platform: str(raw.platform, 'cli[].platform'),
    file: str(raw.file, 'cli[].file'),
    sha256: str(raw.sha256, 'cli[].sha256'),
  };
}

/**
 * The parsed manifest's checked parts: the top-level shape, schema version, arch and array fields are refused here.
 * The string fields and the entries of `images`, `models` and `cli` are refused by `parseManifest` as it reads them.
 */
function checkedManifest(text: string) {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw bad('JSON');
  }
  if (!isRecord(raw) || !isRecord(raw.template) || !isRecord(raw.renet)) throw bad('shape');
  if (raw.schema !== BUNDLE_SCHEMA) {
    throw new BundleError(
      t('commands.server.bundle.errors.schema', { schema: String(raw.schema) })
    );
  }
  const arch = raw.renet.arch;
  if (!BUNDLE_ARCHES.includes(arch as BundleArch)) throw bad('renet.arch');
  if (!Array.isArray(raw.images)) throw bad('images');
  return {
    raw,
    template: raw.template,
    renet: raw.renet,
    arch: arch as BundleArch,
    images: raw.images as unknown[],
    cli: optionalArray(raw.cli, 'cli'),
    models: optionalArray(raw.models, 'models'),
  };
}

/** An optional array field: absent stays undefined, anything else but an array is refused. */
function optionalArray(value: unknown, field: string): unknown[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw bad(field);
  return value;
}

export function parseManifest(text: string): BundleManifest {
  const { raw, template, renet, arch, images, cli, models } = checkedManifest(text);
  return {
    schema: BUNDLE_SCHEMA,
    cliVersion: str(raw.cliVersion, 'cliVersion'),
    template: {
      name: str(template.name, 'template.name'),
      version: Number(template.version),
      sha256: str(template.sha256, 'template.sha256'),
    },
    renet: {
      version: str(renet.version, 'renet.version'),
      arch,
      file: str(renet.file, 'renet.file'),
      sha256: str(renet.sha256, 'renet.sha256'),
    },
    images: images.map(image),
    ...(cli !== undefined && { cli: cli.map(cliEntry) }),
    ...(models !== undefined && { models: models.map(fileEntry) }),
    imageList: str(raw.imageList, 'imageList'),
    createdAt: str(raw.createdAt, 'createdAt'),
  };
}

/** The server image's ref in a bundle. */
export function serverImageOf(manifest: BundleManifest): ManifestImage {
  const found = manifest.images.find((i) => i.file === 'images/server.tar');
  if (!found) throw bad('images (no server.tar)');
  return found;
}
