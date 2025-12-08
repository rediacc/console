import type { CSSProperties, ReactNode } from 'react';

export type ListVariant = 'default' | 'bordered' | 'card';
export type ListSize = 'sm' | 'md';

export interface RediaccListProps<T = unknown> {
  /** List style variant */
  variant?: ListVariant;
  /** Size affects padding */
  size?: ListSize;
  /** Show dividers between items */
  split?: boolean;
  /** Data source for list items */
  dataSource?: T[];
  /** Render function for each item */
  renderItem?: (item: T, index: number) => ReactNode;
  /** List header */
  header?: ReactNode;
  /** List footer */
  footer?: ReactNode;
  /** Loading state */
  loading?: boolean;
  /** Empty state content */
  locale?: { emptyText: ReactNode };
  /** Row key getter */
  rowKey?: string | ((item: T) => string);
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
