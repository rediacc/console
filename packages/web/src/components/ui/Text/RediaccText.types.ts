import type { ReactNode, CSSProperties } from 'react';

/**
 * Text variants for different use cases
 */
export type TextVariant = 'caption'; // Small text

/**
 * Font size scale
 */
export type TextSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

/**
 * Font weight scale
 */
export type TextWeight = 'regular' | 'medium' | 'semibold' | 'bold';

/**
 * Text color options
 */
export type TextColor =
  | 'primary' // Main text color
  | 'secondary' // Secondary text color
  | 'tertiary' // Tertiary text color
  | 'muted' // Muted text color
  | 'danger' // Error/danger color
  | 'success' // Success color
  | 'warning' // Warning color
  | 'info' // Info color
  | 'inherit'; // Inherit from parent

/**
 * Text alignment options
 */
export type TextAlign = 'left' | 'center' | 'right';

/**
 * HTML element to render as
 */
export type TextElement = 'span' | 'p' | 'div' | 'label';
export type RediaccTextRef =
  | HTMLSpanElement
  | HTMLDivElement
  | HTMLParagraphElement
  | HTMLLabelElement;

export interface RediaccTextProps {
  /** Visual style variant - applies preset styling */
  variant?: TextVariant;
  /** Font size override */
  size?: TextSize;
  /** Font weight override */
  weight?: TextWeight;
  /** Deprecated: use color="muted" instead */
  muted?: boolean;
  /** Text color */
  color?: TextColor;
  /** Text alignment */
  align?: TextAlign;
  /** Truncate text with ellipsis */
  truncate?: boolean;
  /** Maximum number of lines before truncating (requires truncate: true) */
  maxLines?: number;
  /** Render as inline code (monospace) */
  code?: boolean;
  /** HTML element to render */
  as?: TextElement;
  /** Text content */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
  /** HTML id attribute */
  id?: string;
  /** Click handler */
  onClick?: () => void;
  /** Enable copy functionality */
  copyable?: boolean | { text?: string; onCopy?: () => void };
  /** Enable ellipsis with optional configuration */
  ellipsis?: boolean | { rows?: number; expandable?: boolean; onExpand?: () => void };
}
