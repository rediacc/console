import type { ReactNode, CSSProperties } from 'react';

export type AlertVariant = 'info' | 'warning' | 'error' | 'success' | 'neutral';
export type AlertSize = 'sm' | 'md';

export interface RediaccAlertProps {
  /** Alert type/color variant */
  variant?: AlertVariant;
  /** Padding size: sm, md */
  size?: AlertSize;
  /** Show icon beside message */
  showIcon?: boolean;
  /** Show close button */
  closable?: boolean;
  /** Full-width banner style (no rounded corners) */
  banner?: boolean;
  /** Rounded corners (default true) */
  rounded?: boolean;
  /** Alert message content */
  message?: ReactNode;
  /** Additional description */
  description?: ReactNode;
  /** Custom icon */
  icon?: ReactNode;
  /** Callback when alert is closed */
  onClose?: () => void;
  /** Children (alternative to message prop) */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
