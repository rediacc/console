import type { ReactNode, MouseEvent } from 'react';

export type TagVariant =
  | 'default'
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'neutral';

export type TagSize = 'sm' | 'md' | 'lg';

// Semantic presets for common domain concepts
export type TagPreset =
  | 'team'
  | 'machine'
  | 'bridge'
  | 'region';

export interface RediaccTagProps {
  /** Visual style variant */
  variant?: TagVariant;
  /** Tag size: sm (XS font), md (SM font), lg (BASE font) */
  size?: TagSize;
  /** Semantic preset for domain concepts (overrides variant) */
  preset?: TagPreset;
  /** Remove border */
  borderless?: boolean;
  /** Icon element to render before children */
  icon?: ReactNode;
  /** Show close button */
  closable?: boolean;
  /** Close handler */
  onClose?: (e: MouseEvent<HTMLElement>) => void;
  /** Tag content */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Test identifier */
  'data-testid'?: string;
}
