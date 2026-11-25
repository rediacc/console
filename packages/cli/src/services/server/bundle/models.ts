/**
 * The detection models of an air-gapped bundle (D12): the stable channel's pointer, the manifest it
 * names and the objects that manifest lists, each with its detached `.sig`, written under `models/`
 * in the layout the public data bucket serves them in. The box's renet verifies them with the model
 * key; the bundle only carries them, and records every file, signatures included, in the manifest and the
 * sums, which `verifyBundle` checks at install, so a signature changed after bundling is refused.
 */

import { dirname, join } from 'node:path';
import { t } from '../../../i18n/index.js';
import { outputService } from '../../core/output.js';
import { ServerError } from '../box.js';
import type { ServerDeps } from '../types.js';
import type { ManifestFile } from './manifest.js';

const MODELS_DIR = 'models';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function shapeError(file: string): ServerError {
  return new ServerError(t('commands.server.bundle.errors.modelsShape', { file }));
}

function parseJson(text: string, file: string): Record<string, unknown> {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw shapeError(file);
  }
  if (!isRecord(raw)) throw shapeError(file);
  return raw;
}

const POINTER = 'channels/stable.json';

/** The manifest version and sha256 the stable pointer names. */
function pointerOf(text: string): { version: string; manifestSha256: string } {
  const { version, manifest_sha256: sha } = parseJson(text, POINTER);
  if (typeof version !== 'string' || !/^[\w.-]+$/.test(version) || typeof sha !== 'string') {
    throw shapeError(POINTER);
  }
  return { version, manifestSha256: sha };
}

function objectHashes(text: string, file: string): string[] {
  const files = parseJson(text, file).files;
  if (!Array.isArray(files)) throw shapeError(file);
  return files.map((entry) => {
    const sha = isRecord(entry) ? entry.sha256 : undefined;
    if (typeof sha !== 'string' || !/^[0-9a-f]{64}$/.test(sha)) throw shapeError(file);
    return sha;
  });
}

/** The models root on the release host: the channel's origin without its `/cli` path, plus `/models`. */
function modelsBase(deps: ServerDeps): string {
  return `${deps.release.baseUrl().replace(/\/cli$/, '')}/models`;
}

async function fetchFile(
  deps: ServerDeps,
  out: string,
  rel: string,
  expected?: string
): Promise<ManifestFile> {
  const file = `${MODELS_DIR}/${rel}`;
  const url = `${modelsBase(deps)}/${rel}`;
  await deps.makeDir(dirname(join(out, file)));
  await deps.release.download(url, join(out, file));
  const sha256 = await deps.sha256File(join(out, file));
  if (expected !== undefined && sha256 !== expected) {
    throw new ServerError(
      t('commands.server.bundle.errors.modelsSha256Mismatch', { url, expected, actual: sha256 })
    );
  }
  return { file, sha256 };
}

/** Download the stable channel's models and their signatures; every file is returned for the records. */
export async function fetchModels(deps: ServerDeps, out: string): Promise<ManifestFile[]> {
  outputService.info(t('commands.server.bundle.fetchingModels'));
  const pointer = await fetchFile(deps, out, POINTER);
  const entries: ManifestFile[] = [pointer, await fetchFile(deps, out, `${POINTER}.sig`)];
  const { version, manifestSha256 } = pointerOf(await deps.readFile(join(out, pointer.file)));
  const manifestRel = `manifests/${version}.json`;
  entries.push(
    await fetchFile(deps, out, manifestRel, manifestSha256),
    await fetchFile(deps, out, `${manifestRel}.sig`)
  );
  const manifestText = await deps.readFile(join(out, MODELS_DIR, manifestRel));
  for (const sha of new Set(objectHashes(manifestText, manifestRel))) {
    entries.push(
      await fetchFile(deps, out, `objects/${sha}`, sha),
      await fetchFile(deps, out, `objects/${sha}.sig`)
    );
  }
  return entries;
}
