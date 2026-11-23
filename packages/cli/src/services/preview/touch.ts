/**
 * The provisioner's view of the preview overlay (PLAN-preview-signer.md D9): whether a replacement of a
 * server's renet must be recorded and pinned, and under which config name.
 */
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { readPreviewOverlay } from './state.js';

/** The machine-name rule of the config schema (`resourceName`), the key of `preview.touched`. */
const MACHINE_NAME = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;

/**
 * The `previewTouch` provision option while a preview is active, nothing otherwise. A replacement that cannot
 * name the machine in the config would leave no record to switch back from, so it is refused instead of
 * proceeding unrecorded.
 */
export function previewTouchOption(machineName: string | undefined): {
  previewTouch?: { machine: string };
} {
  const overlay = readPreviewOverlay();
  if (!overlay) return {};
  if (machineName === undefined || !MACHINE_NAME.test(machineName)) {
    throw new ValidationError(
      t('errors.preview.machineUnnamed', { name: overlay.name, machine: machineName ?? '' })
    );
  }
  return { previewTouch: { machine: machineName } };
}
