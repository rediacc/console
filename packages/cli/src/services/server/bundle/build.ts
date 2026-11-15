/**
 * `rdc server bundle --out <dir>`: run online, writes everything an air-gapped box installs from:
 *
 *   images/server.tar, rustfs.tar, traefik.tar   each `docker save --platform linux/<arch>`
 *   images/manifest.txt                          the `<tar> <ref>` lines the template loads
 *   renet/renet-linux-<arch>                     this CLI's own renet
 *   manifest.json, SHA256SUMS
 */

import { join } from 'node:path';
import { t } from '../../../i18n/index.js';
import { VERSION } from '../../../version.js';
import { outputService } from '../../core/output.js';
import { ServerError } from '../box.js';
import type { BundleArch, ServerDeps } from '../types.js';
import { bundleImages, serverRef } from './images.js';
import {
  BUNDLE_SCHEMA,
  type BundleManifest,
  IMAGE_LIST_FILE,
  imageListText,
  MANIFEST_FILE,
  type ManifestImage,
  SUMS_FILE,
  type SumEntry,
  sumsText,
  templateInfo,
} from './manifest.js';

export interface BundleOptions {
  out: string;
  arch?: BundleArch;
  tag?: string;
  /** A locally present image to ship instead of pulling the registry's. */
  image?: string;
}

async function must(
  deps: ServerDeps,
  command: string,
  args: string[],
  failure: string
): Promise<void> {
  if ((await deps.local(command, args)) !== 0) throw new ServerError(failure);
}

/** Pull (unless the image is local), save and hash one image. */
async function saveImage(
  deps: ServerDeps,
  out: string,
  arch: BundleArch,
  image: { ref: string; file: string },
  pull: boolean
): Promise<ManifestImage> {
  const platform = `linux/${arch}`;
  if (pull) {
    outputService.info(t('commands.server.bundle.pulling', { image: image.ref, platform }));
    await must(
      deps,
      'docker',
      ['pull', '--platform', platform, image.ref],
      t('commands.server.bundle.errors.pullFailed', { image: image.ref })
    );
  }
  const file = join(out, image.file);
  outputService.info(t('commands.server.bundle.saving', { image: image.ref, file: image.file }));
  await must(
    deps,
    'docker',
    ['save', '--platform', platform, '-o', file, image.ref],
    t('commands.server.bundle.errors.saveFailed', { image: image.ref })
  );
  const inspected = await deps.localOut('docker', [
    'image',
    'inspect',
    '--format',
    '{{.Id}}',
    image.ref,
  ]);
  const digest = inspected.stdout.trim();
  if (inspected.code !== 0 || !digest) {
    throw new ServerError(t('commands.server.bundle.errors.inspectFailed', { image: image.ref }));
  }
  return { ref: image.ref, digest, file: image.file, sha256: await deps.sha256File(file) };
}

export async function serverBundle(deps: ServerDeps, opts: BundleOptions): Promise<BundleManifest> {
  const arch = opts.arch ?? 'amd64';
  if (opts.tag && opts.image) {
    throw new ServerError(t('commands.server.bundle.errors.tagAndImage'));
  }
  await deps.makeDir(join(opts.out, 'images'));
  await deps.makeDir(join(opts.out, 'renet'));

  const images: ManifestImage[] = [];
  for (const image of bundleImages(serverRef(opts))) {
    // A local `--image` is saved as it is; every other image is pulled for the target platform first.
    const local = image.name === 'server' && opts.image !== undefined;
    images.push(await saveImage(deps, opts.out, arch, image, !local));
  }

  const renetFile = `renet/renet-linux-${arch}`;
  const renet = await deps.renetAsset(arch, join(opts.out, renetFile));
  const manifest: BundleManifest = {
    schema: BUNDLE_SCHEMA,
    cliVersion: VERSION,
    template: templateInfo(),
    renet: { version: renet.version, arch, file: renetFile, sha256: renet.sha256 },
    images,
    createdAt: new Date(deps.now()).toISOString(),
  };

  const manifestText = `${JSON.stringify(manifest, null, 2)}\n`;
  const listText = imageListText(images);
  await deps.writePrivate(join(opts.out, MANIFEST_FILE), manifestText);
  await deps.writePrivate(join(opts.out, IMAGE_LIST_FILE), listText);
  const sums: SumEntry[] = [
    ...images.map((i) => ({ file: i.file, sha256: i.sha256 })),
    { file: renetFile, sha256: renet.sha256 },
    { file: MANIFEST_FILE, sha256: await deps.sha256File(join(opts.out, MANIFEST_FILE)) },
    { file: IMAGE_LIST_FILE, sha256: await deps.sha256File(join(opts.out, IMAGE_LIST_FILE)) },
  ];
  await deps.writePrivate(join(opts.out, SUMS_FILE), sumsText(sums));
  outputService.success(t('commands.server.bundle.written', { dir: opts.out, arch }));
  return manifest;
}
