import type { CSSProperties, ReactNode } from 'react';
import type { TooltipPlacement } from 'antd/es/tooltip';

export type TooltipVariant = 'default' | 'info' | 'warning' | 'error' | 'success';

export interface RediaccTooltipProps {
  /** Content to display in the tooltip */
  title: ReactNode;
  /** Visual style variant */
  variant?: TooltipVariant;
  /** Tooltip placement relative to target */
  placement?: TooltipPlacement;
  /** Whether the tooltip arrow is visible */
  arrow?: boolean;
  /** Open state (controlled) */
  open?: boolean;
  /** Callback when visibility changes */
  onOpenChange?: (open: boolean) => void;
  /** Trigger mode */
  trigger?: 'hover' | 'focus' | 'click' | ('hover' | 'focus' | 'click')[];
  /** Mouse enter delay in seconds */
  mouseEnterDelay?: number;
  /** Mouse leave delay in seconds */
  mouseLeaveDelay?: number;
  /** Tooltip z-index */
  zIndex?: number;
  /** Element the tooltip wraps */
  children: ReactNode;
  /** Additional class name for tooltip overlay */
  overlayClassName?: string;
  /** Inline styles for tooltip overlay */
  overlayStyle?: CSSProperties;
  /** Custom overlay inner style */
  overlayInnerStyle?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
}
