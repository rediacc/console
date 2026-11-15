/**
 * The images an air-gapped Elite box needs, and where each ref comes from:
 *
 *   server   the account server image, `--image <local ref>` or `<registry>/server:<tag>`;
 *   rustfs   the digest-pinned ref in the elite template's compose file, read from the built-in
 *            template so a bundle never ships a RustFS the template would not run;
 *   traefik  renet's proxy (`private/renet/proxy/docker-compose.yml`), a constant here that a
 *            vitest pins to that file.
 */

import { t } from '../../../i18n/index.js';
import { ServerError } from '../box.js';
import { DEFAULT_IMAGE, templateFiles } from '../common.js';

/** Renet's proxy image; must equal the `image:` line of private/renet/proxy/docker-compose.yml. */
export const TRAEFIK_REF = 'traefik:v3.7.16';

type BundleImageName = 'server' | 'rustfs' | 'traefik';

export interface BundleImage {
  name: BundleImageName;
  ref: string;
  /** The tar's path inside the bundle. */
  file: string;
}

const RUSTFS_REF = /rustfs\/rustfs@sha256:[0-9a-f]{64}/;

/** The RustFS ref the built-in elite template runs. */
export function rustfsRef(): string {
  const compose =
    Object.entries(templateFiles()).find(([name]) => name === 'docker-compose.yml')?.[1] ?? '';
  const match = RUSTFS_REF.exec(compose);
  if (!match) throw new ServerError(t('commands.server.bundle.errors.noRustfsRef'));
  return match[0];
}

/** `<registry>/server:<tag>` for a tag; the default image's own ref when neither is given. */
export function serverRef(opts: { tag?: string; image?: string }): string {
  if (opts.image) return opts.image;
  if (!opts.tag) return DEFAULT_IMAGE;
  return `${DEFAULT_IMAGE.slice(0, DEFAULT_IMAGE.lastIndexOf(':'))}:${opts.tag}`;
}

export function bundleImages(server: string): BundleImage[] {
  return [
    { name: 'server', ref: server, file: 'images/server.tar' },
    { name: 'rustfs', ref: rustfsRef(), file: 'images/rustfs.tar' },
    { name: 'traefik', ref: TRAEFIK_REF, file: 'images/traefik.tar' },
  ];
}
