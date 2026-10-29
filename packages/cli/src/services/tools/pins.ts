/**
 * The seam between the tools service and the generated OpenTofu pin.
 *
 * The pins driver writes `opentofu-pin.generated.ts` (leaf `cli-tool:opentofu` in .ci/config/pins.json). Until that file lands, this module carries a stand-in of the same shape whose checksums are all zeros, so an install fails closed at the checksum step and places nothing. Once the generated file exists, this whole module becomes the one line
 *
 *   export { OPENTOFU_PIN } from './opentofu-pin.generated.js';
 */

import type { ToolAsset, ToolPin } from './types.js';

const STANDIN_VERSION = '1.10.6';
const ZERO_SHA = '0'.repeat(64);

function standinAsset(os: string, arch: string): ToolAsset {
  return {
    url: `https://github.com/opentofu/opentofu/releases/download/v${STANDIN_VERSION}/tofu_${STANDIN_VERSION}_${os}_${arch}.zip`,
    sha256: ZERO_SHA,
  };
}

export const OPENTOFU_PIN: ToolPin = {
  version: STANDIN_VERSION,
  assets: {
    'linux-amd64': standinAsset('linux', 'amd64'),
    'linux-arm64': standinAsset('linux', 'arm64'),
    'darwin-amd64': standinAsset('darwin', 'amd64'),
    'darwin-arm64': standinAsset('darwin', 'arm64'),
    'windows-amd64': standinAsset('windows', 'amd64'),
    'windows-arm64': standinAsset('windows', 'arm64'),
  },
};
