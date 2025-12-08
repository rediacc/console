import type { ReactNode, CSSProperties } from 'react';

export type AlertVariant = 'info' | 'warning' | 'error' | 'success' | 'neutral';
export type AlertSize = 'sm' | 'md';

/**
 * Alert spacing variants for margin-bottom control
 */
export type AlertSpacing = 'none' | 'compact' | 'default' | 'spacious';

export interface RediaccAlertProps {
  /** Alert type/color variant */
  variant?: AlertVariant;
  /** Padding size: sm, md */
  size?: AlertSize;
  /** Margin-bottom spacing: none (0), compact (sm), default (md), spacious (lg) */
  spacing?: AlertSpacing;
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
  /** Custom action element (e.g., button) */
  action?: ReactNode;
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
