import type { ReactNode, CSSProperties } from 'react';

export type CardVariant = 'default' | 'section' | 'selectable' | 'bordered' | 'elevated';
export type CardSize = 'sm' | 'md' | 'lg';

/**
 * Card spacing variants for margin-bottom control
 */
export type CardSpacing = 'none' | 'compact' | 'default' | 'spacious';

export interface RediaccCardProps {
  /** Visual style variant */
  variant?: CardVariant;
  /** Padding size: sm (12px), md (16px), lg (24px) */
  size?: CardSize;
  /** For selectable variant - shows selected state */
  selected?: boolean;
  /** Enable hover effects */
  interactive?: boolean;
  /** Enable hover effects (alias for interactive) */
  hoverable?: boolean;
  /** Stretch to full container width */
  fullWidth?: boolean;
  /** Stretch to full container height */
  fullHeight?: boolean;
  /** Margin-bottom spacing: none (0), compact (sm), default (md), spacious (lg) */
  spacing?: CardSpacing;
  /** Remove all padding */
  noPadding?: boolean;
  /** Card title (renders a header section) */
  title?: ReactNode;
  /** Extra content in the header (top right) */
  extra?: ReactNode;
  /** Card content */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
  /** Click handler (for interactive cards) */
  onClick?: () => void;
}
