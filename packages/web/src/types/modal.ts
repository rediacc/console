/**
 * Modal Size Types and Enums
 *
 * This file provides type-safe modal sizing options that correspond to the CSS classes
 * defined in /src/styles/GlobalStyles.ts
 *
 * Usage:
 * import { ModalSize } from '@/types/modal'
 *
 * <Modal className={ModalSize.Medium} />
 */

/**
 * Modal size enum with CSS class names
 */
export enum ModalSize {
  /** Small modal - ideal for confirmations, simple forms */
  Small = 'modal-sm',
  /** Medium modal - ideal for standard forms, content viewing */
  Medium = 'modal-md',
  /** Large modal - ideal for complex forms, detailed content */
  Large = 'modal-lg',
  /** Extra large modal - ideal for full-featured interfaces */
  ExtraLarge = 'modal-xl',
  /** Full width modal - ideal for tables, dashboards */
  Full = 'modal-full',
  /** Fullscreen modal - occupies entire browser viewport */
  Fullscreen = 'modal-fullscreen',
}

/**
 * Helper type for modal size values
 */
export type ModalSizeValue = `${ModalSize}`;

/**
 * Modal configuration interface
 * Provides additional options for modal behavior and styling
 */
export interface ModalConfig {
  /** Size preset to apply */
  size: ModalSize;
  /** Whether modal content should be scrollable */
  scrollable?: boolean;
  /** Custom CSS class to add alongside size class */
  className?: string;
}

/**
 * Helper function to generate modal className string
 * Combines size class with optional scrollable/custom classes
 */
export function getModalClassName(config: ModalConfig): string {
  const classes: string[] = [config.size as string];

  if (config.scrollable) {
    classes.push('modal-content-scrollable' as string);
  }

  if (config.className) {
    classes.push(config.className);
  }

  return classes.join(' ');
}

/**
 * Modal size recommendations based on content type
 */
export const MODAL_SIZE_RECOMMENDATIONS = {
  // Simple content
  confirmation: ModalSize.Small,
  alert: ModalSize.Small,
  simpleForm: ModalSize.Small,

  // Standard content
  standardForm: ModalSize.Medium,
  contentView: ModalSize.Medium,
  userProfile: ModalSize.Medium,

  // Complex content
  complexForm: ModalSize.Large,
  multiStepWizard: ModalSize.Large,
  detailedView: ModalSize.Large,

  // Full-featured content
  dashboard: ModalSize.ExtraLarge,
  dataTable: ModalSize.ExtraLarge,
  editor: ModalSize.ExtraLarge,

  // Maximum content
  fullInterface: ModalSize.Full,
  reporting: ModalSize.Full,
  analytics: ModalSize.Full,
} as const;

/**
 * Type for modal size recommendation keys
 */
export type ModalSizeRecommendation = keyof typeof MODAL_SIZE_RECOMMENDATIONS;

/**
 * Shared type definitions for modal component props.
 * Use these base types to ensure consistency across all modal implementations.
 */

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

/**
 * Props for modals that contain forms (create/edit operations)
 */
export interface FormModalProps<T = Record<string, unknown>> extends BaseModalProps {
  /** Whether this is create or edit mode */
  mode: 'create' | 'edit';
  /** Initial data for edit mode */
  initialData?: Partial<T>;
  /** Form submission handler */
  onSubmit: (data: T) => void | Promise<void>;
}

/**
 * Props for modals that handle resource selection
 */
export interface SelectionModalProps<T = unknown> extends BaseModalProps {
  /** Available items to select from */
  items: T[];
  /** Currently selected items */
  selectedItems?: T[];
  /** Callback when selection changes */
  onSelect: (items: T[]) => void;
  /** Whether multiple selection is allowed */
  multiSelect?: boolean;
}

/**
 * Props for confirmation modals
 */
export interface ConfirmationModalProps extends BaseModalProps {
  /** Title of the confirmation */
  title: string;
  /** Description/message to show */
  message: string;
  /** Callback when confirmed */
  onConfirm: () => void | Promise<void>;
  /** Whether the action is dangerous (affects styling) */
  danger?: boolean;
  /** Text for confirm button */
  confirmText?: string;
  /** Text for cancel button */
  cancelText?: string;
}

/**
 * Props for modals that display detailed information
 */
export interface DetailModalProps<T = unknown> extends BaseModalProps {
  /** The data to display */
  data: T | null;
  /** Loading state */
  loading?: boolean;
}
