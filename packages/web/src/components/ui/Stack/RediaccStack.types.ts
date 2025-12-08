import type { ReactNode, CSSProperties } from 'react';

export type StackDirection = 'horizontal' | 'vertical';
export type StackGap = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
export type StackAlign = 'start' | 'center' | 'end' | 'stretch' | 'baseline';
export type StackJustify = 'start' | 'center' | 'end' | 'between' | 'around';

/**
 * Stack layout presets for common patterns
 * - row: horizontal with md gap
 * - column: vertical with md gap
 * - tight-row: horizontal with xs gap
 * - spaced-column: vertical with lg gap
 * - wrap-grid: horizontal with wrap and sm gap
 */
export type StackVariant =
  | 'default'
  | 'row'
  | 'column'
  | 'tight-row'
  | 'spaced-column'
  | 'wrap-grid';

export interface RediaccStackProps {
  /** Layout preset variant (sets direction, gap, and wrap) */
  variant?: StackVariant;
  /** Stack direction: horizontal (row) or vertical (column) */
  direction?: StackDirection;
  /** Gap between items: none, xs (4px), sm (8px), md (16px), lg (24px), xl (32px) */
  gap?: StackGap | number;
  /** Align items on cross axis */
  align?: StackAlign;
  /** Justify content on main axis */
  justify?: StackJustify;
  /** Allow items to wrap */
  wrap?: boolean;
  /** Stretch to full container width */
  fullWidth?: boolean;
  /** Stack content */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
  /** HTML element to render as */
  as?: 'div' | 'span' | 'section' | 'article' | 'nav' | 'aside' | 'header' | 'footer';
}
