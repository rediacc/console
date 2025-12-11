import React from 'react';
import { LoadingContainer } from './styles';

export interface InlineLoadingIndicatorProps {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  className?: string;
  style?: React.CSSProperties;
  'data-testid'?: string;
  'aria-label'?: string;
}

/**
 * Lightweight skeleton-style indicator for inline loading states.
 * Uses the global skeleton shimmer utility to stay consistent with other placeholders.
 */
const InlineLoadingIndicator: React.FC<InlineLoadingIndicatorProps> = ({
  width = 120,
  height = 20,
  borderRadius = 6,
  className,
  style,
  'data-testid': dataTestId,
  'aria-label': ariaLabel = 'loading',
}) => {
  const classes = ['skeleton-shimmer', className].filter(Boolean).join(' ');

  return (
    <LoadingContainer
      className={classes}
      $width={width}
      $height={height}
      $borderRadius={borderRadius}
      style={style}
      data-testid={dataTestId}
      aria-label={ariaLabel}
    />
  );
};

export default InlineLoadingIndicator;
