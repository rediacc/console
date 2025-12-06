import type { ReactNode, CSSProperties } from 'react';

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'fullscreen';
export type ModalVariant = 'default' | 'danger';

export interface RediaccModalProps {
  /** Modal width size */
  size?: ModalSize;
  /** Color variant for header/actions */
  variant?: ModalVariant;
  /** Center modal vertically */
  centered?: boolean;
  /** Show close button */
  closable?: boolean;
  /** Close on mask click */
  maskClosable?: boolean;
  /** Destroy content on close */
  destroyOnClose?: boolean;
  /** Modal visibility */
  open?: boolean;
  /** Modal title */
  title?: ReactNode;
  /** Footer content (null to hide) */
  footer?: ReactNode;
  /** Close callback */
  onCancel?: () => void;
  /** OK callback */
  onOk?: () => void;
  /** OK button loading state */
  confirmLoading?: boolean;
  /** OK button text */
  okText?: ReactNode;
  /** Cancel button text */
  cancelText?: ReactNode;
  /** Modal content */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
  /** z-index for layering */
  zIndex?: number;
}
