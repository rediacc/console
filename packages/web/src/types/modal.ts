/**
 * Modal Size Types and Enums
 *
 * This file provides type-safe modal sizing options that correspond to the CSS classes
 * defined in /src/styles/global.css
 *
 * Usage:
 * import { ModalSize } from '@/types/modal'
 *
 * <Modal className={ModalSize.Medium} />
 */

/**
 * Modal size enum with CSS class names
 * Simplified to 3 core sizes plus fullscreen
 */
export enum ModalSize {
  /** Small modal (560px) - ideal for confirmations, simple forms */
  Small = 'modal-sm',
  /** Medium modal (768px) - ideal for standard forms, content viewing */
  Medium = 'modal-md',
  /** Large modal (1024px) - ideal for complex forms, dashboards, detailed content */
  Large = 'modal-lg',
  /** Fullscreen modal - occupies entire browser viewport */
  Fullscreen = 'modal-fullscreen',
}

/**
 * Modal width values for use with Ant Design Modal's width prop
 * Use these with className to get proper sizing without !important
 *
 * Usage:
 * <Modal width={MODAL_WIDTHS[ModalSize.Large]} className={ModalSize.Large} />
 */
export const MODAL_WIDTHS: Record<ModalSize, number | string> = {
  [ModalSize.Small]: 560,
  [ModalSize.Medium]: 768,
  [ModalSize.Large]: 1024,
  [ModalSize.Fullscreen]: 'calc(100vw - 32px)',
};

/**
 * Base props that all modals should have
 */
export interface BaseModalProps {
  /** Whether the modal is visible */
  open: boolean;
  /** Callback when modal is closed/cancelled */
  onCancel: () => void;
  /** Optional callback when modal operation succeeds */
  onSuccess?: () => void;
}
