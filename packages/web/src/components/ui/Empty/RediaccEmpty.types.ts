import type { ReactNode, CSSProperties } from 'react';

export type EmptyVariant = 'default' | 'minimal' | 'illustrated';
export type EmptySize = 'sm' | 'md' | 'lg';

export interface RediaccEmptyProps {
  /** Empty state variant */
  variant?: EmptyVariant;
  /** Size affects padding and icon size */
  size?: EmptySize;
  /** Title text */
  title?: ReactNode;
  /** Description text */
  description?: ReactNode;
  /** Custom icon/image */
  image?: ReactNode;
  /** Action element (button, link) */
  action?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
