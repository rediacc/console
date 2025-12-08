import type { ReactNode, MouseEvent, CSSProperties } from 'react';

export type ButtonVariant = 'primary' | 'danger' | 'default' | 'text' | 'link' | 'ghost';
export type ButtonSize = 'sm' | 'md';

export interface RediaccButtonProps {
  /** Visual style variant */
  variant?: ButtonVariant;
  /** Button size: sm (28px), md (32px) */
  size?: ButtonSize;
  /** Render as icon-only button (square, no text) */
  iconOnly?: boolean;
  /** Alias for iconOnly - square button with icon only */
  square?: boolean;
  /** Compact mode: smaller size with tighter padding (equivalent to size='sm') */
  compact?: boolean;
  /** Icon element to render before children */
  icon?: ReactNode;
  /** Loading state - shows spinner and disables button */
  loading?: boolean;
  /** Disabled state */
  disabled?: boolean;
  /** HTML button type for form submission */
  htmlType?: 'button' | 'submit' | 'reset';
  /** Click handler */
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  /** Minimum width in pixels */
  minWidth?: number;
  /** Stretch to full container width */
  fullWidth?: boolean;
  /** Danger styling (semantic alias for variant="danger") */
  danger?: boolean;
  /** Accessibility label (required for iconOnly buttons) */
  'aria-label'?: string;
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Button content */
  children?: ReactNode;
  /** Tab index for keyboard navigation */
  tabIndex?: number;
  /** Block display (full width, deprecated - use fullWidth) */
  block?: boolean;
  /** HTML title attribute for tooltip on hover */
  title?: string;
}
