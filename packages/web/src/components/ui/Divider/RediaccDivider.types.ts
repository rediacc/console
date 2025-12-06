import type { ReactNode, CSSProperties } from 'react';

export type DividerOrientation = 'horizontal' | 'vertical';
export type DividerSpacing = 'none' | 'sm' | 'md' | 'lg';

export interface RediaccDividerProps {
  /** Orientation of the divider */
  orientation?: DividerOrientation;
  /** Spacing (margin) around the divider */
  spacing?: DividerSpacing;
  /** Dashed line style */
  dashed?: boolean;
  /** Text to display in center of divider (horizontal only) */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
