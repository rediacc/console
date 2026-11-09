import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { CONFIGURED_IMAGES, ImageTestHelper } from '../image/ImageTestHelper.js';

const dirs: string[] = [];
afterEach(() => {
  for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

describe('ImageTestHelper.listCustomImages', () => {
  it('lists the files named by the configured image urls and leaves other disks out', () => {
    const disks = fs.mkdtempSync(path.join(os.tmpdir(), 'image-list-'));
    dirs.push(disks);
    const first = path.basename(new URL(CONFIGURED_IMAGES[0].url).pathname);
    fs.writeFileSync(path.join(disks, first), '');
    fs.writeFileSync(path.join(disks, 'unrelated-base.qcow2'), '');
    const helper = new ImageTestHelper({ disksPath: disks, renetBin: process.execPath });
    expect(helper.listCustomImages()).toEqual([first]);
  });

  it('returns an empty list for a missing disks directory', () => {
    const helper = new ImageTestHelper({
      disksPath: path.join(os.tmpdir(), 'image-list-does-not-exist'),
      renetBin: process.execPath,
    });
    expect(helper.listCustomImages()).toEqual([]);
  });
});
