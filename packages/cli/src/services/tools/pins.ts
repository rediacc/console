/** The seam between the tools service and the generated pins: OpenTofu (leaf `cli-tool:opentofu`) and the MSYS2 rsync set (leaves `cli-tool:msys2-*`) in .ci/config/pins.json. */
export { MSYS2_REPO, MSYS2_RSYNC_PIN } from './msys2-rsync-pin.generated.js';
export { OPENTOFU_PIN } from './opentofu-pin.generated.js';
