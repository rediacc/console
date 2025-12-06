import type { ReactNode, CSSProperties } from 'react';

export type StackDirection = 'horizontal' | 'vertical';
export type StackGap = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl';
export type StackAlign = 'start' | 'center' | 'end' | 'stretch' | 'baseline';
export type StackJustify = 'start' | 'center' | 'end' | 'between' | 'around';

export interface RediaccStackProps {
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
