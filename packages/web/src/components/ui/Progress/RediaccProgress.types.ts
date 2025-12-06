import type { CSSProperties } from 'react';

export type ProgressVariant = 'line' | 'circle';
export type ProgressSize = 'sm' | 'md' | 'lg';
export type ProgressStatus = 'normal' | 'success' | 'exception' | 'active';

export interface RediaccProgressProps {
  /** Progress display type */
  variant?: ProgressVariant;
  /** Size of the progress bar/circle */
  size?: ProgressSize;
  /** Current progress percentage (0-100) */
  percent?: number;
  /** Status/color of progress */
  status?: ProgressStatus;
  /** Show percentage text */
  showInfo?: boolean;
  /** Width of the progress bar stroke */
  strokeWidth?: number;
  /** Custom color */
  strokeColor?: string;
  /** Trail color (background) */
  trailColor?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
