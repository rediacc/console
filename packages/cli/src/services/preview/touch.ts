/**
 * The provisioner's view of the preview overlay (PLAN-preview-signer.md D9): whether a replacement of a
 * server's renet must be recorded and pinned, and under which config name.
 */
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import type { PreviewTouch } from './slot-ops.js';
import { readPreviewOverlay } from './state.js';

/** The machine-name rule of the config schema (`resourceName`), the key of `preview.touched`. */
const MACHINE_NAME = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;

/**
 * The `previewTouch` provision option while a preview is active, nothing otherwise. A replacement that cannot
 * name the machine in the config would leave no record to switch back from, so the provisioner refuses it with
 * the carried error instead of proceeding unrecorded; a provision that replaces nothing is not refused.
 */
export function previewTouchOption(machineName: string | undefined): {
  previewTouch?: PreviewTouch;
} {
  const overlay = readPreviewOverlay();
  if (!overlay) return {};
  if (machineName === undefined || !MACHINE_NAME.test(machineName)) {
    // Raised only when a replacement is about to be recorded: a no-op provision of an unnamed machine proceeds.
    return {
      previewTouch: {
        refusal: new ValidationError(
          t('errors.preview.machineUnnamed', { name: overlay.name, machine: machineName ?? '' })
        ),
      },
    };
  }
  return { previewTouch: { machine: machineName } };
}
