import type { ReactNode, CSSProperties } from 'react';

export type CardVariant = 'default' | 'section' | 'selectable' | 'bordered' | 'elevated';
export type CardSize = 'sm' | 'md' | 'lg';

export interface RediaccCardProps {
  /** Visual style variant */
  variant?: CardVariant;
  /** Padding size: sm (12px), md (16px), lg (24px) */
  size?: CardSize;
  /** For selectable variant - shows selected state */
  selected?: boolean;
  /** Enable hover effects */
  interactive?: boolean;
  /** Stretch to full container width */
  fullWidth?: boolean;
  /** Remove all padding */
  noPadding?: boolean;
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
