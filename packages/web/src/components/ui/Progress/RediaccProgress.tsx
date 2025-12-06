import { forwardRef } from 'react';
import { StyledRediaccProgress, resolveProgressHeight, resolveCircleWidth } from './RediaccProgress.styles';
import type { RediaccProgressProps } from './RediaccProgress.types';

export const RediaccProgress = forwardRef<HTMLDivElement, RediaccProgressProps>(
  (
    {
      variant = 'line',
      size = 'md',
      percent = 0,
      status = 'normal',
      showInfo = true,
      strokeWidth,
      strokeColor,
      trailColor,
      ...rest
    },
    ref
  ) => {
    // Use size-based defaults if strokeWidth not provided
    const resolvedStrokeWidth = strokeWidth ?? (variant === 'line'
      ? resolveProgressHeight(size)
      : 6);

    // Use size-based width for circle
    const circleWidth = variant === 'circle' ? resolveCircleWidth(size) : undefined;

    return (
      <StyledRediaccProgress
        ref={ref}
        type={variant}
        $variant={variant}
        $size={size}
        $status={status}
        percent={percent}
        status={status}
        showInfo={showInfo}
        strokeWidth={resolvedStrokeWidth}
        strokeColor={strokeColor}
        trailColor={trailColor}
        size={circleWidth}
        {...rest}
      />
    );
  }
);

RediaccProgress.displayName = 'RediaccProgress';
