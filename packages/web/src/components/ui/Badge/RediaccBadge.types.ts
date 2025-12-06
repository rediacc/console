import type { ReactNode, CSSProperties } from 'react';

export type BadgeVariant =
  | 'default'
  | 'primary'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'muted';
export type BadgeSize = 'sm' | 'md';

export interface RediaccBadgeProps {
  /** Badge color variant */
  variant?: BadgeVariant;
  /** Badge size: sm, md */
  size?: BadgeSize;
  /** Number to display */
  count?: number;
  /** Show as dot instead of count */
  dot?: boolean;
  /** Show badge when count is zero */
  showZero?: boolean;
  /** Maximum count to display (shows count+ when exceeded) */
  overflowCount?: number;
  /** Badge content (usually the element to badge) */
  children?: ReactNode;
  /** Offset position [x, y] */
  offset?: [number, number];
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
