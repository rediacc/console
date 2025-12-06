import { forwardRef } from 'react';
import { StyledRediaccBadge } from './RediaccBadge.styles';
import type { RediaccBadgeProps } from './RediaccBadge.types';

export const RediaccBadge = forwardRef<HTMLSpanElement, RediaccBadgeProps>(
  (
    {
      variant = 'default',
      size = 'md',
      count,
      dot = false,
      showZero = false,
      overflowCount = 99,
      children,
      offset,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccBadge
        ref={ref}
        $variant={variant}
        $size={size}
        count={count}
        dot={dot}
        showZero={showZero}
        overflowCount={overflowCount}
        offset={offset}
        {...rest}
      >
        {children}
      </StyledRediaccBadge>
    );
  }
);

RediaccBadge.displayName = 'RediaccBadge';
